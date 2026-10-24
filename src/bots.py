"""Bots do chat: um por agente do projeto. Cada bot responde só com o arquivo que o seu agente grava na
pasta da semana (casas.json, noticias.json, risco.json...), em formato de texto curto com fonte e data.

Nada aqui chama a rede nem o Claude: só lê arquivos e monta o contexto. O que falta vira "não verificado".
"""
import json
import os


def corta(txt, n=900):
    txt = str(txt if txt is not None else '').strip()
    return txt if len(txt) <= n else txt[:n].rstrip() + '...'


def ausente(v):
    return v is None or v == '' or str(v).strip().lower().startswith('não verificado')


def ler(caminho, padrao=None):
    try:
        with open(caminho, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


class Fontes:
    """Tabela de identificadores: F1, F2... -> (fonte, data). Repetidas dividem o identificador."""

    def __init__(self):
        self.itens = {}
        self._por_chave = {}

    def id(self, fonte, data):
        fonte = corta(fonte or 'fonte não informada', 160)
        chave = (fonte, str(data) if data else '')
        if chave not in self._por_chave:
            n = f'F{len(self._por_chave) + 1}'
            self._por_chave[chave] = n
            self.itens[n] = {'fonte': fonte, 'data': str(data) if data else None}
        return self._por_chave[chave]


def _dict(x):
    return x if isinstance(x, dict) else {}


def _lista(x):
    return x if isinstance(x, list) else []


def _sem_arquivo(nome):
    return [f'{nome} não existe nesta semana: tudo sobre este assunto é não verificado.']


# ---------- um construtor de contexto por bot: (pasta, tickers, F) -> linhas ----------

def ctx_advogado(pasta, tks, F):
    j = ler(os.path.join(pasta, 'contra.json'))
    if not isinstance(j, dict):
        return _sem_arquivo('contra.json')
    f0 = F.id('contra.json (advogado)', j.get('data'))
    linhas = [f"Escopo do advogado: {corta(j.get('escopo'), 300)} [{f0}]", f"Veredito geral [{f0}]: {corta(j.get('veredito_geral'), 700)}"]
    for l in _lista(j.get('lacunas'))[:4]:
        linhas.append(f"- lacuna [{f0}]: {corta(l, 250)}")
    resumo = _dict(j.get('resumo_por_ticker'))
    objs = [o for o in _lista(j.get('objecoes')) if isinstance(o, dict)]
    alvo = tks or [o.get('ticker') for o in objs][:8]
    for tk in dict.fromkeys(alvo):
        r = _dict(resumo.get(tk))
        if r:
            linhas.append(f"{tk}: força máxima da objeção {r.get('forca_maxima')} | nota do analista {r.get('nota_sintese')} | nota sugerida pelo advogado {r.get('nota_sugerida')} | ação sugerida {r.get('acao_sugerida')} [{f0}]")
        for o in [o for o in objs if o.get('ticker') == tk][:3 if tks else 1]:
            linhas.append(f"- objeção {tk}, força {o.get('forca')}, muda a nota: {o.get('muda_nota')} [{F.id(o.get('fonte'), o.get('data'))}]: {corta(o.get('objecao'), 500)}")
            if tks and not ausente(o.get('evidencia')):
                linhas.append(f"  evidência: {corta(o.get('evidencia'), 600)}")
        if tks and not [o for o in objs if o.get('ticker') == tk]:
            linhas.append(f"- {tk}: nenhuma objeção registrada nesta semana (fora do escopo do advogado).")
    return linhas


def ctx_auditor(pasta, tks, F):
    a, c = ler(os.path.join(pasta, 'auditoria.json')), ler(os.path.join(pasta, 'conferencia.json'))
    linhas = []
    if isinstance(a, dict):
        f = F.id('auditoria.json', a.get('data'))
        linhas.append(f"Auditoria, rodada {a.get('rodada')} de {a.get('rodadas_maximas')} [{f}]: {a.get('conferidos')} conferidos, "
                      f"{a.get('aprovados')} aprovados, {a.get('reprovados')} reprovados; por severidade: {a.get('reprovados_por_severidade')}.")
        itens = [i for i in _lista(a.get('itens')) if isinstance(i, dict)]
        sel = [i for i in itens if i.get('ticker') in tks] if tks else [i for i in itens if i.get('resultado') == 'reprovado']
        for i in sel[:12]:
            extra = f" | correção registrada: {corta(i['correcao'], 200)}" if i.get('correcao') else ''
            linhas.append(f"- {i.get('ticker') or 'geral'} {i.get('campo')} ({i.get('arquivo')}), {i.get('resultado')} [{f}]: {corta(i.get('motivo'), 260)}{extra}")
    else:
        linhas += _sem_arquivo('auditoria.json')
    if isinstance(c, dict):
        f = F.id('conferencia.json', c.get('data_conferencia'))
        linhas.append(f"Conferência automática [{f}]: {c.get('resumo')}")
        itens = [i for i in _lista(c.get('itens')) if isinstance(i, dict) and (not tks or i.get('ticker') in tks or not i.get('ticker'))]
        for i in itens[:8]:
            linhas.append(f"- {i.get('severidade')} {i.get('regra')} {i.get('ticker') or ''} ({i.get('arquivo')}) [{f}]: {corta(i.get('mensagem'), 220)}")
    return linhas


def ctx_fundamentos(pasta, tks, F):
    j = ler(os.path.join(pasta, 'fundamentos.json'))
    d = _dict(_dict(ler(os.path.join(pasta, 'dossie.json'))).get('tickers'))
    if not isinstance(j, dict) and not d:
        return _sem_arquivo('fundamentos.json')
    t = _dict(_dict(j).get('tickers'))
    f0 = F.id('fundamentos.json (agente, sem CVM)', _dict(j).get('data_coleta'))
    linhas = [f"Observação do agente [{f0}]: {corta(_dict(j).get('observacao'), 300)}"]
    for tk in (tks or list(t)[:14]):
        x = _dict(t.get(tk))
        if not x:
            linhas.append(f"{tk}: sem fundamentos nesta semana (não verificado).")
            continue
        if tks:
            campos = [f"{k}: {corta(v, 220)}" for k, v in x.items() if k not in ('fontes',) and isinstance(v, str)]
            linhas.append(f"DETALHE {tk} [{f0}]: " + ' | '.join(campos))
        else:
            linhas.append(f"{tk}: período {x.get('periodo')} | certeza {x.get('certeza')} [{f0}]")
        dv = _dict(d.get(tk))
        v = _dict(dv.get('valuation'))
        if v.get('status') == 'ok':
            cen = _dict(v.get('cenarios'))
            linhas.append(f"- valuation por cenários (CVM, dossie.json) [{F.id('dossie.json (CVM)', _dict(ler(os.path.join(pasta, 'dossie.json'))).get('data'))}]: "
                          + ', '.join(f"{k} {_dict(cen.get(k)).get('valor_justo_por_acao')}" for k in ('bear', 'base', 'bull')))
        elif tks:
            linhas.append('- valuation por cenários: não verificado (dossie.json não gerado ou sem demonstrações na CVM).')
    return linhas


def ctx_casas(pasta, tks, F):
    j = ler(os.path.join(pasta, 'casas.json'))
    if not isinstance(j, dict):
        return _sem_arquivo('casas.json')
    t = _dict(j.get('tickers'))
    f0 = F.id('casas.json', j.get('data_coleta'))
    linhas = [f"Regra de antiguidade [{f0}]: {corta(j.get('regra_antiguidade'), 300)}"]
    for tk in (tks or list(t)):
        x = _dict(t.get(tk))
        if not x:
            linhas.append(f"{tk}: sem casas nesta semana (não verificado).")
            continue
        linhas.append(f"{tk}: contagem verificada {x.get('contagem_verificada')} | mediana do alvo {x.get('mediana_preco_alvo')} {x.get('moeda_mediana') or ''} "
                      f"com {x.get('n_alvos_mediana')} alvos | status {x.get('status')} | XP {x.get('xp')} [{f0}]")
        if tks:
            if not ausente(x.get('divergencia_xp')):
                linhas.append(f"- divergência da XP [{f0}]: {corta(x['divergencia_xp'], 400)}")
            for c in [c for c in _lista(x.get('casas')) if isinstance(c, dict)][:10]:
                obs = f" | {corta(c['obs'], 160)}" if c.get('obs') else ''
                linhas.append(f"- {c.get('casa')}: {c.get('rating')}, alvo {c.get('moeda') or ''} {c.get('preco_alvo')}, {c.get('situacao')}{obs} [{F.id(c.get('fonte'), c.get('data'))}]")
    return linhas


def ctx_noticias(pasta, tks, F):
    j = ler(os.path.join(pasta, 'noticias.json'))
    if not isinstance(j, dict):
        return _sem_arquivo('noticias.json')
    t = _dict(j.get('tickers'))
    f0 = F.id('noticias.json', j.get('data_coleta'))
    linhas = [f"Janela das notícias [{f0}]: {corta(j.get('janela'), 200)}. {corta(j.get('observacao'), 250)}"]
    for tk in (tks or list(t)):
        x = _dict(t.get(tk))
        itens = [i for i in _lista(x.get('itens')) if isinstance(i, dict)]
        if not tks:
            linhas.append(f"{tk}: {len(itens)} itens, {len(_lista(x.get('eventos_futuros')))} eventos futuros [{f0}].")
            continue
        if not itens:
            linhas.append(f"{tk}: nenhuma notícia nesta semana (não verificado).")
        for i in sorted(itens, key=lambda i: str(i.get('data')), reverse=True)[:6]:
            linhas.append(f"- {tk} {i.get('data')}, {i.get('tipo')}, impacto {i.get('impacto')}, certeza {i.get('certeza')} [{F.id(i.get('fonte'), i.get('data'))}]: {corta(i.get('resumo'), 350)}")
        for e in [e for e in _lista(x.get('eventos_futuros')) if isinstance(e, dict)][:4]:
            linhas.append(f"- evento futuro {tk}: {e.get('evento')}, data {e.get('data')}, certeza {e.get('certeza')} [{F.id(e.get('fonte'), j.get('data_coleta'))}]")
    return linhas


def ctx_fluxo(pasta, tks, F):
    j = ler(os.path.join(pasta, 'fluxo.json'))
    if not isinstance(j, dict):
        return _sem_arquivo('fluxo.json')
    f0 = F.id('fluxo.json', j.get('data_calculo'))
    linhas = [f"Retornos do Ibovespa [{f0}]: {j.get('retornos_ibovespa')}. {corta(j.get('nota'), 250)}"]
    a = _dict(j.get('acoes'))
    for tk in (tks or list(a)):
        x = _dict(a.get(tk))
        if not x:
            linhas.append(f"{tk}: sem dados de fluxo (não verificado).")
            continue
        linhas.append(f"{tk}: retorno 5d {x.get('retorno_5d_pct')}%, 30d {x.get('retorno_30d_pct')}%, 90d {x.get('retorno_90d_pct')}% | "
                      f"contra o Ibovespa (pp) 5d {x.get('diferenca_5d_pp')}, 30d {x.get('diferenca_30d_pp')}, 90d {x.get('diferenca_90d_pp')} | "
                      f"acima da MM50: {x.get('acima_mm50')}, da MM200: {x.get('acima_mm200')} | distância da máxima de 52 semanas {x.get('distancia_max_52w_pct')}% | "
                      f"volume 5d/90d {x.get('razao_volume_5d_90d')} | volatilidade {x.get('vol_anualizada_pct')}% | beta {x.get('beta_90d')} [{f0}]")
    return linhas


def ctx_macro(pasta, tks, F):
    j = ler(os.path.join(pasta, 'macro.json'))
    if not isinstance(j, dict):
        return _sem_arquivo('macro.json')
    linhas = []
    for i in [i for i in _lista(j.get('indicadores')) if isinstance(i, dict)][:20]:
        linhas.append(f"- {i.get('indicador')}: {i.get('valor_atual')} {i.get('unidade') or ''} (dado de {i.get('data_do_dado')}); 3 meses: {corta(i.get('variacao_3m'), 120)} [{F.id(i.get('fonte'), i.get('data_coleta'))}]")
    p = _dict(j.get('cenario_politico'))
    if p:
        linhas.append(f"Cenário político [{F.id('macro.json (cenário político)', p.get('data_coleta'))}]: {corta(p.get('fato'), 400)} Leitura: {corta(p.get('leitura'), 400)}")
    f0 = F.id('macro.json', j.get('data_coleta'))
    for setor, e in list(_dict(j.get('efeito_por_setor_4_semanas')).items())[:12]:
        e = _dict(e)
        linhas.append(f"- efeito em {setor} ({e.get('tipo')}): {e.get('efeito')}. {corta(e.get('motivo'), 220)} [{f0}]")
    for e in [e for e in _lista(j.get('eventos_4_semanas')) if isinstance(e, dict)][:8]:
        linhas.append(f"- evento {e.get('data')}: {e.get('evento')} (certeza {e.get('certeza')}; {corta(e.get('nota'), 100)}) [{f0}]")
    linhas.append(f"Risco central [{f0}]: {corta(j.get('risco_central'), 600)}")
    return linhas


def ctx_risco(pasta, tks, F):
    j = ler(os.path.join(pasta, 'risco.json'))
    if not isinstance(j, dict):
        return _sem_arquivo('risco.json')
    f0 = F.id('risco.json', j.get('data'))
    linhas = [f"Método [{f0}]: {corta(json.dumps(j.get('metodo'), ensure_ascii=False), 500)}", f"Resumo [{f0}]: {corta(j.get('resumo'), 700)}"]
    t = _dict(j.get('tabela_por_ticker'))
    for tk in (tks or list(t)):
        x = _dict(t.get(tk))
        if not x:
            linhas.append(f"{tk}: sem risco calculado (não verificado).")
        elif tks:
            linhas.append(f"{tk} [{f0}]: " + ', '.join(f"{k} {v}" for k, v in x.items()))
        else:
            linhas.append(f"{tk}: volatilidade {x.get('vol_90pregoes_anual_pct')}% | beta {x.get('beta_ibov_multifator')} | setor {x.get('setor')} [{f0}]")
    for k in ('queda_conjunta_top5', 'concentracao_setorial', 'limites', 'cenarios_estresse_4_semanas'):
        if j.get(k):
            linhas.append(f"{k} [{f0}]: {corta(json.dumps(j[k], ensure_ascii=False), 700)}")
    return linhas


def ctx_monitor(pasta, tks, F):
    j = ler(os.path.join(pasta, 'alertas.json'))
    if not isinstance(j, dict):
        return _sem_arquivo('alertas.json')
    linhas = [f"Critério [{F.id('alertas.json', j.get('data'))}]: {corta(j.get('criterio'), 300)}", f"Resumo: {corta(j.get('resumo'), 300)}"]
    for a in [a for a in _lista(j.get('alertas')) if isinstance(a, dict) and (not tks or a.get('ticker') in tks)][:10]:
        linhas.append(f"- {a.get('nivel')} {a.get('ticker')} [{F.id(a.get('fonte'), a.get('data'))}]: {corta(a.get('fato'), 450)} Impacto: {corta(a.get('impacto'), 200)} "
                      f"Ação: {corta(a.get('acao_recomendada'), 160)} (certeza {a.get('certeza')}; auditoria {a.get('status_auditoria')})")
    return linhas


# O analista usa o contexto do ranking montado em chat.py (tese, prós e contras, valuation).
BOTS = {
    'analista': {'nome': 'Analista', 'mono': 'AN', 'descricao': 'Sintetiza os dados, pontua cada ação e monta o ranking.',
                 'papel': 'Você explica o ranking: notas, ação sugerida, certeza, tese, prós, contras, riscos e onde o modelo discorda da XP.',
                 'sugestoes': ['Qual a tese de {t}?', 'Compare {t} e {t2}', 'Onde o modelo discorda da XP?'], 'ctx': None},
    'advogado': {'nome': 'Advogado', 'mono': 'AD', 'descricao': 'Ataca o ranking com contrapontos fundamentados.',
                 'papel': 'Você é o advogado do diabo: expõe as objeções contra o ranking e o que o analista ignorou.',
                 'sugestoes': ['Qual a objeção mais forte em {t}?', 'O que o advogado não conseguiu verificar?', 'Qual o veredito geral?'], 'ctx': ctx_advogado},
    'auditor': {'nome': 'Auditor', 'mono': 'AU', 'descricao': 'Confere dados, fontes, cálculos e coerência.',
                'papel': 'Você é o auditor: diz o que foi conferido, o que foi reprovado e o que foi corrigido.',
                'sugestoes': ['O que o auditor reprovou?', 'Os números de {t} conferem?', 'Quantos itens foram conferidos?'], 'ctx': ctx_auditor},
    'fundamentos': {'nome': 'Fundamentos', 'mono': 'FU', 'descricao': 'Indicadores fundamentalistas e valuation.',
                    'papel': 'Você responde sobre indicadores, resultados e valuation, e aponta o que não foi verificado.',
                    'sugestoes': ['Quais indicadores de {t} estão verificados?', 'O que falta no valuation de {t}?', 'Qual o resultado mais recente de {t2}?'], 'ctx': ctx_fundamentos},
    'casas': {'nome': 'Casas', 'mono': 'CA', 'descricao': 'Recomendações e preços alvo das casas de análise.',
              'papel': 'Você responde sobre recomendações, alvos, mediana e divergência das casas contra a XP.',
              'sugestoes': ['O que as casas dizem de {t}?', 'Quais alvos ficaram fora da mediana?', 'Onde a XP diverge das casas?'], 'ctx': ctx_casas},
    'noticias': {'nome': 'Notícias', 'mono': 'NO', 'descricao': 'Fatos relevantes e comunicados recentes.',
                 'papel': 'Você responde sobre notícias e fatos recentes, separando fato, opinião e projeção, e eventos futuros.',
                 'sugestoes': ['Quais as notícias recentes de {t}?', 'Há eventos futuros para {t}?', 'O que mudou em {t2}?'], 'ctx': ctx_noticias},
    'fluxo': {'nome': 'Fluxo', 'mono': 'FL', 'descricao': 'Momentum, volume e sinais técnicos.',
              'papel': 'Você responde sobre retornos, momentum, volume, médias móveis, volatilidade e beta.',
              'sugestoes': ['Como está o momentum de {t}?', 'Quem está acima da média de 200 dias?', 'Quem ficou atrás do Ibovespa em 30 dias?'], 'ctx': ctx_fluxo},
    'macro': {'nome': 'Macro', 'mono': 'MA', 'descricao': 'Cenário macroeconômico, político e externo.',
              'papel': 'Você responde sobre juros, câmbio, inflação, cenário eleitoral, fatores externos e efeito por setor.',
              'sugestoes': ['Qual o risco central da semana?', 'Qual o efeito macro por setor?', 'Quais eventos vêm nas próximas semanas?'], 'ctx': ctx_macro},
    'risco': {'nome': 'Risco', 'mono': 'RI', 'descricao': 'Risco da carteira como um todo.',
              'papel': 'Você responde sobre volatilidade, beta, correlação, concentração e cenários de estresse.',
              'sugestoes': ['Qual o risco de {t}?', 'Há queda conjunta no top 5?', 'Qual a concentração por setor?'], 'ctx': ctx_risco},
    'monitor': {'nome': 'Monitor', 'mono': 'MO', 'descricao': 'Alertas sobre os tickers da carteira.',
                'papel': 'Você responde sobre os alertas da semana: nível, fato, impacto e ação recomendada.',
                'sugestoes': ['Há alertas esta semana?', 'Qual o alerta mais urgente?', 'Há alertas sobre {t}?'], 'ctx': ctx_monitor},
}
ORDEM = list(BOTS)

# Arquivos da semana que cada bot lê (o primeiro é o principal). Aparecem no cartão do bot, como os "apps" do kit de design.
ARQUIVOS = {
    'analista': ('sintese.json', 'xp.json'), 'advogado': ('contra.json',), 'auditor': ('auditoria.json', 'conferencia.json'),
    'fundamentos': ('fundamentos.json', 'dossie.json'), 'casas': ('casas.json',), 'noticias': ('noticias.json',),
    'fluxo': ('fluxo.json',), 'macro': ('macro.json',), 'risco': ('risco.json',), 'monitor': ('alertas.json',),
}
_CHAVES_DATA = ('data', 'data_coleta', 'data_calculo', 'data_conferencia', 'data_relatorio')


def estado(pasta):
    """Por bot: arquivos lidos (existem?), data dos dados e se o arquivo principal está na pasta da semana."""
    saida = {}
    for k in ORDEM:
        nomes = ARQUIVOS[k]
        arquivos = [{'nome': n, 'existe': bool(pasta) and os.path.isfile(os.path.join(pasta, n))} for n in nomes]
        j = ler(os.path.join(pasta, nomes[0])) if pasta and arquivos[0]['existe'] else None
        data = next((j[c] for c in _CHAVES_DATA if isinstance(j, dict) and isinstance(j.get(c), str)), None)
        saida[k] = {'arquivos': arquivos, 'pronto': arquivos[0]['existe'], 'data': data}
    return saida


def lista():
    return [{'id': k, 'nome': BOTS[k]['nome'], 'mono': BOTS[k]['mono'], 'descricao': BOTS[k]['descricao'],
             'sugestoes': BOTS[k]['sugestoes']} for k in ORDEM]


def persona(bot):
    """Linha acrescentada ao prompt de sistema: papel do bot e para onde mandar o que não é dele."""
    b = BOTS[bot]
    outros = '; '.join(f"{BOTS[k]['nome']} ({BOTS[k]['descricao'].rstrip('.').lower()})" for k in ORDEM if k != bot)
    return (f"\nVocê é o bot {b['nome']}. {b['papel']} Responda só dentro deste escopo. "
            f"Se a pergunta for de outro assunto, diga qual bot consultar: {outros}.")


def montar(bot, pasta, tickers, F):
    """Linhas de contexto do bot a partir dos arquivos da pasta da semana (bots diferentes do analista)."""
    return BOTS[bot]['ctx'](pasta, list(tickers), F)
