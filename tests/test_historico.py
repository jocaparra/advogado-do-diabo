"""Testes do registro de componentes e previsões no histórico (offline)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ, 'src', 'atualizar_historico.py')


def r(ticker, acao, **kw):
    return {'posicao': 1, 'ticker': ticker, 'setor': 'X', 'nota': 5.0, 'acao_sugerida': acao, 'certeza': 'baixa',
            'preco_atual': 10.0, 'data_cotacao': '2026-10-05', 'componentes': {'momentum': 6}, 'gatilho_revisao': 'g', 'retornos': {'5d_pct': 4.09}, **kw}


class TestePrevisoes(unittest.TestCase):
    def test_gravacao_end_to_end(self):
        with tempfile.TemporaryDirectory() as raiz:
            pasta = os.path.join(raiz, 'semana_20261005')
            os.makedirs(pasta)
            with open(os.path.join(pasta, 'sintese.json'), 'w', encoding='utf-8') as f:
                json.dump({'metodologia': {'pesos': {'momentum': 1}}, 'conclusoes_semana': ['c'],
                           'ranking': [r('AAA3', 'comprar'), r('BBB3', 'evitar'), r('CCC3', 'aguardar'), r('DDD3', 'outra')]}, f)
            with open(os.path.join(pasta, 'xp.json'), 'w', encoding='utf-8') as f:
                json.dump({'fonte': 'teste'}, f)
            p = subprocess.run([sys.executable, SCRIPT, pasta], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            with open(os.path.join(raiz, 'historico_carteira.json'), encoding='utf-8') as f:
                s = json.load(f)['semanas'][0]
            self.assertEqual(s['ranking'][0]['componentes'], {'momentum': 6})
            dirs = {x['ticker']: x['direcao_esperada'] for x in s['previsoes']}
            self.assertEqual(dirs, {'AAA3': 'acima', 'BBB3': 'abaixo', 'CCC3': 'neutra'})
            self.assertEqual(s['ranking'][0]['retorno_5d_pct'], 4.09)
            self.assertEqual(s['conclusoes'], ['c'])

    def test_arquivo_das_casas_nao_sobrescreve(self):
        with tempfile.TemporaryDirectory() as raiz:
            pasta = os.path.join(raiz, 'semana_20261005')
            os.makedirs(pasta)
            with open(os.path.join(pasta, 'sintese.json'), 'w', encoding='utf-8') as f:
                json.dump({'ranking': [r('AAA3', 'comprar')]}, f)
            with open(os.path.join(pasta, 'xp.json'), 'w', encoding='utf-8') as f:
                json.dump({'fonte': 'teste'}, f)
            with open(os.path.join(pasta, 'casas.json'), 'w', encoding='utf-8') as f:
                json.dump({'tickers': {'AAA3': {'casas': [{'casa': 'X', 'preco_alvo': 12.0}]}}}, f)
            for _ in range(2):
                p = subprocess.run([sys.executable, SCRIPT, pasta], capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
            pasta_h = os.path.join(raiz, 'aprendizado', 'historico_casas')
            self.assertEqual(sorted(os.listdir(pasta_h)), ['2026-10-05.json', '2026-10-05_rev2.json'])
            with open(os.path.join(pasta_h, '2026-10-05.json'), encoding='utf-8') as f:
                self.assertEqual(json.load(f)['casas']['AAA3']['casas'][0]['preco_alvo'], 12.0)


if __name__ == '__main__':
    unittest.main()
