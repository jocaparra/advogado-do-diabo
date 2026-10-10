"""Testes da avaliação das recomendações contra o Ibovespa (offline, séries sintéticas)."""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import avaliar as A  # noqa: E402


def serie(inicio, dias, valor0, passo):
    d0 = dt.date.fromisoformat(inicio)
    return [[(d0 + dt.timedelta(days=i)).isoformat(), round(valor0 * (1 + passo) ** i, 6)] for i in range(dias)]


class TesteSpearman(unittest.TestCase):
    def test_monotono(self):
        self.assertAlmostEqual(A.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(A.spearman([1, 2, 3, 4], [40, 30, 20, 10]), -1.0)

    def test_empates_e_amostra_curta(self):
        self.assertIsNone(A.spearman([1, 2], [1, 2]))
        self.assertIsNone(A.spearman([1, 1, 1], [1, 2, 3]))


class TesteAvaliacao(unittest.TestCase):
    def monta(self, tmp, hoje_dias=200):
        # Ibovespa sobe 0,1% ao dia; AAA sobe 0,3% ao dia; BBB cai 0,1% ao dia
        s = {'^BVSP': serie('2026-01-01', hoje_dias, 100000, 0.001), 'AAA3': serie('2026-01-01', hoje_dias, 10, 0.003),
             'BBB3': serie('2026-01-01', hoje_dias, 10, -0.001)}
        pasta = os.path.join(tmp, 'semana_20260601')
        os.makedirs(pasta)
        with open(os.path.join(pasta, 'precos.json'), 'w') as f:
            json.dump({'ibovespa': {'serie': s['^BVSP']}, 'acoes': {t: {'serie': s[t]} for t in ('AAA3', 'BBB3')}}, f)
        d0 = '2026-02-01'
        px = {t: dict(serie_) for t, serie_ in ((k, s[k]) for k in s)}
        sem = {'data': d0, 'ranking': [
            {'posicao': 1, 'ticker': 'AAA3', 'nota': 7, 'acao_sugerida': 'comprar', 'certeza': 'alta', 'preco_atual': px['AAA3'][d0], 'data_cotacao': d0},
            {'posicao': 2, 'ticker': 'BBB3', 'nota': 3, 'acao_sugerida': 'evitar', 'certeza': 'média', 'preco_atual': px['BBB3'][d0], 'data_cotacao': d0}]}
        with open(os.path.join(tmp, 'historico_carteira.json'), 'w') as f:
            json.dump({'semanas': [sem]}, f)

    def test_excesso_e_agregacao(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.monta(tmp)
            r = A.avaliar(tmp, hoje=dt.date(2026, 7, 1))
            h4 = r['horizontes']['4_semanas']
            self.assertEqual(h4['observacoes'], 2)
            comprar = h4['por_acao']['comprar']
            evitar = h4['por_acao']['evitar']
            esperado_a = ((1.003 ** 28) - (1.001 ** 28)) * 100
            self.assertAlmostEqual(comprar['excesso_medio_pp'], esperado_a, delta=0.05)
            self.assertLess(evitar['excesso_medio_pp'], 0)
            self.assertGreater(h4['spread_comprar_menos_evitar_pp'], 0)
            self.assertEqual(h4['amostra'], 'insuficiente')  # 2 observações: sem conclusão

    def test_horizonte_nao_vencido_fica_pendente(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.monta(tmp)
            r = A.avaliar(tmp, hoje=dt.date(2026, 2, 20))  # 19 dias depois
            self.assertEqual(r['horizontes']['4_semanas']['observacoes'], 0)
            self.assertEqual(r['horizontes']['4_semanas']['pendentes'], 2)

    def test_sem_futuro_nos_precos_nao_inventa(self):
        # hoje é depois do horizonte, mas a série termina antes: continua pendente
        with tempfile.TemporaryDirectory() as tmp:
            self.monta(tmp, hoje_dias=40)  # série vai até 2026-02-09
            r = A.avaliar(tmp, hoje=dt.date(2026, 7, 1))
            self.assertEqual(r['horizontes']['4_semanas']['observacoes'], 0)
            self.assertEqual(r['horizontes']['4_semanas']['pendentes'], 2)

    def test_desdobramento_posterior_nao_gera_retorno_falso(self):
        # preço gravado era nominal da época (100); a série atual está ajustada por split 5:1 (20 em todo o período)
        ibov = {(dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat(): 100000.0 for i in range(120)}
        acao = {k: 20.0 for k in ibov}
        sem = {'data': '2026-02-02', 'ranking': [{'posicao': 1, 'ticker': 'XXXX3', 'nota': 7, 'acao_sugerida': 'comprar',
                                                  'certeza': 'alta', 'preco_atual': 100.0, 'data_cotacao': '2026-02-02'}]}
        obs, _ = A.avaliar_entradas([sem], {'XXXX3': acao, '^BVSP': ibov}, dt.date(2026, 6, 1))
        self.assertAlmostEqual(obs['4_semanas'][0]['retorno_pct'], 0.0, places=6)


if __name__ == '__main__':
    unittest.main()
