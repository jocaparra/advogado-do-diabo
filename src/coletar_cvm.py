"""Coleta determinística de fundamentos na CVM (DFP, ITR, FCA) para os tickers da semana.

uso: python src/coletar_cvm.py <pasta_da_semana>

Entradas: xp.json (tickers), precos.json (preço e data), macro.json (câmbio, se a moeda não for real).
Saída: fundamentos_cvm.json, com cada número, o método e o documento de origem. Nenhum LLM nem busca web.
"""
import datetime as dt
import json
import os
import re
import sys

import carteira as C
import cvm
import indicadores as I


def _unit_acoes(composicao):
    """'1 ação ordinária e 4 preferenciais' -> 5. Devolve None se não conseguir ler."""
    if not composicao:
        return None
    nums = [int(n) for n in re.findall(r'(\d+)\s*(?:a[cç][aã]o|a[cç][oõ]es|ON|PN|ordin|prefer)', composicao, re.I)]
    return float(sum(nums)) if nums else None


def _cambio(macro):
    try:
        serie = macro['figura_8_series']['dolar_ptax']
        return serie[-1][1], serie[-1][0]
    except (KeyError, IndexError, TypeError):
        return None, None


def main():
    pasta = C.pasta_semana()
    a, m, d = C.data_semana(pasta)
    hoje = dt.date(a, m, d)
    xp = C.ler(C.arquivo_xp(pasta))
    precos = C.ler(os.path.join(pasta, 'precos.json'))
    macro = C.ler(os.path.join(pasta, 'macro.json'), {})
    tickers = [x['ticker'] for x in xp['acoes']]
    cambio, dt_cambio = _cambio(macro)

    mapa = {}
    for ano in (hoje.year, hoje.year - 1):
        try:
            for t, v in cvm.mapa_tickers(ano).items():
                mapa.setdefault(t, v)
        except Exception as e:
            print(f'aviso: FCA {ano} indisponível ({e})', file=sys.stderr)
    for t, v in cvm.manual().items():
        mapa[t] = v
    cnpjs = {mapa[t]['cnpj'] for t in tickers if t in mapa}
    cad = cvm.cadastro(cnpjs)
    dados = cvm.carregar_empresas(cnpjs, hoje.year)

    resultado = {'data_coleta': hoje.isoformat(), 'fonte': 'CVM, dados abertos (DFP, ITR, FCA, composição do capital)',
                 'url_base': cvm.BASE_URL, 'metodo': 'src/coletar_cvm.py; valores em unidades da moeda de reporte; 12 meses = DFP + ITR acumulado - ITR comparativo',
                 'cambio': {'rs_por_usd': cambio, 'data': dt_cambio, 'fonte': 'macro.json (PTAX)'}, 'tickers': {}}
    for t in tickers:
        item = {'ticker': t}
        if t not in mapa:
            item.update({'situacao': 'sem_dado_cvm', 'motivo': 'ticker não localizado na FCA da CVM nem em dados/mapa_tickers_manual.json (BDR de emissor estrangeiro não tem DFP/ITR na CVM; use as demonstrações do emissor no exterior)', 'certeza': 'alta'})
            resultado['tickers'][t] = item
            continue
        info = mapa[t]
        cnpj = info['cnpj']
        saida, meta = dados[cnpj]
        px = precos.get('acoes', {}).get(t, {})
        preco = {'valor': px.get('preco_atual'), 'data': px.get('data_cotacao')} if px.get('preco_atual') else None
        acoes = cvm.capital(cnpj, hoje.year)
        unit = _unit_acoes(info['composicao_unit']) if info['valor_mobiliario'].lower().startswith('unit') else None
        fx = cambio if (meta.get('moeda') or 'REAL') != 'REAL' else None
        calc = I.calcular(saida, meta, preco, acoes, cambio=fx, unit_acoes=unit)
        docs = sorted({(k[0], k[1], k[2], u) for k, u in meta['documentos'].items()}, key=lambda x: (x[1], x[2]))
        if not calc:
            item['motivo'] = ('sem exercício anual completo (31/12) nas demonstrações: empresa nova, exercício social fora do ano civil '
                              'ou documentos ainda não publicados')
        item.update({'situacao': 'ok' if calc else 'sem_demonstracoes', 'cnpj': cnpj, 'nome': info['nome'],
                     'classe': info['valor_mobiliario'], 'segmento': info['segmento'],
                     'cadastro': cad.get(cnpj, {}),
                     'preco': preco})
        if calc:
            item.update(calc)
            item['documentos'] = [{'tipo': k[0], 'data_referencia': k[1], 'versao': k[2], 'url': k[3]} for k in docs[-4:]]
            if acoes:
                item['acoes'] = {k: acoes[k] for k in ('dt_refer', 'total', 'tesouraria', 'ordinarias', 'preferenciais', 'fonte')}
        resultado['tickers'][t] = item
    if cvm.AVISOS_REDE:
        resultado['avisos_coleta'] = sorted(set(cvm.AVISOS_REDE))
        for av in resultado['avisos_coleta']:
            print('aviso:', av, file=sys.stderr)
    saida_path = os.path.join(pasta, 'fundamentos_cvm.json')
    with open(saida_path, 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1)
    ok = [t for t, v in resultado['tickers'].items() if v.get('situacao') == 'ok']
    print(f'fundamentos_cvm.json: {len(ok)} de {len(tickers)} tickers com demonstrações; sem dado: ' +
          ', '.join(t for t in tickers if t not in ok))


if __name__ == '__main__':
    main()
