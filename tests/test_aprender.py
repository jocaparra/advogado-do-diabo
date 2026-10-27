"""Testes do aprendizado conservador de pesos (offline, observações sintéticas)."""
import datetime as dt
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import aprender as L  # noqa: E402

PESOS = {'catalisadores': 0.25, 'noticias': 0.20, 'momentum': 0.20, 'macro_eleicao': 0.20, 'valuation_upside': 0.15}


def obs_sinteticas(semanas, por_semana=6, sinal='momentum'):
    """`sinal` determina o excesso; os demais componentes são ruído determinístico."""
    out = []
    for s in range(semanas):
        data = (dt.date(2026, 1, 5) + dt.timedelta(days=7 * s)).isoformat()
        for i in range(por_semana):
            comp = {c: float((i * 3 + j * 5 + s) % 10) for j, c in enumerate(L.COMPONENTES)}
            comp[sinal] = float(i)
            out.append({'semana': data, 'ticker': f'T{i}', 'posicao': i, 'nota': 5, 'acao': 'aguardar', 'certeza': 'baixa',
                        'retorno_pct': 0, 'ibovespa_pct': 0, 'excesso_pp': comp[sinal] * 1.5 - 4, 'veredito': 'neutro_confirmado',
                        'componentes': comp})
    return out


class TestePortao(unittest.TestCase):
    def test_fechado_com_pouca_amostra_nao_propoe(self):
        p = L.propor(obs_sinteticas(1, 6), PESOS)
        self.assertEqual(p['status'], 'portao_fechado')
        self.assertNotIn('pesos_propostos', p)

    def test_observacoes_sem_componentes_nao_contam(self):
        obs = obs_sinteticas(10, 6)
        for o in obs:
            o['componentes'] = None
        self.assertFalse(L.portao(obs)['aberto'])

    def test_portao_exige_semanas_e_observacoes(self):
        self.assertFalse(L.portao(obs_sinteticas(5, 10))['aberto'])    # 50 obs, 5 semanas
        self.assertFalse(L.portao(obs_sinteticas(10, 2))['aberto'])    # 20 obs, 10 semanas
        self.assertTrue(L.portao(obs_sinteticas(10, 6))['aberto'])     # 60 obs, 10 semanas


class TesteProposta(unittest.TestCase):
    def test_proposta_dentro_dos_limites_e_valida_fora_da_amostra(self):
        p = L.propor(obs_sinteticas(12, 6, 'momentum'), PESOS, hoje=dt.date(2026, 4, 1))
        self.assertEqual(p['status'], 'proposta', p)
        self.assertAlmostEqual(sum(p['pesos_propostos'].values()), 1.0, places=3)
        for c in L.COMPONENTES:
            self.assertLessEqual(abs(p['delta'][c]), L.MAX_DELTA + 0.01)
            self.assertGreaterEqual(p['pesos_propostos'][c], L.PISO_PESO - 1e-6)
        self.assertGreater(p['pesos_propostos']['momentum'], PESOS['momentum'])   # sinal real ganha peso
        self.assertTrue(set(p['validacao']['semanas_treino']).isdisjoint(p['validacao']['semanas_teste']))
        self.assertGreaterEqual(p['validacao']['ganho'], L.MARGEM_TESTE)

    def test_resultado_atipico_isolado_nao_gera_proposta(self):
        # uma única semana extrema no meio de ruído não pode abrir proposta por si só
        obs = obs_sinteticas(10, 6, 'momentum')
        for o in obs:
            o['excesso_pp'] = 0.0 + (o['componentes']['noticias'] % 3) * 0.0   # sem relação com componente algum
        p = L.propor(obs, PESOS)
        self.assertNotEqual(p['status'], 'proposta')


class TesteVersoes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.arq = os.path.join(self.tmp.name, 'parametros.json')
        self.obs = obs_sinteticas(12, 6, 'momentum')
        self.dados = L.carregar_versoes(self.arq)
        self.dados['versoes'][0]['parametros']['pesos'] = dict(PESOS)

    def tearDown(self):
        self.tmp.cleanup()

    def _proposta(self):
        L._salvar(self.dados, self.arq)
        return L.propor(self.obs, PESOS, hoje=dt.date(2026, 4, 1))

    def test_aplicar_exige_aprovacao_e_gera_versao_sem_apagar(self):
        p = self._proposta()
        with self.assertRaises(ValueError):
            L.aplicar(p, self.obs, 'modelo', arquivo=self.arq)
        n = L.aplicar(p, self.obs, 'usuario', hoje=dt.date(2026, 4, 1), arquivo=self.arq)
        d = L.carregar_versoes(self.arq)
        self.assertEqual((n['versao'], d['versao_atual'], len(d['versoes'])), (2, 2, 2))
        self.assertEqual(d['versoes'][0]['parametros']['pesos'], PESOS)       # baseline intacta

    def test_aplicar_recusa_portao_fechado_e_proposta_sobre_outra_versao(self):
        p = self._proposta()
        with self.assertRaises(ValueError):
            L.aplicar(p, obs_sinteticas(1, 6), 'usuario', arquivo=self.arq)
        L.aplicar(p, self.obs, 'usuario', arquivo=self.arq)
        with self.assertRaises(ValueError):                                    # mesma proposta, versão já mudou
            L.aplicar(p, self.obs, 'usuario', arquivo=self.arq)

    def test_reverter_cria_nova_versao_com_parametros_antigos(self):
        L.aplicar(self._proposta(), self.obs, 'usuario', arquivo=self.arq)
        r = L.reverter(1, arquivo=self.arq)
        d = L.carregar_versoes(self.arq)
        self.assertEqual(r['versao'], 3)
        self.assertEqual(L.versao(d)['parametros']['pesos'], PESOS)
        self.assertEqual(len(d['versoes']), 3)
        with self.assertRaises(ValueError):
            L.reverter(3, arquivo=self.arq)

    def test_verificar_detecta_regressao_e_recomenda_rollback(self):
        L.aplicar(self._proposta(), self.obs, 'usuario', hoje=dt.date(2026, 1, 1), arquivo=self.arq)
        # uma proposta real muda no máximo +-5 pp por peso e quase nunca cruza a tolerância; para exercitar
        # a detecção, a versão aplicada é trocada por pesos extremos concentrados em um componente
        d = L.carregar_versoes(self.arq)
        d['versoes'][-1]['parametros']['pesos'] = {c: (0.96 if c == 'momentum' else 0.01) for c in L.COMPONENTES}
        L._salvar(d, self.arq)
        # depois da aplicação o sinal passa a ser OUTRO componente: os pesos novos pioram o ranking
        pos = obs_sinteticas(6, 6, 'valuation_upside')
        for o in pos:
            o['excesso_pp'] = -o['componentes']['momentum']
        r = L.verificar(pos, arquivo=self.arq)
        self.assertEqual(r['status'], 'regressao', r)
        self.assertEqual(r['recomendacao'], 'reverter --para 1')

    def test_verificar_sem_semanas_suficientes(self):
        L.aplicar(self._proposta(), self.obs, 'usuario', hoje=dt.date(2027, 1, 1), arquivo=self.arq)
        self.assertEqual(L.verificar(self.obs, arquivo=self.arq)['status'], 'amostra_insuficiente')


class TesteArquivoDeProposta(unittest.TestCase):
    def test_proposta_salva_e_relida_com_o_mesmo_conteudo(self):
        import json
        p = L.propor(obs_sinteticas(12, 6, 'momentum'), PESOS, hoje=dt.date(2026, 4, 1))
        self.assertEqual(p['status'], 'proposta')
        with tempfile.TemporaryDirectory() as tmp:
            antigo, L.PASTA = L.PASTA, tmp
            try:
                caminho = L._salvar_proposta(p)
            finally:
                L.PASTA = antigo
            self.assertTrue(caminho.endswith(p['id'] + '.json'))
            with open(caminho, encoding='utf-8') as f:
                self.assertEqual(json.load(f)['pesos_propostos'], p['pesos_propostos'])


class TesteFase(unittest.TestCase):
    def test_hoje_e_fase_1_e_estima_o_que_falta(self):
        f = L.fase([], semanas_historico=1, semanas_com_componentes=0, horizonte='4_semanas')
        self.assertEqual(f['fase_atual'], 1)
        self.assertFalse(f['fase_2']['liberada'])
        self.assertEqual(f['fase_2']['semanas_restantes_estimadas'], L.A.MIN_SEMANAS + 4)

    def test_horizonte_mais_curto_chega_a_fase_2_antes(self):
        curto = L.fase([], 1, 0, horizonte='1_semana')['fase_2']['semanas_restantes_estimadas']
        longo = L.fase([], 1, 0, horizonte='4_semanas')['fase_2']['semanas_restantes_estimadas']
        self.assertEqual((curto, longo), (L.A.MIN_SEMANAS + 1, L.A.MIN_SEMANAS + 4))
        self.assertEqual(L.HORIZONTE, '1_semana')

    def test_fase_2_liberada_com_amostra_minima_e_fase_3_nao(self):
        f = L.fase(obs_sinteticas(10, 6), semanas_historico=14, semanas_com_componentes=14)
        self.assertEqual(f['fase_atual'], 2)
        self.assertTrue(f['fase_2']['liberada'])
        self.assertFalse(f['fase_3']['liberada'])
        self.assertEqual(f['fase_2']['semanas_restantes_estimadas'], 0)
        self.assertGreater(f['fase_3']['semanas_restantes_estimadas'], 0)

    def test_fase_3_exige_muito_mais(self):
        f = L.fase(obs_sinteticas(60, 14), semanas_historico=64, semanas_com_componentes=64)
        self.assertEqual(f['fase_atual'], 3)


class TestePadroes(unittest.TestCase):
    def test_correlacao_por_componente_reflete_o_sinal(self):
        p = L.padroes(obs_sinteticas(10, 6, 'momentum'))
        self.assertGreater(p['componentes']['momentum']['rho_medio'], 0.9)
        self.assertEqual(p['componentes']['momentum']['semanas'], 10)
        self.assertEqual(p['erros_recorrentes'], {})
        self.assertTrue(p['portao']['aberto'])

    def test_sem_dados_nao_inventa(self):
        p = L.padroes([])
        self.assertEqual(p['componentes'], {})
        self.assertFalse(p['portao']['aberto'])


class TesteEntradasInvalidas(unittest.TestCase):
    def test_propor_recusa_pesos_incompletos_sem_quebrar(self):
        p = L.propor(obs_sinteticas(12, 6), {'momentum': 1.0})
        self.assertEqual(p['status'], 'pesos_invalidos')
        self.assertEqual(L.propor(obs_sinteticas(12, 6), None)['status'], 'pesos_invalidos')

    def test_erros_recorrentes_ignora_observacao_sem_veredito(self):
        self.assertEqual(L.erros_recorrentes([{'semana': 's', 'ticker': 'T'}]), {})


class TesteErrosRecorrentes(unittest.TestCase):
    def _obs(self, tickers, semanas, erra):
        return [{'semana': f'2026-{1 + s // 4:02d}-{1 + (s % 4) * 7:02d}', 'ticker': t,
                 'veredito': 'oportunidade_perdida' if erra(t, s) else 'neutro_confirmado'}
                for t in tickers for s in range(semanas)]

    def test_so_aparece_quem_erra_muito_mais_que_os_outros(self):
        tk = ['AAA3', 'BBB3', 'CCC3', 'DDD3', 'EEE3', 'FFF3']
        # AAA3 erra em 17 de 20 semanas; os demais erram de vez em quando (~10%)
        o = self._obs(tk, 20, lambda t, s: (t == 'AAA3' and s % 7 != 0) or (t != 'AAA3' and s % 10 == 3))
        self.assertEqual(list(L.erros_recorrentes(o)), ['AAA3'])

    def test_erro_aleatorio_espalhado_nao_e_recorrente(self):
        # todos erram ~20% das semanas, o que não distingue nenhum papel
        tk = [f'T{i}' for i in range(14)]
        o = self._obs(tk, 37, lambda t, s: (s * 7 + int(t[1:]) * 3) % 5 == 0)
        self.assertEqual(L.erros_recorrentes(o), {})

    def test_exige_semanas_distintas_e_nao_quebra_sem_dados(self):
        tk = ['AAA3', 'BBB3', 'CCC3', 'DDD3']
        o = self._obs(tk, 12, lambda t, s: False)
        o += [{'semana': '2026-06-01', 'ticker': 'ZZZ3', 'veredito': 'erro'}] * 8   # 8 erros, 1 semana só
        self.assertEqual(L.erros_recorrentes(o), {})
        self.assertEqual(L.erros_recorrentes([]), {})


if __name__ == '__main__':
    unittest.main()


class TesteValidacaoDaProposta(unittest.TestCase):
    """Auditoria: a proposta é um JSON editável; `aplicar` não pode confiar nele às cegas."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.arq = os.path.join(self.tmp.name, 'parametros.json')
        self.obs = obs_sinteticas(10, 6)
        self.dados = {'versao_atual': 1, 'versoes': [{'versao': 1, 'criado_em': 'x', 'parametros': {'pesos': PESOS}, 'motivo': 'baseline',
                                                      'aprovado_por': 'baseline', 'evidencia': None, 'aplicada_a_partir_de': None}]}
        L._salvar(self.dados, self.arq)
        self.p = L.propor(self.obs, PESOS, hoje=dt.date(2026, 4, 1))
        self.assertEqual(self.p['status'], 'proposta')

    def _recusa(self, p):
        def bytes_do_arquivo():
            with open(self.arq, 'rb') as f:
                return f.read()
        antes = bytes_do_arquivo()
        with self.assertRaises(ValueError):
            L.aplicar(p, self.obs, 'usuario', arquivo=self.arq)
        self.assertEqual(bytes_do_arquivo(), antes)   # recusa não toca no arquivo de versões

    def test_proposta_legitima_passa(self):
        L.validar_proposta(self.p)

    def test_pesos_editados_a_mao_sao_recusados(self):
        p = dict(self.p, pesos_propostos=dict(self.p['pesos_propostos'], momentum=0.60))
        self._recusa(p)

    def test_mudanca_acima_do_limite_e_recusada_mesmo_com_id_coerente(self):
        import hashlib
        import json
        novos = dict(PESOS, momentum=0.40, noticias=0.0)
        p = dict(self.p, pesos_propostos=novos, id='p20260401_' + hashlib.sha256(json.dumps(novos, sort_keys=True).encode()).hexdigest()[:8])
        self._recusa(p)

    def test_pesos_que_nao_somam_um_ou_nao_finitos_sao_recusados(self):
        self._recusa(dict(self.p, pesos_propostos={c: 0.3 for c in L.COMPONENTES}))
        self._recusa(dict(self.p, pesos_propostos=dict(self.p['pesos_propostos'], momentum=float('nan'))))
        self._recusa(dict(self.p, pesos_propostos={'momentum': 1.0}))

    def test_ganho_inflado_ou_ausente_e_recusado(self):
        self._recusa(dict(self.p, validacao=dict(self.p['validacao'], ganho=0.0)))
        self._recusa({k: v for k, v in self.p.items() if k != 'validacao'})

    def test_id_adulterado_e_recusado(self):
        self._recusa(dict(self.p, id='p20260401_deadbeef'))

    def test_proposta_que_nao_e_dict_ou_sem_ganho_e_recusada(self):
        for ruim in (None, [], 'x', {'status': 'sem_ganho'}):
            with self.assertRaises(ValueError):
                L.validar_proposta(ruim)

    def test_aplicacao_recusada_nao_corrompe_e_rollback_restaura_exatamente(self):
        self._recusa(dict(self.p, id='p20260401_deadbeef'))
        L.aplicar(self.p, self.obs, 'usuario', hoje=dt.date(2026, 4, 1), arquivo=self.arq)
        L.reverter(1, arquivo=self.arq)
        d = L.carregar_versoes(self.arq)
        self.assertEqual(L.versao(d)['parametros'], d['versoes'][0]['parametros'])
        self.assertEqual([v['versao'] for v in d['versoes']], [1, 2, 3])     # nada apagado
        self.assertEqual(d['versoes'][1]['parametros']['pesos'], self.p['pesos_propostos'])
        self.assertEqual(d['versao_atual'], 3)


class TesteLimitesDosCandidatos(unittest.TestCase):
    def test_nenhum_peso_passa_do_delta_maximo_e_a_soma_fecha(self):
        for sinal in L.COMPONENTES:
            cand, _ = L.candidatos(obs_sinteticas(10, 6, sinal=sinal), PESOS)
            self.assertAlmostEqual(sum(cand.values()), 1.0, delta=1e-3)
            for c in L.COMPONENTES:
                self.assertLessEqual(abs(cand[c] - PESOS[c]), L.MAX_DELTA + 1e-3, (sinal, c))
                self.assertGreaterEqual(cand[c], L.PISO_PESO - 1e-9)
