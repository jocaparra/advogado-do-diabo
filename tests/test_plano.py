"""Testes offline do plano do usuário (horizonte, risco vs. tolerância, limites)."""
import json
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import minha_carteira as M  # noqa: E402
import plano as PL  # noqa: E402

COMP_VALOR = {'catalisadores': 2, 'noticias': 2, 'momentum': 2, 'macro_eleicao': 2, 'valuation_upside': 10}
COMP_GIRO = {'catalisadores': 10, 'noticias': 10, 'momentum': 10, 'macro_eleicao': 10, 'valuation_upside': 0}

RANKING = [
    {'posicao': 1, 'ticker': 'AAAA3', 'setor': 'Energia', 'nota': 6.0, 'acao_sugerida': 'comprar', 'certeza': 'baixa',
     'preco_atual': 10.0, 'componentes': COMP_GIRO, 'vol_90pregoes_anual_pct': 40.0,
     'valuation_margem_pct': {'bear': -50.0, 'base': -30.0, 'bull': -10.0}},
    {'posicao': 2, 'ticker': 'BBBB4', 'setor': 'Financeiro', 'nota': 4.0, 'acao_sugerida': 'aguardar', 'certeza': 'media',
     'preco_atual': 10.0, 'componentes': COMP_VALOR, 'vol_90pregoes_anual_pct': 20.0},
]
POS = [{'ticker': 'AAAA3', 'quantidade': 10, 'preco_medio': None, 'preco_atual': None},
       {'ticker': 'BBBB4', 'quantidade': 10, 'preco_medio': None, 'preco_atual': None}]


def plano(**kw):
    base = {'horizonte': 'meses', 'objetivo': 'crescimento', 'queda_max_pct': 15, 'limite_ativo_pct': 25,
            'limite_setor_pct': 40}
    base.update(kw)
    return PL.validar(base)


class TesteHorizontes(unittest.TestCase):
    def test_pesos_somam_um_e_semanas_reproduz_o_modelo(self):
        h = PL.horizontes()
        for nome in PL.HORIZONTES:
            self.assertAlmostEqual(sum(h[nome]['pesos'].values()), 1.0, places=9, msg=nome)
            self.assertEqual(set(h[nome]['pesos']), set(PL.COMPONENTES))
        self.assertEqual(h['semanas']['pesos'], {'catalisadores': 0.25, 'noticias': 0.20, 'momentum': 0.20,
                                                 'macro_eleicao': 0.20, 'valuation_upside': 0.15})

    def test_semanas_devolve_a_nota_publicada(self):
        self.assertEqual(PL.nota_no_horizonte(COMP_VALOR, 'semanas', 4.0), 4.0)

    def test_anos_valoriza_valuation(self):
        sem = PL.nota_no_horizonte(COMP_VALOR, 'meses')
        ano = PL.nota_no_horizonte(COMP_VALOR, 'anos')
        self.assertEqual(sem, round(0.2 * 2 + 0.1 * 2 + 0.1 * 2 + 0.2 * 2 + 0.4 * 10, 2))
        self.assertGreater(ano, sem)
        self.assertLess(PL.nota_no_horizonte(COMP_GIRO, 'anos'), PL.nota_no_horizonte(COMP_GIRO, 'meses'))

    def test_componente_ausente_devolve_none(self):
        self.assertIsNone(PL.nota_no_horizonte({'catalisadores': 5}, 'meses'))
        self.assertIsNone(PL.nota_no_horizonte(None, 'anos'))


class TesteRisco(unittest.TestCase):
    def test_vol_ponderada_e_raiz_do_prazo(self):
        linhas = [{'peso_pct': 50, 'vol_anual_pct': 40.0}, {'peso_pct': 50, 'vol_anual_pct': 20.0}]
        r = PL.risco_vs_tolerancia(linhas, 'anos', 25)
        self.assertEqual(r['vol_anual_pct'], 30.0)
        self.assertEqual(r['movimento_1dp_pct'], 30.0)            # raiz(1 ano) = 1
        self.assertTrue(r['acima_da_tolerancia'])
        r = PL.risco_vs_tolerancia(linhas, 'meses', 25)
        self.assertAlmostEqual(r['movimento_1dp_pct'], round(30 * math.sqrt(0.5), 1))
        self.assertFalse(r['acima_da_tolerancia'])

    def test_sem_volatilidade_devolve_none(self):
        self.assertIsNone(PL.risco_vs_tolerancia([{'peso_pct': 100, 'vol_anual_pct': None}], 'meses', 10))


class TesteValidacao(unittest.TestCase):
    def test_rejeita_horizonte_e_faixas_invalidas(self):
        with self.assertRaises(ValueError):
            plano(horizonte='decadas')
        with self.assertRaises(ValueError):
            plano(queda_max_pct=0)
        with self.assertRaises(ValueError):
            plano(limite_ativo_pct=150)
        with self.assertRaises(ValueError):
            plano(objetivo='lucro')

    def test_assistente_com_respostas_simuladas(self):
        resp = iter(['3', '2', '', '30', '20'])           # anos, renda, padrão, 30, 20
        p = PL.assistente(lambda _='': next(resp))
        self.assertEqual((p['horizonte'], p['objetivo']), ('anos', 'renda'))
        self.assertEqual((p['queda_max_pct'], p['limite_ativo_pct'], p['limite_setor_pct']), (15.0, 30.0, 20.0))


class TeseArquivo(unittest.TestCase):
    def test_salva_0600_le_e_apaga(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ['ADVOGADO_DO_DIABO_PLANO'] = os.path.join(d, 'x', 'plano.json')
            try:
                self.assertIsNone(PL.ler_plano())
                caminho = PL.salvar_plano(plano(horizonte='anos'))
                self.assertEqual(oct(os.stat(caminho).st_mode & 0o777), oct(0o600))
                self.assertEqual(PL.ler_plano()['horizonte'], 'anos')
                self.assertTrue(PL.apagar_plano())
                self.assertFalse(PL.apagar_plano())
            finally:
                os.environ.pop('ADVOGADO_DO_DIABO_PLANO')


class TesteIntegracao(unittest.TestCase):
    def test_sem_plano_nada_muda(self):
        r = M.cruzar(POS, RANKING)
        self.assertNotIn('plano', r)
        self.assertNotIn('Seu plano', M.md(r, '2026-10-05'))

    def test_limites_do_plano_valem(self):
        r = M.cruzar(POS, RANKING, plano=plano(limite_ativo_pct=60, limite_setor_pct=60))
        self.assertFalse(any('limite' in a for a in r['alertas']))              # cada posição tem 50% < 60
        r = M.cruzar(POS, RANKING, plano=plano(limite_ativo_pct=30))
        self.assertTrue(any('AAAA3' in a and 'seu' in a for a in r['alertas']))

    def test_secao_por_horizonte_e_ordem(self):
        meses = M.cruzar(POS, RANKING, plano=plano(horizonte='meses'))
        self.assertEqual(meses['plano']['ordem_no_horizonte'], ['AAAA3', 'BBBB4'])   # 6,0 contra 5,2
        anos = M.cruzar(POS, RANKING, plano=plano(horizonte='anos'))
        self.assertEqual(anos['plano']['ordem_no_horizonte'], ['BBBB4', 'AAAA3'])    # valuation inverte: 6,8 contra 4,0
        txt = M.md(meses, '2026-10-05')
        self.assertIn('Seu plano: meses', txt)
        self.assertIn('premissa do projeto, não validada', txt)
        self.assertNotRegex(txt.lower(), r'\b(compre|venda|aporte)\b')

    def test_anos_mostra_valuation_e_aviso(self):
        txt = M.md(M.cruzar(POS, RANKING, plano=plano(horizonte='anos')), '2026-10-05')
        self.assertIn('evidência do modelo semanal é fraca', txt)
        self.assertIn('AAAA3', txt.split('Margem do valor justo')[1])

    def test_ranking_v1_sem_campos_nao_quebra(self):
        v1 = [{k: v for k, v in RANKING[0].items() if k not in ('componentes', 'vol_90pregoes_anual_pct')}]
        txt = M.md(M.cruzar(POS[:1], v1, plano=plano()), '2026-10-05')
        self.assertIn('não traz volatilidade', txt)
        self.assertIn('não traz os componentes', txt)

    def test_exportacao_v2_enriquecida(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, 'sintese.json'), 'w') as f:
                json.dump({'data': '2026-10-05', 'ranking': [{'ticker': 'AAAA3', 'componentes': COMP_VALOR,
                                                              'preco_alvo_xp': 9.0}]}, f)
            with open(os.path.join(d, 'risco.json'), 'w') as f:
                json.dump({'tabela_por_ticker': {'AAAA3': {'vol_90pregoes_anual_pct': 33.0,
                                                          'beta_ibov_multifator': 0.7}}}, f)
            with open(os.path.join(d, 'dossie.json'), 'w') as f:
                json.dump({'tickers': [{'ticker': 'AAAA3', 'valuation': {'status': 'ok', 'cenarios': {
                    'bear': {'margem_pct': -40.04}, 'base': {'margem_pct': -20.0}, 'bull': {'margem_pct': 5.0}}}}]}, f)
            pub = M.exportar_publico(d)
        self.assertEqual(pub['versao'], 2)
        r = pub['ranking'][0]
        self.assertEqual((r['vol_90pregoes_anual_pct'], r['beta_ibov_multifator']), (33.0, 0.7))
        self.assertEqual(r['valuation_margem_pct'], {'bear': -40.0, 'base': -20.0, 'bull': 5.0})
        self.assertNotIn('preco_alvo_xp', r)


if __name__ == '__main__':
    unittest.main()
