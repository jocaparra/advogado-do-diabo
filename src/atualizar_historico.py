"""Registra o ranking da semana em historico_carteira.json (idempotente: refazer substitui a semana).

uso: python src/atualizar_historico.py <pasta_da_semana>
"""
import hashlib
import json
import os

import carteira as c

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
                         'upside_xp_pct', 'upside_mediana_pct', 'upside_ajustado_pct')}
                for r in sint['ranking']],
    'alertas': [{k: a_.get(k) for k in ('ticker', 'nivel', 'fato', 'data')} for a_ in alertas.get('alertas', [])],
}
hist['semanas'] = [s for s in hist['semanas'] if s['data'] != data] + [entrada]
hist['semanas'].sort(key=lambda s: s['data'])
with open(caminho, 'w', encoding='utf-8') as f:
    json.dump(hist, f, ensure_ascii=False, indent=1)
print('histórico atualizado:', caminho, f'({len(hist["semanas"])} semanas)')
