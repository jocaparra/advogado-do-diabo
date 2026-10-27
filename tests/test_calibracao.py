"""Testes da calibração (offline, valores conhecidos)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import calibracao as K  # noqa: E402


class TesteMetricasProbabilisticas(unittest.TestCase):
    def test_brier_de_valores_conhecidos(self):
        self.assertEqual(K.brier([1.0, 0.0], [1, 0]), 0.0)
        self.assertAlmostEqual(K.brier([0.5, 0.5], [1, 0]), 0.25)
        self.assertAlmostEqual(K.brier([0.8, 0.2], [0, 1]), 0.64)

    def test_log_loss_e_apara_zero_e_um(self):
        self.assertAlmostEqual(K.log_loss([0.5, 0.5], [1, 0]), 0.693147, places=5)
        self.assertTrue(K.log_loss([0.0], [1]) < 40)            # não explode em infinito

    def test_entradas_vazias_ou_desalinhadas_devolvem_none(self):
        self.assertIsNone(K.brier([], []))
        self.assertIsNone(K.brier([0.5], [1, 0]))
        self.assertIsNone(K.log_loss([], []))

    def test_curva_perfeita_tem_previsto_igual_a_observado(self):
        p = [0.1] * 10 + [0.9] * 10
        y = [0] * 9 + [1] + [1] * 9 + [0]
        c = K.curva(p, y, faixas=5)
        self.assertEqual([x['n'] for x in c], [10, 10])
        self.assertAlmostEqual(c[0]['observado'], 0.1)
        self.assertAlmostEqual(c[1]['observado'], 0.9)

    def test_probabilidade_um_cai_na_ultima_faixa(self):
        self.assertEqual(K.curva([1.0], [1], faixas=4)[0]['faixa'], [0.75, 1.0])

    def test_wilson(self):
        self.assertIsNone(K.wilson(0, 0))
        lo, hi = K.wilson(5, 10)
        self.assertTrue(lo < 50 < hi)
        lo2, hi2 = K.wilson(500, 1000)
        self.assertLess(hi2 - lo2, hi - lo)                      # mais amostra, intervalo mais estreito
        self.assertEqual(K.wilson(0, 5)[0], 0.0)


class TesteGrupos(unittest.TestCase):
    def obs(self, certeza, excesso, veredito, semana='s1'):
        return {'certeza': certeza, 'excesso_pp': excesso, 'veredito': veredito, 'semana': semana}

    def test_frequencia_por_nivel_e_portao_de_amostra(self):
        o = [self.obs('alta', 5, 'acerto', 's1'), self.obs('alta', -2, 'erro', 's2'), self.obs('baixa', 1, 'neutro_confirmado')]
        r = K.por_grupo(o, 'certeza', min_obs=30, min_semanas=8)
        self.assertEqual(r['alta']['n'], 2)
        self.assertEqual(r['alta']['acima_ibov_pct'], 50.0)
        self.assertEqual(r['alta']['acerto_direcional_pct'], 50.0)
        self.assertEqual(r['alta']['semanas'], 2)
        self.assertEqual(r['alta']['amostra'], 'insuficiente')
        self.assertIsNone(r['baixa']['acerto_direcional_pct'])   # só neutro: sem previsão direcional
        self.assertEqual(r['baixa']['direcionais'], 0)

    def test_amostra_suficiente_exige_observacoes_e_semanas(self):
        muitas_mesma_semana = [self.obs('alta', 1, 'acerto', 's1') for _ in range(40)]
        self.assertEqual(K.por_grupo(muitas_mesma_semana, 'certeza', 30, 8)['alta']['amostra'], 'insuficiente')
        espalhadas = [self.obs('alta', 1, 'acerto', f's{i % 10}') for i in range(40)]
        self.assertEqual(K.por_grupo(espalhadas, 'certeza', 30, 8)['alta']['amostra'], 'suficiente')

    def test_certeza_ausente_vira_nao_informada(self):
        r = K.por_grupo([{'excesso_pp': 1, 'veredito': 'acerto', 'semana': 's'}], 'certeza', 30, 8)
        self.assertIn('não informada', r)


if __name__ == '__main__':
    unittest.main()
