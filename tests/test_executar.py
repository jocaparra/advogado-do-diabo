import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
import executar as E  # noqa: E402


class TesteComplementos(unittest.TestCase):
    def _raiz(self, retrato=False, posicoes=None):
        d = tempfile.mkdtemp()
        if retrato:
            os.makedirs(os.path.join(d, 'aprendizado', 'quant'))
            open(os.path.join(d, 'aprendizado', 'quant', 'carteira_2026-01-01.json'), 'w').close()
        if posicoes:
            os.makedirs(os.path.join(d, 'entrada'))
            open(os.path.join(d, 'entrada', posicoes), 'w').close()
        return d

    def _chamadas(self, raiz, sem_rede=False, sem_notificar=False):
        with mock.patch.object(E, 'RAIZ', raiz), mock.patch.object(E, 'rodar') as r, contextlib.redirect_stdout(io.StringIO()):
            E.complementos(sem_rede, sem_notificar)
        return r.call_args_list

    def test_sem_rede_nao_roda_nada(self):
        self.assertEqual(self._chamadas(self._raiz(True, 'posicoes.csv'), sem_rede=True), [])

    def test_sem_retrato_nem_posicoes_pula_ambos(self):
        self.assertEqual(self._chamadas(self._raiz()), [])

    def test_roda_medicao_e_checagem_sem_interromper(self):
        raiz = self._raiz(True, 'posicoes.csv')
        c = self._chamadas(raiz, sem_notificar=True)
        self.assertEqual([x.args[0] for x in c], ['medir_quant.py', 'checagem_semanal.py'])
        self.assertTrue(all(x.kwargs['tolerar'] for x in c))
        self.assertEqual(c[1].kwargs['extras'], ['--csv', os.path.join(raiz, 'entrada', 'posicoes.csv'), '--sem-notificar'])

    def test_prefere_posicoes_pluggy(self):
        c = self._chamadas(self._raiz(False, 'posicoes_pluggy.csv'))
        self.assertTrue(c[0].kwargs['extras'][1].endswith('posicoes_pluggy.csv'))
        self.assertNotIn('--sem-notificar', c[0].kwargs['extras'])


if __name__ == '__main__':
    unittest.main()


class TesteColetarYahoo(unittest.TestCase):
    def test_extrai_campos_e_tolera_falha_por_ticker(self):
        import coletar_yahoo as Y
        info = {'AAA3.SA': {'currentPrice': 10.0, 'trailingPE': 8.0, 'priceToBook': 1.2, 'trailingAnnualDividendYield': 0.0512},
                'CCC3.SA': {}}

        def buscar(s):
            if s == 'BBB3.SA':
                raise RuntimeError('404')
            return info[s]
        d = Y.coletar(['AAA3', 'BBB3', 'CCC3'], buscar)
        self.assertEqual(d['acoes']['AAA3']['p_l'], 8.0)
        self.assertEqual(d['acoes']['AAA3']['dividend_yield_12m_pct'], 5.12)
        self.assertEqual(sorted(s['ticker'] for s in d['sem_dado']), ['BBB3', 'CCC3'])

    def test_tickers_vem_do_ranking_nao_das_chaves_da_sintese(self):
        import coletar_yahoo as Y
        with tempfile.TemporaryDirectory() as p:
            with open(os.path.join(p, 'sintese.json'), 'w') as f:
                f.write('{"data": "x", "agente": "y", "ranking": [{"ticker": "PETR4"}, {"ticker": "vale3"}]}')
            self.assertEqual(Y.tickers_da_semana(p), ['PETR4', 'VALE3'])
