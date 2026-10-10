"""Plano do usuário: horizonte, objetivo, tolerância a queda e limites de concentração.

Guardado em ~/.config/advogado-do-diabo/plano.json (só o seu usuário lê; fora de qualquer
repositório). Usado por minha_carteira.py para reavaliar a carteira sob o seu prazo e a sua
tolerância. Só biblioteca padrão.

Os pesos por horizonte (dados/horizontes.json) são premissa do projeto, não calibração.
Nada aqui indica o que comprar, vender ou quanto aportar.
"""
import json
import math
import os

HORIZONTES = ('semanas', 'meses', 'anos')
OBJETIVOS = ('crescimento', 'renda', 'preservacao')
PADRAO = {'queda_max_pct': 15.0, 'limite_ativo_pct': 25.0, 'limite_setor_pct': 40.0}
COMPONENTES = ('catalisadores', 'noticias', 'momentum', 'macro_eleicao', 'valuation_upside')
ARQ_HORIZONTES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dados', 'horizontes.json')


def caminho_plano():
    """ADVOGADO_DO_DIABO_PLANO troca o caminho (testes)."""
    return os.environ.get('ADVOGADO_DO_DIABO_PLANO') or os.path.join(
        os.path.expanduser('~'), '.config', 'advogado-do-diabo', 'plano.json')


def gravar_privado(caminho, dados):
    """Grava JSON com permissão 0600 (só o dono lê), criando a pasta com 0700."""
    os.makedirs(os.path.dirname(caminho), mode=0o700, exist_ok=True)
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        os.fchmod(fd, 0o600)           # antes de gravar: vale também se o arquivo já existia com permissão larga
    except (AttributeError, OSError):  # Windows
        pass
    os.ftruncate(fd, 0)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        pass
    return caminho


def validar(d):
    """Normaliza e valida um plano. Levanta ValueError com a mensagem para o usuário."""
    if not isinstance(d, dict):
        raise ValueError('plano inválido')
    h, o = str(d.get('horizonte', '')).strip().lower(), str(d.get('objetivo', '')).strip().lower()
    if h not in HORIZONTES:
        raise ValueError(f'horizonte deve ser um de: {", ".join(HORIZONTES)}')
    if o not in OBJETIVOS:
        raise ValueError(f'objetivo deve ser um de: {", ".join(OBJETIVOS)}')
    saida = {'horizonte': h, 'objetivo': o}
    for k, padrao in PADRAO.items():
        v = d.get(k, padrao)
        if isinstance(v, bool):
            raise ValueError(f'{k} deve ser um número')
        try:
            v = float(str(v).replace(',', '.'))
        except (TypeError, ValueError):
            raise ValueError(f'{k} deve ser um número')
        if not 0 < v <= 100:
            raise ValueError(f'{k} deve estar entre 0 e 100')
        saida[k] = v
    return saida


def ler_plano():
    """Plano salvo, ou None se não existir ou estiver inválido."""
    try:
        with open(caminho_plano(), encoding='utf-8') as f:
            return validar(json.load(f))
    except (OSError, ValueError):
        return None


def salvar_plano(plano):
    return gravar_privado(caminho_plano(), validar(plano))


def apagar_plano():
    try:
        os.remove(caminho_plano())
        return True
    except FileNotFoundError:
        return False


def horizontes():
    with open(ARQ_HORIZONTES, encoding='utf-8') as f:
        return json.load(f)['horizontes']


def nota_no_horizonte(componentes, horizonte, nota_semanal=None):
    """Nota recalculada com os pesos do horizonte, ou None se faltar algum componente.

    Em 'semanas' devolve a nota publicada (os pesos são os do próprio modelo).
    """
    if horizonte == 'semanas':
        return nota_semanal
    if not isinstance(componentes, dict) or horizonte not in HORIZONTES:
        return None
    pesos = horizontes()[horizonte]['pesos']
    try:
        valores = [float(componentes[k]) for k in COMPONENTES]
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(v) and 0 <= v <= 10 for v in valores):
        return None
    return round(sum(pesos[k] * v for k, v in zip(COMPONENTES, valores)), 2)


def risco_vs_tolerancia(linhas, horizonte, queda_max_pct):
    """Volatilidade da carteira e movimento de 1 desvio-padrão no horizonte, contra a tolerância.

    A volatilidade é a média ponderada das volatilidades individuais: um limite superior, porque
    supõe que todas as ações andam juntas. Usa só posições com peso e volatilidade conhecidos.
    Devolve None se nenhuma tiver volatilidade.
    """
    uteis = [l for l in linhas if l.get('peso_pct') and l.get('vol_anual_pct') is not None]
    base = sum(l['peso_pct'] for l in uteis)
    if not base:
        return None
    vol = sum(l['peso_pct'] * l['vol_anual_pct'] for l in uteis) / base
    janela = horizontes()[horizonte]['janela_anos']
    queda = vol * math.sqrt(janela)
    return {'vol_anual_pct': round(vol, 1), 'janela_anos': janela, 'movimento_1dp_pct': round(queda, 1),
            'queda_max_pct': queda_max_pct, 'acima_da_tolerancia': queda > queda_max_pct,
            'cobertura_peso_pct': round(base, 1)}


def _perguntar_numero(entrada, texto, padrao):
    while True:
        bruto = entrada(f'{texto} [{padrao:g}]: ').strip().replace(',', '.')
        if not bruto:
            return float(padrao)
        try:
            v = float(bruto)
            if 0 < v <= 100:
                return v
        except ValueError:
            pass
        print('  digite um número entre 0 e 100.')


def _perguntar_opcao(entrada, texto, opcoes):
    print(texto)
    for i, (_, rotulo) in enumerate(opcoes, 1):
        print(f'  {i}) {rotulo}')
    while True:
        bruto = entrada('Escolha: ').strip()
        if bruto.isdigit() and 1 <= int(bruto) <= len(opcoes):
            return opcoes[int(bruto) - 1][0]
        print(f'  digite um número de 1 a {len(opcoes)}.')


def assistente(entrada=input):
    """Faz as perguntas e devolve o plano validado (sem salvar)."""
    h = _perguntar_opcao(entrada, '\n1. Por quanto tempo pretende manter essas ações?', [
        ('semanas', 'Semanas (até cerca de 1 mês)'),
        ('meses', 'Meses (de 1 a 12 meses)'),
        ('anos', 'Anos (mais de 1 ano)')])
    o = _perguntar_opcao(entrada, '\n2. Qual é o objetivo principal?', [
        ('crescimento', 'Crescer o patrimônio'),
        ('renda', 'Gerar renda (dividendos)'),
        ('preservacao', 'Preservar o patrimônio')])
    print('\n3. Quanto de queda você toleraria na carteira, no prazo escolhido (em %)?')
    q = _perguntar_numero(entrada, 'Queda máxima tolerada', PADRAO['queda_max_pct'])
    print('\n4. Qual é o máximo que aceita ter em uma única ação (% da carteira)?')
    a = _perguntar_numero(entrada, 'Limite por ação', PADRAO['limite_ativo_pct'])
    print('\n5. E em um único setor (% da carteira)?')
    s = _perguntar_numero(entrada, 'Limite por setor', PADRAO['limite_setor_pct'])
    return validar({'horizonte': h, 'objetivo': o, 'queda_max_pct': q,
                    'limite_ativo_pct': a, 'limite_setor_pct': s})
