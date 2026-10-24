"""Servidor local da interface (app/). Só biblioteca padrão; escuta apenas em 127.0.0.1.

uso: python3 src/servidor.py [--porta 8765]

Serve app/ e uma API de leitura sobre a pasta semana_* mais recente (sintese.json, contra.json,
dossie.json etc.). Nada é inventado: o que falta nos arquivos chega como null e a tela mostra
"não verificado" ou "pendente".

Dados pessoais: o CSV da carteira fica só em memória, nunca vai para disco por aqui. O plano usa o
mesmo arquivo privado de src/plano.py (~/.config), fora do repositório.

Celular: `--celular` abre o servidor para a rede local (mesmo Wi-Fi) e exige um token aleatório,
impresso na URL que você abre no aparelho. Sem a opção, só o próprio computador acessa. A rede local
usa HTTP sem criptografia: use só em rede de confiança.

Rotina semanal: o botão só dispara `claude -p "/semana"` depois de uma confirmação explícita no
corpo da requisição, e uma execução por vez.
"""
import argparse
import glob
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import unicodedata
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
APP = os.path.join(RAIZ, 'app')
sys.path.insert(0, AQUI)

import agenda as AG  # noqa: E402
import bots as BT  # noqa: E402
import chat as CH  # noqa: E402
import minha_carteira as MC  # noqa: E402
import plano as PL  # noqa: E402

MAX_CORPO = 200_000
TICKER_RE = re.compile(r'^[A-Z0-9]{4,7}$')
SEMANA_RE = re.compile(r'^semana_[0-9A-Za-z_]+$')
RATING_PARA_ACAO = {'compra': 'comprar', 'neutro': 'aguardar', 'venda': 'evitar'}
FORCA = {'forte': 0, 'alta': 0, 'media': 1, 'moderada': 1, 'fraca': 2, 'baixa': 2}
ETAPAS = [  # (nome, arquivos que provam a etapa)
    ('Leitor do PDF mensal', ('xp.json',)),
    ('Preços e casas', ('precos.json', 'casas.json')),
    ('Notícias, fluxo e macro', ('noticias.json', 'fluxo.json', 'macro.json')),
    ('Fundamentos CVM', ('fundamentos.json',)),
    ('Analista e risco', ('sintese.json', 'risco.json')),
    ('Advogado do diabo', ('contra.json',)),
    ('Auditor', ('auditoria.json', 'conferencia.json')),
    ('Gráficos e relatório', ('relatorio.pdf',)),
]
HORIZONTES_AVALIACAO = ('1_semana', '4_semanas', '12_semanas')

_trava = threading.Lock()
_trava_chat = threading.Lock()   # uma pergunta por vez: cada resposta consome uso do Claude
MEMORIA = {'carteira': None}
JOB = {'estado': 'parado', 'inicio': None, 'fim': None, 'codigo': None, 'processo': None}
LANCADOR = subprocess.Popen  # trocado nos testes


# ---------- leitura de arquivos ----------

def ler(caminho, padrao=None):
    try:
        with open(caminho, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def _norm(s):
    return unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().strip().lower()


def semanas(raiz=None, exigir_sintese=True):
    """Pastas semana_* em ordem decrescente de nome."""
    raiz = raiz or RAIZ
    pastas = [p for p in glob.glob(os.path.join(raiz, 'semana_*')) if os.path.isdir(p)]
    if exigir_sintese:
        pastas = [p for p in pastas if os.path.isfile(os.path.join(p, 'sintese.json'))]
    return sorted(pastas, key=os.path.basename, reverse=True)


def pasta_semana(nome=None, raiz=None):
    """Pasta pedida (validada) ou a mais recente com sintese.json; None se não houver."""
    if nome:
        if not SEMANA_RE.match(nome):
            return None
        p = os.path.join(raiz or RAIZ, nome)
        return p if os.path.isfile(os.path.join(p, 'sintese.json')) else None
    achadas = semanas(raiz)
    return achadas[0] if achadas else None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ---------- semana ----------

def diferenca_xp(acao, rating):
    esperado = RATING_PARA_ACAO.get(_norm(rating))
    if not esperado or not acao:
        return None
    return 'concorda' if esperado == _norm(acao) else 'discorda'


def semana(pasta):
    s = ler(os.path.join(pasta, 'sintese.json'), {})
    itens = []
    for r in s.get('ranking', []):
        if not isinstance(r, dict) or not r.get('ticker'):
            continue
        nota = _num(r.get('nota'))
        itens.append({
            'posicao': r.get('posicao'), 'ticker': r['ticker'], 'setor': r.get('setor'), 'nota': nota,
            'acao': r.get('acao_sugerida'), 'certeza': r.get('certeza'), 'preco': _num(r.get('preco_atual')),
            'data_cotacao': r.get('data_cotacao'), 'rating_xp': r.get('rating_xp'),
            'diferenca': diferenca_xp(r.get('acao_sugerida'), r.get('rating_xp')),
            'upside_ajustado_pct': _num(r.get('upside_ajustado_pct')), 'sem_dados': nota is None,
        })
    return {'semana': os.path.basename(pasta), 'data': s.get('data'), 'ranking': itens,
            'fonte': 'sintese.json', 'semanas_disponiveis': [os.path.basename(p) for p in semanas()]}


# ---------- dossiê e objeções ----------

def _metrica(rotulo, valor, unidade, fonte, data):
    ok = _num(valor) is not None
    return {'rotulo': rotulo, 'valor': valor if ok else None, 'unidade': unidade if ok else None,
            'fonte': fonte if ok else None, 'data': data if ok else None}


def _roe_texto(txt):
    """Número no início do texto de fundamentos.json (ex.: '21,4% ...'); None se não houver."""
    m = re.match(r'\s*(-?\d+(?:[.,]\d+)?)\s*%', str(txt or ''))
    return float(m.group(1).replace(',', '.')) if m else None


def dossie(pasta, ticker):
    s = ler(os.path.join(pasta, 'sintese.json'), {})
    item = next((r for r in s.get('ranking', []) if isinstance(r, dict) and r.get('ticker') == ticker), None)
    if not item:
        return None
    dos = (ler(os.path.join(pasta, 'dossie.json'), {}).get('tickers') or {})
    dos = dos.get(ticker) if isinstance(dos, dict) else None
    yahoo = (ler(os.path.join(pasta, 'precos_yahoo.json'), {}).get('acoes') or {}).get(ticker) or {}
    fund = (ler(os.path.join(pasta, 'fundamentos.json'), {}).get('tickers') or {}).get(ticker) or {}
    ind = (dos or {}).get('indicadores') or {}
    data_dos = ler(os.path.join(pasta, 'dossie.json'), {}).get('data') or s.get('data')
    y_data = yahoo.get('data_cotacao')

    def da_cvm(chave):
        x = ind.get(chave) or {}
        return x.get('valor'), x.get('unidade')

    roe_v, roe_u = da_cvm('roe_12m')
    if _num(roe_v) is not None:
        roe = _metrica('ROE', roe_v, roe_u, 'CVM · dossie.json', data_dos)
    else:
        roe = _metrica('ROE', _roe_texto(fund.get('roe')), '%', 'fundamentos.json (agente, sem CVM)', s.get('data'))
    pl_v, pl_u = da_cvm('p_l')
    pl = (_metrica('P/L', pl_v, pl_u, 'CVM · dossie.json', data_dos) if _num(pl_v) is not None
          else _metrica('P/L', yahoo.get('p_l'), None, 'Yahoo, não auditado', y_data))
    pvp_v, pvp_u = da_cvm('p_vp')
    pvp = (_metrica('P/VP', pvp_v, pvp_u, 'CVM · dossie.json', data_dos) if _num(pvp_v) is not None
           else _metrica('P/VP', yahoo.get('p_vp'), None, 'Yahoo, não auditado', y_data))

    val = (dos or {}).get('valuation') or {}
    valuation = None
    if val.get('status') == 'ok' and isinstance(val.get('cenarios'), dict):
        cen = {k: {'valor': _num(c.get('valor_justo_por_acao')), 'margem_pct': _num(c.get('margem_pct'))}
               for k, c in val['cenarios'].items() if isinstance(c, dict) and k in ('bear', 'base', 'bull')}
        if all(cen.get(k, {}).get('valor') is not None for k in ('bear', 'base', 'bull')):
            valuation = {'cenarios': cen, 'preco': _num((dos or {}).get('preco')) or _num(item.get('preco_atual')),
                         'ke_implicito_pct': _num(val.get('ke_implicito_pct')),
                         'g_implicito_pct': _num(val.get('g_implicito_pct')),
                         'fonte': 'CVM · dossie.json', 'data': data_dos}
    checklist = [{'rotulo': c.get('rotulo'), 'valor': c.get('valor'), 'fonte': c.get('fonte'), 'data': c.get('data'),
                  'status': c.get('status')} for c in (dos or {}).get('checklist') or [] if isinstance(c, dict)]
    return {
        'ticker': ticker, 'setor': item.get('setor'), 'acao': item.get('acao_sugerida'), 'nota': _num(item.get('nota')),
        'certeza': item.get('certeza'), 'preco': _num(item.get('preco_atual')), 'data_cotacao': item.get('data_cotacao'),
        'rating_xp': item.get('rating_xp'), 'diferenca': diferenca_xp(item.get('acao_sugerida'), item.get('rating_xp')),
        'metricas': [roe, pl, pvp], 'valuation': valuation, 'checklist': checklist,
        'tese': item.get('tese'), 'principal_motivo': item.get('principal_motivo'), 'semana': os.path.basename(pasta),
        'data': s.get('data'),
    }


def objecoes(pasta, ticker):
    s = ler(os.path.join(pasta, 'sintese.json'), {})
    item = next((r for r in s.get('ranking', []) if isinstance(r, dict) and r.get('ticker') == ticker), None)
    if not item:
        return None
    xp = ler(os.path.join(pasta, 'xp.json'), {})
    acao_xp = next((a for a in xp.get('acoes', []) if a.get('ticker') == ticker), {})
    contra = ler(os.path.join(pasta, 'contra.json'), {})
    obj = [o for o in contra.get('objecoes', []) if isinstance(o, dict) and o.get('ticker') == ticker]
    obj.sort(key=lambda o: FORCA.get(_norm(o.get('forca')), 3))
    audit = ler(os.path.join(pasta, 'auditoria.json'), {})
    confer = ler(os.path.join(pasta, 'conferencia.json'), {})
    checks = []
    for i in audit.get('itens', []):
        if isinstance(i, dict) and i.get('ticker') == ticker:
            estado = {'aprovado': 'confere', 'reprovado': 'nao_confere'}.get(_norm(i.get('resultado')), 'nao_verificado')
            detalhe = i.get('motivo') or i.get('verificacao') or ''
            if estado == 'nao_confere' and i.get('correcao'):
                detalhe = f"{detalhe} Correção registrada: {i['correcao']}".strip()
            checks.append({'estado': estado, 'texto': f"{i.get('campo')} ({i.get('arquivo')})",
                           'detalhe': detalhe, 'fonte': 'auditoria.json'})
    for i in confer.get('itens', []):
        if isinstance(i, dict) and i.get('ticker') == ticker:
            checks.append({'estado': 'nao_confere' if _norm(i.get('severidade')) == 'erro' else 'nao_verificado',
                           'texto': i.get('mensagem'), 'detalhe': f"{i.get('regra')} · {i.get('arquivo')}",
                           'fonte': 'conferencia.json'})
    checks.sort(key=lambda c: {'nao_confere': 0, 'nao_verificado': 1, 'confere': 2}[c['estado']])
    return {
        'ticker': ticker, 'semana': os.path.basename(pasta), 'data': s.get('data'),
        'tese_xp': {'texto': acao_xp.get('comentario_mes'), 'rating': acao_xp.get('rating'),
                    'fonte': 'XP Research', 'data': xp.get('data_relatorio')} if acao_xp else None,
        'objecoes': [{'tipo_alvo': o.get('tipo_alvo'), 'objecao': o.get('objecao'), 'evidencia': o.get('evidencia'),
                      'fonte': o.get('fonte'), 'data': o.get('data'), 'forca': o.get('forca'),
                      'muda_nota': o.get('muda_nota')} for o in obj],
        'escopo_advogado': contra.get('escopo'), 'conferencias': checks,
        'gatilho_revisao': item.get('gatilho_revisao'), 'divergencia_xp': item.get('divergencia_xp'),
    }


# ---------- desempenho ----------

def desempenho(raiz=None):
    raiz = raiz or RAIZ
    av = ler(os.path.join(raiz, 'avaliacao.json'))
    if not isinstance(av, dict):
        return {'disponivel': False, 'motivo': 'avaliacao.json ainda não existe: rode a rotina semanal.'}
    minimos = av.get('minimos_para_conclusao') or {}
    saida = {'disponivel': True, 'data': av.get('data_avaliacao'), 'semanas_no_historico': av.get('semanas_no_historico'),
             'minimos': minimos, 'horizontes': {}, 'cdi': None}
    for hz in HORIZONTES_AVALIACAO:
        h = (av.get('horizontes') or {}).get(hz) or {}
        obs = [o for o in (av.get('observacoes') or {}).get(hz, []) if isinstance(o, dict)
               and o.get('acao') == 'comprar' and _num(o.get('retorno_pct')) is not None and _num(o.get('ibovespa_pct')) is not None]
        por_sem = {}
        for o in obs:
            por_sem.setdefault(o.get('semana'), []).append(o)
        serie = []
        for sem in sorted(k for k in por_sem if k):
            g = por_sem[sem]
            serie.append({'semana': sem, 'n': len(g),
                          'bot': round(sum(o['retorno_pct'] for o in g) / len(g), 2),
                          'ibov': round(sum(o['ibovespa_pct'] for o in g) / len(g), 2)})
        saida['horizontes'][hz] = {
            'observacoes': h.get('observacoes', 0), 'semanas': h.get('semanas', 0), 'amostra': h.get('amostra'),
            'pendentes': h.get('pendentes', 0), 'proventos_completo': (h.get('proventos') or {}).get('completo'),
            'serie_comprar': serie,
            'media_bot': round(sum(p['bot'] for p in serie) / len(serie), 2) if serie else None,
            'media_ibov': round(sum(p['ibov'] for p in serie) / len(serie), 2) if serie else None,
        }
    return saida


# ---------- rotina ----------

def _estado_job():
    with _trava:
        p = JOB['processo']
        if JOB['estado'] == 'rodando' and p is not None and p.poll() is not None:
            JOB['estado'] = 'concluido' if p.returncode == 0 else 'falhou'
            JOB['codigo'] = p.returncode
            JOB['fim'] = time.time()
        return {k: JOB[k] for k in ('estado', 'inicio', 'fim', 'codigo')}


def rotina(raiz=None):
    raiz = raiz or RAIZ
    pastas = semanas(raiz, exigir_sintese=False)
    pasta = pastas[0] if pastas else None
    job = _estado_job()
    rodando = job['estado'] == 'rodando'
    passos, achou_atual = [], False
    for nome, arquivos in ETAPAS:
        feitos = bool(pasta) and all(os.path.isfile(os.path.join(pasta, a)) for a in arquivos)
        if feitos:
            estado = 'ok'
        elif rodando and not achou_atual:
            estado, achou_atual = 'agora', True
        else:
            estado = 'fila'
        passos.append({'nome': nome, 'estado': estado, 'arquivo': arquivos[0] if len(arquivos) == 1 else None,
                       'arquivos': list(arquivos)})
    return {'semana': os.path.basename(pasta) if pasta else None, 'job': job, 'passos': passos,
            'concluidas': sum(1 for p in passos if p['estado'] == 'ok'), 'total': len(passos)}


def iniciar_rotina(raiz=None):
    """Dispara a rotina semanal. Devolve (ok, mensagem)."""
    raiz = raiz or RAIZ
    with _trava:
        if JOB['estado'] == 'rodando' and JOB['processo'] is not None and JOB['processo'].poll() is None:
            return False, 'Já existe uma rodada em andamento.'
    hoje = time.strftime('%Y%m%d')
    log = os.path.join(raiz, '.cache', 'rotina.log')
    os.makedirs(os.path.dirname(log), exist_ok=True)
    try:
        with open(log, 'ab') as saida:   # o processo filho herda o descritor; o nosso pode fechar
            proc = LANCADOR(['claude', '-p', f'/semana {hoje}'], cwd=raiz, stdout=saida, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL)
    except OSError as e:
        return False, f'Não consegui iniciar o claude: {e}'
    with _trava:
        JOB.update(estado='rodando', inicio=time.time(), fim=None, codigo=None, processo=proc)
    return True, f'Rodada iniciada para {hoje}. Log em .cache/rotina.log.'


# ---------- minha carteira e plano ----------

def minha_carteira_ler(pasta):
    with _trava:
        mem = MEMORIA['carteira']
    if mem:
        return dict(mem, origem='memória (CSV importado nesta sessão)')
    arq = ler(os.path.join(pasta, 'minha_carteira.json')) if pasta else None
    if isinstance(arq, dict):
        return dict(arq, origem='arquivo local da semana (não versionado)')
    return {'vazio': True}


def minha_carteira_importar(pasta, texto):
    posicoes = MC.ler_posicoes(texto)  # ValueError com mensagem clara
    ranking, pesos_xp, _ = MC.carregar_semana(pasta)
    res = MC.cruzar(posicoes, ranking, pesos_xp, PL.ler_plano())
    with _trava:
        MEMORIA['carteira'] = res
    return dict(res, origem='memória (CSV importado nesta sessão)')


def plano_ler():
    return {'plano': PL.ler_plano(), 'padrao': PL.PADRAO, 'horizontes': list(PL.HORIZONTES),
            'objetivos': list(PL.OBJETIVOS)}


# ---------- chat ----------

def chat_status(pasta=None):
    estados = BT.estado(pasta)
    return {'disponivel': bool(shutil.which('claude')), 'modelo': CH.MODELO,
            'bots': [dict(b, **estados[b['id']]) for b in BT.lista()]}


def _historico_valido(h):
    if h is None:
        return []
    if not isinstance(h, list):
        raise Erro(400, 'historico deve ser uma lista.')
    saida = []
    for t in h[-CH.MAX_TURNOS:]:
        if not isinstance(t, dict) or t.get('papel') not in ('usuario', 'assistente') or not isinstance(t.get('texto'), str):
            raise Erro(400, 'historico inválido.')
        saida.append({'papel': t['papel'], 'texto': t['texto'][:CH.MAX_TEXTO_TURNO]})
    return saida


def chat_responder(pasta, corpo):
    if not isinstance(corpo, dict):
        raise Erro(400, 'Corpo inválido.')
    pergunta = corpo.get('pergunta')
    if not isinstance(pergunta, str) or not pergunta.strip():
        raise Erro(400, 'Escreva uma pergunta.')
    if len(pergunta) > CH.MAX_PERGUNTA:
        raise Erro(400, f'A pergunta passou de {CH.MAX_PERGUNTA} caracteres.')
    historico = _historico_valido(corpo.get('historico'))
    bot = corpo.get('bot', 'analista')
    if not isinstance(bot, str) or bot not in BT.BOTS:
        raise Erro(400, 'Bot desconhecido.')
    sem = semana(pasta)
    sint = ler(os.path.join(pasta, 'sintese.json'), {})
    conhecidos = {r['ticker'] for r in sem['ranking']}
    recentes = ' '.join(t['texto'] for t in historico[-2:])
    citados = CH.tickers_citados(pergunta, conhecidos) or CH.tickers_citados(recentes, conhecidos)
    detalhes = {}
    for tk in (citados[:3] if bot == 'analista' else []):   # os outros bots leem o próprio arquivo
        d, o = dossie(pasta, tk), objecoes(pasta, tk)
        item = next((r for r in sint.get('ranking', []) if r.get('ticker') == tk), {})
        detalhes[tk] = {'item': item, 'objecoes': o['objecoes'], 'tese_xp': o['tese_xp'], 'valuation': d['valuation'],
                        'metricas': d['metricas'], 'conferencias': o['conferencias']}
    dados = {'semana': sem['semana'], 'data': sem['data'], 'ranking': sem['ranking'], 'conclusoes': sint.get('conclusoes_semana')}
    carteira = None
    if corpo.get('carteira') is True:
        with _trava:
            carteira = MEMORIA['carteira']
    if not _trava_chat.acquire(blocking=False):
        raise Erro(429, 'Aguarde a resposta anterior terminar.')
    try:
        return CH.responder(dados, detalhes, pergunta, historico, carteira, bot=bot, pasta=pasta)
    except CH.ErroChat as e:
        raise Erro(502, str(e))
    finally:
        _trava_chat.release()


# ---------- agenda ----------

ID_RE = re.compile(r'^[0-9a-f]{8}$')


def agenda_interpretar(corpo):
    """Texto -> proposta de agendamento (nada é gravado aqui). Sem pedido de agendamento: {'agendamento': False}."""
    texto = corpo.get('texto') if isinstance(corpo, dict) else None
    if not isinstance(texto, str) or not texto.strip() or len(texto) > CH.MAX_PERGUNTA:
        raise Erro(400, 'Texto inválido.')
    bot = corpo.get('bot', 'analista')
    try:
        p = AG.interpretar(texto, bot_atual=bot if isinstance(bot, str) else 'analista')
    except AG.PedidoInvalido as e:
        return {'agendamento': True, 'entendido': False, 'motivo': str(e)}
    if p is None:
        return {'agendamento': False}
    return {'agendamento': True, 'entendido': True, 'proposta': p}


def agenda_criar(corpo):
    if not isinstance(corpo, dict):
        raise Erro(400, 'Corpo inválido.')
    try:
        return AG.criar(corpo.get('bot'), corpo.get('pergunta'), corpo.get('quando'))
    except AG.PedidoInvalido as e:
        raise Erro(400, str(e))


def _executar_agendada(tarefa):
    """Roda a pergunta agendada no bot, como o chat faz. Chat ocupado: tenta no próximo ciclo."""
    pasta = pasta_semana()
    if not pasta:
        raise RuntimeError('Nenhuma semana com sintese.json encontrada.')
    try:
        return chat_responder(pasta, {'pergunta': tarefa['pergunta'], 'bot': tarefa['bot']})
    except Erro as e:
        if e.codigo == 429:
            raise AG.Ocupado()
        raise RuntimeError(e.msg)


# ---------- HTTP ----------

class Erro(Exception):
    def __init__(self, codigo, msg):
        super().__init__(msg)
        self.codigo, self.msg = codigo, msg


def rota_api(metodo, caminho, consulta, corpo):
    """Roteia a API. Devolve (código, objeto)."""
    nome = (consulta.get('semana') or [None])[0]
    pasta = pasta_semana(nome)
    partes = [p for p in caminho.split('/') if p][1:]  # sem 'api'
    if metodo == 'GET':
        if partes == ['semana']:
            if not pasta:
                raise Erro(404, 'Nenhuma semana com sintese.json encontrada.')
            return 200, semana(pasta)
        if len(partes) == 2 and partes[0] in ('dossie', 'objecoes'):
            tk = partes[1].upper()
            if not TICKER_RE.match(tk):
                raise Erro(400, 'Ticker inválido.')
            if not pasta:
                raise Erro(404, 'Nenhuma semana com sintese.json encontrada.')
            r = (dossie if partes[0] == 'dossie' else objecoes)(pasta, tk)
            if r is None:
                raise Erro(404, f'{tk} não está no ranking desta semana.')
            return 200, r
        if partes == ['desempenho']:
            return 200, desempenho()
        if partes == ['rotina']:
            return 200, rotina()
        if partes == ['minha-carteira']:
            return 200, minha_carteira_ler(pasta)
        if partes == ['plano']:
            return 200, plano_ler()
        if partes == ['chat', 'status']:
            return 200, chat_status(pasta)
        if partes == ['agenda']:
            return 200, {'tarefas': AG.listar(), 'agora': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    if metodo == 'POST':
        if partes == ['agenda', 'interpretar']:
            return 200, agenda_interpretar(corpo)
        if partes == ['agenda']:
            return 200, agenda_criar(corpo)
        if len(partes) == 3 and partes[0] == 'agenda' and partes[2] == 'vista' and ID_RE.match(partes[1]):
            return (200, {'ok': True}) if AG.marcar_vista(partes[1]) else (404, {'erro': 'Tarefa não encontrada.'})
        if partes == ['chat']:
            if not pasta:
                raise Erro(404, 'Nenhuma semana com sintese.json encontrada.')
            return 200, chat_responder(pasta, corpo)
        if partes == ['minha-carteira']:
            if not pasta:
                raise Erro(404, 'Nenhuma semana com sintese.json encontrada.')
            texto = corpo.get('csv') if isinstance(corpo, dict) else None
            if not isinstance(texto, str) or not texto.strip():
                raise Erro(400, 'Envie o conteúdo do CSV em "csv".')
            try:
                return 200, minha_carteira_importar(pasta, texto)
            except ValueError as e:
                raise Erro(400, str(e))
        if partes == ['rotina', 'iniciar']:
            if not (isinstance(corpo, dict) and corpo.get('confirmar') is True):
                raise Erro(400, 'Confirmação explícita necessária ("confirmar": true).')
            ok, msg = iniciar_rotina()
            return (200 if ok else 409), {'ok': ok, 'mensagem': msg}
    if metodo == 'PUT' and partes == ['plano']:
        try:
            PL.salvar_plano(corpo)
        except ValueError as e:
            raise Erro(400, str(e))
        return 200, plano_ler()
    if metodo == 'DELETE':
        if len(partes) == 2 and partes[0] == 'agenda' and ID_RE.match(partes[1]):
            if AG.cancelar(partes[1]):
                return 200, {'ok': True}
            raise Erro(404, 'Tarefa não encontrada ou já executada.')
        if partes == ['plano']:
            PL.apagar_plano()
            return 200, plano_ler()
        if partes == ['minha-carteira']:
            with _trava:
                MEMORIA['carteira'] = None
            return 200, {'vazio': True}
    raise Erro(404, 'Rota não encontrada.')


CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


class Handler(BaseHTTPRequestHandler):
    server_version = 'AdvogadoDoDiabo'

    def log_message(self, fmt, *args):  # silencioso: evita registrar caminhos com dados pessoais
        pass

    def _hosts_ok(self):
        host = (self.headers.get('Host') or '').lower()
        porta = self.server.server_address[1]
        permitidos = {f'127.0.0.1:{porta}', f'localhost:{porta}'}
        permitidos |= {f'{h}:{porta}' for h in getattr(self.server, 'hosts_extra', ())}
        return host in permitidos

    def _autorizado(self, url):
        """Sem token configurado, tudo liberado. Com token: cookie válido, ou ?k= válido (vira cookie).
        Devolve True, False ou ('redirecionar', caminho)."""
        token = getattr(self.server, 'token', None)
        if not token:
            return True
        c = SimpleCookie(self.headers.get('Cookie') or '')
        if 'adv_k' in c and secrets.compare_digest(c['adv_k'].value, token):
            return True
        k = (parse_qs(url.query).get('k') or [''])[0]
        if k and secrets.compare_digest(k, token) and self.command in ('GET', 'HEAD'):
            return ('redirecionar', url.path or '/')
        return False

    def _enviar(self, codigo, corpo, tipo):
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(corpo)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', CSP)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(corpo)

    def _json(self, codigo, obj):
        self._enviar(codigo, json.dumps(obj, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

    def _estatico(self, caminho):
        rel = unquote(caminho).lstrip('/') or 'index.html'
        alvo = os.path.realpath(os.path.join(APP, rel))
        if not alvo.startswith(os.path.realpath(APP) + os.sep) or not os.path.isfile(alvo):
            return self._json(404, {'erro': 'Não encontrado.'})
        tipo = mimetypes.guess_type(alvo)[0] or 'application/octet-stream'
        if tipo.startswith('text/') or tipo in ('application/javascript', 'application/json'):
            tipo += '; charset=utf-8'
        with open(alvo, 'rb') as f:
            self._enviar(200, f.read(), tipo)

    def _tratar(self):
        if not self._hosts_ok():
            return self._json(403, {'erro': 'Host não permitido.'})
        url = urlparse(self.path)
        aut = self._autorizado(url)
        if aut is not True:
            if aut:
                self.send_response(302)
                self.send_header('Location', aut[1])
                self.send_header('Set-Cookie', f'adv_k={self.server.token}; Path=/; HttpOnly; SameSite=Strict')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            return self._json(401, {'erro': 'Acesso negado: abra a URL com o token impressa no terminal.'})
        if not url.path.startswith('/api/'):
            if self.command not in ('GET', 'HEAD'):
                return self._json(405, {'erro': 'Método não permitido.'})
            return self._estatico(url.path)
        corpo = None
        if self.command != 'GET':
            if self.headers.get('X-Adv') != '1':
                return self._json(403, {'erro': 'Cabeçalho X-Adv ausente.'})
            origem = self.headers.get('Origin')
            if origem and origem not in (f'http://{self.headers.get("Host")}',):
                return self._json(403, {'erro': 'Origem não permitida.'})
            try:
                n = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                n = -1
            if n < 0 or n > MAX_CORPO:
                return self._json(413, {'erro': 'Corpo grande demais.'})
            bruto = self.rfile.read(n) if n else b''
            try:
                corpo = json.loads(bruto.decode('utf-8')) if bruto else {}
            except ValueError:
                return self._json(400, {'erro': 'JSON inválido.'})
        try:
            codigo, obj = rota_api(self.command, url.path, parse_qs(url.query), corpo)
        except Erro as e:
            return self._json(e.codigo, {'erro': e.msg})
        self._json(codigo, obj)

    do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = _tratar


class Servidor(ThreadingHTTPServer):
    request_queue_size = 128   # o padrão (5) derruba o navegador quando ele abre vários módulos em paralelo
    daemon_threads = True
    hosts_extra = ()
    token = None


def ips_locais():
    """Endereços da máquina na rede local (sem 127.x)."""
    achados = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(('10.255.255.255', 1))   # não envia nada; só descobre a interface de saída
            achados.add(sk.getsockname()[0])
    except OSError:
        pass
    try:
        achados.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return sorted(ip for ip in achados if not ip.startswith('127.'))


def criar_servidor(porta=8765, celular=False):
    """celular=True escuta na rede local, exige token e aceita o IP e o nome da máquina como Host."""
    srv = Servidor(('0.0.0.0' if celular else '127.0.0.1', porta), Handler)
    if celular:
        srv.token = secrets.token_urlsafe(16)
        nome = socket.gethostname().lower()
        srv.hosts_extra = tuple(ips_locais()) + ((nome,) if nome else ())
    return srv


def main():
    ap = argparse.ArgumentParser(description='Interface local do Advogado do Diabo')
    ap.add_argument('--porta', type=int, default=8765)
    ap.add_argument('--celular', action='store_true',
                    help='abre para a rede local (Wi-Fi) com token, para testar no celular')
    ap.add_argument('--raiz', default=None, help='pasta com semana_*/, avaliacao.json e historico (padrão: o projeto)')
    a = ap.parse_args()
    if a.raiz:
        global RAIZ
        RAIZ = os.path.abspath(a.raiz)
    srv = criar_servidor(a.porta, celular=a.celular)
    porta = srv.server_address[1]
    if a.celular:
        print('Modo celular: acessível na rede local, só com o token abaixo. HTTP sem criptografia: use em rede de confiança.')
        for h in srv.hosts_extra:
            if re.match(r'^\d+\.\d+\.\d+\.\d+$', h):
                print(f'  No celular (mesmo Wi-Fi): http://{h}:{porta}/?k={srv.token}')
        print(f'  Neste computador:         http://127.0.0.1:{porta}/?k={srv.token}  (Ctrl+C para sair)', flush=True)
    else:
        print(f'Interface em http://127.0.0.1:{porta}/  (Ctrl+C para sair)', flush=True)
    agendador = AG.Agendador(_executar_agendada)
    agendador.start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        agendador.parar.set()
        srv.server_close()


if __name__ == '__main__':
    main()
