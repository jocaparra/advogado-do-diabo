"""Dados abertos da CVM: DFP (anual), ITR (trimestral), FCA (tickers) e composição do capital.

Fonte primária e gratuita: https://dados.cvm.gov.br/dados/CIA_ABERTA. Tudo é calculado em código,
sem LLM e sem busca na web. Os arquivos ficam em cache local (.cache/cvm/, ignorado pelo git).
"""
import csv
import datetime as dt
import io
import os
import re
import time
import urllib.request
import zipfile

BASE_URL = 'https://dados.cvm.gov.br/dados/CIA_ABERTA'
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.environ.get('CARTEIRA_CACHE', os.path.join(RAIZ, '.cache', 'cvm'))
csv.field_size_limit(10 ** 8)


class SemDadoCVM(Exception):
    """Emissor sem demonstrações na CVM (ex.: BDR de empresa estrangeira)."""


def baixar(rel, max_idade_dias=7):
    """Baixa `rel` (caminho relativo a BASE_URL) para o cache e devolve o caminho local.
    Reaproveita o arquivo se tiver menos de `max_idade_dias` dias."""
    os.makedirs(CACHE, exist_ok=True)
    destino = os.path.join(CACHE, rel.replace('/', '__'))
    if os.path.exists(destino) and (time.time() - os.path.getmtime(destino)) < max_idade_dias * 86400:
        return destino
    req = urllib.request.Request(f'{BASE_URL}/{rel}', headers={'User-Agent': 'advogado-do-diabo/1.0 (pesquisa)'})
    tmp = destino + '.parte'
    try:
        with urllib.request.urlopen(req, timeout=180) as r, open(tmp, 'wb') as f:
            while True:
                bloco = r.read(1 << 20)
                if not bloco:
                    break
                f.write(bloco)
        os.replace(tmp, destino)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        if os.path.exists(destino):  # melhor um cache antigo do que nada, o aviso fica no relatório
            return destino
        raise
    return destino


def _linhas(zip_path, nome):
    with zipfile.ZipFile(zip_path) as z, z.open(nome) as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, encoding='latin-1', newline=''), delimiter=';')


def _tem(zip_path, nome):
    with zipfile.ZipFile(zip_path) as z:
        return nome in z.namelist()


def url_arquivo(rel):
    return f'{BASE_URL}/{rel}'


# ---------------------------------------------------------------- cadastro de tickers
def mapa_tickers(ano):
    """ticker -> {cnpj, nome, valor_mobiliario, segmento}, pela FCA (valor mobiliário) mais recente."""
    rel = f'DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip'
    z = baixar(rel, 30)
    versao = {}
    for r in _linhas(z, f'fca_cia_aberta_valor_mobiliario_{ano}.csv'):
        t = r['Codigo_Negociacao'].strip().upper()
        if not t or r['Mercado'] != 'Bolsa':
            continue
        chave = (r['Data_Referencia'], int(r['Versao'] or 0))
        if t not in versao or chave > versao[t][0]:
            versao[t] = (chave, {'cnpj': r['CNPJ_Companhia'], 'nome': r['Nome_Empresarial'],
                                 'valor_mobiliario': r['Valor_Mobiliario'], 'segmento': r['Segmento'],
                                 'composicao_unit': r.get('Composicao_BDR_Unit', '')})
    return {t: v[1] for t, v in versao.items()}


def manual():
    p = os.path.join(RAIZ, 'dados', 'mapa_tickers_manual.json')
    if not os.path.exists(p):
        return {}
    import json
    with open(p, encoding='utf-8') as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith('_')}


def cadastro(cnpjs):
    """CNPJ -> {cd_cvm, setor, situacao, controle} pelo cadastro de companhias abertas."""
    z = baixar('CAD/DADOS/cad_cia_aberta.csv', 30)
    out = {}
    with open(z, encoding='latin-1', newline='') as fh:
        for r in csv.DictReader(fh, delimiter=';'):
            if r['CNPJ_CIA'] in cnpjs:
                out[r['CNPJ_CIA']] = {'cd_cvm': r['CD_CVM'], 'setor': r['SETOR_ATIV'], 'situacao': r['SIT'],
                                      'controle': r['CONTROLE_ACIONARIO']}
    return out


# ---------------------------------------------------------------- demonstrações
DEMONSTRACOES = ('DRE', 'BPA', 'BPP', 'DVA', 'DFC_MI')


def _num(r):
    try:
        v = float(r['VL_CONTA'])
    except (ValueError, KeyError):
        return None
    if r.get('CD_CONTA', '').startswith('3.99'):  # lucro por ação já vem em unidades da moeda
        return v
    return v * (1000.0 if r.get('ESCALA_MOEDA', 'MIL') == 'MIL' else 1.0)


def carregar_empresas(cnpjs, ano_atual):
    """Lê DFP (3 exercícios) e ITR (ano corrente e anterior) de todas as empresas em uma passada.

    Devolve {cnpj: ({demo: {escopo: {(dt_ini, dt_fim): {cd_conta: (valor, descricao, dt_refer, versao, doc)}}}},
                    {'moeda': str, 'documentos': {(tipo, dt_refer, versao): url}})}.
    Para cada período vale a versão mais recente do documento (reapresentações substituem)."""
    cnpjs = set(cnpjs)
    docs = [('DFP', 'dfp', f'DOC/DFP/DADOS/dfp_cia_aberta_{a}.zip', a) for a in range(ano_atual - 3, ano_atual + 1)]
    docs += [('ITR', 'itr', f'DOC/ITR/DADOS/itr_cia_aberta_{a}.zip', a) for a in (ano_atual - 1, ano_atual)]
    out = {c: ({d: {'con': {}, 'ind': {}} for d in DEMONSTRACOES}, {'moeda': None, 'documentos': {}}) for c in cnpjs}
    for tipo, pref, rel, ano in docs:
        try:
            z = baixar(rel, 7 if ano >= ano_atual - 1 else 90)
        except Exception:
            continue  # ano ainda não publicado
        for demo in DEMONSTRACOES:
            for escopo in ('con', 'ind'):
                nome = f'{pref}_cia_aberta_{demo}_{escopo}_{ano}.csv'
                if not _tem(z, nome):
                    continue
                for r in _linhas(z, nome):
                    c = r['CNPJ_CIA']
                    if c not in cnpjs:
                        continue
                    v = _num(r)
                    if v is None:
                        continue
                    saida, meta = out[c]
                    meta['moeda'] = meta['moeda'] or r.get('MOEDA')
                    per = (r.get('DT_INI_EXERC', ''), r['DT_FIM_EXERC'])
                    ver = int(r['VERSAO'] or 0)
                    destino = saida[demo][escopo].setdefault(per, {})
                    atual = destino.get(r['CD_CONTA'])
                    if atual is None or (r['DT_REFER'], ver) > (atual[2], atual[3]):
                        destino[r['CD_CONTA']] = (v, r['DS_CONTA'], r['DT_REFER'], ver, f'{tipo} {ano}')
                    meta['documentos'][(tipo, r['DT_REFER'], ver)] = url_arquivo(rel)
    return out


def capital(cnpj, ano_atual):
    """Ações (total, tesouraria) do documento mais recente (ITR ou DFP)."""
    melhor = None
    for pref, rel_t in (('itr', 'ITR'), ('dfp', 'DFP')):
        for ano in (ano_atual, ano_atual - 1):
            rel = f'DOC/{rel_t}/DADOS/{pref}_cia_aberta_{ano}.zip'
            try:
                z = baixar(rel, 7)
            except Exception:
                continue
            nome = f'{pref}_cia_aberta_composicao_capital_{ano}.csv'
            if not _tem(z, nome):
                continue
            for r in _linhas(z, nome):
                if r['CNPJ_CIA'] != cnpj:
                    continue
                chave = (r['DT_REFER'], int(r['VERSAO'] or 0))
                if melhor is None or chave > melhor[0]:
                    f = lambda k: float(r[k] or 0)
                    melhor = (chave, {'dt_refer': r['DT_REFER'], 'versao': int(r['VERSAO'] or 0),
                                      'total': f('QT_ACAO_TOTAL_CAP_INTEGR'), 'ordinarias': f('QT_ACAO_ORDIN_CAP_INTEGR'),
                                      'preferenciais': f('QT_ACAO_PREF_CAP_INTEGR'),
                                      'tesouraria': f('QT_ACAO_TOTAL_TESOURO'), 'fonte': url_arquivo(rel)})
    return melhor[1] if melhor else None


def ult_dia(dt_iso):
    return dt.date.fromisoformat(dt_iso)
