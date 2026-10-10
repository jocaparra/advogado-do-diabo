"""Regressões de robustez: entradas malformadas e falhas de ambiente achadas na caça a bugs."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'src'))

import minha_carteira as M  # noqa: E402
import plano as PL  # noqa: E402
import pluggy_posicoes as P  # noqa: E402

RK = [{'posicao': 1, 'ticker': 'PRIO3', 'setor': 'Energia', 'nota': 6.0, 'acao_sugerida': 'comprar',
       'certeza': 'baixa', 'preco_atual': 60.0, 'data_cotacao': '2026-10-05',
       'componentes': {'catalisadores': 5, 'noticias': 5, 'momentum': 5, 'macro_eleicao': 5, 'valuation_upside': 5}}]


def pos(tk='PRIO3', q=1):
    return {'ticker': tk, 'quantidade': q, 'preco_medio': None, 'preco_atual': None}


class TesteCsv(unittest.TestCase):
    def test_tabulacao_do_excel(self):
        self.assertEqual(M.ler_posicoes('ticker\tquantidade\nPRIO3\t10\n')[0]['quantidade'], 10.0)

    def test_sufixo_sa_e_cabecalho_com_ponto(self):
        p = M.ler_posicoes('Código;Qtd.;Preço Médio\nPRIO3.SA;10;50\n')
        self.assertEqual((p[0]['ticker'], p[0]['quantidade'], p[0]['preco_medio']), ('PRIO3', 10.0, 50.0))

    def test_nan_e_inf_sao_rejeitados(self):
        for ruim in ('nan', 'inf', '-inf'):
            with self.assertRaises(ValueError):
                M.ler_posicoes(f'ticker;quantidade\nPRIO3;{ruim}\n')

    def test_milhar_en_us_quando_o_arquivo_usa_virgula(self):
        self.assertEqual(M.ler_posicoes('ticker,quantidade\nPRIO3,"1,000"\n')[0]['quantidade'], 1000.0)

    def test_linha_curta_tem_mensagem_clara(self):
        with self.assertRaisesRegex(ValueError, 'linha 2: faltam colunas'):
            M.ler_posicoes('ticker;quantidade;preco_medio\nPRIO3\n')


class TesteRankingMalformado(unittest.TestCase):
    def test_itens_invalidos_sao_ignorados_e_nota_texto_vira_none(self):
        rk = ['PRIO3', {'nota': 1}, dict(RK[0], nota='cinco'), None]
        r = M.cruzar([pos()], rk, ['lista'])
        self.assertEqual(r['posicoes'][0]['no_ranking'], True)
        self.assertIsNone(r['nota_media_ponderada'])
        self.assertEqual(r['carteira_xp_sem_posicao'], [])

    def test_pesos_xp_nao_dict(self):
        with tempfile.TemporaryDirectory() as d:
            arq = os.path.join(d, 'r.json')
            with open(arq, 'w') as f:
                json.dump({'ranking': RK, 'pesos_xp': [1, 2], 'data': None}, f)
            ranking, pesos, data = M.carregar_publico(arq)
        self.assertEqual((pesos, data), ({}, ''))


class TestePlano(unittest.TestCase):
    def test_aceita_virgula_e_maiuscula_rejeita_bool(self):
        p = PL.validar({'horizonte': ' Meses ', 'objetivo': 'RENDA', 'queda_max_pct': '15,5'})
        self.assertEqual((p['horizonte'], p['objetivo'], p['queda_max_pct']), ('meses', 'renda', 15.5))
        with self.assertRaises(ValueError):
            PL.validar({'horizonte': 'meses', 'objetivo': 'renda', 'queda_max_pct': True})

    def test_nota_fora_da_escala_ou_horizonte_invalido(self):
        c = dict(RK[0]['componentes'], momentum=99)
        self.assertIsNone(PL.nota_no_horizonte(c, 'meses'))
        self.assertIsNone(PL.nota_no_horizonte(dict(c, momentum=float('nan')), 'meses'))
        self.assertIsNone(PL.nota_no_horizonte(RK[0]['componentes'], 'decadas'))

    def test_gravar_privado_corrige_permissao_de_arquivo_existente(self):
        if os.name == 'nt':
            self.skipTest('permissões POSIX')
        with tempfile.TemporaryDirectory() as d:
            arq = os.path.join(d, 'c.json')
            with open(arq, 'w') as f:
                f.write('x' * 500)
            os.chmod(arq, 0o644)
            PL.gravar_privado(arq, {'a': 1})
            self.assertEqual(stat.S_IMODE(os.stat(arq).st_mode), 0o600)
            with open(arq) as f:
                self.assertEqual(json.load(f), {'a': 1})          # truncou o conteúdo antigo


class TestePluggy(unittest.TestCase):
    def test_quantidade_em_texto_negativa_e_itens_estranhos(self):
        invs = [{'type': 'EQUITY', 'code': 'PRIO3', 'quantity': '3,5', 'value': '10,2'},
                {'type': 'EQUITY', 'code': 'ITUB4', 'quantity': -3, 'value': 1},
                {'type': 'EQUITY', 'code': 'VALE3', 'quantity': float('nan'), 'value': 1}, 'lixo', None]
        pos_, ign = P.extrair_acoes(invs)
        self.assertEqual(pos_, [{'ticker': 'PRIO3', 'quantidade': 3.5, 'preco_atual': 10.2}])
        self.assertEqual(len(ign), 2)

    def test_respostas_inesperadas_viram_pluggyerro(self):
        with mock.patch.object(P, '_chamar', side_effect=[{}]):
            with self.assertRaises(P.PluggyErro):
                P.autenticar('a', 'b')
        with mock.patch.object(P, '_chamar', side_effect=[{'apiKey': 'k'}, []]):
            with self.assertRaises(P.PluggyErro):
                P.baixar('a', 'b', ['i'])
        with mock.patch.object(P, '_chamar', side_effect=[{'apiKey': 'k'}, {'results': None, 'totalPages': 'x'}]):
            self.assertEqual(P.baixar('a', 'b', ['i']), ([], []))


class TesteCli(unittest.TestCase):
    def rodar(self, *args, env=None):
        e = dict(os.environ, ADVOGADO_DO_DIABO_CONFIG='/nao/existe/c.json', ADVOGADO_DO_DIABO_PLANO='/nao/existe/p.json')
        e.pop('PLUGGY_CLIENT_ID', None)
        return subprocess.run([sys.executable, os.path.join(RAIZ, 'src', 'minha_carteira.py'), *args],
                              capture_output=True, text=True, env=e, cwd=env)

    def test_semana_sem_sintese_nao_da_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, 'semana_20260101'))
            with open(os.path.join(d, 'p.csv'), 'w') as f:
                f.write('ticker;quantidade\nPRIO3;1\n')
            r = self.rodar('--csv', os.path.join(d, 'p.csv'), '--semana', os.path.join(d, 'semana_20260101'))
        self.assertEqual(r.returncode, 1)
        self.assertNotIn('Traceback', r.stderr)
        self.assertIn('sintese.json', r.stderr)

    def test_csv_apontando_para_pasta_e_salvar_invalido(self):
        with tempfile.TemporaryDirectory() as d:
            rk = os.path.join(d, 'r.json')
            with open(rk, 'w') as f:
                json.dump({'ranking': RK}, f)
            r = self.rodar('--csv', d, '--ranking', rk)
            self.assertIn('é uma pasta', r.stderr)
            with open(os.path.join(d, 'p.csv'), 'w') as f:
                f.write('ticker;quantidade\nPRIO3;1\n')
            r = self.rodar('--csv', os.path.join(d, 'p.csv'), '--ranking', rk, '--salvar', os.path.join(d, 'nao', 'x.md'))
            self.assertEqual(r.returncode, 1)
            self.assertNotIn('Traceback', r.stderr)
            self.assertIn('Minha carteira', r.stdout)           # o relatório saiu mesmo assim


if __name__ == '__main__':
    unittest.main()
