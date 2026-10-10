"""Valuation simplificado e transparente: lucros descontados com reinvestimento implícito pelo ROE.

Para cada ano t = 1..N:  FCFE_t = L_t * (1 - g_t / ROE),  L_t = L_0 * prod(1 + g).
Valor terminal em N:      VT = L_N * (1 + gT) * (1 - gT / ROE) / (ke - gT).
Valor do patrimônio:      soma(FCFE_t / (1 + ke)^t) + VT / (1 + ke)^N.

É um modelo de referência, não uma previsão: depende de premissas (dados/premissas_valuation.json),
do ROE normalizado e do lucro normalizado. Serve para comparar o preço com uma faixa de valor
sob hipóteses explícitas e para mostrar que expectativa de crescimento o preço embute.
"""
import statistics


def roe_normalizado(roe_ltm, historico, prem, ciclica=False):
    """ROE usado no modelo, em fração, limitado à faixa das premissas.

    Cíclicas: média dos ROE anuais e do de 12 meses (o ciclo importa). Demais: ROE de 12 meses, para não
    penalizar empresas em recuperação com anos ruins que já passaram; sem ele, média dos anos."""
    anos = [h['roe_pct'] / 100 for h in historico if h.get('roe_pct') is not None]
    if ciclica:
        vals = anos + ([roe_ltm / 100] if roe_ltm is not None else [])
        bruto = statistics.fmean(vals) if vals else None
    else:
        bruto = roe_ltm / 100 if roe_ltm is not None else (statistics.fmean(anos) if anos else None)
    if bruto is None:
        return None
    return min(max(bruto, prem['roe_minimo']), prem['roe_maximo'])


def lucro_normalizado(ll_ltm, historico, ciclica):
    """Cíclicas: média dos exercícios disponíveis e do lucro de 12 meses. Demais: lucro de 12 meses se positivo."""
    anos = [h['lucro_liquido'] for h in historico if h.get('lucro_liquido') is not None]
    if ciclica:
        base = anos + ([ll_ltm] if ll_ltm is not None else [])
        return statistics.fmean(base) if base else None
    if ll_ltm is not None and ll_ltm > 0:
        return ll_ltm
    pos = [a for a in anos if a > 0]
    return statistics.fmean(pos) if pos else None


def valor_patrimonio(lucro0, roe, ke, g_curto, g_term, anos=5, fracao_max=0.9):
    """Valor do patrimônio pelo modelo acima. None se ke <= g_term ou entradas inválidas."""
    if lucro0 is None or roe is None or lucro0 <= 0 or roe <= 0 or ke <= g_term:
        return None
    g = min(g_curto, fracao_max * roe)
    gt = min(g_term, fracao_max * roe)
    l = lucro0
    total = 0.0
    for t in range(1, anos + 1):
        l *= 1 + g
        total += l * (1 - g / roe) / (1 + ke) ** t
    vt = l * (1 + gt) * (1 - gt / roe) / (ke - gt)
    return total + vt / (1 + ke) ** anos


def g_implicito(valor_mercado, lucro0, roe, ke, anos=5, lo=-0.05, hi=None, fracao_max=0.9):
    """Crescimento terminal (e de curto prazo, igual) que iguala o modelo ao valor de mercado, por bisseção.
    None se não houver solução na faixa [lo, min(hi, ke - 0.5pp)]."""
    if not valor_mercado or lucro0 is None or lucro0 <= 0 or roe is None or roe <= 0:
        return None
    hi = min(hi if hi is not None else ke - 0.005, ke - 0.005)
    f = lambda g: (valor_patrimonio(lucro0, roe, ke, g, g, anos, fracao_max) or 0) - valor_mercado
    a, b = lo, hi
    if f(a) > 0 or f(b) < 0:
        return None
    for _ in range(60):
        m = (a + b) / 2
        if f(m) < 0:
            a = m
        else:
            b = m
    return (a + b) / 2


def ke_implicito(valor_mercado, lucro0, roe, g_curto, g_term, anos=5, fracao_max=0.9):
    """Taxa de desconto (retorno exigido) que iguala o modelo ao valor de mercado, por bisseção.
    É o retorno esperado de longo prazo embutido no preço, dadas as premissas de crescimento."""
    if not valor_mercado or lucro0 is None or lucro0 <= 0 or roe is None or roe <= 0:
        return None
    f = lambda ke: (valor_patrimonio(lucro0, roe, ke, g_curto, g_term, anos, fracao_max) or float('inf')) - valor_mercado
    a, b = g_term + 0.002, 0.40
    if f(a) < 0 or f(b) > 0:
        return None
    for _ in range(80):
        m = (a + b) / 2
        if f(m) > 0:
            a = m
        else:
            b = m
    return (a + b) / 2


def avaliar(ll_ltm, historico, roe_ltm, valor_mercado, preco, p_vp, perfil, prem, g_curto_cagr=None):
    """Cenários bear/base/bull, grade de sensibilidade e crescimento implícito.

    Devolve dict pronto para gravar no dossiê. Valores por ação = preço x (valor do modelo / valor de mercado),
    o que evita depender da contagem de ações (units e classes)."""
    avisos = []
    anos = prem['horizonte_anos']
    roe = roe_normalizado(roe_ltm, historico, prem, perfil.get('ciclica', False))
    l0 = lucro_normalizado(ll_ltm, historico, perfil.get('ciclica', False))
    if roe is None or l0 is None or l0 <= 0:
        return {'status': 'indisponivel', 'motivo': 'lucro ou ROE normalizado não positivo ou ausente', 'avisos': avisos}
    g_base = perfil.get('g_curto')
    if g_base is None:
        g_base = min(max(g_curto_cagr or 0.06, 0.03), 0.12)
        avisos.append('crescimento de curto prazo estimado pelo CAGR de receita dos exercícios (limitado a 3% a 12%)')
    out = {'status': 'ok', 'lucro_normalizado': l0, 'roe_normalizado_pct': roe * 100, 'ciclica': perfil.get('ciclica', False),
           'g_curto_base_pct': g_base * 100, 'cenarios': {}, 'avisos': avisos}
    for nome, c in prem['cenarios'].items():
        v = valor_patrimonio(l0 * c['fator_lucro'], roe, c['ke'], g_base + c['delta_g_curto'], c['g_terminal'], anos, prem['fracao_max_crescimento_sobre_roe'])
        item = {'ke_pct': c['ke'] * 100, 'g_terminal_pct': c['g_terminal'] * 100, 'g_curto_pct': (g_base + c['delta_g_curto']) * 100,
                'fator_lucro': c['fator_lucro'], 'valor_patrimonio': v}
        if v is not None and valor_mercado:
            item['valor_justo_por_acao'] = preco * v / valor_mercado
            item['margem_pct'] = (v / valor_mercado - 1) * 100
        out['cenarios'][nome] = item
    grade = []
    for ke in prem['grade']['ke']:
        linha = []
        for gt in prem['grade']['g_terminal']:
            v = valor_patrimonio(l0, roe, ke, g_base, gt, anos, prem['fracao_max_crescimento_sobre_roe'])
            linha.append(preco * v / valor_mercado if (v is not None and valor_mercado) else None)
        grade.append(linha)
    out['grade'] = {'ke_pct': [k * 100 for k in prem['grade']['ke']], 'g_terminal_pct': [g * 100 for g in prem['grade']['g_terminal']],
                    'valor_por_acao': grade}
    ke_b = prem['cenarios']['base']['ke']
    gi = g_implicito(valor_mercado, l0, roe, ke_b, anos, fracao_max=prem['fracao_max_crescimento_sobre_roe'])
    out['g_implicito_pct'] = gi * 100 if gi is not None else None
    gt_b = prem['cenarios']['base']['g_terminal']
    ki = ke_implicito(valor_mercado, l0, roe, g_base, gt_b, anos, prem['fracao_max_crescimento_sobre_roe'])
    out['ke_implicito_pct'] = ki * 100 if ki is not None else None
    if p_vp and p_vp > 0:
        # P/VP justificado = (ROE - g) / (ke - g)  =>  ROE exigido para sustentar o P/VP atual
        out['roe_exigido_pct'] = (gt_b + p_vp * (ke_b - gt_b)) * 100
        out['p_vp_atual'] = p_vp
    if gi is None:
        out['avisos'].append('não há crescimento na faixa testada que iguale o modelo ao valor de mercado (preço muito acima ou abaixo do modelo)')
    return out
