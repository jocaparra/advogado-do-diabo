"""Testes da avaliação das recomendações contra o Ibovespa (offline, séries sintéticas)."""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import avaliar as A  # noqa: E402


def serie(inicio, dias, valor0, passo):
    d0 = dt.date.fromisoformat(inicio)
    return [[(d0 + dt.timedelta(days=i)).isoformat(), round(valor0 * (1 + passo) ** i, 6)] for i in range(dias)]


class TesteSpearman(unittest.TestCase):
    def test_monotono(self):
        self.assertAlmostEqual(A.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(A.spearman([1, 2, 3, 4], [40, 30, 20, 10]), -1.0)

    def test_empates_e_amostra_curta(self):
        self.assertIsNone(A.spearman([1, 2], [1, 2]))
        self.assertIsNone(A.spearman([1, 1, 1], [1, 2, 3]))


class TesteAvaliacao(unittest.TestCase):
    def monta(self, tmp, hoje_dias=200):
        # Ibovespa sobe 0,1% ao dia; AAA sobe 0,3% ao dia; BBB cai 0,1% ao dia
        s = {'^BVSP': serie('2026-01-01', hoje_dias, 100000, 0.001), 'AAA3': serie('2026-01-01', hoje_dias, 10, 0.003),
             'BBB3': serie('2026-01-01', hoje_dias, 10, -0.001)}
        pasta = os.path.join(tmp, 'semana_20260601')
        os.makedirs(pasta)
        with open(os.path.join(pasta, 'precos.json'), 'w') as f:
            json.dump({'ibovespa': {'serie': s['^BVSP']}, 'acoes': {t: {'serie': s[t]} for t in ('AAA3', 'BBB3')}}, f)
        d0 = '2026-02-01'
        px = {t: dict(serie_) for t, serie_ in ((k, s[k]) for k in s)}
        sem = {'data': d0, 'ranking': [
            {'posicao': 1, 'ticker': 'AAA3', 'nota': 7, 'acao_sugerida': 'comprar', 'certeza': 'alta', 'preco_atual': px['AAA3'][d0], 'data_cotacao': d0},
            {'posicao': 2, 'ticker': 'BBB3', 'nota': 3, 'acao_sugerida': 'evitar', 'certeza': 'média', 'preco_atual': px['BBB3'][d0], 'data_cotacao': d0}]}
        with open(os.path.join(tmp, 'historico_carteira.json'), 'w') as f:
            json.dump({'semanas': [sem]}, f)

    def test_excesso_e_agregacao(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.monta(tmp)
            r = A.avaliar(tmp, hoje=dt.date(2026, 7, 1))
            h4 = r['horizontes']['4_semanas']
            self.assertEqual(h4['observacoes'], 2)
            comprar = h4['por_acao']['comprar']
            evitar = h4['por_acao']['evitar']
            esperado_a = ((1.003 ** 28) - (1.001 ** 28)) * 100
            self.assertAlmostEqual(comprar['excesso_medio_pp'], esperado_a, delta=0.05)
            self.assertLess(evitar['excesso_medio_pp'], 0)
            self.assertGreater(h4['spread_comprar_menos_evitar_pp'], 0)
            self.assertEqual(h4['amostra'], 'insuficiente')  # 2 observações: sem conclusão

    def test_horizonte_nao_vencido_fica_pendente(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.monta(tmp)
            r = A.avaliar(tmp, hoje=dt.date(2026, 2, 20))  # 19 dias depois
            self.assertEqual(r['horizontes']['4_semanas']['observacoes'], 0)
            self.assertEqual(r['horizontes']['4_semanas']['pendentes'], 2)

    def test_sem_futuro_nos_precos_nao_inventa(self):
        # hoje é depois do horizonte, mas a série termina antes: continua pendente
        with tempfile.TemporaryDirectory() as tmp:
            self.monta(tmp, hoje_dias=40)  # série vai até 2026-02-09
            r = A.avaliar(tmp, hoje=dt.date(2026, 7, 1))
            self.assertEqual(r['horizontes']['4_semanas']['observacoes'], 0)
            self.assertEqual(r['horizontes']['4_semanas']['pendentes'], 2)

    def test_desdobramento_posterior_nao_gera_retorno_falso(self):
        # preço gravado era nominal da época (100); a série atual está ajustada por split 5:1 (20 em todo o período)
        ibov = {(dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat(): 100000.0 for i in range(120)}
        acao = {k: 20.0 for k in ibov}
        sem = {'data': '2026-02-02', 'ranking': [{'posicao': 1, 'ticker': 'XXXX3', 'nota': 7, 'acao_sugerida': 'comprar',
                                                  'certeza': 'alta', 'preco_atual': 100.0, 'data_cotacao': '2026-02-02'}]}
        obs, _ = A.avaliar_entradas([sem], {'XXXX3': acao, '^BVSP': ibov}, dt.date(2026, 6, 1))
        self.assertAlmostEqual(obs['4_semanas'][0]['retorno_pct'], 0.0, places=6)

    def test_veredito_por_direcao_e_banda(self):
        self.assertEqual(A.veredito('acima', 0.5, 6), 'acerto')
        self.assertEqual(A.veredito('acima', -0.5, 6), 'erro')
        self.assertEqual(A.veredito('abaixo', -5, 6), 'acerto')
        self.assertEqual(A.veredito('abaixo', 1, 6), 'erro')
        self.assertEqual(A.veredito('neutra', 5.9, 6), 'neutro_confirmado')
        self.assertEqual(A.veredito('neutra', 13, 6), 'oportunidade_perdida')
        self.assertEqual(A.veredito('neutra', -7, 6), 'queda_evitada')
        self.assertEqual(A.veredito(None, 1, 6), 'inconclusivo')

    def test_horizonte_de_uma_semana_e_marcacao_por_previsao(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.monta(tmp)
            r = A.avaliar(tmp, hoje=dt.date(2026, 7, 1))
            h1 = r['horizontes']['1_semana']
            self.assertEqual(h1['observacoes'], 2)
            self.assertEqual(h1['por_veredito'], {'acerto': 2})  # AAA3 comprar sobe, BBB3 evitar cai
            self.assertEqual(h1['acerto_direcional_pct'], 100.0)
            obs = {o['ticker']: o for o in r['observacoes']['1_semana']}
            self.assertEqual(obs['AAA3']['direcao_esperada'], 'acima')
            self.assertEqual(obs['BBB3']['direcao_esperada'], 'abaixo')

    def test_spearman_por_componente_usa_componentes_gravados(self):
        obs = [{'semana': 's', 'ticker': t, 'posicao': i, 'nota': 5, 'acao': 'aguardar', 'certeza': 'baixa', 'retorno_pct': 0,
                'ibovespa_pct': 0, 'excesso_pp': ex, 'veredito': 'neutro_confirmado', 'componentes': {'momentum': m}}
               for i, (t, ex, m) in enumerate([('A', 1, 2), ('B', 2, 5), ('C', 3, 9), ('D', 4, 9.5)])]
        ag = A.agregar(obs)
        self.assertAlmostEqual(ag['spearman_por_componente']['momentum']['spearman_medio'], 1.0)
        self.assertNotIn('noticias', ag['spearman_por_componente'])  # sem dado, não inventa

    def test_linha_malformada_nao_derruba_a_avaliacao(self):
        ibov = {(dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat(): 100000.0 + i for i in range(120)}
        acao = {k: 10.0 + i * 0.01 for i, k in enumerate(ibov)}
        base = {'posicao': 1, 'ticker': 'AAA3', 'nota': 7, 'acao_sugerida': 'comprar', 'certeza': 'alta',
                'preco_atual': 10.3, 'data_cotacao': '2026-02-01'}
        quebradas = [{k: v for k, v in base.items() if k != faltando} for faltando in ('posicao', 'nota', 'acao_sugerida', 'ticker')]
        quebradas.append({**base, 'data_cotacao': 12345})
        sem = {'data': '2026-02-01', 'ranking': quebradas + [base]}
        obs, _ = A.avaliar_entradas([sem, {'data': '2026-02-01'}], {'AAA3': acao, '^BVSP': ibov}, dt.date(2026, 6, 1))
        self.assertEqual(len(obs['4_semanas']), 1)        # só a linha íntegra
        self.assertEqual(obs['4_semanas'][0]['certeza'], 'alta')

    def test_preco_zero_ou_nan_nao_gera_retorno(self):
        ibov = {(dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat(): 100000.0 for i in range(120)}
        sem = {'data': '2026-02-01', 'ranking': [{'posicao': 1, 'ticker': 'ZZZ3', 'nota': 7, 'acao_sugerida': 'comprar',
                                                  'certeza': 'alta', 'preco_atual': 10.0, 'data_cotacao': '2026-02-01'}]}
        for ruim in (0.0, float('nan')):
            serie_ruim = {k: ruim for k in ibov}
            obs, _ = A.avaliar_entradas([sem], {'ZZZ3': serie_ruim, '^BVSP': ibov}, dt.date(2026, 6, 1))
            self.assertEqual(sum(len(v) for v in obs.values()), 0)

    def test_veredito_nao_finito_e_inconclusivo(self):
        self.assertEqual(A.veredito('neutra', float('nan'), 6), 'inconclusivo')
        self.assertEqual(A.veredito('acima', float('inf'), 6), 'inconclusivo')

    def test_tipos_trocados_e_semanas_invalidas_nao_quebram(self):
        ibov = {(dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat(): 100000.0 + i for i in range(120)}
        acao = {k: 10.0 + i * 0.01 for i, k in enumerate(ibov)}
        base = {'posicao': 1, 'ticker': 'AAA3', 'nota': 7, 'acao_sugerida': 'comprar', 'certeza': 'alta',
                'preco_atual': 10.3, 'data_cotacao': '2026-02-01'}
        ruins = [{**base, 'posicao': 'primeiro'}, {**base, 'nota': 'alta'}, {**base, 'acao_sugerida': 5},
                 {**base, 'ticker': 123}, {**base, 'nota': True}, 'texto', None, {**base, 'nota': float('nan')}]
        semanas = [None, 5, {'data': '2026-02-01', 'ranking': 'x'}, {'data': '2026-02-01', 'ranking': ruins + [base]}]
        obs, _ = A.avaliar_entradas(semanas, {'AAA3': acao, '^BVSP': ibov}, dt.date(2026, 6, 1))
        self.assertEqual(len(obs['4_semanas']), 1)
        A.agregar(obs['4_semanas'])                        # não pode levantar nem por tipos misturados


if __name__ == '__main__':
    unittest.main()


class TesteAcertoERoteamento(unittest.TestCase):
    """Regressões da auditoria: rótulo de acerto e cobertura de proventos."""

    def obs(self, acao, excesso, veredito):
        return {'semana': 's', 'ticker': 'X', 'posicao': 1, 'nota': 5, 'acao': acao, 'certeza': 'alta', 'retorno_pct': excesso,
                'proventos_pct': 0, 'ibovespa_pct': 0, 'excesso_pp': excesso, 'veredito': veredito, 'componentes': None}

    def test_evitar_que_caiu_e_acerto_nao_zero(self):
        r = A.agregar([self.obs('evitar', -5.0, 'acerto')])['por_acao']['evitar']
        self.assertEqual(r['acerto_pct'], 100.0)   # antes saía 0.0: era "% acima do Ibovespa"
        self.assertEqual(r['acima_ibov_pct'], 0.0)

    def test_aguardar_sem_previsao_direcional_nao_tem_acerto(self):
        r = A.agregar([self.obs('aguardar', 1.0, 'neutro_confirmado')])['por_acao']['aguardar']
        self.assertIsNone(r['acerto_pct'])

    def test_sem_cobertura_de_proventos_marca_incompleta(self):
        with tempfile.TemporaryDirectory() as tmp:
            TesteAvaliacao().monta(tmp)   # precos.json sem a chave `dividendos`
            r = A.avaliar(tmp, hoje=dt.date(2026, 7, 1))
            self.assertTrue(r['avaliacao_incompleta'])
            self.assertEqual(r['horizontes']['4_semanas']['proventos']['obs_sem_cobertura'], 2)
            self.assertFalse(r['observacoes']['4_semanas'][0]['proventos_completos'])

    def test_cobertura_vem_do_precos_json_e_do_sidecar_confirmado(self):
        with tempfile.TemporaryDirectory() as tmp:
            TesteAvaliacao().monta(tmp)
            pasta = os.path.join(tmp, 'semana_20260601')
            p = json.load(open(os.path.join(pasta, 'precos.json')))
            p['data_coleta'] = '2026-06-30 10:00:00'
            p['acoes']['AAA3']['dividendos'] = [['2026-02-10', 0.5]]
            json.dump(p, open(os.path.join(pasta, 'precos.json'), 'w'))
            json.dump({'por_ticker': {
                'BBB3': {'eventos': [['2026-02-15', 0.2]], 'coberto_ate': '2026-06-30', 'verificacao': {'status': 'confirmado'}},
                'CCC3': {'eventos': [['2026-02-15', 9.9]], 'coberto_ate': '2026-06-30', 'verificacao': {'status': 'divergente'}}}},
                open(os.path.join(pasta, 'proventos.json'), 'w'))
            divs, cob = A.carregar_proventos(tmp)
            self.assertEqual(cob['AAA3'], ('2026-06-30', ''))          # fonte única: cobre, mas não verificado
            self.assertEqual(cob['BBB3'], ('2026-06-30', '2026-06-30'))
            self.assertNotIn('CCC3', cob)                              # divergente não vale
            self.assertNotIn('CCC3', divs)
            r = A.avaliar(tmp, hoje=dt.date(2026, 7, 1))
            h = r['horizontes']['4_semanas']['proventos']
            self.assertEqual(h['obs_sem_cobertura'], 0)
            self.assertEqual(h['obs_fonte_unica'], 1)                  # AAA3
            self.assertFalse(r['avaliacao_incompleta'])
            ob = {o['ticker']: o for o in r['observacoes']['4_semanas']}
            self.assertGreater(ob['AAA3']['proventos_pct'], 0)
