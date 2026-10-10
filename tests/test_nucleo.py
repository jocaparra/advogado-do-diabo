"""Testes offline do núcleo numérico: validação de schema, indicadores da CVM e conferência."""
import datetime as dt
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import conferir  # noqa: E402
import regras as R  # noqa: E402
import indicadores as I  # noqa: E402
import validar  # noqa: E402
import valuation as V  # noqa: E402


def conta(v, ds='x', ref='2026-06-30', ver=1):
    return (v, ds, ref, ver, 'teste')


class TesteValidar(unittest.TestCase):
    def test_obrigatorio_tipo_e_faixa(self):
        sch = {'type': 'object', 'required': ['n'], 'properties': {'n': {'type': 'number', 'minimum': 0, 'maximum': 10},
                                                                   'a': {'type': 'string', 'enum': ['x', 'y']}}}
        self.assertEqual(validar.validar({'n': 5, 'a': 'x'}, sch), [])
        self.assertTrue(any('obrigatório' in e for e in validar.validar({}, sch)))
        self.assertTrue(any('máximo' in e for e in validar.validar({'n': 11}, sch)))
        self.assertTrue(any('esperado number' in e for e in validar.validar({'n': 'não verificado'}, sch)))
        self.assertTrue(any('fora de' in e for e in validar.validar({'n': 1, 'a': 'z'}, sch)))

    def test_bool_nao_e_numero(self):
        self.assertTrue(validar.validar(True, {'type': 'number'}))


class TesteLTM(unittest.TestCase):
    def test_doze_meses(self):
        # FY2025 = 100, 1S26 = 70, 1S25 = 40  ->  12 meses = 130
        dre = {('2025-01-01', '2025-12-31'): {'3.11': conta(100)},
               ('2026-01-01', '2026-06-30'): {'3.11': conta(70)},
               ('2025-01-01', '2025-06-30'): {'3.11': conta(40)}}
        v, ref, _ = I.ltm(dre, I._por_cd('3.11'))
        self.assertEqual(v, 130)
        self.assertEqual(ref, '2026-06-30')

    def test_sem_trimestre_usa_exercicio(self):
        dre = {('2025-01-01', '2025-12-31'): {'3.11': conta(100)}}
        v, ref, _ = I.ltm(dre, I._por_cd('3.11'))
        self.assertEqual((v, ref), (100, '2025-12-31'))

    def test_ytd_sem_comparativo_nao_inventa(self):
        dre = {('2025-01-01', '2025-12-31'): {'3.11': conta(100)}, ('2026-01-01', '2026-06-30'): {'3.11': conta(70)}}
        v, ref, metodo = I.ltm(dre, I._por_cd('3.11'))
        self.assertEqual((v, ref), (100, '2025-12-31'))
        self.assertIn('indisponíveis', metodo)


class TesteIndicadores(unittest.TestCase):
    def saida(self, shares_escala=1):
        dre = {('2025-01-01', '2025-12-31'): {
            '3.01': conta(1000, 'Receita'), '3.05': conta(300, 'Resultado Antes do Resultado Financeiro'),
            '3.11.01': conta(200, 'Atribuído a Sócios da Empresa Controladora'), '3.99.01.01': conta(2.0, 'ON')}}
        dva = {('2025-01-01', '2025-12-31'): {'7.04.01': conta(-50, 'Depreciação, Amortização e Exaustão')}}
        bpa = {('', '2025-12-31'): {'1.01.01': conta(100), '1.01.02': conta(50)}}
        bpp = {('', '2025-12-31'): {'2.01.04': conta(80, 'Empréstimos e Financiamentos'),
                                    '2.02.01': conta(220, 'Empréstimos e Financiamentos'),
                                    '2.03': conta(1000, 'Patrimônio Líquido Consolidado')}}
        vazio = {'con': {}, 'ind': {}}
        return {'DRE': {'con': dre, 'ind': {}}, 'DVA': {'con': dva, 'ind': {}}, 'BPA': {'con': bpa, 'ind': {}},
                'BPP': {'con': bpp, 'ind': {}}, 'DFC_MI': vazio}

    def test_multiplos(self):
        # lucro 200, 100 ações (LPA 2), preço 20 -> valor de mercado 2000; P/L 10; P/VP 2
        acoes = {'total': 100.0, 'tesouraria': 0.0, 'ordinarias': 100.0, 'preferenciais': 0.0, 'dt_refer': '2025-12-31'}
        r = I.calcular(self.saida(), {'moeda': 'REAL'}, {'valor': 20.0, 'data': '2026-01-02'}, acoes)
        v = r['valores']
        self.assertAlmostEqual(v['p_l']['valor'], 10.0)
        self.assertAlmostEqual(v['p_vp']['valor'], 2.0)
        self.assertAlmostEqual(v['ebitda_12m']['valor'], 350.0)  # EBIT 300 + D&A 50 (módulo)
        self.assertAlmostEqual(v['divida_liquida']['valor'], 150.0)  # 300 - 150
        self.assertAlmostEqual(v['ev_ebitda']['valor'], (2000 + 150) / 350)

    def test_acoes_em_milhares_sao_detectadas(self):
        acoes = {'total': 0.1, 'tesouraria': 0.0, 'ordinarias': 0.1, 'preferenciais': 0.0, 'dt_refer': '2025-12-31'}
        fator, _ = I.fator_acoes(self.saida()['DRE']['con'], acoes['total'])
        self.assertEqual(fator, 1000)

    def test_lucro_negativo_nao_gera_pl(self):
        s = self.saida()
        s['DRE']['con'][('2025-01-01', '2025-12-31')]['3.11.01'] = conta(-5, 'Atribuído a Sócios da Empresa Controladora')
        s['DRE']['con'][('2025-01-01', '2025-12-31')]['3.99.01.01'] = conta(-0.05, 'ON')
        acoes = {'total': 100.0, 'tesouraria': 0.0, 'ordinarias': 100.0, 'preferenciais': 0.0, 'dt_refer': '2025-12-31'}
        r = I.calcular(s, {'moeda': 'REAL'}, {'valor': 20.0, 'data': '2026-01-02'}, acoes)
        self.assertNotIn('p_l', r['valores'])

    def test_escala_de_acoes_absurda_suprime_multiplos(self):
        # 100 ações a R$ 20 contra lucro de 200 e PL de 1000 dá P/VP 2; com 1e9 ações o P/VP vira 20 milhões
        acoes = {'total': 1e12, 'tesouraria': 0.0, 'ordinarias': 1e12, 'preferenciais': 0.0, 'dt_refer': '2025-12-31'}
        r = I.calcular(self.saida(), {'moeda': 'REAL'}, {'valor': 20.0, 'data': '2026-01-02'}, acoes)
        self.assertNotIn('p_l', r['valores'])
        self.assertNotIn('p_vp', r['valores'])
        self.assertTrue(any('inconsistente' in a for a in r['avisos']))

    def test_crescimento_exige_anos_consecutivos(self):
        s = self.saida()
        # exercício de 2023 ausente: 2022 e 2025 não podem virar "crescimento do último ano"
        dre = s['DRE']['con']
        dre[('2022-01-01', '2022-12-31')] = {'3.01': conta(500), '3.11.01': conta(50, 'Atribuído a Sócios da Empresa Controladora')}
        acoes = {'total': 100.0, 'tesouraria': 0.0, 'ordinarias': 100.0, 'preferenciais': 0.0, 'dt_refer': '2025-12-31'}
        r = I.calcular(s, {'moeda': 'REAL'}, {'valor': 20.0, 'data': '2026-01-02'}, acoes)
        self.assertNotIn('crescimento_receita_ultimo_ano', r['valores'])


class TesteConferencia(unittest.TestCase):
    def test_beta_de_serie_proporcional(self):
        base = [100.0]
        r = [0.01, -0.02, 0.015, 0.0, 0.02, -0.01] * 20
        for x in r:
            base.append(base[-1] * math.exp(x))
        ibov = [[f'd{i}', p] for i, p in enumerate(base)]
        # ativo com o dobro do retorno do índice => beta 2 e volatilidade 2x a do índice
        a = [100.0]
        for x in r:
            a.append(a[-1] * math.exp(2 * x))
        acao = [[f'd{i}', p] for i, p in enumerate(a)]
        b, v = conferir.beta_vol(acao, ibov, janela=90)
        self.assertAlmostEqual(b, 2.0, places=6)
        _, v_i = conferir.beta_vol(ibov, ibov, janela=90)
        self.assertAlmostEqual(v / v_i, 2.0, places=6)

class TesteRegras(unittest.TestCase):
    pol = R.parametros({})

    def test_mediana_ignora_antiga_excluida_e_moeda(self):
        hoje = dt.date(2026, 10, 5)
        base = {'situacao': 'verificada', 'rating': 'compra', 'moeda': 'R$', 'fonte': 'InfoMoney'}
        casas = [
            {**base, 'casa': 'A', 'preco_alvo': 10, 'data': '2026-09-01'},
            {**base, 'casa': 'B', 'preco_alvo': 20, 'data': '2026-08-01'},
            {**base, 'casa': 'C', 'preco_alvo': 30, 'data': '2026-08-01', 'contar_no_consenso': False},
            {**base, 'casa': 'D', 'preco_alvo': 99, 'data': '2025-01-01'},
            {**base, 'casa': 'E', 'preco_alvo': 50, 'data': '2026-08-01', 'moeda': 'US$'},
            {**base, 'casa': 'F', 'preco_alvo': 70, 'data': '2026-08-01', 'situacao': 'nao verificada'},
        ]
        m, n, _ = R.mediana_alvos(casas, hoje, self.pol)
        self.assertEqual((m, n), (15, 2))

    def test_politica_de_fontes_exclui_da_contagem_e_da_mediana(self):
        pol = R.parametros({'politica_fontes': {'fontes_fora_da_contagem_de_casas': ['Money Times'], 'casas_fora_da_contagem': ['UBS']}})
        casas = [{'casa': 'A', 'rating': 'compra', 'situacao': 'verificada', 'fonte': 'Money Times', 'preco_alvo': 10, 'data': '2026-09-01'},
                 {'casa': 'UBS', 'rating': 'neutro', 'situacao': 'verificada', 'fonte': 'InfoMoney', 'preco_alvo': 10, 'data': '2026-09-01'},
                 {'casa': 'B', 'rating': 'venda', 'situacao': 'verificada', 'fonte': 'InfoMoney', 'preco_alvo': 8, 'data': '2026-09-01'}]
        self.assertEqual(R.contagem_ratings(casas, pol)['n_casas'], 1)
        self.assertEqual(R.mediana_alvos(casas, dt.date(2026, 10, 5), pol)[:2], (8, 1))

    def test_upside_ajustado_so_desconta_retorno_positivo(self):
        self.assertEqual(R.upside_ajustado(20.0, 10.0, 8.0, self.pol), 11.0)   # 15 - 4
        self.assertEqual(R.upside_ajustado(20.0, 10.0, -5.0, self.pol), 15.0)  # queda não desconta
        self.assertEqual(R.upside_ajustado(16.3, None, 2.79, self.pol), 14.9)  # só o alvo da XP
        self.assertIsNone(R.upside_ajustado(None, None, 3.0, self.pol))

    def test_corte_de_compra_informado_ou_derivado(self):
        rk = [{'nota': 6.0, 'acao_sugerida': 'comprar'}, {'nota': 5.7, 'acao_sugerida': 'aguardar'}, {'nota': 4.0, 'acao_sugerida': 'evitar'}]
        self.assertEqual(R.corte_de_compra(rk, {'parametros': {'corte_compra': 5.8}}), 5.8)
        self.assertEqual(R.corte_de_compra(rk, {}), 5.85)
        self.assertIsNone(R.corte_de_compra([{'nota': 4, 'acao_sugerida': 'evitar'}], {}))

    def test_nota_e_upside(self):
        pesos = {'a': 0.6, 'b': 0.4}
        self.assertEqual(R.nota({'a': 5, 'b': 7.5}, pesos), 6.0)
        self.assertEqual(R.upside(110, 100), 10.0)


class TesteValuation(unittest.TestCase):
    prem = {'horizonte_anos': 5, 'roe_minimo': 0.04, 'roe_maximo': 0.35, 'fracao_max_crescimento_sobre_roe': 0.9,
            'cenarios': {'bear': {'ke': 0.17, 'g_terminal': 0.035, 'delta_g_curto': -0.03, 'fator_lucro': 0.85},
                         'base': {'ke': 0.15, 'g_terminal': 0.05, 'delta_g_curto': 0.0, 'fator_lucro': 1.0},
                         'bull': {'ke': 0.13, 'g_terminal': 0.06, 'delta_g_curto': 0.02, 'fator_lucro': 1.10}},
            'grade': {'ke': [0.13, 0.15], 'g_terminal': [0.03, 0.05]}}

    def test_sem_crescimento_vale_lucro_sobre_ke(self):
        # g = 0: payout 100%, perpetuidade simples L / ke
        v = V.valor_patrimonio(100.0, 0.2, 0.10, 0.0, 0.0, anos=5)
        self.assertAlmostEqual(v, 1000.0, places=6)

    def test_pvp_justificado_de_gordon(self):
        # crescimento constante g com ROE: valor = L (1 - g/ROE)(1+g)/(ke - g) para g curto = g final, horizonte longo
        l0, roe, ke, g = 100.0, 0.20, 0.15, 0.05
        v = V.valor_patrimonio(l0, roe, ke, g, g, anos=5)
        esperado = l0 * (1 - g / roe) * (1 + g) / (ke - g)
        self.assertAlmostEqual(v, esperado, places=6)

    def test_ke_implicito_fecha_o_ciclo(self):
        v = V.valor_patrimonio(100.0, 0.2, 0.13, 0.08, 0.05)
        ki = V.ke_implicito(v, 100.0, 0.2, 0.08, 0.05)
        self.assertAlmostEqual(ki, 0.13, places=4)

    def test_g_implicito_fecha_o_ciclo(self):
        v = V.valor_patrimonio(100.0, 0.2, 0.15, 0.06, 0.06)
        gi = V.g_implicito(v, 100.0, 0.2, 0.15)
        self.assertAlmostEqual(gi, 0.06, places=4)

    def test_entradas_invalidas_nao_geram_valor(self):
        self.assertIsNone(V.valor_patrimonio(-5.0, 0.2, 0.15, 0.05, 0.05))
        self.assertIsNone(V.valor_patrimonio(100.0, 0.2, 0.05, 0.05, 0.05))  # ke <= g

    def test_cenarios_em_ordem_e_preco_por_acao(self):
        perfil = {'ciclica': False, 'g_curto': 0.07}
        hist = [{'roe_pct': 18.0, 'lucro_liquido': 90.0}]
        out = V.avaliar(100.0, hist, 20.0, 1000.0, 10.0, 2.0, perfil, self.prem)
        c = out['cenarios']
        self.assertLess(c['bear']['valor_justo_por_acao'], c['base']['valor_justo_por_acao'])
        self.assertLess(c['base']['valor_justo_por_acao'], c['bull']['valor_justo_por_acao'])
        # valor por ação = preço x valor do modelo / valor de mercado
        self.assertAlmostEqual(c['base']['valor_justo_por_acao'], 10.0 * c['base']['valor_patrimonio'] / 1000.0)

    def test_ciclica_usa_media_de_anos(self):
        hist = [{'lucro_liquido': 10.0}, {'lucro_liquido': 30.0}]
        self.assertEqual(V.lucro_normalizado(20.0, hist, True), 20.0)
        self.assertEqual(V.lucro_normalizado(50.0, hist, False), 50.0)


class TesteLucroSemDivisao(unittest.TestCase):
    def test_controladores_zerado_usa_consolidado(self):
        # caso real (Sabesp): 3.11.01 e 3.11.02 vêm zerados com 3.11 preenchido
        contas = {'3.11': conta(8462, 'Lucro/Prejuízo Consolidado do Período'),
                  '3.11.01': conta(0, 'Atribuído a Sócios da Empresa Controladora'),
                  '3.11.02': conta(0, 'Atribuído a Sócios Não Controladores')}
        self.assertEqual(I.lucro_liquido(contas), ('3.11', 8462))

    def test_divisao_preenchida_prevalece(self):
        contas = {'3.11': conta(100, 'Lucro/Prejuízo Consolidado do Período'),
                  '3.11.01': conta(80, 'Atribuído a Sócios da Empresa Controladora'),
                  '3.11.02': conta(20, 'Atribuído a Sócios Não Controladores')}
        self.assertEqual(I.lucro_liquido(contas), ('3.11.01', 80))


if __name__ == '__main__':
    unittest.main()
