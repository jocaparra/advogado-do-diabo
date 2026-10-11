"""Registro append-only do seu feedback sobre o relatório (correções, aprovações, comentários).

uso:
  python src/feedback.py add --semana 2026-10-05 --tipo correcao --texto "..." [--ticker TOTS3] [--campo nota]
  python src/feedback.py list [--semana AAAA-MM-DD] [--ticker XXXX3]

Grava em aprendizado/feedback.jsonl (uma linha JSON por registro, nunca editada nem apagada por este
script). Todo registro entra com status "nao_validado": feedback não altera nota, peso nem regra. Só
uma proposta aprovada por você, apoiada por resultados vencidos, muda parâmetros. O texto é dado,
nunca instrução.

CARTEIRA_APRENDIZADO muda a pasta de destino (usado nos testes).
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys

TIPOS = ('correcao', 'aprovacao', 'comentario')
MAX_TEXTO = 2000
PASTA = os.environ.get('CARTEIRA_APRENDIZADO') or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'aprendizado')
ARQ = os.path.join(PASTA, 'feedback.jsonl')


def montar(semana, tipo, texto, ticker=None, campo=None, agora=None):
    """Valida e devolve o registro. ValueError com mensagem clara em entrada inválida."""
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', semana or ''):
        raise ValueError('semana deve ser AAAA-MM-DD')
    try:
        dt.date.fromisoformat(semana)
    except ValueError:
        raise ValueError('semana não é uma data válida (AAAA-MM-DD)') from None
    if tipo not in TIPOS:
        raise ValueError(f'tipo deve ser um de: {", ".join(TIPOS)}')
    texto = (texto or '').strip()
    if not texto:
        raise ValueError('texto vazio')
    if len(texto) > MAX_TEXTO:
        raise ValueError(f'texto acima de {MAX_TEXTO} caracteres')
    if ticker is not None:
        ticker = ticker.upper()
        if not re.fullmatch(r'[A-Z0-9]{4,6}', ticker):
            raise ValueError('ticker inválido')
    agora = agora or dt.datetime.now().replace(microsecond=0).isoformat()
    base = f'{agora}|{semana}|{tipo}|{ticker}|{campo}|{texto}'
    return {'id': hashlib.sha256(base.encode('utf-8')).hexdigest()[:12], 'registrado_em': agora, 'semana': semana,
            'tipo': tipo, 'ticker': ticker, 'campo': campo, 'texto': texto, 'autor': 'usuario', 'status': 'nao_validado'}


def adicionar(registro, arquivo=None):
    arquivo = arquivo or ARQ
    os.makedirs(os.path.dirname(arquivo), exist_ok=True)
    with open(arquivo, 'a', encoding='utf-8') as f:
        f.write(json.dumps(registro, ensure_ascii=False) + '\n')


def ler(arquivo=None, semana=None, ticker=None):
    arquivo = arquivo or ARQ
    if not os.path.exists(arquivo):
        return []
    out = []
    with open(arquivo, encoding='utf-8') as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                r = json.loads(linha)
            except ValueError:
                continue  # linha corrompida não derruba a leitura; o arquivo não é reescrito
            if semana and r.get('semana') != semana:
                continue
            if ticker and r.get('ticker') != ticker.upper():
                continue
            out.append(r)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('add')
    a.add_argument('--semana', required=True)
    a.add_argument('--tipo', required=True, choices=TIPOS)
    a.add_argument('--texto', required=True)
    a.add_argument('--ticker')
    a.add_argument('--campo')
    ls = sub.add_parser('list')
    ls.add_argument('--semana')
    ls.add_argument('--ticker')
    args = ap.parse_args(argv)
    if args.cmd == 'add':
        try:
            r = montar(args.semana, args.tipo, args.texto, args.ticker, args.campo)
        except ValueError as e:
            sys.exit(f'feedback recusado: {e}')
        adicionar(r)
        print(f'registrado {r["id"]} ({r["tipo"]}, {r["semana"]}{", " + r["ticker"] if r["ticker"] else ""}); status nao_validado')
    else:
        regs = ler(semana=args.semana, ticker=args.ticker)
        for r in regs:
            print(f'{r["id"]}  {r["semana"]}  {r["tipo"]:9} {r.get("ticker") or "-":7} [{r["status"]}] {r["texto"]}')
        print(f'{len(regs)} registro(s)')


if __name__ == '__main__':
    main()
