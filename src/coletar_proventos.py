"""Coleta os proventos (dividendos e JCP) dos tickers da semana e confere cada série em uma segunda fonte.

uso: python src/coletar_proventos.py <pasta_da_semana> [TICKER ...]

Fonte principal: Yahoo Finance (chart API, events=div), a mesma de precos_yahoo.py. Segunda fonte: brapi.dev
(cashDividends, com data ex e tipo). Por ticker, compara a soma por data ex dos últimos 12 meses:
  confirmado     toda data ex até hoje existe nas duas fontes com valor igual (tolerância de 2%)
  divergente     alguma data ou valor não bate; lista as divergências e NÃO conta como cobertura
  nao_verificado a segunda fonte não respondeu
Só `confirmado` entra na avaliação como proventos verificados (avaliar.carregar_proventos). Grava
proventos.json na pasta da semana, sem alterar precos.json. Sai com código 1 se houver divergência.
Sem BRAPI_TOKEN a brapi atende poucos tickers; os demais ficam `nao_verificado` e não contam como cobertura.
Limites: o Yahoo informa valor bruto por data ex; não há tratamento de IR sobre JCP nem reinvestimento.
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

import carteira as C
import coletar_yahoo as CY
import precos_yahoo as PY

BRAPI = 'https://brapi.dev/api/quote/{t}?dividends=true'
# a brapi serve valores nominais da época; o Yahoo ajusta os proventos passados por bonificação/desdobramento
AJUSTES = {'BONIFICACAO': 1, 'DESDOBRAMENTO': 1, 'GRUPAMENTO': -1}
TOL_REL = 0.02
TOL_ABS = 0.0005


def eventos_yahoo(ticker):
    """{data_ex_iso: valor} do Yahoo para os últimos 12 meses."""
    return {d: v for d, v in PY.interpretar_dividendos(PY.baixar(f'{ticker}.SA'))}


def eventos_brapi(ticker):
    """{data_ex_iso: soma dos valores} da brapi (cashDividends), na mesma base de ajuste do Yahoo.

    Divide o valor de cada provento pelos fatores de bonificação/desdobramento (e multiplica pelos de
    grupamento) cuja data com (`lastDatePrior`) é igual ou posterior à data ex do provento. Sem esse ajuste os
    valores antigos divergem do Yahoo pelo fator (ITUB4 em 2025: 1,03). Com BRAPI_TOKEN no ambiente, usa o token;
    sem ele, a brapi só atende alguns tickers (os demais respondem 401). Levanta exceção se a fonte falhar."""
    url = BRAPI.format(t=ticker)
    if os.environ.get('BRAPI_TOKEN'):
        url += '&token=' + urllib.parse.quote(os.environ['BRAPI_TOKEN'])
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)['results'][0]
    dados = res.get('dividendsData') or {}
    ajustes = set()  # conjunto: o mesmo evento repetido pela fonte não pode ser aplicado duas vezes
    for x in dados.get('stockDividends') or []:
        sinal = AJUSTES.get(str(x.get('label') or '').upper())
        data, fator = str(x.get('lastDatePrior') or '')[:10], x.get('factor')
        if sinal and data and isinstance(fator, (int, float)) and fator > 0:
            ajustes.add((data, fator ** sinal))
    out = {}
    for x in dados.get('cashDividends') or []:
        ex = str(x.get('exDate') or '')[:10]
        if ex and isinstance(x.get('rate'), (int, float)):
            v = x['rate']
            for data, f in ajustes:
                if ex <= data:
                    v /= f
            out[ex] = round(out.get(ex, 0.0) + v, 8)
    return out


def comparar(yahoo, brapi, ini, fim):
    """Lista de divergências entre as duas séries, só para datas ex em [ini, fim] (iso)."""
    div = []
    for d in sorted({*yahoo, *brapi}):
        if not (ini <= d <= fim):
            continue
        a, b = yahoo.get(d), brapi.get(d)
        if a is None or b is None:
            div.append({'data_ex': d, 'yahoo': a, 'brapi': b, 'motivo': 'data presente em uma só fonte'})
        elif abs(a - b) > max(TOL_ABS, TOL_REL * max(a, b)):
            div.append({'data_ex': d, 'yahoo': a, 'brapi': b, 'motivo': 'valores diferentes'})
    return div


def coletar(tickers, hoje=None, fonte_principal=eventos_yahoo, fonte_secundaria=eventos_brapi):
    hoje = hoje or dt.date.today()
    ini, fim = (hoje - dt.timedelta(days=360)).isoformat(), hoje.isoformat()
    out = {'fontes': {'principal': 'Yahoo Finance (chart API, events=div)', 'secundaria': 'brapi.dev (cashDividends)'},
           'coletado_em': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'janela': [ini, fim],
           'por_ticker': {}, 'sem_dado': []}
    for t in tickers:
        try:
            y = fonte_principal(t)
        except Exception as e:  # rede, ticker inexistente, formato novo
            out['sem_dado'].append({'ticker': t, 'motivo': str(e)[:120]})
            continue
        item = {'eventos': sorted([d, v] for d, v in y.items() if ini <= d <= fim), 'coberto_ate': None}
        try:
            b = fonte_secundaria(t)
        except Exception as e:
            item['verificacao'] = {'status': 'nao_verificado', 'motivo': str(e)[:120]}
        else:
            div = comparar(y, b, ini, fim)
            item['verificacao'] = {'status': 'divergente' if div else 'confirmado', 'divergencias': div}
            if not div:
                item['coberto_ate'] = fim
        out['por_ticker'][t] = item
    return out


def main():
    pasta = C.pasta_semana(sys.argv[:2])
    tickers = [t.split('.')[0].upper() for t in sys.argv[2:]] or CY.tickers_da_semana(pasta)
    d = coletar(tickers)
    with open(os.path.join(pasta, 'proventos.json'), 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    cont = {}
    for v in d['por_ticker'].values():
        cont[v['verificacao']['status']] = cont.get(v['verificacao']['status'], 0) + 1
    print(f"proventos.json: {len(d['por_ticker'])} de {len(tickers)} tickers; {cont or 'nenhum'}")
    for t, v in d['por_ticker'].items():
        for x in v['verificacao'].get('divergencias', []):
            print(f"  DIVERGENTE {t} {x['data_ex']}: yahoo={x['yahoo']} brapi={x['brapi']} ({x['motivo']})")
    for s in d['sem_dado']:
        print('  sem dado:', s['ticker'], '-', s['motivo'])
    if cont.get('divergente') or d['sem_dado']:
        sys.exit(1)


if __name__ == '__main__':
    main()
