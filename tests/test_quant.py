"""Testes offline da estratégia quantitativa: point-in-time, fatores, proventos na avaliação e carteira."""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import avaliar as A  # noqa: E402
import fatores_quant as F  # noqa: E402
import quant_dados as Q  # noqa: E402


def reg(refer, receb, tipo, ni, ni_ant, pl, acoes=1000.0):
    return {'cnpj': 'x', 'dt_refer': refer, 'dt_receb': receb, 'tipo': tipo, 'ni_ytd': ni, 'ni_ytd_ant': ni_ant,
            'pl': pl, 'acoes': acoes}


class TestePointInTime(unittest.TestCase):
    def setUp(self):
        self.r = [reg('2023-12-31', '2024-03-01', 'DFP', 100.0, 80.0, 500.0),
                  reg('2024-03-31', '2024-05-10', 'ITR', 30.0, 20.0, 520.0),
                  reg('2024-06-30', '2024-08-08', 'ITR', 70.0, 45.0, 540.0)]

    def test_nao_ve_o_futuro(self):
        self.assertIsNone(Q.estado_em(self.r, '2024-02-28'))
        # em 15/04 só o anual de 2023 é conhecido
        self.assertEqual(Q.estado_em(self.r, '2024-04-15')['ni_ttm'], 100.0)

    def test_ttm_de_trimestre(self):
        # 12m em jun/24 = anual 2023 + acumulado 2024 - acumulado 2023 = 100 + 70 - 45
        self.assertEqual(Q.estado_em(self.r, '2024-09-01')['ni_ttm'], 125.0)
        self.assertEqual(Q.estado_em(self.r, '2024-09-01')['pl'], 540.0)

    def test_sem_anual_anterior_nao_inventa(self):
        self.assertIsNone(Q.estado_em(self.r[1:], '2024-09-01')['ni_ttm'])


class TesteFatores(unittest.TestCase):
    def test_postos_com_empate(self):
        p = F._postos({'a': 1, 'b': 2, 'c': 2, 'd': 9})
        self.assertAlmostEqual(p['a'], 0.125)
        self.assertAlmostEqual(p['b'], p['c'])
        self.assertGreater(p['d'], p['b'])

    def test_composto_exige_tres_fatores(self):
        fat = {f'c{i}': {'valor_ep': i / 10, 'momentum': i / 5, 'vol': 0.02 - i / 1000} for i in range(10)}
        sc = F.pontuar(fat)
        self.assertEqual(len(sc), 10)  # valor, momentum e baixa_vol bastam
        self.assertGreater(sc['c9']['composto'], sc['c0']['composto'])
        fat['c0'] = {'momentum': 0.1}
        self.assertNotIn('c0', F.pontuar(fat))

    def test_pesos_zero_ignoram_fator(self):
        fat = {f'c{i}': {'valor_ep': i, 'momentum': -i, 'vol': 0.01 + i / 1000} for i in range(10)}
        so_valor = F.pontuar(fat, {'valor': 1, 'qualidade': 0, 'momentum': 0, 'dividendos': 0, 'baixa_vol': 0})
        self.assertGreater(so_valor['c9']['composto'], so_valor['c0']['composto'])


class TesteProventos(unittest.TestCase):
    def test_soma_apenas_a_janela(self):
        divs = {'AAA3': {'2026-01-10': 1.0, '2026-02-10': 0.5, '2026-03-10': 2.0}}
        d0, d1 = dt.date(2026, 1, 10), dt.date(2026, 3, 9)
        self.assertEqual(A.proventos(divs, 'AAA3', d0, d1), 0.5)  # exclui a data inicial e o que vem depois
        self.assertEqual(A.proventos(None, 'AAA3', d0, d1), 0.0)

    def test_retorno_total_soma_proventos(self):
        hist = [{'data': '2026-01-05', 'ranking': [{'posicao': 1, 'ticker': 'AAA3', 'nota': 5, 'acao_sugerida': 'comprar',
                                                   'preco_atual': 100.0, 'data_cotacao': '2026-01-05'}]}]
        d0 = dt.date(2026, 1, 5)
        dias = [(d0 + dt.timedelta(days=i)).isoformat() for i in range(40)]
        series = {'AAA3': {d: 100.0 for d in dias}, '^BVSP': {d: 1000.0 for d in dias}}
        obs, _ = A.avaliar_entradas(hist, series, dt.date(2026, 2, 20), {'AAA3': {'2026-01-20': 3.0}})
        o = obs['4_semanas'][0]
        self.assertAlmostEqual(o['retorno_pct'], 3.0)
        self.assertAlmostEqual(o['proventos_pct'], 3.0)
        self.assertAlmostEqual(o['excesso_pp'], 3.0)


if __name__ == '__main__':
    unittest.main()


class TesteCarteira(unittest.TestCase):
    def test_teto_por_setor(self):
        import carteira_quant as CQ
        ranking = [(f'c{i}', 1 - i / 10) for i in range(8)]
        setores = {'c0': 'A', 'c1': 'A', 'c2': 'A', 'c3': 'A', 'c4': 'B', 'c5': 'B', 'c6': 'C', 'c7': 'C'}
        topo = CQ.escolher(ranking, setores, 5, 2)
        self.assertEqual(topo, ['c0', 'c1', 'c4', 'c5', 'c6'])  # no máximo 2 por setor

    def test_reponderar_mistura_70_30(self):
        import carteira_quant as CQ
        semana = {'ranking': [{'ticker': 'AAA3', 'posicao': 1, 'nota': 6.0,
                               'componentes': {'catalisadores': 5, 'noticias': 5, 'macro_eleicao': 5}},
                              {'ticker': 'BBB3', 'posicao': 2, 'nota': 5.0,
                               'componentes': {'catalisadores': 5, 'noticias': 5, 'macro_eleicao': 5}}]}
        r = CQ.reponderar(semana, {'AAA3': 2.0, 'BBB3': 9.0},
                          {'quantitativa': 0.7, 'qualitativa': 0.3}, {'catalisadores': 0.25, 'noticias': 0.2, 'macro_eleicao': 0.2})
        nova = {x['ticker']: x for x in r}
        self.assertAlmostEqual(nova['BBB3']['nota_nova'], 0.7 * 9 + 0.3 * 5)
        self.assertEqual(nova['BBB3']['posicao_nova'], 1)
        self.assertEqual(nova['AAA3']['posicao_nova'], 2)

    def test_medicao_so_vence_com_dado(self):
        import medir_quant as M
        datas = [(dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat() for i in range(400)]
        s = {'datas': datas, 'adj': [10 + i * 0.01 for i in range(400)], 'close': [100 + i for i in range(400)]}
        retrato = {'data': '2026-01-01', 'carteira': [{'ticker': 'AAA3'}]}
        hoje = dt.date(2027, 1, 1)
        m = M.medir_retrato(retrato, 91, {'AAA3': s}, s, {}, 0.0, hoje)
        self.assertAlmostEqual(m['carteira_pct'], round(100 * (10 + 91 * 0.01) / 10 - 100, 2), places=1)
        self.assertIsNone(M.medir_retrato(retrato, 365, {'AAA3': s}, s, {}, 0.0, dt.date(2026, 6, 1)))  # não venceu
