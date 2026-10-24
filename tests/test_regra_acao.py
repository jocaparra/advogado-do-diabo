"""A regra de ação do analista fica no prompt do agente: este teste impede que ela mude sem registro."""
import math
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'src'))

import regras as R  # noqa: E402

with open(os.path.join(RAIZ, '.claude', 'agents', 'analista.md'), encoding='utf-8') as f:
    ANALISTA = f.read()


class TesteRegraAcao(unittest.TestCase):
    def test_proporcao_de_comprar_e_declarada(self):
        self.assertIn('40% superiores', ANALISTA)
        self.assertIn('6 de 14', ANALISTA)
        self.assertEqual(math.ceil(0.4 * 14), 6)          # a conta do prompt confere

    def test_mudanca_registrada_como_nao_validada(self):
        self.assertIn('NÃO foi validada', ANALISTA)
        self.assertIn('definida pelo usuário', ANALISTA)

    def test_excecoes_continuam_valendo(self):
        for exc in ('alerta vermelho', 'upside ajustado negativo', 'dado insuficiente'):
            self.assertIn(exc, ANALISTA)

    def test_corte_de_nota_sem_comprar(self):
        ranking = [{'nota': 5.0, 'acao_sugerida': 'aguardar'}]
        self.assertIsNone(R.corte_de_compra(ranking))

    def test_corte_de_nota_entre_comprar_e_resto(self):
        ranking = [{'nota': 6.0, 'acao_sugerida': 'comprar'}, {'nota': 5.0, 'acao_sugerida': 'comprar'},
                   {'nota': 4.0, 'acao_sugerida': 'aguardar'}]
        self.assertEqual(R.corte_de_compra(ranking), 4.5)


if __name__ == '__main__':
    unittest.main()
