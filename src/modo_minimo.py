"""Modo mínimo: dossiê numérico de uma lista de tickers, sem agentes e sem Claude Code.

uso: python src/modo_minimo.py <pasta_da_semana> TICKER [TICKER ...]

Faz, em ordem: cria um xp.json mínimo na pasta (a lista de tickers), coleta cotações (Yahoo),
fundamentos (CVM), calcula o dossiê (valuation por cenários, ke implícito) e grava resumo_dossie.md.
Não há notícias, casas de análise, ranking nem relatório PDF: isso exige a cadeia de agentes.
Nada aqui é recomendação de investimento (docs/AVISO_LEGAL.md).
"""
import datetime as dt
import json
import os
import subprocess
import sys

import carteira as C

AQUI = os.path.dirname(os.path.abspath(__file__))


def rodar(script, *args):
    r = subprocess.run([sys.executable, os.path.join(AQUI, script), *args])
    if r.returncode != 0:
        sys.exit(f'falhou: {script}')


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    pasta = os.path.abspath(sys.argv[1])
    tickers = [t.upper() for t in sys.argv[2:]]
    os.makedirs(pasta, exist_ok=True)
    a, m, d = C.data_semana(pasta)
    hoje = dt.date(a, m, d)
    xp = {'data_relatorio': hoje.replace(day=1).isoformat(), 'dados_ate': hoje.isoformat(),
          'fonte': 'lista de tickers do modo mínimo (sem relatório da XP)',
          'acoes': [{'ticker': t, 'empresa': t, 'setor': 'n/d', 'peso_atual': 0, 'peso_anterior': None, 'rating': 'n/d', 'preco_alvo': None}
                    for t in tickers],
          'carteira': {'retornos': {}, 'indicadores': {}}, 'setores': []}
    with open(os.path.join(pasta, 'xp.json'), 'w', encoding='utf-8') as f:
        json.dump(xp, f, ensure_ascii=False, indent=1)
    rodar('precos_yahoo.py', pasta, *tickers)
    rodar('coletar_cvm.py', pasta)
    rodar('gerar_dossie.py', pasta)
    dos = C.ler(os.path.join(pasta, 'dossie.json'))
    linhas = ['# Dossiê numérico (modo mínimo)', '', f'Data: {hoje.isoformat()}. Não é recomendação de investimento.', '',
              '| Ticker | Preço | Valor base | Contra o preço | ke implícito | P/L | P/VP | ROE 12m |', '|---|---:|---:|---:|---:|---:|---:|---:|']
    f1 = lambda v, s='': '-' if v is None else f'{v:,.1f}{s}'
    for t, it in dos['tickers'].items():
        ind, val = it.get('indicadores', {}), it['valuation']
        g = lambda k: (ind.get(k) or {}).get('valor')
        base = val.get('cenarios', {}).get('base', {}) if val.get('status') == 'ok' else {}
        linhas.append(f"| {t} | {f1(it.get('preco'))} | {f1(base.get('valor_justo_por_acao'))} | {f1(base.get('margem_pct'), '%')} | "
                      f"{f1(val.get('ke_implicito_pct'), '%')} | {f1(g('p_l'))} | {f1(g('p_vp'))} | {f1(g('roe_12m'), '%')} |")
    linhas += ['', 'Premissas: `dados/premissas_valuation.json`. O valor base usa ke de 15% e crescimento terminal de 5%.']
    caminho = os.path.join(pasta, 'resumo_dossie.md')
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write('\n'.join(linhas) + '\n')
    print('\n'.join(linhas))
    print('\nFiguras em', os.path.join(pasta, 'graficos'))


if __name__ == '__main__':
    main()
