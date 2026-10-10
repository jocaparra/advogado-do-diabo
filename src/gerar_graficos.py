import json, os, sys, textwrap, datetime as dt
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates, matplotlib.ticker
from matplotlib.patches import Patch, Rectangle
from matplotlib.lines import Line2D

import carteira as C

D = C.pasta_semana() + os.sep
G = D + "graficos" + os.sep
os.makedirs(G, exist_ok=True)
L = lambda f, pad=None: C.ler(D + f, pad)
xp = C.ler(C.arquivo_xp(D.rstrip(os.sep)))
pr, ma, ca, ri, sy = L("precos.json"), L("macro.json"), L("casas.json"), L("risco.json"), L("sintese.json")
TX = L("textos.json", {})
PAR = {"corte_compra": 5.8, "min_casas_consenso": 3, **TX.get("parametros", {})}
FIGT = TX.get("figuras", {})
POL = TX.get("politica_fontes", {})

plt.rcParams.update({
    "font.family": ["Arial", "DejaVu Sans"], "font.size": 10,
    "axes.edgecolor": "#BBBBBB", "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": False, "savefig.facecolor": "white", "figure.facecolor": "white",
})
GOLD, BLACK, GREY, LGREY = "#FFB800", "#000000", "#7F7F7F", "#F0F0F0"
GREEN, AMBER, RED = "#2E7D32", "#F9A825", "#C62828"
ACT = {"comprar": GREEN, "aguardar": AMBER, "evitar": RED}
A_, M_, D_ = C.data_semana(D)
HOJE = dt.date(A_, M_, D_)
DATA_BR = HOJE.strftime("%d/%m/%Y")
DADOS_XP = C.data_br(xp["dados_ate"])
MES_XP = C.mes_extenso(xp["data_relatorio"])
CUT = f"Data de corte: {DATA_BR}."
ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
_dx = dt.date.fromisoformat(xp["dados_ate"])
CHAVE_MES = f"{ABREV[_dx.month - 1]}-{_dx.strftime('%y')}"


def n(x, d=1, sign=False):
    s = f"{x:+.{d}f}" if sign else f"{x:.{d}f}"
    return s.replace(".", ",")


def base(num, desc, fonte, h=7.5):
    fig = plt.figure(figsize=(13.333, h))
    fig.text(0.02, 0.955 if h < 8 else 0.96, f"Figura {num}: {desc}", fontsize=16, fontweight="bold", color=BLACK, va="center")
    fig.add_artist(Line2D([0.02, 0.98], [0.925 if h < 8 else 0.93] * 2, color=GOLD, lw=2.5))
    fig.text(0.02, 0.025, f"Fonte: {fonte} {CUT}", fontsize=9, color=GREY, va="center")
    return fig


def grid(ax, axis="y"):
    ax.grid(axis=axis, color="#DDDDDD", lw=0.7)
    ax.set_axisbelow(True)


def save(fig, num, dados):
    fig.savefig(G + f"fig{num}.png", dpi=200)
    json.dump(dados, open(G + f"fig{num}_dados.json", "w"), ensure_ascii=False, indent=1)
    plt.close(fig)


rank = sy["ranking"]
order = [r["ticker"] for r in rank]
P = pr["acoes"]
pct = lambda s: float(str(s).replace("%", ""))
num = lambda v: isinstance(v, (int, float))

# ---------------- Figura 1
fig = base(1, "Retorno da carteira XP contra o Ibovespa por período e Ibovespa em base 100 (12 meses)",
           f"XP Research, Carteira Top Ações XP {MES_XP} (retornos até {DADOS_XP}, incluem dividendos); Yahoo Finance, Ibovespa (série diária até {DATA_BR}).")
ax = fig.add_axes([0.06, 0.20, 0.50, 0.66])
ser = pr["ibovespa"]["serie"]
dts = [dt.date.fromisoformat(s[0]) for s in ser]
b100 = [s[1] / ser[0][1] * 100 for s in ser]
ax.plot(dts, b100, color=GREY, lw=2.2, label=f"Ibovespa, base 100 em {dts[0].strftime('%d/%m/%Y')}")
ax.scatter([dts[-1]], [b100[-1]], color=GREY, zorder=5)
ax.annotate(f"{n(b100[-1])} ({dts[-1].strftime('%d/%m/%Y')})", (dts[-1], b100[-1]), xytext=(-8, 8), textcoords="offset points", ha="right", fontsize=10, fontweight="bold", color=BLACK)
ax.axhline(100, color="#BBBBBB", lw=0.8)
grid(ax)
ax.set_ylabel(f"Índice (base 100 = {dts[0].strftime('%d/%m/%Y')})")
ax.set_xlabel("Data (fechamento diário)")
ax.set_ylim(80, max(b100) + 12)
ax.text(0.02, 0.97, "Linha da carteira XP não gerada: a série diária da carteira não foi\nverificada (o PDF da XP traz só retornos por período e o ponto final).",
        transform=ax.transAxes, va="top", fontsize=9.5, color=BLACK, bbox=dict(boxstyle="round,pad=0.5", fc=LGREY, ec="none"))
ax.legend(loc="lower right", frameon=False, fontsize=10)
ax.set_title("Ibovespa em 12 meses", fontsize=11, loc="left", color=GREY)
ret = xp["carteira"]["retornos"]
_ini = xp["carteira"].get("inicio_carteira", "").split(" ")[0].replace("-", "/")
per = [(f"Mês ({CHAVE_MES.replace('-', '/')})", ret["mensal"][CHAVE_MES]), (str(_dx.year), ret[str(_dx.year)]), ("12 meses", ret["ultimos_12m"]),
       (f"Desde o início\n({_ini})", ret["desde_inicio"])]
ax2 = fig.add_axes([0.62, 0.20, 0.36, 0.66])
xs = np.arange(len(per)); w = 0.36
c_ = [p[1]["carteira"] for p in per]; i_ = [p[1]["ibovespa"] for p in per]
b1 = ax2.bar(xs - w / 2, c_, w, color=GOLD, label="Carteira XP")
b2 = ax2.bar(xs + w / 2, i_, w, color=GREY, label="Ibovespa")
for bars in (b1, b2):
    for b in bars:
        ax2.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.8, n(b.get_height()) + "%", ha="center", fontsize=9.5, fontweight="bold")
ax2.set_xticks(xs); ax2.set_xticklabels([p[0] for p in per], fontsize=9.5)
ax2.set_ylabel("Retorno (%)"); ax2.set_ylim(min(0, min(c_ + i_) * 1.2), max(c_ + i_) * 1.15); grid(ax2)
ax2.legend(loc="upper left", frameon=False, fontsize=10)
ax2.set_title(f"Retornos por período (até {DADOS_XP})", fontsize=11, loc="left", color=GREY)
fig.text(0.62, 0.09, f"Semana: não verificado (o PDF da XP não traz).\nBases diferentes: o Ibovespa de 12 meses ao lado (série até\n{dts[-1].strftime('%d/%m')}) não é comparável com o retorno de 12 meses\nda XP (até {DADOS_XP[:5]}, {n(ret['ultimos_12m']['carteira'])}%).", fontsize=9, color=GREY, va="center")
save(fig, 1, {"retornos_periodo_xp_json": {"mes": ret["mensal"][CHAVE_MES], "ano": ret[str(_dx.year)], "12m": ret["ultimos_12m"], "desde_inicio": ret["desde_inicio"], "semana": "não verificado"},
              "ibovespa_base100_12m": [[d.isoformat(), round(v, 2), s[1]] for d, v, s in zip(dts, b100, ser)],
              "carteira_serie": "não gerada: série diária da carteira não verificada (xp.json traz só o ponto final)",
              "fonte": ["xp.json carteira.retornos", "precos.json ibovespa.serie"], "data_corte": HOJE.isoformat()})

# ---------------- Figura 2
fig = base(2, f"Ranking das {len(rank)} ações por nota do analista, cor pela ação sugerida e certeza",
           "Síntese do analista (sintese.json), a partir de XP Research, Yahoo Finance, InfoMoney e casas de análise. A nota serve para ordenar e não é probabilidade.")
ax = fig.add_axes([0.23, 0.13, 0.62, 0.72])
ys = np.arange(len(rank))[::-1]
for y, r in zip(ys, rank):
    ax.barh(y, r["nota"], color=ACT[r["acao_sugerida"]], height=0.66)
    ax.text(r["nota"] + 0.08, y, n(r["nota"], 2), va="center", fontsize=10, fontweight="bold", zorder=7, bbox=dict(fc="white", ec="none", pad=0.8))
    ax.text(10.15, y, r["certeza"], va="center", fontsize=10, color=BLACK)
ax.set_yticks(ys); ax.set_yticklabels([f"{r['posicao']}. {r['ticker']} ({r['setor']})" for r in rank], fontsize=10)
ax.set_xlim(0, 10); ax.set_ylim(-0.7, len(rank) - 0.3)
ax.set_xlabel("Nota do analista (0 a 10)"); grid(ax, "x")
CORTE = PAR["corte_compra"]
ax.axvline(CORTE, color=BLACK, ls="--", lw=1.4)
ax.text(CORTE + 0.05, len(rank) - 0.35, f"Corte de compra: nota {n(CORTE)}", fontsize=10, fontweight="bold", va="bottom")
ax.text(10.15, len(rank) - 0.35, "Certeza", fontsize=10, fontweight="bold", va="bottom")
ax.legend(handles=[Patch(color=GREEN, label="Comprar"), Patch(color=AMBER, label="Aguardar"), Patch(color=RED, label="Evitar"), Line2D([0], [0], color=BLACK, ls="--", label=f"Corte de compra ({n(CORTE)})")],
          loc="lower right", frameon=False, fontsize=10, bbox_to_anchor=(1.0, 0.0))
_ab = [r for r in rank if r["acao_sugerida"] != "comprar" and CORTE - r["nota"] <= 0.3]
_msg = f"Comprar exige nota a partir de {n(CORTE)}\ne upside ajustado positivo."
if _ab:
    _r = max(_ab, key=lambda r: r["nota"])
    _msg += f"\n{_r['ticker']} ({n(_r['nota'], 2)}) fica {n(CORTE - _r['nota'], 2)} abaixo\ndo corte e por isso é {_r['acao_sugerida']}."
ax.text(0.62, 0.52, _msg, fontsize=10, va="center", transform=ax.transAxes, bbox=dict(boxstyle="round,pad=0.6", fc=LGREY, ec="none"))
fig.text(0.98, 0.06, "A nota serve para ordenar e não é probabilidade.", fontsize=10, fontweight="bold", ha="right", va="center")
save(fig, 2, [{k: r[k] for k in ["posicao", "ticker", "setor", "nota", "acao_sugerida", "certeza"]} for r in rank])

# ---------------- Figura 3
fig = base(3, "Upside até o alvo da XP, até a mediana das casas e ajustado pelo analista",
           "XP Research (alvos), InfoMoney e casas de análise (medianas), Yahoo Finance (preço), síntese do analista (ajustado, projeção).")
ax = fig.add_axes([0.075, 0.20, 0.52, 0.67])
ys = np.arange(len(rank))[::-1]
h = 0.26
f3 = []
for y, r in zip(ys, rank):
    vals = [(r["upside_xp_pct"], GOLD, None, ""), (r["upside_mediana_pct"], GREY, "///" if r["n_alvos_mediana"] < 3 else None, f" (n={r['n_alvos_mediana']})"), (r["upside_ajustado_pct"], BLACK, None, "")]
    for k, (v, c, ht, suf) in enumerate(vals):
        yy = y + (1 - k) * h
        if num(v):
            ax.barh(yy, v, height=h * 0.92, color=c, hatch=ht, edgecolor="white" if ht else c, lw=0)
            ax.text(v + (0.8 if v >= 0 else -0.8), yy, n(v, 1, True) + "%" + (suf if k == 1 else ""), va="center", ha="left" if v >= 0 else "right", fontsize=9)
        else:
            ax.text(0.8, yy, "mediana não verificada", va="center", fontsize=9, color=GREY)
    f3.append({"ticker": r["ticker"], "preco_atual": r["preco_atual"], "data_cotacao": r["data_cotacao"], "preco_alvo_xp": r["preco_alvo_xp"], "upside_xp_pct": r["upside_xp_pct"],
               "mediana_casas": r["mediana_casas"], "n_alvos_mediana": r["n_alvos_mediana"], "upside_mediana_pct": r["upside_mediana_pct"], "upside_ajustado_pct": r["upside_ajustado_pct"]})
ax.set_yticks(ys); ax.set_yticklabels(order, fontsize=10, fontweight="bold")
_vs = [v for r in rank for v in (r["upside_xp_pct"], r["upside_mediana_pct"], r["upside_ajustado_pct"]) if num(v)]
ax.set_ylim(-0.6, len(rank) - 0.4); ax.set_xlim(min(-10, min(_vs) - 14), max(_vs) + 16)
ax.axvline(0, color=BLACK, lw=0.9); grid(ax, "x")
ax.set_xlabel(f"Upside sobre o preço atual de {DATA_BR} (%)")
ax.legend(handles=[Patch(color=GOLD, label="Até o alvo da XP"), Patch(facecolor=GREY, label="Até a mediana das casas"), Patch(facecolor=GREY, hatch="///", edgecolor="white", label="Mediana de menos de 3 alvos (n)"), Patch(color=BLACK, label="Ajustado pelo analista (projeção)")],
          loc="upper center", bbox_to_anchor=(0.5, -0.10), ncol=2, frameon=False, fontsize=9.5)
at = fig.add_axes([0.62, 0.20, 0.365, 0.67], sharey=ax)
at.set_xlim(0, 1); at.axis("off")
cols = [(0.10, "Preço atual\n(R$)"), (0.34, "Alvo XP\n(R$)"), (0.60, "Mediana casas\n(R$, n)"), (0.88, "Cotação")]
for i, (y, r) in enumerate(zip(ys, rank)):
    if i % 2 == 0:
        at.add_patch(Rectangle((0, y - 0.5), 1, 1, color=LGREY, zorder=0))
    med = r["mediana_casas"]
    row = [n(r["preco_atual"], 2), n(r["preco_alvo_xp"], 2), (n(med, 2) + f" ({r['n_alvos_mediana']})") if num(med) else "n/v", r["data_cotacao"][8:] + "/" + r["data_cotacao"][5:7] + "/" + r["data_cotacao"][:4]]
    for (x, _), t in zip(cols, row):
        at.text(x + 0.06, y, t, ha="center", va="center", fontsize=9)
at.add_patch(Rectangle((0, len(rank) - 0.5), 1, 0.9, color=GOLD, clip_on=False))
for x, t in cols:
    at.text(x + 0.06, len(rank) - 0.05, t, ha="center", va="center", fontsize=9, fontweight="bold", clip_on=False)
at.set_ylim(ax.get_ylim())
fig.text(0.62, 0.13, FIGT.get("fig3", {}).get("nota", "n/v = não verificado. Medianas de 1 ou 2 alvos não são consenso."), fontsize=9, color=GREY, va="center")
save(fig, 3, f3)

# ---------------- Figura 4
import regras as R
POLR = R.parametros(TX)
FORA_FONTES, FORA_CASAS = POLR["fontes_fora_da_contagem_de_casas"], POLR["casas_fora_da_contagem"]
MINC = POLR["min_casas_consenso"]
CONTAGEM = {t: R.contagem_ratings(v["casas"], POLR) for t, v in ca["tickers"].items()}
f4 = {}
for t in order:
    ct = CONTAGEM[t]
    f4[t] = {"compra": ct["compra"], "neutro": ct["neutro"], "venda": ct["venda"], "n_casas": ct["n_casas"],
             "rating_xp": ca["tickers"][t]["xp"]["rating"], "casas": ct["casas"]}
ok = [t for t in order if f4[t]["n_casas"] >= MINC]
ins = [t for t in order if f4[t]["n_casas"] < MINC]
fig = base(4, f"Ratings das casas de análise: compra, neutro e venda (só tickers com {MINC} ou mais casas verificadas)",
           "casas de análise verificadas em fontes da lista permitida (casas.json) e rating da XP (xp.json).")
ax = fig.add_axes([0.10, 0.36, 0.55, 0.50])
ys = np.arange(len(ok))[::-1]
_mx = max([f4[t]["n_casas"] for t in ok] + [3])
XPX = _mx + 0.35
for y, t in zip(ys, ok):
    left = 0
    for k, c in (("compra", GREEN), ("neutro", AMBER), ("venda", RED)):
        v = f4[t][k]
        if v:
            ax.barh(y, v, left=left, color=c, height=0.5)
            ax.text(left + v / 2, y, str(v), ha="center", va="center", color="white", fontsize=12, fontweight="bold")
        left += v
    ax.scatter([XPX], [y], marker="D", s=170, color=GOLD, edgecolor=BLACK, zorder=5)
    ax.text(XPX + 0.2, y, f"XP: {f4[t]['rating_xp']}", va="center", fontsize=10.5, fontweight="bold")
    ax.text(0.0, y - 0.32, "Casas: " + ", ".join(f4[t]["casas"]), fontsize=9, color=GREY, va="top")
ax.set_yticks(ys); ax.set_yticklabels(ok, fontsize=12, fontweight="bold")
ax.set_xlim(0, _mx + 1.6); ax.set_ylim(-0.9, len(ok) - 0.4)
ax.set_xticks(range(_mx + 1)); ax.set_xlabel("Número de casas verificadas"); grid(ax, "x")
ax.legend(handles=[Patch(color=GREEN, label="Compra"), Patch(color=AMBER, label="Neutro"), Patch(color=RED, label="Venda"), Line2D([0], [0], marker="D", color="w", markerfacecolor=GOLD, markeredgecolor=BLACK, markersize=10, label="Rating da XP")],
          loc="upper right", frameon=False, fontsize=10, ncol=4, bbox_to_anchor=(1.0, 1.12))
txt = f"Dado insuficiente (menos de {MINC} casas verificadas): " + "; ".join(f"{t} ({f4[t]['n_casas']})" for t in ins) + "."
fig.text(0.02, 0.27, "\n".join(textwrap.wrap(txt, 150)), fontsize=10, va="top", color=BLACK, bbox=dict(boxstyle="round,pad=0.6", fc=LGREY, ec="none"))
if FIGT.get("fig4", {}).get("nota"):
    fig.text(0.02, 0.10, FIGT["fig4"]["nota"], fontsize=9, color=GREY, va="center")
save(fig, 4, {"criterio": f"casas verificadas, sem {FORA_FONTES + FORA_CASAS}; mínimo de {MINC} casas", "por_ticker": f4})

# ---------------- Figura 5
fig = base(5, "Retorno de 5 dias, 30 dias e 2026 por ação contra o Ibovespa",
           f"Yahoo Finance (fechamento sem ajuste por proventos, B3) via precos.json; Ibovespa ao fechamento de {DATA_BR}.")
per5 = [("ret_5d", "5 dias"), ("ret_30d", "30 dias"), ("ret_ano", f"No ano ({HOJE.year})")]
f5 = {"ibovespa": {k: pct(pr["ibovespa"][k]) for k, _ in per5}, "acoes": {}}
for i, (k, nome) in enumerate(per5):
    ax = fig.add_axes([0.065, 0.66 - i * 0.27, 0.915, 0.19])
    vals = [pct(P[t][k]) for t in order]
    ib = pct(pr["ibovespa"][k])
    NT = len(order)
    bars = ax.bar(range(NT), vals, color=GOLD, width=0.62)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + (1.5 if v >= 0 else -1.5), n(v, 1, True) + "%", ha="center", va="bottom" if v >= 0 else "top", fontsize=9, fontweight="bold", color=GREEN if v >= 0 else RED, zorder=7, bbox=dict(fc="white", ec="none", pad=0.6))
    ax.axhline(ib, color=GREY, ls="--", lw=2)
    ax.set_xlim(-0.6, NT + 1.3)
    ax.text(NT + 1.2, ib, f"Ibovespa {n(ib, 1, True)}%", ha="right", va="bottom", fontsize=9.5, fontweight="bold", color=GREY, bbox=dict(fc="white", ec="none", pad=1))
    ax.axhline(0, color=BLACK, lw=0.8)
    ax.set_xticks(range(NT)); ax.set_xticklabels(order if i == 2 else [""] * NT, fontsize=10, fontweight="bold")
    ax.set_ylabel(f"{nome} (%)", fontsize=10)
    lo, hi = min(vals + [ib, 0]), max(vals + [ib])
    ax.set_ylim(lo - (hi - lo) * 0.16, hi + (hi - lo) * 0.18); grid(ax)
    for t in order: f5["acoes"].setdefault(t, {})[k] = pct(P[t][k])
fig.legend(handles=[Patch(color=GOLD, label="Retorno da ação"), Line2D([0], [0], color=GREY, ls="--", lw=2, label="Ibovespa no mesmo período")], loc="upper right", bbox_to_anchor=(0.98, 0.915), frameon=False, fontsize=10, ncol=2)
save(fig, 5, f5)

# ---------------- Figura 6
fig = base(6, "Upside ajustado contra volatilidade de 90 pregões, tamanho do ponto pela certeza",
           "Síntese do analista (upside ajustado, projeção), risco.json (volatilidade anualizada de 90 pregões, calculada sobre Yahoo Finance).")
ax = fig.add_axes([0.07, 0.14, 0.70, 0.74])
SZ = {"alta": 520, "média": 300, "baixa": 140}
pts = []
for r in rank:
    vol = ri["tabela_por_ticker"][r["ticker"]]["vol_90pregoes_anual_pct"]
    pts.append((r["ticker"], vol, r["upside_ajustado_pct"], r["certeza"], r["acao_sugerida"]))
    ax.scatter(vol, r["upside_ajustado_pct"], s=SZ[r["certeza"]], color=ACT[r["acao_sugerida"]], edgecolor=BLACK, lw=0.8, alpha=0.9, zorder=3)
ax.axhline(0, color=BLACK, lw=0.9)
_vx = [p[1] for p in pts]; _vy = [p[2] for p in pts]
ax.set_xlim(min(_vx) - 3, max(_vx) + 3); ax.set_ylim(min(_vy + [0]) - 8, max(_vy) + 8); grid(ax, "both")
ax.set_xlabel("Volatilidade anualizada de 90 pregões (%)"); ax.set_ylabel("Upside ajustado (%)")
fig.canvas.draw()
rend = fig.canvas.get_renderer()
placed = []
import math
dirs = [(1, 1, "left", "bottom"), (1, -1, "left", "top"), (-1, 1, "right", "bottom"), (-1, -1, "right", "top"), (0, 1, "center", "bottom"), (0, -1, "center", "top"), (1, 0, "left", "center"), (-1, 0, "right", "center")]
rad = lambda c: math.sqrt(SZ[c]) / 2 * 100 / 72 + 3
dots = [(ax.transData.transform((p[1], p[2])), rad(p[3])) for p in pts]
axbb = ax.get_window_extent(rend)
placed = []
FORCE = {k: tuple(v) for k, v in FIGT.get("fig6", {}).get("posicoes_forcadas", {}).items()}
for k, (t, x, y, c, a) in enumerate(pts):
    best = None
    for dist in (1.0, 1.6, 2.4):
        for dx, dy, ha, va in ([FORCE[t]] if t in FORCE else dirs):
            rp = math.sqrt(SZ[c]) / 2 + 3
            d = rp * dist
            nrm = math.hypot(dx, dy)
            tx = ax.annotate(f"{t} ({n(y, 1, True)}%)", (x, y), xytext=(dx / nrm * d, dy / nrm * d), textcoords="offset points", ha=ha, va=va, fontsize=9.5, fontweight="bold", zorder=6)
            bb = tx.get_window_extent(rend).expanded(1.03, 1.08)
            clash = sum(bb.overlaps(q) for q in placed)
            for (cx, cy), rr in dots:
                if bb.x0 - rr < cx < bb.x1 + rr and bb.y0 - rr < cy < bb.y1 + rr: clash += 1
            out = bb.x0 < axbb.x0 or bb.x1 > axbb.x1 or bb.y0 < axbb.y0 or bb.y1 > axbb.y1
            score = clash * 10 + (50 if out else 0) + dist
            if best is None or score < best[0]:
                if best: best[1].remove()
                best = (score, tx, bb)
            else:
                tx.remove()
    placed.append(best[2])
fig.legend(handles=[Line2D([0], [0], marker="o", color="w", markerfacecolor=ACT[k], markeredgecolor=BLACK, markersize=11, label=k.capitalize()) for k in ACT], title="Ação sugerida", loc="upper left", bbox_to_anchor=(0.79, 0.86), frameon=False, fontsize=10, title_fontsize=10)
fig.legend(handles=[Line2D([0], [0], marker="o", color="w", markerfacecolor="#CCCCCC", markeredgecolor=BLACK, markersize=m, label=l) for l, m in (("Certeza alta", 20), ("Certeza média", 15), ("Certeza baixa", 10))], title="Tamanho do ponto", loc="upper left", bbox_to_anchor=(0.79, 0.68), frameon=False, fontsize=10, title_fontsize=10, labelspacing=1.0)
fig.text(0.79, 0.38, "Quanto mais à direita, maior o risco.\nQuanto mais alto, maior a projeção\nde ganho. O upside ajustado é\nprojeção do analista, não fato.", fontsize=10, va="top", bbox=dict(boxstyle="round,pad=0.6", fc=LGREY, ec="none"))
save(fig, 6, [{"ticker": t, "vol_90pregoes_anual_pct": x, "upside_ajustado_pct": y, "certeza": c, "acao_sugerida": a} for t, x, y, c, a in pts])

# ---------------- Figura 7
setores = xp["setores"]
comprar = [r for r in rank if r["acao_sugerida"] == "comprar"]
wcomp = {s["setor"]: 0.0 for s in setores}
for r in comprar:
    if r["setor"] in wcomp: wcomp[r["setor"]] += 100.0 / len(comprar)
_cn = "+".join(r["ticker"] for r in comprar) or "nenhum"
fig = base(7, "Exposição setorial: Ibovespa, carteira XP e conjunto comprar do analista",
           f"XP Research (pesos de setor da carteira e do Ibovespa, PDF de {MES_XP}, base {DADOS_XP}) e síntese do analista (conjunto comprar: {', '.join(r['ticker'] for r in comprar) or 'nenhum'}).")
ax = fig.add_axes([0.07, 0.24, 0.90, 0.62])
xs = np.arange(len(setores)); w = 0.26
sv = [(s["peso_ibovespa"], s["peso_carteira"], wcomp[s["setor"]]) for s in setores]
for k, (nm, c) in enumerate((("Peso no Ibovespa", GREY), ("Peso na carteira XP", GOLD), (f"Peso no conjunto comprar ({_cn})", GREEN))):
    bars = ax.bar(xs + (k - 1) * w, [v[k] for v in sv], w * 0.92, color=c, label=nm)
    for b in bars:
        if b.get_height() > 0:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1, n(b.get_height()) + "%", ha="center", fontsize=9.5, fontweight="bold")
ax.set_xticks(xs); ax.set_xticklabels([s["setor"].replace("Tecnologia da Informação", "Tecnologia da\nInformação").replace("Utilidade Pública", "Utilidade\nPública").replace("Bens Industriais", "Bens\nIndustriais") for s in setores], fontsize=10)
ax.set_ylabel("Peso (% do total)"); ax.set_ylim(0, max(max(v) for v in sv) * 1.15 + 2); grid(ax)
ax.legend(loc="upper right", frameon=False, fontsize=10)
soma = sum(s["peso_ibovespa"] for s in setores)
fig.text(0.07, 0.13, f"Os setores do Ibovespa que não estão listados no PDF da XP não aparecem: os {len(setores)} setores mostrados somam {n(soma)}% do índice, e o restante ({n(100 - soma)}%) não está no gráfico.\n" + FIGT.get("fig7", {}).get("nota", ""), fontsize=9.5, color=GREY, va="center")
save(fig, 7, {"setores": [{"setor": s["setor"], "segmento": s["segmento"], "peso_ibovespa": s["peso_ibovespa"], "peso_carteira_xp": s["peso_carteira"], "peso_conjunto_comprar": wcomp[s["setor"]]} for s in setores],
              "soma_ibovespa_listado": round(soma, 1), "conjunto_comprar": [r["ticker"] for r in comprar]})

# ---------------- Figura 8
S = ma["figura_8_series"]
ind = {i["indicador"]: i for i in ma["indicadores"]}
EF8 = FIGT.get("fig8", {}).get("efeitos", {})
_pd = lambda k: EF8.get(k, "Efeito: não verificado.")
panels = [
    ("Selic meta (% a.a.)", S["selic_meta"], "Selic meta", "{:.2f}%", "step", _pd("Selic meta")),
    ("Dólar PTAX venda (R\\$/US\\$)", S["dolar_ptax"], "Dólar PTAX venda", "R$ {:.4f}", "line", _pd("Dólar PTAX venda")),
    ("Brent (US$/barril)", S["brent"], "Brent", "US$ {:.2f}", "line", _pd("Brent")),
    ("Ibovespa (pontos)", S["ibovespa"], "Ibovespa", "{:,.0f}", "line", _pd("Ibovespa")),
    ("Treasury 10 anos (% a.a.)", S["treasury10y"], "Treasury 10 anos", "{:.2f}%", "line", _pd("Treasury 10 anos")),
]
_p0, _p1 = (dt.date.fromisoformat(x) for x in S["periodo"].split(" a "))
_ticks = [_p0 + (_p1 - _p0) * k / 3 for k in range(4)]
fig = base(8, f"Painel macro dos últimos 3 meses ({_p0.strftime('%d/%m')} a {_p1.strftime('%d/%m/%Y')}) e efeito na carteira",
           "Banco Central (Selic, PTAX), Yahoo Finance (Brent, Ibovespa, Treasury), InfoMoney (fluxo estrangeiro); macro.json, seção figura_8_series.", h=8.4)
pos = [(0.045, 0.60), (0.37, 0.60), (0.695, 0.60), (0.045, 0.17), (0.37, 0.17), (0.695, 0.17)]
f8 = {}
for (x0, y0), p in zip(pos[:5], panels):
    ax = fig.add_axes([x0, y0 + 0.07, 0.275, 0.20])
    d = [dt.date.fromisoformat(a[0]) for a in p[1]]; v = [a[1] for a in p[1]]
    if p[4] == "step": ax.step(d, v, where="post", color=GOLD, lw=2.5)
    else: ax.plot(d, v, color=GOLD, lw=2.5)
    ax.scatter([d[-1]], [v[-1]], color=BLACK, zorder=5, s=25)
    ptb = lambda z: z.replace(",", "§").replace(".", ",").replace("§", ".")
    ax.annotate(ptb(p[3].format(v[-1])) + "\n(início\n" + ptb(p[3].format(v[0])) + ")", (d[-1], v[-1]), xytext=(7, 0), textcoords="offset points", ha="left", va="center", fontsize=9, fontweight="bold")
    ax.set_xlim(d[0] - dt.timedelta(days=2), d[-1] + dt.timedelta(days=36))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda val, pos_: ptb(f"{val:,.2f}" if abs(val) < 1000 else f"{val:,.0f}")))
    pad = (max(v) - min(v)) * 0.25
    ax.set_ylim(min(v) - pad, max(v) + pad)
    ax.set_xticks(_ticks)
    ax.set_xticklabels([t.strftime("%d/%m") for t in _ticks], fontsize=9)
    ax.tick_params(axis="y", labelsize=9); grid(ax)
    ax.set_title(p[0], fontsize=10.5, fontweight="bold", loc="left")
    fig.text(x0, y0 + 0.035, "\n".join(textwrap.wrap(p[5], 62)), fontsize=9, va="top", color=BLACK)
    f8[p[2]] = {"serie": p[1], "fonte": ind[p[2]]["fonte"], "variacao_3m": ind[p[2]].get("variacao_3m_pct", ind[p[2]].get("variacao_3m"))}
x0, y0 = pos[5]
ax = fig.add_axes([x0, y0 + 0.07, 0.275, 0.20])
fl = S["fluxo_estrangeiro_mensal_RS_bi"]
meses = [(k.capitalize(), v) for k, v in fl.items() if isinstance(v, (int, float))]
bars = ax.bar(range(len(meses)), [m[1] for m in meses], color=[RED if m[1] < 0 else GREEN for m in meses], width=0.5)
for b, m in zip(bars, meses):
    ax.text(b.get_x() + b.get_width() / 2, m[1] + (1.2 if m[1] >= 0 else -1.2), "R$ " + n(m[1], 2, True) + " bi", ha="center", va="bottom" if m[1] >= 0 else "top", fontsize=9.5, fontweight="bold")
ax.axhline(0, color=BLACK, lw=0.8); ax.set_xticks(range(len(meses))); ax.set_xticklabels([m[0] for m in meses], fontsize=9)
_fv = [m[1] for m in meses]; ax.set_ylim(min(_fv + [0]) * 1.25 - 1, max(_fv + [0]) * 1.4 + 2); ax.tick_params(axis="y", labelsize=9); grid(ax)
ax.set_title("Fluxo estrangeiro na B3 (R$ bilhões, mensal)", fontsize=10.5, fontweight="bold", loc="left")
fig.text(x0, y0 + 0.035, "\n".join(textwrap.wrap(_pd("fluxo"), 62)), fontsize=9, va="top")
f8["Fluxo estrangeiro mensal"] = {"R$ bi": fl, "serie_diaria": "não verificado"}
save(fig, 8, f8)

# ---------------- Figura 9
ant = C.semana_anterior(D.rstrip(os.sep))
if ant is None:
    fig = plt.figure(figsize=(13.333, 7.5))
    fig.text(0.02, 0.955, "Figura 9: Mudança de posição no ranking contra a semana anterior", fontsize=16, fontweight="bold", va="center")
    fig.add_artist(Line2D([0.02, 0.98], [0.925, 0.925], color=GOLD, lw=2.5))
    fig.add_artist(Rectangle((0.2, 0.33), 0.6, 0.30, transform=fig.transFigure, color=LGREY))
    fig.text(0.5, 0.52, "Primeira execução, sem comparação", fontsize=26, fontweight="bold", ha="center", va="center")
    fig.text(0.5, 0.42, "Não existe ranking da semana anterior para comparar.", fontsize=13, ha="center", va="center", color=GREY)
    fig.text(0.02, 0.025, f"Fonte: síntese do analista (sintese.json), sem histórico anterior. {CUT}", fontsize=9, color=GREY, va="center")
    save(fig, 9, {"status": "primeira execução, sem comparação", "ranking_atual": order})
else:
    pos_ant = {r["ticker"]: r for r in ant["ranking"]}
    fig = base(9, f"Mudança de posição no ranking contra a semana de {C.data_br(ant['data'])}",
               f"síntese do analista (sintese.json) e historico_carteira.json (semana de {C.data_br(ant['data'])}).")
    ax = fig.add_axes([0.20, 0.13, 0.60, 0.74])
    f9 = []
    for r in rank:
        a_ = pos_ant.get(r["ticker"])
        mov = (a_["posicao"] - r["posicao"]) if a_ else None
        f9.append({"ticker": r["ticker"], "posicao_atual": r["posicao"], "posicao_anterior": a_["posicao"] if a_ else None,
                   "mudanca": mov, "nota_atual": r["nota"], "nota_anterior": a_["nota"] if a_ else None,
                   "acao_atual": r["acao_sugerida"], "acao_anterior": a_["acao_sugerida"] if a_ else None})
    ys = np.arange(len(rank))[::-1]
    for y, f in zip(ys, f9):
        mov = f["mudanca"]
        cor = GREY if mov in (0, None) else (GREEN if mov > 0 else RED)
        ax.barh(y, mov or 0, color=cor, height=0.6)
        rotulo = "novo no ranking" if mov is None else (f"{mov:+d}".replace("-", "−") + " posições" if mov else "sem mudança")
        ax.text((mov or 0) + (0.15 if (mov or 0) >= 0 else -0.15), y, rotulo, va="center", ha="left" if (mov or 0) >= 0 else "right", fontsize=9.5, fontweight="bold")
        if f["acao_anterior"] and f["acao_anterior"] != f["acao_atual"]:
            ax.text(0.99, y, f"{f['acao_anterior']} → {f['acao_atual']}", transform=ax.get_yaxis_transform(), va="center", ha="right", fontsize=9.5, color=BLACK)
    ax.set_yticks(ys); ax.set_yticklabels([f"{f['posicao_atual']}. {f['ticker']}" for f in f9], fontsize=10)
    _m = max([abs(f["mudanca"] or 0) for f in f9] + [1])
    ax.set_xlim(-_m - 3, _m + 4); ax.axvline(0, color=BLACK, lw=0.9); grid(ax, "x")
    ax.set_xlabel("Posições ganhas (+) ou perdidas (−) contra a semana anterior")
    save(fig, 9, {"semana_anterior": ant["data"], "por_ticker": f9})

# ---------------- Figura 10
F10 = FIGT.get("fig10", {})
d0, d1 = HOJE, HOJE + dt.timedelta(days=28)
_ev = []
for e in ma.get("eventos_4_semanas", []):
    try:
        d_ = dt.date.fromisoformat(e["data"][:10])
    except (ValueError, KeyError):
        continue
    if d0 <= d_ <= d1 and e.get("certeza") in ("alta", "média"):
        _ev.append((d_, e))
_ev.sort(key=lambda x: x[0])
fig = base(10, f"Calendário de catalisadores de {d0.strftime('%d/%m')} a {d1.strftime('%d/%m/%Y')} e eventos sem data verificada",
           "macro.json (eventos_4_semanas, só os de certeza alta ou média) e noticias.json. Eventos sem data confirmada ficam na lista ao lado.")
ax = fig.add_axes([0.05, 0.14, 0.52, 0.72])
ax.set_xlim(d0 - dt.timedelta(days=1), d1 + dt.timedelta(days=4)); ax.set_ylim(0, 10)
for s_ in ("left", "top", "right"): ax.spines[s_].set_visible(False)
ax.set_yticks([])
wk = [d0 + dt.timedelta(days=7 * i) for i in range(5)]
ax.set_xticks(wk); ax.set_xticklabels([d.strftime("%d/%m") for d in wk], fontsize=10)
ax.grid(axis="x", color="#DDDDDD"); ax.set_axisbelow(True)
ax.set_xlabel(f"Data (semanas a partir de {d0.strftime('%d/%m/%Y')})")
ax.axvline(d0, color=GREY, lw=1.5, ls=":"); ax.text(d0, 9.6, " Hoje", fontsize=9.5, color=GREY, ha="left")
faixa = F10.get("destaque_faixa")
if faixa:
    ax.add_patch(Rectangle((matplotlib.dates.date2num(dt.date.fromisoformat(faixa[0])), 0), faixa[1], 10, color=GOLD, alpha=0.22, zorder=0))
alturas = [7.2, 3.2, 5.2, 1.6, 8.4, 4.2]
com_data = []
for k, (d_, e) in enumerate(_ev):
    chave = d_.isoformat()
    y = alturas[k % len(alturas)]
    ha = "right" if (d_ - d0).days > 14 and k % 2 == 0 else "left"
    titulo = F10.get("rotulos", {}).get(chave) or f"{d_.strftime('%d/%m')}: " + "\n".join(textwrap.wrap(e["evento"], 34))
    afeta = F10.get("afeta", {}).get(chave, "")
    ax.vlines(d_, 0, y, color=BLACK, lw=2)
    ax.scatter([d_], [y], s=130, color=GOLD, edgecolor=BLACK, zorder=5)
    off = -12 if ha == "right" else 12
    ax.annotate(titulo, (d_, y), xytext=(off, 10), textcoords="offset points", ha=ha, va="bottom", fontsize=10.5, fontweight="bold")
    if afeta:
        ax.annotate(afeta, (d_, y), xytext=(off, -6), textcoords="offset points", ha=ha, va="top", fontsize=9.5, color=BLACK)
    com_data.append({"data": chave, "evento": e["evento"], "afeta": afeta, "fonte": e.get("fonte", "")})
ax.text(d0 + dt.timedelta(days=1), 0.5, f"Só {len(_ev)} evento(s) com data verificada dentro da janela.", fontsize=9.5, color=GREY)
_h = [Line2D([0], [0], marker="o", color="w", markerfacecolor=GOLD, markeredgecolor=BLACK, markersize=11, label="Evento com data verificada")]
if faixa:
    _h.append(Patch(color=GOLD, alpha=0.22, label=f"Dias do evento destacado ({faixa[2]})"))
ax.legend(handles=_h, loc="upper left", bbox_to_anchor=(0, 0.93), frameon=False, fontsize=10)
box = fig.add_axes([0.61, 0.14, 0.37, 0.72]); box.axis("off")
box.add_patch(Rectangle((0, 0), 1, 1, color=LGREY, transform=box.transAxes))
lista = []
if F10.get("sem_data"):
    lista += [("Sem data verificada (sem posição no eixo)", None)] + [(t, 1) for t in F10["sem_data"]]
if F10.get("fora_janela"):
    lista += [("Fora da janela de 4 semanas", None)] + [(t, 1) for t in F10["fora_janela"]]
yy = 0.97
for t, k in lista:
    if k is None:
        if t.startswith("Fora"): yy -= 0.03
        box.text(0.04, yy, t, transform=box.transAxes, fontsize=10.5, fontweight="bold", va="top"); yy -= 0.055
    else:
        w_ = textwrap.wrap(t, 56)
        box.text(0.06, yy, "\n".join(w_), transform=box.transAxes, fontsize=9.5, va="top")
        yy -= 0.033 * len(w_) + 0.02
save(fig, 10, {"com_data_verificada": com_data, "sem_data_verificada": [l[0] for l in lista if l[1]]})

# ---------------- frases
fr = TX.get("frases_figuras", {})
json.dump(fr, open(G + "frases_leitura.json", "w"), ensure_ascii=False, indent=1)
print("figuras geradas em", G)
