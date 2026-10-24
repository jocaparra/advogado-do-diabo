"""Roda os testes do front-end (tests/js/interface.test.mjs) em Node. Pula se não houver Node recente."""
import json
import os
import shutil
import subprocess
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ, 'tests', 'js', 'interface.test.mjs')


@unittest.skipUnless(shutil.which('node'), 'Node não encontrado')
class TesteInterfaceJS(unittest.TestCase):
    def test_front_end(self):
        r = subprocess.run(['node', SCRIPT], capture_output=True, text=True, timeout=60)
        if 'ERR_UNKNOWN_FILE_EXTENSION' in r.stderr or 'Cannot use import statement' in r.stderr:
            self.skipTest('Node sem detecção de módulo ES (use 22.7 ou mais novo)')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])['falhas'], [])


if __name__ == '__main__':
    unittest.main()
