"""Indicadores fundamentalistas calculados em código a partir das demonstrações da CVM.

Cada função é pura (entrada: dicionários já carregados por cvm.py), para poder ser testada.
"""
import datetime as dt
import re

from cvm import ult_dia

FINANCEIRA = re.compile(r'intermedia[cç][aã]o financeira|pr[eê]mios|receitas da intermedia', re.I)
LL_CONTROLADORES = re.compile(r'atribu[ií]do a s[oó]cios da empresa controladora|atribu[ií]do.*(aos )?controladores', re.I)
LL_NAO_CONTROLADORES = re.compile(r'n[aã]o controlador|minorit', re.I)
LL_CONSOLIDADO = re.compile(r'(lucro|preju[ií]zo).*(consolidado|l[ií]quido).*(per[ií]odo|exerc)', re.I)
PL_TOTAL = re.compile(r'^patrim[oô]nio l[ií]quido( consolidado)?$', re.I)
PL_CONTROL = re.compile(r'(patrim[oô]nio l[ií]quido atribu[ií]do|atribu[ií]do).*(controlador|s[oó]cios da empresa)', re.I)


# ------------------------------------------------------------ utilidades
def _profundidade(cd):
    return cd.count('.') + 1


def _achar(contas, regex, prefixo='', prof=None):
    """Primeira conta (menor código) cuja descrição casa com `regex`."""
    for cd in sorted(contas, key=lambda c: [int(x) if x.isdigit() else 0 for x in c.split('.')]):
        if prefixo and not cd.startswith(prefixo):
            continue
        if prof and _profundidade(cd) != prof:
            continue
        if regex.search(contas[cd][1]):
            return cd, contas[cd][0]
    return None, None


def escolher_escopo(demos):
    return 'con' if demos['DRE']['con'] else 'ind'


def eh_financeira(dre_periodo):
    c = dre_periodo.get('3.01')
    return bool(c and FINANCEIRA.search(c[1]))


def lucro_liquido(contas):
    """Lucro atribuído aos controladores. Se a companhia não preencheu a divisão (controladores e não
    controladores zerados com consolidado diferente de zero), usa o consolidado para não misturar
    períodos de contas diferentes. Devolve (conta, valor)."""
    cd_c = v_c = None
    for cd in sorted(contas, key=lambda c: [int(x) if x.isdigit() else 0 for x in c.split('.')]):
        if cd.startswith('3.') and LL_CONTROLADORES.search(contas[cd][1]) and not LL_NAO_CONTROLADORES.search(contas[cd][1]):
            cd_c, v_c = cd, contas[cd][0]
            break
    cd_t, v_t = _achar(contas, LL_CONSOLIDADO, '3.', prof=2)
    nci = None
    for cd in contas:
        if cd.startswith('3.') and LL_NAO_CONTROLADORES.search(contas[cd][1]) and re.search(r'atribu', contas[cd][1], re.I):
            nci = contas[cd][0]
            break
    if cd_c is None:
        return cd_t, v_t
    if v_c == 0 and v_t not in (None, 0) and (nci in (None, 0)):
        return cd_t, v_t  # divisão não preenchida
    return cd_c, v_c


def _fim_ano(periodos, ano):
    k = (f'{ano}-01-01', f'{ano}-12-31')
    return periodos.get(k)


def anos_completos(periodos):
    return sorted({int(f[:4]) for i, f in periodos if i == f[:4] + '-01-01' and f.endswith('-12-31')})


def ytd_mais_recente(periodos, ano):
    c = [(i, f) for i, f in periodos if i == f'{ano}-01-01' and not f.endswith('-12-31')]
    return max(c, key=lambda p: p[1]) if c else None


def mesmo_periodo_ano_anterior(per):
    ini, fim = per
    d = ult_dia(fim)
    try:
        d0 = d.replace(year=d.year - 1)
    except ValueError:  # 29/02
        d0 = d.replace(year=d.year - 1, day=28)
    return (f'{d0.year}-01-01', d0.isoformat())


def ltm(demo, extrator):
    """12 meses até o último documento: FY anterior + YTD atual - YTD do ano anterior.

    `demo` é {(ini, fim): {cd: ...}}. `extrator(contas)` devolve (cd, valor).
    Devolve (valor, referencia_iso, metodo) ou (None, None, motivo)."""
    anos = anos_completos(demo)
    if not anos:
        return None, None, 'sem exercício anual completo'
    ano = anos[-1]
    fy = _fim_ano(demo, ano)
    v_fy = extrator(fy)[1]
    ytd = ytd_mais_recente(demo, ano + 1)
    if not ytd:
        return v_fy, f'{ano}-12-31', f'exercício de {ano} (DFP)'
    prev = demo.get(mesmo_periodo_ano_anterior(ytd))
    v_c = extrator(demo[ytd])[1]
    v_p = extrator(prev)[1] if prev else None
    if None in (v_fy, v_c, v_p):
        return v_fy, f'{ano}-12-31', f'exercício de {ano} (DFP); 12 meses indisponíveis'
    return v_fy + v_c - v_p, ytd[1], f'DFP {ano} + {ytd[0]} a {ytd[1]} - mesmo período de {ano}'


def _por_cd(cd):
    def f(contas):
        c = contas.get(cd) if contas else None
        return (cd, c[0]) if c else (None, None)
    return f


def _dva_da(contas):
    """Depreciação, amortização e exaustão (DVA 7.04.01). Aparece negativa nas retenções: devolve o módulo."""
    if not contas:
        return None, None
    cd, v = _achar(contas, re.compile(r'deprecia', re.I), '7.04')
    return cd, (abs(v) if v is not None else None)


def _dva_dist(contas):
    """JCP + dividendos distribuídos (DVA 7.08.04.*)."""
    if not contas:
        return None, None
    total, achou = 0.0, False
    for cd, (v, ds, *_r) in contas.items():
        if cd.startswith('7.08.04.') and re.search(r'juros sobre|dividend', ds, re.I):
            total += v
            achou = True
    return ('7.08.04', total) if achou else (None, None)


def _saldo(bp, regex=None, cd=None, prefixo='', prof=None):
    if regex is not None:
        return _achar(bp, regex, prefixo, prof)[1]
    c = bp.get(cd)
    return c[0] if c else None


def ultimo_balanco(bp_escopo):
    """(data_iso, contas) do balanço mais recente."""
    if not bp_escopo:
        return None, None
    fim = max(f for _, f in bp_escopo)
    # BPA/BPP registram só a data-base; várias chaves podem existir (ini vazio)
    contas = {}
    for (i, f), c in bp_escopo.items():
        if f == fim:
            contas.update(c)
    return fim, contas


def fator_acoes(dre, acoes_total):
    """Algumas companhias informam a quantidade de ações em milhares apesar do layout pedir unidades.
    Compara com lucro / lucro por ação (DRE 3.99) do último exercício e devolve 1 ou 1000."""
    anos = anos_completos(dre)
    if not anos or not acoes_total:
        return 1, 'sem lucro por ação para conferir a escala; assumida em unidades'
    p = _fim_ano(dre, anos[-1])
    ll = lucro_liquido(p)[1]
    lpa = None
    for cd in sorted(p):
        if cd.startswith('3.99.01') and p[cd][0] and p[cd][0] > 0:
            lpa = p[cd][0]
            break
    if not ll or ll <= 0 or not lpa:
        return 1, 'sem lucro por ação positivo para conferir a escala; assumida em unidades'
    est = ll / lpa
    r = acoes_total / est
    if r < 0.05:
        return 1000, f'quantidade de ações informada em milhares (razão {r:.4f} contra lucro/LPA)'
    return 1, f'escala de ações conferida contra lucro/LPA (razão {r:.2f})'


# ------------------------------------------------------------ cálculo principal
def calcular(saida, meta, preco, acoes, cambio=None, unit_acoes=None):
    """Indicadores de uma empresa. Valores em unidades da moeda de reporte (não em milhares).

    saida/meta: de cvm.carregar_empresas. preco: {valor, data}. acoes: de cvm.capital.
    cambio: R$ por unidade da moeda de reporte, se não for REAL. unit_acoes: ações por unit.
    Devolve dict com 'valores' (campo -> {valor, unidade, certeza, metodo}) e 'avisos'."""
    avisos = []
    escopo = escolher_escopo(saida)
    dre, bpa, bpp, dva = (saida[d][escopo] for d in ('DRE', 'BPA', 'BPP', 'DVA'))
    anos = anos_completos(dre)
    if not anos:
        return None
    ano = anos[-1]
    fin = eh_financeira(_fim_ano(dre, ano))
    moeda = meta.get('moeda') or 'REAL'
    out = {}

    def reg(nome, valor, unidade, certeza, metodo):
        out[nome] = {'valor': valor, 'unidade': unidade, 'certeza': certeza, 'metodo': metodo}

    ll, ref, met = ltm(dre, lucro_liquido)
    rec, _, met_r = ltm(dre, _por_cd('3.01'))
    if fin:
        ebit = da = ebitda = None
    else:
        ebit, _, _ = ltm(dre, _por_cd('3.05'))
        da, _, _ = ltm(dva, _dva_da)
        ebitda = (ebit + da) if (ebit is not None and da is not None) else None
    dist, _, _ = ltm(dva, _dva_dist)
    ll_fy = lucro_liquido(_fim_ano(dre, ano))[1]
    if ll is not None and ll_fy not in (None, 0):
        if (ll > 0) != (ll_fy > 0) or not (0.4 <= abs(ll / ll_fy) <= 2.5):
            avisos.append(f'lucro de 12 meses ({ll:,.0f}) difere muito do último exercício ({ll_fy:,.0f}): conferir reapresentações, itens extraordinários ou mudança de conta')
    reg('referencia_12m', ref, 'data', 'alta', met)
    reg('receita_12m', rec, moeda, 'alta', 'DRE 3.01, ' + met_r)
    reg('lucro_liquido_12m', ll, moeda, 'alta', 'lucro atribuído aos controladores, ' + met)
    if not fin:
        reg('ebit_12m', ebit, moeda, 'alta', 'DRE 3.05')
        reg('depreciacao_amortizacao_12m', da, moeda, 'média', 'DVA 7.04.01 (retenções)')
        reg('ebitda_12m', ebitda, moeda, 'média', 'EBIT + depreciação e amortização da DVA; não é EBITDA ajustado da empresa')
    reg('proventos_12m', dist, moeda, 'média', 'DVA 7.08.04 (JCP + dividendos), base competência')

    # balanço
    dt_bp, bp_a = ultimo_balanco(bpa)
    _, bp_p = ultimo_balanco(bpp)
    if bp_a and bp_p:
        caixa = (_saldo(bp_a, cd='1.01.01') or 0) + (_saldo(bp_a, cd='1.01.02') or 0)
        div = sum(v[0] for cd, v in bp_p.items() if cd in ('2.01.04', '2.02.01') and re.search(r'empr[eé]stimo', v[1], re.I))
        _, pl = _achar(bp_p, PL_TOTAL, '2.', prof=2)
        _, pl_c = _achar(bp_p, PL_CONTROL, '2.')
        pl_c = pl_c if pl_c is not None else pl
        reg('data_balanco', dt_bp, 'data', 'alta', 'último BPA/BPP')
        reg('patrimonio_liquido', pl_c, moeda, 'alta', 'PL atribuído aos controladores')
        if not fin:
            reg('caixa_e_aplicacoes', caixa, moeda, 'alta', 'BPA 1.01.01 + 1.01.02')
            reg('divida_bruta', div, moeda, 'média', 'BPP 2.01.04 + 2.02.01 (empréstimos, financiamentos e debêntures); exclui arrendamentos')
            reg('divida_liquida', div - caixa, moeda, 'média', 'dívida bruta - caixa e aplicações')
            if ebitda and ebitda > 0:
                reg('divida_liquida_sobre_ebitda', (div - caixa) / ebitda, 'x', 'média', 'dívida líquida / EBITDA 12 meses')
    else:
        pl_c = None
        avisos.append('balanço patrimonial indisponível')

    # valor de mercado
    mcap = None
    if preco and acoes:
        fator, nota_esc = fator_acoes(dre, acoes['total'])
        if fator != 1:
            avisos.append(nota_esc)
        circ = (acoes['total'] - acoes['tesouraria']) * fator
        if unit_acoes and unit_acoes > 0:
            qtd = circ / unit_acoes
            avisos.append(f'ticker é unit ({unit_acoes:g} ações por unit): valor de mercado = preço x total de ações / {unit_acoes:g}; aproximação, pois parte das ações pode estar fora das units')
        else:
            qtd = circ
        if acoes['preferenciais'] > 0 and not unit_acoes:
            avisos.append('empresa com ON e PN: valor de mercado usa o preço do ticker para todas as classes (aproximação)')
        mcap_moeda = preco['valor'] * qtd
        if moeda != 'REAL':
            if cambio:
                mcap_moeda = mcap_moeda / cambio
            else:
                avisos.append(f'moeda de reporte {moeda} sem câmbio: múltiplos não calculados')
                mcap_moeda = None
        mcap = mcap_moeda
        cert = 'média' if (acoes['preferenciais'] > 0 or unit_acoes) else 'alta'
        reg('acoes_em_circulacao', circ, 'ações', 'alta' if fator == 1 and 'razão' in nota_esc else 'média', f'total integralizado - tesouraria ({acoes["dt_refer"]}); {nota_esc}')
        if mcap:
            reg('valor_de_mercado', mcap, moeda, cert, f'preço {preco["valor"]} ({preco["data"]}) x ações em circulação')
    if mcap:
        # sanidade de escala: múltiplos absurdos indicam quantidade de ações em escala errada
        pvp_s = mcap / pl_c if (pl_c and pl_c > 0) else None
        pl_s = mcap / ll if (ll and ll > 0) else None
        if (pvp_s is not None and not 0.05 <= pvp_s <= 80) or (pl_s is not None and not 0.5 <= pl_s <= 400):
            avisos.append(f'valor de mercado inconsistente com patrimônio e lucro (P/VP {pvp_s if pvp_s is None else round(pvp_s, 3)}, '
                          f'P/L {pl_s if pl_s is None else round(pl_s, 2)}): possível erro de escala nas ações; múltiplos não calculados')
            out['valor_de_mercado']['certeza'] = 'baixa'
            mcap = None
    if mcap:
        if ll and ll > 0:
            reg('p_l', mcap / ll, 'x', out['valor_de_mercado']['certeza'], 'valor de mercado / lucro 12 meses')
        elif ll is not None:
            avisos.append('lucro 12 meses não positivo: P/L não significativo')
        if pl_c and pl_c > 0:
            reg('p_vp', mcap / pl_c, 'x', out['valor_de_mercado']['certeza'], 'valor de mercado / PL dos controladores')
        if not fin and 'divida_liquida' in out and ebitda and ebitda > 0:
            ev = mcap + out['divida_liquida']['valor']
            reg('ev_ebitda', ev / ebitda, 'x', 'média', '(valor de mercado + dívida líquida) / EBITDA; sem ajuste de minoritários e arrendamentos')
        if dist is not None and dist > 0:
            reg('dividend_yield_12m', dist / mcap * 100, '%', 'média', 'proventos 12 meses (DVA) / valor de mercado')
    if ll is not None and ll > 0 and dist is not None:
        reg('payout_12m', dist / ll * 100, '%', 'média', 'proventos (DVA) / lucro 12 meses')

    # rentabilidade
    if ll is not None and rec:
        if not fin:
            reg('margem_liquida', ll / rec * 100, '%', 'alta', 'lucro / receita líquida, 12 meses')
        if ebit is not None:
            reg('margem_ebit', ebit / rec * 100, '%', 'alta', 'EBIT / receita líquida, 12 meses')
        if ebitda is not None:
            reg('margem_ebitda', ebitda / rec * 100, '%', 'média', 'EBITDA / receita líquida, 12 meses')
    if ll is not None and pl_c and pl_c > 0:
        reg('roe_12m', ll / pl_c * 100, '%', 'alta', 'lucro 12 meses / PL final (não médio)')

    # histórico anual e crescimento
    hist = []
    for a in anos[-4:]:
        p = _fim_ano(dre, a)
        pd = _fim_ano(dva, a) or {}
        l_ = lucro_liquido(p)[1]
        r_ = (p.get('3.01') or (None,))[0]
        e_ = (p.get('3.05') or (None,))[0] if not fin else None
        d_ = _dva_da(pd)[1] if pd and not fin else None
        item = {'ano': a, 'receita': r_, 'lucro_liquido': l_, 'ebit': e_,
                'ebitda': (e_ + d_) if (e_ is not None and d_ is not None) else None}
        item['margem_liquida_pct'] = (l_ / r_ * 100) if (l_ is not None and r_ and not fin) else None
        bp_fim = {}
        for (i_, f_), c_ in bpp.items():
            if f_ == f'{a}-12-31':
                bp_fim.update(c_)
        pl_a = None
        if bp_fim:
            pl_a = _achar(bp_fim, PL_CONTROL, '2.')[1]
            if pl_a is None:
                pl_a = _achar(bp_fim, PL_TOTAL, '2.', prof=2)[1]
        item['patrimonio_liquido'] = pl_a
        item['roe_pct'] = (l_ / pl_a * 100) if (l_ is not None and pl_a and pl_a > 0) else None
        if not (r_ in (None, 0) and l_ in (None, 0)):
            hist.append(item)
    consecutivos = len(hist) >= 2 and hist[-1]['ano'] - hist[-2]['ano'] == 1
    if consecutivos and hist[-1]['receita'] and hist[-2]['receita']:
        reg('crescimento_receita_ultimo_ano', (hist[-1]['receita'] / hist[-2]['receita'] - 1) * 100, '%', 'alta', f'DFP {hist[-1]["ano"]} contra {hist[-2]["ano"]}')
    if consecutivos and hist[-1]['lucro_liquido'] and hist[-2]['lucro_liquido'] and hist[-2]['lucro_liquido'] > 0:
        reg('crescimento_lucro_ultimo_ano', (hist[-1]['lucro_liquido'] / hist[-2]['lucro_liquido'] - 1) * 100, '%', 'alta', f'DFP {hist[-1]["ano"]} contra {hist[-2]["ano"]}')
    return {'tipo': 'financeira' if fin else 'nao_financeira', 'escopo': 'consolidado' if escopo == 'con' else 'individual',
            'moeda': moeda, 'valores': out, 'historico_anual': hist, 'avisos': avisos}
