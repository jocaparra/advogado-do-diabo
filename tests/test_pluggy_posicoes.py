"""Testes offline da conversão de investimentos da Pluggy em posições (sem rede)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import minha_carteira as M  # noqa: E402
import pluggy_posicoes as P  # noqa: E402

INVS = [
    {'type': 'EQUITY', 'code': 'PRIO3', 'name': 'PRIO ON', 'quantity': 100, 'value': 60.0},
    {'type': 'EQUITY', 'code': 'PRIO3', 'name': 'PRIO ON', 'quantity': 50, 'value': 63.0},       # outra corretora
    {'type': 'EQUITY', 'code': 'ITUB4F', 'name': 'ITAUUNIBANCO PN', 'quantity': 7},
    {'type': 'ETF', 'code': 'BOVA11', 'name': 'ISHARES BOVA', 'quantity': 3},
    {'type': 'FIXED_INCOME', 'code': None, 'name': 'CDB Banco X', 'quantity': 1},
    {'type': 'EQUITY', 'code': 'Tesouro', 'name': 'algo', 'quantity': 1},
    {'type': 'EQUITY', 'code': 'VALE3', 'name': 'VALE ON', 'quantity': 0},
]


class TestePluggy(unittest.TestCase):
    def test_extrai_soma_e_lista_ignorados(self):
        pos, ign = P.extrair_acoes(INVS)
        self.assertEqual(pos, [{'ticker': 'BOVA11', 'quantidade': 3.0, 'preco_atual': None},
                               {'ticker': 'ITUB4', 'quantidade': 7.0, 'preco_atual': None},
                               {'ticker': 'PRIO3', 'quantidade': 150.0, 'preco_atual': 61.0}])
        self.assertEqual(len(ign), 3)

    def test_csv_gerado_e_lido_pelo_cruzamento(self):
        pos, _ = P.extrair_acoes(INVS)
        lidas = M.ler_posicoes(P.csv_texto(pos))
        self.assertEqual({p['ticker']: p['quantidade'] for p in lidas},
                         {'BOVA11': 3.0, 'ITUB4': 7.0, 'PRIO3': 150.0})
        self.assertEqual({p['ticker']: p['preco_atual'] for p in lidas}['PRIO3'], 61.0)


class TesteLerJson(unittest.TestCase):
    def test_resposta_paginada_com_custo(self):
        import json
        import pluggy_posicoes as P
        doc = {'total': 3, 'results': [
            {'type': 'EQUITY', 'code': 'PETR4', 'quantity': 10, 'value': 40.0, 'amountOriginal': 300.0},
            {'type': 'EQUITY', 'code': 'PETR4F', 'quantity': 5, 'value': 40.0, 'amountOriginal': 200.0},
            {'type': 'EQUITY', 'code': 'VALE3', 'quantity': 2, 'value': 60.0},
            {'type': 'FIXED_INCOME', 'code': 'CDB', 'quantity': 1}]}
        pos, ign = P.ler_json(json.dumps(doc))
        d = {p['ticker']: p for p in pos}
        self.assertAlmostEqual(d['PETR4']['quantidade'], 15)
        self.assertAlmostEqual(d['PETR4']['preco_medio'], 500 / 15, places=3)   # custo total / quantidade
        self.assertIsNone(d['VALE3'].get('preco_medio'))                            # sem amountOriginal: não inventa
        self.assertEqual(len(ign), 1)
        self.assertIn('15', P.csv_texto(pos))

    def test_lista_de_respostas_e_lote_sem_custo(self):
        import json
        import pluggy_posicoes as P
        a = {'results': [{'type': 'EQUITY', 'code': 'ITUB4', 'quantity': 4, 'value': 50.0, 'amountOriginal': 160.0}]}
        b = {'results': [{'type': 'EQUITY', 'code': 'ITUB4', 'quantity': 6, 'value': 50.0}]}
        pos, _ = P.ler_json(json.dumps([a, b]))
        self.assertEqual(pos[0]['quantidade'], 10)
        self.assertIsNone(pos[0].get('preco_medio'))    # um lote sem custo invalida o preço médio do ticker

    def test_json_invalido_ou_sem_investimentos(self):
        import pluggy_posicoes as P
        for txt in ('{nao e json', '{"results": []}', '{"foo": 1}'):
            with self.assertRaises(P.PluggyErro):
                P.ler_json(txt)


if __name__ == '__main__':
    unittest.main()
