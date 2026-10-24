"""Testes offline do servidor local da interface: leitura dos JSON da semana, segurança e rotina.

Tudo roda sobre uma raiz sintética em pasta temporária; nenhum dado real é lido ou gravado.
"""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import servidor as S  # noqa: E402

COMP = {'catalisadores': 5, 'noticias': 5, 'momentum': 5, 'macro_eleicao': 5, 'valuation_upside': 5}
SINTESE = {'data': '2030-01-07', 'ranking': [
    {'posicao': 1, 'ticker': 'AAAA3', 'setor': 'Energia', 'nota': 7.5, 'componentes': COMP, 'acao_sugerida': 'comprar',
     'certeza': 'alta', 'preco_atual': 10.0, 'data_cotacao': '2030-01-07', 'rating_xp': 'Compra',
     'gatilho_revisao': 'Rever se cair.', 'tese': 'tese de teste'},
    {'posicao': 2, 'ticker': 'BBBB4', 'setor': 'Financeiro', 'nota': 4.2, 'componentes': COMP, 'acao_sugerida': 'aguardar',
     'certeza': 'média', 'preco_atual': 20.0, 'data_cotacao': '2030-01-07', 'rating_xp': 'Compra'},
    {'posicao': 3, 'ticker': 'CCCC3', 'setor': 'Varejo', 'nota': None, 'componentes': COMP, 'acao_sugerida': None,
     'certeza': None, 'preco_atual': None, 'data_cotacao': None, 'rating_xp': None},
]}
DOSSIE = {'data': '2030-01-07', 'tickers': {'AAAA3': {
    'preco': 10.0,
    'indicadores': {'roe_12m': {'valor': 20.0, 'unidade': '%'}, 'p_l': {'valor': 8.0, 'unidade': 'x'}},
    'valuation': {'status': 'ok', 'ke_implicito_pct': 12.0, 'g_implicito_pct': 4.0, 'cenarios': {
        'bear': {'valor_justo_por_acao': 6.0, 'margem_pct': -40.0}, 'base': {'valor_justo_por_acao': 9.0, 'margem_pct': -10.0},
        'bull': {'valor_justo_por_acao': 14.0, 'margem_pct': 40.0}}},
    'checklist': [{'rotulo': 'Item A', 'valor': 'sim', 'fonte': 'CVM', 'data': '2030-01-01', 'status': 'preenchido'},
                  {'rotulo': 'Item B', 'valor': 'não verificado', 'fonte': None, 'data': None, 'status': 'pendente'}]}}}
CONTRA = {'escopo': 'top 2', 'objecoes': [
    {'ticker': 'AAAA3', 'objecao': 'fraca', 'forca': 'fraca', 'fonte': 'F1', 'data': '2030-01-05', 'tipo_alvo': 'x'},
    {'ticker': 'AAAA3', 'objecao': 'forte', 'forca': 'forte', 'fonte': 'F2', 'data': '2030-01-06', 'tipo_alvo': 'x'}]}
AUDITORIA = {'itens': [
    {'ticker': 'AAAA3', 'campo': 'preco', 'arquivo': 'precos.json', 'resultado': 'aprovado', 'motivo': 'ok'},
    {'ticker': 'AAAA3', 'campo': 'alvo', 'arquivo': 'casas.json', 'resultado': 'reprovado', 'motivo': 'errado', 'correcao': 'refeito'}]}
CONFERENCIA = {'itens': [{'ticker': 'AAAA3', 'severidade': 'aviso', 'regra': 'r', 'arquivo': 'a.json', 'mensagem': 'm'}]}
XP = {'data_relatorio': '2030-01-01', 'acoes': [{'ticker': 'AAAA3', 'rating': 'Compra', 'comentario_mes': 'comentário da XP'}]}


def gravar(caminho, obj):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(obj, f)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = self.tmp.name
        self.antes = (S.RAIZ, S.LANCADOR, dict(S.JOB), os.environ.get('ADVOGADO_DO_DIABO_PLANO'))
        S.RAIZ = self.raiz
        S.MEMORIA['carteira'] = None
        S.JOB.update(estado='parado', inicio=None, fim=None, codigo=None, processo=None)
        os.environ['ADVOGADO_DO_DIABO_PLANO'] = os.path.join(self.raiz, 'plano.json')
        sem = os.path.join(self.raiz, 'semana_20300107_v1')
        for nome, obj in (('sintese.json', SINTESE), ('dossie.json', DOSSIE), ('contra.json', CONTRA),
                          ('auditoria.json', AUDITORIA), ('conferencia.json', CONFERENCIA), ('xp.json', XP)):
            gravar(os.path.join(sem, nome), obj)
        self.sem = sem

    def tearDown(self):
        S.RAIZ, S.LANCADOR = self.antes[0], self.antes[1]
        S.JOB.clear()
        S.JOB.update(self.antes[2])
        if self.antes[3] is None:
            os.environ.pop('ADVOGADO_DO_DIABO_PLANO', None)
        else:
            os.environ['ADVOGADO_DO_DIABO_PLANO'] = self.antes[3]
        self.tmp.cleanup()


class TestSemana(Base):
    def test_ranking_e_diferenca_contra_a_xp(self):
        r = S.semana(self.sem)
        por = {x['ticker']: x for x in r['ranking']}
        self.assertEqual(por['AAAA3']['diferenca'], 'concorda')   # comprar vs Compra
        self.assertEqual(por['BBBB4']['diferenca'], 'discorda')   # aguardar vs Compra
        self.assertIsNone(por['CCCC3']['diferenca'])              # sem rating: não inventa
        self.assertTrue(por['CCCC3']['sem_dados'])

    def test_pasta_mais_recente_e_validacao_de_nome(self):
        gravar(os.path.join(self.raiz, 'semana_20300114_v1', 'sintese.json'), SINTESE)
        self.assertTrue(S.pasta_semana().endswith('semana_20300114_v1'))
        self.assertIsNone(S.pasta_semana('../etc'))
        self.assertIsNone(S.pasta_semana('semana_inexistente'))

    def test_sem_semana(self):
        with tempfile.TemporaryDirectory() as vazio:
            self.assertIsNone(S.pasta_semana(raiz=vazio))


class TestDossie(Base):
    def test_valores_da_cvm_e_cenarios(self):
        d = S.dossie(self.sem, 'AAAA3')
        m = {x['rotulo']: x for x in d['metricas']}
        self.assertEqual(m['ROE']['valor'], 20.0)
        self.assertIn('CVM', m['ROE']['fonte'])
        self.assertEqual(d['valuation']['cenarios']['base']['valor'], 9.0)
        self.assertEqual(len(d['checklist']), 2)

    def test_dado_ausente_nao_vira_numero(self):
        d = S.dossie(self.sem, 'BBBB4')
        self.assertIsNone(d['valuation'])
        for x in d['metricas']:
            self.assertIsNone(x['valor'])
            self.assertIsNone(x['fonte'])      # sem valor, sem fonte: a tela mostra "não verificado"

    def test_roe_texto_so_com_numero_no_inicio(self):
        self.assertEqual(S._roe_texto('21,4% (ITR)'), 21.4)
        self.assertIsNone(S._roe_texto('não verificado (21% em notícia)'))
        self.assertIsNone(S._roe_texto(None))

    def test_ticker_fora_do_ranking(self):
        self.assertIsNone(S.dossie(self.sem, 'ZZZZ3'))


class TestObjecoes(Base):
    def test_ordem_por_forca_e_conferencias(self):
        o = S.objecoes(self.sem, 'AAAA3')
        self.assertEqual([x['forca'] for x in o['objecoes']], ['forte', 'fraca'])
        estados = [c['estado'] for c in o['conferencias']]
        self.assertEqual(estados[0], 'nao_confere')            # problemas primeiro
        self.assertIn('nao_verificado', estados)               # aviso da conferência
        self.assertEqual(estados[-1], 'confere')
        rep = next(c for c in o['conferencias'] if c['estado'] == 'nao_confere')
        self.assertIn('refeito', rep['detalhe'])               # correção registrada aparece
        self.assertEqual(o['tese_xp']['texto'], 'comentário da XP')

    def test_sem_objecao_traz_escopo(self):
        o = S.objecoes(self.sem, 'BBBB4')
        self.assertEqual(o['objecoes'], [])
        self.assertEqual(o['escopo_advogado'], 'top 2')
        self.assertIsNone(o['tese_xp'])


class TestDesempenho(Base):
    def test_sem_avaliacao(self):
        self.assertFalse(S.desempenho(self.raiz)['disponivel'])

    def test_serie_so_com_comprar_e_sem_cdi(self):
        obs = [{'semana': '2030-01-07', 'acao': 'comprar', 'retorno_pct': 2.0, 'ibovespa_pct': 1.0},
               {'semana': '2030-01-07', 'acao': 'comprar', 'retorno_pct': 4.0, 'ibovespa_pct': 1.0},
               {'semana': '2030-01-07', 'acao': 'aguardar', 'retorno_pct': 99.0, 'ibovespa_pct': 0.0}]
        gravar(os.path.join(self.raiz, 'avaliacao.json'), {
            'data_avaliacao': '2030-02-01', 'semanas_no_historico': 1,
            'minimos_para_conclusao': {'observacoes': 30, 'semanas': 8},
            'horizontes': {'1_semana': {'observacoes': 3, 'semanas': 1, 'amostra': 'insuficiente', 'pendentes': 0}},
            'observacoes': {'1_semana': obs}})
        d = S.desempenho(self.raiz)
        h = d['horizontes']['1_semana']
        self.assertEqual(h['serie_comprar'], [{'semana': '2030-01-07', 'n': 2, 'bot': 3.0, 'ibov': 1.0}])
        self.assertIsNone(d['cdi'])                             # sem CDI nos dados: não inventa
        self.assertEqual(d['horizontes']['4_semanas']['media_bot'], None)


class TestRotina(Base):
    def test_etapas_pelos_arquivos(self):
        r = S.rotina(self.raiz)
        estados = {p['nome']: p['estado'] for p in r['passos']}
        self.assertEqual(estados['Leitor do PDF mensal'], 'ok')
        self.assertEqual(estados['Preços e casas'], 'fila')     # precos.json e casas.json não existem
        self.assertEqual(estados['Advogado do diabo'], 'ok')

    def test_iniciar_dispara_uma_vez(self):
        chamadas = []

        class Falso:
            returncode = None
            def poll(self):
                return None

        def lancador(cmd, **kw):
            chamadas.append(cmd)
            return Falso()

        S.LANCADOR = lancador
        ok, _ = S.iniciar_rotina(self.raiz)
        self.assertTrue(ok)
        self.assertEqual(chamadas[0][:2], ['claude', '-p'])
        self.assertTrue(chamadas[0][2].startswith('/semana '))
        ok2, msg = S.iniciar_rotina(self.raiz)
        self.assertFalse(ok2)                                   # uma execução por vez
        self.assertEqual(len(chamadas), 1)
        r = S.rotina(self.raiz)
        self.assertEqual(r['job']['estado'], 'rodando')
        self.assertIn('agora', [p['estado'] for p in r['passos']])

    def test_falha_do_processo_aparece(self):
        class Fim:
            returncode = 3
            def poll(self):
                return 3

        S.LANCADOR = lambda cmd, **kw: Fim()
        S.iniciar_rotina(self.raiz)
        self.assertEqual(S.rotina(self.raiz)['job']['estado'], 'falhou')


class TestCarteiraEPlano(Base):
    def test_importar_csv_fica_so_na_memoria(self):
        r = S.minha_carteira_importar(self.sem, 'ticker;quantidade;preco_medio\nAAAA3;10;8,00\nBBBB4;5;\n')
        self.assertEqual(r['n_posicoes'], 2)
        self.assertEqual(S.minha_carteira_ler(self.sem)['n_posicoes'], 2)
        self.assertFalse(os.path.exists(os.path.join(self.sem, 'minha_carteira.json')))   # nada gravado em disco

    def test_csv_invalido(self):
        with self.assertRaises(ValueError):
            S.minha_carteira_importar(self.sem, '')

    def test_vazio_sem_dados(self):
        self.assertEqual(S.minha_carteira_ler(self.sem), {'vazio': True})


class TestHTTP(Base):
    def setUp(self):
        super().setUp()
        self.srv = S.criar_servidor(0)
        self.porta = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def req(self, metodo, caminho, corpo=None, host=None, extra=None):
        c = http.client.HTTPConnection('127.0.0.1', self.porta, timeout=5)
        h = {'Host': host or f'127.0.0.1:{self.porta}'}
        h.update(extra or {})
        dados = None
        if corpo is not None:
            dados = json.dumps(corpo)
            h['Content-Type'] = 'application/json'
        c.request(metodo, caminho, body=dados, headers=h)
        r = c.getresponse()
        txt = r.read().decode('utf-8')
        c.close()
        return r.status, txt, dict(r.getheaders())

    def test_estaticos_e_cabecalhos(self):
        st, txt, h = self.req('GET', '/')
        self.assertEqual(st, 200)
        self.assertIn('Advogado do Diabo', txt)
        self.assertIn("default-src 'self'", h['Content-Security-Policy'])
        self.assertEqual(h['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self.req('GET', '/js/app.js')[0], 200)

    def test_nao_sai_da_pasta_app(self):
        for caminho in ('/../src/servidor.py', '/%2e%2e/src/servidor.py', '/..%2fsrc%2fservidor.py', '/tokens.css/../../CLAUDE.md'):
            self.assertEqual(self.req('GET', caminho)[0], 404, caminho)

    def test_host_estranho_recusado(self):
        self.assertEqual(self.req('GET', '/api/semana', host='evil.example')[0], 403)
        self.assertEqual(self.req('GET', '/api/semana', host=f'127.0.0.1.evil.example:{self.porta}')[0], 403)

    def test_api_semana(self):
        st, txt, _ = self.req('GET', '/api/semana')
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(txt)['ranking'][0]['ticker'], 'AAAA3')

    def test_ticker_invalido_e_ausente(self):
        self.assertEqual(self.req('GET', '/api/dossie/..%2F..')[0], 400)
        self.assertEqual(self.req('GET', '/api/dossie/ZZZZ3')[0], 404)

    def test_escrita_exige_cabecalho_e_origem(self):
        corpo = {'confirmar': True}
        self.assertEqual(self.req('POST', '/api/rotina/iniciar', corpo)[0], 403)
        self.assertEqual(self.req('POST', '/api/rotina/iniciar', corpo, extra={'X-Adv': '1', 'Origin': 'http://evil.example'})[0], 403)

    def test_rotina_exige_confirmacao_explicita(self):
        S.LANCADOR = lambda *a, **k: self.fail('não deveria disparar')
        st, txt, _ = self.req('POST', '/api/rotina/iniciar', {}, extra={'X-Adv': '1'})
        self.assertEqual(st, 400)
        st, _, _ = self.req('POST', '/api/rotina/iniciar', {'confirmar': 'true'}, extra={'X-Adv': '1'})
        self.assertEqual(st, 400)                               # só o booleano true vale

    def test_importar_e_esquecer(self):
        h = {'X-Adv': '1'}
        st, txt, _ = self.req('POST', '/api/minha-carteira', {'csv': 'ticker;quantidade\nAAAA3;10\n'}, extra=h)
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(txt)['n_posicoes'], 1)
        self.assertEqual(self.req('POST', '/api/minha-carteira', {'csv': ''}, extra=h)[0], 400)
        self.req('DELETE', '/api/minha-carteira', extra=h)
        self.assertEqual(json.loads(self.req('GET', '/api/minha-carteira')[1]), {'vazio': True})

    def test_plano_salvar_validar_apagar(self):
        h = {'X-Adv': '1'}
        ok = {'horizonte': 'anos', 'objetivo': 'renda', 'queda_max_pct': '20', 'limite_ativo_pct': 20, 'limite_setor_pct': 35}
        st, txt, _ = self.req('PUT', '/api/plano', ok, extra=h)
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(txt)['plano']['horizonte'], 'anos')
        self.assertEqual(self.req('PUT', '/api/plano', dict(ok, horizonte='dias'), extra=h)[0], 400)
        self.req('DELETE', '/api/plano', extra=h)
        self.assertIsNone(json.loads(self.req('GET', '/api/plano')[1])['plano'])

    def test_json_invalido_e_corpo_grande(self):
        c = http.client.HTTPConnection('127.0.0.1', self.porta, timeout=5)
        c.request('POST', '/api/plano', body='{', headers={'Host': f'127.0.0.1:{self.porta}', 'X-Adv': '1'})
        self.assertEqual(c.getresponse().status, 400)
        c.close()
        c = http.client.HTTPConnection('127.0.0.1', self.porta, timeout=5)
        c.putrequest('POST', '/api/plano', skip_host=True)
        for k, v in (('Host', f'127.0.0.1:{self.porta}'), ('X-Adv', '1'), ('Content-Length', str(S.MAX_CORPO + 1))):
            c.putheader(k, v)
        c.endheaders()
        self.assertEqual(c.getresponse().status, 413)
        c.close()

    def test_varias_conexoes_em_paralelo(self):
        # regressão: o backlog padrão (5) derrubava o navegador ao carregar vários módulos de uma vez
        resultados = []

        def pedir():
            resultados.append(self.req('GET', '/api/semana')[0])

        ts = [threading.Thread(target=pedir) for _ in range(30)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(resultados, [200] * 30)


class TestCelular(Base):
    """Modo --celular: rede local só com token; sem a opção, só o próprio computador."""

    def abrir(self, celular):
        srv = S.criar_servidor(0, celular=celular)
        if celular:
            srv.hosts_extra = ('192.168.0.10',)   # IP fixo para o teste
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        return srv

    def pedir(self, srv, metodo, caminho, host=None, headers=None, corpo=None):
        porta = srv.server_address[1]
        c = http.client.HTTPConnection('127.0.0.1', porta, timeout=5)
        h = {'Host': host or f'127.0.0.1:{porta}'}
        h.update(headers or {})
        c.request(metodo, caminho, body=json.dumps(corpo) if corpo is not None else None, headers=h)
        r = c.getresponse()
        txt = r.read().decode('utf-8')
        saida = (r.status, txt, dict(r.getheaders()))
        c.close()
        return saida

    def test_padrao_nao_tem_token_nem_aceita_rede(self):
        srv = self.abrir(False)
        self.assertEqual(srv.server_address[0], '127.0.0.1')
        self.assertIsNone(srv.token)
        self.assertEqual(self.pedir(srv, 'GET', '/api/semana')[0], 200)
        self.assertEqual(self.pedir(srv, 'GET', '/api/semana', host=f'192.168.0.10:{srv.server_address[1]}')[0], 403)

    def test_celular_escuta_na_rede_e_gera_token(self):
        srv = self.abrir(True)
        self.assertEqual(srv.server_address[0], '0.0.0.0')
        self.assertGreaterEqual(len(srv.token), 16)
        outro = S.criar_servidor(0, celular=True)
        self.addCleanup(outro.server_close)
        self.assertNotEqual(srv.token, outro.token)          # um token novo por execução

    def test_sem_token_negado(self):
        srv = self.abrir(True)
        st, txt, _ = self.pedir(srv, 'GET', '/api/semana')
        self.assertEqual(st, 401)
        self.assertNotIn('AAAA3', txt)                       # nenhum dado vaza
        self.assertEqual(self.pedir(srv, 'GET', '/')[0], 401)
        self.assertEqual(self.pedir(srv, 'GET', '/api/semana?k=errado')[0], 401)

    def test_token_na_url_vira_cookie_e_libera(self):
        srv = self.abrir(True)
        host = f'192.168.0.10:{srv.server_address[1]}'
        st, _, h = self.pedir(srv, 'GET', f'/?k={srv.token}', host=host)
        self.assertEqual(st, 302)
        self.assertEqual(h['Location'], '/')                 # o token sai da URL
        self.assertIn('HttpOnly', h['Set-Cookie'])
        self.assertIn('SameSite=Strict', h['Set-Cookie'])
        cookie = h['Set-Cookie'].split(';')[0]
        st, txt, _ = self.pedir(srv, 'GET', '/api/semana', host=host, headers={'Cookie': cookie})
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(txt)['ranking'][0]['ticker'], 'AAAA3')

    def test_cookie_errado_negado(self):
        srv = self.abrir(True)
        self.assertEqual(self.pedir(srv, 'GET', '/api/semana', headers={'Cookie': 'adv_k=errado'})[0], 401)

    def test_token_na_url_nao_vale_para_escrita(self):
        srv = self.abrir(True)
        r = self.pedir(srv, 'POST', f'/api/rotina/iniciar?k={srv.token}', headers={'X-Adv': '1'}, corpo={'confirmar': True})
        self.assertEqual(r[0], 401)                          # só o cookie autoriza POST

    def test_host_estranho_continua_recusado_com_token(self):
        srv = self.abrir(True)
        cookie = f'adv_k={srv.token}'
        self.assertEqual(self.pedir(srv, 'GET', '/api/semana', host='evil.example', headers={'Cookie': cookie})[0], 403)
        self.assertEqual(self.pedir(srv, 'GET', '/api/semana', headers={'Cookie': cookie})[0], 200)

    def test_ips_locais_sem_loopback(self):
        self.assertTrue(all(not ip.startswith('127.') for ip in S.ips_locais()))


if __name__ == '__main__':
    unittest.main()
