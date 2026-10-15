"""Coleta múltiplos de mercado (P/L, P/VP, EV/EBITDA, dividend yield) no Yahoo Finance e grava precos_yahoo.json.

uso: python src/coletar_yahoo.py <pasta_da_semana> [TICKER ...]

Complementa precos_yahoo.py (que grava as séries de preço em precos.json) e coletar_cvm.py (balanços): aqui
entram só os indicadores que o Yahoo calcula sobre o preço de hoje. Sem tickers na linha de comando usa os
de sintese.json (ranking) ou, na falta dele, os do xp.json. Precisa do pacote yfinance (requirements.txt).
Os números são do agregador, não conferidos; falha de um ticker não derruba os demais.
"""
import datetime as dt
import json
import os
import sys

import carteira as C


def tickers_da_semana(pasta):
    sint = C.ler(os.path.join(pasta, 'sintese.json'), {})
    t = [r['ticker'] for r in sint.get('ranking', []) if r.get('ticker')]
    if not t:
        t = [a['ticker'] for a in C.ler(C.arquivo_xp(pasta))['acoes']]
    return list(dict.fromkeys(x.split('.')[0].upper() for x in t))


def _pct(v):
    return round(v * 100, 2) if isinstance(v, (int, float)) else None


def extrair(info):
    """Campos do `Ticker.info` do Yahoo no formato do projeto (None quando ausente)."""
    return {'cotacao': info.get('currentPrice') or info.get('regularMarketPrice'),
            'fechamento_anterior': info.get('previousClose'),
            'p_l': info.get('trailingPE'), 'p_vp': info.get('priceToBook'), 'ev_ebitda': info.get('enterpriseToEbitda'),
            # fração (0,05 = 5%); `dividendYield` mudou de unidade entre versões do Yahoo, esta é estável
            'dividend_yield_12m_pct': _pct(info.get('trailingAnnualDividendYield')),
            'valor_mercado': info.get('marketCap')}


def buscar_info(simbolo):
    import yfinance as yf
    return yf.Ticker(simbolo).info


def coletar(tickers, buscar=buscar_info):
    out = {'fonte': 'Yahoo Finance (yfinance)', 'data_coleta': dt.datetime.now().isoformat(timespec='seconds'),
           'acoes': {}, 'sem_dado': []}
    for t in tickers:
        try:
            item = extrair(buscar(f'{t}.SA') or {})
        except Exception as e:  # rede, ticker inexistente, mudança de formato
            out['sem_dado'].append({'ticker': t, 'motivo': str(e)[:120]})
            continue
        if all(v is None for v in item.values()):
            out['sem_dado'].append({'ticker': t, 'motivo': 'sem campos retornados'})
        else:
            out['acoes'][t] = item
    return out


def main():
    pasta = C.pasta_semana(sys.argv[:2])
    tickers = [t.split('.')[0].upper() for t in sys.argv[2:]] or tickers_da_semana(pasta)
    try:
        import yfinance  # noqa: F401
    except ImportError:
        sys.exit('falta o pacote yfinance: pip install -r requirements.txt')
    d = coletar(tickers)
    with open(os.path.join(pasta, 'precos_yahoo.json'), 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print(f"precos_yahoo.json: {len(d['acoes'])} de {len(tickers)} tickers")
    for s in d['sem_dado']:
        print('  sem dado:', s['ticker'], '-', s['motivo'])


if __name__ == '__main__':
    main()
