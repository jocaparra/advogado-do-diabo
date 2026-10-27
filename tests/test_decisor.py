"""Camada de decisão em modo sombra: consolidação determinística e conferência da saída do agente."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
import conferir_decisao as CD  # noqa: E402
import consolidar_evidencias as CE  # noqa: E402


def semana(tmp, **extra):
    r = [{'ticker': 'AAA3', 'posicao': 1, 'nota': 7.0, 'acao_sugerida': 'comprar', 'certeza': 'média', 'setor': 'Energia',
          'upside_xp_pct': 20.0, 'upside_mediana_pct': None, 'upside_ajustado_pct': -2.0, 'n_alvos_mediana': 0},
         {'ticker': 'BBB3', 'posicao': 2, 'nota': 5.0, 'acao_sugerida': 'aguardar', 'certeza': 'baixa', 'setor': 'Bancos',
          'upside_xp_pct': 5.0, 'upside_mediana_pct': 6.0, 'upside_ajustado_pct': 5.0, 'n_alvos_mediana': 3}]
    arq = {'sintese.json': {'ranking': r},
           'casas.json': {'tickers': {'BBB3': {'status': 'ok', 'n_casas_verificadas': 3}, 'AAA3': {'status': 'dado insuficiente'}}},
           'fundamentos_cvm.json': {'tickers': {'AAA3': {'situacao': 'ok', 'valores': {'p_l': {'valor': 10.0}}}}},
           'precos_yahoo.json': {'acoes': {'AAA3': {'p_l': 30.0}}},
           'fluxo.json': {'acoes': {'AAA3': {'retornos_preco_pct': {'ret_30_dias_corridos': {'diferenca_pp': -3.0}}}}},
           'risco.json': {'tabela_por_ticker': {'AAA3': {'vol_90pregoes_anual_pct': 30.0}},
                          'correlacao_topo_90pregoes': {'AAA3_BBB3': 0.8, 'leitura': 'x'}}}
    arq.update(extra)
    for n, d in arq.items():
        json.dump(d, open(os.path.join(tmp, n), 'w'))


class TesteConsolidar(unittest.TestCase):
    def test_divergencias_por_regra_e_fatos_citaveis(self):
        with tempfile.TemporaryDirectory() as raiz:
            tmp = os.path.join(raiz, 'semana_20261015')
            os.makedirs(tmp)
            semana(tmp)
            ev = CE.consolidar(tmp)
        tipos = {(d['tipo'], d['ticker']) for d in ev['divergencias']}
        self.assertIn(('compra_sem_consenso_de_casas', 'AAA3'), tipos)
        self.assertIn(('compra_com_upside_nao_positivo', 'AAA3'), tipos)
        self.assertIn(('compra_contra_o_fluxo', 'AAA3'), tipos)
        self.assertIn(('multiplo_yahoo_vs_cvm', 'AAA3'), tipos)         # 30x contra 10x
        self.assertIn(('par_do_topo_correlacionado', None), tipos)
        self.assertEqual(ev['fatos']['AAA3.upside_ajustado_pct'], -2.0)
        self.assertEqual(ev['fatos']['AAA3.yahoo_nao_auditado_p_l'], 30.0)  # rótulo no próprio id
        self.assertEqual(ev['por_ticker']['AAA3']['confianca_dados'], 'média')   # sem casas nem notícias: nunca 'alta'
        self.assertNotIn('casas', ev['por_ticker']['AAA3']['fontes_disponiveis'])
        self.assertIn('casas de análise: dado insuficiente', ev['por_ticker']['AAA3']['dados_ausentes'])

    def test_sem_sintese_recusa(self):
        with tempfile.TemporaryDirectory() as raiz:
            tmp = os.path.join(raiz, 'semana_20261015')
            os.makedirs(tmp)
            with self.assertRaises(SystemExit):
                CE.consolidar(tmp)


class TesteConferirDecisao(unittest.TestCase):
    EV = {'fatos': {'AAA3.upside_ajustado_pct': -2.0, 'AAA3.cvm_p_l': 10.0, 'BBB3.nota': 5.0},
          'por_ticker': {'AAA3': {'confianca_dados': 'baixa', 'dados_ausentes': ['casas']},
                         'BBB3': {'confianca_dados': 'alta', 'dados_ausentes': []}}}

    def dec(self, **kw):
        base = {'ticker': 'AAA3', 'acao': 'aguardar', 'acao_ranking': 'comprar', 'tese': 'Upside ajustado negativo.',
                'evidencias_ids': ['AAA3.upside_ajustado_pct'], 'argumentos_contrarios': ['Fluxo forte'],
                'alternativas_rejeitadas': [], 'invalidadores': ['Casas confirmarem alvo'], 'confianca': 'baixa',
                'dados_ausentes': ['casas'], 'revisar_quando': ['Próxima semana']}
        base.update(kw)
        d2 = dict(base, ticker='BBB3', confianca='média', dados_ausentes=[], evidencias_ids=['BBB3.nota'], tese='Nota neutra.')
        return {'modo': 'sombra', 'conclusao_geral': 'ok', 'ranking_confiavel': True, 'decisoes': [base, d2]}

    def test_decisao_valida(self):
        e, a = CD.conferir(self.dec(), self.EV)
        self.assertEqual((e, a), ([], []))

    def test_erros_estruturais(self):
        e, _ = CD.conferir(self.dec(evidencias_ids=['AAA3.inventado']), self.EV)
        self.assertTrue(any('inexistentes' in x for x in e))
        e, _ = CD.conferir(self.dec(confianca='alta'), self.EV)
        self.assertTrue(any("confiança 'alta'" in x for x in e))
        d = self.dec()
        d['decisoes'].pop()
        e, _ = CD.conferir(d, self.EV)
        self.assertTrue(any('sem decisão' in x for x in e))
        d = self.dec()
        del d['decisoes'][0]['invalidadores']
        e, _ = CD.conferir(d, self.EV)
        self.assertTrue(any(x.startswith('schema') for x in e))

    def so_aaa(self, **kw):
        """Decisão com os campos aplicados apenas ao primeiro papel (AAA3); BBB3 fica como está."""
        d = self.dec()
        d['decisoes'][0].update(kw)
        return d

    def test_decisao_antiga_sem_independencia_continua_valida(self):
        e, a = CD.conferir(self.dec(), self.EV)            # campo opcional: arquivos antigos seguem válidos
        self.assertEqual((e, a), ([], []))

    def test_comprar_sem_independencia_vira_aviso_e_nao_erro(self):
        e, a = CD.conferir(self.so_aaa(acao='comprar'), self.EV)
        self.assertEqual(e, [])
        self.assertTrue(any('independencia_evidencias' in x for x in a))

    def test_independencia_valida_passa(self):
        ind = {'fontes_independentes': 1, 'grupos_mesma_origem': [['AAA3.upside_ajustado_pct']], 'observacao': 'mesmo balanço'}
        e, a = CD.conferir(self.so_aaa(acao='comprar', independencia_evidencias=ind), self.EV)
        self.assertEqual((e, a), ([], []))

    def test_independencia_incoerente_e_erro(self):
        e, _ = CD.conferir(self.so_aaa(independencia_evidencias={'fontes_independentes': 5}), self.EV)
        self.assertTrue(any('fontes independentes declaradas' in x for x in e))
        e, _ = CD.conferir(self.so_aaa(independencia_evidencias={'fontes_independentes': 1, 'grupos_mesma_origem': [['AAA3.outro']]}), self.EV)
        self.assertTrue(any('grupos_mesma_origem' in x for x in e))
        e, _ = CD.conferir(self.so_aaa(independencia_evidencias={'fontes_independentes': -1}), self.EV)
        self.assertTrue(any(x.startswith('schema') for x in e))
        e, _ = CD.conferir(self.so_aaa(independencia_evidencias={'observacao': 'sem número'}), self.EV)
        self.assertTrue(any(x.startswith('schema') for x in e))

    def test_confianca_alta_exige_duas_fontes_independentes(self):
        ev = {**self.EV, 'por_ticker': {**self.EV['por_ticker'], 'AAA3': {'confianca_dados': 'alta', 'dados_ausentes': []}}}
        d = self.so_aaa(confianca='alta', dados_ausentes=[], independencia_evidencias={'fontes_independentes': 1})
        e, _ = CD.conferir(d, ev)
        self.assertTrue(any('fonte(s) independente(s)' in x for x in e))
        d = self.so_aaa(confianca='alta', dados_ausentes=[], evidencias_ids=['AAA3.upside_ajustado_pct', 'AAA3.cvm_p_l'],
                        independencia_evidencias={'fontes_independentes': 2})
        e, _ = CD.conferir(d, ev)
        self.assertEqual(e, [])

    def test_numero_inventado_vira_aviso(self):
        _, a = CD.conferir(self.dec(tese='Upside ajustado de -2,0% e P/L de 14,7x.'), self.EV)
        self.assertEqual(len(a), 1)              # -2,0 bate com o fato; 14,7 não
        self.assertIn('14.7', a[0])


if __name__ == '__main__':
    unittest.main()
