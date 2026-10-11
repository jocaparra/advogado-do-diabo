"""Utilitários comuns aos scripts: localização dos dados, datas e leitura dos JSON.

Organização das pastas (a partir de uma raiz de trabalho):

    xp_mensal/AAAAMM/xp.json    dados do PDF da XP, uma vez por mês (agente leitor)
    semana_AAAAMMDD/*.json      coleta e análise de cada semana
    historico_carteira.json     ranking de cada semana, para comparar semana a semana
"""
import glob
import json
import os
import re
import sys

MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro',
         'outubro', 'novembro', 'dezembro']


def pasta_semana(argv=None):
    """Lê a pasta da semana da linha de comando e devolve o caminho absoluto."""
    argv = sys.argv if argv is None else argv
    if len(argv) != 2:
        sys.exit(f'uso: python {os.path.relpath(argv[0])} <pasta_da_semana>  (ex.: semana_20261005)')
    d = os.path.abspath(argv[1])
    if not os.path.isdir(d):
        sys.exit(f'pasta não encontrada: {d}')
    return d


def data_semana(pasta):
    """(ano, mes, dia) tirados do nome semana_AAAAMMDD."""
    m = re.search(r'semana_(\d{4})(\d{2})(\d{2})', pasta)
    if not m:
        sys.exit('o nome da pasta precisa seguir o formato semana_AAAAMMDD')
    return tuple(int(x) for x in m.groups())


def data_br(iso):
    """'2026-10-05' -> '05/10/2026'."""
    a, m, d = iso[:10].split('-')
    return f'{d}/{m}/{a}'


def mes_extenso(iso):
    """'2026-10-01' -> 'outubro de 2026'."""
    return f'{MESES[int(iso[5:7]) - 1]} de {iso[:4]}'


def arquivo_xp(pasta):
    """xp.json da semana: o da própria pasta (se existir) ou o do relatório mensal mais recente
    publicado até a data da semana."""
    local = os.path.join(pasta, 'xp.json')
    if os.path.exists(local):
        return local
    a, m, d = data_semana(pasta)
    limite = f'{a:04d}-{m:02d}-{d:02d}'
    candidatos = []
    for p in glob.glob(os.path.join(os.path.dirname(pasta), 'xp_mensal', '*', 'xp.json')):
        with open(p, encoding='utf-8') as f:
            dr = json.load(f).get('data_relatorio', '')
        if dr and dr <= limite:
            candidatos.append((dr, p))
    if not candidatos:
        sys.exit('xp.json não encontrado: rode o agente leitor sobre o PDF do mês (xp_mensal/AAAAMM/xp.json)')
    return max(candidatos)[1]


def arquivo_historico(pasta):
    p = os.path.join(os.path.dirname(pasta), 'historico_carteira.json')
    return p if os.path.exists(p) else None


def ler(caminho, padrao=None):
    try:
        with open(caminho, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        if padrao is not None:
            return padrao
        raise


def semana_anterior(pasta):
    """Ranking da semana imediatamente anterior ao da pasta, ou None na primeira execução."""
    h = arquivo_historico(pasta)
    if not h:
        return None
    a, m, d = data_semana(pasta)
    atual = f'{a:04d}-{m:02d}-{d:02d}'
    anteriores = [s for s in ler(h)['semanas'] if s['data'] < atual]
    return max(anteriores, key=lambda s: s['data']) if anteriores else None
