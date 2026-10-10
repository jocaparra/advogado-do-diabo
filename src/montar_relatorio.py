# -*- coding: utf-8 -*-
"""Monta relatorio.pdf (paisagem 16:9) a partir dos JSON da semana. Rodar de novo para refazer."""
import json, os, re, sys, glob
from xml.sax.saxutils import escape
import matplotlib
from reportlab.lib.pagesizes import landscape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, Flowable, KeepInFrame)
from reportlab.lib.utils import ImageReader

import carteira as C

BASE = C.pasta_semana()
GRAF = os.path.join(BASE, 'graficos')
OUT = os.path.join(BASE, 'relatorio.pdf')
_a, _m, _d = C.data_semana(BASE)
DATA_REL = f'{_d:02d}/{_m:02d}/{_a}'
CORTE = 'Corte dos dados: fechamento de ' + DATA_REL

# ---------- fontes ----------
FD = os.path.join(os.path.dirname(matplotlib.__file__), 'mpl-data/fonts/ttf')
for n, f in [('DV', 'DejaVuSans.ttf'), ('DV-B', 'DejaVuSans-Bold.ttf'), ('DV-I', 'DejaVuSans-Oblique.ttf'),
             ('DV-BI', 'DejaVuSans-BoldOblique.ttf')]:
    pdfmetrics.registerFont(TTFont(n, os.path.join(FD, f)))
pdfmetrics.registerFontFamily('DV', normal='DV', bold='DV-B', italic='DV-I', boldItalic='DV-BI')

# ---------- paleta ----------
GOLD = colors.HexColor('#FFB800'); BLACK = colors.HexColor('#000000'); GRAY = colors.HexColor('#7F7F7F')
LGRAY = colors.HexColor('#F0F0F0'); GREEN = colors.HexColor('#2E7D32'); AMBER = colors.HexColor('#F9A825')
RED = colors.HexColor('#C62828'); WHITE = colors.white
HX = {'gold': '#FFB800', 'gray': '#7F7F7F', 'green': '#2E7D32', 'amber': '#F9A825', 'red': '#C62828', 'black': '#000000'}
ACAO_COR = {'comprar': GREEN, 'aguardar': AMBER, 'evitar': RED}
ACAO_HX = {'comprar': HX['green'], 'aguardar': '#B07A00', 'evitar': HX['red']}  # texto do amarelo escurecido p/ leitura? mantido na paleta abaixo
ACAO_HX['aguardar'] = HX['amber']

PW, PH = 960, 540
HDR_H = 50
FR_X, FR_Y, FR_W, FR_H = 28, 34, 904, 446

# ---------- carga ----------
MESES = 'jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez'

def J(n):
    with open(os.path.join(BASE, n), encoding='utf-8') as f:
        return json.load(f)
S, CONTRA, RISCO, AUD, ALR, MACRO, CASAS, PRECOS, FLUXO = (J(n) for n in [
    'sintese.json', 'contra.json', 'risco.json', 'auditoria.json', 'alertas.json', 'macro.json', 'casas.json',
    'precos.json', 'fluxo.json'])
XP = C.ler(C.arquivo_xp(BASE))
CONF = C.ler(os.path.join(BASE, 'conferencia.json'), {})
if CONF.get('resumo', {}).get('erros') and os.environ.get('CARTEIRA_FORCAR') != '1':
    sys.exit(f"conferencia.json aponta {CONF['resumo']['erros']} erro(s): corrija os dados (python src/conferir.py "
             f"{os.path.relpath(BASE)}) ou gere mesmo assim com CARTEIRA_FORCAR=1")
try:
    TX = J('textos.json')
except FileNotFoundError:
    TX = {}
PAG = TX.get('paginas', {})
NOTAS = TX.get('notas_paginas', {})
import regras as R
PARAM = {'min_casas_consenso': 3, 'top_n_risco': 5, **TX.get('parametros', {})}
PARAM['corte_compra'] = R.corte_de_compra(S['ranking'], TX) or 0
POL = TX.get('politica_fontes', {})
DADOS_XP = C.data_br(XP['dados_ate'])
MES_XP = C.mes_extenso(XP['data_relatorio'])
_dx = __import__('datetime').date.fromisoformat(XP['dados_ate'])
CHAVE_MES = f"{MESES.split('|')[_dx.month - 1]}-{_dx.strftime('%y')}"
MES_NOME = C.MESES[_dx.month - 1]
_ini = XP['carteira'].get('inicio_carteira', '').split(' ')[0].replace('-', '/')
def fmtc(txt, **extra):
    return txt.format(**extra, dados_xp=DADOS_XP, data=DATA_REL, mes_xp=MES_XP, min_casas=PARAM['min_casas_consenso'],
                      corte=str(PARAM['corte_compra']).replace('.', ','))
R2 = AUD['rodada2']
XPT = {a['ticker']: a for a in XP['acoes']}

# ---------- texto ----------
class M(str):
    """marcação já pronta (não escapar)"""

JSON_MAP = {'risco': 'análise de risco', 'casas': 'levantamento das casas', 'fluxo': 'análise de fluxo',
            'precos': 'série de preços', 'fundamentos': 'fundamentos', 'macro': 'painel macro',
            'sintese': 'síntese', 'alertas': 'alertas', 'xp': 'dados da XP', 'auditoria': 'auditoria',
            'noticias': 'notícias', 'contra': 'objeções'}

def san(t):
    t = str(t)
    t = t.replace('fora de casas.json', 'fora do levantamento das casas')
    t = re.sub(r'(\w+)\.json', lambda m: JSON_MAP.get(m.group(1), m.group(1)), t)
    t = t.replace('2026-09/10', '25/09/2026')
    t = re.sub(r'(\d{4})-(\d{2})-(\d{2})', r'\3/\2/\1', t)
    t = re.sub(r'\b(\d{4})-(\d{2})\b(?!/)', r'\2/\1', t)
    t = re.sub(r'\b(%s)-(\d{2})\b' % MESES, r'\1/\2', t)
    t = t.replace('—', ', ').replace('–', ', ').replace(' - ', ', ')
    t = re.sub(r'(?<=\d)-(?=\d)', ' a ', t)
    t = re.sub(r'(?<=[A-Za-zÀ-ÿ])-(?=[A-Za-zÀ-ÿ0-9])', ' ', t)
    t = re.sub(r'(?<![\w)])-(?=\d)', '−', t)
    t = t.replace('->', 'para')
    return t

def X(t):
    return t if isinstance(t, M) else escape(san(t))

def lab(t):
    """destaca Fato/Opinião/Projeção"""
    t = X(t)
    return M(re.sub(r'(Fato|Opinião|Projeção)(:)', r'<b>\1\2</b>', t))

def fmt(v, d=1, pct=False, sign=False, pre=''):
    if v is None or isinstance(v, str):
        return 'não verificado'
    s = f'{abs(v):,.{d}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    neg = v < 0
    sg = '−' if neg else ('+' if sign and v > 0 else '')
    return f'{sg}{pre}{s}{"%" if pct else ""}'

def col(txt, v, bold=False):
    if isinstance(v, (int, float)) and v > 0: c = HX['green']
    elif isinstance(v, (int, float)) and v < 0: c = HX['red']
    else: c = HX['black']
    s = f'<font color="{c}">{X(txt)}</font>'
    return M(f'<b>{s}</b>' if bold else s)

def sty(name, size=10, lead=None, font='DV', color=BLACK, align=TA_LEFT, **kw):
    return ParagraphStyle(name, fontName=font, fontSize=size, leading=lead or size * 1.28, textColor=color,
                          alignment=align, **kw)
BODY = sty('body', 10); SMALL = sty('small', 9, 11.5); BOLD = sty('bold', 10, font='DV-B')
H2 = sty('h2', 11, font='DV-B', spaceAfter=2)
FRASE = sty('frase', 9, 11.5, font='DV-I', color=BLACK)
CELL = {a: sty('c' + a, 9, 11, align=al) for a, al in [('L', TA_LEFT), ('R', TA_RIGHT), ('C', TA_CENTER)]}
CELLB = {a: sty('cb' + a, 9, 11, font='DV-B', align=al) for a, al in [('L', TA_LEFT), ('R', TA_RIGHT), ('C', TA_CENTER)]}
CELLK = sty('cellk', 9, 11, wordWrap='CJK')

def P(t, st=BODY):
    return Paragraph(X(t), st)

def PL(t, st=BODY):
    return Paragraph(lab(t), st)

def bullets(items, st=SMALL):
    return [Paragraph('• ' + X(i), ParagraphStyle('b', parent=st, leftIndent=9, firstLineIndent=-9, spaceAfter=1.5)) for i in items]

def tbl(rows, widths, aligns=None, header=True, zebra=True, extra=None, bold_first_col=False, valign='MIDDLE', pad=3):
    aligns = aligns or ['L'] * len(widths)
    data = []
    for ri, row in enumerate(rows):
        out = []
        for ci, c in enumerate(row):
            if isinstance(c, Flowable) or isinstance(c, list):
                out.append(c); continue
            stl = CELLB[aligns[ci] if not (header and ri == 0) else ('C' if aligns[ci] == 'C' else aligns[ci])] \
                if (header and ri == 0) or (bold_first_col and ci == 0) else CELL[aligns[ci]]
            out.append(Paragraph(X(c), stl))
        data.append(out)
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [('VALIGN', (0, 0), (-1, -1), valign), ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
          ('TOPPADDING', (0, 0), (-1, -1), pad), ('BOTTOMPADDING', (0, 0), (-1, -1), pad),
          ('LINEBELOW', (0, 0), (-1, -1), 0.25, GRAY)]
    if header:
        st += [('BACKGROUND', (0, 0), (-1, 0), GOLD)]
    if zebra:
        st += [('ROWBACKGROUNDS', (0, 1 if header else 0), (-1, -1), [WHITE, LGRAY])]
    t.setStyle(TableStyle(st + (extra or [])))
    return t

def box(flowables, w, bg=LGRAY, bar=None, pad=6):
    t = Table([[flowables]], colWidths=[w])
    st = [('BACKGROUND', (0, 0), (-1, -1), bg), ('LEFTPADDING', (0, 0), (-1, -1), pad), ('RIGHTPADDING', (0, 0), (-1, -1), pad),
          ('TOPPADDING', (0, 0), (-1, -1), pad - 1), ('BOTTOMPADDING', (0, 0), (-1, -1), pad - 1)]
    if bar:
        st += [('LINEBEFORE', (0, 0), (0, -1), 4, bar)]
    t.setStyle(TableStyle(st))
    return t

def cols(blocks, widths, gap=0, valign='TOP'):
    t = Table([blocks], colWidths=widths)
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), valign), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                           ('RIGHTPADDING', (0, 0), (-1, -1), gap), ('TOPPADDING', (0, 0), (-1, -1), 0),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    return t

# ---------- figuras ----------
FIGS_MISSING = []
try:
    FRASES = J('graficos/frases_leitura.json')
except Exception:
    FRASES = None

def frase(n):
    if FRASES is None:
        return 'Frase de leitura pendente (frases_leitura.json não encontrado).'
    v = None
    if isinstance(FRASES, dict):
        for k in (f'fig{n}', f'Figura {n}', str(n), f'figura{n}', f'fig_{n}', f'Fig{n}'):
            if k in FRASES:
                v = FRASES[k]; break
    elif isinstance(FRASES, list):
        for it in FRASES:
            if isinstance(it, dict) and str(it.get('figura', it.get('n', it.get('id')))) in (str(n), f'fig{n}', f'Figura {n}'):
                v = it; break
        if v is None and 0 < n <= len(FRASES): v = FRASES[n - 1]
    if isinstance(v, dict):
        v = v.get('frase') or v.get('frase_leitura') or v.get('leitura') or v.get('texto')
    return v or f'Frase de leitura da Figura {n} pendente.'

class Fig(Flowable):
    def __init__(self, n, w, h):
        super().__init__(); self.n, self.w, self.h = n, w, h
        self.path = os.path.join(GRAF, f'fig{n}.png')
        self.ok = os.path.exists(self.path)
        if self.ok:
            iw, ih = ImageReader(self.path).getSize()
            self.sc = min(w / iw, h / ih); self.dw, self.dh = iw * self.sc, ih * self.sc
        else:
            FIGS_MISSING.append(n); self.dw, self.dh = w, h
    def wrap(self, aw, ah):
        return self.w, self.dh
    def draw(self):
        c = self.canv
        if self.ok:
            c.drawImage(self.path, (self.w - self.dw) / 2, 0, self.dw, self.dh, mask='auto')
        else:
            c.setFillColor(LGRAY); c.rect(0, 0, self.w, self.h, stroke=0, fill=1)
            c.setFillColor(GRAY); c.setFont('DV-B', 12)
            c.drawCentredString(self.w / 2, self.h / 2, f'Figura {self.n}: em geração')

def figblock(n, w, h):
    return [Fig(n, w, h), Spacer(1, 3), Paragraph(X(frase(n)), FRASE)]

# ---------- documento ----------
META = {'title': '', 'sub': '', 'fonte': ''}
class Meta(Flowable):
    def __init__(self, title, sub, fonte):
        super().__init__(); self.m = (title, sub, fonte)
    def wrap(self, aw, ah): return 0, 0
    def draw(self):
        META['title'], META['sub'], META['fonte'] = self.m

def deco(canv, doc):
    canv.saveState()
    canv.setFillColor(BLACK); canv.rect(0, PH - HDR_H, PW, HDR_H, stroke=0, fill=1)
    canv.setFillColor(GOLD); canv.setFont('DV-B', 17); canv.drawString(28, PH - 25, META['title'][:95])
    canv.setFillColor(WHITE); canv.setFont('DV', 10); canv.drawString(28, PH - 42, META['sub'][:150])
    canv.setFont('DV-B', 11); canv.drawRightString(PW - 28, PH - 30, DATA_REL)
    canv.setStrokeColor(GRAY); canv.setLineWidth(0.5); canv.line(28, 30, PW - 28, 30)
    canv.setFillColor(GRAY); canv.setFont('DV', 9)
    f = META['fonte']
    canv.drawString(28, 18, f'Fonte: {f}. {CORTE}.'[:170])
    canv.drawRightString(PW - 28, 18, f'Página {doc.page}')
    canv.setFont('DV', 7.5)
    canv.drawString(28, 7, 'Material de pesquisa independente, sem vínculo com a XP Investimentos. Não é recomendação de investimento nem substitui assessor habilitado.')
    canv.restoreState()

def page(title, sub, fonte, content, fixed=True):
    out = [Meta(san(title), san(sub), san(fonte))]
    if fixed:
        out.append(KeepInFrame(FR_W, FR_H, content, mode='error'))
    else:
        out += content
    out.append(PageBreak())
    return out

# ---------- ranking ----------
RK = S['ranking']
RKD = {r['ticker']: r for r in RK}
MOTIVO = TX.get('motivo_por_ticker', {})
F4 = J('graficos/fig4_dados.json')['por_ticker']
def cons_short(r):
    f = F4.get(r['ticker'])
    if f:
        n = f['n_casas']
        if n == 0: return 'dado insuficiente (0 casas verificadas)'
        return f'{f["compra"]} compra, {f["neutro"]} neutro, {f["venda"]} venda ({n} casas; ' + ('consenso)' if n >= 3 else 'não é consenso)')
    m = re.search(r'(\d+) compra, (\d+) neutro, (\d+) venda entre (\d+)', r['consenso_casas'])
    if r['ticker'] == 'RDOR3': return 'dado insuficiente'
    if not m: return r['consenso_casas']
    a, b, cc, n = m.groups()
    ok = 'consenso' if int(n) >= 3 else 'não é consenso'
    return f'{a} compra, {b} neutro, {cc} venda ({n} casas; {ok})'

def pct_cell(v, d=1, sign=True):
    return col(fmt(v, d, True, sign), v) if isinstance(v, (int, float)) else 'não verificado'

def acao_cell(a, bold=True):
    return M(f'<b><font color="{ACAO_HX[a]}">{X(a.capitalize())}</font></b>')

# ================= PÁGINAS =================
story = []
FONTE_BASE = fmtc(TX.get('fonte_base', 'XP Research (dados até {dados_xp}), Yahoo Finance (agregador de dados da B3)'))

# ---- Página 1 ----
resumo = []
for it in TX.get('resumo_executivo', []):
    rot = it['rotulo']
    rot = f'{rot}.' if rot.isdigit() else f'{rot}:'
    resumo.append(M(f'<b>{escape(rot)}</b> ' + X(it['texto'])))
RSTY = sty('res', 10, 13)
nl = 0
for t in resumo:
    p = Paragraph(t, RSTY); p.wrap(388, 1000); nl += len(p.blPara.lines)
print('linhas do resumo executivo:', nl)
assert nl <= 10, nl
rsm_box = box([Paragraph('Resumo executivo', ParagraphStyle('rt', parent=H2))] + [Paragraph(t, ParagraphStyle('rr', parent=RSTY, spaceAfter=3)) for t in resumo], 410, bar=GOLD, pad=8)
rt = XP['carteira']['retornos']
ib = PRECOS['ibovespa']
def pr(v): return col(fmt(v, 1, True, True), v)
rows = [['Período', 'Carteira XP', 'Ibovespa'],
        ['Semana', 'não verificado', 'não verificado'],
        [f'Mês ({MES_NOME})', pr(rt['mensal'][CHAVE_MES]['carteira']), pr(rt['mensal'][CHAVE_MES]['ibovespa'])],
        [str(_dx.year), pr(rt[str(_dx.year)]['carteira']), pr(rt[str(_dx.year)]['ibovespa'])],
        ['12 meses', pr(rt['ultimos_12m']['carteira']), pr(rt['ultimos_12m']['ibovespa'])],
        [f'Desde o início ({_ini})', pr(rt['desde_inicio']['carteira']), pr(rt['desde_inicio']['ibovespa'])]]
t_ret = tbl(rows, [150, 100, 100], ['L', 'R', 'R'], pad=2)
nota_ret = Paragraph(X(fmtc(NOTAS.get('ret_xp', 'Retornos da carteira e do Ibovespa pelo PDF da XP, com dados até {dados_xp} e dividendos.')) + ' '
                       f'Ibovespa até {DATA_REL} (Yahoo Finance): 5 pregões {fmt(float(ib["ret_5d"].strip("%")),2,True,True)}, 30 dias {fmt(float(ib["ret_30d"].strip("%")),2,True,True)}, '
                       f'{_dx.year} {fmt(float(ib["ret_ano"].strip("%")),2,True,True)}, 12 meses {fmt(float(ib["ret_12m"].strip("%")),2,True,True)}.'), SMALL)
left1 = [rsm_box, Spacer(1, 8), t_ret, Spacer(1, 4), nota_ret]
right1 = figblock(1, 484, 300)
story += page('Resumo executivo', 'Top Ações XP: análise independente para o horizonte de semanas', FONTE_BASE,
              [cols([left1, right1], [420, 484], gap=12)])

# ---- Página 2: macro ----
efe = MACRO['efeito_por_setor_4_semanas']
COLE = {'positivo': HX['green'], 'negativo': HX['red'], 'neutro': HX['gray']}
rows = [['Setor', 'Efeito em 4 semanas']] + [[k, M(f'<b><font color="{COLE[v["efeito"]]}">{v["efeito"].capitalize()}</font></b>')] for k, v in efe.items()]
t_ef = tbl(rows, [170, 120], ['L', 'L'])
flux = MACRO['figura_8_series']['fluxo_estrangeiro_mensal_RS_bi']
leit = [P(S['visao_mercado'], SMALL), Spacer(1, 4),
        P(f'Fluxo estrangeiro na B3: setembro {fmt(flux["setembro"],2,False,True,"R$ ")} bi e agosto {fmt(flux["agosto"],2,False,True,"R$ ")} bi (InfoMoney, dados da B3; só o agregado mensal é verificável).', SMALL),
        Spacer(1, 4), P('Efeito esperado por setor (projeção do painel macro):', SMALL), Spacer(1, 2), t_ef]
story += page('Painel macro', 'Juros, dólar, Brent, Ibovespa e fluxo estrangeiro nos últimos 3 meses',
              'Banco Central (SGS), Yahoo Finance, InfoMoney, Federal Reserve',
              [cols([figblock(8, 590, 400), [Paragraph('Leitura do cenário', H2)] + leit], [606, 298])])

# ---- Páginas de figura: figura grande à esquerda, apoio à direita ----
FW, FH, RW = 670, 392, 224
def figpage(n, right, title, sub, fonte, fh=FH):
    return page(title, sub, fonte, [cols([figblock(n, FW, fh), right], [FW + 10, RW], gap=0)])
def rtitle(t): return Paragraph(t, ParagraphStyle('rt2', parent=H2, fontSize=10))

# ---- Página 3: ranking ----
rows = [['#', 'Ticker', 'Ação', 'Nota', 'Upside aj.']]
for r in RK:
    rows.append([str(r['posicao']), r['ticker'], acao_cell(r['acao_sugerida']), fmt(r['nota'], 2), pct_cell(r['upside_ajustado_pct'])])
t_rank = tbl(rows, [24, 48, 58, 36, 52], ['C', 'L', 'L', 'R', 'R'], pad=1.5)
story += figpage(2, [t_rank], 'Ranking completo', 'Nota de 0 a 10 para o horizonte de semanas e ação sugerida',
                 'Análise do agente (síntese), XP Research, Yahoo Finance, InfoMoney')
rows = [['#', 'Ticker', 'Ação', 'Nota', 'Upside ajust.', 'Principal motivo']]
for r in RK:
    rows.append([str(r['posicao']), r['ticker'], acao_cell(r['acao_sugerida']), fmt(r['nota'], 2), pct_cell(r['upside_ajustado_pct']), MOTIVO.get(r['ticker'], r.get('principal_motivo', ''))])
story += page('Ranking completo: principal motivo', 'Ação sugerida, nota, upside ajustado e o motivo de cada posição',
              'Análise do agente (síntese), XP Research, Yahoo Finance, InfoMoney',
              [tbl(rows, [26, 56, 66, 40, 74, 642], ['C', 'L', 'L', 'R', 'R', 'L'], pad=2.5), Spacer(1, 5),
               P(fmtc(PAG.get('ranking_rodape', 'A nota serve para ordenar e não é probabilidade.')), SMALL)])
# ---- Resumo por ação ----
rows = [['Ticker', 'Setor', 'Preço atual', 'Alvo XP', 'Upside XP', 'Upside ajust.', 'Rating XP', 'Consenso das casas', 'Nota', 'Ação', 'Certeza']]
for r in RK:
    rows.append([r['ticker'], r['setor'], fmt(r['preco_atual'], 2, False, False, 'R$ '), fmt(r['preco_alvo_xp'], 2, False, False, 'R$ '),
                 pct_cell(r['upside_xp_pct']), pct_cell(r['upside_ajustado_pct']), r['rating_xp'], cons_short(r), fmt(r['nota'], 2),
                 acao_cell(r['acao_sugerida']), r['certeza'].capitalize()])
story += page('Resumo por ação', 'Preço atual, alvo da XP, consenso das casas, nota e ação sugerida',
              f'XP Research, Yahoo Finance (cotação de {DATA_REL}), InfoMoney e sites de casas de análise',
              [tbl(rows, [54, 106, 66, 62, 56, 60, 52, 246, 36, 60, 46], ['L', 'L', 'R', 'R', 'R', 'R', 'L', 'L', 'R', 'L', 'L'], pad=2),
               Spacer(1, 5),
               P(f'Preço atual é o fechamento de {DATA_REL} (Yahoo Finance, agregador dos dados da B3). ' + fmtc(PAG.get('upside_ajustado_metodo', '')) + fmtc(' Consenso só vale com {min_casas} ou mais casas verificadas.'), SMALL)])

# ---- Páginas 4 a 6: upside, consenso, desempenho, risco ----
story += figpage(3, [rtitle('Como ler'), P(fmtc(PAG.get('fig3_como_ler', '')) + f' Cotação de {DATA_REL}.', SMALL)] + [x for t_ in NOTAS.get('fig3', []) for x in (Spacer(1, 4), P(t_, SMALL))],
                 'Upside até o alvo', 'Até o alvo da XP, até a mediana das outras casas e ajustado pelo agente',
                 f'XP Research, InfoMoney e sites de casas de análise, Yahoo Finance (cotação de {DATA_REL})')
MINC = PARAM['min_casas_consenso']
ncs = ', '.join(f'{k} ({v["n_casas"]})' for k, v in F4.items() if v['n_casas'] < MINC)
com_cons = ', '.join(k for k, v in F4.items() if v['n_casas'] >= MINC) or 'nenhum ticker'
story += figpage(4, [rtitle('Consenso das casas'), P(fmtc(PAG.get('fig4_consenso', 'Só vale o consenso com pelo menos {min_casas} casas verificadas.'), com_consenso=com_cons) + ' ' + NOTAS.get('fig4', ''), SMALL), Spacer(1, 4),
                   P('Casas verificadas nos demais: ' + ncs + '.', SMALL)],
                 'Consenso das casas', 'Compra, neutro e venda por ticker, com o rating da XP',
                 f'InfoMoney e sites de casas de análise, XP Research (casas verificadas até {DATA_REL})')
ibr = [['Período', 'Ibovespa'], ['5 pregões', pr(float(ib['ret_5d'].strip('%')))], ['30 dias', pr(float(ib['ret_30d'].strip('%')))],
       [str(_dx.year), pr(float(ib['ret_ano'].strip('%')))], ['12 meses', pr(float(ib['ret_12m'].strip('%')))]]
story += figpage(5, [rtitle(f'Ibovespa até {DATA_REL}'), tbl(ibr, [90, 100], ['L', 'R'], pad=2), Spacer(1, 4),
                     P('Retornos de preço de fechamento sem ajuste por proventos (Yahoo Finance, dados da B3).', SMALL)],
                 'Desempenho das ações', f'Retorno de 5 dias, 30 dias e {_dx.year} de cada ação contra o Ibovespa',
                 'Yahoo Finance (agregador de dados da B3), XP Research')
tp = RISCO['tabela_por_ticker']
rows = [['Ticker', 'Vol. 90d', 'Beta']] + [[r['ticker'], fmt(tp[r['ticker']]['vol_90pregoes_anual_pct'], 1, True), fmt(tp[r['ticker']]['beta_90pregoes_ibov'], 2)] for r in RK]
story += figpage(6, [rtitle('Risco de cada ação'), tbl(rows, [54, 76, 74], ['L', 'R', 'R'], pad=1.5)],
                 'Upside ajustado contra risco', 'Volatilidade anualizada e beta de 90 pregões',
                 f'Yahoo Finance, cálculos do agente de risco (90 pregões até {DATA_REL}), análise do agente')

# ---- Página 7: exposição setorial e riscos ----
rc = RISCO['cenarios_estresse_4_semanas']
top5 = [r['ticker'] for r in RK[:PARAM['top_n_risco']]]
def est(cn, t):
    v = rc[cn]['estimativa_pct'].get(t)
    return col(fmt(v, 1, True, True), v) if v is not None else 'n/e'
rows = [['Cenário (projeção)'] + top5]
for i, nm in enumerate(PAG.get('risco_cenarios') or [c_.get('nome', f'Cenário {k + 1}') for k, c_ in enumerate(rc)]):
    rows.append([nm] + [est(i, t) for t in top5])
t_str = tbl(rows, [120] + [50] * len(top5), ['L'] + ['R'] * len(top5), pad=2)
_risco_txt = PAG.get('risco') or [RISCO.get('concentracao_setorial', {}).get('leitura', ''),
                                  RISCO.get('correlacao_top6', {}).get('leitura', ''),
                                  RISCO.get('queda_conjunta_top5', {}).get('resposta_curta', '')]
rk6 = [Paragraph('Riscos da carteira como um todo', H2)]
for _t in _risco_txt:
    if _t:
        rk6 += [P(_t, SMALL), Spacer(1, 3)]
rk6 += [P('Projeção de queda em 4 semanas (beta linear, 90 pregões, amostra curta; não é previsão). n/e: não estimado.', SMALL), Spacer(1, 2), t_str]
story += page('Exposição setorial e riscos da carteira', 'Peso no Ibovespa, na carteira da XP e no conjunto que o agente classificou como comprar',
              f'XP Research (pesos), análise de risco do agente (preços e macro até {DATA_REL})',
              [cols([figblock(7, 520, 380), rk6], [530, 374])])

# ---- Avaliação das recomendações anteriores (só se houver horizonte vencido) ----
AVAL = C.ler(os.path.join(os.path.dirname(BASE), 'avaliacao.json'), {})
def _pagina_avaliacao():
    hz = AVAL.get('horizontes', {})
    if not any(h.get('observacoes') for h in hz.values()):
        return []
    rows = [['Horizonte', 'Ação sugerida', 'Observações', 'Excesso médio contra o Ibovespa', 'Acerto (bateu o Ibovespa)']]
    notas = []
    for nome, h in hz.items():
        rot = nome.replace('_', ' ')
        for ac, v in h.get('por_acao', {}).items():
            rows.append([rot, ac.capitalize(), str(v['n']), col(fmt(v['excesso_medio_pp'], 2, False, True) + ' pp', v['excesso_medio_pp']),
                         f"{fmt(v['acerto_pct'], 0)}%".replace('%%', '%')])
        if h.get('observacoes'):
            sp = h.get('spearman_nota_excesso_medio')
            notas.append(f"{rot}: {h['observacoes']} observações em {h['semanas']} semana(s), amostra {h['amostra']}; "
                         f"correlação de postos entre nota e excesso de retorno: {fmt(sp, 2) if sp is not None else 'não definida'}.")
    corpo = [tbl(rows, [150, 150, 110, 260, 234], ['L', 'L', 'R', 'R', 'R'], pad=2), Spacer(1, 6)]
    corpo += bullets(notas) + [Spacer(1, 4), P('Método: ' + AVAL.get('metodo', '') + '. Com amostra insuficiente, nada disso é evidência de que a nota funciona.', SMALL)]
    return page('Desempenho das recomendações anteriores', 'Retorno contra o Ibovespa 4 e 12 semanas depois de cada recomendação',
                'historico_carteira.json, séries de preço (Yahoo Finance), cálculo do agente', corpo, fixed=False)
story += _pagina_avaliacao()

# ---- Página 8: mudanças no ranking ----
story += page('Mudanças no ranking', 'Posição contra a semana anterior',
              'Análise do agente; mudanças de peso da carteira: XP Research',
              [cols([figblock(9, 560, 330), [Paragraph('Mudanças do mês na carteira da XP', H2), P(XP['mudancas_mes'].replace(' Páginas 1 e 2.', ''), SMALL)]], [580, 324], gap=10)])
# ---- Página 9: calendário ----
story += figpage(10, [rtitle('Catalisadores'), P(NOTAS.get('catalisadores', 'Veja na figura os eventos com data verificada.'), SMALL)],
                 'Calendário de catalisadores', 'Próximas 4 semanas e ação afetada',
                 'Painel macro (InfoMoney, Federal Reserve, Banco Central), análise do agente', fh=420)

# ---- Páginas por ação ----
RESSALVA = TX.get('ressalvas_por_ticker', {})
CAIXAS = TX.get('caixas_por_ticker', {})

def fonte_par(f):
    nm = X(f['fonte']); d = X(f['data'])
    u = f.get('url')
    if isinstance(u, str) and u.startswith('http'):
        return Paragraph(f'<a href="{u}" color="#000000"><u>{nm}</u></a>, {d}', ParagraphStyle('f', parent=SMALL, fontSize=9, leading=10.5, spaceAfter=1.5, leftIndent=8, firstLineIndent=-8))
    return Paragraph(f'{nm}, {d}', ParagraphStyle('f', parent=SMALL, fontSize=9, leading=10.5, spaceAfter=1.5, leftIndent=8, firstLineIndent=-8))

def page_ticker(r):
    t = r['ticker']; x = XPT[t]
    hdr = [['Ticker', 'Setor', 'Preço atual', 'Alvo XP', 'Upside XP', 'Mediana casas', 'Upside ajust.', 'Rating XP', 'Peso XP', 'Consenso das casas', 'Nota', 'Ação', 'Certeza'],
           [t, r['setor'], M(X(fmt(r['preco_atual'], 2, False, False, 'R$ ')) + '<br/>' + X(r['data_cotacao'])), fmt(r['preco_alvo_xp'], 2, False, False, 'R$ '), pct_cell(r['upside_xp_pct']),
            (fmt(r['mediana_casas'], 2, False, False, 'R$ ') if isinstance(r['mediana_casas'], (int, float)) else 'não verificado') + (f' ({r["n_alvos_mediana"]} alvos)' if r.get('n_alvos_mediana') else ''),
            pct_cell(r['upside_ajustado_pct']), r['rating_xp'], f'{fmt(x["peso_atual"],1,True)} (antes {fmt(x["peso_anterior"],1,True)})',
            cons_short(r), fmt(r['nota'], 2), acao_cell(r['acao_sugerida']), r['certeza'].capitalize()]]
    th = tbl(hdr, [50, 78, 84, 56, 52, 92, 52, 54, 64, 168, 34, 66, 54], ['L', 'L', 'R', 'R', 'R', 'R', 'R', 'L', 'L', 'L', 'R', 'L', 'L'], pad=2, zebra=False)
    comp = r['componentes']
    comp_txt = (f'Componentes da nota (0 a 10, projeção do analista): catalisadores {fmt(comp["catalisadores"],1)} (25%), notícias {fmt(comp["noticias"],1)} (20%), '
                f'momentum {fmt(comp["momentum"],1)} (20%), macro e eleição {fmt(comp["macro_eleicao"],1)} (20%), valuation e upside {fmt(comp["valuation_upside"],1)} (15%). '
                f'Retornos: 5 dias {fmt(r["retornos"]["5d_pct"],1,True,True)}, 30 dias {fmt(r["retornos"]["30d_pct"],1,True,True)}, 90 dias {fmt(r["retornos"]["90d_pct"],1,True,True)}; beta 90 dias {fmt(r["retornos"]["beta_90d"],2)}.')
    tese = box([Paragraph(lab(r['tese']), sty('t', 9.5, 12)), Spacer(1, 2), Paragraph(X(comp_txt), sty('ct', 9, 11, color=GRAY))], FR_W)
    pros = [Paragraph('Prós', H2)] + bullets(r['pros'])
    contras = [Paragraph('Contras', H2)] + bullets(r['contras'])
    cat = [Paragraph('Catalisadores', H2)] + bullets([f'{c["evento"]}: {c["data"]}' for c in r['catalisadores']])
    risc = [Paragraph('Riscos', H2)] + bullets(r['riscos'])
    gat = [Paragraph('Gatilho de revisão', H2), P(r['gatilho_revisao'], SMALL), Spacer(1, 3), Paragraph('Divergência com a XP', H2), P(r['divergencia_xp'], SMALL)]
    fts = [fonte_par(f) for f in r['fontes']]
    half = (len(fts) + 1) // 2
    body = [th, Spacer(1, 5), tese, Spacer(1, 5),
            cols([pros, contras], [452, 452], gap=8), Spacer(1, 4),
            cols([cat, risc, gat], [250, 250, 404], gap=8), Spacer(1, 4)]
    if t in CAIXAS:
        cx = CAIXAS[t]
        body += [box([Paragraph(M('<b>' + X(cx['titulo']) + '</b> ' + X(cx['texto'])), sty('ig', 9.5, 12))], FR_W, bg=WHITE, bar=GOLD), Spacer(1, 4)]
    if t in RESSALVA:
        txt = '<b>Ressalvas e itens retirados pela auditoria:</b> ' + ' '.join(X(s) for s in RESSALVA[t])
        body += [box([Paragraph(M(txt), sty('rs', 9, 11))], FR_W, bg=LGRAY, bar=GRAY, pad=5), Spacer(1, 4)]
    body += [Paragraph('Fontes com data', H2), cols([fts[:half], fts[half:]], [452, 452], gap=8)]
    sub = f'{x["empresa"]}, {r["setor"]}. Ação sugerida: {r["acao_sugerida"]}, nota {fmt(r["nota"], 2)}, certeza {r["certeza"]}'
    return page(f'{r["posicao"]}. {t}', sub, 'fontes listadas ao fim da página (links na lista de fontes), XP Research, Yahoo Finance', body)
DOS = C.ler(os.path.join(BASE, 'dossie.json'), {}).get('tickers', {})
IND_ORDEM = [('receita_12m', 'Receita 12 meses', 'bi'), ('ebitda_12m', 'EBITDA 12 meses (aprox.)', 'bi'), ('lucro_liquido_12m', 'Lucro líquido 12 meses', 'bi'),
             ('margem_liquida', 'Margem líquida', 'pct'), ('margem_ebitda', 'Margem EBITDA', 'pct'), ('roe_12m', 'ROE 12 meses', 'pct'),
             ('divida_liquida_sobre_ebitda', 'Dívida líquida / EBITDA', 'x'), ('p_l', 'P/L', 'x'), ('p_vp', 'P/VP', 'x'), ('ev_ebitda', 'EV/EBITDA', 'x'),
             ('dividend_yield_12m', 'Dividend yield 12 meses', 'pct'), ('payout_12m', 'Payout 12 meses', 'pct'),
             ('crescimento_receita_ultimo_ano', 'Crescimento da receita (último ano)', 'pct')]

def _fmt_ind(v, tipo):
    if v is None or isinstance(v, str):
        return 'n/d'
    if tipo == 'bi':
        return 'R$ ' + fmt(v / 1e9, 1) + ' bi'
    if tipo == 'pct':
        return fmt(v, 1, True)
    return fmt(v, 1) + 'x'

def page_dossie(r):
    t = r['ticker']
    d = DOS.get(t)
    if not d:
        return []
    val = d['valuation']
    ind = d.get('indicadores', {})
    rows = [['Indicador (CVM)', 'Valor']]
    for k, nome, tp in IND_ORDEM:
        if k in ind and ind[k]['valor'] is not None:
            rows.append([nome, _fmt_ind(ind[k]['valor'], tp)])
    if len(rows) == 1:
        rows.append(['Sem demonstrações na CVM', 'n/d'])
    t_ind = tbl(rows, [190, 120], ['L', 'R'], pad=1.5)
    chk = [['Checklist do setor', 'Valor', 'Fonte e data']]
    for c in d['checklist']:
        fonte = f"{c['fonte']}, {c['data']}" if c.get('fonte') else 'pendente'
        chk.append([c['rotulo'], str(c['valor']), fonte])
    t_chk = tbl(chk, [150, 95, 85], ['L', 'L', 'L'], pad=1.5)
    esq = [Fig(0, 0, 0)] if False else []
    img = os.path.join(GRAF, f'dossie_{t}.png')
    fig_f = []
    if os.path.exists(img):
        iw, ih = ImageReader(img).getSize()
        w = 560; h = w * ih / iw
        class _I(Flowable):
            def __init__(s): super().__init__(); s.w, s.h = w, h
            def wrap(s, aw, ah): return s.w, s.h
            def draw(s): s.canv.drawImage(img, 0, 0, s.w, s.h, mask='auto')
        fig_f = [_I()]
    if val.get('status') == 'ok':
        cs = val['cenarios']
        vr = [['Cenário', 'ke', 'g curto', 'g final', 'Valor por ação', 'Contra o preço']]
        for nome in ('bear', 'base', 'bull'):
            c = cs[nome]
            vr.append([nome.capitalize(), fmt(c['ke_pct'], 1, True), fmt(c['g_curto_pct'], 1, True), fmt(c['g_terminal_pct'], 1, True),
                       fmt(c.get('valor_justo_por_acao'), 2, False, False, 'R$ '), col(fmt(c.get('margem_pct'), 1, True, True), c.get('margem_pct'))])
        t_val = tbl(vr, [70, 60, 70, 70, 110, 110], ['L', 'R', 'R', 'R', 'R', 'R'], pad=1.5)
        gr = [['ke \\ g final'] + [fmt(g, 1, True) for g in val['grade']['g_terminal_pct']]]
        for ke, lin in zip(val['grade']['ke_pct'], val['grade']['valor_por_acao']):
            gr.append([fmt(ke, 1, True)] + [fmt(v, 2, False, False, 'R$ ') for v in lin])
        t_gr = tbl(gr, [90, 90, 90, 90], ['L', 'R', 'R', 'R'], pad=1.5)
        ki = val.get('ke_implicito_pct')
        leitura = (f"O preço de R$ {fmt(d['preco'], 2)} embute retorno esperado de {fmt(ki, 1, True)} ao ano nas premissas do projeto "
                   f"(referência de {fmt(cs['base']['ke_pct'], 1, True)}). " if ki is not None else '')
        if val.get('roe_exigido_pct') is not None:
            leitura += (f"Para sustentar o P/VP de {fmt(val['p_vp_atual'], 1)}x com crescimento de {fmt(cs['base']['g_terminal_pct'], 1, True)}, o ROE precisaria ser de "
                        f"{fmt(val['roe_exigido_pct'], 1, True)}; o normalizado é {fmt(val['roe_normalizado_pct'], 1, True)}.")
        notas = (leitura + ' Modelo simplificado de lucros descontados, com premissas do projeto (dados/premissas_valuation.json): serve para comparar e não prevê preço.')
        base_txt = [Paragraph('Valuation por cenários (R$ por ação)', H2), t_val, Spacer(1, 5), Paragraph('Sensibilidade do valor por ação (cenário base de lucro)', H2), t_gr,
                    Spacer(1, 4), P(notas, SMALL)]
    else:
        base_txt = [Paragraph('Valuation', H2), P('Indisponível: ' + val.get('motivo', 'sem dados') + '.', SMALL)]
    esquerda = fig_f + [Spacer(1, 4)] + base_txt
    direita = [t_ind, Spacer(1, 6), t_chk]
    return page(f'{r["posicao"]}. {t}: dossiê', f'{d["empresa"] or t}, perfil {d["perfil"]["nome"]}',
                'CVM (DFP e ITR, dados abertos), premissas do projeto, cotação de ' + DATA_REL, [cols([esquerda, direita], [574, 330], gap=10)])

for r in RK:
    story += page_ticker(r)
    story += page_dossie(r)

# ---- Divergências com a XP ----
dv = {d['ticker']: d for d in S['divergencias_xp']}
rows = [['Ticker', 'XP', 'Agente', 'Onde discorda e por quê']]
DIV_OVR = TX.get('divergencia_texto_override', {})
for r in RK:
    d = dv.get(r['ticker'])
    if d:
        rows.append([r['ticker'], d['xp'], acao_cell(d['analista']), d['motivo']])
    else:
        xr = XPT[r['ticker']]
        rows.append([r['ticker'], f'{xr["rating"]}, peso {fmt(xr["peso_atual"],1,True)}' + (f', alvo R$ {fmt(xr["preco_alvo"],2)}' if xr.get('preco_alvo') else ''),
                     acao_cell(r['acao_sugerida']), DIV_OVR.get(r['ticker'], r['divergencia_xp'])])
story += page('Divergências com a XP', 'Onde o agente discorda da carteira Top Ações XP, lado a lado',
              f'XP Research (PDF de {MES_XP}), análise do agente',
              [tbl(rows, [48, 190, 62, 604], ['L', 'L', 'L', 'L'], pad=2)], fixed=False)

# ---- XP no horizonte de semanas ----
ind = XP['carteira']['indicadores']
rows = [['Indicador', 'Carteira XP', 'Ibovespa'],
        ['Sharpe', fmt(ind['sharpe']['carteira'], 2), fmt(ind['sharpe']['ibovespa'], 2)],
        ['Volatilidade', fmt(ind['volatilidade_pct']['carteira'], 2, True), fmt(ind['volatilidade_pct']['ibovespa'], 2, True)],
        ['Beta', fmt(ind['beta']['carteira'], 1), fmt(ind['beta']['ibovespa'], 1)]]
t_ind = tbl(rows, [120, 90, 80], ['L', 'R', 'R'], pad=2)
rows = [['Mês', 'Carteira', 'Ibovespa']]
for k, v in rt['mensal'].items():
    rows.append([k.replace('-', '/'), pr(v['carteira']), pr(v['ibovespa'])])
t_mes = tbl(rows, [70, 80, 80], ['L', 'R', 'R'], pad=1)
story += page('A carteira da XP para o horizonte de semanas', 'Desempenho da carteira contra o Ibovespa e o que isso muda na leitura',
              f'XP Research (Top Ações XP, {MES_XP}, dados até {DADOS_XP}), análise do agente',
              [cols([[Paragraph('Discussão', H2), P(S['discussao_xp_horizonte_semanas'], sty('d', 10, 13.5)), Spacer(1, 6),
                      Paragraph('Mudanças do mês na carteira da XP', H2), P(XP['mudancas_mes'], SMALL)],
                     [Paragraph('Indicadores (PDF da XP)', H2), t_ind, Spacer(1, 6), Paragraph('Retornos mensais (%)', H2), t_mes]],
                    [560, 344], gap=16)])

# ---- Objeções do advogado ----
rev = {i['ticker']: i for i in S['revisao_pos_advogado']['itens']}
rows = [['Ticker', 'Força', 'Objeção do advogado', 'Decisão do analista', 'Nota antes, depois']]
seen = set()
for o in CONTRA['objecoes']:
    t = o['ticker']; i = rev.get(t, {})
    if o['forca'] == 'fraca': dec = 'Rejeitada'
    elif t in NOTAS.get('objecoes_aceita_em_parte', []): dec = 'Aceita em parte'
    else: dec = 'Aceita'
    nota = ''
    if t not in seen and o['forca'] != 'fraca' or (t == 'VALE3'):
        nota = f'{fmt(i.get("nota_antes"),2)} para {fmt(i.get("nota_depois"),2)}' if i else ''
    seen.add(t)
    rows.append([f'{t} (#{o["posicao"]})', o['forca'].capitalize(), o['objecao'], dec, nota])
ob_txt = P('Veredito do advogado: ' + CONTRA['veredito_geral'], SMALL)
rv = S['revisao_pos_advogado']
story += page('Objeções do advogado', 'Razões contra o ranking e o que o analista aceitou ou rejeitou',
              'Agente advogado (InfoMoney, Yahoo Finance, análise de risco), revisão do analista',
              [tbl(rows, [70, 46, 520, 150, 118], ['L', 'L', 'L', 'L', 'R'], pad=2), Spacer(1, 5),
               P('Pesos da nota mantidos. ' + rv['regra_acao'][0].upper() + rv['regra_acao'][1:] + ' ' + ('Notas depois da rodada 1 da auditoria: ' + ', '.join(f'{k} {fmt(v["depois"],2)}' for k, v in S['correcoes_rodada1']['notas_antes_depois'].items()) if all(isinstance(v, dict) and 'depois' in v for v in S['correcoes_rodada1']['notas_antes_depois'].values()) else ''), SMALL)],
              fixed=False)
story += page('Veredito do advogado', 'Resumo do agente advogado sobre a robustez do ranking',
              'Agente advogado, análise do agente',
              [box([P(CONTRA['veredito_geral'], sty('v', 10.5, 14))], FR_W, bar=GOLD, pad=8), Spacer(1, 8),
               Paragraph('Lacunas apontadas pelo advogado', H2)] + bullets(CONTRA['lacunas']))

# ---- Auditoria ----
u = AUD['universo']
r2i = R2['itens']
n_ap = sum(1 for i in r2i if i['resultado'] == 'aprovado'); n_rp = sum(1 for i in r2i if i['resultado'] == 'reprovado')
rows = [['Rodada', 'Itens conferidos', 'Aprovados', 'Reprovados', 'Severidade dos reprovados / observação'],
        ['1', f'{AUD["conferidos"]} de {u["total_itens"]} ({fmt(AUD["percentual_conferido_universo"],1,True)})', str(AUD['aprovados']), str(AUD['reprovados']),
         f'alta {AUD["reprovados_por_severidade"]["alta"]}, média {AUD["reprovados_por_severidade"]["média"]}, baixa {AUD["reprovados_por_severidade"]["baixa"]}; veredito: reprovado, com correções'],
        ['2', f'{len(r2i)} (os {R2["reprovados_rodada1_reconferidos"]} reprovados da rodada 1 e {R2["achados_novos"]} achados novos)', str(n_ap), str(n_rp),
         f'dos {R2["reprovados_rodada1_reconferidos"]} reprovados da rodada 1, {R2["agora_aprovados"]} foram corrigidos e {R2["seguem_reprovados"]} seguem reprovados']]
t_rod = tbl(rows, [50, 290, 70, 70, 424], ['C', 'L', 'R', 'R', 'L'], pad=3)
rows = [['Universo auditado', 'Itens'],
        ['Itens totais', f'{u["total_itens"]} ({u["itens_base"]} da base e {u["itens_adicionais_achados"]} achados adicionais)'],
        ['Numéricos verificados integralmente', str(u['numericos_verificados_integralmente'])],
        ['Textuais obrigatórios', str(u['textuais_obrigatorios'])],
        ['Demais textuais (amostra de 25% sorteada)', f'{u["amostrados_dos_demais"]} de {u["textuais_demais"]}'],
        ['Total conferido', f'{AUD["conferidos"]} ({fmt(AUD["percentual_conferido_universo"],1,True)} do universo)']]
t_uni = tbl(rows, [260, 320], ['L', 'L'], pad=2)
seguem = TX.get('auditoria', {}).get('seguem_reprovados', [])
_au = TX.get('auditoria', {})
_cf = CONF.get('resumo')
conf_par = P(f"Conferência automática em código (src/conferir.py): {_cf['verificacoes']} verificações, {_cf['erros']} erros e {_cf['avisos']} avisos. "
             "Recalcula notas, upsides, medianas, retornos, beta e volatilidade a partir dos dados e valida os arquivos contra os schemas.", SMALL) if _cf else Spacer(1, 0)
ver = box([Paragraph('<b>Veredito final: ' + X(_au.get('rotulo_veredito', 'ver auditoria')) + '.</b> ' + X(_au.get('veredito_final', R2.get('veredito_final', ''))), sty('ver', 10.5, 14))], FR_W, bar=GOLD, pad=8)
story += page('Auditoria', 'Universo, itens conferidos, duas rodadas e veredito',
              f'Agente auditor (auditoria.json, rodadas 1 e 2 em {DATA_REL})',
              [ver, Spacer(1, 4), conf_par, Spacer(1, 6), Paragraph('Rodadas', H2), t_rod, Spacer(1, 6),
               cols([[Paragraph('Universo', H2), t_uni],
                     [Paragraph('Itens que seguem reprovados após a rodada 2', H2)] + bullets(seguem) +
                     [Spacer(1, 3), P(f'Amostra de regressão da rodada 2: {len(R2["amostra_regressao"])} itens textuais aprovados, todos mantidos. Itens retirados do relatório: {len(R2["sai_do_relatorio"])} (ver página de lacunas).', SMALL)]],
                    [600, 304], gap=10)])

RES18 = [tuple(x) for x in TX.get('ressalvas_auditoria', [])] or \
        [(i.get('ticker', ''), i.get('campo', ''), i.get('ressalva', '')) for i in R2.get('fica_com_ressalva', [])]
rows = [['Ticker', 'Item', 'Ressalva da auditoria']] + [[a, b, c_] for a, b, c_ in RES18]
story += page('Auditoria: ressalvas que ficam no relatório', 'Itens aprovados com ressalva, na forma exigida pela rodada 2',
              f'Agente auditor (rodada 2, {DATA_REL})',
              [tbl(rows, [56, 170, 678], ['L', 'L', 'L'], pad=2)])

# ---- Alertas ----
DOT = {'vermelho': HX['red'], 'amarelo': HX['amber'], 'verde': HX['green']}
rows = [['Nível', 'Ticker', 'Fato', 'Fonte e data', 'Impacto esperado', 'Ação recomendada']]
for a in ALR['alertas']:
    rows.append([Paragraph(f'<font color="{DOT[a["nivel"]]}">●</font>', ParagraphStyle('dot', fontName='DV', fontSize=14, leading=14, alignment=TA_CENTER)), a['ticker'], a['fato'], f'{a["fonte"]}, {a["data"]}', a['impacto'], a['acao_recomendada']])
story += page('Alertas', ALR['resumo'], 'InfoMoney, Yahoo Finance (dados da B3), análise do agente',
              [tbl(rows, [38, 62, 340, 150, 120, 194], ['C', 'L', 'L', 'L', 'L', 'L'], pad=2), Spacer(1, 4),
               P(NOTAS.get('alertas', 'Critério: vermelho, tese invalidada, considerar sair; amarelo, tese enfraquecida, monitorar; verde, tese reforçada.'), SMALL)],
              fixed=False)

# ---- Lacunas ----
sai = TX.get('lacunas', {}).get('retirados', [])
dados = TX.get('lacunas', {}).get('nao_verificados', [])
story += page('Lacunas (1 de 2)', 'O que saiu do relatório pela auditoria e o que não foi possível verificar',
              'Auditoria (rodada 2), síntese do analista, advogado',
              [cols([[Paragraph('Itens retirados do relatório pela auditoria', H2)] + bullets(sai),
                     [Paragraph('Dados não verificados ou insuficientes', H2)] + bullets(dados)], [446, 458], gap=12)])
_dg = TX.get('diagnostico_acesso', {})
diag = [['Fonte', _dg.get('titulo_coluna', 'Resultado do teste de acesso') + f' ({DATA_REL})']] + _dg.get('linhas', [])
story += page('Lacunas (2 de 2): diagnóstico de acesso', 'Fontes que abriram, fontes bloqueadas e como isso afeta o relatório',
              f'diagnostico_acesso.md (coleta de {DATA_REL}), auditoria',
              [tbl(diag, [330, 574], ['L', 'L'], pad=2), Spacer(1, 6),
               P(_dg.get('efeito', ''), SMALL)])

# ---- Lista de fontes ----
fontes = {}
def add(fonte, url, data):
    if not isinstance(url, str) or not url.startswith('http'): return
    if any(b in url for b in POL.get('dominios_fora_da_lista_de_fontes', [])): return
    fontes.setdefault(url, (fonte, data))
for r in RK:
    for f in r['fontes']:
        if 'yahoo.com' in str(f.get('url')): continue
        u_ = f.get('url')
        if isinstance(u_, str) and u_.startswith('http'): add(f['fonte'] + f' ({r["ticker"]})', u_, f['data'])
for a in ALR['alertas']:
    for u_ in (a['url'] if isinstance(a['url'], list) else [a['url']]): add(a['fonte'] + f' ({a["ticker"]})', u_, a['data'])
for i in MACRO['indicadores']:
    add(i['fonte'] + f' ({i["indicador"]})', i.get('url'), i.get('data_do_dado', ''))
for o in CONTRA['objecoes']:
    for u_ in (o['url'] if isinstance(o['url'], list) else [o['url']]): add(o['fonte'].split(';')[0] + f' ({o["ticker"]})', u_, o['data'])
items = [(Paragraph(f'<b>{X(n)}</b>, {X(d)}<br/><font color="#7F7F7F">{escape(u_)}</font>', CELLK)) for u_, (n, d) in fontes.items()]
for k_, e_ in enumerate(TX.get('fontes_extras', [])):
    items.insert(k_, Paragraph(f'<b>{X(e_["nome"])}</b>, {X(e_["data"])}<br/><font color="#7F7F7F">{escape(e_["url"])}</font>', CELLK))
rowsF = []
for i in range(0, len(items), 2):
    rowsF.append([items[i], items[i + 1] if i + 1 < len(items) else ''])
tf = Table(rowsF, colWidths=[452, 452], repeatRows=0)
tf.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ROWBACKGROUNDS', (0, 0), (-1, -1), [WHITE, LGRAY]),
                        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4), ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
story += [Meta('Lista de fontes', 'Fonte, data e link de cada informação usada (links dos veículos permitidos e fontes oficiais)',
               'fontes citadas ao longo do relatório'), tf]
# Money Times e Seu Dinheiro ficam sinalizados: ver lacunas
doc = BaseDocTemplate(OUT, pagesize=(PW, PH), leftMargin=FR_X, rightMargin=28, topMargin=60, bottomMargin=34,
                      title=f'Advogado do Diabo: análise semanal de {DATA_REL}', author='advogado-do-diabo (projeto de código aberto)')
doc.addPageTemplates([PageTemplate(id='p', frames=[Frame(FR_X, FR_Y, FR_W, FR_H, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPageEnd=deco)])
doc.build(story)
print('PDF gerado:', OUT)
print('Figuras ausentes:', sorted(set(FIGS_MISSING)))
