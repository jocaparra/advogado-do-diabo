"""Coleta cotações diárias (12 meses) no Yahoo Finance e grava precos.json no formato do projeto.

uso: python src/precos_yahoo.py <pasta_da_semana> [TICKER ...]

Sem tickers na linha de comando, lê os do xp.json (mensal mais recente). Inclui o Ibovespa (^BVSP).
Fechamento sem ajuste por proventos, ajustado por desdobramentos (padrão do Yahoo); os proventos
comem em "dividendos" de cada ação, para o retorno total na avaliação. O último ponto
pode ser intradiário se rodar durante o pregão: o aviso fica em precos.json (campo "notas").
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

import carteira as C

URL = 'https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}?range=1y&interval=1d&events=div'


def interpretar(payload):
    """Extrai [[data_iso, fechamento], ...] do JSON do Yahoo, descartando pontos sem preço."""
    res = payload['chart']['result'][0]
    ts = res.get('timestamp') or []
    closes = res['indicators']['quote'][0].get('close') or []
    off = res.get('meta', {}).get('gmtoffset', 0) or 0
    serie = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        d = (dt.datetime.fromtimestamp(t, dt.timezone.utc) + dt.timedelta(seconds=off)).date().isoformat()
        if serie and serie[-1][0] == d:
            serie[-1] = [d, round(c, 4)]
        else:
            serie.append([d, round(c, 4)])
    return serie


def interpretar_dividendos(payload):
    """[[data_ex_iso, valor por ação], ...] de dividendos e JCP, na mesma base de desdobramentos da série."""
    res = payload['chart']['result'][0]
    off = res.get('meta', {}).get('gmtoffset', 0) or 0
    eventos = (res.get('events') or {}).get('dividends') or {}
    return sorted([(dt.datetime.fromtimestamp(e['date'], dt.timezone.utc) + dt.timedelta(seconds=off)).date().isoformat(),
                   round(e['amount'], 6)] for e in eventos.values())


def retornos(serie):
    """Retornos de 5 pregões, 30 dias corridos, no ano e 12 meses, como strings '12.34%'."""
    if len(serie) < 7:
        return {}
    ult_d, ult_p = serie[-1]
    d = dt.date.fromisoformat(ult_d)

    def desde(data):
        ref = [p for dd, p in serie if dd <= data.isoformat()]
        return f'{(ult_p / ref[-1] - 1) * 100:.2f}%' if ref else 'não verificado'
    ano0 = dt.date(d.year - 1, 12, 31)
    return {'ret_5d': f'{(ult_p / serie[-6][1] - 1) * 100:.2f}%', 'ret_30d': desde(d - dt.timedelta(days=30)),
            'ret_ano': desde(ano0), 'ret_12m': f'{(ult_p / serie[0][1] - 1) * 100:.2f}%'}


def baixar(simbolo):
    req = urllib.request.Request(URL.format(simbolo=urllib.parse.quote(simbolo)), headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def coletar(tickers):
    out = {'fonte': 'Yahoo Finance (dados B3)', 'url_api': URL.split('{')[0],
           'metodo': 'fechamento sem ajuste por proventos, ajustado por desdobramentos; série diária de 12 meses; dividendos e JCP por data ex em "dividendos"',
           'data_coleta': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'acoes': {}, 'sem_dado': [],
           'notas': ['Se coletado durante o pregão, o último ponto pode ser intradiário.']}
    for simbolo, destino in [('^BVSP', None)] + [(f'{t}.SA', t) for t in tickers]:
        try:
            payload = baixar(simbolo)
            serie = interpretar(payload)
            divs = interpretar_dividendos(payload)
        except Exception as e:  # rede, ticker inexistente, formato novo
            if destino:
                out['sem_dado'].append({'ticker': destino, 'motivo': str(e)[:120]})
            else:
                raise SystemExit(f'não foi possível baixar o Ibovespa: {e}')
            continue
        if not serie:
            out['sem_dado'].append({'ticker': destino or '^BVSP', 'motivo': 'série vazia'})
            continue
        item = {'preco_atual': serie[-1][1], 'data_cotacao': serie[-1][0], **retornos(serie), 'serie': serie,
                'dividendos': divs}
        if destino is None:
            out['ibovespa'] = item
        else:
            out['acoes'][destino] = item
    return out


def main():
    pasta = C.pasta_semana(sys.argv[:2])
    tickers = [t.upper() for t in sys.argv[2:]]
    if not tickers:
        tickers = [a['ticker'] for a in C.ler(C.arquivo_xp(pasta))['acoes']]
    d = coletar(tickers)
    with open(os.path.join(pasta, 'precos.json'), 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print(f'precos.json: {len(d["acoes"])} de {len(tickers)} tickers; Ibovespa {d["ibovespa"]["preco_atual"]} em {d["ibovespa"]["data_cotacao"]}')
    for s in d['sem_dado']:
        print('  sem dado:', s['ticker'], '-', s['motivo'])


if __name__ == '__main__':
    main()
