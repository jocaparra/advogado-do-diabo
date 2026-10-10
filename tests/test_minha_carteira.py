"""Testes offline do cruzamento carteira pessoal x ranking."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import minha_carteira as M  # noqa: E402

RANKING = [
    {'posicao': 1, 'ticker': 'PRIO3', 'setor': 'Energia', 'nota': 6.0, 'acao_sugerida': 'comprar',
     'certeza': 'baixa', 'preco_atual': 60.0, 'data_cotacao': '2026-10-05', 'upside_ajustado_pct': 10.0},
    {'posicao': 2, 'ticker': 'ITUB4', 'setor': 'Financeiro', 'nota': 4.0, 'acao_sugerida': 'aguardar',
     'certeza': 'media', 'preco_atual': 40.0, 'data_cotacao': '2026-10-05', 'upside_ajustado_pct': 2.0},
]


class TesteLeitura(unittest.TestCase):
    def test_ponto_e_virgula_e_decimal_brasileiro(self):
        p = M.ler_posicoes('Ativo;Qtd;Preço Médio\nPRIO3;100;"42,10"\n')
        self.assertEqual(p, [{'ticker': 'PRIO3', 'quantidade': 100.0, 'preco_medio': 42.10, 'preco_atual': None}])

    def test_virgula_como_separador_e_fracionario(self):
        p = M.ler_posicoes('ticker,quantidade\nitub4f,10\nITUB4,20\n')
        self.assertEqual(p, [{'ticker': 'ITUB4', 'quantidade': 30.0, 'preco_medio': None, 'preco_atual': None}])

    def test_preco_medio_ponderado(self):
        p = M.ler_posicoes('ticker;quantidade;preco_medio\nPRIO3;100;10\nPRIO3;300;20\n')
        self.assertEqual(p[0]['preco_medio'], 17.5)

    def test_preco_atual_serve_para_ativo_fora_do_ranking(self):
        p = M.ler_posicoes('ticker;quantidade;preco_medio;preco_atual\nBTLG11;5;;102,40\n')
        r = M.cruzar(p, RANKING)
        self.assertEqual(r['valor_total'], 512.0)
        self.assertEqual(r['posicoes'][0]['origem_preco'], 'preço informado por você/corretora')
        self.assertEqual(r['cobertura_ranking_pct'], 0.0)

    def test_milhar_brasileiro_sem_decimal(self):
        p = M.ler_posicoes('ticker;quantidade\nPRIO3;1.000\n')
        self.assertEqual(p[0]['quantidade'], 1000.0)

    def test_coluna_obrigatoria(self):
        with self.assertRaises(ValueError):
            M.ler_posicoes('papel;valor\nPRIO3;10\n')


class TesteCruzamento(unittest.TestCase):
    def test_pesos_cobertura_e_alertas(self):
        pos = [{'ticker': 'PRIO3', 'quantidade': 100, 'preco_medio': 50.0},     # 6000
               {'ticker': 'ITUB4', 'quantidade': 50, 'preco_medio': None},      # 2000
               {'ticker': 'XXXX3', 'quantidade': 100, 'preco_medio': 20.0}]     # 2000, fora do ranking
        r = M.cruzar(pos, RANKING, {'PRIO3': 10.0, 'WEGE3': 5.0})
        self.assertEqual(r['valor_total'], 10000.0)
        self.assertEqual(r['cobertura_ranking_pct'], 80.0)
        self.assertEqual(r['fora_do_ranking'], ['XXXX3'])
        self.assertEqual(r['peso_por_acao_modelo_pct'], {'comprar': 60.0, 'aguardar': 20.0})
        self.assertEqual(r['nota_media_ponderada'], 5.5)           # (6*60 + 4*20) / 80
        self.assertEqual(r['carteira_xp_sem_posicao'], ['WEGE3'])
        self.assertEqual(r['posicoes'][0]['resultado_vs_preco_medio_pct'], 20.0)
        self.assertTrue(any('PRIO3' in a and '25%' in a for a in r['alertas']))
        self.assertTrue(any('Energia' in a for a in r['alertas']))

    def test_ranking_com_campos_nulos_nao_quebra(self):
        rk = [{'ticker': 'X1', 'preco_atual': 10.0, 'nota': None, 'setor': None, 'acao_sugerida': None}]
        r = M.cruzar([{'ticker': 'X1', 'quantidade': 1, 'preco_medio': None, 'preco_atual': None}], rk)
        self.assertIsNone(r['nota_media_ponderada'])
        self.assertIn('n/d', r['peso_por_setor_pct'])
        self.assertIn('data não informada', M.md(r, ''))

    def test_preco_informado_vence_o_do_ranking(self):
        r = M.cruzar([{'ticker': 'PRIO3', 'quantidade': 10, 'preco_medio': None, 'preco_atual': 70.0}], RANKING)
        self.assertEqual(r['valor_total'], 700.0)

    def test_sem_preco_nao_quebra(self):
        r = M.cruzar([{'ticker': 'XXXX3', 'quantidade': 10, 'preco_medio': None}], RANKING)
        self.assertEqual(r['valor_total'], 0)
        self.assertIsNone(r['posicoes'][0]['peso_pct'])
        self.assertTrue(any('Sem preço' in a for a in r['alertas']))
        self.assertEqual(r['sem_preco'], ['XXXX3'])
        self.assertIn('fora do valor total', M.md(r, '2026-10-05'))
        self.assertIn('Minha carteira', M.md(r, '2026-10-05'))


class TestePublico(unittest.TestCase):
    def test_exporta_so_campos_publicos_e_recarrega(self):
        with tempfile.TemporaryDirectory() as d:
            pasta = os.path.join(d, 'semana_20261005')
            os.mkdir(pasta)
            rk = [dict(r, preco_alvo_xp=99.0, justificativa_upside_ajustado='texto longo') for r in RANKING]
            with open(os.path.join(pasta, 'sintese.json'), 'w') as f:
                json.dump({'data': '2026-10-05', 'ranking': rk}, f)
            with open(os.path.join(pasta, 'xp.json'), 'w') as f:
                json.dump({'data_relatorio': '2026-10-01', 'acoes': [{'ticker': 'PRIO3', 'peso_atual': 5.0}]}, f)
            pub = M.exportar_publico(pasta)
            self.assertNotIn('preco_alvo_xp', pub['ranking'][0])
            self.assertNotIn('justificativa_upside_ajustado', pub['ranking'][0])
            self.assertEqual(pub['pesos_xp'], {'PRIO3': 5.0})
            arq = os.path.join(d, 'ranking.json')
            with open(arq, 'w') as f:
                json.dump(pub, f)
            ranking, pesos, data = M.carregar_publico(arq)
            self.assertEqual((len(ranking), pesos, data), (2, {'PRIO3': 5.0}, '2026-10-05'))

    def test_url_http_sem_tls_e_recusada(self):
        with self.assertRaises(SystemExit):
            M.carregar_publico('http://exemplo.com/ranking.json')


if __name__ == '__main__':
    unittest.main()
