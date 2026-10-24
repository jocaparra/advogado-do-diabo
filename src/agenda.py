"""Mensagens agendadas do chat: "me manda o resumo do Risco segunda às 16".

O pedido é entendido em código (sem chamar o Claude): dia e hora em português viram uma data exata, que a
tela mostra para você confirmar. Só depois da confirmação a tarefa é gravada. No horário, o servidor roda a
pergunta no bot escolhido e avisa pela notificação do macOS; a resposta também fica no chat.

Limites assumidos: uma vez só (sem recorrência), até 60 dias à frente, no máximo 10 tarefas ativas. O Mac e o
servidor precisam estar ligados; tarefa vencida há mais de 12 horas é marcada como perdida em vez de rodar tarde.

A agenda fica em ~/.config/advogado-do-diabo/agenda.json (só o seu usuário lê; fora de qualquer repositório).
Não guarda carteira nem posições.
"""
import datetime as dt
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import unicodedata

import bots as BT
import plano as PL

MAX_ATIVAS = 10
MAX_DIAS = 60
ATRASO_MAX = dt.timedelta(hours=12)
MAX_PERGUNTA = 1000
MAX_HISTORICO = 50
MAX_TENTATIVAS = 5
PERGUNTA_PADRAO = 'Resumo da semana'
DIAS = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo']
_trava = threading.Lock()


def caminho():
    """ADVOGADO_DO_DIABO_AGENDA troca o caminho (testes)."""
    return os.environ.get('ADVOGADO_DO_DIABO_AGENDA') or os.path.join(
        os.path.expanduser('~'), '.config', 'advogado-do-diabo', 'agenda.json')


# ---------- entender o pedido ----------

def _sem_acento(s):
    """Minúsculas e sem acento, mantendo o mesmo comprimento (os trechos achados valem para o texto original)."""
    saida = []
    for ch in s:
        base = ''.join(c for c in unicodedata.normalize('NFD', ch) if not unicodedata.combining(c))
        saida.append(base.lower() if len(base) == 1 else ch.lower())
    return ''.join(saida)


_SEMANA = r'(segunda|terca|quarta|quinta|sexta|sabado|domingo)(?:[- ]feira)?'
RE_GATILHO = re.compile(r'\b(?:me\s+)?(mande|manda|mandar|envie|envia|enviar|avise|avisa|avisar|lembre|lembra|lembrar|'
                        r'notifique|notifica|notificar|agende|agendar|programe|programar|retorne|responda)\b')
RE_RECORRENTE = re.compile(r'\b(?:toda|todo|todos\s+os|todas\s+as|cada)\s+(?:dia|semana|mes|manha|tarde|noite|segunda|terca|quarta|'
                           r'quinta|sexta|sabado|domingo)|\b(?:diariamente|semanalmente|mensalmente)\b')
RE_REL = re.compile(r'\b(?:daqui\s+a|em)\s+(\d{1,3})\s*(minutos?|min|horas?|h)\b')
RE_REL_DIAS = re.compile(r'\b(?:daqui\s+a|em)\s+(\d{1,3})\s*(dias?|semanas?)\b')
RE_PRAZO_VAGO = re.compile(r'\b(?:daqui\s+a|em)\s+(?:\d{1,3}|uma?|duas?)\s*(?:mes(?:es)?|anos?)\b|\b(?:semana|mes|ano)\s+que\s+vem\b|'
                           r'\bproxim[ao]\s+(?:semana|mes|ano)\b|\bfim\s+(?:de\s+semana|do\s+mes|da\s+semana)\b|\bfinal\s+(?:de\s+semana|do\s+mes)\b')
RE_DEPOIS_AMANHA = re.compile(r'\bdepois\s+de\s+amanha\b')
RE_AMANHA = re.compile(r'\bamanha\b')
RE_HOJE = re.compile(r'\bhoje\b')
RE_DIA_SEMANA = re.compile(r'\b(?:(proxim[ao])\s+)?' + _SEMANA + r'\b')
RE_DATA = re.compile(r'\b(?:(?:no\s+)?dia\s+)?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b')
RE_DIA_N = re.compile(r'\b(?:no\s+)?dia\s+(\d{1,2})\b(?!\s*/)')
RE_HORA_MIN = re.compile(r'\b(?:as\s+)?(\d{1,2})\s*(?::|h|hs)\s*(\d{2})\b')
RE_HORA_H = re.compile(r'\b(?:as\s+)?(\d{1,2})\s*(?:h|hs|horas?)\b')
RE_HORA_AS = re.compile(r'\bas\s+(\d{1,2})\b(?!\s*[/:])')
RE_MEIO_DIA = re.compile(r'\bmeio[- ]dia\b')
RE_MEIA_NOITE = re.compile(r'\bmeia[- ]noite\b')
RE_PERIODO = re.compile(r'\s*(?:da|de)\s+(manha|tarde|noite|madrugada)\b')
_NOMES_BOT = {'analista': 'analista', 'advogado': 'advogado', 'auditor': 'auditor', 'fundamentos': 'fundamentos',
              'fundamentalista': 'fundamentos', 'casas': 'casas', 'noticias': 'noticias', 'noticia': 'noticias',
              'fluxo': 'fluxo', 'macro': 'macro', 'risco': 'risco', 'monitor': 'monitor', 'alertas': 'monitor'}


class PedidoInvalido(ValueError):
    """Pedido de agendamento que não dá para atender; a mensagem vai para o usuário."""


def texto_quando(q):
    return f"{DIAS[q.weekday()]}, {q:%d/%m} às {q:%H:%M}"


def _hora(t, orig, spans):
    """Procura a hora no texto normalizado. Devolve (hora, minuto) ou None; registra os trechos usados."""
    m = RE_MEIO_DIA.search(t)
    if m:
        spans.append(m.span())
        return 12, 0
    m = RE_MEIA_NOITE.search(t)
    if m:
        spans.append(m.span())
        return 0, 0
    for rx, tem_min in ((RE_HORA_MIN, True), (RE_HORA_H, False), (RE_HORA_AS, False)):
        for m in rx.finditer(t):
            if any(a <= m.start() < b for a, b in spans):      # parte de uma data, ex. 25/10
                continue
            if rx is RE_HORA_AS:
                # "às 16" é hora; "as 5 casas" é artigo. Aceita com acento, ou sem nada de palavra depois do número.
                resto = t[m.end():].lstrip()
                seguinte = resto.split()[0] if resto else ''
                if not (orig[m.start():m.start() + 2].lower() == 'às' or not seguinte or not seguinte[0].isalpha() or seguinte == 'da'):
                    continue
            h = int(m.group(1))
            mi = int(m.group(2)) if tem_min else 0
            fim = m.end()
            p = RE_PERIODO.match(t, fim)
            periodo = None
            if p:
                periodo, fim = p.group(1), p.end()
            if mi > 59 or h > 23 or (periodo in ('tarde', 'noite') and h > 12) or (periodo == 'manha' and h > 12):
                raise PedidoInvalido(f'Não entendi o horário "{m.group(0).strip()}".')
            if periodo in ('tarde', 'noite') and h < 12:
                h += 12
            if periodo == 'manha' and h == 12:
                h = 0
            spans.append((m.start(), fim))
            return h, mi
    return None


def interpretar(texto, agora=None, bot_atual='analista'):
    """Texto do usuário -> proposta de agendamento.

    Devolve None se a mensagem não é um pedido de agendamento (vai para o chat normal). Levanta PedidoInvalido
    com a explicação quando é um pedido mas não dá para atender. A proposta traz bot, pergunta e `quando`.
    """
    agora = (agora or dt.datetime.now().astimezone()).replace(second=0, microsecond=0)
    t = _sem_acento(texto or '')
    gatilho = RE_GATILHO.search(t)
    spans = []
    achou_tempo = False
    rel = RE_REL.search(t)
    dia_m = dia_rx = None
    for rx in (RE_DEPOIS_AMANHA, RE_AMANHA, RE_HOJE, RE_DIA_SEMANA, RE_DATA, RE_DIA_N):
        dia_m = rx.search(t)
        if dia_m:
            dia_rx = rx
            break
    if dia_m:
        spans.append(dia_m.span())
    hora = None
    if not rel:
        hora = _hora(t, texto, spans)
    reld = RE_REL_DIAS.search(t)
    achou_tempo = bool(rel or reld or dia_m or hora or RE_PRAZO_VAGO.search(t))
    if not (gatilho and achou_tempo):
        return None
    if not rel and not reld and hora is None and dia_rx is RE_HOJE and not RE_PRAZO_VAGO.search(t):
        return None   # "me manda o alerta de hoje": pedido imediato, não agendamento
    if RE_PRAZO_VAGO.search(t):
        raise PedidoInvalido('Não agendo por "mês", "ano" ou "semana que vem". Diga o dia, por exemplo "sexta às 16" ou "dia 30/10 às 9".')
    if RE_RECORRENTE.search(t):
        raise PedidoInvalido('Por enquanto só agendo uma vez. Peça de novo a cada vez que quiser.')

    if reld and not rel:
        if hora is None:
            raise PedidoInvalido('Faltou o horário. Diga, por exemplo, "em 3 dias às 9h".')
        n = int(reld.group(1)) * (7 if reld.group(2).startswith('semana') else 1)
        if n <= 0:
            raise PedidoInvalido('Informe um prazo maior que zero.')
        quando = dt.datetime.combine(agora.date() + dt.timedelta(days=n), dt.time(*hora)).astimezone()
        spans.append(reld.span())
    elif rel:
        n, un = int(rel.group(1)), rel.group(2)
        delta = dt.timedelta(minutes=n) if un.startswith('min') else dt.timedelta(hours=n)
        if n <= 0:
            raise PedidoInvalido('Informe um prazo maior que zero.')
        quando = agora + delta
        spans.append(rel.span())
    else:
        if hora is None:
            raise PedidoInvalido('Faltou o horário. Diga, por exemplo, "segunda às 16" ou "amanhã às 9h30".')
        h, mi = hora
        hoje = agora.date()
        if dia_m is None:
            dia = hoje if agora.replace(hour=h, minute=mi) > agora else hoje + dt.timedelta(days=1)
        elif dia_rx is RE_DEPOIS_AMANHA:
            dia = hoje + dt.timedelta(days=2)
        elif dia_rx is RE_AMANHA:
            dia = hoje + dt.timedelta(days=1)
        elif dia_rx is RE_HOJE:
            dia = hoje
        elif dia_rx is RE_DIA_SEMANA:
            alvo = ['segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo'].index(dia_m.group(2))
            delta = (alvo - hoje.weekday()) % 7
            if delta == 0 and (dia_m.group(1) or agora.replace(hour=h, minute=mi) <= agora):
                delta = 7
            dia = hoje + dt.timedelta(days=delta)
        else:
            try:
                if dia_rx is RE_DATA:
                    d, m_, a = int(dia_m.group(1)), int(dia_m.group(2)), dia_m.group(3)
                    ano = hoje.year if a is None else (int(a) + 2000 if len(a) == 2 else int(a))
                    dia = dt.date(ano, m_, d)
                    if dia < hoje:
                        raise PedidoInvalido(f'{d:02d}/{m_:02d} já passou. Se for no futuro, informe o ano.')
                else:
                    d = int(dia_m.group(1))
                    ano, mes = hoje.year, hoje.month
                    for _ in range(2):
                        try:
                            dia = dt.date(ano, mes, d)
                        except ValueError:
                            dia = None
                        if dia and (dia > hoje or (dia == hoje and agora.replace(hour=h, minute=mi) > agora)):
                            break
                        mes, ano = (1, ano + 1) if mes == 12 else (mes + 1, ano)
                        dia = None
                    if dia is None:
                        raise ValueError
            except PedidoInvalido:
                raise
            except ValueError:
                raise PedidoInvalido('Essa data não existe. Confira o dia e o mês.')
        quando = dt.datetime.combine(dia, dt.time(h, mi)).astimezone()
    if quando <= agora:
        raise PedidoInvalido(f'{texto_quando(quando)} já passou. Escolha um horário no futuro.')
    if quando > agora + dt.timedelta(days=MAX_DIAS):
        raise PedidoInvalido(f'Só agendo até {MAX_DIAS} dias à frente.')

    bot = bot_atual if bot_atual in BT.BOTS else 'analista'
    for palavra in re.findall(r'[a-z]+', t):
        if palavra in _NOMES_BOT:
            bot = _NOMES_BOT[palavra]
            break
    # pergunta = o pedido sem o gatilho e sem a expressão de tempo
    spans.append(gatilho.span())
    spans.extend(m.span() for m in re.finditer(r'\b(?:de|da|a)\s+(?:manha|tarde|noite|madrugada)\b', t))
    resto = list(texto)
    for a, b in spans:
        for i in range(a, min(b, len(resto))):
            resto[i] = ' '
    pergunta = re.sub(r'\s+', ' ', ''.join(resto)).strip(' ,.;:-')
    palavras = pergunta.split(' ') if pergunta else []
    sobras_ini = {'me', 'que', 'para', 'pra', 'favor', 'por', 'e', 'o', 'a'}
    sobras_fim = {'as', 'às', 'para', 'pra', 'em', 'no', 'na', 'de', 'do', 'da', 'a', 'o', 'e', 'me', 'daqui', 'proxima', 'próxima', 'proximo', 'próximo'}
    while palavras and _sem_acento(palavras[0]) in sobras_ini and len(palavras) > 1:
        palavras.pop(0)
    while palavras and _sem_acento(palavras[-1]) in {_sem_acento(x) for x in sobras_fim}:
        palavras.pop()
    pergunta = ' '.join(palavras).strip(' ,.;:-')
    if len(pergunta) < 3 or _sem_acento(pergunta) in _NOMES_BOT or _sem_acento(pergunta) in ('o', 'a', 'me'):
        pergunta = PERGUNTA_PADRAO
    pergunta = pergunta[:MAX_PERGUNTA]
    pergunta = pergunta[0].upper() + pergunta[1:]
    return {'bot': bot, 'pergunta': pergunta, 'quando': quando.isoformat(), 'quando_texto': texto_quando(quando),
            'nome_bot': BT.BOTS[bot]['nome']}


# ---------- guardar ----------

def carregar():
    try:
        with open(caminho(), encoding='utf-8') as f:
            d = json.load(f)
        return [t for t in d.get('tarefas', []) if isinstance(t, dict) and t.get('id')]
    except (OSError, ValueError, AttributeError):
        return []


def _salvar(tarefas):
    ativas = [t for t in tarefas if t.get('estado') == 'agendada']
    outras = [t for t in tarefas if t.get('estado') != 'agendada'][-MAX_HISTORICO:]
    PL.gravar_privado(caminho(), {'tarefas': ativas + outras})


def listar():
    with _trava:
        return sorted(carregar(), key=lambda t: t.get('quando', ''))


def criar(bot, pergunta, quando_iso, agora=None):
    """Grava uma tarefa já confirmada. Valida tudo de novo: o que chega da tela não é confiável."""
    agora = agora or dt.datetime.now().astimezone()
    if not isinstance(bot, str) or bot not in BT.BOTS:
        raise PedidoInvalido('Bot desconhecido.')
    if not isinstance(pergunta, str) or not pergunta.strip():
        raise PedidoInvalido('A pergunta está vazia.')
    if len(pergunta) > MAX_PERGUNTA:
        raise PedidoInvalido(f'A pergunta passou de {MAX_PERGUNTA} caracteres.')
    try:
        quando = dt.datetime.fromisoformat(quando_iso)
    except (TypeError, ValueError):
        raise PedidoInvalido('Data inválida.')
    if quando.tzinfo is None:
        quando = quando.astimezone()
    if quando <= agora:
        raise PedidoInvalido('Esse horário já passou.')
    if quando > agora + dt.timedelta(days=MAX_DIAS):
        raise PedidoInvalido(f'Só agendo até {MAX_DIAS} dias à frente.')
    with _trava:
        tarefas = carregar()
        if sum(1 for t in tarefas if t.get('estado') == 'agendada') >= MAX_ATIVAS:
            raise PedidoInvalido(f'Já existem {MAX_ATIVAS} mensagens agendadas. Cancele alguma antes.')
        t = {'id': secrets.token_hex(4), 'bot': bot, 'pergunta': pergunta.strip(), 'quando': quando.isoformat(),
             'quando_texto': texto_quando(quando), 'criada_em': agora.isoformat(), 'estado': 'agendada', 'tentativas': 0}
        tarefas.append(t)
        _salvar(tarefas)
    return t


def cancelar(id_):
    with _trava:
        tarefas = carregar()
        for t in tarefas:
            if t['id'] == id_ and t.get('estado') == 'agendada':
                t['estado'] = 'cancelada'
                _salvar(tarefas)
                return True
    return False


def marcar_vista(id_):
    with _trava:
        tarefas = carregar()
        for t in tarefas:
            if t['id'] == id_:
                t['vista'] = True
                _salvar(tarefas)
                return True
    return False


# ---------- executar ----------

class Ocupado(Exception):
    """O chat está respondendo outra pergunta; tenta de novo no próximo ciclo."""


def notificar_mac(titulo, texto):
    """Notificação do macOS. Título e texto vão como argumentos do osascript, nunca dentro do script: a resposta
    vem de arquivos com texto da web e não pode virar comando AppleScript."""
    if sys.platform != 'darwin' or os.environ.get('ADV_SEM_NOTIFICAR'):
        return False
    limpo = lambda s, n: re.sub(r'[\x00-\x1f]+', ' ', str(s or '')).strip()[:n]
    try:
        r = subprocess.run(['osascript', '-e', 'on run argv', '-e', 'display notification (item 1 of argv) with title (item 2 of argv)',
                            '-e', 'end run', limpo(texto, 220), limpo(titulo, 80)], check=False, timeout=10,
                           capture_output=True)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def executar_vencidas(agora, executar, notificar=notificar_mac):
    """Roda as tarefas cujo horário chegou. `executar(tarefa)` devolve o resultado do chat ou levanta Ocupado."""
    feitas = []
    with _trava:
        tarefas = carregar()
    for t in tarefas:
        if t.get('estado') != 'agendada':
            continue
        quando = dt.datetime.fromisoformat(t['quando'])
        if quando > agora:
            continue
        nome = BT.BOTS.get(t['bot'], {}).get('nome', t['bot'])
        if agora - quando > ATRASO_MAX:
            t['estado'] = 'perdida'
            t['erro'] = 'O computador ou o servidor estava desligado no horário e o prazo de 12 horas passou.'
            feitas.append(t)
            continue
        try:
            r = executar(t)
        except Ocupado:
            t['tentativas'] = t.get('tentativas', 0) + 1
            if t['tentativas'] >= MAX_TENTATIVAS:
                t['estado'], t['erro'] = 'falhou', 'O chat ficou ocupado por tempo demais.'
                feitas.append(t)
            continue
        except Exception as e:   # noqa: BLE001 - qualquer falha vira estado "falhou", nunca derruba o agendador
            t['estado'], t['erro'] = 'falhou', str(e)[:300] or 'Falha ao responder.'
            t['executada_em'] = agora.isoformat()
            notificar(f'Advogado do Diabo · {nome}', f'Não consegui responder: {t["pergunta"]}')
            feitas.append(t)
            continue
        atrasada = agora - quando > dt.timedelta(minutes=2)
        t.update(estado='executada', executada_em=agora.isoformat(), atrasada=atrasada,
                 resultado={k: r.get(k) for k in ('resposta', 'fontes', 'nao_verificado', 'formato_ok')})
        notificar(f'Advogado do Diabo · {nome}' + (' (atrasada)' if atrasada else ''), r.get('resposta') or t['pergunta'])
        feitas.append(t)
    if feitas or any(t.get('tentativas') for t in tarefas):
        with _trava:
            atuais = {t['id']: t for t in carregar()}
            for t in tarefas:
                if t['id'] in atuais and atuais[t['id']].get('estado') == 'agendada':   # não desfaz um cancelamento feito no meio
                    atuais[t['id']] = t
            _salvar(list(atuais.values()))
    return feitas


class Agendador(threading.Thread):
    """Verifica a agenda a cada `intervalo` segundos enquanto o servidor estiver rodando."""

    def __init__(self, executar, intervalo=20):
        super().__init__(daemon=True)
        self.executar, self.intervalo, self.parar = executar, intervalo, threading.Event()

    def run(self):
        while not self.parar.is_set():
            try:
                executar_vencidas(dt.datetime.now().astimezone(), self.executar)
            except Exception:   # noqa: BLE001 - o agendador nunca morre por causa de uma tarefa
                pass
            self.parar.wait(self.intervalo)
