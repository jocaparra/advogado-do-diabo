"""Aprendizado supervisionado e conservador sobre as recomendações já vencidas. NUNCA aplica sozinho.

uso:
  python src/aprender.py relatorio <pasta_da_semana>     # portão de amostra, padrões e erros recorrentes
                                                         # (atalho: aprender.py <pasta_da_semana>)
  python src/aprender.py propor <pasta_da_semana>        # gera proposta de pesos (só se o portão abrir)
  python src/aprender.py aplicar <pasta_da_semana> --proposta ID --aprovado-por usuario
  python src/aprender.py verificar <pasta_da_semana>     # compara a versão atual com a anterior; sugere rollback
  python src/aprender.py reverter --para VERSAO          # nova versão que copia uma anterior
  python src/aprender.py versoes
  python src/aprender.py fase <pasta_da_semana>          # em que fase de aprendizado os dados permitem estar

Os comandos com <pasta_da_semana> aceitam --horizonte {1_semana,4_semanas,12_semanas} (padrão 1_semana).

O que aprende: os 5 pesos da nota (catalisadores, notícias, momentum, macro_eleicao, valuation_upside).
Como: ajuste conservador pela correlação de postos de cada componente com o excesso de retorno, limitado
a +-MAX_DELTA por peso e validado fora da amostra (treino nas primeiras semanas, teste nas últimas). Isto
é calibração de poucos parâmetros com regra de parada, não treinamento de um modelo de ML.

Segurança: sem >= MIN_OBS observações vencidas em >= MIN_SEMANAS semanas o portão fica fechado e nada é
proposto; a proposta só vale se melhorar o teste fora da amostra; aplicar exige aprovação explícita do
usuário e repete o portão; toda mudança vira uma nova versão (nada é apagado) e reverter também.

Variáveis: CARTEIRA_APRENDIZADO (propostas) e CARTEIRA_PARAMETROS (arquivo de versões) mudam os destinos.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import statistics
import sys

import avaliar as A
import carteira as C

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPONENTES = A.COMPONENTES
# Horizonte usado para aprender. 1 semana devolve resultado mais cedo, mas com mais ruído por observação;
# 4 ou 12 semanas são mais estáveis e mais lentos. Troque com --horizonte.
HORIZONTES_VALIDOS = tuple(A.HORIZONTES)
HORIZONTE = '1_semana'
MAX_DELTA = 0.05                 # mudança máxima por peso numa proposta
PISO_PESO = 0.05
K = 0.5                          # intensidade do ajuste por correlação
MARGEM_TESTE = 0.03              # ganho mínimo de Spearman fora da amostra para valer a proposta
FRACAO_TREINO = 0.6
TOLERANCIA_REGRESSAO = 0.05
RECORRENTE_MIN_SEMANAS = 3
# Fase 3 (modelo mais flexível). Convenção do projeto, NÃO calibrada: só vale considerar com muito mais
# dado do que a calibração de pesos, porque os papéis de uma semana são correlacionados entre si.
FASE3_MIN_OBS = 200
FASE3_MIN_SEMANAS = 52
LATENCIAS = {'1_semana': 1, '4_semanas': 4, '12_semanas': 12}   # semanas até uma recomendação virar observação
PASTA = os.environ.get('CARTEIRA_APRENDIZADO') or os.path.join(AQUI, 'aprendizado')
ARQ_VERSOES = os.environ.get('CARTEIRA_PARAMETROS') or os.path.join(AQUI, 'dados', 'parametros_aprendidos.json')
ARQ_HORIZONTES = os.path.join(AQUI, 'dados', 'horizontes.json')


# ---------- métricas ----------
def nota_com(componentes, pesos):
    return sum(pesos[k] * componentes[k] for k in pesos)


def _completo(o):
    c = o.get('componentes')
    return isinstance(c, dict) and all(isinstance(c.get(k), (int, float)) for k in COMPONENTES)


def spearman_medio(obs, valor):
    """Média, por semana, da correlação de postos entre valor(o) e o excesso. (media, semanas_usadas)."""
    rhos = []
    for s in sorted({o['semana'] for o in obs}):
        grupo = [o for o in obs if o['semana'] == s]
        rho = A.spearman([valor(o) for o in grupo], [o['excesso_pp'] for o in grupo])
        if rho is not None:
            rhos.append(rho)
    return (statistics.fmean(rhos), len(rhos)) if rhos else (None, 0)


def portao(obs):
    """Aberto só com amostra mínima (mesmo critério do avaliar.py), contando só observações com componentes."""
    usaveis = [o for o in obs if _completo(o)]
    semanas = len({o['semana'] for o in usaveis})
    return {'aberto': len(usaveis) >= A.MIN_OBS and semanas >= A.MIN_SEMANAS, 'observacoes_usaveis': len(usaveis),
            'semanas': semanas, 'minimo': {'observacoes': A.MIN_OBS, 'semanas': A.MIN_SEMANAS}}


def _cauda_binomial(k, n, p):
    """P(X >= k) para X ~ Binomial(n, p)."""
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def erros_recorrentes(obs, alfa=0.05):
    """Tickers cuja taxa de erro (ou oportunidade perdida) é maior do que a dos demais, e não só frequente.

    Contar semanas erradas não basta: com muitas semanas todo papel erra algumas vezes por acaso. Compara a
    taxa de cada ticker com a taxa geral por cauda binomial, com correção de Bonferroni entre os tickers,
    e exige pelo menos RECORRENTE_MIN_SEMANAS semanas distintas. Devolve ticker -> semanas com erro."""
    erro = lambda o: o.get('veredito') in ('erro', 'oportunidade_perdida')
    com_ticker = [o for o in obs if isinstance(o.get('ticker'), str)]
    if not com_ticker:
        return {}
    taxa = sum(erro(o) for o in com_ticker) / len(com_ticker)
    por_ticker = {}
    for o in com_ticker:
        d = por_ticker.setdefault(o['ticker'], {'n': 0, 'erros': set()})
        d['n'] += 1
        if erro(o):
            d['erros'].add(o.get('semana'))
    out = {}
    for t, d in por_ticker.items():
        k = len(d['erros'])
        if k >= RECORRENTE_MIN_SEMANAS and 0 < taxa < 1 and _cauda_binomial(k, d['n'], taxa) <= alfa / len(por_ticker):
            out[t] = sorted(d['erros'])
    return out


# ---------- o que a máquina enxerga ----------
def padroes(obs):
    """Padrões descritivos (não são conclusões): correlação média de cada componente com o excesso, por semana,
    e papéis com erro recorrente. Com amostra pequena é só leitura; nada aqui altera parâmetro."""
    usaveis = [o for o in obs if _completo(o)]
    comp = {}
    for c in COMPONENTES:
        rs = []
        for s in sorted({o['semana'] for o in usaveis}):
            g = [o for o in usaveis if o['semana'] == s]
            r = A.spearman([o['componentes'][c] for o in g], [o['excesso_pp'] for o in g])
            if r is not None:
                rs.append(r)
        if rs:
            ep = statistics.stdev(rs) / len(rs) ** 0.5 if len(rs) > 1 else None
            comp[c] = {'rho_medio': round(statistics.fmean(rs), 3), 'erro_padrao': round(ep, 3) if ep is not None else None,
                       'semanas': len(rs), 'semanas_positivas': sum(x > 0 for x in rs)}
    return {'componentes': comp, 'erros_recorrentes': erros_recorrentes(obs), 'portao': portao(obs)}


# ---------- portão de treino ----------
def fase(obs, semanas_historico, semanas_com_componentes, horizonte=None):
    """Em que fase os dados permitem estar e quanto falta. Assume cadência semanal e o mesmo universo."""
    latencia = LATENCIAS[horizonte or HORIZONTE]
    g = portao(obs)
    n, s = g['observacoes_usaveis'], g['semanas']
    f2 = n >= A.MIN_OBS and s >= A.MIN_SEMANAS
    f3 = n >= FASE3_MIN_OBS and s >= FASE3_MIN_SEMANAS
    # semanas de histórico (com componentes) necessárias para ter MIN_SEMANAS semanas vencidas no horizonte
    falta2 = 0 if f2 else max(0, A.MIN_SEMANAS + latencia - semanas_com_componentes)
    falta3 = 0 if f3 else max(0, FASE3_MIN_SEMANAS + latencia - semanas_com_componentes)
    atual = 3 if f3 else 2 if f2 else 1
    nomes = {1: 'coleta e memória contextual (não é treinamento de modelo)',
             2: 'calibração conservadora dos pesos, validada fora da amostra',
             3: 'modelo supervisionado mais flexível, só com validação walk-forward e comparação com a versão anterior'}
    return {'fase_atual': atual, 'descricao': nomes[atual], 'observacoes_usaveis': n, 'semanas_vencidas_com_componentes': s,
            'semanas_no_historico': semanas_historico, 'semanas_no_historico_com_componentes': semanas_com_componentes,
            'fase_2': {'liberada': f2, 'minimo': {'observacoes': A.MIN_OBS, 'semanas': A.MIN_SEMANAS}, 'semanas_restantes_estimadas': falta2},
            'fase_3': {'liberada': f3, 'minimo': {'observacoes': FASE3_MIN_OBS, 'semanas': FASE3_MIN_SEMANAS},
                       'semanas_restantes_estimadas': falta3},
            'horizonte': horizonte or HORIZONTE,
            'premissas': f'cadência semanal, universo de ~14 ações, horizonte de {(horizonte or HORIZONTE).replace("_", " ")}, '
                         'observações só de semanas gravadas com componentes'}


# ---------- proposta de pesos ----------
def _normalizar(pesos):
    s = sum(pesos.values())
    return {k: v / s for k, v in pesos.items()}


def candidatos(obs_treino, atuais):
    """Pesos candidatos: ajuste por correlação, limitado a +-MAX_DELTA e com piso, somando 1."""
    rho = {}
    for c in COMPONENTES:
        r, n = spearman_medio(obs_treino, lambda o, c=c: o['componentes'][c])
        rho[c] = r if r is not None else 0.0
    bruto = _normalizar({c: max(atuais[c] * (1 + K * rho[c]), PISO_PESO) for c in COMPONENTES})
    lim = {c: min(max(bruto[c], atuais[c] - MAX_DELTA), atuais[c] + MAX_DELTA) for c in COMPONENTES}
    lim = {c: max(v, PISO_PESO) for c, v in lim.items()}
    return {c: round(v, 4) for c, v in _normalizar(lim).items()}, rho


def propor(obs, atuais, hoje=None):
    """Dict com status 'portao_fechado', 'sem_ganho' ou 'proposta'. Nunca altera nada."""
    hoje = hoje or dt.date.today()
    if not isinstance(atuais, dict) or set(atuais) != set(COMPONENTES):
        return {'status': 'pesos_invalidos', 'motivo': f'os pesos atuais precisam ter exatamente: {", ".join(COMPONENTES)}'}
    g = portao(obs)
    if not g['aberto']:
        return {'status': 'portao_fechado', 'portao': g,
                'motivo': f'{g["observacoes_usaveis"]} obs em {g["semanas"]} semana(s); mínimo {A.MIN_OBS} obs em {A.MIN_SEMANAS} semanas'}
    usaveis = [o for o in obs if _completo(o)]
    semanas = sorted({o['semana'] for o in usaveis})
    corte = max(1, math.ceil(len(semanas) * FRACAO_TREINO))
    treino = [o for o in usaveis if o['semana'] in semanas[:corte]]
    teste = [o for o in usaveis if o['semana'] in semanas[corte:]]
    if len({o['semana'] for o in teste}) < 2:
        return {'status': 'portao_fechado', 'portao': g, 'motivo': 'menos de 2 semanas de teste fora da amostra'}
    cand, rho = candidatos(treino, atuais)
    s_atual, _ = spearman_medio(teste, lambda o: nota_com(o['componentes'], atuais))
    s_cand, _ = spearman_medio(teste, lambda o: nota_com(o['componentes'], cand))
    if s_atual is None or s_cand is None:
        return {'status': 'sem_ganho', 'portao': g, 'motivo': 'correlação não definida no teste'}
    ganho = s_cand - s_atual
    out = {'status': 'proposta' if ganho >= MARGEM_TESTE else 'sem_ganho', 'portao': g, 'gerada_em': hoje.isoformat(),
           'horizonte': HORIZONTE, 'pesos_atuais': atuais, 'pesos_propostos': cand,
           'delta': {c: round(cand[c] - atuais[c], 4) for c in COMPONENTES}, 'rho_treino': {c: round(r, 3) for c, r in rho.items()},
           'validacao': {'semanas_treino': semanas[:corte], 'semanas_teste': semanas[corte:], 'spearman_teste_atual': round(s_atual, 3),
                         'spearman_teste_proposto': round(s_cand, 3), 'ganho': round(ganho, 3), 'margem_exigida': MARGEM_TESTE}}
    out['id'] = 'p' + hoje.strftime('%Y%m%d') + '_' + hashlib.sha256(json.dumps(cand, sort_keys=True).encode()).hexdigest()[:8]
    return out


# ---------- versões (nada é apagado) ----------
def pesos_baseline():
    with open(ARQ_HORIZONTES, encoding='utf-8') as f:
        return json.load(f)['horizontes']['semanas']['pesos']


def carregar_versoes(arquivo=None):
    arquivo = arquivo or ARQ_VERSOES
    if os.path.exists(arquivo):
        with open(arquivo, encoding='utf-8') as f:
            return json.load(f)
    return {'versao_atual': 1, 'versoes': [{'versao': 1, 'criado_em': dt.datetime.now().replace(microsecond=0).isoformat(),
                                            'parametros': {'pesos': pesos_baseline()}, 'motivo': 'baseline: pesos de dados/horizontes.json (semanas)',
                                            'aprovado_por': 'baseline', 'evidencia': None, 'aplicada_a_partir_de': None}]}


def _salvar(dados, arquivo=None):
    arquivo = arquivo or ARQ_VERSOES
    os.makedirs(os.path.dirname(arquivo), exist_ok=True)
    tmp = arquivo + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, arquivo)


def versao(dados, n=None):
    n = n or dados['versao_atual']
    for v in dados['versoes']:
        if v['versao'] == n:
            return v
    raise ValueError(f'versão inexistente: {n}')


def aplicar(proposta, obs, aprovado_por, hoje=None, arquivo=None):
    """Nova versão a partir de uma proposta. Recusa sem aprovação do usuário, com portão fechado ou proposta sem ganho."""
    hoje = hoje or dt.date.today()
    if aprovado_por != 'usuario':
        raise ValueError('aplicar exige aprovação explícita do usuário (--aprovado-por usuario)')
    if proposta.get('status') != 'proposta':
        raise ValueError(f'proposta não aplicável (status: {proposta.get("status")})')
    if not portao(obs)['aberto']:
        raise ValueError('portão de amostra fechado nesta data; a evidência da proposta não se sustenta')
    dados = carregar_versoes(arquivo)
    atual = versao(dados)
    if atual['parametros']['pesos'] != proposta['pesos_atuais']:
        raise ValueError('a proposta foi feita sobre outra versão; gere uma nova')
    nova = {'versao': max(v['versao'] for v in dados['versoes']) + 1,
            'criado_em': dt.datetime.now().replace(microsecond=0).isoformat(), 'parametros': {'pesos': proposta['pesos_propostos']},
            'motivo': f'proposta {proposta["id"]}: ganho de {proposta["validacao"]["ganho"]} em Spearman fora da amostra',
            'aprovado_por': aprovado_por, 'evidencia': {'portao': proposta['portao'], 'validacao': proposta['validacao']},
            'aplicada_a_partir_de': hoje.isoformat(), 'base': atual['versao']}
    dados['versoes'].append(nova)
    dados['versao_atual'] = nova['versao']
    _salvar(dados, arquivo)
    return nova


def reverter(para, motivo='rollback manual', hoje=None, arquivo=None):
    """Cria nova versão copiando os parâmetros de uma anterior (o histórico fica intacto)."""
    hoje = hoje or dt.date.today()
    dados = carregar_versoes(arquivo)
    alvo = versao(dados, para)
    atual = versao(dados)
    if alvo['versao'] == atual['versao']:
        raise ValueError('a versão pedida já é a atual')
    nova = {'versao': max(v['versao'] for v in dados['versoes']) + 1,
            'criado_em': dt.datetime.now().replace(microsecond=0).isoformat(), 'parametros': json.loads(json.dumps(alvo['parametros'])),
            'motivo': f'{motivo}: volta aos parâmetros da versão {para}', 'aprovado_por': 'usuario', 'evidencia': None,
            'aplicada_a_partir_de': hoje.isoformat(), 'base': atual['versao']}
    dados['versoes'].append(nova)
    dados['versao_atual'] = nova['versao']
    _salvar(dados, arquivo)
    return nova


def verificar(obs, arquivo=None):
    """Compara versão atual e a de base nas semanas posteriores à aplicação. Só sugere; não reverte."""
    dados = carregar_versoes(arquivo)
    atual = versao(dados)
    if not atual.get('base') or not atual.get('aplicada_a_partir_de'):
        return {'status': 'sem_comparacao', 'motivo': 'versão atual é a baseline ou um rollback sem base de comparação'}
    base = versao(dados, atual['base'])
    pos = [o for o in obs if _completo(o) and o['semana'] >= atual['aplicada_a_partir_de']]
    sem = len({o['semana'] for o in pos})
    if sem < 2:
        return {'status': 'amostra_insuficiente', 'semanas_pos_aplicacao': sem, 'motivo': 'menos de 2 semanas vencidas após a aplicação'}
    pa, pb = atual['parametros']['pesos'], base['parametros']['pesos']
    sa, _ = spearman_medio(pos, lambda o: nota_com(o['componentes'], pa))
    sb, _ = spearman_medio(pos, lambda o: nota_com(o['componentes'], pb))
    if sa is None or sb is None:
        return {'status': 'sem_comparacao', 'motivo': 'correlação não definida'}
    regressao = sa < sb - TOLERANCIA_REGRESSAO
    return {'status': 'regressao' if regressao else 'ok', 'versao_atual': atual['versao'], 'versao_base': base['versao'],
            'spearman_atual': round(sa, 3), 'spearman_base': round(sb, 3), 'semanas_pos_aplicacao': sem,
            'recomendacao': f'reverter --para {base["versao"]}' if regressao else None}


# ---------- CLI ----------
def _obs(pasta):
    raiz = os.path.dirname(pasta)
    r = A.avaliar(raiz)
    if r is None:
        sys.exit('historico_carteira.json não encontrado ao lado das pastas de semana')
    todas = r['observacoes'][HORIZONTE]
    obs = [o for o in todas if o.get('proventos_completos', True)]  # retorno só de preço não é comparável ao Ibovespa
    if len(obs) < len(todas):
        print(f'aviso: {len(todas) - len(obs)} de {len(todas)} observações ({HORIZONTE}) fora do aprendizado por falta '
              'de proventos até o fim da janela (veja avaliacao.json)')
    return obs, r


def _salvar_proposta(p):
    d = os.path.join(PASTA, 'propostas')
    os.makedirs(d, exist_ok=True)
    caminho = os.path.join(d, p['id'] + '.json')
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(p, f, ensure_ascii=False, indent=1)
    return caminho


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    def com_horizonte(p):
        p.add_argument('--horizonte', choices=HORIZONTES_VALIDOS, default=HORIZONTE,
                       help=f'horizonte em que o aprendizado mede o resultado (padrão: {HORIZONTE})')
        return p
    for nome in ('relatorio', 'propor', 'verificar', 'fase'):
        p = sub.add_parser(nome)
        p.add_argument('pasta')
        com_horizonte(p)
    a = sub.add_parser('aplicar')
    a.add_argument('pasta')
    com_horizonte(a)
    a.add_argument('--proposta', required=True)
    a.add_argument('--aprovado-por', required=True)
    rv = sub.add_parser('reverter')
    rv.add_argument('--para', type=int, required=True)
    sub.add_parser('versoes')
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) == 1 and argv[0] not in sub.choices and not argv[0].startswith('-'):
        argv = ['relatorio', argv[0]]          # forma curta usada por executar.py
    args = ap.parse_args(argv)
    global HORIZONTE
    HORIZONTE = getattr(args, 'horizonte', HORIZONTE)
    try:
        if args.cmd == 'versoes':
            d = carregar_versoes()
            for v in d['versoes']:
                print(f'{"*" if v["versao"] == d["versao_atual"] else " "} v{v["versao"]}  {v["criado_em"]}  {v["aprovado_por"]:9} {v["motivo"]}')
            return
        if args.cmd == 'reverter':
            n = reverter(args.para)
            print(f'nova versão v{n["versao"]}: {n["motivo"]}')
            return
        pasta = os.path.abspath(args.pasta)
        obs, aval = _obs(pasta)
        if args.cmd == 'relatorio':
            g = portao(obs)
            print(f'portão de amostra ({HORIZONTE}): {"ABERTO" if g["aberto"] else "FECHADO"}; {g["observacoes_usaveis"]} obs com componentes '
                  f'em {g["semanas"]} semana(s) (mínimo {g["minimo"]["observacoes"]} em {g["minimo"]["semanas"]})')
            ver = {}
            for o in obs:                       # só as observações que o aprendizado usa (com proventos conhecidos)
                ver[o['veredito']] = ver.get(o['veredito'], 0) + 1
            direc = ver.get('acerto', 0) + ver.get('erro', 0)
            acerto = round(100 * ver.get('acerto', 0) / direc, 1) if direc else None
            print(f'  vereditos: {ver or "nenhum vencido"}; acerto direcional: {acerto}')
            rec = erros_recorrentes(obs)
            print('  erros recorrentes: ' + (', '.join(f'{t} ({len(s)} semanas)' for t, s in rec.items()) or 'nenhum'))
            for c, v in padroes(obs)['componentes'].items():
                print(f'  componente {c:16} ρ médio {v["rho_medio"]:+.3f} em {v["semanas"]} semana(s), {v["semanas_positivas"]} positivas')
            if not g['aberto']:
                print('  nenhuma conclusão é suportada ainda; continue coletando semanas (veja: aprender.py fase <pasta>).')
        elif args.cmd == 'propor':
            p = propor(obs, versao(carregar_versoes())['parametros']['pesos'])
            if p['status'] == 'proposta':
                print(f'proposta {p["id"]} salva em {_salvar_proposta(p)}\n  delta: {p["delta"]}\n  validação: {p["validacao"]}')
            else:
                print(f'sem proposta ({p["status"]}): {p.get("motivo")}')
        elif args.cmd == 'aplicar':
            caminho = os.path.join(PASTA, 'propostas', args.proposta + '.json')
            if not os.path.exists(caminho):
                sys.exit(f'proposta não encontrada: {caminho}')
            with open(caminho, encoding='utf-8') as f:
                n = aplicar(json.load(f), obs, args.aprovado_por)
            print(f'aplicada: v{n["versao"]} ({n["motivo"]})')
        elif args.cmd == 'verificar':
            print(json.dumps(verificar(obs), ensure_ascii=False, indent=1))
        elif args.cmd == 'fase':
            hist = C.ler(os.path.join(os.path.dirname(pasta), 'historico_carteira.json'), {'semanas': []})['semanas']
            com = [s for s in hist if any(isinstance(r.get('componentes'), dict) for r in s.get('ranking', []))]
            f = fase(obs, len(hist), len(com))
            print(f'fase atual: {f["fase_atual"]} ({f["descricao"]})')
            print(f'  dados: {f["observacoes_usaveis"]} obs usáveis em {f["semanas_vencidas_com_componentes"]} semana(s) vencida(s); '
                  f'histórico: {f["semanas_no_historico"]} semana(s), {f["semanas_no_historico_com_componentes"]} com componentes')
            for k, nome in (('fase_2', 'Fase 2 (pesos)'), ('fase_3', 'Fase 3 (modelo)')):
                x = f[k]
                st = 'LIBERADA' if x['liberada'] else f'faltam ~{x["semanas_restantes_estimadas"]} semana(s)'
                print(f'  {nome}: {st} (mínimo {x["minimo"]["observacoes"]} obs em {x["minimo"]["semanas"]} semanas)')
            print(f'  premissas: {f["premissas"]}')
    except ValueError as e:
        sys.exit(f'recusado: {e}')


if __name__ == '__main__':
    main()
