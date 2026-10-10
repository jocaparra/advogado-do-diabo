"""Regras numéricas únicas do projeto: quais casas contam, mediana de preço alvo, upsides e nota.

Usado por calcular_derivados.py (que grava os campos derivados), gerar_graficos.py (Figura 4) e
conferir.py (conferência). Mudar uma regra aqui muda o projeto inteiro, sem divergência entre arquivos.
"""
import datetime as dt
import statistics

PADRAO = {
    'janela_meses_alvos': 6,          # alvo mais antigo que isso fica fora da mediana
    'min_casas_consenso': 3,          # abaixo disso a contagem não é consenso
    'casas_fora_da_contagem': [],     # nomes de casa excluídos por decisão da auditoria
    'fontes_fora_da_contagem_de_casas': [],  # trechos do campo "fonte" que invalidam o item
    'peso_desconto_rali': 0.5,        # fração do retorno positivo de 5 pregões descontada do upside
}


def parametros(textos=None):
    """PADRAO + parametros e politica_fontes de textos.json (a semana pode ajustar)."""
    p = dict(PADRAO)
    textos = textos or {}
    p.update({k: v for k, v in textos.get('parametros', {}).items() if k in PADRAO})
    pol = textos.get('politica_fontes', {})
    for k in ('casas_fora_da_contagem', 'fontes_fora_da_contagem_de_casas'):
        if k in pol:
            p[k] = pol[k]
    return p


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def data_iso(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def casa_conta_rating(c, pol):
    """A casa entra na contagem de compra, neutro e venda?"""
    if c.get('situacao') != 'verificada' or c.get('contar_no_consenso') is False:
        return False
    if c.get('casa') in pol['casas_fora_da_contagem']:
        return False
    if any(x in str(c.get('fonte', '')) for x in pol['fontes_fora_da_contagem_de_casas']):
        return False
    return c.get('rating') in ('compra', 'neutro', 'venda')


def contagem_ratings(casas, pol):
    cs = [c for c in casas if casa_conta_rating(c, pol)]
    return {'compra': sum(c['rating'] == 'compra' for c in cs), 'neutro': sum(c['rating'] == 'neutro' for c in cs),
            'venda': sum(c['rating'] == 'venda' for c in cs), 'n_casas': len(cs), 'casas': [c['casa'] for c in cs]}


def mediana_alvos(casas, hoje, pol):
    """(mediana, n, lista) dos preços alvo em R$ das casas contáveis dentro da janela de antiguidade."""
    limite = hoje - dt.timedelta(days=round(pol['janela_meses_alvos'] * 30.4))
    alvos = []
    for c in casas:
        if not casa_conta_rating(c, pol) or c.get('moeda', 'R$') != 'R$' or num(c.get('preco_alvo')) is None:
            continue
        d = data_iso(c.get('data'))
        if d is None or d < limite or d > hoje:
            continue
        alvos.append((c['casa'], c['preco_alvo']))
    valores = [v for _, v in alvos]
    return (statistics.median(valores) if valores else None), len(valores), [n for n, _ in alvos]


def upside(alvo, preco):
    a, p = num(alvo), num(preco)
    return round((a / p - 1) * 100, 1) if a is not None and p else None


def upside_ajustado(up_xp, up_med, ret_5d, pol):
    """Média dos upsides disponíveis menos a fração do retorno positivo de 5 pregões."""
    base = [v for v in (up_xp, up_med) if num(v) is not None]
    if not base:
        return None
    desconto = pol['peso_desconto_rali'] * max(num(ret_5d) or 0.0, 0.0)
    return round(sum(base) / len(base) - desconto, 1)


def nota(componentes, pesos):
    """Soma ponderada dos componentes (0 a 10), arredondada a 2 casas."""
    return round(sum(pesos[k] * componentes[k] for k in pesos), 2)
