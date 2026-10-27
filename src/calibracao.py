"""Calibração: o que a "certeza" do ranking diz sobre o que aconteceu depois.

Evento medido: retorno total da ação > retorno total do Ibovespa no horizonte (excesso_pp > 0). "Certeza" é um nível
qualitativo (alta, média, baixa), NÃO uma probabilidade; aqui só se mede a frequência observada por nível, com
intervalo de confiança e portão de amostra. Brier e log loss ficam prontos para quando o sistema emitir
probabilidades numéricas (hoje não emite); nada converte nota ou certeza em probabilidade.
"""
import math


def brier(p, y):
    """Erro quadrático médio entre probabilidade prevista e resultado (0/1). Menor é melhor; constante 0,5 dá 0,25."""
    if not p or len(p) != len(y):
        return None
    return sum((a - b) ** 2 for a, b in zip(p, y)) / len(p)


def log_loss(p, y, eps=1e-12):
    """Log loss médio; probabilidades são aparadas em [eps, 1-eps] para não explodir em 0 ou 1."""
    if not p or len(p) != len(y):
        return None
    t = 0.0
    for a, b in zip(p, y):
        a = min(max(a, eps), 1 - eps)
        t -= b * math.log(a) + (1 - b) * math.log(1 - a)
    return t / len(p)


def curva(p, y, faixas=5):
    """[{faixa, n, previsto_medio, observado}] por faixas iguais de probabilidade (faixas vazias ficam de fora)."""
    saida = []
    for k in range(faixas):
        lo, hi = k / faixas, (k + 1) / faixas
        grupo = [(a, b) for a, b in zip(p, y) if lo <= a < hi or (k == faixas - 1 and a == 1.0)]
        if grupo:
            saida.append({'faixa': [round(lo, 3), round(hi, 3)], 'n': len(grupo),
                          'previsto_medio': round(sum(a for a, _ in grupo) / len(grupo), 4),
                          'observado': round(sum(b for _, b in grupo) / len(grupo), 4)})
    return saida


def wilson(k, n, z=1.96):
    """Intervalo de Wilson (95%) para uma proporção k/n, em %. None sem observações."""
    if n <= 0:
        return None
    ph = k / n
    d = 1 + z * z / n
    centro = (ph + z * z / (2 * n)) / d
    meia = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return [round(100 * max(0.0, centro - meia), 1), round(100 * min(1.0, centro + meia), 1)]


def por_grupo(obs, campo, min_obs, min_semanas):
    """Frequência observada por valor de `campo` (ex.: 'certeza').

    Por grupo: n, semanas distintas, % com excesso > 0 e % de acerto direcional (acertos / (acertos + erros)), ambos
    com intervalo de Wilson. As observações de uma mesma semana são correlacionadas: o intervalo é otimista, e por isso
    o portão exige também semanas distintas. `amostra`: 'suficiente' ou 'insuficiente' por grupo."""
    grupos = {}
    for o in obs:
        grupos.setdefault(o.get(campo) or 'não informada', []).append(o)
    out = {}
    for g, lista in sorted(grupos.items()):
        n = len(lista)
        acima = sum(o['excesso_pp'] > 0 for o in lista)
        dire = [o for o in lista if o.get('veredito') in ('acerto', 'erro')]
        acertos = sum(o['veredito'] == 'acerto' for o in dire)
        semanas = len({o['semana'] for o in lista})
        out[g] = {'n': n, 'semanas': semanas,
                  'acima_ibov_pct': round(100 * acima / n, 1), 'acima_ibov_ic95': wilson(acima, n),
                  'direcionais': len(dire),
                  'acerto_direcional_pct': round(100 * acertos / len(dire), 1) if dire else None,
                  'acerto_direcional_ic95': wilson(acertos, len(dire)),
                  'amostra': 'suficiente' if n >= min_obs and semanas >= min_semanas else 'insuficiente'}
    return out
