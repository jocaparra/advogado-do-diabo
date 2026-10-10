"""Avalia as recomendações passadas contra o Ibovespa (4 e 12 semanas) a partir do histórico.

uso: python src/avaliar.py <pasta_de_qualquer_semana>

Lê historico_carteira.json (na pasta acima das semanas) e as séries de preço de todas as
semana_*/precos.json vizinhas, sem rede. Para cada recomendação com horizonte já vencido calcula o
retorno do ticker, o do Ibovespa na mesma janela e o excesso. Agrega por ação sugerida, por certeza
e por posição no ranking, e mede se a nota ordena (correlação de postos de Spearman).

Saída: avaliacao.json (ao lado do histórico). Com amostra pequena o resultado é marcado como
"amostra insuficiente": não conclua nada antes disso.
"""
import datetime as dt
import glob
import json
import os
import statistics
import sys

import carteira as C

HORIZONTES = {'4_semanas': 28, '12_semanas': 84}
MIN_OBS = 30        # observações vencidas por horizonte para falar em evidência
MIN_SEMANAS = 8     # semanas distintas
JANELA_PRECO = 5    # dias de calendário para trás aceitos ao procurar o fechamento da data


def spearman(x, y):
    """Correlação de postos (empates com posto médio). None se não definida."""
    if len(x) < 3 or len(x) != len(y):
        return None

    def postos(v):
        ordem = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[ordem[j + 1]] == v[ordem[i]]:
                j += 1
            for k in range(i, j + 1):
                r[ordem[k]] = (i + j) / 2 + 1
            i = j + 1
        return r

    rx, ry = postos(x), postos(y)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def carregar_series(raiz):
    """ticker -> {data_iso: fechamento}; semanas mais recentes sobrescrevem as antigas."""
    series = {}
    for p in sorted(glob.glob(os.path.join(raiz, 'semana_*', 'precos.json'))):
        d = C.ler(p)
        itens = {t: v.get('serie') for t, v in d.get('acoes', {}).items()}
        itens['^BVSP'] = d.get('ibovespa', {}).get('serie')
        for t, s in itens.items():
            if isinstance(s, list):
                series.setdefault(t, {}).update({x[0]: x[1] for x in s})
    return series


def fechamento(serie, alvo, janela=JANELA_PRECO):
    """Último fechamento em `alvo` ou até `janela` dias antes. (None, None) se não houver."""
    d = alvo
    for _ in range(janela + 1):
        v = serie.get(d.isoformat())
        if v is not None:
            return d, v
        d -= dt.timedelta(days=1)
    return None, None


def avaliar_entradas(semanas, series, hoje):
    """Lista de observações vencidas e contagem de pendentes, por horizonte."""
    obs = {h: [] for h in HORIZONTES}
    pend = {h: 0 for h in HORIZONTES}
    ibov = series.get('^BVSP', {})
    ultima = max(ibov) if ibov else None
    for sem in semanas:
        for r in sem['ranking']:
            try:
                d0 = dt.date.fromisoformat(r.get('data_cotacao') or sem['data'])
            except ValueError:
                continue
            s = series.get(r['ticker'])
            if s is None or not r.get('preco_atual'):
                continue
            # preço inicial na MESMA base da série mais recente (ajustada por desdobramentos);
            # o preço gravado no histórico é o nominal da época e quebraria o retorno após um split
            _, p0 = fechamento(s, d0)
            if p0 is None:
                p0 = r['preco_atual']
            _, b0 = fechamento(ibov, d0)
            for h, dias in HORIZONTES.items():
                alvo = d0 + dt.timedelta(days=dias)
                if alvo > hoje or ultima is None or alvo.isoformat() > ultima:
                    pend[h] += 1
                    continue
                d1, p1 = fechamento(s, alvo)
                d1b, b1 = fechamento(ibov, alvo)
                if None in (p1, b0, b1):
                    continue
                rt = (p1 / p0 - 1) * 100
                rb = (b1 / b0 - 1) * 100
                obs[h].append({'semana': sem['data'], 'ticker': r['ticker'], 'posicao': r['posicao'], 'nota': r['nota'],
                               'acao': r['acao_sugerida'], 'certeza': r['certeza'], 'retorno_pct': round(rt, 2),
                               'ibovespa_pct': round(rb, 2), 'excesso_pp': round(rt - rb, 2),
                               'upside_ajustado_pct': r.get('upside_ajustado_pct'), 'data_fim': d1.isoformat()})
    return obs, pend


def _resumo(lista):
    if not lista:
        return {'n': 0}
    ex = [o['excesso_pp'] for o in lista]
    return {'n': len(lista), 'excesso_medio_pp': round(statistics.fmean(ex), 2), 'excesso_mediano_pp': round(statistics.median(ex), 2),
            'acerto_pct': round(sum(e > 0 for e in ex) / len(ex) * 100, 1),
            'retorno_medio_pct': round(statistics.fmean(o['retorno_pct'] for o in lista), 2)}


def agregar(obs_h):
    por = lambda campo: {k: _resumo([o for o in obs_h if o[campo] == k]) for k in sorted({o[campo] for o in obs_h})}
    semanas = sorted({o['semana'] for o in obs_h})
    rhos = []
    for s in semanas:
        o = [x for x in obs_h if x['semana'] == s]
        rho = spearman([x['nota'] for x in o], [x['excesso_pp'] for x in o])
        if rho is not None:
            rhos.append(rho)
    topo = [o for o in obs_h if o['posicao'] <= 5]
    ranking = {'top5': _resumo(topo), 'demais': _resumo([o for o in obs_h if o['posicao'] > 5])}
    n_sem = len(semanas)
    suficiente = len(obs_h) >= MIN_OBS and n_sem >= MIN_SEMANAS
    comprar = _resumo([o for o in obs_h if o['acao'] == 'comprar'])
    evitar = _resumo([o for o in obs_h if o['acao'] == 'evitar'])
    return {'observacoes': len(obs_h), 'semanas': n_sem, 'amostra': 'suficiente' if suficiente else 'insuficiente',
            'geral': _resumo(obs_h), 'por_acao': por('acao'), 'por_certeza': por('certeza'), 'por_posicao': ranking,
            'spearman_nota_excesso_medio': round(statistics.fmean(rhos), 3) if rhos else None, 'semanas_com_spearman': len(rhos),
            'spread_comprar_menos_evitar_pp': (round(comprar['excesso_medio_pp'] - evitar['excesso_medio_pp'], 2)
                                               if comprar.get('n') and evitar.get('n') else None)}


def avaliar(raiz, hoje=None):
    hoje = hoje or dt.date.today()
    h = os.path.join(raiz, 'historico_carteira.json')
    if not os.path.exists(h):
        return None
    hist = C.ler(h)
    series = carregar_series(raiz)
    obs, pend = avaliar_entradas(hist['semanas'], series, hoje)
    saida = {'data_avaliacao': hoje.isoformat(), 'semanas_no_historico': len(hist['semanas']),
             'metodo': 'retorno de preço (sem dividendos) do ticker contra o Ibovespa, da data da cotação da recomendação até +28 e +84 dias; '
                       'Ibovespa é índice de retorno total, o que subestima o ticker em ~dividend yield',
             'minimos_para_conclusao': {'observacoes': MIN_OBS, 'semanas': MIN_SEMANAS}, 'horizontes': {}}
    for hz in HORIZONTES:
        ag = agregar(obs[hz])
        ag['pendentes'] = pend[hz]
        saida['horizontes'][hz] = ag
    saida['observacoes'] = {hz: obs[hz] for hz in HORIZONTES}
    return saida


def main():
    pasta = C.pasta_semana()
    raiz = os.path.dirname(pasta)
    r = avaliar(raiz)
    if r is None:
        sys.exit('historico_carteira.json não encontrado ao lado das pastas de semana')
    with open(os.path.join(raiz, 'avaliacao.json'), 'w', encoding='utf-8') as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    print(f'avaliação: {r["semanas_no_historico"]} semana(s) no histórico')
    for hz, ag in r['horizontes'].items():
        g = ag['geral']
        if not ag['observacoes']:
            print(f'  {hz}: sem observações vencidas ({ag["pendentes"]} pendentes)')
            continue
        print(f'  {hz}: {ag["observacoes"]} obs em {ag["semanas"]} semanas, amostra {ag["amostra"]}; excesso médio {g["excesso_medio_pp"]:+.2f} pp, acerto {g["acerto_pct"]}%')
        for k, v in ag['por_acao'].items():
            print(f'      {k:9} n={v["n"]:3} excesso {v["excesso_medio_pp"]:+.2f} pp, acerto {v["acerto_pct"]}%')
        print(f'      Spearman nota x excesso (média das semanas): {ag["spearman_nota_excesso_medio"]}')


if __name__ == '__main__':
    main()
