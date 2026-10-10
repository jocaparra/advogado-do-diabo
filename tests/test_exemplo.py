"""Teste de fumaça: gera figuras e PDF de uma semana local (pasta exemplo/, não versionada).

Pula se exemplo/ não existir (o repositório não distribui dados de semana).

uso: python -m unittest discover tests
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXEMPLO = os.path.join(RAIZ, 'exemplo')


class TesteExemplo(unittest.TestCase):
    @unittest.skipUnless(os.path.isdir(os.path.join(EXEMPLO, 'semana_20261005')), 'sem semana local em exemplo/')
    def test_gera_figuras_e_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            for nome in ('semana_20261005', 'xp_mensal'):
                shutil.copytree(os.path.join(EXEMPLO, nome), os.path.join(tmp, nome))
            semana = os.path.join(tmp, 'semana_20261005')
            for script in ('gerar_graficos.py', 'montar_relatorio.py'):
                r = subprocess.run([sys.executable, os.path.join(RAIZ, 'src', script), semana],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            for n in range(1, 11):
                self.assertTrue(os.path.exists(os.path.join(semana, 'graficos', f'fig{n}.png')), f'fig{n}')
            self.assertGreater(os.path.getsize(os.path.join(semana, 'relatorio.pdf')), 100_000)

    def test_semana_sem_xp_mensal_falha_com_mensagem(self):
        with tempfile.TemporaryDirectory() as tmp:
            semana = os.path.join(tmp, 'semana_20261005')
            os.makedirs(semana)
            r = subprocess.run([sys.executable, os.path.join(RAIZ, 'src', 'gerar_graficos.py'), semana],
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('xp.json', r.stderr)


if __name__ == '__main__':
    unittest.main()
