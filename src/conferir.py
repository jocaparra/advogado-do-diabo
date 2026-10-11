"""Conferência determinística de uma semana: schemas, cobertura, coerência e recálculo de números.

uso: python src/conferir.py <pasta_da_semana> [--estrito]

Grava conferencia.json na pasta. Sai com código 1 se houver erros (ou avisos, com --estrito).
Tudo é recalculado em código a partir dos arquivos de dados; nenhum LLM participa.
"""
import datetime as dt
import json
import math
import os
import re
import statistics
import sys

import carteira as C
import regras as R
import validar

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQ_SCHEMA = {'precos.json': 'precos', 'casas.json': 'casas', 'sintese.json': 'sintese', 'macro.json': 'macro',
              'risco.json': 'risco', 'alertas.json': 'alertas', 'fundamentos_cvm.json': 'fundamentos_cvm',
              'textos.json': 'textos', 'dossie_qualitativo.json': 'dossie_qualitativo'}
TOL = {'upside_pp': 0.15, 'nota': 0.011, 'retorno_pp': 0.06, 'beta': 0.06, 'vol_pp': 1.0, 'preco': 0.005}


class Relatorio:
    def __init__(self):
        self.itens = []
        self.verificacoes = 0

    def ok(self, n=1):
        self.verificacoes += n

    def add(self, sev, regra, arquivo, mensagem, ticker=None, esperado=None, encontrado=None):
        self.itens.append({'severidade': sev, 'regra': regra, 'arquivo': arquivo, 'ticker': ticker,
                           'mensagem': mensagem, 'esperado': esperado, 'encontrado': encontrado})

    def erro(self, *a, **k):
        self.add('erro', *a, **k)

    def aviso(self, *a, **k):
        self.add('aviso', *a, **k)


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _pct(s):
    try:
        return float(str(s).replace('%', ''))
    except ValueError:
        return None


def _data(s):
    s = str(s)
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        pass
    m = re.fullmatch(r'(\d{4})-(\d{2})', s.strip())  # precisão de mês: vale o último dia
    if m:
        a, mes = int(m.group(1)), int(m.group(2))
        if 1 <= mes <= 12:
            prox = dt.date(a + (mes == 12), mes % 12 + 1, 1)
            return prox - dt.timedelta(days=1)
    return None



def beta_vol(acao, ibov, janela=90):
    """Beta contra o Ibovespa e volatilidade anualizada, sobre os últimos `janela` retornos logarítmicos
    das datas em comum (método descrito em risco.json)."""
    a = {x[0]: x[1] for x in acao}
    comum = [(x[0], a[x[0]], x[1]) for x in ibov if x[0] in a]
    if len(comum) < janela + 1:
        return None, None
    comum = comum[-(janela + 1):]
    ra = [math.log(comum[i][1] / comum[i - 1][1]) for i in range(1, len(comum))]
    ri = [math.log(comum[i][2] / comum[i - 1][2]) for i in range(1, len(comum))]
    mi, ma = statistics.fmean(ri), statistics.fmean(ra)
    cov = sum((x - ma) * (y - mi) for x, y in zip(ra, ri)) / (len(ra) - 1)
    var = sum((y - mi) ** 2 for y in ri) / (len(ri) - 1)
    return cov / var, statistics.stdev(ra) * math.sqrt(252) * 100


def conferir(pasta):
    rel = Relatorio()
    a, m, d = C.data_semana(pasta)
    hoje = dt.date(a, m, d)
    carregados = {}

    # 1. schemas
    caminhos = {os.path.basename(p): p for p in [C.arquivo_xp(pasta)]}
    caminhos = {'xp.json': C.arquivo_xp(pasta)}
    for arq in ARQ_SCHEMA:
        p = os.path.join(pasta, arq)
        if os.path.exists(p):
            caminhos[arq] = p
    for arq, p in caminhos.items():
        nome = 'xp' if arq == 'xp.json' else ARQ_SCHEMA[arq]
        try:
            dado = C.ler(p)
        except json.JSONDecodeError as e:
            rel.erro('json_valido', arq, f'JSON inválido: {e}')
            continue
        carregados[arq] = dado
        with open(os.path.join(RAIZ, 'schemas', f'{nome}.schema.json'), encoding='utf-8') as f:
            erros = validar.validar(dado, json.load(f))
        rel.ok()
        for e in erros[:25]:
            rel.erro('schema', arq, e)
        if len(erros) > 25:
            rel.erro('schema', arq, f'... e mais {len(erros) - 25} erros de schema')
    for arq in ('precos.json', 'sintese.json', 'casas.json'):
        if arq not in carregados:
            rel.erro('arquivo_obrigatorio', arq, 'arquivo ausente ou inválido; conferência numérica incompleta')
    xp, pr, sy, ca = (carregados.get(k) for k in ('xp.json', 'precos.json', 'sintese.json', 'casas.json'))
    ri, tx = carregados.get('risco.json'), carregados.get('textos.json', {})
    cv = carregados.get('fundamentos_cvm.json')
    pol = R.parametros(tx)
    par = {'corte_compra': R.corte_de_compra(sy['ranking'], tx) if sy else None}

    # 2. cobertura entre arquivos
    if xp and sy and pr:
        conj = {'xp': {x['ticker'] for x in xp['acoes']}, 'sintese': {r['ticker'] for r in sy['ranking']},
                'precos': set(pr['acoes'])}
        if ca:
            conj['casas'] = set(ca['tickers'])
        if ri:
            conj['risco'] = set(ri['tabela_por_ticker'])
        if cv:
            conj['fundamentos_cvm'] = set(cv['tickers'])
        ref = conj['xp']
        for nome, s in conj.items():
            rel.ok()
            if s != ref:
                rel.erro('cobertura', f'{nome}', 'tickers diferentes do xp.json',
                         esperado=sorted(ref - s) or None, encontrado=sorted(s - ref) or None)

    # 3. ranking
    if sy:
        rk = sy['ranking']
        pesos = sy['metodologia']['pesos']
        rel.ok()
        if abs(sum(pesos.values()) - 1) > 1e-6:
            rel.erro('pesos', 'sintese.json', 'pesos da nota não somam 1', esperado=1, encontrado=sum(pesos.values()))
        rel.ok()
        if [r['posicao'] for r in rk] != list(range(1, len(rk) + 1)):
            rel.erro('posicoes', 'sintese.json', 'posições não são 1..N em sequência')
        for i in range(1, len(rk)):
            rel.ok()
            if rk[i]['nota'] > rk[i - 1]['nota'] + 1e-9:
                rel.erro('ordem', 'sintese.json', f'{rk[i]["ticker"]} tem nota maior que a posição anterior', rk[i]['ticker'],
                         esperado=f'<= {rk[i - 1]["nota"]}', encontrado=rk[i]['nota'])
        for r in rk:
            t = r['ticker']
            if set(pesos) <= set(r['componentes']):
                calc = sum(pesos[k] * r['componentes'][k] for k in pesos)
                rel.ok()
                if abs(calc - r['nota']) > TOL['nota']:
                    rel.erro('nota', 'sintese.json', 'nota diferente da soma ponderada dos componentes', t,
                             esperado=round(calc, 3), encontrado=r['nota'])
            if r['acao_sugerida'] == 'comprar':
                rel.ok()
                if par['corte_compra'] is not None and r['nota'] < par['corte_compra']:
                    rel.erro('regra_acao', 'sintese.json', f'comprar com nota abaixo do corte {par["corte_compra"]}', t,
                             esperado=f'>= {par["corte_compra"]}', encontrado=r['nota'])
                ua = _num(r.get('upside_ajustado_pct'))
                if ua is not None and ua <= 0:
                    rel.erro('regra_acao', 'sintese.json', 'comprar com upside ajustado não positivo', t, encontrado=ua)
            elif r['acao_sugerida'] == 'aguardar' and par['corte_compra'] is not None and r['nota'] >= par['corte_compra']:
                rel.aviso('regra_acao', 'sintese.json', 'nota acima do corte mas ação é aguardar (conferir justificativa)', t,
                          encontrado=r['nota'])

    # 4. preços, upside, mediana, upside ajustado
    if sy and pr:
        for r in sy['ranking']:
            t = r['ticker']
            p = pr['acoes'].get(t)
            if not p:
                continue
            rel.ok(2)
            if abs(r['preco_atual'] / p['preco_atual'] - 1) > TOL['preco']:
                rel.erro('preco', 'sintese.json', 'preço da síntese difere de precos.json', t, esperado=p['preco_atual'], encontrado=r['preco_atual'])
            if r['data_cotacao'] != p['data_cotacao']:
                rel.erro('data_cotacao', 'sintese.json', 'data da cotação difere de precos.json', t, esperado=p['data_cotacao'], encontrado=r['data_cotacao'])
            alvo = _num(r.get('preco_alvo_xp'))
            if alvo and _num(r.get('upside_xp_pct')) is not None:
                esp = (alvo / r['preco_atual'] - 1) * 100
                rel.ok()
                if abs(esp - r['upside_xp_pct']) > TOL['upside_pp']:
                    rel.erro('upside_xp', 'sintese.json', 'upside até o alvo da XP não confere', t, esperado=round(esp, 2), encontrado=r['upside_xp_pct'])
            if xp:
                xa = next((x for x in xp['acoes'] if x['ticker'] == t), None)
                if xa and _num(xa.get('preco_alvo')) is not None and alvo is not None:
                    rel.ok()
                    if abs(xa['preco_alvo'] - alvo) > 0.005:
                        rel.erro('alvo_xp', 'sintese.json', 'alvo da XP difere de xp.json', t, esperado=xa['preco_alvo'], encontrado=alvo)
            med = _num(r.get('mediana_casas'))
            if med is not None and _num(r.get('upside_mediana_pct')) is not None:
                esp = (med / r['preco_atual'] - 1) * 100
                rel.ok()
                if abs(esp - r['upside_mediana_pct']) > TOL['upside_pp']:
                    rel.erro('upside_mediana', 'sintese.json', 'upside até a mediana não confere', t, esperado=round(esp, 2), encontrado=r['upside_mediana_pct'])
            ua, ux, um = (_num(r.get(k)) for k in ('upside_ajustado_pct', 'upside_xp_pct', 'upside_mediana_pct'))
            r5 = _pct(p.get('ret_5d'))
            esp = R.upside_ajustado(ux, um, r5, pol)
            if esp is not None and ua is not None:
                rel.ok()
                if abs(esp - ua) > 0.11:
                    rel.erro('upside_ajustado', 'sintese.json', 'upside ajustado difere da regra única (src/regras.py); rode calcular_derivados.py', t,
                             esperado=esp, encontrado=ua)
            if ca and t in ca['tickers']:
                m_calc, n_calc, _ = R.mediana_alvos(ca['tickers'][t]['casas'], hoje, pol)
                m_arq, n_arq = _num(r.get('mediana_casas')), r.get('n_alvos_mediana')
                rel.ok(2)
                if (m_calc is None) != (m_arq is None) or (m_calc is not None and abs(m_calc - m_arq) > 0.02):
                    rel.erro('mediana', 'sintese.json', 'mediana da síntese difere da regra única; rode calcular_derivados.py', t,
                             esperado=None if m_calc is None else round(m_calc, 2), encontrado=m_arq)
                if n_arq is not None and n_arq != n_calc:
                    rel.erro('n_alvos', 'sintese.json', 'número de alvos da mediana difere da regra única', t, esperado=n_calc, encontrado=n_arq)
                m_cj = _num(ca['tickers'][t].get('mediana_preco_alvo'))
                if (m_cj is None) != (m_calc is None) or (m_cj is not None and abs(m_cj - m_calc) > 0.02):
                    rel.erro('mediana_casas_json', 'casas.json', 'mediana_preco_alvo difere da regra única; rode calcular_derivados.py', t,
                             esperado=None if m_calc is None else round(m_calc, 2), encontrado=m_cj)

    # 5. séries de preço: retorno de 5 dias, atualidade e consistência
    if pr:
        ib = pr['ibovespa']
        for t, p in pr['acoes'].items():
            serie = p.get('serie')
            if not isinstance(serie, list) or len(serie) < 7:
                rel.aviso('serie', 'precos.json', 'série diária ausente ou curta', t)
                continue
            rel.ok(3)
            if serie[-1][0] != p['data_cotacao']:
                rel.erro('serie_data', 'precos.json', 'última data da série difere da data da cotação', t, esperado=p['data_cotacao'], encontrado=serie[-1][0])
            if abs(serie[-1][1] / p['preco_atual'] - 1) > TOL['preco']:
                rel.erro('serie_preco', 'precos.json', 'último ponto da série difere do preço atual', t, esperado=p['preco_atual'], encontrado=serie[-1][1])
            r5 = _pct(p.get('ret_5d'))
            if r5 is not None:
                esp = (serie[-1][1] / serie[-6][1] - 1) * 100
                if abs(esp - r5) > TOL['retorno_pp']:
                    rel.erro('ret_5d', 'precos.json', 'retorno de 5 pregões não confere com a série', t, esperado=round(esp, 2), encontrado=r5)
            dc = _data(p['data_cotacao'])
            rel.ok()
            if dc and (hoje - dc).days > 5:
                rel.aviso('defasagem', 'precos.json', f'cotação com {(hoje - dc).days} dias de defasagem', t)
            if dc and dc > hoje:
                rel.erro('data_futura', 'precos.json', 'cotação posterior à data da semana', t, encontrado=p['data_cotacao'])
        # 6. risco recalculado
        if ri:
            for t, linha in ri['tabela_por_ticker'].items():
                s = pr['acoes'].get(t, {}).get('serie')
                if not isinstance(s, list):
                    continue
                b, v = beta_vol(s, ib['serie'])
                if b is None:
                    rel.aviso('risco', 'risco.json', 'série curta para recalcular beta e volatilidade', t)
                    continue
                rel.ok(2)
                if abs(b - linha['beta_90pregoes_ibov']) > TOL['beta']:
                    rel.aviso('beta', 'risco.json', 'beta de 90 pregões difere do recalculado', t, esperado=round(b, 2), encontrado=linha['beta_90pregoes_ibov'])
                if abs(v - linha['vol_90pregoes_anual_pct']) > TOL['vol_pp']:
                    rel.aviso('volatilidade', 'risco.json', 'volatilidade de 90 pregões difere da recalculada', t, esperado=round(v, 1), encontrado=linha['vol_90pregoes_anual_pct'])

    # 7. fontes: datas, links e domínios fora da lista
    if sy:
        fora = tx.get('politica_fontes', {}).get('dominios_fora_da_lista_de_fontes', [])
        for r in sy['ranking']:
            for f in r['fontes']:
                rel.ok()
                u = f.get('url', '')
                df = _data(f.get('data'))
                if df is None:
                    rel.aviso('fonte_data', 'sintese.json', f'fonte sem data válida: {f.get("fonte")[:50]}', r['ticker'], encontrado=f.get('data'))
                elif df > hoje:
                    rel.erro('fonte_data', 'sintese.json', 'fonte datada depois da semana', r['ticker'], encontrado=f.get('data'))
                if not str(u).startswith('http') and 'PDF local' not in str(u):
                    rel.aviso('fonte_link', 'sintese.json', f'fonte sem link verificável: {f.get("fonte")[:50]}', r['ticker'], encontrado=str(u)[:60])
                if any(x in str(u) for x in fora):
                    rel.erro('fonte_proibida', 'sintese.json', 'fonte de domínio fora da lista permitida', r['ticker'], encontrado=u)

    # 8. fundamentos da CVM contra o que a síntese afirma (quando a tese cita P/L)
    if cv:
        for t, v in cv['tickers'].items():
            rel.ok()
            if v.get('situacao') == 'ok':
                for av in v.get('avisos', []):
                    rel.aviso('cvm_aviso', 'fundamentos_cvm.json', av, t)
            else:
                rel.aviso('cvm_sem_dado', 'fundamentos_cvm.json', v.get('motivo', 'sem demonstrações'), t)

    # 9. dossiê: itens preenchidos só existem no perfil do ticker, e o valuation é coerente
    dq = carregados.get('dossie_qualitativo.json')
    if dq:
        perfis = C.ler(os.path.join(RAIZ, 'dados', 'perfis_setoriais.json'))
        for t, itens in dq.items():
            pid = perfis['tickers'].get(t, 'generico')
            validos = {c['id'] for c in perfis['perfis'][pid]['checklist']}
            for k, v in itens.items():
                rel.ok()
                if k not in validos:
                    rel.aviso('dossie_item', 'dossie_qualitativo.json', f'item "{k}" não pertence ao perfil {pid}', t)
                d_ = _data(v.get('data'))
                if d_ and d_ > hoje:
                    rel.erro('dossie_data', 'dossie_qualitativo.json', f'item "{k}" com data posterior à semana', t, encontrado=v.get('data'))
    dos = C.ler(os.path.join(pasta, 'dossie.json'), None) if os.path.exists(os.path.join(pasta, 'dossie.json')) else None
    if dos and pr:
        for t, v in dos['tickers'].items():
            val = v['valuation']
            if val.get('status') != 'ok':
                continue
            rel.ok()
            b = val['cenarios'].get('base', {})
            px = pr['acoes'].get(t, {}).get('preco_atual')
            if px and b.get('valor_justo_por_acao') is not None and abs(v['preco'] - px) > 0.005:
                rel.erro('dossie_preco', 'dossie.json', 'preço do dossiê difere de precos.json; rode gerar_dossie.py de novo', t, esperado=px, encontrado=v['preco'])
            ordem = [val['cenarios'][k].get('valor_justo_por_acao') for k in ('bear', 'base', 'bull')]
            if None not in ordem and not (ordem[0] <= ordem[1] <= ordem[2]):
                rel.erro('dossie_cenarios', 'dossie.json', 'cenários fora de ordem (bear <= base <= bull)', t, encontrado=ordem)

    res = {'erros': sum(i['severidade'] == 'erro' for i in rel.itens), 'avisos': sum(i['severidade'] == 'aviso' for i in rel.itens),
           'verificacoes': rel.verificacoes}
    return {'semana': os.path.basename(pasta), 'data_conferencia': dt.date.today().isoformat(), 'resumo': res, 'itens': rel.itens}


def main():
    estrito = '--estrito' in sys.argv
    args = [x for x in sys.argv if x != '--estrito']
    sys.argv = args
    pasta = C.pasta_semana()
    r = conferir(pasta)
    with open(os.path.join(pasta, 'conferencia.json'), 'w', encoding='utf-8') as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    s = r['resumo']
    print(f'conferência: {s["verificacoes"]} verificações, {s["erros"]} erros, {s["avisos"]} avisos')
    for i in r['itens']:
        marca = 'ERRO ' if i['severidade'] == 'erro' else 'aviso'
        print(f'  {marca} [{i["regra"]}] {i["arquivo"]} {i["ticker"] or ""}: {i["mensagem"]}'
              + (f' (esperado {i["esperado"]}, encontrado {i["encontrado"]})' if i['esperado'] is not None or i['encontrado'] is not None else ''))
    if s['erros'] or (estrito and s['avisos']):
        sys.exit(1)


if __name__ == '__main__':
    main()
