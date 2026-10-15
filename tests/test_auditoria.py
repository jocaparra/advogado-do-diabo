"""Regressões da auditoria: proventos em segunda fonte, metadados do Yahoo, pesos efetivos e custo da medição."""
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coletar_proventos as CP  # noqa: E402
import coletar_yahoo as CY  # noqa: E402
import conferir as CF  # noqa: E402


class TesteProventos(unittest.TestCase):
    def test_comparar_aceita_tolerancia_e_aponta_diferencas(self):
        y = {'2026-03-01': 1.00, '2026-06-01': 0.50, '2026-07-01': 0.30}
        b = {'2026-03-01': 1.01, '2026-06-01': 0.80}
        d = CP.comparar(y, b, '2026-01-01', '2026-12-31')
        self.assertEqual([(x['data_ex'], x['motivo']) for x in d],
                         [('2026-06-01', 'valores diferentes'), ('2026-07-01', 'data presente em uma só fonte')])
        self.assertEqual(CP.comparar(y, b, '2026-07-01', '2026-12-31')[0]['data_ex'], '2026-07-01')

    def test_brapi_ajusta_por_bonificacao_como_o_yahoo(self):
        payload = {'results': [{'dividendsData': {
            'cashDividends': [{'exDate': '2025-12-10T03:00:00.000Z', 'rate': 2.0},
                              {'exDate': '2026-02-10T03:00:00.000Z', 'rate': 1.0}],
            'stockDividends': [{'label': 'BONIFICACAO', 'factor': 1.03, 'lastDatePrior': '2025-12-23T03:00:00.000Z'}]}}]}

        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with mock.patch.object(CP.urllib.request, 'urlopen', return_value=R(json.dumps(payload).encode())):
            e = CP.eventos_brapi('ITUB4')
        self.assertAlmostEqual(e['2025-12-10'], 2.0 / 1.03, places=6)
        self.assertAlmostEqual(e['2026-02-10'], 1.0, places=6)    # depois da bonificação: nominal

    def test_status_por_ticker(self):
        import datetime as dt
        fp = lambda t: {'2026-08-24': 1.0}
        ok = CP.coletar(['A'], dt.date(2026, 10, 15), fp, lambda t: {'2026-08-24': 1.0})
        self.assertEqual(ok['por_ticker']['A']['verificacao']['status'], 'confirmado')
        self.assertEqual(ok['por_ticker']['A']['coberto_ate'], '2026-10-15')
        div = CP.coletar(['A'], dt.date(2026, 10, 15), fp, lambda t: {'2026-08-24': 2.0})
        self.assertEqual(div['por_ticker']['A']['verificacao']['status'], 'divergente')
        self.assertIsNone(div['por_ticker']['A']['coberto_ate'])

        def cai(t):
            raise OSError('HTTP Error 401')
        nv = CP.coletar(['A'], dt.date(2026, 10, 15), fp, cai)
        self.assertEqual(nv['por_ticker']['A']['verificacao']['status'], 'nao_verificado')
        self.assertIsNone(nv['por_ticker']['A']['coberto_ate'])


class TesteYahoo(unittest.TestCase):
    def test_metadados_de_nao_auditado_e_data_da_cotacao(self):
        # 2026-10-14 20:55 UTC = 17:55 em Brasília: mesma data
        d = CY.coletar(['AAA3'], lambda s: {'currentPrice': 10, 'regularMarketTime': 1792011300, 'marketState': 'CLOSED'})
        self.assertIs(d['auditado'], False)
        self.assertIn('não auditado', d['aviso'])
        self.assertTrue(d['data_coleta'].endswith('+00:00'))
        self.assertEqual(d['acoes']['AAA3']['data_cotacao'], '2026-10-14')
        self.assertIs(d['acoes']['AAA3']['mercado_aberto'], False)

    def test_schema_do_arquivo_gerado(self):
        import validar
        d = CY.coletar(['AAA3'], lambda s: {'currentPrice': 10, 'regularMarketTime': 1792011300, 'marketState': 'REGULAR'})
        with open(os.path.join(CF.RAIZ, 'schemas', 'precos_yahoo.schema.json'), encoding='utf-8') as f:
            self.assertEqual(validar.validar(d, json.load(f)), [])
        d['auditado'] = True
        with open(os.path.join(CF.RAIZ, 'schemas', 'precos_yahoo.schema.json'), encoding='utf-8') as f:
            self.assertTrue(validar.validar(d, json.load(f)))

    def test_conferir_alerta_intradiario_e_cobertura(self):
        rel = CF.Relatorio()
        y = {'auditado': False, 'data_coleta': '2026-10-15T11:00:00+00:00',
             'acoes': {'AAA3': {'mercado_aberto': True}}}
        CF.conferir_yahoo(rel, y, {'ibovespa': {'data_cotacao': '2026-10-14'}}, [{'ticker': 'AAA3'}, {'ticker': 'BBB3'}])
        regras = {i['regra'] for i in rel.itens}
        self.assertEqual(regras, {'yahoo_cobertura', 'yahoo_intradiario'})


class TestePesosEfetivos(unittest.TestCase):
    def test_baseline_sem_arquivo_de_versoes(self):
        with tempfile.TemporaryDirectory() as tmp:
            import aprender
            with mock.patch.object(aprender, 'ARQ_VERSOES', os.path.join(tmp, 'nao_existe.json')):
                pesos, rotulo = CF.pesos_efetivos()
            self.assertAlmostEqual(sum(pesos.values()), 1.0)
            self.assertIn('baseline', rotulo)


class TesteBonificacaoITUB4(unittest.TestCase):
    """Fator de bonificação aplicado só aos eventos anteriores à data com, uma única vez."""

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def brapi(self, caixa, acoes):
        payload = {'results': [{'dividendsData': {'cashDividends': [
            {'exDate': d + 'T03:00:00.000Z', 'rate': v} for d, v in caixa], 'stockDividends': acoes}}]}
        with mock.patch.object(CP.urllib.request, 'urlopen', return_value=self.R(json.dumps(payload).encode())):
            return CP.eventos_brapi('ITUB4')

    def bonus(self, fator, data, label='BONIFICACAO'):
        return {'label': label, 'factor': fator, 'lastDatePrior': data + 'T03:00:00.000Z', 'exDate': None}

    def test_fator_so_nos_eventos_anteriores_a_data_com(self):
        e = self.brapi([('2025-12-10', 1.03), ('2025-12-23', 1.03), ('2025-12-24', 1.03), ('2026-02-10', 1.03)],
                       [self.bonus(1.03, '2025-12-23')])
        self.assertAlmostEqual(e['2025-12-10'], 1.0, places=6)    # antes: ajustado
        self.assertAlmostEqual(e['2025-12-23'], 1.0, places=6)    # na data com: ainda ajustado
        self.assertAlmostEqual(e['2025-12-24'], 1.03, places=6)   # data ex da bonificação: nominal
        self.assertAlmostEqual(e['2026-02-10'], 1.03, places=6)   # depois: nominal

    def test_evento_duplicado_na_fonte_nao_aplica_o_fator_duas_vezes(self):
        e = self.brapi([('2025-12-10', 1.03)], [self.bonus(1.03, '2025-12-23'), self.bonus(1.03, '2025-12-23')])
        self.assertAlmostEqual(e['2025-12-10'], 1.0, places=6)   # 1.03/1.03, não 1.03/1.03**2

    def test_bonificacoes_distintas_se_compoem(self):
        e = self.brapi([('2025-02-01', 1.1 * 1.03), ('2025-06-01', 1.03), ('2026-01-05', 5.0)],
                       [self.bonus(1.1, '2025-03-17'), self.bonus(1.03, '2025-12-23')])
        self.assertAlmostEqual(e['2025-02-01'], 1.0, places=6)    # antes das duas
        self.assertAlmostEqual(e['2025-06-01'], 1.0, places=6)    # entre as duas: só a de dezembro
        self.assertAlmostEqual(e['2026-01-05'], 5.0, places=6)    # depois das duas

    def test_reducao_de_capital_e_rotulos_desconhecidos_nao_ajustam(self):
        e = self.brapi([('2025-06-01', 2.0)], [self.bonus(100, '2025-12-23', 'CIS RED CAP')])
        self.assertAlmostEqual(e['2025-06-01'], 2.0, places=6)

    def test_grupamento_multiplica(self):
        e = self.brapi([('2025-06-01', 0.1)], [self.bonus(10, '2025-12-23', 'GRUPAMENTO')])
        self.assertAlmostEqual(e['2025-06-01'], 1.0, places=6)

    def test_serie_do_itub4_do_arquivo_real_reconcilia_com_yahoo(self):
        # valores reais de 2025 (brapi nominal x Yahoo ajustado), coletados em 15/10/2026
        brapi = [('2025-11-03', 0.01765), ('2025-12-01', 0.01765), ('2025-12-10', 2.237973)]
        yahoo = {'2025-11-03': 0.017136, '2025-12-01': 0.017136, '2025-12-10': 2.172789}
        e = self.brapi(brapi, [self.bonus(1.03, '2025-12-23')])
        self.assertEqual(CP.comparar(yahoo, e, '2025-10-20', '2026-10-15'), [])


class TesteAprendizadoExcluiSemCobertura(unittest.TestCase):
    """aprender._obs só entrega observações com proventos conhecidos até o fim da janela."""

    def rodar(self, com_cobertura):
        import aprender
        import test_avaliar as TA
        with tempfile.TemporaryDirectory() as tmp:
            TA.TesteAvaliacao().monta(tmp)
            if com_cobertura:
                pasta = os.path.join(tmp, 'semana_20260601')
                p = json.load(open(os.path.join(pasta, 'precos.json')))
                p['data_coleta'] = '2026-09-30 10:00:00'      # depois do fim das janelas (série termina em jul/2026)
                for v in p['acoes'].values():
                    v['dividendos'] = []
                json.dump(p, open(os.path.join(pasta, 'precos.json'), 'w'))
            out = io.StringIO()
            with mock.patch.object(aprender, 'HORIZONTE', '4_semanas'), mock.patch.object(sys, 'stdout', out):
                obs, aval = aprender._obs(os.path.join(tmp, 'semana_20260601'))
        return obs, aval, out.getvalue()

    def test_sem_cobertura_fica_fora_e_avisa(self):
        obs, aval, saida = self.rodar(com_cobertura=False)
        self.assertEqual(len(aval['observacoes']['4_semanas']), 2)   # a avaliação as enxerga...
        self.assertEqual(obs, [])                                    # ...o aprendizado não as usa
        self.assertIn('2 de 2 observações', saida)
        self.assertTrue(aval['avaliacao_incompleta'])

    def test_com_cobertura_entra(self):
        obs, aval, saida = self.rodar(com_cobertura=True)
        self.assertEqual(len(obs), 2)
        self.assertNotIn('aviso:', saida)
        self.assertFalse(aval['avaliacao_incompleta'])


if __name__ == '__main__':
    unittest.main()


class TesteRotuloYahoo(unittest.TestCase):
    def test_cita_yahoo_sem_rotulo_gera_aviso(self):
        with tempfile.TemporaryDirectory() as tmp:
            json.dump({'ranking': [{'fontes': [
                {'fonte': 'Yahoo, não auditado (P/L 14x)'},
                {'fonte': 'precos.json, Yahoo Finance (dados B3), fechamento'},
                {'fonte': 'P/L de 197x vem só do Yahoo'},
                {'fonte': 'precos_yahoo.json não usado nesta rodada.'}]}]}, open(os.path.join(tmp, 'sintese.json'), 'w'))
            rel = CF.Relatorio()
            CF.conferir_rotulo_yahoo(rel, tmp)
        self.assertEqual(len(rel.itens), 1)
        self.assertEqual(rel.itens[0]['regra'], 'rotulo_yahoo')
        self.assertIn('197', rel.itens[0]['encontrado'])
