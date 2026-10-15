"""Confere decisao_sombra.json contra evidencias.json: o decisor interpreta, o código calcula.

uso: python src/conferir_decisao.py <pasta_da_semana>

Erros (saída 1): schema inválido; papel fora de evidencias.json; id de evidência inexistente; confiança "alta"
quando a confiança dos dados do papel não é alta; "comprar" sem argumento contrário ou sem invalidador; papel
do ranking sem decisão. Avisos: número escrito em texto que não bate com nenhum fato citado (o modelo não deve
inventar nem recalcular números: deve citar o id). Grava conferencia_decisao.json.
"""
import json
import os
import re
import sys

import carteira as C
import validar

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM = re.compile(r'(?<![\w.])(-?\d+(?:[.,]\d+)?)(\s*(?:dias|dia|pregões|pregoes|semanas|semana|meses|mês|anos|ano)\b)?', re.I)


def _numeros(txt):
    out = []
    for numero, unidade_tempo in NUM.findall(txt or ''):
        if unidade_tempo:                   # "30 dias", "2 semanas": prazo, não fato
            continue
        try:
            out.append(float(numero.replace(',', '.')))
        except ValueError:
            pass
    return out


def conferir(decisao, evid):
    erros, avisos = [], []
    with open(os.path.join(RAIZ, 'schemas', 'decisao_sombra.schema.json'), encoding='utf-8') as f:
        erros += [f'schema: {e}' for e in validar.validar(decisao, json.load(f))]
    if erros:
        return erros, avisos
    fatos, papeis = evid['fatos'], evid['por_ticker']
    vistos = set()
    for d in decisao['decisoes']:
        t = d['ticker']
        vistos.add(t)
        if t not in papeis:
            erros.append(f'{t}: papel fora de evidencias.json')
            continue
        faltam = [i for i in d['evidencias_ids'] if i not in fatos]
        if faltam:
            erros.append(f'{t}: ids de evidência inexistentes: {faltam}')
        if d['confianca'] == 'alta' and papeis[t]['confianca_dados'] != 'alta':
            erros.append(f"{t}: confiança 'alta' com dados de confiança '{papeis[t]['confianca_dados']}'")
        if d['acao'] == 'comprar' and papeis[t]['dados_ausentes'] and d['confianca'] != 'baixa' and not d['dados_ausentes']:
            erros.append(f'{t}: comprar com dados ausentes no consolidado e sem declará-los em dados_ausentes')
        citados = [fatos[i] for i in d['evidencias_ids'] if i in fatos and isinstance(fatos[i], (int, float))]
        textos = [d['tese']] + d['argumentos_contrarios'] + d['invalidadores']
        for tx in textos:
            for n in _numeros(tx):
                if not any(abs(n - c) <= max(0.06, abs(c) * 0.005) for c in citados) and n not in (1.0, 2.0, 3.0, 4.0, 5.0) \
                        and not (1900 <= n <= 2100):
                    avisos.append(f'{t}: número {n:g} no texto não bate com nenhum fato citado em evidencias_ids')
    faltam = sorted(set(papeis) - vistos)
    if faltam:
        erros.append(f'papéis do ranking sem decisão: {faltam}')
    return erros, avisos


def main():
    pasta = C.pasta_semana(sys.argv[:2])
    dec = C.ler(os.path.join(pasta, 'decisao_sombra.json'), None)
    ev = C.ler(os.path.join(pasta, 'evidencias.json'), None)
    if dec is None or ev is None:
        sys.exit('faltam decisao_sombra.json e/ou evidencias.json (rode consolidar_evidencias.py e o agente decisor)')
    erros, avisos = conferir(dec, ev)
    with open(os.path.join(pasta, 'conferencia_decisao.json'), 'w', encoding='utf-8') as f:
        json.dump({'erros': erros, 'avisos': avisos}, f, ensure_ascii=False, indent=1)
    print(f'conferência da decisão: {len(erros)} erro(s), {len(avisos)} aviso(s)')
    for e in erros:
        print('  ERRO ', e)
    for a in avisos[:15]:
        print('  aviso', a)
    sys.exit(1 if erros else 0)


if __name__ == '__main__':
    main()
