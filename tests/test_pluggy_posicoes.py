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


class TestePrecoMedioTransacoes(unittest.TestCase):
    def compra(self, q, v, data, **kw):
        return dict({'type': 'BUY', 'quantity': q, 'value': v, 'tradeDate': data}, **kw)

    def test_compras_ponderadas_por_quantidade(self):
        import pluggy_posicoes as P
        t = [self.compra(2, 10.0, '2026-01-02'), self.compra(8, 20.0, '2026-02-02')]
        self.assertAlmostEqual(P.preco_medio_transacoes(t, 10), 18.0)

    def test_despesas_entram_no_custo(self):
        import pluggy_posicoes as P
        self.assertAlmostEqual(P.preco_medio_transacoes([self.compra(10, 10.0, '2026-01-02', expenses=5)], 10), 10.5)

    def test_venda_mantem_preco_medio(self):
        import pluggy_posicoes as P
        t = [self.compra(10, 10.0, '2026-01-02'), {'type': 'SELL', 'quantity': 4, 'value': 30.0, 'tradeDate': '2026-03-01'},
             self.compra(4, 20.0, '2026-04-01')]      # fora de ordem na lista: a data decide
        self.assertAlmostEqual(P.preco_medio_transacoes(list(reversed(t)), 10), (6 * 10 + 4 * 20) / 10)

    def test_historico_que_nao_fecha_nao_inventa(self):
        import pluggy_posicoes as P
        c = self.compra(5, 10.0, '2026-01-02')
        self.assertIsNone(P.preco_medio_transacoes([c], 8))                                   # posição maior que as compras
        self.assertIsNone(P.preco_medio_transacoes([c, {'type': 'SELL', 'quantity': 9, 'value': 1, 'tradeDate': '2026-02-01'}], 5))
        self.assertIsNone(P.preco_medio_transacoes([dict(c, type='TRANSFER')], 5))             # tipo desconhecido
        self.assertIsNone(P.preco_medio_transacoes([dict(c, value=None)], 5))
        self.assertIsNone(P.preco_medio_transacoes([], 5))

    def test_extrair_acoes_prioriza_transacoes_sobre_amount_original(self):
        import pluggy_posicoes as P
        invs = [{'id': 'a', 'type': 'EQUITY', 'code': 'PETR4', 'quantity': 10, 'value': 40.0, 'amountOriginal': 999.0},
                {'id': 'b', 'type': 'EQUITY', 'code': 'VALE3', 'quantity': 2, 'value': 60.0, 'amountOriginal': 100.0},
                {'id': 'c', 'type': 'EQUITY', 'code': 'ITUB4', 'quantity': 2, 'value': 30.0}]
        trans = {'a': [self.compra(10, 30.0, '2026-01-02')],
                 'b': [self.compra(1, 30.0, '2026-01-02')]}      # não fecha com 2: cai no amountOriginal
        pos, _ = P.extrair_acoes(invs, trans)
        d = {p['ticker']: p for p in pos}
        self.assertAlmostEqual(d['PETR4']['preco_medio'], 30.0)
        self.assertAlmostEqual(d['VALE3']['preco_medio'], 50.0)
        self.assertNotIn('preco_medio', d['ITUB4'])               # sem transações nem custo

    def test_lotes_PETR4_e_PETR4F_somam_transacoes(self):
        import pluggy_posicoes as P
        invs = [{'id': 'a', 'type': 'EQUITY', 'code': 'PETR4', 'quantity': 10, 'value': 40.0},
                {'id': 'b', 'type': 'EQUITY', 'code': 'PETR4F', 'quantity': 5, 'value': 40.0}]
        pos, _ = P.extrair_acoes(invs, {'a': [self.compra(10, 30.0, '2026-01-02')], 'b': [self.compra(5, 36.0, '2026-02-02')]})
        self.assertAlmostEqual(pos[0]['preco_medio'], (300 + 180) / 15)
        pos, _ = P.extrair_acoes(invs, {'a': [self.compra(10, 30.0, '2026-01-02')]})      # um lote sem transações
        self.assertNotIn('preco_medio', pos[0])

    def test_baixar_busca_transacoes_e_tolera_falha(self):
        from unittest import mock
        import pluggy_posicoes as P

        def falso(metodo, caminho, chave=None, corpo=None, consulta=None):
            if caminho == '/auth':
                return {'apiKey': 'k'}
            if caminho == '/investments':
                return {'results': [{'id': 'a', 'type': 'EQUITY', 'code': 'PETR4', 'quantity': 10, 'value': 40.0},
                                    {'id': 'b', 'type': 'EQUITY', 'code': 'VALE3', 'quantity': 2, 'value': 60.0},
                                    {'id': 'z', 'type': 'EQUITY', 'code': 'BPAC11', 'quantity': 0}], 'totalPages': 1}
            if caminho == '/investments/a/transactions':
                return {'results': [self.compra(10, 30.0, '2026-01-02')], 'totalPages': 1}
            raise P.PluggyErro('falhou')
        with mock.patch.object(P, '_chamar', side_effect=falso) as m:
            pos, _ = P.baixar('i', 's', ['item'])
        d = {p['ticker']: p for p in pos}
        self.assertAlmostEqual(d['PETR4']['preco_medio'], 30.0)
        self.assertNotIn('preco_medio', d['VALE3'])                # falha nas transações não derruba a leitura
        self.assertNotIn('/investments/z/transactions', [c.args[1] for c in m.call_args_list])   # posição zerada não consulta


if __name__ == '__main__':
    unittest.main()
