"""Cruza as posições de uma carteira pessoal com o ranking da semana. Um comando só.

uso: python src/minha_carteira.py [--semana PASTA | --ranking ARQUIVO_OU_URL] [--csv ARQUIVO | --pluggy] [--salvar ARQUIVO]
       python src/minha_carteira.py --configurar | --plano | --esquecer

Fonte das posições (nesta ordem, se nada for indicado):
    1. --csv ARQUIVO              CSV com ticker;quantidade[;preco_medio][;preco_atual]
    2. --pluggy, ou as variáveis PLUGGY_CLIENT_ID, PLUGGY_CLIENT_SECRET e PLUGGY_ITEM_IDS
       definidas (MeuPluggy / Open Finance, somente leitura; veja src/pluggy_posicoes.py)
    3. a configuração salva por --configurar (feita uma vez; vale nas próximas execuções)
    4. entrada/posicoes.csv

Plano (opcional): --plano pergunta horizonte, objetivo, queda tolerada e limites de concentração
e salva em ~/.config/advogado-do-diabo/plano.json; com ele, o relatório reavalia a carteira no seu
prazo e contra a sua tolerância. --sem-plano ignora o plano numa execução.

--configurar guarda Client ID, Client Secret e Item ID(s) em ~/.config/advogado-do-diabo/config.json
(permissão só do seu usuário, fora de qualquer repositório); --esquecer apaga esse arquivo.

Ranking: a pasta semana_* mais recente (na pasta atual ou na do projeto) com sintese.json; --semana
indica outra; --ranking ARQUIVO_OU_URL usa um ranking publicado (gerado por src/publicar_ranking.py).
Sem nenhuma das duas, baixa o ranking publicado do projeto. Nesse modo nada é gravado em disco,
só impresso; use --salvar ARQUIVO se quiser guardar o relatório.

O CSV aceita separador ; ou , e decimal com vírgula. Cabeçalhos (sem acento, qualquer caixa):
ticker/ativo/codigo, quantidade/qtd/qtde, preco_medio/pm, preco_atual/cotacao.

Lê sintese.json (ranking) e xp.json da semana, sem rede (a Pluggy usa rede só se pedida).
Grava minha_carteira.json e minha_carteira.md na pasta da semana, que não é versionada, e imprime
o relatório no terminal. Chaves e posições nunca são gravadas em arquivo versionado.

A saída descreve como o modelo classificou o que você já tem. Não é recomendação personalizada:
ignora seu perfil, seus objetivos e seus impostos.
"""
import argparse
import csv
import getpass
import glob
import io
import json
import math
import os
import re
import sys
import unicodedata
import urllib.request

import carteira as C
import plano as PL

ALIAS = {
    'ticker': {'ticker', 'ativo', 'codigo', 'papel', 'simbolo'},
    'quantidade': {'quantidade', 'qtd', 'qtde', 'quant'},
    'preco_medio': {'preco medio', 'pm', 'preco medio r', 'custo medio', 'pm r'},
    'preco_atual': {'preco atual', 'cotacao', 'preco', 'ultimo preco'},
}
LIMITE_ATIVO_PCT = 25.0     # uma posição acima disso é sinalizada
LIMITE_SETOR_PCT = 40.0     # um setor acima disso é sinalizado
LIMITE_COBERTURA_PCT = 50.0  # abaixo disso, o cruzamento cobre pouco da carteira


def _norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^\w\s]', ' ', s.lower()).replace('_', ' ')
    return re.sub(r'\s+', ' ', s).strip()


def _num(txt, virgula_milhar=False):
    """'1.234,56' -> 1234.56; '1.000' -> 1000; '42.10' -> 42.1; vazio -> None.

    virgula_milhar=True (arquivo separado por vírgula): '1,000' é mil, não um.
    """
    t = str(txt).strip().replace('R$', '').replace(' ', '')
    if not t:
        return None
    if virgula_milhar and re.fullmatch(r'\d{1,3}(,\d{3})+(\.\d+)?', t):
        t = t.replace(',', '')
    elif ',' in t:
        t = t.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(\.\d{3})+', t):   # "1.000" no Brasil é mil
        t = t.replace('.', '')
    try:
        v = float(t)
    except ValueError:
        raise ValueError(f'número inválido: {txt!r}')
    if not math.isfinite(v):
        raise ValueError(f'número inválido: {txt!r}')
    return v


def _ticker(t):
    """'petr4f' -> 'PETR4' (lote fracionário vira o papel do lote padrão)."""
    t = str(t).strip().upper()
    if t.endswith('.SA'):
        t = t[:-3]
    m = re.fullmatch(r'([A-Z]{4}\d{1,2})F', t)
    return m.group(1) if m else t


def ler_posicoes(texto):
    """Lê o CSV e soma linhas repetidas do mesmo ticker (preço médio ponderado pela quantidade)."""
    amostra = texto[:2048]
    cont = {sep: amostra.count(sep) for sep in (';', '\t', ',')}
    sep = max(cont, key=lambda k: (cont[k], k == ';'))   # empate favorece ';'
    leitor = csv.reader(io.StringIO(texto.lstrip('﻿')), delimiter=sep)
    linhas = [l for l in leitor if any(c.strip() for c in l)]
    if not linhas:
        raise ValueError('CSV vazio')
    cab = [_norm(c) for c in linhas[0]]
    idx = {}
    for campo, nomes in ALIAS.items():
        for i, c in enumerate(cab):
            if c in nomes:
                idx[campo] = i
                break
    for obrigatorio in ('ticker', 'quantidade'):
        if obrigatorio not in idx:
            raise ValueError(f'coluna "{obrigatorio}" não encontrada; cabeçalho lido: {linhas[0]}')
    agg = {}
    for n, l in enumerate(linhas[1:], start=2):
        try:
            if max(idx['ticker'], idx['quantidade']) >= len(l):
                raise ValueError('faltam colunas (ticker ou quantidade)')
            vm = sep == ','
            tk = _ticker(l[idx['ticker']])
            q = _num(l[idx['quantidade']], vm)
            pm = _num(l[idx['preco_medio']], vm) if 'preco_medio' in idx and idx['preco_medio'] < len(l) else None
            pa = _num(l[idx['preco_atual']], vm) if 'preco_atual' in idx and idx['preco_atual'] < len(l) else None
        except ValueError as e:
            raise ValueError(f'linha {n}: {e}')
        if not tk or q is None or q <= 0:
            continue
        a = agg.setdefault(tk, {'quantidade': 0.0, 'custo': 0.0, 'com_pm': 0.0, 'atual': 0.0, 'com_pa': 0.0})
        a['quantidade'] += q
        if pa is not None:
            a['atual'] += q * pa
            a['com_pa'] += q
        if pm is not None:
            a['custo'] += q * pm
            a['com_pm'] += q
    return [{'ticker': tk, 'quantidade': a['quantidade'],
             'preco_medio': round(a['custo'] / a['com_pm'], 4) if a['com_pm'] else None,
             'preco_atual': round(a['atual'] / a['com_pa'], 4) if a['com_pa'] else None}
            for tk, a in agg.items()]


def _f(x):
    """Número finito ou None (texto, nan e inf viram None)."""
    try:
        v = float(str(x).replace(',', '.')) if isinstance(x, str) else float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def cruzar(posicoes, ranking, pesos_xp=None, plano=None):
    """Junta posições ao ranking. Devolve o dicionário que vira minha_carteira.json.

    `plano` (de plano.ler_plano) troca os limites de concentração e acrescenta a leitura por
    horizonte e o risco contra a tolerância.
    """
    lim_ativo = plano['limite_ativo_pct'] if plano else LIMITE_ATIVO_PCT
    lim_setor = plano['limite_setor_pct'] if plano else LIMITE_SETOR_PCT
    por_tk = {}
    for r in ranking if isinstance(ranking, list) else []:
        if isinstance(r, dict) and isinstance(r.get('ticker'), str):
            r = dict(r)
            for k in ('nota', 'preco_atual', 'upside_ajustado_pct', 'vol_90pregoes_anual_pct'):
                r[k] = _f(r.get(k))
            por_tk.setdefault(r['ticker'].strip().upper(), r)
    pesos_xp = pesos_xp if isinstance(pesos_xp, dict) else {}
    linhas, sem_preco = [], []
    for p in posicoes:
        r = por_tk.get(p['ticker'])
        preco, origem = None, None
        if p.get('preco_atual') is not None:
            preco, origem = p['preco_atual'], 'preço informado por você/corretora'
        elif r and r.get('preco_atual') is not None:
            preco, origem = r['preco_atual'], f"cotação de {r.get('data_cotacao', 'data n/d')} (relatório da semana)"
        elif p['preco_medio'] is not None:
            preco, origem = p['preco_medio'], 'preço médio informado (sem cotação do relatório)'
        valor = round(preco * p['quantidade'], 2) if preco is not None else None
        if valor is None:
            sem_preco.append(p['ticker'])
        linha = {
            'ticker': p['ticker'], 'quantidade': p['quantidade'], 'preco_medio': p['preco_medio'],
            'preco_usado': preco, 'origem_preco': origem, 'valor': valor,
            'no_ranking': r is not None,
            'setor': r.get('setor') if r else None,
            'posicao_ranking': r.get('posicao') if r else None,
            'nota': r.get('nota') if r else None,
            'acao_modelo': r.get('acao_sugerida') if r else None,
            'certeza': r.get('certeza') if r else None,
            'upside_ajustado_pct': r.get('upside_ajustado_pct') if r else None,
            'peso_xp_pct': pesos_xp.get(p['ticker']),
            'vol_anual_pct': r.get('vol_90pregoes_anual_pct') if r else None,
            'valuation_margem_pct': r.get('valuation_margem_pct') if r else None,
        }
        if plano and r:
            linha['nota_horizonte'] = PL.nota_no_horizonte(r.get('componentes'), plano['horizonte'], r.get('nota'))
        if preco is not None and p['preco_medio']:
            linha['resultado_vs_preco_medio_pct'] = round((preco / p['preco_medio'] - 1) * 100, 1)
        linhas.append(linha)

    total = sum(l['valor'] for l in linhas if l['valor'] is not None)
    for l in linhas:
        l['peso_pct'] = round(l['valor'] / total * 100, 1) if total and l['valor'] is not None else None
    linhas.sort(key=lambda l: -(l['valor'] or 0))

    def soma(filtro):
        return round(sum(l['peso_pct'] or 0 for l in linhas if filtro(l)), 1)

    cobertura = soma(lambda l: l['no_ranking'])
    por_acao, por_setor = {}, {}
    for l in linhas:
        if l['no_ranking']:
            ac, st = l['acao_modelo'] or 'n/d', l['setor'] or 'n/d'
            por_acao[ac] = round(por_acao.get(ac, 0) + (l['peso_pct'] or 0), 1)
            por_setor[st] = round(por_setor.get(st, 0) + (l['peso_pct'] or 0), 1)
    cobertos = [l for l in linhas if l['no_ranking'] and l['peso_pct'] and l['nota'] is not None]
    base = sum(l['peso_pct'] for l in cobertos)
    nota_media = round(sum(l['nota'] * l['peso_pct'] for l in cobertos) / base, 2) if base else None
    hhi = round(sum((l['peso_pct'] / 100) ** 2 for l in linhas if l['peso_pct']) * 10000)

    alertas = []
    for l in linhas:
        if (l['peso_pct'] or 0) > lim_ativo:
            alertas.append(f"{l['ticker']} é {_pct(l['peso_pct'])} da carteira (limite {'seu' if plano else 'de atenção'}: {lim_ativo:.0f}%).")
    for s, v in por_setor.items():
        if v > lim_setor:
            alertas.append(f"Setor {s} soma {_pct(v)} da carteira (limite {'seu' if plano else 'de atenção'}: {lim_setor:.0f}%).")
    if cobertura < LIMITE_COBERTURA_PCT:
        alertas.append(f'Só {_pct(cobertura)} da carteira está entre as ações analisadas; o cruzamento cobre pouco.')
    if sem_preco:
        alertas.append('Sem preço (fora do ranking e sem preço médio), ficaram de fora dos pesos: ' + ', '.join(sem_preco) + '.')

    xp_ausentes = sorted(tk for tk in pesos_xp if tk not in {l['ticker'] for l in linhas})
    res_plano = None
    if plano:
        com_nota = [l for l in linhas if l.get('nota_horizonte') is not None]
        res_plano = {
            **plano,
            'risco': PL.risco_vs_tolerancia(linhas, plano['horizonte'], plano['queda_max_pct']),
            'ordem_no_horizonte': [l['ticker'] for l in sorted(com_nota, key=lambda l: -l['nota_horizonte'])],
        }
    resultado = {
        'valor_total': round(total, 2),
        'n_posicoes': len(linhas),
        'sem_preco': sem_preco,
        'cobertura_ranking_pct': cobertura,
        'fora_do_ranking': [l['ticker'] for l in linhas if not l['no_ranking']],
        'peso_por_acao_modelo_pct': por_acao,
        'peso_por_setor_pct': dict(sorted(por_setor.items(), key=lambda kv: -kv[1])),
        'nota_media_ponderada': nota_media,
        'concentracao': {'maior_posicao_pct': linhas[0]['peso_pct'] if linhas else None,
                         'top3_pct': round(sum(l['peso_pct'] or 0 for l in linhas[:3]), 1),
                         'hhi': hhi},
        'alertas': alertas,
        'carteira_xp_sem_posicao': xp_ausentes,
        'posicoes': linhas,
    }
    if res_plano:
        resultado['plano'] = res_plano
    return resultado


def _brl(v):
    return 'n/d' if v is None else 'R$ ' + f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _pct(v):
    return 'n/d' if v is None else f'{v:.1f}%'.replace('.', ',')


def _secao_plano(res):
    p = res['plano']
    h = PL.horizontes()[p['horizonte']]
    o = ['', f"## Seu plano: {p['horizonte']} ({h['descricao']}), objetivo {p['objetivo']}", '',
         f"Seus limites: até {p['limite_ativo_pct']:.0f}% em uma ação, {p['limite_setor_pct']:.0f}% em um setor; "
         f"queda tolerada de {p['queda_max_pct']:.0f}%."]
    r = p.get('risco')
    if r:
        o += ['', f"- **Risco:** volatilidade anual estimada de {_pct(r['vol_anual_pct'])} (limite superior: supõe que as "
                  f"ações caem juntas; cobre {_pct(r['cobertura_peso_pct'])} da carteira). Um movimento de 1 desvio-padrão "
                  f"no prazo do seu plano é de cerca de {_pct(r['movimento_1dp_pct'])}, "
                  + ('**acima** da queda que você tolera.' if r['acima_da_tolerancia'] else 'dentro da queda que você tolera.')]
    else:
        o += ['', '- **Risco:** o ranking usado não traz volatilidade; atualize para a versão mais recente.']
    if p['objetivo'] == 'renda':
        o.append('- O modelo não mede dividendos nem renda; a nota não responde ao seu objetivo de renda.')
    if p['horizonte'] != 'semanas':
        com = [l for l in res['posicoes'] if l.get('nota_horizonte') is not None]
        if com:
            ordem = {tk: i for i, tk in enumerate(p['ordem_no_horizonte'], 1)}
            o += ['', 'Nota recalculada com pesos para o seu horizonte (premissa do projeto, não validada):', '',
                  '| Ticker | Nota semanal | Nota no seu horizonte | Diferença | Ordem na sua carteira |',
                  '|---|---:|---:|---:|---:|']
            for l in sorted(com, key=lambda l: ordem[l['ticker']]):
                dif = l['nota_horizonte'] - l['nota']
                o.append(f"| {l['ticker']} | {l['nota']:.2f} | {l['nota_horizonte']:.2f} | {dif:+.2f} | {ordem[l['ticker']]} |".replace('.', ','))
        else:
            o.append('- O ranking usado não traz os componentes da nota; atualize para a versão mais recente.')
    if p['horizonte'] == 'anos':
        o += ['', '> Em prazos de anos a evidência do modelo semanal é fraca: a nota foi calibrada para semanas. '
                  'Prefira os cenários de valuation abaixo e os dossiês de cada ação.']
        val = [l for l in res['posicoes'] if l.get('valuation_margem_pct')]
        if val:
            o += ['', 'Margem do valor justo sobre o preço (negativa = valor justo abaixo do preço):', '',
                  '| Ticker | Bear | Base | Bull |', '|---|---:|---:|---:|']
            for l in val:
                m = l['valuation_margem_pct']
                o.append(f"| {l['ticker']} | {_pct(m.get('bear'))} | {_pct(m.get('base'))} | {_pct(m.get('bull'))} |")
        else:
            o.append('- Cenários de valuation indisponíveis neste ranking.')
    return o


def md(res, data_semana):
    quando = f'da semana de {C.data_br(data_semana)}' if data_semana else '(data não informada)'
    o = [f'# Minha carteira x ranking {quando}', '',
         '> Classificação do modelo sobre as ações que você já tem. **Não é recomendação de investimento**: '
         'ignora seu perfil, objetivos e impostos. Veja o aviso legal do projeto.', '',
         f"Valor total: **{_brl(res['valor_total'])}** em {res['n_posicoes']} posições. "
         f"Cobertura do ranking: **{_pct(res['cobertura_ranking_pct'])}** da carteira."]
    if res.get('sem_preco'):
        o.append(f"Atenção: {len(res['sem_preco'])} posição(ões) sem preço ({', '.join(res['sem_preco'])}) ficaram "
                 'fora do valor total e dos percentuais; informe `preco_atual` ou `preco_medio` no CSV.')
    if res['nota_media_ponderada'] is not None:
        o.append(f"Nota média ponderada (só ações do ranking): **{str(res['nota_media_ponderada']).replace('.', ',')}**.")
    if res['alertas']:
        o += ['', '## Pontos de atenção', ''] + [f'- {a}' for a in res['alertas']]
    o += ['', '## Posições', '',
          '| Ticker | Peso | Valor | Setor | Posição no ranking | Nota | Modelo | Certeza | Upside ajust. | Peso na XP |',
          '|---|---:|---:|---|---:|---:|---|---|---:|---:|']
    for l in res['posicoes']:
        o.append('| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |'.format(
            l['ticker'], _pct(l['peso_pct']), _brl(l['valor']), l['setor'] or 'fora do ranking',
            l['posicao_ranking'] or '-', str(l['nota']).replace('.', ',') if l['nota'] is not None else '-',
            l['acao_modelo'] or '-', l['certeza'] or '-', _pct(l['upside_ajustado_pct']) if l['upside_ajustado_pct'] is not None else '-',
            _pct(l['peso_xp_pct']) if l['peso_xp_pct'] is not None else '-'))
    if res.get('plano'):
        o += _secao_plano(res)
    if res['peso_por_acao_modelo_pct']:
        o += ['', '## Por classificação do modelo', ''] + [f'- {k}: {_pct(v)}' for k, v in res['peso_por_acao_modelo_pct'].items()]
    if res['peso_por_setor_pct']:
        o += ['', '## Por setor', ''] + [f'- {k}: {_pct(v)}' for k, v in res['peso_por_setor_pct'].items()]
    if res['carteira_xp_sem_posicao']:
        o += ['', '## Na carteira da XP e não na sua', '', ', '.join(res['carteira_xp_sem_posicao'])]
    o.append('')
    return '\n'.join(o)


def _enriquecer(ranking, pasta):
    """Acrescenta a cada ação a volatilidade e o beta (risco.json) e a margem do valuation
    (dossie.json), quando esses arquivos existem na pasta da semana."""
    risco = C.ler(os.path.join(pasta, 'risco.json'), {}).get('tabela_por_ticker', {})
    dossie = C.ler(os.path.join(pasta, 'dossie.json'), {}).get('tickers', [])
    if isinstance(dossie, dict):
        dossie = list(dossie.values())
    margens = {}
    for d in dossie:
        v = d.get('valuation') or {}
        if v.get('status') == 'ok' and isinstance(v.get('cenarios'), dict):
            margens[d.get('ticker')] = {k: round(c['margem_pct'], 1) for k, c in v['cenarios'].items()
                                        if isinstance(c.get('margem_pct'), (int, float))}
    saida = []
    for r in ranking:
        r = dict(r)
        rk = risco.get(r.get('ticker'), {})
        r['vol_90pregoes_anual_pct'] = rk.get('vol_90pregoes_anual_pct')
        r['beta_ibov_multifator'] = rk.get('beta_ibov_multifator')
        r['valuation_margem_pct'] = margens.get(r.get('ticker'))
        saida.append(r)
    return saida


def carregar_semana(pasta):
    """(ranking, pesos_xp, data) da pasta da semana, sem rede."""
    sintese = C.ler(os.path.join(pasta, 'sintese.json'))
    try:
        xp = C.ler(C.arquivo_xp(pasta))
        pesos_xp = {a['ticker']: a.get('peso_atual') for a in xp.get('acoes', [])}
    except (FileNotFoundError, SystemExit):
        pesos_xp = {}
    return _enriquecer(sintese['ranking'], pasta), pesos_xp, sintese.get('data', '')


RANKING_URL = 'https://raw.githubusercontent.com/jocaparra/advogado-do-diabo/main/publico/ranking.json'
MAX_BYTES = 2_000_000


def carregar_publico(origem):
    """(ranking, pesos_xp, data) de um ranking.json publicado: arquivo local ou URL https."""
    if re.match(r'https?://', origem):
        if not origem.startswith('https://'):
            sys.exit('use uma URL https para o ranking')
        try:
            with urllib.request.urlopen(origem, timeout=20) as r:
                bruto = r.read(MAX_BYTES + 1)
        except OSError as e:
            sys.exit(f'não consegui baixar o ranking ({e}). Use --semana ou --ranking com um arquivo local.')
        if len(bruto) > MAX_BYTES:
            sys.exit('ranking publicado grande demais; abortei')
        try:
            dados = json.loads(bruto)
        except ValueError:
            sys.exit('o ranking baixado não é um JSON válido')
    else:
        try:
            dados = C.ler(os.path.abspath(origem))
        except (OSError, ValueError) as e:
            sys.exit(f'não consegui ler o ranking: {e}')
    if not isinstance(dados, dict) or not isinstance(dados.get('ranking'), list):
        sys.exit('ranking.json inválido: falta a lista "ranking"')
    pesos = dados.get('pesos_xp')
    return dados['ranking'], (pesos if isinstance(pesos, dict) else {}), str(dados.get('data') or '')


CAMPOS_PUBLICOS = ('posicao', 'ticker', 'setor', 'nota', 'acao_sugerida', 'certeza', 'preco_atual',
                   'data_cotacao', 'upside_ajustado_pct', 'componentes', 'vol_90pregoes_anual_pct',
                   'beta_ibov_multifator', 'valuation_margem_pct')


def exportar_publico(pasta):
    """ranking.json enxuto da semana: só o que o cruzamento usa, sem preços-alvo da XP nem textos."""
    ranking, pesos_xp, data = carregar_semana(pasta)
    return {'versao': 2, 'data': data,
            'aviso': 'Classificação de um modelo, não recomendação de investimento.',
            'ranking': [{k: r.get(k) for k in CAMPOS_PUBLICOS} for r in ranking],
            'pesos_xp': pesos_xp}


def _semana_recente():
    """Pasta semana_* mais recente com sintese.json (pasta atual, depois a do projeto) ou None."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    achadas = []
    for base in dict.fromkeys([os.getcwd(), raiz]):
        achadas += glob.glob(os.path.join(base, 'semana_*', 'sintese.json'))
    achadas.sort(key=lambda a: os.path.basename(os.path.dirname(a)), reverse=True)
    return os.path.dirname(achadas[0]) if achadas else None


AJUDA_FONTE = """Não encontrei suas posições ({caminho}).

Escolha um caminho:

  A) Arquivo com suas ações (mais rápido). Crie minhas_acoes.csv assim:

         ticker;quantidade
         PRIO3;10
         ITUB4;5

     e rode:  npx advogado-do-diabo@latest --csv minhas_acoes.csv

  B) Direto da corretora (MeuPluggy, grátis, feito uma vez):
     1. meu.pluggy.ai            conecte sua corretora pelo Open Finance
     2. dashboard.pluggy.ai      crie uma aplicação e copie Client ID e Client Secret
     3. Demo da aplicação        conecte pelo MeuPluggy e copie o Item ID
     4. npx advogado-do-diabo@latest --configurar     (cola os 3 valores, uma vez)
        npx advogado-do-diabo@latest                  (nas próximas vezes, só isso)

Detalhes: https://github.com/jocaparra/advogado-do-diabo#cruze-com-a-sua-carteira-5-minutos"""


def _ler_csv(caminho):
    """Texto do CSV: UTF-8 (com ou sem BOM) ou, se falhar, Windows-1252 (Excel em português)."""
    with open(caminho, 'rb') as f:
        bruto = f.read()
    try:
        return bruto.decode('utf-8-sig')
    except UnicodeDecodeError:
        return bruto.decode('cp1252', errors='replace')


def caminho_config():
    """~/.config/advogado-do-diabo/config.json (ADVOGADO_DO_DIABO_CONFIG troca o caminho)."""
    return os.environ.get('ADVOGADO_DO_DIABO_CONFIG') or os.path.join(
        os.path.expanduser('~'), '.config', 'advogado-do-diabo', 'config.json')


def ler_config():
    """Credenciais salvas por --configurar, ou None."""
    try:
        with open(caminho_config(), encoding='utf-8') as f:
            c = json.load(f)
    except (OSError, ValueError):
        return None
    ok = c.get('client_id') and c.get('client_secret') and isinstance(c.get('item_ids'), list) and c['item_ids']
    return c if ok else None


def salvar_config(client_id, client_secret, item_ids):
    """Grava com permissão 0600 (só o dono lê), criando a pasta com 0700."""
    return PL.gravar_privado(caminho_config(), {'client_id': client_id, 'client_secret': client_secret,
                                                'item_ids': item_ids})


def _credenciais():
    """(client_id, secret, itens, origem): variáveis de ambiente primeiro, depois a configuração salva."""
    cid, sec = os.environ.get('PLUGGY_CLIENT_ID'), os.environ.get('PLUGGY_CLIENT_SECRET')
    itens = [x.strip() for x in os.environ.get('PLUGGY_ITEM_IDS', '').split(',') if x.strip()]
    if cid and sec and itens:
        return cid, sec, itens, 'variáveis de ambiente'
    c = ler_config()
    if c:
        return c['client_id'], c['client_secret'], c['item_ids'], 'configuração salva'
    return cid, sec, itens, None


def configurar():
    import pluggy_posicoes as P
    print('Configuração do MeuPluggy (feita uma vez). Os dados ficam só nesta máquina.\n'
          'Onde pegar cada valor: https://github.com/jocaparra/advogado-do-diabo#caminho-b-puxar-da-corretora-open-finance-grátis\n')
    try:
        cid = input('Client ID: ').strip()
        sec = getpass.getpass('Client Secret (não aparece enquanto digita): ').strip()
        itens = [x.strip() for x in input('Item ID (vários separados por vírgula): ').split(',') if x.strip()]
    except (EOFError, KeyboardInterrupt):
        sys.exit('\ncancelado; nada foi salvo.')
    if not (cid and sec and itens):
        sys.exit('preencha Client ID, Client Secret e ao menos um Item ID; nada foi salvo.')
    print('Testando a conexão...')
    try:
        pos, _ = P.baixar(cid, sec, itens)
    except P.PluggyErro as e:
        sys.exit(f'não consegui conectar: {e}\nNada foi salvo. Confira os três valores e tente de novo.')
    caminho = salvar_config(cid, sec, itens)
    print(f'ok: {len(pos)} ações/ETFs encontrados. Configuração salva em {caminho}')
    print('Daqui em diante basta rodar:  npx advogado-do-diabo@latest\n'
          'Para apagar:  npx advogado-do-diabo@latest --esquecer')


def definir_plano():
    print('Seu plano (feito uma vez; fica só nesta máquina). Enter aceita o valor entre colchetes.')
    try:
        plano = PL.assistente()
    except (EOFError, KeyboardInterrupt):
        sys.exit('\ncancelado; nada foi salvo.')
    caminho = PL.salvar_plano(plano)
    print(f'\nok: plano salvo em {caminho}\n'
          'Daqui em diante o relatório mostra a seção "Seu plano". Para ignorar numa execução: --sem-plano.')


def esquecer():
    caminho = caminho_config()
    try:
        os.remove(caminho)
        print(f'configuração apagada: {caminho}')
    except FileNotFoundError:
        print('não havia configuração salva.')
    if PL.apagar_plano():
        print(f'plano apagado: {PL.caminho_plano()}')


def _posicoes_pluggy():
    import pluggy_posicoes as P
    cid, sec, itens, origem = _credenciais()
    if not origem:
        sys.exit('MeuPluggy ainda não configurado. Rode uma vez:  npx advogado-do-diabo@latest --configurar')
    try:
        pos, ignorados = P.baixar(cid, sec, itens)
    except P.PluggyErro as e:
        sys.exit(str(e))
    print(f'Pluggy ({origem}): {len(pos)} ações/ETFs de {len(itens)} conexão(ões).')
    for g in ignorados:
        print('  não incluído:', g)
    return M_ler(P.csv_texto(pos))


def M_ler(texto):
    try:
        return ler_posicoes(texto)
    except ValueError as e:
        sys.exit(f'erro no CSV: {e}')


def main():
    ap = argparse.ArgumentParser(description='Cruza sua carteira com o ranking da semana.')
    ap.add_argument('--semana', help='pasta da semana (padrão: a mais recente)')
    ap.add_argument('--ranking', help='ranking publicado: arquivo .json ou URL https')
    ap.add_argument('--salvar', help='grava o relatório (.md) neste arquivo (modo ranking publicado)')
    ap.add_argument('--configurar', action='store_true', help='salva suas chaves do MeuPluggy (uma vez)')
    ap.add_argument('--esquecer', action='store_true', help='apaga a configuração e o plano salvos')
    ap.add_argument('--plano', action='store_true', help='define seu plano (horizonte, tolerância, limites) e salva')
    ap.add_argument('--sem-plano', action='store_true', help='ignora o plano salvo nesta execução')
    fonte = ap.add_mutually_exclusive_group()
    fonte.add_argument('--csv', help='CSV de posições')
    fonte.add_argument('--pluggy', action='store_true', help='ler posições do MeuPluggy (variáveis PLUGGY_*)')
    a = ap.parse_args()
    if a.configurar:
        return configurar()
    if a.esquecer:
        return esquecer()
    if a.plano:
        return definir_plano()

    if a.semana and a.ranking:
        sys.exit('use --semana ou --ranking, não os dois')
    pasta = C.pasta_semana(['x', a.semana]) if a.semana else (None if a.ranking else _semana_recente())
    tem_pluggy = _credenciais()[3] is not None
    if a.csv or (not a.pluggy and not tem_pluggy):
        caminho = os.path.abspath(a.csv or 'entrada/posicoes.csv')
        if os.path.isdir(caminho):
            sys.exit(f'{caminho} é uma pasta; informe o arquivo CSV com --csv.')
        if not os.path.isfile(caminho):
            sys.exit(AJUDA_FONTE.format(caminho=caminho))
        posicoes = M_ler(_ler_csv(caminho))
    else:
        posicoes = _posicoes_pluggy()

    if pasta:
        try:
            ranking, pesos_xp, data = carregar_semana(pasta)
        except (OSError, ValueError, KeyError) as e:
            sys.exit(f'não consegui ler a análise de {pasta}: {e}\n'
                     'A pasta precisa ter sintese.json (gerado por /semana). Use --ranking para um ranking publicado.')
    else:
        ranking, pesos_xp, data = carregar_publico(a.ranking or RANKING_URL)
    plano = None if a.sem_plano else PL.ler_plano()
    res = cruzar(posicoes, ranking, pesos_xp, plano)
    res['semana'] = data
    texto = md(res, data)
    print(texto)
    try:
        if pasta:
            with open(os.path.join(pasta, 'minha_carteira.json'), 'w', encoding='utf-8') as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
            destino = os.path.join(pasta, 'minha_carteira.md')
        else:
            destino = os.path.abspath(a.salvar) if a.salvar else None
        if destino:
            with open(destino, 'w', encoding='utf-8') as f:
                f.write(texto)
            print(f'(salvo em {destino})')
    except OSError as e:
        sys.exit(f'o relatório foi impresso, mas não consegui salvar: {e}')


if __name__ == '__main__':
    main()
