"""Mede em 3, 6 e 12 meses as carteiras quantitativas salvas por carteira_quant.py.

uso: python src/medir_quant.py [--custo 0.15]

Para cada retrato em aprendizado/quant/carteira_*.json, calcula o retorno total (preço mais proventos,
comprar e segurar com pesos iguais, sem rebalancear) até +91, +182 e +365 dias, contra o Ibovespa e o CDI,
e agrega por horizonte. O custo de entrada (por lado, sobre a carteira inteira) é descontado.
Retratos mensais se sobrepõem em janelas longas: a amostra efetiva é menor que a contagem. Abaixo de
12 retratos vencidos por horizonte o resultado é marcado como insuficiente.
Grava aprendizado/quant/medicao.json. Não é recomendação de investimento.
"""
import argparse
import bisect
import datetime as dt
import glob
import json
import math
import os
import statistics

import quant_dados as Q

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA = os.path.join(RAIZ, 'aprendizado', 'quant')
HORIZONTES = {'3_meses': 91, '6_meses': 182, '12_meses': 365}
MIN_RETRATOS = 12


def _em(serie, data_iso, campo):
    i = bisect.bisect_right(serie['datas'], data_iso) - 1
    return serie[campo][i] if i >= 0 else None


def medir_retrato(retrato, horizonte_dias, series, ibov, cdi, custo_pct, hoje):
    """Resultado de um retrato em um horizonte; None se ainda não venceu ou faltar preço."""
    d0 = dt.date.fromisoformat(retrato['data'])
    d1 = d0 + dt.timedelta(days=horizonte_dias)
    ultima = min(ibov['datas'][-1], hoje.isoformat())
    if d1.isoformat() > ultima:
        return None
    ini, fim = d0.isoformat(), d1.isoformat()
    rets = []
    for p in retrato['carteira']:
        s = series.get(p['ticker'])
        if not s:
            return None
        a0, a1 = _em(s, ini, 'adj'), _em(s, fim, 'adj')
        if not a0 or not a1:
            return None
        rets.append(a1 / a0 - 1)
    cart = statistics.fmean(rets) - custo_pct / 100
    b0, b1 = _em(ibov, ini, 'close'), _em(ibov, fim, 'close')
    bench = b1 / b0 - 1
    cdi_r = math.prod(1 + v for d, v in cdi.items() if ini < d <= fim) - 1
    return {'data': retrato['data'], 'fim': fim, 'carteira_pct': round(100 * cart, 2), 'ibovespa_pct': round(100 * bench, 2),
            'cdi_pct': round(100 * cdi_r, 2), 'excesso_pp': round(100 * (cart - bench), 2),
            'acima_do_ibov': cart > bench}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--custo', type=float, default=0.15, help='%% por lado, cobrado uma vez na entrada')
    a = ap.parse_args()
    hoje = dt.date.today()
    arquivos = sorted(glob.glob(os.path.join(PASTA, 'carteira_*.json')))
    if not arquivos:
        raise SystemExit('nenhum retrato em aprendizado/quant/: rode python src/carteira_quant.py')
    retratos = [json.load(open(p, encoding='utf-8')) for p in arquivos]
    tickers = sorted({p['ticker'] for r in retratos for p in r['carteira']})
    series = {t: Q.serie_yahoo(f'{t}.SA', '3y') for t in tickers}
    ibov = Q.serie_yahoo('^BVSP', '3y')
    cdi = Q.cdi_diario(dt.date.fromisoformat(retratos[0]['data']) - dt.timedelta(days=7), hoje)

    saida = {'data_medicao': hoje.isoformat(), 'retratos': len(retratos), 'custo_entrada_pct': a.custo, 'horizontes': {}}
    print(f'{len(retratos)} retrato(s) de {retratos[0]["data"]} a {retratos[-1]["data"]}; custo de entrada {a.custo}%\n')
    for nome, dias in HORIZONTES.items():
        obs, pend = [], []
        for r in retratos:
            m = medir_retrato(r, dias, series, ibov, cdi, a.custo, hoje)
            if m:
                obs.append(m)
            else:
                pend.append({'data': r['data'], 'vence_em': (dt.date.fromisoformat(r['data']) + dt.timedelta(days=dias)).isoformat()})
        info = {'observacoes': obs, 'pendentes': pend, 'n': len(obs),
                'amostra': 'suficiente' if len(obs) >= MIN_RETRATOS else 'insuficiente'}
        if obs:
            ex = [o['excesso_pp'] for o in obs]
            info.update({'excesso_medio_pp': round(statistics.fmean(ex), 2), 'excesso_mediano_pp': round(statistics.median(ex), 2),
                         'acima_do_ibov_pct': round(100 * sum(o['acima_do_ibov'] for o in obs) / len(obs), 1),
                         'carteira_media_pct': round(statistics.fmean(o['carteira_pct'] for o in obs), 2),
                         'ibovespa_medio_pct': round(statistics.fmean(o['ibovespa_pct'] for o in obs), 2),
                         'cdi_medio_pct': round(statistics.fmean(o['cdi_pct'] for o in obs), 2)})
        saida['horizontes'][nome] = info
        if not obs:
            prox = min((p['vence_em'] for p in pend), default='-')
            print(f'{nome:10} sem retratos vencidos; o primeiro vence em {prox}')
            continue
        print(f"{nome:10} n={len(obs):2} ({info['amostra']}): carteira {info['carteira_media_pct']:+.1f}%, "
              f"Ibovespa {info['ibovespa_medio_pct']:+.1f}%, CDI {info['cdi_medio_pct']:+.1f}%; excesso médio "
              f"{info['excesso_medio_pp']:+.1f} pp (mediana {info['excesso_mediano_pp']:+.1f}); acima do Ibovespa em "
              f"{info['acima_do_ibov_pct']}% dos retratos")
    with open(os.path.join(PASTA, 'medicao.json'), 'w', encoding='utf-8') as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
