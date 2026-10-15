"""Monta a carteira quantitativa de hoje: IBrX 100 pontuado por 5 fatores, N melhores, pesos iguais.

uso: python src/carteira_quant.py [--n 12] [--por-setor 3] [--extra TICKER ...] [--semana semana_AAAAMMDD]
                                  [--universo IBXX|amplo|IBOV,SMLL,...] [--sem-salvar]

Universo: IBXX (padrão, IBrX 100, o da validação histórica), `amplo` (IBRA + SMLL: ~250 ações líquidas da
bolsa) ou uma lista de índices da B3 separada por vírgula. Os papéis da carteira da XP (--semana) e os
--extra entram sempre, mesmo fora do índice, e aparecem marcados com [XP]; a seleção não os favorece.

Regras (dados/pesos_quant.json, status 'proposta'): composto de valor, qualidade, momentum, dividendos e
baixa volatilidade com pesos iguais; as N melhores com pesos iguais; no máximo `por-setor` por setor
(regra de risco). Com --semana, compara a nota da XP (historico_carteira.json)
com a reponderada (70% quantitativa, 30% qualitativa) e mostra quem mudaria de posição.
Salva o retrato em aprendizado/quant/carteira_AAAA-MM-DD.json para a medição em 3 a 12 meses.
Não é recomendação de investimento.
"""
import argparse
import datetime as dt
import json
import os
import re

import cvm
import fatores_quant as F
import quant_dados as Q

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_RETRATOS = os.path.join(RAIZ, 'aprendizado', 'quant')


ATALHOS_UNIVERSO = {'AMPLO': ['IBRA', 'SMLL']}


def montar_universo(indices, extras, buscar=Q.universo):
    """([tickers], descrição): união dos índices na ordem dada, sem repetição, mais os papéis extras (XP)."""
    nomes = [i for t in indices for i in ATALHOS_UNIVERSO.get(t.upper(), [t.upper()])]
    base, datas = [], []
    for ind in dict.fromkeys(nomes):
        u = buscar(ind)
        datas.append(f"{ind} de {u['data']}")
        base += [i['ticker'] for i in u['itens']]
    base = list(dict.fromkeys(base))
    return base + [t for t in dict.fromkeys(extras) if t not in base], ' + '.join(datas)


def carregar_pesos():
    with open(os.path.join(RAIZ, 'dados', 'pesos_quant.json'), encoding='utf-8') as f:
        return json.load(f)


def escolher(ranking, setores, n, por_setor):
    """Percorre o ranking (melhor primeiro) respeitando o teto por setor. ranking: [(cnpj, nota)]."""
    contagem, topo = {}, []
    for cnpj, _ in ranking:
        s = re.sub(r'^Emp\. Adm\. Part\. - ', '', setores.get(cnpj) or 'sem setor')  # holding e operadora = mesmo setor
        if contagem.get(s, 0) >= por_setor:
            continue
        contagem[s] = contagem.get(s, 0) + 1
        topo.append(cnpj)
        if len(topo) == n:
            break
    return topo


def reponderar(hist_semana, nota_quant_por_ticker, mistura, componentes_q):
    """Nota XP (5 componentes) -> nota reponderada. Devolve linhas ordenadas pela nota nova."""
    wsum = sum(componentes_q.values())
    linhas = []
    for r in hist_semana['ranking']:
        nq = nota_quant_por_ticker.get(r['ticker'])
        comp = r.get('componentes') or {}
        if nq is None or any(k not in comp for k in componentes_q):
            linhas.append({'ticker': r['ticker'], 'posicao_xp': r['posicao'], 'nota_xp': r['nota'], 'nota_quant': nq,
                           'nota_nova': None})
            continue
        qual = sum(comp[k] * w for k, w in componentes_q.items()) / wsum
        nova = mistura['quantitativa'] * nq + mistura['qualitativa'] * qual
        linhas.append({'ticker': r['ticker'], 'posicao_xp': r['posicao'], 'nota_xp': r['nota'], 'nota_quant': round(nq, 2),
                       'nota_qualitativa': round(qual, 2), 'nota_nova': round(nova, 2)})
    ok = sorted([x for x in linhas if x['nota_nova'] is not None], key=lambda x: -x['nota_nova'])
    for i, x in enumerate(ok, 1):
        x['posicao_nova'] = i
    return linhas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int)
    ap.add_argument('--por-setor', type=int)
    ap.add_argument('--extra', nargs='*', default=[])
    ap.add_argument('--semana')
    ap.add_argument('--universo', default='IBXX', help='IBXX (padrão), amplo ou índices da B3 separados por vírgula')
    ap.add_argument('--sem-salvar', action='store_true')
    a = ap.parse_args()
    cfg = carregar_pesos()
    n = a.n or cfg['carteira']['n_ativos']
    por_setor = a.por_setor or cfg['carteira']['max_por_setor']
    hoje = dt.date.today()

    hist_semana = None
    extras = [t.upper() for t in a.extra]
    xp = set()
    if a.semana:
        h = os.path.join(os.path.dirname(os.path.abspath(a.semana)), 'historico_carteira.json')
        with open(h, encoding='utf-8') as f:
            semanas = json.load(f)['semanas']
        hist_semana = semanas[-1]
        xp = {r['ticker'] for r in hist_semana['ranking']}
        extras += sorted(xp)

    tickers, desc_universo = montar_universo(a.universo.split(','), extras)
    ctx, sem = F.preparar(tickers, range(hoje.year - 2, hoje.year + 1), periodo='3y')
    ibov = Q.serie_yahoo('^BVSP', '3y')
    data = ibov['datas'][-1]
    fat = F.fatores_em(ctx, data)
    sc = F.pontuar(fat, cfg['fatores'])
    ranking = sorted(((c, s['composto']) for c, s in sc.items()), key=lambda x: -x[1])
    setores = {c: v.get('setor') for c, v in cvm.cadastro(set(sc)).items()}
    topo = escolher(ranking, setores, n, por_setor)

    carteira = [{'ticker': ctx[c]['ticker'], 'cnpj': c, 'nome': ctx[c]['nome'], 'setor': setores.get(c),
                 'peso_pct': round(100 / len(topo), 2), 'nota_quant': round(sc[c]['composto'] * 10, 2),
                 'fatores': {k: round(v, 2) for k, v in sc[c].items() if k != 'composto'},
                 'preco': fat[c]['preco']} for c in topo]
    print(f"Carteira quantitativa em {data} ({desc_universo}; {len(sc)} empresas pontuadas, "
          f"{len(sem)} sem dado)\n")
    print(f"{'#':>2} {'ticker':7}{'nota':>6}{'peso%':>7}  {'valor':>6}{'qualid':>7}{'moment':>7}{'dividi':>7}{'vol':>6}  setor")
    for i, p in enumerate(carteira, 1):
        p['na_xp'] = p['ticker'] in xp
        f = p['fatores']
        g = lambda k: f'{f[k]:.2f}' if k in f else '  -'
        print(f"{i:>2} {p['ticker']:7}{p['nota_quant']:6.2f}{p['peso_pct']:7.1f}  {g('valor'):>6}{g('qualidade'):>7}"
              f"{g('momentum'):>7}{g('dividendos'):>7}{g('baixa_vol'):>6}  {(p['setor'] or '')[:40]}{' [XP]' if p['na_xp'] else ''}")
    fora = [r for r in ranking[:n] if r[0] not in topo]
    if fora:
        print('\nTop-' + str(n), 'barrados pelo teto de setor:', ', '.join(ctx[c]['ticker'] for c, _ in fora))
    if sem:
        print('\nSem dado:', ', '.join(f'{t} ({m})' for t, m in sem))

    comparacao = None
    if hist_semana:
        nq = {ctx[c]['ticker']: sc[c]['composto'] * 10 for c in sc}
        for c in sc:  # outras classes da mesma empresa herdam a nota
            for t in ctx[c]['todos']:
                nq.setdefault(t, sc[c]['composto'] * 10)
        comparacao = reponderar(hist_semana, nq, cfg['mistura_nota_xp'], cfg['componentes_qualitativos'])
        print(f"\nNota da XP (semana {hist_semana['data']}) contra a reponderada "
              f"({cfg['mistura_nota_xp']['quantitativa']:.0%} quant + {cfg['mistura_nota_xp']['qualitativa']:.0%} qualitativa)")
        print(f"{'ticker':8}{'pos XP':>7}{'nota XP':>8}{'quant':>7}{'qualit':>7}{'nova':>7}{'pos nova':>9}")
        for x in sorted(comparacao, key=lambda x: x['posicao_xp']):
            f2 = lambda v: f'{v:.2f}' if v is not None else '  -'
            print(f"{x['ticker']:8}{x['posicao_xp']:>7}{x['nota_xp']:8.2f}{f2(x['nota_quant']):>7}"
                  f"{f2(x.get('nota_qualitativa')):>7}{f2(x['nota_nova']):>7}{str(x.get('posicao_nova', '-')):>9}")

    if not a.sem_salvar:
        os.makedirs(PASTA_RETRATOS, exist_ok=True)
        saida = os.path.join(PASTA_RETRATOS, f'carteira_{data}.json')
        with open(saida, 'w', encoding='utf-8') as f:
            json.dump({'data': data, 'universo': desc_universo, 'parametros': {'n': n, 'por_setor': por_setor,
                       'fatores': cfg['fatores'], 'status_pesos': cfg['status']},
                       'carteira': carteira,
                       'ranking': [{'ticker': ctx[c]['ticker'], 'nota_quant': round(s * 10, 2)} for c, s in ranking],
                       'comparacao_xp': comparacao, 'sem_dado': sem,
                       'aviso': 'Saída de modelo, não é recomendação de investimento.'},
                      f, ensure_ascii=False, indent=1)
        print(f'\nsalvo em {os.path.relpath(saida, RAIZ)}')


if __name__ == '__main__':
    main()
