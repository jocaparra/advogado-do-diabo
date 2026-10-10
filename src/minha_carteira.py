"""Cruza as posições de uma carteira pessoal com o ranking da semana. Um comando só.

uso: python src/minha_carteira.py [--semana PASTA | --ranking ARQUIVO_OU_URL] [--csv ARQUIVO | --pluggy] [--salvar ARQUIVO]

Fonte das posições (nesta ordem, se nada for indicado):
    1. --csv ARQUIVO              CSV com ticker;quantidade[;preco_medio][;preco_atual]
    2. --pluggy, ou as variáveis PLUGGY_CLIENT_ID, PLUGGY_CLIENT_SECRET e PLUGGY_ITEM_IDS
       definidas (MeuPluggy / Open Finance, somente leitura; veja src/pluggy_posicoes.py)
    3. entrada/posicoes.csv

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
import glob
import io
import json
import os
import re
import sys
import unicodedata
import urllib.request

import carteira as C

ALIAS = {
    'ticker': {'ticker', 'ativo', 'codigo', 'papel', 'simbolo'},
    'quantidade': {'quantidade', 'qtd', 'qtde', 'quant'},
    'preco_medio': {'preco_medio', 'pm', 'preco medio', 'preco_medio_r', 'custo_medio'},
    'preco_atual': {'preco_atual', 'preco atual', 'cotacao', 'preco'},
}
LIMITE_ATIVO_PCT = 25.0     # uma posição acima disso é sinalizada
LIMITE_SETOR_PCT = 40.0     # um setor acima disso é sinalizado
LIMITE_COBERTURA_PCT = 50.0  # abaixo disso, o cruzamento cobre pouco da carteira


def _norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', s.strip().lower())


def _num(txt):
    """'1.234,56' -> 1234.56; '1.000' -> 1000; '42.10' -> 42.1; vazio -> None."""
    t = str(txt).strip().replace('R$', '').replace(' ', '')
    if not t:
        return None
    if ',' in t:
        t = t.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(\.\d{3})+', t):   # "1.000" no Brasil é mil
        t = t.replace('.', '')
    try:
        return float(t)
    except ValueError:
        raise ValueError(f'número inválido: {txt!r}')


def _ticker(t):
    """'petr4f' -> 'PETR4' (lote fracionário vira o papel do lote padrão)."""
    t = str(t).strip().upper()
    m = re.fullmatch(r'([A-Z]{4}\d{1,2})F', t)
    return m.group(1) if m else t


def ler_posicoes(texto):
    """Lê o CSV e soma linhas repetidas do mesmo ticker (preço médio ponderado pela quantidade)."""
    amostra = texto[:2048]
    sep = ';' if amostra.count(';') >= amostra.count(',') else ','
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
            tk = _ticker(l[idx['ticker']])
            q = _num(l[idx['quantidade']])
            pm = _num(l[idx['preco_medio']]) if 'preco_medio' in idx and idx['preco_medio'] < len(l) else None
            pa = _num(l[idx['preco_atual']]) if 'preco_atual' in idx and idx['preco_atual'] < len(l) else None
        except (ValueError, IndexError) as e:
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


def cruzar(posicoes, ranking, pesos_xp=None):
    """Junta posições ao ranking. Devolve o dicionário que vira minha_carteira.json."""
    por_tk = {r['ticker']: r for r in ranking}
    pesos_xp = pesos_xp or {}
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
        }
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
        if (l['peso_pct'] or 0) > LIMITE_ATIVO_PCT:
            alertas.append(f"{l['ticker']} é {_pct(l['peso_pct'])} da carteira (limite de atenção: {LIMITE_ATIVO_PCT:.0f}%).")
    for s, v in por_setor.items():
        if v > LIMITE_SETOR_PCT:
            alertas.append(f'Setor {s} soma {_pct(v)} da carteira (limite de atenção: {LIMITE_SETOR_PCT:.0f}%).')
    if cobertura < LIMITE_COBERTURA_PCT:
        alertas.append(f'Só {_pct(cobertura)} da carteira está entre as ações analisadas; o cruzamento cobre pouco.')
    if sem_preco:
        alertas.append('Sem preço (fora do ranking e sem preço médio), ficaram de fora dos pesos: ' + ', '.join(sem_preco) + '.')

    xp_ausentes = sorted(tk for tk in pesos_xp if tk not in {l['ticker'] for l in linhas})
    return {
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


def _brl(v):
    return 'n/d' if v is None else 'R$ ' + f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _pct(v):
    return 'n/d' if v is None else f'{v:.1f}%'.replace('.', ',')


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
    if res['peso_por_acao_modelo_pct']:
        o += ['', '## Por classificação do modelo', ''] + [f'- {k}: {_pct(v)}' for k, v in res['peso_por_acao_modelo_pct'].items()]
    if res['peso_por_setor_pct']:
        o += ['', '## Por setor', ''] + [f'- {k}: {_pct(v)}' for k, v in res['peso_por_setor_pct'].items()]
    if res['carteira_xp_sem_posicao']:
        o += ['', '## Na carteira da XP e não na sua', '', ', '.join(res['carteira_xp_sem_posicao'])]
    o.append('')
    return '\n'.join(o)


def carregar_semana(pasta):
    """(ranking, pesos_xp, data) da pasta da semana, sem rede."""
    sintese = C.ler(os.path.join(pasta, 'sintese.json'))
    try:
        xp = C.ler(C.arquivo_xp(pasta))
        pesos_xp = {a['ticker']: a.get('peso_atual') for a in xp.get('acoes', [])}
    except (FileNotFoundError, SystemExit):
        pesos_xp = {}
    return sintese['ranking'], pesos_xp, sintese.get('data', '')


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
    return dados['ranking'], dados.get('pesos_xp', {}), dados.get('data', '')


CAMPOS_PUBLICOS = ('posicao', 'ticker', 'setor', 'nota', 'acao_sugerida', 'certeza', 'preco_atual',
                   'data_cotacao', 'upside_ajustado_pct')


def exportar_publico(pasta):
    """ranking.json enxuto da semana: só o que o cruzamento usa, sem preços-alvo da XP nem textos."""
    ranking, pesos_xp, data = carregar_semana(pasta)
    return {'data': data,
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


def _ler_csv(caminho):
    """Texto do CSV: UTF-8 (com ou sem BOM) ou, se falhar, Windows-1252 (Excel em português)."""
    with open(caminho, 'rb') as f:
        bruto = f.read()
    try:
        return bruto.decode('utf-8-sig')
    except UnicodeDecodeError:
        return bruto.decode('cp1252', errors='replace')


def _posicoes_pluggy():
    import pluggy_posicoes as P
    cid, sec = os.environ.get('PLUGGY_CLIENT_ID'), os.environ.get('PLUGGY_CLIENT_SECRET')
    itens = [x.strip() for x in os.environ.get('PLUGGY_ITEM_IDS', '').split(',') if x.strip()]
    falta = [n for n, v in (('PLUGGY_CLIENT_ID', cid), ('PLUGGY_CLIENT_SECRET', sec), ('PLUGGY_ITEM_IDS', itens)) if not v]
    if falta:
        sys.exit('faltam variáveis de ambiente: ' + ', '.join(falta) + ' (veja docs/MINHA_CARTEIRA.md)')
    try:
        pos, ignorados = P.baixar(cid, sec, itens)
    except P.PluggyErro as e:
        sys.exit(str(e))
    print(f'Pluggy: {len(pos)} ações/ETFs de {len(itens)} conexão(ões).')
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
    fonte = ap.add_mutually_exclusive_group()
    fonte.add_argument('--csv', help='CSV de posições')
    fonte.add_argument('--pluggy', action='store_true', help='ler posições do MeuPluggy (variáveis PLUGGY_*)')
    a = ap.parse_args()

    if a.semana and a.ranking:
        sys.exit('use --semana ou --ranking, não os dois')
    pasta = C.pasta_semana(['x', a.semana]) if a.semana else (None if a.ranking else _semana_recente())
    tem_env = all(os.environ.get(v) for v in ('PLUGGY_CLIENT_ID', 'PLUGGY_CLIENT_SECRET', 'PLUGGY_ITEM_IDS'))
    if a.csv or (not a.pluggy and not tem_env):
        caminho = os.path.abspath(a.csv or 'entrada/posicoes.csv')
        if not os.path.isfile(caminho):
            sys.exit(f'CSV não encontrado: {caminho}\n'
                     'Informe --csv ARQUIVO, use --pluggy, ou crie entrada/posicoes.csv (veja docs/MINHA_CARTEIRA.md).')
        posicoes = M_ler(_ler_csv(caminho))
    else:
        posicoes = _posicoes_pluggy()

    if pasta:
        ranking, pesos_xp, data = carregar_semana(pasta)
    else:
        ranking, pesos_xp, data = carregar_publico(a.ranking or RANKING_URL)
    res = cruzar(posicoes, ranking, pesos_xp)
    res['semana'] = data
    texto = md(res, data)
    print(texto)
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


if __name__ == '__main__':
    main()
