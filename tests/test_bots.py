"""Testes offline dos bots do chat: cada bot lê só o arquivo do seu agente, com fontes e sem inventar."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import bots as B  # noqa: E402
import chat as CH  # noqa: E402
import servidor as S  # noqa: E402
from test_servidor import Base, gravar  # noqa: E402

CASAS = {'data_coleta': '2030-01-05', 'regra_antiguidade': 'mais de 6 meses fica fora', 'tickers': {
    'AAAA3': {'casas': [{'casa': 'Casa X', 'rating': 'compra', 'preco_alvo': 12.0, 'moeda': 'R$', 'data': '2030-01-02', 'fonte': 'Veículo Y',
                         'situacao': 'verificada', 'obs': 'obs'}],
              'contagem_verificada': {'compra': 1, 'neutro': 0, 'venda': 0}, 'mediana_preco_alvo': 12.0, 'moeda_mediana': 'R$',
              'n_alvos_mediana': 1, 'status': 'dado insuficiente', 'xp': {'rating': 'Compra'}, 'divergencia_xp': 'XP acima da mediana'}}}
NOTICIAS = {'data_coleta': '2030-01-05', 'janela': '7 dias', 'observacao': 'obs', 'tickers': {'AAAA3': {
    'itens': [{'data': '2030-01-01', 'fonte': 'Jornal A', 'resumo': 'antiga', 'tipo': 'fato', 'impacto': 'positivo', 'certeza': 'alta'},
              {'data': '2030-01-04', 'fonte': 'Jornal B', 'resumo': 'recente <script>x</script>', 'tipo': 'fato', 'impacto': 'negativo', 'certeza': 'média'}],
    'eventos_futuros': [{'evento': 'Resultado', 'data': 'não verificado', 'fonte': 'RI', 'certeza': 'baixa'}]}}}
RISCO = {'data': '2030-01-05', 'metodo': {'janela': '90'}, 'resumo': 'risco ok', 'tabela_por_ticker': {
    'AAAA3': {'setor': 'Energia', 'vol_90pregoes_anual_pct': 30.0, 'beta_ibov_multifator': 0.5}}, 'limites': {'x': 1}}
FLUXO = {'data_calculo': '2030-01-05', 'nota': 'n', 'retornos_ibovespa': {'5d_pct': 1.0}, 'acoes': {
    'AAAA3': {'retorno_5d_pct': 2.0, 'retorno_30d_pct': 3.0, 'retorno_90d_pct': 4.0, 'diferenca_5d_pp': 1.0, 'diferenca_30d_pp': 0.0,
              'diferenca_90d_pp': -1.0, 'acima_mm50': True, 'acima_mm200': False, 'vol_anualizada_pct': 20.0, 'beta_90d': 0.9}}}
MACRO = {'data_coleta': '2030-01-05', 'indicadores': [{'indicador': 'Selic', 'valor_atual': 10.0, 'unidade': '% a.a.', 'data_do_dado': '2030-01-01',
                                                        'variacao_3m': '-1 pp', 'fonte': 'Banco Central', 'data_coleta': '2030-01-05'}],
         'efeito_por_setor_4_semanas': {'Energia': {'efeito': 'positivo', 'motivo': 'm', 'tipo': 'projeção'}},
         'eventos_4_semanas': [{'data': '2030-01-09', 'evento': 'IPCA', 'certeza': 'baixa', 'nota': 'n'}], 'risco_central': 'segundo turno'}
ALERTAS = {'data': '2030-01-05', 'criterio': 'c', 'resumo': '1 amarelo', 'alertas': [
    {'nivel': 'amarelo', 'ticker': 'AAAA3', 'fato': 'caiu', 'fonte': 'Jornal C', 'data': '2030-01-03', 'impacto': 'i', 'acao_recomendada': 'a', 'certeza': 'média'},
    {'nivel': 'verde', 'ticker': 'BBBB4', 'fato': 'subiu', 'fonte': 'Jornal D', 'data': '2030-01-03'}]}
FUNDAMENTOS = {'data_coleta': '2030-01-05', 'observacao': 'sem CVM', 'tickers': {'AAAA3': {'periodo': '2T', 'roe': '20% (ITR)', 'pl': 'não verificado', 'certeza': 'alta'}}}


def texto(bot, pasta, tks):
    F = B.Fontes()
    return '\n'.join(B.montar(bot, pasta, tks, F)), F


class TestBots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = self.tmp.name
        for nome, obj in (('casas.json', CASAS), ('noticias.json', NOTICIAS), ('risco.json', RISCO), ('fluxo.json', FLUXO),
                          ('macro.json', MACRO), ('alertas.json', ALERTAS), ('fundamentos.json', FUNDAMENTOS)):
            gravar(os.path.join(self.pasta, nome), obj)

    def tearDown(self):
        self.tmp.cleanup()

    def test_todos_os_bots_tem_metadados_completos(self):
        self.assertEqual(B.ORDEM[0], 'analista')
        for k, b in B.BOTS.items():
            for campo in ('nome', 'mono', 'descricao', 'papel', 'sugestoes'):
                self.assertTrue(b[campo], f'{k}.{campo}')
            self.assertEqual(len(b['mono']), 2)
            self.assertTrue(all(s.strip() for s in b['sugestoes']))
        self.assertEqual(len({b['mono'] for b in B.BOTS.values()}), len(B.BOTS))     # monogramas distintos
        self.assertEqual(len(B.lista()), len(B.BOTS))

    def test_sugestoes_usam_so_marcadores_conhecidos(self):
        import re
        for b in B.BOTS.values():
            for s in b['sugestoes']:
                self.assertTrue(set(re.findall(r'\{(\w+)\}', s)) <= {'t', 't2'}, s)

    def test_persona_aponta_para_os_outros_bots(self):
        p = B.persona('casas')
        self.assertIn('bot Casas', p)
        self.assertIn('Notícias', p)
        self.assertNotIn('Casas (', p)                                              # não se indica a si mesmo

    def test_casas_com_ticker(self):
        t, F = texto('casas', self.pasta, ['AAAA3'])
        self.assertIn('Casa X: compra, alvo R$ 12.0', t)
        self.assertIn('Veículo Y', [f['fonte'] for f in F.itens.values()])           # fonte e data de cada casa
        self.assertIn('2030-01-02', [f['data'] for f in F.itens.values()])

    def test_noticias_mais_recente_primeiro_e_evento_sem_data(self):
        t, _ = texto('noticias', self.pasta, ['AAAA3'])
        self.assertLess(t.index('recente'), t.index('antiga'))
        self.assertIn('data não verificado', t)                                      # a data ausente continua ausente

    def test_risco_fluxo_macro_monitor_fundamentos(self):
        self.assertIn('volatilidade 30.0%', texto('risco', self.pasta, [])[0])
        self.assertIn('da MM200: False', texto('fluxo', self.pasta, ['AAAA3'])[0])
        m, F = texto('macro', self.pasta, [])
        self.assertIn('Selic: 10.0', m)
        self.assertIn('Banco Central', [f['fonte'] for f in F.itens.values()])
        a, _ = texto('monitor', self.pasta, ['AAAA3'])
        self.assertIn('amarelo AAAA3', a)
        self.assertNotIn('BBBB4', a)                                                 # filtra pelo ticker perguntado
        f, _ = texto('fundamentos', self.pasta, ['AAAA3'])
        self.assertIn('pl: não verificado', f)
        self.assertIn('valuation por cenários: não verificado', f)

    def test_arquivo_ausente_vira_nao_verificado_sem_quebrar(self):
        with tempfile.TemporaryDirectory() as vazio:
            for k in B.ORDEM[1:]:
                t, F = texto(k, vazio, ['AAAA3'])
                self.assertIn('não verificado', t, k)
                self.assertEqual(F.itens, {}, k)                                      # nenhuma fonte inventada

    def test_arquivo_corrompido_nao_quebra(self):
        with open(os.path.join(self.pasta, 'risco.json'), 'w') as f:
            f.write('{ isto não é json')
        self.assertIn('não verificado', texto('risco', self.pasta, [])[0])

    def test_estrutura_inesperada_nao_quebra(self):
        gravar(os.path.join(self.pasta, 'casas.json'), {'tickers': {'AAAA3': {'casas': 'texto', 'xp': 5}}})
        gravar(os.path.join(self.pasta, 'macro.json'), {'indicadores': 'x', 'efeito_por_setor_4_semanas': [1, 2]})
        texto('casas', self.pasta, ['AAAA3'])
        texto('macro', self.pasta, [])


class TestBotNoChat(Base):
    def setUp(self):
        super().setUp()
        for nome, obj in (('casas.json', CASAS), ('risco.json', RISCO)):
            gravar(os.path.join(self.sem, nome), obj)
        self.antes_runner = CH.RUNNER
        self.chamadas = []

        def falso(sistema, prompt, tempo=0):
            self.chamadas.append((sistema, prompt))
            return json.dumps({'resposta': 'ok', 'fontes': ['F2'], 'nao_verificado': []})

        CH.RUNNER = falso

    def tearDown(self):
        CH.RUNNER = self.antes_runner
        super().tearDown()

    def test_bot_usa_o_arquivo_dele_e_a_persona(self):
        r = S.chat_responder(self.sem, {'pergunta': 'O que as casas dizem de AAAA3?', 'bot': 'casas'})
        sistema, prompt = self.chamadas[0]
        self.assertIn('bot Casas', sistema)
        self.assertIn('Casa X: compra', prompt)
        self.assertNotIn('DETALHE AAAA3', prompt)                                    # contexto do analista fica de fora
        self.assertEqual(r['bot'], 'casas')
        self.assertEqual(r['fontes'][0]['fonte'], 'casas.json')                      # F2 vem da tabela do servidor

    def test_padrao_e_o_analista(self):
        r = S.chat_responder(self.sem, {'pergunta': 'AAAA3?'})
        self.assertEqual(r['bot'], 'analista')
        self.assertIn('DETALHE AAAA3', self.chamadas[0][1])

    def test_bot_desconhecido_e_400(self):
        for bot in ('hacker', '', 5, None, ['casas']):
            with self.assertRaises(S.Erro) as c:
                S.chat_responder(self.sem, {'pergunta': 'oi', 'bot': bot})
            self.assertEqual(c.exception.codigo, 400, bot)
        self.assertEqual(self.chamadas, [])

    def test_carteira_vale_para_qualquer_bot_e_so_com_peso(self):
        S.minha_carteira_importar(self.sem, 'ticker;quantidade;preco_medio\nAAAA3;10;8,00\n')
        S.chat_responder(self.sem, {'pergunta': 'risco de AAAA3?', 'bot': 'risco', 'carteira': True})
        p = self.chamadas[0][1]
        self.assertIn('AAAA3: 100.0% da carteira', p)
        self.assertNotIn('preco_medio', p)
        S.chat_responder(self.sem, {'pergunta': 'risco de AAAA3?', 'bot': 'risco'})
        self.assertNotIn('CARTEIRA DO USUÁRIO', self.chamadas[1][1])

    def test_status_lista_os_bots(self):
        st = S.chat_status(self.sem)
        self.assertEqual([b['id'] for b in st['bots']], B.ORDEM)

    def test_status_traz_arquivos_e_se_existem(self):
        por = {b['id']: b for b in S.chat_status(self.sem)['bots']}
        self.assertTrue(por['casas']['pronto'])
        self.assertEqual(por['casas']['arquivos'], [{'nome': 'casas.json', 'existe': True}])
        self.assertEqual(por['casas']['data'], '2030-01-05')                       # data vem do próprio arquivo
        self.assertFalse(por['macro']['pronto'])                                    # arquivo ausente: não finge que tem dados
        self.assertIsNone(por['macro']['data'])
        self.assertEqual([a['existe'] for a in por['analista']['arquivos']], [True, True])   # sintese.json e xp.json do fixture
        self.assertFalse(S.chat_status(None)['bots'][0]['pronto'])                  # sem pasta da semana

    def test_todo_bot_declara_arquivos(self):
        self.assertEqual(set(B.ARQUIVOS), set(B.BOTS))
        for k, nomes in B.ARQUIVOS.items():
            self.assertTrue(nomes and all(n.endswith('.json') for n in nomes), k)

    def test_fonte_inventada_de_bot_e_descartada(self):
        CH.RUNNER = lambda s, p, tempo=0: json.dumps({'resposta': 'x', 'fontes': ['F99', 'casas.json'], 'nao_verificado': []})
        r = S.chat_responder(self.sem, {'pergunta': 'AAAA3?', 'bot': 'casas'})
        self.assertEqual(r['fontes'], [])


if __name__ == '__main__':
    unittest.main()
