"""Testes offline do agendamento: entender "segunda às 16", gravar, executar no horário e notificar.

Nada chama o Claude nem mostra notificação de verdade: o executor e o notificador são trocados por fakes.
"""
import datetime as dt
import http.client
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import agenda as A  # noqa: E402
import chat as CH  # noqa: E402
import servidor as S  # noqa: E402
from test_servidor import Base, SINTESE, gravar  # noqa: E402

AGORA = dt.datetime(2026, 10, 22, 14, 30).astimezone()   # quinta-feira, 14:30


def quando(pedido, **kw):
    p = A.interpretar(pedido, AGORA, **kw)
    return None if p is None else (dt.datetime.fromisoformat(p['quando']).replace(tzinfo=None), p)


def dia_hora(ano, mes, dia, h, m=0):
    return dt.datetime(ano, mes, dia, h, m)


class TestEntenderPedido(unittest.TestCase):
    def test_o_exemplo_do_usuario(self):
        q, p = quando('me manda o resumo do Risco segunda às 16')
        self.assertEqual(q, dia_hora(2026, 10, 26, 16))             # a próxima segunda
        self.assertEqual((p['bot'], p['pergunta']), ('risco', 'Resumo do Risco'))
        self.assertEqual(p['quando_texto'], 'segunda, 26/10 às 16:00')

    def test_dias_da_semana(self):
        self.assertEqual(quando('me manda sexta 8h')[0], dia_hora(2026, 10, 23, 8))
        self.assertEqual(quando('me manda domingo às 20h')[0], dia_hora(2026, 10, 25, 20))
        self.assertEqual(quando('me manda terça-feira às 9')[0], dia_hora(2026, 10, 27, 9))
        self.assertEqual(quando('me manda sábado as 7h45')[0], dia_hora(2026, 10, 24, 7, 45))

    def test_mesmo_dia_da_semana_hoje(self):
        self.assertEqual(quando('me manda quinta às 16')[0], dia_hora(2026, 10, 22, 16))   # ainda dá tempo: hoje
        self.assertEqual(quando('me manda quinta às 10')[0], dia_hora(2026, 10, 29, 10))   # já passou: semana que vem
        self.assertEqual(quando('me manda a próxima quinta às 16')[0], dia_hora(2026, 10, 29, 16))

    def test_hoje_amanha_depois_de_amanha(self):
        self.assertEqual(quando('me avise hoje às 18')[0], dia_hora(2026, 10, 22, 18))
        self.assertEqual(quando('me avise amanhã às 9h30')[0], dia_hora(2026, 10, 23, 9, 30))
        self.assertEqual(quando('me avise depois de amanhã às 8 da manhã')[0], dia_hora(2026, 10, 24, 8))

    def test_so_hora_vai_para_hoje_ou_amanha(self):
        self.assertEqual(quando('me manda o resumo às 16')[0], dia_hora(2026, 10, 22, 16))
        self.assertEqual(quando('me manda o resumo às 10')[0], dia_hora(2026, 10, 23, 10))   # 10h de hoje já passou

    def test_formatos_de_hora(self):
        for texto, esperado in (('às 16', (16, 0)), ('as 16h', (16, 0)), ('16:30', (16, 30)), ('16h30', (16, 30)), ('16 horas', (16, 0)),
                                ('às 4 da tarde', (16, 0)), ('às 8 da noite', (20, 0)), ('às 9 da manhã', (9, 0)),
                                ('ao meio-dia', (12, 0))):
            q, _ = quando(f'me manda amanhã {texto}')
            self.assertEqual((q.hour, q.minute), esperado, texto)

    def test_datas(self):
        self.assertEqual(quando('me manda dia 25 às 10')[0], dia_hora(2026, 10, 25, 10))
        self.assertEqual(quando('me manda no dia 25/10 as 10:15 o resumo')[0], dia_hora(2026, 10, 25, 10, 15))
        self.assertEqual(quando('me manda 23/10/2026 às 7:05')[0], dia_hora(2026, 10, 23, 7, 5))
        self.assertEqual(quando('me manda dia 21 às 10')[0], dia_hora(2026, 11, 21, 10))     # dia 21 já passou neste mês

    def test_prazos_relativos(self):
        self.assertEqual(quando('me manda daqui a 2 horas')[0], dia_hora(2026, 10, 22, 16, 30))
        self.assertEqual(quando('em 30 minutos me avise')[0], dia_hora(2026, 10, 22, 15, 0))
        self.assertEqual(quando('me manda em 3 dias às 9h')[0], dia_hora(2026, 10, 25, 9))
        self.assertEqual(quando('me manda em 2 semanas às 10')[0], dia_hora(2026, 11, 5, 10))

    def test_bot_pelo_nome_ou_o_atual(self):
        self.assertEqual(quando('me manda o resumo do macro amanhã às 9')[1]['bot'], 'macro')
        self.assertEqual(quando('me manda as notícias de PRIO3 amanhã às 9')[1]['bot'], 'noticias')
        self.assertEqual(quando('me manda amanhã às 9', bot_atual='casas')[1]['bot'], 'casas')
        self.assertEqual(quando('me manda amanhã às 9', bot_atual='inexistente')[1]['bot'], 'analista')

    def test_pergunta_sem_o_pedido_de_tempo(self):
        self.assertEqual(quando('me manda segunda às 16 as casas de PRIO3')[1]['pergunta'], 'As casas de PRIO3')
        self.assertEqual(quando('agende o resumo do fluxo para domingo às 20h')[1]['pergunta'], 'Resumo do fluxo')
        self.assertEqual(quando('me manda segunda às 16')[1]['pergunta'], 'Resumo da semana')      # nada além do tempo: padrão
        q, p = quando('me manda o macro amanhã de manhã às 8')
        self.assertEqual((p['bot'], p['pergunta']), ('macro', 'Resumo da semana'))           # só o nome do bot: pergunta padrão
        self.assertEqual(quando('me manda o resumo do macro amanhã de manhã às 8')[1]['pergunta'], 'Resumo do macro')

    def test_artigo_nao_vira_hora(self):
        q, p = quando('me manda as 5 casas de PRIO3 amanhã às 9')
        self.assertEqual(q, dia_hora(2026, 10, 23, 9))
        self.assertEqual(p['pergunta'], 'As 5 casas de PRIO3')
        self.assertEqual(quando('me manda sexta às 16 as 3 notícias')[0], dia_hora(2026, 10, 23, 16))

    def test_nao_e_agendamento_vai_para_o_chat(self):
        for texto in ('quais eventos vêm segunda às 16?', 'segunda às 16 o que acontece', 'me manda o resumo',
                      'me manda o alerta de hoje', 'qual a tese de PRIO3?', 'Compare PRIO3 e IGTI11', ''):
            self.assertIsNone(A.interpretar(texto, AGORA), texto)

    def test_pedidos_que_nao_da_para_atender(self):
        casos = {
            'me manda toda segunda às 16': 'uma vez',
            'me manda todos os dias às 9': 'uma vez',
            'me manda segunda': 'horário',
            'me manda amanhã': 'horário',
            'me manda às 25h': 'horário',
            'me manda às 16:75': 'horário',
            'me manda dia 31/02 às 10': 'não existe',
            'me manda dia 16/10 às 9': 'já passou',
            'me avise hoje às 10': 'já passou',
            'me manda o resumo em 2 meses às 9': 'Diga o dia',
            'me manda o resumo semana que vem às 9': 'Diga o dia',
            'me manda no fim de semana às 9': 'Diga o dia',
            'me manda 25/12 às 9': '60 dias',
            'me manda em 0 minutos': 'maior que zero',
        }
        for texto, trecho in casos.items():
            with self.assertRaises(A.PedidoInvalido, msg=texto) as c:
                A.interpretar(texto, AGORA)
            self.assertIn(trecho, str(c.exception), texto)

    def test_nunca_agenda_no_passado(self):
        for texto in ('me manda hoje às 14:30', 'me manda hoje às 14', 'me manda ontem às 9'):
            try:
                p = A.interpretar(texto, AGORA)
            except A.PedidoInvalido:
                continue
            if p:
                self.assertGreater(dt.datetime.fromisoformat(p['quando']), AGORA, texto)


class TestGuardar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.antes = os.environ.get('ADVOGADO_DO_DIABO_AGENDA')
        os.environ['ADVOGADO_DO_DIABO_AGENDA'] = os.path.join(self.tmp.name, 'sub', 'agenda.json')
        self.futuro = (AGORA + dt.timedelta(days=2)).isoformat()

    def tearDown(self):
        if self.antes is None:
            os.environ.pop('ADVOGADO_DO_DIABO_AGENDA', None)
        else:
            os.environ['ADVOGADO_DO_DIABO_AGENDA'] = self.antes
        self.tmp.cleanup()

    def test_criar_listar_cancelar(self):
        t = A.criar('risco', 'Resumo do risco', self.futuro, AGORA)
        self.assertEqual(t['estado'], 'agendada')
        self.assertRegex(t['id'], r'^[0-9a-f]{8}$')
        self.assertEqual([x['id'] for x in A.listar()], [t['id']])
        self.assertTrue(A.cancelar(t['id']))
        self.assertEqual(A.listar()[0]['estado'], 'cancelada')
        self.assertFalse(A.cancelar(t['id']))                       # já cancelada
        self.assertFalse(A.cancelar('00000000'))

    def test_arquivo_privado(self):
        A.criar('risco', 'x', self.futuro, AGORA)
        caminho = os.environ['ADVOGADO_DO_DIABO_AGENDA']
        self.assertEqual(stat.S_IMODE(os.stat(caminho).st_mode), 0o600)         # só o dono lê

    def test_validacoes(self):
        ruins = [('hacker', 'x', self.futuro), (None, 'x', self.futuro), ('risco', '', self.futuro), ('risco', '  ', self.futuro),
                 ('risco', 'x' * (A.MAX_PERGUNTA + 1), self.futuro), ('risco', 'x', 'amanhã'), ('risco', 'x', None),
                 ('risco', 'x', (AGORA - dt.timedelta(minutes=1)).isoformat()),
                 ('risco', 'x', (AGORA + dt.timedelta(days=A.MAX_DIAS + 1)).isoformat()), (['risco'], 'x', self.futuro), ('risco', 5, self.futuro)]
        for bot, perg, q in ruins:
            with self.assertRaises(A.PedidoInvalido, msg=(bot, perg, q)):
                A.criar(bot, perg, q, AGORA)
        self.assertEqual(A.listar(), [])

    def test_limite_de_tarefas_ativas(self):
        for _ in range(A.MAX_ATIVAS):
            A.criar('risco', 'x', self.futuro, AGORA)
        with self.assertRaises(A.PedidoInvalido) as c:
            A.criar('risco', 'x', self.futuro, AGORA)
        self.assertIn('Cancele', str(c.exception))

    def test_arquivo_corrompido_vira_lista_vazia(self):
        os.makedirs(os.path.dirname(os.environ['ADVOGADO_DO_DIABO_AGENDA']))
        with open(os.environ['ADVOGADO_DO_DIABO_AGENDA'], 'w') as f:
            f.write('{ não é json')
        self.assertEqual(A.listar(), [])


class TestExecutar(TestGuardar):
    def tarefa(self, minutos_atras=0, bot='risco'):
        t = A.criar(bot, 'Resumo do risco', (AGORA + dt.timedelta(hours=1)).isoformat(), AGORA - dt.timedelta(hours=1))
        tarefas = A.carregar()
        for x in tarefas:
            if x['id'] == t['id']:
                x['quando'] = (AGORA - dt.timedelta(minutes=minutos_atras)).isoformat()
        A._salvar(tarefas)
        return t['id']

    def estado(self, id_):
        return next(t for t in A.carregar() if t['id'] == id_)

    def test_ainda_nao_e_hora(self):
        A.criar('risco', 'x', self.futuro, AGORA)
        chamadas = []
        A.executar_vencidas(AGORA, lambda t: chamadas.append(t) or {}, lambda *a: None)
        self.assertEqual(chamadas, [])

    def test_executa_no_horario_e_notifica(self):
        id_ = self.tarefa(0)
        avisos = []
        r = {'resposta': 'O risco da semana é X.', 'fontes': [{'fonte': 'risco.json', 'data': '2026-10-05', 'id': 'F1'}], 'nao_verificado': ['beta'], 'formato_ok': True}
        feitas = A.executar_vencidas(AGORA, lambda t: r, lambda titulo, texto: avisos.append((titulo, texto)))
        self.assertEqual(len(feitas), 1)
        t = self.estado(id_)
        self.assertEqual((t['estado'], t['atrasada']), ('executada', False))
        self.assertEqual(t['resultado']['fontes'][0]['fonte'], 'risco.json')       # a fonte acompanha a resposta guardada
        self.assertEqual(avisos, [('Advogado do Diabo · Risco', 'O risco da semana é X.')])
        # não roda duas vezes
        A.executar_vencidas(AGORA, lambda t: self.fail('rodou de novo'), lambda *a: None)

    def test_atrasada_e_avisada_como_atrasada(self):
        id_ = self.tarefa(minutos_atras=90)
        avisos = []
        A.executar_vencidas(AGORA, lambda t: {'resposta': 'ok'}, lambda titulo, texto: avisos.append(titulo))
        self.assertTrue(self.estado(id_)['atrasada'])
        self.assertIn('atrasada', avisos[0])

    def test_vencida_ha_mais_de_12_horas_e_perdida(self):
        id_ = self.tarefa(minutos_atras=13 * 60)
        A.executar_vencidas(AGORA, lambda t: self.fail('não deveria rodar'), lambda *a: self.fail('nem avisar'))
        t = self.estado(id_)
        self.assertEqual(t['estado'], 'perdida')
        self.assertIn('desligado', t['erro'])

    def test_falha_vira_estado_e_avisa_sem_derrubar(self):
        id_ = self.tarefa(0)
        id2 = self.tarefa(0, bot='casas')
        avisos = []

        def quebra(t):
            if t['bot'] == 'risco':
                raise RuntimeError('o claude caiu')
            return {'resposta': 'ok'}

        A.executar_vencidas(AGORA, quebra, lambda titulo, texto: avisos.append(texto))
        self.assertEqual(self.estado(id_)['estado'], 'falhou')
        self.assertIn('claude caiu', self.estado(id_)['erro'])
        self.assertEqual(self.estado(id2)['estado'], 'executada')                    # a falha de uma não impede a outra
        self.assertTrue(any('Não consegui responder' in a for a in avisos))

    def test_chat_ocupado_tenta_de_novo_e_depois_desiste(self):
        id_ = self.tarefa(0)

        def ocupado(t):
            raise A.Ocupado()

        for i in range(A.MAX_TENTATIVAS - 1):
            A.executar_vencidas(AGORA, ocupado, lambda *a: None)
            self.assertEqual(self.estado(id_)['estado'], 'agendada')
        A.executar_vencidas(AGORA, ocupado, lambda *a: None)
        self.assertEqual(self.estado(id_)['estado'], 'falhou')

    def test_cancelada_nao_roda(self):
        id_ = self.tarefa(0)
        A.cancelar(id_)
        A.executar_vencidas(AGORA, lambda t: self.fail('rodou cancelada'), lambda *a: None)

    def test_cancelamento_durante_a_execucao_nao_e_desfeito(self):
        id_ = self.tarefa(0)

        def executa_e_cancela_no_meio(t):
            A.cancelar(id_)                                  # o usuário cancela enquanto a resposta é gerada
            return {'resposta': 'ok'}

        A.executar_vencidas(AGORA, executa_e_cancela_no_meio, lambda *a: None)
        self.assertEqual(self.estado(id_)['estado'], 'cancelada')

    def test_marcar_vista(self):
        id_ = self.tarefa(0)
        A.executar_vencidas(AGORA, lambda t: {'resposta': 'ok'}, lambda *a: None)
        self.assertFalse(self.estado(id_).get('vista'))
        self.assertTrue(A.marcar_vista(id_))
        self.assertTrue(self.estado(id_)['vista'])


class TestNotificacao(unittest.TestCase):
    def test_texto_vai_como_argumento_e_nao_dentro_do_script(self):
        perigoso = 'x" & do shell script "touch /tmp/invadido" & "'
        with mock.patch.object(A.sys, 'platform', 'darwin'), mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(A.subprocess, 'run') as run:
            os.environ.pop('ADV_SEM_NOTIFICAR', None)
            run.return_value.returncode = 0
            self.assertTrue(A.notificar_mac('Título "x"', perigoso))
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[0], 'osascript')
        script = ' '.join(cmd[:7])
        self.assertNotIn('invadido', script)                  # o texto não entra no código AppleScript
        self.assertNotIn('touch', script)
        self.assertIn(perigoso[:200], cmd[-2])                # chega só como dado, no argv
        self.assertTrue(isinstance(run.call_args[1].get('timeout'), int))

    def test_limpa_controles_e_limita_tamanho(self):
        with mock.patch.object(A.sys, 'platform', 'darwin'), mock.patch.object(A.subprocess, 'run') as run:
            os.environ.pop('ADV_SEM_NOTIFICAR', None)
            run.return_value.returncode = 0
            A.notificar_mac('t' * 500, 'a\nb\x00c' + 'z' * 1000)
        corpo, titulo = run.call_args[0][0][-2:]
        self.assertNotIn('\n', corpo)
        self.assertNotIn('\x00', corpo)
        self.assertLessEqual(len(corpo), 220)
        self.assertLessEqual(len(titulo), 80)

    def test_fora_do_mac_ou_silenciado_nao_chama_nada(self):
        with mock.patch.object(A.sys, 'platform', 'linux'), mock.patch.object(A.subprocess, 'run') as run:
            self.assertFalse(A.notificar_mac('t', 'x'))
            run.assert_not_called()
        with mock.patch.object(A.sys, 'platform', 'darwin'), mock.patch.dict(os.environ, {'ADV_SEM_NOTIFICAR': '1'}), \
                mock.patch.object(A.subprocess, 'run') as run:
            self.assertFalse(A.notificar_mac('t', 'x'))
            run.assert_not_called()

    def test_osascript_ausente_nao_quebra(self):
        with mock.patch.object(A.sys, 'platform', 'darwin'), mock.patch.object(A.subprocess, 'run', side_effect=FileNotFoundError):
            os.environ.pop('ADV_SEM_NOTIFICAR', None)
            self.assertFalse(A.notificar_mac('t', 'x'))


class TestAPIAgenda(Base):
    def setUp(self):
        super().setUp()
        self.antes_ag = os.environ.get('ADVOGADO_DO_DIABO_AGENDA')
        os.environ['ADVOGADO_DO_DIABO_AGENDA'] = os.path.join(self.raiz, 'agenda.json')
        gravar(os.path.join(self.sem, 'sintese.json'), SINTESE)
        self.srv = S.criar_servidor(0)
        self.porta = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        if self.antes_ag is None:
            os.environ.pop('ADVOGADO_DO_DIABO_AGENDA', None)
        else:
            os.environ['ADVOGADO_DO_DIABO_AGENDA'] = self.antes_ag
        super().tearDown()

    def req(self, metodo, caminho, corpo=None, escrita=True):
        c = http.client.HTTPConnection('127.0.0.1', self.porta, timeout=5)
        h = {'Host': f'127.0.0.1:{self.porta}'}
        if escrita and metodo != 'GET':
            h['X-Adv'] = '1'
        c.request(metodo, caminho, body=json.dumps(corpo) if corpo is not None else None, headers=h)
        r = c.getresponse()
        saida = (r.status, json.loads(r.read().decode('utf-8') or '{}'))
        c.close()
        return saida

    def test_interpretar_nao_grava_nada(self):
        st, j = self.req('POST', '/api/agenda/interpretar', {'texto': 'me manda o resumo do risco amanhã às 9', 'bot': 'analista'})
        self.assertEqual(st, 200)
        self.assertTrue(j['entendido'])
        self.assertEqual(j['proposta']['bot'], 'risco')
        self.assertEqual(self.req('GET', '/api/agenda')[1]['tarefas'], [])           # só a confirmação grava

    def test_mensagem_comum_nao_e_agendamento(self):
        self.assertEqual(self.req('POST', '/api/agenda/interpretar', {'texto': 'qual a tese de PRIO3?'})[1], {'agendamento': False})

    def test_pedido_invalido_volta_com_motivo(self):
        st, j = self.req('POST', '/api/agenda/interpretar', {'texto': 'me manda toda segunda às 16'})
        self.assertEqual(st, 200)
        self.assertEqual((j['agendamento'], j['entendido']), (True, False))
        self.assertIn('uma vez', j['motivo'])

    def test_fluxo_confirmar_listar_cancelar(self):
        prop = self.req('POST', '/api/agenda/interpretar', {'texto': 'me manda o resumo do risco em 2 horas'})[1]['proposta']
        st, t = self.req('POST', '/api/agenda', {'bot': prop['bot'], 'pergunta': prop['pergunta'], 'quando': prop['quando']})
        self.assertEqual(st, 200)
        self.assertEqual([x['id'] for x in self.req('GET', '/api/agenda')[1]['tarefas']], [t['id']])
        self.assertEqual(self.req('DELETE', f"/api/agenda/{t['id']}")[0], 200)
        self.assertEqual(self.req('GET', '/api/agenda')[1]['tarefas'][0]['estado'], 'cancelada')
        self.assertEqual(self.req('DELETE', f"/api/agenda/{t['id']}")[0], 404)

    def test_criar_revalida_o_que_vem_da_tela(self):
        for corpo in ({}, {'bot': 'hacker', 'pergunta': 'x', 'quando': '2099-01-01T10:00:00'}, {'bot': 'risco', 'pergunta': '', 'quando': (AGORA + dt.timedelta(days=1)).isoformat()},
                      {'bot': 'risco', 'pergunta': 'x', 'quando': '2000-01-01T10:00:00+00:00'}, []):
            self.assertEqual(self.req('POST', '/api/agenda', corpo)[0], 400, corpo)

    def test_id_malformado_e_rejeitado(self):
        for id_ in ('../../x', 'ABCDEFGH', '123', 'zzzzzzzz'):
            self.assertEqual(self.req('DELETE', f'/api/agenda/{id_}')[0], 404, id_)

    def test_escrita_exige_cabecalho(self):
        self.assertEqual(self.req('POST', '/api/agenda', {'bot': 'risco'}, escrita=False)[0], 403)
        self.assertEqual(self.req('POST', '/api/agenda/interpretar', {'texto': 'x'}, escrita=False)[0], 403)

    def test_texto_invalido(self):
        for corpo in ({}, {'texto': ''}, {'texto': 5}, {'texto': 'x' * (CH.MAX_PERGUNTA + 1)}):
            self.assertEqual(self.req('POST', '/api/agenda/interpretar', corpo)[0], 400, corpo)

    def test_executor_do_servidor_usa_o_chat_e_trata_ocupado(self):
        antes = CH.RUNNER
        CH.RUNNER = lambda s, p, tempo=0: json.dumps({'resposta': 'ok', 'fontes': [], 'nao_verificado': []})
        try:
            r = S._executar_agendada({'pergunta': 'Resumo do risco', 'bot': 'risco'})
            self.assertEqual(r['bot'], 'risco')
            S._trava_chat.acquire()
            try:
                with self.assertRaises(A.Ocupado):
                    S._executar_agendada({'pergunta': 'x', 'bot': 'risco'})
            finally:
                S._trava_chat.release()
        finally:
            CH.RUNNER = antes


if __name__ == '__main__':
    unittest.main()
