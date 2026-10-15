"""Registra o ranking da semana em historico_carteira.json (idempotente: refazer substitui a semana).

uso: python src/atualizar_historico.py <pasta_da_semana>
"""
import datetime
import hashlib
import json
import os

import carteira as c

DIRECAO = {'comprar': 'acima', 'evitar': 'abaixo', 'aguardar': 'neutra'}


def previsoes(ranking):
    """Previsões explícitas do ranking, para a avaliação marcar acerto por ação e por componente.

    `direcao_esperada` é o desempenho esperado contra o Ibovespa na janela do horizonte: acima
    (comprar), abaixo (evitar) ou neutra (aguardar). Derivado só de campos já gravados.
    """
    out = []
    for r in ranking:
        acao = r.get('acao_sugerida')
        if acao not in DIRECAO:
            continue
        out.append({'ticker': r['ticker'], 'tipo': 'acao_sugerida', 'valor': acao, 'direcao_esperada': DIRECAO[acao],
                    'referencia': '^BVSP', 'horizontes': ['1_semana', '4_semanas', '12_semanas'],
                    'certeza': r.get('certeza'), 'gatilho_revisao': r.get('gatilho_revisao')})
    return out

pasta = c.pasta_semana()
a, m, d = c.data_semana(pasta)
data = f'{a:04d}-{m:02d}-{d:02d}'
sint = c.ler(os.path.join(pasta, 'sintese.json'))
xp = c.ler(c.arquivo_xp(pasta))
alertas = c.ler(os.path.join(pasta, 'alertas.json'), {})
caminho = c.arquivo_historico(pasta) or os.path.join(os.path.dirname(pasta), 'historico_carteira.json')
hist = c.ler(caminho, {'semanas': []})

regras = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'regras.py')
with open(regras, 'rb') as f:
    sha = hashlib.sha256(f.read()).hexdigest()[:12]
precos = c.ler(os.path.join(pasta, 'precos.json'), {})
entrada = {
    'data': data,
    'versao_regras': sha,
    'pesos': sint.get('metodologia', {}).get('pesos'),
    'ibovespa': {'valor': precos.get('ibovespa', {}).get('preco_atual'), 'data': precos.get('ibovespa', {}).get('data_cotacao')},
    'pasta': os.path.basename(pasta),
    'pdf_xp': xp.get('fonte', ''),
    'ranking': [{k: r.get(k) for k in ('posicao', 'ticker', 'setor', 'nota', 'acao_sugerida', 'certeza', 'preco_atual', 'data_cotacao',
                         'upside_xp_pct', 'upside_mediana_pct', 'upside_ajustado_pct', 'componentes', 'n_casas', 'rating_xp')}
                | {'retorno_5d_pct': (r.get('retornos') or {}).get('5d_pct')}
                for r in sint['ranking']],
    'previsoes': previsoes(sint['ranking']),
    'conclusoes': sint.get('conclusoes_semana'),
    'alertas': [{k: a_.get(k) for k in ('ticker', 'nivel', 'fato', 'data')} for a_ in alertas.get('alertas', [])],
}
decisao = c.ler(os.path.join(pasta, 'decisao_sombra.json'), {})
if decisao.get('modo') == 'sombra':      # só o registro, para comparar depois; não afeta ranking nem avaliação
    entrada['decisao_sombra'] = {'ranking_confiavel': decisao.get('ranking_confiavel'),
                                 'acoes': {d['ticker']: {'acao': d.get('acao'), 'confianca': d.get('confianca')}
                                           for d in decisao.get('decisoes', []) if isinstance(d, dict) and d.get('ticker')}}
hist['semanas'] = [s for s in hist['semanas'] if s['data'] != data] + [entrada]
hist['semanas'].sort(key=lambda s: s['data'])
with open(caminho, 'w', encoding='utf-8') as f:
    json.dump(hist, f, ensure_ascii=False, indent=1)
print('histórico atualizado:', caminho, f'({len(hist["semanas"])} semanas)')


def arquivar_casas(pasta, data, ranking):
    """Guarda o retrato da semana (casas, alvos, ratings e nota) em aprendizado/historico_casas/AAAA-MM-DD.json.

    Serve para testar no futuro se revisões e mudanças de recomendação antecipam retorno: o que se sabia
    na data, antes do resultado. Não sobrescreve um retrato existente (reexecuções vão para _revN)."""
    casas = c.ler(os.path.join(pasta, 'casas.json'), {})
    if not casas.get('tickers'):
        return None
    destino = os.path.join(os.path.dirname(pasta), 'aprendizado', 'historico_casas')
    os.makedirs(destino, exist_ok=True)
    arq = os.path.join(destino, f'{data}.json')
    rev = 1
    while os.path.exists(arq):
        rev += 1
        arq = os.path.join(destino, f'{data}_rev{rev}.json')
    with open(arq, 'w', encoding='utf-8') as f:
        json.dump({'data': data, 'registrado_em': datetime.datetime.now().isoformat(timespec='seconds'),
                   'fonte': 'casas.json e sintese.json da semana, gravados antes do resultado',
                   'casas': casas['tickers'],
                   'ranking': [{k: r.get(k) for k in ('posicao', 'ticker', 'nota', 'acao_sugerida', 'certeza', 'preco_atual',
                                                      'data_cotacao', 'upside_xp_pct', 'upside_mediana_pct',
                                                      'upside_ajustado_pct', 'n_casas', 'rating_xp')} for r in ranking]},
                  f, ensure_ascii=False, indent=1)
    return arq


try:  # o arquivo é um extra: falhar aqui nunca pode derrubar o registro da semana
    _arq = arquivar_casas(pasta, data, sint['ranking'])
    if _arq:
        print('retrato das casas:', _arq)
except OSError as e:
    print('aviso: retrato das casas não gravado:', e)
