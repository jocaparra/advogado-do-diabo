"""Checagem semanal da carteira: busca cotações e avisa só se houver sinal de venda.

uso: python src/checagem_semanal.py [--csv entrada/posicoes_pluggy.csv] [--sem-notificar]

Sinais de venda (geram notificação do macOS):
  - queda de 8% ou mais nos últimos 5 pregões
  - preço 15% ou mais abaixo da máxima dos últimos 60 pregões
  - classificação "evitar" na última semana do ranking
  - prejuízo de 10% ou mais sobre o seu preço médio (coluna preco_medio do CSV)
Em observação (só aparecem no relatório): upside negativo nas duas referências.

Limite: a nota e o upside vêm do último ranking publicado (historico_carteira.json). Notícias e
casas de análise só mudam quando você rodar a coleta semanal completa; aqui só o preço é novo.
Grava o relatório em checagem/ultima.md. Não é recomendação de investimento.
"""
import csv
import datetime as dt
import json
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'src'))
import precos_yahoo as Y  # noqa: E402

QUEDA_SEMANA_PCT = 8.0
QUEDA_TOPO_PCT = 15.0
PERDA_CUSTO_PCT = 10.0
JANELA_TOPO = 60


def _num(txt):
    try:
        return float(str(txt).strip().replace('.', '').replace(',', '.')) if str(txt).strip() else None
    except ValueError:
        return None


def ler_tickers(caminho):
    with open(caminho, encoding='utf-8') as f:
        return [(l['ticker'].strip().upper(), _num(l.get('preco_medio')))
                for l in csv.DictReader(f, delimiter=';') if l.get('ticker', '').strip()]


def ultimo_ranking():
    with open(os.path.join(RAIZ, 'historico_carteira.json'), encoding='utf-8') as f:
        s = json.load(f)['semanas'][-1]
    return s['data'], {r['ticker']: r for r in s['ranking']}


def avaliar(ticker, item, rank, pm=None):
    serie = item['serie']
    ult = serie[-1][1]
    ret5 = (ult / serie[-6][1] - 1) * 100 if len(serie) >= 6 else 0.0
    topo = max(p for _, p in serie[-JANELA_TOPO:])
    do_topo = (ult / topo - 1) * 100
    venda, obs = [], []
    if ret5 <= -QUEDA_SEMANA_PCT:
        venda.append(f'caiu {ret5:.1f}% em 5 pregões')
    if do_topo <= -QUEDA_TOPO_PCT:
        venda.append(f'{do_topo:.1f}% abaixo da máxima de {JANELA_TOPO} pregões')
    sobre_custo = (ult / pm - 1) * 100 if pm else None
    if sobre_custo is not None and sobre_custo <= -PERDA_CUSTO_PCT:
        venda.append(f'{sobre_custo:.1f}% sobre o seu preço médio (R$ {pm:.2f})')
    if rank:
        if rank.get('acao_sugerida') == 'evitar':
            venda.append('ranking classifica como "evitar"')
        aj, xp = rank.get('upside_ajustado_pct'), rank.get('upside_xp_pct')
        if aj is not None and xp is not None and aj < 0 and xp < 0:
            obs.append(f'upside negativo nas duas referências ({aj:+.1f}% ajustado, {xp:+.1f}% XP)')
    return {'ticker': ticker, 'preco': ult, 'data': serie[-1][0], 'ret5': ret5, 'do_topo': do_topo,
            'venda': venda, 'obs': obs, 'custo': sobre_custo, 'nota': rank.get('nota') if rank else None}


def notificar(titulo, texto):
    texto, titulo = texto.replace('"', "'"), titulo.replace('"', "'")
    subprocess.run(['osascript', '-e', f'display notification "{texto}" with title "{titulo}"'], check=False)


def main():
    args = sys.argv[1:]
    csv_path = os.path.join(RAIZ, 'entrada', 'posicoes_pluggy.csv')
    if '--csv' in args:
        csv_path = args[args.index('--csv') + 1]
    posicoes = ler_tickers(csv_path)
    data_rank, ranking = ultimo_ranking()
    dados = Y.coletar([t for t, _ in posicoes])
    linhas = [avaliar(t, dados['acoes'][t], ranking.get(t), pm) for t, pm in posicoes if t in dados['acoes']]
    sem_dado = [s['ticker'] for s in dados['sem_dado']]

    hoje = dt.datetime.now().strftime('%d/%m/%Y %H:%M')
    out = [f'# Checagem semanal da carteira ({hoje})', '',
           f'Ranking de referência: {data_rank}. Só o preço é novo; notícias e casas não foram recoletadas.', '',
           '| Ticker | Preço | 5 pregões | vs máxima 60d | vs seu custo | Nota | Situação |', '|---|---:|---:|---:|---:|---:|---|']
    alertas = []
    for l in linhas:
        if l['venda']:
            sit = 'SINAL DE VENDA: ' + '; '.join(l['venda'])
            alertas.append(f"{l['ticker']}: " + '; '.join(l['venda']))
        elif l['obs']:
            sit = 'em observação: ' + '; '.join(l['obs'])
        else:
            sit = 'ok'
        nota = '-' if l['nota'] is None else f"{l['nota']:.2f}".replace('.', ',')
        out.append(f"| {l['ticker']} | R$ {l['preco']:.2f} | {l['ret5']:+.1f}% | {l['do_topo']:+.1f}% | {'-' if l['custo'] is None else format(l['custo'], '+.1f') + '%'} | {nota} | {sit} |")
    if sem_dado:
        out += ['', 'Sem cotação: ' + ', '.join(sem_dado)]
    out += ['', 'Não é recomendação de investimento.']

    pasta = os.path.join(RAIZ, 'checagem')
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, 'ultima.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')
    print('\n'.join(out))
    if alertas and '--sem-notificar' not in args:
        notificar('Carteira: sinal de venda', ' | '.join(alertas)[:230])


if __name__ == '__main__':
    main()
