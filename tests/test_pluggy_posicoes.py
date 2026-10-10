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


if __name__ == '__main__':
    unittest.main()
