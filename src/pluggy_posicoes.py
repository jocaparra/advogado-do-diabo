"""Baixa suas posições de renda variável pela API da Pluggy (conector MeuPluggy) e grava um CSV.

uso: python src/pluggy_posicoes.py [saida.csv]        (padrão: entrada/posicoes_pluggy.csv)
     python src/minha_carteira.py --pluggy-json resposta.json   (usa um JSON já salvo, sem credenciais)

Variáveis de ambiente (nunca coloque no código nem no git):
    PLUGGY_CLIENT_ID       credencial da sua aplicação em dashboard.pluggy.ai
    PLUGGY_CLIENT_SECRET   idem
    PLUGGY_ITEM_IDS        itemId(s) das suas conexões, separados por vírgula

O CSV gerado entra direto em:  python src/minha_carteira.py <pasta_da_semana> <saida.csv>

Só stdlib. A chave de API da Pluggy vale poucas horas e é pedida a cada execução. Somente leitura:
nenhuma chamada move dinheiro nem altera conexões.
"""
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.pluggy.ai'


class PluggyErro(Exception):
    """Falha ao falar com a Pluggy; a mensagem é segura para mostrar ao usuário."""


TIPOS_ACAO = {'EQUITY', 'ETF'}
TICKER = re.compile(r'[A-Z]{4}\d{1,2}F?')


def _chamar(metodo, caminho, chave=None, corpo=None, consulta=None):
    url = API + caminho + ('?' + urllib.parse.urlencode(consulta) if consulta else '')
    cab = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if chave:
        cab['X-API-KEY'] = chave
    req = urllib.request.Request(url, method=metodo, headers=cab,
                                 data=json.dumps(corpo).encode() if corpo is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # o corpo da resposta da Pluggy não contém credenciais; é seguro mostrar o status e a mensagem
        raise PluggyErro(f'Pluggy respondeu {e.code} em {caminho}: {e.read().decode(errors="replace")[:300]}')
    except (urllib.error.URLError, OSError) as e:      # inclui timeout
        raise PluggyErro(f'sem conexão com a Pluggy: {getattr(e, "reason", e)}')
    except ValueError:
        raise PluggyErro(f'resposta inesperada da Pluggy em {caminho}')


def autenticar(client_id, client_secret):
    r = _chamar('POST', '/auth', corpo={'clientId': client_id, 'clientSecret': client_secret})
    chave = r.get('apiKey') if isinstance(r, dict) else None
    if not chave:
        raise PluggyErro('a Pluggy não devolveu a chave de acesso; confira Client ID e Client Secret')
    return chave


def investimentos(chave, item_id):
    """Todas as páginas de /investments de um item."""
    pagina, saida = 1, []
    while True:
        r = _chamar('GET', '/investments', chave, consulta={'itemId': item_id, 'page': pagina, 'pageSize': 500})
        if not isinstance(r, dict):
            raise PluggyErro('resposta inesperada da Pluggy em /investments')
        saida += [i for i in (r.get('results') or []) if isinstance(i, dict)]
        total = r.get('totalPages')
        if pagina >= (total if isinstance(total, int) else 1):
            return saida
        pagina += 1


def _numero(x):
    """float finito (aceita texto com vírgula ou ponto) ou None."""
    try:
        v = float(x.replace(',', '.')) if isinstance(x, str) else float(x)
    except (TypeError, ValueError, AttributeError):
        return None
    return v if math.isfinite(v) else None


def preco_medio_transacoes(trans, quantidade_atual):
    """Preço médio móvel a partir das compras e vendas (`/investments/{id}/transactions`), ou None.

    Compra soma quantidade e custo (valor unitário x quantidade + despesas); venda tira custo na proporção
    do preço médio. Só devolve número se o histórico fecha com a posição atual: venda maior que o saldo,
    tipo desconhecido, valor inválido ou quantidade final diferente da posição deixam o preço médio vazio.
    """
    qtd, custo = 0.0, 0.0
    for t in sorted((x for x in trans if isinstance(x, dict)), key=lambda x: str(x.get('tradeDate') or x.get('date') or '')):
        q, v = _numero(t.get('quantity')), _numero(t.get('value'))
        if q is None or q <= 0:
            return None
        if t.get('type') == 'BUY':
            if v is None or v <= 0:
                return None
            qtd += q
            custo += q * v + (_numero(t.get('expenses')) or 0)
        elif t.get('type') == 'SELL':
            if q > qtd + 1e-9:
                return None
            custo -= custo * q / qtd
            qtd -= q
        else:
            return None
    if qtd <= 0 or abs(qtd - quantidade_atual) > 1e-6:
        return None
    return round(custo / qtd, 4)


def extrair_acoes(invs, transacoes=None):
    """Filtra ações/ETFs com código de ticker e soma por ticker. Devolve (posicoes, ignorados).

    O campo `code` da Pluggy traz o ticker nas posições de bolsa; o que não parecer ticker
    (renda fixa, fundos, COE) vai para `ignorados` com o motivo, para você ver o que ficou de fora.

    `transacoes` (opcional) mapeia o `id` de cada investimento para a lista das suas transações; quando
    cobrem todos os lotes do ticker e fecham com a quantidade, o preço médio sai delas (tem prioridade
    sobre `amountOriginal`).
    """
    transacoes = transacoes or {}
    por_tk, valor_tk, custo_tk, trans_tk, ignorados = {}, {}, {}, {}, []
    for i in invs:
        if not isinstance(i, dict):
            continue
        tipo, nome = i.get('type'), i.get('name') or i.get('code') or '?'
        codigo = str(i.get('code') or '').strip().upper()
        if tipo not in TIPOS_ACAO:
            ignorados.append(f'{nome} ({tipo or "tipo n/d"})')
        elif not TICKER.fullmatch(codigo):
            ignorados.append(f'{nome} (código {codigo or "vazio"} não parece ticker)')
        elif (q := _numero(i.get('quantity'))) is None or q <= 0:
            ignorados.append(f'{codigo} (sem quantidade)')
        else:
            tk = codigo[:-1] if codigo.endswith('F') else codigo
            por_tk[tk] = por_tk.get(tk, 0) + q
            valor_tk[tk] = valor_tk.get(tk, 0) + q * (_numero(i.get('value')) or 0)
            # `amountOriginal` = valor aplicado (custo). Sem ele (ou zerado) o preço médio fica vazio:
            # não se deduz custo de outro campo. Se um dos lotes não tiver custo, o ticker inteiro fica sem.
            c = _numero(i.get('amountOriginal'))
            c = c if c is not None and c > 0 else None
            antes = custo_tk.get(tk, 0.0)
            custo_tk[tk] = None if (antes is None or c is None) else antes + c
            lista = transacoes.get(i.get('id'))
            antes_t = trans_tk.get(tk, [])
            trans_tk[tk] = None if (antes_t is None or lista is None) else antes_t + lista
    saida = []
    for t, q in sorted(por_tk.items()):
        item = {'ticker': t, 'quantidade': q, 'preco_atual': round(valor_tk[t] / q, 4) if valor_tk[t] else None}
        pm = preco_medio_transacoes(trans_tk[t], q) if trans_tk.get(t) else None
        if pm is None and custo_tk.get(t):
            pm = round(custo_tk[t] / q, 4)
        if pm:                              # a chave só existe quando há custo (contrato anterior preservado)
            item['preco_medio'] = pm
        saida.append(item)
    return saida, ignorados


def csv_texto(posicoes):
    linhas = ['ticker;quantidade;preco_medio;preco_atual']
    for p in posicoes:
        q = f"{p['quantidade']:.6f}".rstrip('0').rstrip('.')
        pa = f"{p['preco_atual']:.4f}".replace('.', ',') if p.get('preco_atual') else ''
        pm = f"{p['preco_medio']:.4f}".replace('.', ',') if p.get('preco_medio') else ''
        linhas.append(f"{p['ticker']};{q.replace('.', ',')};{pm};{pa}")
    return '\n'.join(linhas) + '\n'


def ler_json(texto):
    """Posições a partir de um JSON de /investments já salvo (sem rede e sem credenciais).

    Aceita a resposta paginada da Pluggy (`{"results": [...]}`), uma lista de investimentos ou o JSON de
    vários itens (lista de respostas). Devolve (posicoes, ignorados) como `extrair_acoes`."""
    try:
        dado = json.loads(texto.lstrip('\ufeff'))
    except ValueError as e:
        raise PluggyErro(f'o arquivo não é um JSON válido: {e}')
    invs = []

    def coletar(x):
        if isinstance(x, list):
            for y in x:
                coletar(y)
        elif isinstance(x, dict):
            if isinstance(x.get('results'), list):
                coletar(x['results'])
            elif isinstance(x.get('investments'), list):
                coletar(x['investments'])
            elif 'type' in x or 'code' in x:
                invs.append(x)
    coletar(dado)
    if not invs:
        raise PluggyErro('não encontrei investimentos no JSON (esperado "results" ou uma lista com "type" e "code")')
    return extrair_acoes(invs)


def transacoes_investimento(chave, inv_id):
    """Todas as páginas de /investments/{id}/transactions."""
    pagina, saida = 1, []
    while True:
        r = _chamar('GET', f'/investments/{urllib.parse.quote(str(inv_id), safe="")}/transactions', chave,
                    consulta={'page': pagina, 'pageSize': 500})
        if not isinstance(r, dict):
            raise PluggyErro('resposta inesperada da Pluggy em /investments/{id}/transactions')
        saida += [t for t in (r.get('results') or []) if isinstance(t, dict)]
        total = r.get('totalPages')
        if pagina >= (total if isinstance(total, int) else 1):
            return saida
        pagina += 1


def baixar(client_id, client_secret, item_ids):
    """Autentica, lê todos os itens e devolve (posicoes, ignorados). Levanta PluggyErro.

    As transações servem só para o preço médio: se a Pluggy falhar nelas, a posição vem sem preço médio
    (ou com o `amountOriginal`, se houver) em vez de derrubar a leitura."""
    chave = autenticar(client_id, client_secret)
    todos = []
    for it in item_ids:
        todos += investimentos(chave, it)
    transacoes = {}
    for i in todos:
        q = _numero(i.get('quantity'))
        if i.get('type') in TIPOS_ACAO and i.get('id') and q is not None and q > 0:
            try:
                transacoes[i['id']] = transacoes_investimento(chave, i['id'])
            except PluggyErro:
                pass
    return extrair_acoes(todos, transacoes)


def main():
    cid, sec = os.environ.get('PLUGGY_CLIENT_ID'), os.environ.get('PLUGGY_CLIENT_SECRET')
    itens = [x.strip() for x in os.environ.get('PLUGGY_ITEM_IDS', '').split(',') if x.strip()]
    falta = [n for n, v in (('PLUGGY_CLIENT_ID', cid), ('PLUGGY_CLIENT_SECRET', sec), ('PLUGGY_ITEM_IDS', itens)) if not v]
    if falta:
        sys.exit('faltam variáveis de ambiente: ' + ', '.join(falta) + ' (veja o topo de src/pluggy_posicoes.py)')
    saida = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'entrada/posicoes_pluggy.csv')
    try:
        posicoes, ignorados = baixar(cid, sec, itens)
    except PluggyErro as e:
        sys.exit(str(e))
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    with open(saida, 'w', encoding='utf-8') as f:
        f.write(csv_texto(posicoes))
    print(f'ok: {len(posicoes)} ações/ETFs de {len(itens)} conexão(ões) -> {saida}')
    if ignorados:
        print('não incluídos (conferir se algum deveria):')
        for g in ignorados:
            print('  -', g)


if __name__ == '__main__':
    main()
