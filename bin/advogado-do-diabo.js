#!/usr/bin/env node
// Lançador: roda src/minha_carteira.py com o Python 3 da máquina. Sem dependências.
'use strict';
const { spawnSync } = require('child_process');
const path = require('path');

const script = path.join(__dirname, '..', 'src', 'minha_carteira.py');

function acharPython() {
  // [comando, argumentos extras]; "py -3" é o lançador do Python no Windows
  for (const [cmd, extra] of [['python3', []], ['python', []], ['py', ['-3']]]) {
    const r = spawnSync(cmd, [...extra, '-c', 'import sys; print(sys.version_info >= (3, 9))'], { encoding: 'utf8' });
    if (r.status === 0 && r.stdout.trim() === 'True') return [cmd, extra];
  }
  return null;
}

const py = acharPython();
if (!py) {
  console.error('advogado-do-diabo precisa do Python 3.9 ou mais novo (https://www.python.org/downloads/).');
  process.exit(1);
}
const r = spawnSync(py[0], [...py[1], script, ...process.argv.slice(2)], { stdio: 'inherit', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
process.exit(r.status === null ? 1 : r.status);
