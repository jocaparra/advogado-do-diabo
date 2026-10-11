"""Testes da memória tipada de aprendizado (offline, pasta temporária)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import memoria as M  # noqa: E402


class TesteMemoria(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.arq = os.path.join(self.tmp.name, 'a', 'memoria.jsonl')

    def tearDown(self):
        self.tmp.cleanup()

    def test_item_nasce_nao_validado_e_conclusao_nao_nasce_direta(self):
        it = M.novo('hipotese', 'h1', setor='Energia', arquivo=self.arq)
        self.assertEqual(it['status'], 'nao_validado')
        with self.assertRaises(ValueError):
            M.novo('conclusao_validada', 'x', arquivo=self.arq)
        with self.assertRaises(ValueError):
            M.novo('hipotese', 'h1', arquivo=self.arq)  # duplicata
        with self.assertRaises(ValueError):
            M.novo('ordem', 'x', arquivo=self.arq)

    def test_promocao_exige_amostra_semanas_e_aprovacao(self):
        iid = M.novo('hipotese', 'h', arquivo=self.arq)['id']
        for obs, sem, quem in [(29, 3, 'usuario'), (30, 2, 'usuario'), (30, 3, 'modelo'), (500, 1, 'usuario')]:
            with self.assertRaises(ValueError, msg=(obs, sem, quem)):
                M.promover(iid, obs, sem, quem, arquivo=self.arq)
        self.assertEqual(M.estado(self.arq)[iid]['status'], 'nao_validado')
        it = M.promover(iid, 30, 3, 'usuario', arquivo=self.arq)
        self.assertEqual((it['status'], it['tipo'], it['versao']), ('validado', 'conclusao_validada', 2))

    def test_log_preserva_historico_e_refutado_nao_volta(self):
        iid = M.novo('hipotese', 'h', arquivo=self.arq)['id']
        M.refutar(iid, 'não se confirmou', arquivo=self.arq)
        eventos = [e for e in M.ler_eventos(self.arq) if e['id'] == iid]
        self.assertEqual([e['versao'] for e in eventos], [1, 2])      # nada reescrito
        self.assertEqual(M.estado(self.arq)[iid]['status'], 'refutado')
        with self.assertRaises(ValueError):
            M.promover(iid, 100, 5, 'usuario', arquivo=self.arq)
        self.assertEqual(M.buscar(setor=None, ticker='X', arquivo=self.arq), [])

    def test_buscar_ordena_por_validacao_e_filtra_irrelevantes(self):
        a = M.novo('hipotese', 'a', setor='Energia', arquivo=self.arq)['id']
        b = M.novo('experiencia', 'b', setor='Energia', arquivo=self.arq)['id']
        M.novo('experiencia', 'c', setor='Bancos', arquivo=self.arq)
        M.promover(b, 40, 4, 'usuario', arquivo=self.arq)
        achados = [i['id'] for i in M.buscar(setor='Energia', arquivo=self.arq)]
        self.assertEqual(achados, [b, a])                              # validado antes, Bancos fora
        self.assertEqual(M.buscar(arquivo=self.arq), [])               # sem contexto, nada
        self.assertIn('VALIDADO', M.bloco_markdown(M.buscar(setor='Energia', arquivo=self.arq)))

    def test_importar_retrospectiva_e_idempotente(self):
        ret = os.path.join(self.tmp.name, 'r.json')
        with open(ret, 'w', encoding='utf-8') as f:
            json.dump({'semana_avaliada': '2026-10-05', 'hipoteses_para_testar': [
                {'id': 'H1', 'texto': 'x', 'n_atual': 1}, {'id': 'H2', 'texto': 'y', 'n_atual': 3}]}, f)
        criados, pulados = M.importar_retrospectiva(ret, self.arq)
        self.assertEqual((len(criados), pulados), (2, []))
        criados, pulados = M.importar_retrospectiva(ret, self.arq)
        self.assertEqual((len(criados), pulados), (0, ['H1', 'H2']))

    def test_linha_corrompida_nao_derruba(self):
        os.makedirs(os.path.dirname(self.arq))
        with open(self.arq, 'w', encoding='utf-8') as f:
            f.write('{lixo\n')
        M.novo('fato', 'ok', arquivo=self.arq)
        self.assertEqual(len(M.estado(self.arq)), 1)

    def test_tags_como_texto_nao_vira_letras(self):
        it = M.novo('fato', 'x', tags='regime_eleicao', arquivo=self.arq)
        self.assertEqual(it['contexto']['tags'], ['regime_eleicao'])

    def test_linhas_incompletas_ou_forjadas_nao_quebram_nem_promovem(self):
        os.makedirs(os.path.dirname(self.arq))
        linhas = [{'id': 'a1', 'texto': 'sem status'},
                  {'id': 'a2', 'texto': 'forjado', 'status': 'validado', 'tipo': 'conclusao_validada', 'versao': 1,
                   'contexto': {'setor': 'X', 'tags': None}, 'atualizado_em': '2026-01-01'},
                  {'id': 'a3', 'texto': 'legitimo', 'status': 'validado', 'tipo': 'conclusao_validada', 'versao': 2,
                   'contexto': {'setor': 'X'}, 'atualizado_em': '2026-01-02',
                   'evidencia': {'observacoes': 40, 'semanas': 5, 'aprovado_por': 'usuario'}},
                  [1, 2], 'solto', {'id': 5}, {'id': 'a4', 'status': 'inventado', 'contexto': {'setor': 'X'}}]
        with open(self.arq, 'w', encoding='utf-8') as f:
            f.write('\n'.join(json.dumps(x) for x in linhas) + '\n')
        est = M.estado(self.arq)
        self.assertEqual(sorted(est), ['a1', 'a2', 'a3', 'a4'])
        self.assertEqual(est['a2']['status'], 'nao_validado')      # validado sem evidência não vale
        self.assertEqual(est['a3']['status'], 'validado')
        self.assertEqual(est['a4']['status'], 'nao_validado')      # status inventado vira o mais conservador
        achados = M.buscar(setor='X', arquivo=self.arq)
        self.assertEqual(achados[0]['id'], 'a3')                   # validado de verdade vem primeiro
        self.assertIn('NÃO VALIDADO', M.bloco_markdown(achados))
        M.refutar('a1', 'teste', arquivo=self.arq)                 # item incompleto ainda pode ser atualizado


if __name__ == '__main__':
    unittest.main()
