"""Fatores quantitativos por empresa em uma data qualquer, só com dados conhecidos nela.

Fatores (todos calculados em código, sem LLM):
  valor      = média do posto de E/P (lucro 12m / valor de mercado) e B/P (patrimônio / valor de mercado)
  qualidade  = ROE 12m (lucro 12m / patrimônio líquido)
  momentum   = retorno de 12 meses excluindo o último mês (12-1), com proventos
  dividendos = proventos pagos nos últimos 12 meses / preço
  baixa_vol  = menos a volatilidade diária de 12 meses
Cada fator vira posto percentual (0 a 1) entre as empresas com dado na data; o composto é a média ponderada
dos fatores disponíveis (mínimo de 3). Limite conhecido: valor de mercado usa o preço de um único papel da
empresa para todas as classes de ação.
"""
import bisect
import datetime as dt
import math
import statistics

import quant_dados as Q

FATORES = ('valor', 'qualidade', 'momentum', 'dividendos', 'baixa_vol')
MIN_FATORES = 3


def preparar(tickers, anos_fundamentos, periodo='11y'):
    """Carrega preços, cadastro e fundamentos PIT. Um papel por empresa (o de maior volume financeiro).
    Devolve {cnpj: {ticker, nome, serie, registros, acoes_por_unit}} e a lista de tickers sem dado."""
    cad = Q.tickers_para_cnpj(tickers)
    series, sem = {}, []
    for t in tickers:
        try:
            s = Q.serie_yahoo(f'{t}.SA', periodo)
            if len(s['datas']) > 60:
                series[t] = s
                continue
        except Exception:
            pass
        sem.append((t, 'sem série no Yahoo'))
    por_cnpj = {}
    for t in series:
        if t not in cad:
            sem.append((t, 'sem CNPJ na CVM'))
            continue
        s = series[t]
        liquidez = sum(c * v for c, v in zip(s['close'][-250:], s['volume'][-250:]))
        por_cnpj.setdefault(cad[t]['cnpj'], []).append((liquidez, t))
    fundos = Q.fundamentos_pit(por_cnpj, anos_fundamentos)
    ctx = {}
    for cnpj, lst in por_cnpj.items():
        t = max(lst)[1]
        info = cad[t]
        unit = None
        if str(info.get('valor_mobiliario', '')).lower().startswith('unit'):
            unit = Q.acoes_por_unit(info.get('composicao_unit'))
            if not unit:
                sem.append((t, 'unit sem composição legível'))
                continue
        if cnpj not in fundos:
            sem.append((t, 'sem demonstrações na CVM'))
        ctx[cnpj] = {'ticker': t, 'nome': info.get('nome'), 'serie': series[t], 'registros': fundos.get(cnpj, []),
                     'acoes_por_unit': unit, 'todos': sorted(x[1] for x in lst)}
    return ctx, sem


def _idx(datas, data_iso):
    i = bisect.bisect_right(datas, data_iso) - 1
    return i if i >= 0 else None


def _mercado(emp, est, preco):
    """Valor de mercado (R$) no preço do papel representativo; None se faltar ação ou patrimônio coerente."""
    if not est or not est['acoes']:
        return None
    acoes = est['acoes']
    # o preço da série está na base de hoje (ajustado por desdobramentos): leva as ações à mesma base
    fator_split = 1.0
    for d, r in emp['serie']['splits'].items():
        if d > est['acoes_dt_refer']:
            fator_split *= r
    acoes *= fator_split
    if emp['acoes_por_unit']:
        acoes /= emp['acoes_por_unit']
    cap = preco * acoes
    # algumas companhias informam ações em milhares: corrige quando o P/VP sai absurdo
    if est['pl'] and est['pl'] > 0 and cap / est['pl'] < 0.02:
        cap *= 1000
    elif not est['pl'] and cap < 5e7:
        cap *= 1000
    return cap


def fatores_em(ctx, data_iso):
    """{cnpj: {valor_ep, valor_bp, roe, momentum, dividendos, vol, preco}} das empresas com preço na data."""
    out = {}
    limite_div = (dt.date.fromisoformat(data_iso) - dt.timedelta(days=365)).isoformat()
    for cnpj, emp in ctx.items():
        s = emp['serie']
        i = _idx(s['datas'], data_iso)
        if i is None or i < 252 or (dt.date.fromisoformat(data_iso) - dt.date.fromisoformat(s['datas'][i])).days > 10:
            continue
        preco = s['close'][i]
        adj = s['adj']
        f = {'preco': preco, 'momentum': adj[i - 21] / adj[i - 252] - 1}
        rets = [math.log(adj[k] / adj[k - 1]) for k in range(i - 251, i + 1) if adj[k - 1] > 0 and adj[k] > 0]
        f['vol'] = statistics.pstdev(rets) if len(rets) > 200 else None
        f['dividendos'] = sum(v for d, v in s['div'].items() if limite_div < d <= data_iso) / preco
        est = Q.estado_em(emp['registros'], data_iso) if emp['registros'] else None
        cap = _mercado(emp, est, preco) if est else None
        if est and cap:
            if est['ni_ttm'] is not None:
                f['valor_ep'] = est['ni_ttm'] / cap
            if est['pl'] and est['pl'] > 0:
                f['valor_bp'] = est['pl'] / cap
                if est['ni_ttm'] is not None:
                    f['roe'] = est['ni_ttm'] / est['pl']
        out[cnpj] = f
    return out


def _postos(valores):
    """{chave: posto percentual 0..1} com empates em posto médio; maior valor = maior posto."""
    itens = sorted(valores.items(), key=lambda kv: kv[1])
    n = len(itens)
    res, i = {}, 0
    while i < n:
        j = i
        while j + 1 < n and itens[j + 1][1] == itens[i][1]:
            j += 1
        for k in range(i, j + 1):
            res[itens[k][0]] = ((i + j) / 2 + 0.5) / n
        i = j + 1
    return res


def pontuar(fat, pesos=None):
    """{cnpj: {'composto', 'valor', 'qualidade', ...}} com postos entre as empresas da data."""
    pesos = pesos or {k: 1.0 for k in FATORES}
    cru = {
        'valor_ep': {c: v['valor_ep'] for c, v in fat.items() if v.get('valor_ep') is not None},
        'valor_bp': {c: v['valor_bp'] for c, v in fat.items() if v.get('valor_bp') is not None},
        'qualidade': {c: v['roe'] for c, v in fat.items() if v.get('roe') is not None},
        'momentum': {c: v['momentum'] for c, v in fat.items() if v.get('momentum') is not None},
        'dividendos': {c: v['dividendos'] for c, v in fat.items() if v.get('dividendos') is not None},
        'baixa_vol': {c: -v['vol'] for c, v in fat.items() if v.get('vol') is not None},
    }
    pr = {k: _postos(v) for k, v in cru.items() if len(v) >= 5}
    res = {}
    for c in fat:
        sc = {}
        ep, bp = pr.get('valor_ep', {}).get(c), pr.get('valor_bp', {}).get(c)
        if ep is not None or bp is not None:
            sc['valor'] = statistics.fmean([x for x in (ep, bp) if x is not None])
        for k in ('qualidade', 'momentum', 'dividendos', 'baixa_vol'):
            if c in pr.get(k, {}):
                sc[k] = pr[k][c]
        if len(sc) >= MIN_FATORES:
            w = sum(pesos[k] for k in sc)
            if w > 0:  # pesos que zeram todos os fatores disponíveis não geram nota
                sc['composto'] = sum(pesos[k] * v for k, v in sc.items()) / w
                res[c] = sc
    return res
