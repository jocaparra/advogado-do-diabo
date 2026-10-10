"""Calcula em código todos os campos derivados da semana (casas.json e sintese.json).

uso: python src/calcular_derivados.py <pasta_da_semana> [--simular]

Ordem: precos.json + casas.json (coletados) -> campos derivados de casas.json -> campos mecânicos
de sintese.json (preço, upsides, mediana, nota, posição). O agente analista só escreve julgamento
(componentes, ação, certeza, textos); o que é conta, o código faz. Registra em
sintese.json['calculos_automaticos'] cada valor que mudou, para o analista revisar o texto.
"""
import datetime as dt
import json
import os
import sys

import carteira as C
import regras as R


def _fmt(v):
    return 'não verificado' if v is None else v


def derivar_casas(ca, hoje, pol):
    mud = []
    for t, v in ca['tickers'].items():
        cont = R.contagem_ratings(v['casas'], pol)
        med, n, _ = R.mediana_alvos(v['casas'], hoje, pol)
        novo = {'contagem_verificada': {k: cont[k] for k in ('compra', 'neutro', 'venda')},
                'n_casas_verificadas': cont['n_casas'],
                'mediana_preco_alvo': med, 'moeda_mediana': 'R$', 'n_alvos_mediana': n,
                'status': 'ok' if cont['n_casas'] >= pol['min_casas_consenso'] else 'dado insuficiente'}
        for k, nv in novo.items():
            if v.get(k) != nv:
                mud.append({'arquivo': 'casas.json', 'ticker': t, 'campo': k, 'antes': v.get(k), 'depois': nv})
            v[k] = nv
    return mud


def derivar_sintese(sy, ca, pr, xp, hoje, pol):
    mud = []
    pesos = sy['metodologia']['pesos']
    xpa = {a['ticker']: a for a in xp['acoes']}
    for r in sy['ranking']:
        t = r['ticker']
        p = pr['acoes'].get(t, {})
        c = ca['tickers'].get(t, {})
        ret5 = C_pct(p.get('ret_5d'))
        novos = {}
        if R.num(p.get('preco_atual')) is not None:
            novos['preco_atual'] = p['preco_atual']
            novos['data_cotacao'] = p['data_cotacao']
        alvo = xpa.get(t, {}).get('preco_alvo')
        novos['preco_alvo_xp'] = alvo if R.num(alvo) is not None else r.get('preco_alvo_xp')
        px = novos.get('preco_atual', r.get('preco_atual'))
        up_xp = R.upside(novos['preco_alvo_xp'], px)
        med = c.get('mediana_preco_alvo')
        n = c.get('n_alvos_mediana', 0)
        up_med = R.upside(med, px)
        novos['upside_xp_pct'] = _fmt(up_xp)
        novos['mediana_casas'] = _fmt(med)
        novos['n_alvos_mediana'] = n
        novos['upside_mediana_pct'] = _fmt(up_med)
        ua = R.upside_ajustado(up_xp, up_med, ret5, pol)
        novos['upside_ajustado_pct'] = _fmt(ua)
        base = [v for v in (up_xp, up_med) if v is not None]
        if base:
            media = sum(base) / len(base)
            desc = pol['peso_desconto_rali'] * max(ret5 or 0.0, 0.0)
            txt = ('Projeção: média do upside até a XP' + (' e até a mediana das casas' if up_med is not None else '')
                   + f' ({media:.1f}%)'.replace('.', ','))
            if desc > 0:
                txt += f', menos metade do ganho de 5 pregões ({ret5:.2f}%)'.replace('.', ',')
                velho = r.get('justificativa_upside_ajustado', '')
                i = velho.find('tratada como parcela')
                txt += (', ' + velho[i:]) if i >= 0 else '.'
            else:
                txt += (', sem desconto porque o papel não subiu nos últimos 5 pregões.' if (ret5 or 0) <= 0 else '.')
            novos['justificativa_upside_ajustado'] = txt
        cont = c.get('contagem_verificada')
        if cont is not None:
            nc = c['n_casas_verificadas']
            novos['consenso_casas'] = (f'{cont["compra"]} compra, {cont["neutro"]} neutro, {cont["venda"]} venda entre {nc} casas verificadas; '
                                       + ('consenso' if nc >= pol['min_casas_consenso'] else f'não é consenso (menos de {pol["min_casas_consenso"]} casas)')
                                       + (f'; mediana de R$ {med:.2f} com {n} alvo(s)'.replace('.', ',') if med is not None else '; mediana de preço alvo não verificada'))
        if ret5 is not None:
            novos['retornos'] = {**r.get('retornos', {}), '5d_pct': ret5}
        if set(pesos) <= set(r.get('componentes', {})):
            novos['nota'] = R.nota(r['componentes'], pesos)
        for k, nv in novos.items():
            if r.get(k) != nv:
                mud.append({'arquivo': 'sintese.json', 'ticker': t, 'campo': k, 'antes': r.get(k), 'depois': nv})
            r[k] = nv
    # ordem e posição
    antes = {r['ticker']: r['posicao'] for r in sy['ranking']}
    sy['ranking'].sort(key=lambda r: (-r['nota'], r['posicao']))
    for i, r in enumerate(sy['ranking'], 1):
        if antes[r['ticker']] != i:
            mud.append({'arquivo': 'sintese.json', 'ticker': r['ticker'], 'campo': 'posicao', 'antes': antes[r['ticker']], 'depois': i})
        r['posicao'] = i
    return mud


def C_pct(s):
    try:
        return float(str(s).replace('%', ''))
    except ValueError:
        return None


def main():
    simular = '--simular' in sys.argv
    sys.argv = [a for a in sys.argv if a != '--simular']
    pasta = C.pasta_semana()
    a, m, d = C.data_semana(pasta)
    hoje = dt.date(a, m, d)
    xp = C.ler(C.arquivo_xp(pasta))
    pr = C.ler(os.path.join(pasta, 'precos.json'))
    ca = C.ler(os.path.join(pasta, 'casas.json'))
    pol = R.parametros(C.ler(os.path.join(pasta, 'textos.json'), {}))
    mud = derivar_casas(ca, hoje, pol)
    sp = os.path.join(pasta, 'sintese.json')
    sy = C.ler(sp, None) if os.path.exists(sp) else None
    if sy:
        mud += derivar_sintese(sy, ca, pr, xp, hoje, pol)
        sy['calculos_automaticos'] = {'regra': 'src/regras.py', 'data': dt.date.today().isoformat(),
                                      'alterados': [x for x in mud if x['arquivo'] == 'sintese.json']}
    relevantes = [x for x in mud if x['campo'] not in ('consenso_casas', 'status', 'moeda_mediana', 'contagem_verificada', 'n_casas_verificadas')]
    print(f'{len(mud)} campos recalculados ({len(relevantes)} numéricos relevantes)')
    for x in relevantes:
        print(f'  {x["arquivo"]:12} {x["ticker"]:7} {x["campo"]:22} {x["antes"]!s:>16} -> {x["depois"]}')
    if simular:
        print('(simulação: nada foi gravado)')
        return
    with open(os.path.join(pasta, 'casas.json'), 'w', encoding='utf-8') as f:
        json.dump(ca, f, ensure_ascii=False, indent=1)
    if sy:
        with open(sp, 'w', encoding='utf-8') as f:
            json.dump(sy, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
