"""Consolida em código as evidências da semana para o agente decisor (modo sombra).

uso: python src/consolidar_evidencias.py <pasta_da_semana>

Lê sintese.json (obrigatório) e, quando existirem, precos.json, risco.json, casas.json, fluxo.json,
fundamentos_cvm.json, precos_yahoo.json, noticias.json, contra.json, proventos.json. Grava evidencias.json:
  fatos            id -> valor, TODOS os números que o decisor pode citar (ex.: "PRIO3.upside_ajustado_pct")
  por_ticker       resumo por papel: ranking, fontes disponíveis, dados ausentes, confiança dos dados
  divergencias     conflitos achados por regra, com os ids dos fatos e o arquivo bruto a abrir
  carteira         concentração por setor e pares correlacionados do topo
O decisor lê este arquivo primeiro e só abre os arquivos brutos nas divergências. Nada aqui usa LLM e nada
altera ranking, nota ou pesos. Os múltiplos do Yahoo entram com o rótulo "Yahoo, não auditado".
"""
import datetime as dt
import json
import os
import sys

import carteira as C

LIM_DIVERGENCIA_MULTIPLO = 1.5      # razão Yahoo/CVM fora de [1/1,5; 1,5]
LIM_CORRELACAO = 0.7                # par do topo correlacionado
FONTES = ('casas', 'cvm', 'fluxo', 'noticias', 'yahoo', 'risco')


def _v(d, *caminho):
    for k in caminho:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d.get('valor') if isinstance(d, dict) and 'valor' in d else d


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def consolidar(pasta):
    lê = lambda n, pad=None: C.ler(os.path.join(pasta, n), pad if pad is not None else {})
    sy = lê('sintese.json', None)
    if not sy or 'ranking' not in sy:
        sys.exit('sintese.json ausente ou sem ranking: nada a consolidar')
    pr, ri, ca = lê('precos.json'), lê('risco.json'), lê('casas.json')
    fl, cv, ya = lê('fluxo.json'), lê('fundamentos_cvm.json'), lê('precos_yahoo.json')
    no, ct, pv = lê('noticias.json'), lê('contra.json'), lê('proventos.json')
    fatos, por_ticker, diverg = {}, {}, []

    def fato(t, nome, valor):
        if _num(valor) is not None or isinstance(valor, str):
            fatos[f'{t}.{nome}'] = valor
            return f'{t}.{nome}'
        return None

    for r in sy['ranking']:
        t = r['ticker']
        ausentes, usadas = [], set()
        for k in ('posicao', 'nota', 'upside_xp_pct', 'upside_mediana_pct', 'upside_ajustado_pct', 'n_alvos_mediana'):
            fato(t, k, r.get(k))
        fato(t, 'acao_ranking', r.get('acao_sugerida'))
        fato(t, 'certeza_ranking', r.get('certeza'))
        # casas
        c = (ca.get('tickers') or {}).get(t)
        if c and c.get('status') == 'ok':
            usadas.add('casas')
            fato(t, 'n_casas_verificadas', c.get('n_casas_verificadas'))
        else:
            ausentes.append('casas de análise: dado insuficiente' if c else 'casas.json sem o papel')
        # CVM
        cvt = (cv.get('tickers') or {}).get(t) or {}
        vals = cvt.get('valores') or {}
        mult = {k: _num(_v(vals, k, )) for k in ('p_l', 'p_vp', 'ev_ebitda', 'dividend_yield_12m')}
        if cvt.get('situacao') == 'ok' and any(v is not None for v in mult.values()):
            usadas.add('cvm')
            for k, v in mult.items():
                fato(t, f'cvm_{k}', v)
        else:
            ausentes.append('fundamentos da CVM ausentes')
        # Yahoo (não auditado)
        y = (ya.get('acoes') or {}).get(t)
        if y:
            usadas.add('yahoo')
            for k in ('p_l', 'p_vp', 'ev_ebitda', 'dividend_yield_12m_pct'):
                fato(t, f'yahoo_nao_auditado_{k}', y.get(k))
            for k_y, k_c in (('p_l', 'p_l'), ('p_vp', 'p_vp'), ('ev_ebitda', 'ev_ebitda')):
                a, b = _num(y.get(k_y)), mult.get(k_c)
                if a and b and a > 0 and b > 0 and not (1 / LIM_DIVERGENCIA_MULTIPLO <= a / b <= LIM_DIVERGENCIA_MULTIPLO):
                    diverg.append({'ticker': t, 'tipo': 'multiplo_yahoo_vs_cvm', 'campo': k_y,
                                   'fatos': [f'{t}.yahoo_nao_auditado_{k_y}', f'{t}.cvm_{k_c}'], 'abrir': ['fundamentos_cvm.json', 'precos_yahoo.json'],
                                   'nota': 'CVM prevalece; Yahoo é agregador não auditado'})
        else:
            ausentes.append('Yahoo ausente')
        # fluxo
        f = (fl.get('acoes') or {}).get(t) or {}
        rp = f.get('retornos_preco_pct') or {}
        if rp:
            usadas.add('fluxo')
            for k in ('ret_5_pregoes', 'ret_30_dias_corridos', 'ret_90_dias_corridos'):
                fato(t, f'fluxo_{k}_vs_ibov_pp', (rp.get(k) or {}).get('diferenca_pp'))
            tend = (f.get('tendencia') or {}).get('classificacao')
            if tend:
                fato(t, 'fluxo_tendencia', tend)
        else:
            ausentes.append('fluxo ausente')
        # risco
        rk = (ri.get('tabela_por_ticker') or {}).get(t) or {}
        if rk:
            usadas.add('risco')
            fato(t, 'vol_90pregoes_anual_pct', rk.get('vol_90pregoes_anual_pct'))
            fato(t, 'beta_90pregoes_ibov', rk.get('beta_90pregoes_ibov'))
        else:
            ausentes.append('risco ausente')
        # notícias e objeções
        nt = (no.get('tickers') or {}).get(t) or {}
        itens = nt.get('itens') or []
        fato(t, 'n_noticias_7d', len(itens))
        if itens:
            usadas.add('noticias')
        else:
            ausentes.append('sem notícias datadas na janela')
        obj = [o for o in (ct.get('objecoes') or []) if o.get('ticker') == t]
        fato(t, 'n_objecoes_advogado', len(obj))
        # proventos
        pt = (pv.get('por_ticker') or {}).get(t) or {}
        st = (pt.get('verificacao') or {}).get('status')
        if st:
            fato(t, 'proventos_status', st)
            ev_ = [x[1] for x in pt.get('eventos') or [] if isinstance(x, list) and len(x) == 2 and _num(x[1]) is not None]
            fato(t, 'proventos_n_eventos_janela', len(ev_))
            soma = round(sum(ev_), 4)
            fato(t, 'proventos_soma_janela_por_acao', soma)
            px = _num((pr.get('acoes') or {}).get(t, {}).get('preco_atual'))
            if px:
                fato(t, 'proventos_yield_janela_pct', round(soma / px * 100, 2))
        # regras de divergência sobre o ranking
        acao = r.get('acao_sugerida')
        ua = _num(r.get('upside_ajustado_pct'))
        if acao == 'comprar':
            if 'casas' not in usadas:
                diverg.append({'ticker': t, 'tipo': 'compra_sem_consenso_de_casas', 'fatos': [f'{t}.acao_ranking'],
                               'abrir': ['casas.json'], 'nota': 'recomendação de compra sem casas verificadas'})
            if ua is not None and ua <= 0:
                diverg.append({'ticker': t, 'tipo': 'compra_com_upside_nao_positivo', 'fatos': [f'{t}.upside_ajustado_pct'],
                               'abrir': ['sintese.json'], 'nota': 'regra exige upside ajustado positivo'})
            m30 = _num((rp.get('ret_30_dias_corridos') or {}).get('diferenca_pp'))
            if m30 is not None and m30 < 0:
                diverg.append({'ticker': t, 'tipo': 'compra_contra_o_fluxo', 'fatos': [f'{t}.fluxo_ret_30_dias_corridos_vs_ibov_pp'],
                               'abrir': ['fluxo.json'], 'nota': 'ativo abaixo do Ibovespa em 30 dias'})
        if acao == 'evitar' and ua is not None and ua > 15:
            diverg.append({'ticker': t, 'tipo': 'evitar_com_upside_alto', 'fatos': [f'{t}.upside_ajustado_pct'],
                           'abrir': ['sintese.json'], 'nota': 'evitar apesar de upside ajustado alto'})
        n_ok = len(usadas)
        por_ticker[t] = {'acao_ranking': acao, 'posicao': r.get('posicao'), 'setor': r.get('setor'),
                         'fontes_disponiveis': sorted(usadas), 'dados_ausentes': ausentes,
                         'confianca_dados': 'alta' if n_ok >= 5 and 'casas' in usadas and 'cvm' in usadas
                         else 'média' if n_ok >= 3 and 'cvm' in usadas else 'baixa'}
    # carteira (sobre os "comprar")
    comprar = [t for t, v in por_ticker.items() if v['acao_ranking'] == 'comprar']
    setores = {}
    for t in comprar:
        setores.setdefault(por_ticker[t].get('setor') or 'sem setor', []).append(t)
    corr = {k: v for k, v in (ri.get('correlacao_topo_90pregoes') or {}).items() if isinstance(v, (int, float))}
    pares = sorted([k for k, v in corr.items() if v >= LIM_CORRELACAO])
    for k in pares:
        diverg.append({'ticker': None, 'tipo': 'par_do_topo_correlacionado', 'fatos': [f'carteira.correlacao.{k}'],
                       'abrir': ['risco.json'], 'nota': f'correlação {corr[k]:.2f} no topo: risco concentrado'})
    for k, v in corr.items():
        fatos[f'carteira.correlacao.{k}'] = v
    for s, ts in setores.items():
        fatos[f'carteira.n_comprar_setor.{s}'] = len(ts)
    fatos['carteira.n_comprar'] = len(comprar)
    return {'data': dt.date.today().isoformat(), 'semana': os.path.basename(pasta), 'modo': 'sombra',
            'aviso': 'Camada de entrada do decisor. Saída de modelo, não é recomendação de investimento. '
                     'Múltiplos do Yahoo: "Yahoo, não auditado".',
            'fatos': fatos, 'por_ticker': por_ticker, 'divergencias': diverg,
            'carteira': {'comprar': comprar, 'setores_dos_comprar': setores, 'pares_correlacionados': pares}}


def main():
    pasta = C.pasta_semana(sys.argv[:2])
    ev = consolidar(pasta)
    with open(os.path.join(pasta, 'evidencias.json'), 'w', encoding='utf-8') as f:
        json.dump(ev, f, ensure_ascii=False, indent=1)
    print(f"evidencias.json: {len(ev['por_ticker'])} papéis, {len(ev['fatos'])} fatos, {len(ev['divergencias'])} divergências")
    for d in ev['divergencias']:
        print(f"  {d['tipo']:34} {d['ticker'] or '-':7} {d['nota']}")


if __name__ == '__main__':
    main()
