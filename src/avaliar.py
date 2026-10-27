"""Avalia as recomendações passadas contra o Ibovespa (1, 4 e 12 semanas) a partir do histórico.

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
import math
import os
import statistics
import sys

import calibracao as K
import carteira as C

HORIZONTES = {'1_semana': 7, '4_semanas': 28, '12_semanas': 84}
# Faixa (pp de excesso contra o Ibovespa) dentro da qual "aguardar" conta como confirmado. Convenção do
# projeto, NÃO calibrada: 3 pp em 1 semana escalado pela raiz do prazo (4 sem ~ 6 pp, 12 sem ~ 10 pp).
BANDA_NEUTRA_PP = {'1_semana': 3.0, '4_semanas': 6.0, '12_semanas': 10.0}
DIRECAO = {'comprar': 'acima', 'evitar': 'abaixo', 'aguardar': 'neutra'}
COMPONENTES = ('catalisadores', 'noticias', 'momentum', 'macro_eleicao', 'valuation_upside')
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


def _data_coleta(d):
    """Data (iso) da coleta de um precos.json, ou None."""
    txt = str(d.get('data_coleta') or '')[:10]
    try:
        return dt.date.fromisoformat(txt).isoformat()
    except ValueError:
        return None


def carregar_proventos(raiz):
    """(divs, cobertura) de todas as semanas.

    divs: ticker -> {data_ex_iso: valor por ação}. cobertura: ticker -> (ate, ate_verificado): proventos
    conhecidos até `ate` (iso) e confirmados em segunda fonte até `ate_verificado` ('' se nunca). Vem de precos.json com a chave `dividendos` (coletados pelo precos_yahoo.py,
    fonte única, não verificada) e de proventos.json (coletar_proventos.py), só dos tickers cuja série foi
    CONFIRMADA em segunda fonte. Semanas coletadas sem a chave não dão cobertura."""
    divs, cob = {}, {}

    def cobrir(t, ate, verificado):
        qualquer, verif = cob.get(t, ('', ''))
        cob[t] = (max(qualquer, ate), max(verif, ate) if verificado else verif)

    for p in sorted(glob.glob(os.path.join(raiz, 'semana_*', 'precos.json'))):
        d = C.ler(p)
        coleta = _data_coleta(d)
        for t, v in d.get('acoes', {}).items():
            if not isinstance(v.get('dividendos'), list):
                continue
            for x in v['dividendos']:
                if isinstance(x, list) and len(x) == 2:
                    divs.setdefault(t, {})[x[0]] = x[1]
            if coleta:
                cobrir(t, coleta, False)
    for p in sorted(glob.glob(os.path.join(raiz, 'semana_*', 'proventos.json'))):
        d = C.ler(p)
        for t, v in (d.get('por_ticker') or {}).items():
            if (v.get('verificacao') or {}).get('status') != 'confirmado' or not v.get('coberto_ate'):
                continue
            for x in v.get('eventos') or []:
                if isinstance(x, list) and len(x) == 2:
                    divs.setdefault(t, {})[x[0]] = x[1]
            cobrir(t, v['coberto_ate'], True)
    return divs, cob


def carregar_dividendos(raiz):
    """ticker -> {data_ex_iso: valor por ação} (sem a cobertura; veja carregar_proventos)."""
    return carregar_proventos(raiz)[0]


def proventos(divs, ticker, d0, d1):
    """Soma dos proventos por ação com data ex em (d0, d1]. Sem reinvestimento (aproximação conservadora)."""
    return sum(v for d, v in (divs or {}).get(ticker, {}).items()
               if _num(v) and d0.isoformat() < d <= d1.isoformat())


def fechamento(serie, alvo, janela=JANELA_PRECO):
    """Último fechamento em `alvo` ou até `janela` dias antes. (None, None) se não houver."""
    d = alvo
    for _ in range(janela + 1):
        v = serie.get(d.isoformat())
        if v is not None:
            return d, v
        d -= dt.timedelta(days=1)
    return None, None


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _preco_ok(v):
    """Preço utilizável: número finito e positivo (zero ou NaN quebrariam o retorno)."""
    return isinstance(v, (int, float)) and math.isfinite(v) and v > 0


def veredito(direcao, excesso_pp, banda):
    """Marca uma previsão contra o excesso observado. `inconclusivo` quando a direção ou o excesso não são utilizáveis."""
    if not isinstance(excesso_pp, (int, float)) or not math.isfinite(excesso_pp):
        return 'inconclusivo'
    if direcao == 'acima':
        return 'acerto' if excesso_pp > 0 else 'erro'
    if direcao == 'abaixo':
        return 'acerto' if excesso_pp < 0 else 'erro'
    if direcao == 'neutra':
        if abs(excesso_pp) <= banda:
            return 'neutro_confirmado'
        return 'oportunidade_perdida' if excesso_pp > 0 else 'queda_evitada'
    return 'inconclusivo'


def avaliar_entradas(semanas, series, hoje, dividendos=None, cobertura=None, exclusoes=None):
    """Lista de observações vencidas e contagem de pendentes, por horizonte.

    `cobertura` (ticker -> (ate, ate_verificado), de carregar_proventos) diz até quando os proventos do ticker são
    conhecidos: uma observação cujo fim da janela passa dessa data fica com `proventos_completos=False` (retorno
    só de preço, não comparável ao Ibovespa de retorno total). Sem `cobertura`, assume-se completo.

    `exclusoes` (dict opcional, preenchido no lugar) conta as linhas e janelas descartadas por motivo, para que nada
    saia da avaliação em silêncio: 'linha_malformada', 'sem_data', 'sem_serie', 'sem_preco_inicial' e, por horizonte,
    'sem_preco_final'."""
    def excluir(motivo):
        if exclusoes is not None:
            exclusoes[motivo] = exclusoes.get(motivo, 0) + 1

    obs = {h: [] for h in HORIZONTES}
    pend = {h: 0 for h in HORIZONTES}
    ibov = series.get('^BVSP', {})
    ultima = max(ibov) if ibov else None
    for sem in semanas:
        if not isinstance(sem, dict) or not isinstance(sem.get('ranking'), list):
            continue
        for r in sem['ranking']:
            # uma linha malformada no histórico não pode derrubar a avaliação inteira
            if (not isinstance(r, dict) or not isinstance(r.get('ticker'), str) or not isinstance(r.get('acao_sugerida'), str)
                    or not all(_num(r.get(k)) for k in ('posicao', 'nota'))):
                excluir('linha_malformada')
                continue
            try:
                d0 = dt.date.fromisoformat(r.get('data_cotacao') or sem.get('data'))
            except (ValueError, TypeError):
                excluir('sem_data')
                continue
            s = series.get(r['ticker'])
            if s is None or not r.get('preco_atual'):
                excluir('sem_serie')
                continue
            # preço inicial na MESMA base da série mais recente (ajustada por desdobramentos);
            # o preço gravado no histórico é o nominal da época e quebraria o retorno após um split
            _, p0 = fechamento(s, d0)
            if p0 is None:
                p0 = r['preco_atual']
            _, b0 = fechamento(ibov, d0)
            if not (_preco_ok(p0) and _preco_ok(b0)):
                excluir('sem_preco_inicial')
                continue
            for h, dias in HORIZONTES.items():
                alvo = d0 + dt.timedelta(days=dias)
                if alvo > hoje or ultima is None or alvo.isoformat() > ultima:
                    pend[h] += 1
                    continue
                d1, p1 = fechamento(s, alvo)
                _, b1 = fechamento(ibov, alvo)
                if not (_preco_ok(p1) and _preco_ok(b1)):
                    excluir(f'sem_preco_final_{h}')
                    continue
                prov = proventos(dividendos, r['ticker'], d0, d1)
                if cobertura is None:
                    completos, verificados = True, False
                else:
                    ate, ate_verif = cobertura.get(r['ticker'], ('', ''))
                    completos = bool(ate and ate >= d1.isoformat())
                    verificados = bool(ate_verif and ate_verif >= d1.isoformat())
                rt = ((p1 + prov) / p0 - 1) * 100  # retorno total, comparável ao Ibovespa
                rb = (b1 / b0 - 1) * 100
                direcao = DIRECAO.get(r['acao_sugerida'])
                obs[h].append({'semana': sem['data'], 'ticker': r['ticker'], 'posicao': r['posicao'], 'nota': r['nota'],
                               'acao': r['acao_sugerida'], 'certeza': r.get('certeza') or 'não informada', 'retorno_pct': round(rt, 2),
                               'proventos_pct': round(prov / p0 * 100, 2), 'proventos_completos': completos,
                               'proventos_verificados': verificados,
                               'ibovespa_pct': round(rb, 2), 'excesso_pp': round(rt - rb, 2),
                               'upside_ajustado_pct': r.get('upside_ajustado_pct'), 'data_fim': d1.isoformat(),
                               'direcao_esperada': direcao, 'veredito': veredito(direcao, rt - rb, BANDA_NEUTRA_PP[h]),
                               'componentes': r.get('componentes')})
    return obs, pend


def _resumo(lista):
    """Resumo de um grupo de observações.

    `acima_ibov_pct`: % com excesso > 0 (independe da previsão). `acerto_pct`: acertos / (acertos + erros)
    direcionais; None quando o grupo não tem previsão direcional (ex.: só "aguardar"). Para "evitar", acertar
    é cair abaixo do Ibovespa, então os dois números são opostos."""
    if not lista:
        return {'n': 0}
    ex = [o['excesso_pp'] for o in lista]
    dir_ = [o for o in lista if o.get('veredito') in ('acerto', 'erro')]
    return {'n': len(lista), 'excesso_medio_pp': round(statistics.fmean(ex), 2), 'excesso_mediano_pp': round(statistics.median(ex), 2),
            'acima_ibov_pct': round(sum(e > 0 for e in ex) / len(ex) * 100, 1),
            'acerto_pct': round(sum(o['veredito'] == 'acerto' for o in dir_) / len(dir_) * 100, 1) if dir_ else None,
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
    por_veredito = {}
    for o in obs_h:
        por_veredito[o['veredito']] = por_veredito.get(o['veredito'], 0) + 1
    direcionais = [o for o in obs_h if o['veredito'] in ('acerto', 'erro')]
    rho_comp = {}
    for c in COMPONENTES:
        rs = []
        for s in semanas:
            o = [x for x in obs_h if x['semana'] == s and x.get('componentes') and c in x['componentes']]
            rho = spearman([x['componentes'][c] for x in o], [x['excesso_pp'] for x in o])
            if rho is not None:
                rs.append(rho)
        if rs:
            rho_comp[c] = {'spearman_medio': round(statistics.fmean(rs), 3), 'semanas': len(rs)}
    sem_prov = sum(not o.get('proventos_completos', True) for o in obs_h)
    nao_verif = sum(o.get('proventos_completos', True) and not o.get('proventos_verificados', False) for o in obs_h)
    return {'observacoes': len(obs_h), 'semanas': n_sem, 'por_veredito': por_veredito,
            'proventos': {'completo': sem_prov == 0, 'obs_sem_cobertura': sem_prov, 'obs_fonte_unica': nao_verif},
            'acerto_direcional_pct': (round(sum(o['veredito'] == 'acerto' for o in direcionais) / len(direcionais) * 100, 1)
                                      if direcionais else None),
            'spearman_por_componente': rho_comp, 'amostra': 'suficiente' if suficiente else 'insuficiente',
            'calibracao_certeza': K.por_grupo(obs_h, 'certeza', MIN_OBS, MIN_SEMANAS),
            'geral': _resumo(obs_h), 'por_acao': por('acao'), 'por_certeza': por('certeza'), 'por_posicao': ranking,
            'spearman_nota_excesso_medio': round(statistics.fmean(rhos), 3) if rhos else None, 'semanas_com_spearman': len(rhos),
            'spread_comprar_menos_evitar_pp': (round(comprar['excesso_medio_pp'] - evitar['excesso_medio_pp'], 2)
                                               if comprar.get('n') and evitar.get('n') else None)}


def _versao_codigo():
    """Commit do git (com '+' se houver alteração local não commitada) ou None fora de um repositório."""
    import subprocess
    aqui = os.path.dirname(os.path.abspath(__file__))
    try:
        h = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=aqui, capture_output=True, text=True, timeout=5)
        if h.returncode != 0:
            return None
        sujo = subprocess.run(['git', 'status', '--porcelain', '--', '.'], cwd=aqui, capture_output=True, text=True, timeout=5)
        return h.stdout.strip() + ('+' if sujo.stdout.strip() else '')
    except (OSError, subprocess.SubprocessError):
        return None


def avaliar(raiz, hoje=None):
    hoje = hoje or dt.date.today()
    h = os.path.join(raiz, 'historico_carteira.json')
    if not os.path.exists(h):
        return None
    hist = C.ler(h)
    series = carregar_series(raiz)
    divs, cobertura = carregar_proventos(raiz)
    exclusoes = {}
    obs, pend = avaliar_entradas(hist['semanas'], series, hoje, divs, cobertura, exclusoes)
    saida = {'data_avaliacao': hoje.isoformat(), 'semanas_no_historico': len(hist['semanas']),
             'reproducao': {'codigo': _versao_codigo(), 'banda_neutra_pp': BANDA_NEUTRA_PP, 'horizontes_dias': HORIZONTES,
                            'reinvestimento_proventos': False, 'janela_preco_dias': JANELA_PRECO, 'corte': hoje.isoformat()},
             'excluidas': exclusoes,
             'metodo': 'retorno total do ticker (preço mais dividendos e JCP com data ex no período, sem reinvestimento) contra o '
                       'Ibovespa (índice de retorno total), da data da cotação da recomendação até +7, +28 e +84 dias; '
                       'observações sem cobertura de proventos até o fim da janela ficam só com retorno de preço e são contadas em '
                       '"proventos.obs_sem_cobertura" (a avaliação fica marcada como incompleta)',
             'minimos_para_conclusao': {'observacoes': MIN_OBS, 'semanas': MIN_SEMANAS}, 'horizontes': {}}
    for hz in HORIZONTES:
        ag = agregar(obs[hz])
        ag['pendentes'] = pend[hz]
        saida['horizontes'][hz] = ag
    incompletos = {hz: ag['proventos']['obs_sem_cobertura'] for hz, ag in saida['horizontes'].items()
                   if ag['proventos']['obs_sem_cobertura']}
    saida['avaliacao_incompleta'] = bool(incompletos)
    if incompletos:
        saida['aviso_proventos'] = ('observações sem proventos conhecidos até o fim da janela têm retorno só de preço, contra um '
                                    'Ibovespa de retorno total: o excesso delas está subestimado. Colete com precos_yahoo.py ou '
                                    'coletar_proventos.py; enquanto isso, não use este resultado como conclusão. '
                                    f'Observações sem cobertura por horizonte: {incompletos}')
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
        print(f'  {hz}: {ag["observacoes"]} obs em {ag["semanas"]} semanas, amostra {ag["amostra"]}; excesso médio {g["excesso_medio_pp"]:+.2f} pp, acima do Ibovespa em {g["acima_ibov_pct"]}% das vezes')
        for k, v in ag['por_acao'].items():
            ac = 'n/a' if v['acerto_pct'] is None else f'{v["acerto_pct"]}%'
            print(f'      {k:9} n={v["n"]:3} excesso {v["excesso_medio_pp"]:+.2f} pp, acima do Ibovespa {v["acima_ibov_pct"]}%, acerto da previsão {ac}')
        print(f'      Spearman nota x excesso (média das semanas): {ag["spearman_nota_excesso_medio"]}')
    if r.get('avaliacao_incompleta'):
        print('  AVALIAÇÃO INCOMPLETA:', r['aviso_proventos'])


if __name__ == '__main__':
    main()
