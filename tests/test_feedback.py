"""Testes do registro de feedback (offline, pasta temporária)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import feedback as F  # noqa: E402


class TesteFeedback(unittest.TestCase):
    def test_registro_valido_entra_nao_validado(self):
        r = F.montar('2026-10-05', 'correcao', ' TOTS3 deveria ser compra ', 'tots3', 'acao_sugerida', agora='2026-10-11T10:00:00')
        self.assertEqual(r['status'], 'nao_validado')
        self.assertEqual(r['ticker'], 'TOTS3')
        self.assertEqual(r['texto'], 'TOTS3 deveria ser compra')

    def test_entradas_invalidas_sao_recusadas(self):
        for args in [('05/10/2026', 'correcao', 'x'), ('2026-10-05', 'ordem', 'x'), ('2026-10-05', 'correcao', '  '),
                     ('2026-10-05', 'correcao', 'x' * 2001), ('2026-13-45', 'correcao', 'x')]:
            with self.assertRaises(ValueError, msg=str(args)):
                F.montar(*args)
        with self.assertRaises(ValueError):
            F.montar('2026-10-05', 'correcao', 'x', ticker='../etc')

    def test_append_nao_reescreve_e_filtra(self):
        with tempfile.TemporaryDirectory() as tmp:
            arq = os.path.join(tmp, 'sub', 'feedback.jsonl')
            F.adicionar(F.montar('2026-10-05', 'comentario', 'a', 'AAAA3', agora='2026-10-11T10:00:00'), arq)
            antes = open(arq, encoding='utf-8').read()
            F.adicionar(F.montar('2026-10-12', 'aprovacao', 'b', agora='2026-10-12T10:00:00'), arq)
            depois = open(arq, encoding='utf-8').read()
            self.assertTrue(depois.startswith(antes))
            self.assertEqual(len(F.ler(arq)), 2)
            self.assertEqual(len(F.ler(arq, semana='2026-10-05')), 1)
            self.assertEqual(len(F.ler(arq, ticker='aaaa3')), 1)

    def test_linha_corrompida_nao_derruba_leitura(self):
        with tempfile.TemporaryDirectory() as tmp:
            arq = os.path.join(tmp, 'f.jsonl')
            with open(arq, 'w', encoding='utf-8') as f:
                f.write('{lixo\n{"semana": "2026-10-05", "texto": "ok"}\n')
            self.assertEqual(len(F.ler(arq)), 1)

    def test_data_impossivel_tem_mensagem_clara(self):
        with self.assertRaisesRegex(ValueError, 'data válida'):
            F.montar('2026-02-30', 'comentario', 'x')


if __name__ == '__main__':
    unittest.main()
