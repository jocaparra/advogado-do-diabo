"""Dados da estratégia quantitativa: universo (B3), preços com proventos (Yahoo), CDI (BCB) e
fundamentos point-in-time (CVM). Tudo em código, sem LLM. Cache local em .cache/quant/ (fora do git).

Point-in-time: cada demonstração vale a partir da data em que a CVM a recebeu (DT_RECEB), na primeira
versão entregue; reapresentações posteriores não entram no passado (evita olhar o futuro).
"""
import base64
import datetime as dt
import json
import os
import re
import time
import urllib.parse
import urllib.request

import cvm

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(RAIZ, '.cache', 'quant')
UA = {'User-Agent': 'Mozilla/5.0'}
B3_URL = 'https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{}'
YAHOO = 'https://query1.finance.yahoo.com/v8/finance/chart/{s}?range={r}&interval=1d&events=div%2Csplits'
BCB = 'https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial={a}&dataFinal={b}'


def _cache(nome, max_horas, buscar):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, nome)
    if os.path.exists(p) and (time.time() - os.path.getmtime(p)) < max_horas * 3600:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    dado = buscar()
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(dado, f)
    return dado


def _get(url, timeout=40):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.load(r)


# ---------------------------------------------------------------- universo
def universo(indice='IBXX'):
    """Composição atual do índice na B3 (IBXX = IBrX 100, IBOV = Ibovespa): [{ticker, nome, peso_pct}]."""
    def buscar():
        p = base64.b64encode(json.dumps({'language': 'pt-br', 'pageNumber': 1, 'pageSize': 200,
                                         'index': indice, 'segment': '1'}).encode()).decode()
        d = _get(B3_URL.format(p))
        return {'data': d['header']['date'],
                'itens': [{'ticker': r['cod'], 'nome': r['asset'], 'peso_pct': float(r['part'].replace('.', '').replace(',', '.'))}
                          for r in d['results']]}
    return _cache(f'universo_{indice}_{dt.date.today().isoformat()}.json', 24, buscar)


# ---------------------------------------------------------------- preços
def serie_yahoo(simbolo, periodo='11y'):
    """{'datas': [iso], 'close': [...], 'adj': [...], 'volume': [...], 'div': {iso: valor}, 'splits': {iso: razão}}.
    close é ajustado por desdobramentos; adj também por proventos (retorno total)."""
    def buscar():
        time.sleep(0.15)
        d = _get(YAHOO.format(s=urllib.parse.quote(simbolo), r=periodo))
        res = d['chart']['result'][0]
        off = res.get('meta', {}).get('gmtoffset', 0) or 0
        iso = lambda t: (dt.datetime.fromtimestamp(t, dt.timezone.utc) + dt.timedelta(seconds=off)).date().isoformat()
        q = res['indicators']['quote'][0]
        adj = (res['indicators'].get('adjclose') or [{}])[0].get('adjclose') or q['close']
        out = {'datas': [], 'close': [], 'adj': [], 'volume': []}
        for t, c, a, v in zip(res['timestamp'], q['close'], adj, q.get('volume') or [0] * len(adj)):
            if c is None or a is None:
                continue
            di = iso(t)
            if out['datas'] and out['datas'][-1] == di:  # ponto intradiário duplicado
                for k in ('close', 'adj', 'volume'):
                    out[k].pop()
                out['datas'].pop()
            out['datas'].append(di)
            out['close'].append(c)
            out['adj'].append(a)
            out['volume'].append(v or 0)
        ev = res.get('events') or {}
        out['div'] = {iso(x['date']): x['amount'] for x in (ev.get('dividends') or {}).values()}
        out['splits'] = {iso(x['date']): x['numerator'] / x['denominator'] for x in (ev.get('splits') or {}).values()
                         if x.get('denominator')}
        return out
    return _cache(f'yahoo_{simbolo}_{periodo}_{dt.date.today().isoformat()}.json', 24, buscar)


def cdi_diario(inicio, fim):
    """{data_iso: taxa_diaria} do CDI (SGS 12 do BCB, % a.d. convertido para fração). Pede em blocos de
    2 anos (a API recusa janelas longas) e repete a chamada se vier resposta que não é JSON."""
    def pedir(a, b):
        for tentativa in range(5):
            try:
                return _get(BCB.format(a=a.strftime('%d/%m/%Y'), b=b.strftime('%d/%m/%Y')), 90)
            except (ValueError, OSError):  # resposta HTML, 502 ou queda de rede
                time.sleep(3 * (tentativa + 1))
        raise RuntimeError(f'BCB SGS 12 sem resposta válida para {a} a {b}')

    def buscar():
        out = {}
        a = inicio
        while a <= fim:
            b = min(dt.date(a.year + 2, a.month, 1) - dt.timedelta(days=1), fim)
            for r in pedir(a, b):
                out[dt.datetime.strptime(r['data'], '%d/%m/%Y').date().isoformat()] = float(r['valor']) / 100
            a = b + dt.timedelta(days=1)
        return out
    return _cache(f'cdi_{inicio}_{fim}.json', 24 * 7, buscar)


# ---------------------------------------------------------------- cadastro
def tickers_para_cnpj(tickers):
    """ticker -> {cnpj, nome, valor_mobiliario, composicao_unit} (FCA mais recente + correções manuais)."""
    mapa = {}
    for ano in (dt.date.today().year, dt.date.today().year - 1, dt.date.today().year - 2):
        try:
            for t, v in cvm.mapa_tickers(ano).items():
                mapa.setdefault(t, v)
        except Exception:
            continue
    for t, v in cvm.manual().items():
        mapa[t] = v
    return {t: mapa[t] for t in tickers if t in mapa}


def acoes_por_unit(composicao):
    """'1 ação ordinária e 4 preferenciais' ou '1 KLBN3 + 4 KLBN4' -> 5 (ações por unit). None se não der para ler."""
    txt = composicao or ''
    nums = [int(n) for n in re.findall(r'(\d+)\s*(?:a[cç][aã]o|a[cç][oõ]es|ON|PN|ordin|prefer)', txt, re.I)]
    nums += [int(n) for n in re.findall(r'(\d+)\s*[A-Z]{4}\d{1,2}\b', txt)]  # '1 KLBN3 + 4 KLBN4'
    return float(sum(nums)) if nums else None


# ---------------------------------------------------------------- fundamentos point-in-time
# lucro líquido: não financeiras usam 3.11(.01); instituições financeiras, 3.09(.01). Preferência: controladores.
_CONTAS_DRE = ('3.11.01', '3.09.01', '3.11', '3.09')


def _valor(r):
    try:
        v = float(r['VL_CONTA'])
    except (ValueError, KeyError):
        return None
    return v * (1000.0 if r.get('ESCALA_MOEDA', 'MIL') == 'MIL' else 1.0)


def _escolher(d, contas):
    """Consolidado antes do individual; contas em ordem de preferência."""
    for escopo in ('con', 'ind'):
        for conta in contas:
            if (escopo, conta) in d:
                return d[(escopo, conta)]
    return None


def fundamentos_pit(cnpjs, anos):
    """{cnpj: [registro, ...]} ordenado por data de recebimento. Registro: dt_refer, dt_receb, tipo, ni_ytd,
    ni_ytd_ant, pl, acoes. ni = lucro líquido dos controladores; pl = patrimônio líquido menos
    participação de não controladores. Vale a menor versão presente nas demonstrações e a data de
    recebimento dessa versão (a CVM só mantém nos arquivos a versão mais recente de alguns períodos)."""
    cnpjs = set(cnpjs)
    hoje = dt.date.today()
    rec = {}  # (cnpj, dt_refer) -> {'tipo', 'receb': {ver: data}, 'v': {ver: dados}}

    def dados(k, ver):
        return rec[k]['v'].setdefault(ver, {'ni': {}, 'ni_ant': {}, 'pl': {}, 'acoes': None})

    for ano in anos:
        for pref, tipo in (('dfp', 'DFP'), ('itr', 'ITR')):
            rel = f'DOC/{tipo}/DADOS/{pref}_cia_aberta_{ano}.zip'
            try:
                z = cvm.baixar(rel, 7 if ano >= hoje.year - 1 else 3650)
            except Exception:
                continue
            for r in cvm._linhas(z, f'{pref}_cia_aberta_{ano}.csv'):
                if r['CNPJ_CIA'] in cnpjs:
                    k = (r['CNPJ_CIA'], r['DT_REFER'])
                    rec.setdefault(k, {'tipo': tipo, 'receb': {}, 'v': {}})['receb'][int(r['VERSAO'] or 0)] = r['DT_RECEB']
            for demo in ('DRE', 'BPP'):
                for escopo in ('con', 'ind'):
                    nome = f'{pref}_cia_aberta_{demo}_{escopo}_{ano}.csv'
                    if not cvm._tem(z, nome):
                        continue
                    for r in cvm._linhas(z, nome):
                        if r['CNPJ_CIA'] not in cnpjs:
                            continue
                        conta = r['CD_CONTA']
                        if demo == 'DRE' and conta not in _CONTAS_DRE:
                            continue
                        if demo == 'BPP':  # patrimônio líquido muda de código entre plano geral (2.03) e bancos (2.08)
                            desc = r['DS_CONTA'].lower()
                            if conta.count('.') == 1 and desc.startswith('patrimônio líquido'):
                                conta = 'PL'
                            elif conta.count('.') == 2 and desc.startswith('participação') and 'não controlador' in desc:
                                conta = 'MIN'
                            else:
                                continue
                        k = (r['CNPJ_CIA'], r['DT_REFER'])
                        v = _valor(r)
                        if k not in rec or v is None:
                            continue
                        d = dados(k, int(r['VERSAO'] or 0))
                        ultimo = r['ORDEM_EXERC'].upper().startswith(('ÚLT', 'ULT'))
                        if demo == 'BPP':
                            if ultimo and r['DT_FIM_EXERC'] == r['DT_REFER']:
                                d['pl'].setdefault((escopo, conta), v)
                        elif r.get('DT_INI_EXERC', '')[5:] == '01-01':  # só o acumulado do ano (YTD ou exercício)
                            (d['ni'] if ultimo else d['ni_ant']).setdefault((escopo, conta), v)
            capital = f'{pref}_cia_aberta_composicao_capital_{ano}.csv'
            if cvm._tem(z, capital):
                for r in cvm._linhas(z, capital):
                    k = (r['CNPJ_CIA'], r['DT_REFER'])
                    if k in rec:
                        try:
                            dados(k, int(r['VERSAO'] or 0))['acoes'] = (float(r['QT_ACAO_TOTAL_CAP_INTEGR'] or 0)
                                                                       - float(r['QT_ACAO_TOTAL_TESOURO'] or 0))
                        except ValueError:
                            pass

    out = {}
    for (c, d_ref), info in rec.items():
        if not info['v']:
            continue
        ver = min(info['v'])
        d = info['v'][ver]
        pl = _escolher(d['pl'], ('PL',))
        minoritarios = _escolher(d['pl'], ('MIN',))
        acoes = d['acoes']
        if acoes is None:  # capital pode ter vindo em outra versão do mesmo período
            acoes = next((x['acoes'] for _, x in sorted(info['v'].items()) if x['acoes']), None)
        out.setdefault(c, []).append({
            'cnpj': c, 'dt_refer': d_ref, 'tipo': info['tipo'],
            'dt_receb': info['receb'].get(ver) or min(info['receb'].values()),
            'ni_ytd': _escolher(d['ni'], _CONTAS_DRE),
            'ni_ytd_ant': _escolher(d['ni_ant'], _CONTAS_DRE),
            'pl': (pl - (minoritarios or 0.0)) if pl is not None else None, 'acoes': acoes})
    for lst in out.values():
        lst.sort(key=lambda x: (x['dt_receb'], x['dt_refer']))
    return out


def estado_em(registros, data_iso):
    """Fundamentos conhecidos em `data_iso`: {ni_ttm, pl, acoes, acoes_dt_refer, dt_refer} ou None."""
    visiveis = [r for r in registros if r['dt_receb'] <= data_iso]
    if not visiveis:
        return None
    ult = max(visiveis, key=lambda r: r['dt_refer'])
    ni_ttm = None
    if ult['ni_ytd'] is not None:
        if ult['dt_refer'][5:] == '12-31':
            ni_ttm = ult['ni_ytd']
        else:
            fy = f'{int(ult["dt_refer"][:4]) - 1}-12-31'
            anual = next((r for r in visiveis if r['dt_refer'] == fy and r['ni_ytd'] is not None), None)
            if anual is not None and ult['ni_ytd_ant'] is not None:
                ni_ttm = anual['ni_ytd'] + ult['ni_ytd'] - ult['ni_ytd_ant']
    acoes = next(((r['acoes'], r['dt_refer']) for r in sorted(visiveis, key=lambda r: r['dt_refer'], reverse=True)
                  if r['acoes']), (None, None))
    return {'ni_ttm': ni_ttm, 'pl': ult['pl'], 'acoes': acoes[0], 'acoes_dt_refer': acoes[1], 'dt_refer': ult['dt_refer']}
