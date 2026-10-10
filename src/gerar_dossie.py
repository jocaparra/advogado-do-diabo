"""Dossiê por ação: indicadores da CVM, histórico, valuation por cenários e checklist setorial.

uso: python src/gerar_dossie.py <pasta_da_semana>

Entradas: fundamentos_cvm.json (obrigatório), precos.json, sintese.json, casas.json, dossie_qualitativo.json
(opcional, escrito pelo agente fundamentos), dados/perfis_setoriais.json e dados/premissas_valuation.json.
Saídas: dossie.json e graficos/dossie_TICKER.png (histórico e faixa de valuation contra preço, alvo XP e casas).
"""
import json
import os
import sys

import carteira as C
import regras as R
import valuation as V

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _perfil(ticker, perfis, cad_setor=''):
    pid = perfis['tickers'].get(ticker, 'generico')
    return pid, perfis['perfis'][pid]


def construir(pasta):
    cv = C.ler(os.path.join(pasta, 'fundamentos_cvm.json'))
    pr = C.ler(os.path.join(pasta, 'precos.json'))
    sy = C.ler(os.path.join(pasta, 'sintese.json'), {})
    ca = C.ler(os.path.join(pasta, 'casas.json'), {})
    ql = C.ler(os.path.join(pasta, 'dossie_qualitativo.json'), {})
    perfis = C.ler(os.path.join(RAIZ, 'dados', 'perfis_setoriais.json'))
    prem = C.ler(os.path.join(RAIZ, 'dados', 'premissas_valuation.json'))
    rk = {r['ticker']: r for r in sy.get('ranking', [])}
    saida = {'data': cv['data_coleta'], 'fonte': 'fundamentos_cvm.json (CVM), precos.json, premissas em dados/premissas_valuation.json',
             'premissas': {k: prem[k] for k in ('horizonte_anos', 'cenarios', 'grade')}, 'tickers': {}}
    for t, v in cv['tickers'].items():
        pid, perfil = _perfil(t, perfis)
        item = {'ticker': t, 'empresa': v.get('nome'), 'perfil': {'id': pid, 'nome': perfil['nome']}, 'situacao': v['situacao'],
                'preco': pr['acoes'].get(t, {}).get('preco_atual'), 'data_cotacao': pr['acoes'].get(t, {}).get('data_cotacao')}
        r = rk.get(t, {})
        item['referencias'] = {'alvo_xp': R.num(r.get('preco_alvo_xp')), 'mediana_casas': R.num(r.get('mediana_casas')),
                               'n_alvos_mediana': r.get('n_alvos_mediana'), 'nota': r.get('nota'), 'acao': r.get('acao_sugerida')}
        casas_alvos = [c['preco_alvo'] for c in ca.get('tickers', {}).get(t, {}).get('casas', [])
                       if c.get('situacao') == 'verificada' and R.num(c.get('preco_alvo')) is not None and c.get('moeda', 'R$') == 'R$']
        item['referencias']['faixa_alvos_casas'] = [min(casas_alvos), max(casas_alvos)] if casas_alvos else None
        if v['situacao'] != 'ok':
            item['valuation'] = {'status': 'indisponivel', 'motivo': v.get('motivo', 'sem demonstrações na CVM')}
            item['indicadores'] = {}
            item['historico_anual'] = []
        else:
            vals = v['valores']
            g = lambda k: (vals.get(k) or {}).get('valor')
            item['indicadores'] = {k: {'valor': x['valor'], 'unidade': x['unidade'], 'certeza': x['certeza']} for k, x in vals.items()}
            item['historico_anual'] = v['historico_anual']
            hist = v['historico_anual']
            cagr = None
            if len(hist) >= 3 and hist[0].get('receita') and hist[-1].get('receita') and hist[0]['receita'] > 0:
                n = hist[-1]['ano'] - hist[0]['ano']
                cagr = (hist[-1]['receita'] / hist[0]['receita']) ** (1 / n) - 1 if n > 0 else None
            item['valuation'] = V.avaliar(g('lucro_liquido_12m'), hist, g('roe_12m'), g('valor_de_mercado'), item['preco'],
                                          g('p_vp'), perfil, prem, cagr)
            item['valuation']['cagr_receita_pct'] = cagr * 100 if cagr is not None else None
            item['avisos_cvm'] = v.get('avisos', [])
        q = ql.get(t, {})
        item['checklist'] = []
        for c in perfil['checklist']:
            d = q.get(c['id'])
            ok = isinstance(d, dict) and d.get('valor') not in (None, '', 'não verificado') and d.get('fonte')
            item['checklist'].append({'id': c['id'], 'rotulo': c['rotulo'], 'unidade': c['unidade'],
                                      'valor': d['valor'] if ok else 'não verificado',
                                      'fonte': d.get('fonte') if ok else None, 'url': d.get('url') if ok else None,
                                      'data': d.get('data') if ok else None, 'certeza': d.get('certeza') if ok else None,
                                      'status': 'preenchido' if ok else 'pendente'})
        saida['tickers'][t] = item
    return saida


def figuras(d, pasta):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    GOLD, BLACK, GREY, GREEN, RED = '#FFB800', '#000000', '#7F7F7F', '#2E7D32', '#C62828'
    out = os.path.join(pasta, 'graficos')
    os.makedirs(out, exist_ok=True)
    pt = lambda x, n=1: f'{x:,.{n}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    for t, it in d['tickers'].items():
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.333, 5.2), gridspec_kw={'width_ratios': [1, 1.25]})
        fig.suptitle(f'Dossiê {t}: histórico e valuation', x=0.02, ha='left', fontsize=15, fontweight='bold')
        h = it['historico_anual']
        if h:
            anos = [str(x['ano']) for x in h]
            rec = [(x['receita'] or 0) / 1e9 for x in h]
            ll = [(x['lucro_liquido'] or 0) / 1e9 for x in h]
            xs = range(len(h))
            ax1.bar([i - 0.2 for i in xs], rec, 0.38, color=GREY, label='Receita')
            ax1.bar([i + 0.2 for i in xs], ll, 0.38, color=GOLD, label='Lucro líquido')
            for i in xs:
                ax1.text(i - 0.2, rec[i], pt(rec[i], 1), ha='center', va='bottom', fontsize=8)
                ax1.text(i + 0.2, ll[i], pt(ll[i], 1), ha='center', va='bottom' if ll[i] >= 0 else 'top', fontsize=8)
            ax1.set_xticks(list(xs)); ax1.set_xticklabels(anos)
            ax1.set_ylabel('R$ bilhões'); ax1.axhline(0, color=BLACK, lw=0.6); ax1.legend(frameon=False, fontsize=9)
            ax1.set_title('Exercícios anuais (CVM)', loc='left', fontsize=10, color=GREY)
        else:
            ax1.axis('off'); ax1.text(0.5, 0.5, 'Sem demonstrações na CVM', ha='center', va='center', fontsize=12, color=GREY)
        for s in ('top', 'right'):
            ax1.spines[s].set_visible(False)
        preco = it.get('preco')
        v = it['valuation']
        linhas = []
        if v.get('status') == 'ok':
            cs = v['cenarios']
            vals = [c.get('valor_justo_por_acao') for c in cs.values() if c.get('valor_justo_por_acao') is not None]
            if vals:
                linhas.append(('Valuation (bear a bull)', min(vals), max(vals), cs['base'].get('valor_justo_por_acao'), GOLD))
        fa = it['referencias'].get('faixa_alvos_casas')
        if fa:
            linhas.append(('Alvos das casas (mín. a máx.)', fa[0], fa[1], it['referencias'].get('mediana_casas'), GREY))
        if it['referencias'].get('alvo_xp'):
            a = it['referencias']['alvo_xp']
            linhas.append(('Alvo da XP', a, a, a, BLACK))
        for k, (nome, lo, hi, mid, cor) in enumerate(linhas[::-1]):
            if hi > lo:
                ax2.barh(k, hi - lo, left=lo, color=cor, height=0.45, alpha=0.85)
                ax2.text(lo, k + 0.33, pt(lo, 2), ha='right', va='bottom', fontsize=8)
                ax2.text(hi, k + 0.33, pt(hi, 2), ha='left', va='bottom', fontsize=8)
            if mid is not None:
                ax2.scatter([mid], [k], marker='D', s=70, color=BLACK, zorder=5)
        ax2.set_yticks(range(len(linhas))); ax2.set_yticklabels([l[0] for l in linhas[::-1]], fontsize=9)
        if preco:
            ax2.axvline(preco, color=RED, ls='--', lw=1.6)
            ax2.text(preco, len(linhas) - 0.45, f'Preço R$ {pt(preco, 2)}', color=RED, ha='center', va='bottom', fontsize=9, fontweight='bold')
        if not linhas:
            ax2.text(0.5, 0.5, v.get('motivo', 'valuation indisponível'), transform=ax2.transAxes, ha='center', va='center', fontsize=11, color=GREY)
        ax2.set_xlabel('R$ por ação'); ax2.set_ylim(-0.6, max(len(linhas), 1) + 0.3)
        ax2.set_title('Faixa de valuation e referências', loc='left', fontsize=10, color=GREY)
        for s in ('top', 'right'):
            ax2.spines[s].set_visible(False)
        ax2.legend(handles=[Line2D([0], [0], marker='D', color='w', markerfacecolor=BLACK, markersize=8, label='Cenário base / mediana')],
                   loc='lower right', frameon=False, fontsize=8)
        fig.text(0.02, 0.01, f'Fonte: CVM (DFP e ITR), premissas do projeto (dados/premissas_valuation.json), cotação de {C.data_br(it["data_cotacao"] or d["data"])}. '
                 'Modelo simplificado: não é previsão nem recomendação.', fontsize=8, color=GREY)
        fig.tight_layout(rect=(0, 0.04, 1, 0.94))
        fig.savefig(os.path.join(out, f'dossie_{t}.png'), dpi=170, facecolor='white')
        plt.close(fig)


def main():
    pasta = C.pasta_semana()
    d = construir(pasta)
    with open(os.path.join(pasta, 'dossie.json'), 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    figuras(d, pasta)
    ok = [t for t, v in d['tickers'].items() if v['valuation'].get('status') == 'ok']
    pend = sum(1 for v in d['tickers'].values() for c in v['checklist'] if c['status'] == 'pendente')
    print(f'dossie.json: {len(d["tickers"])} tickers, valuation em {len(ok)}; {pend} itens do checklist setorial pendentes')
    for t in ok:
        c = d['tickers'][t]['valuation']
        b = c['cenarios']['base']
        print(f'  {t:7} preço {d["tickers"][t]["preco"]:>7.2f} | valor base {b.get("valor_justo_por_acao", float("nan")):>7.2f} ({b.get("margem_pct", float("nan")):+6.1f}%) '
              f'| ke implícito {("%.1f%%" % c["ke_implicito_pct"]) if c.get("ke_implicito_pct") is not None else "n/d"} | ROE {c["roe_normalizado_pct"]:4.1f}% (exigido {c.get("roe_exigido_pct", float("nan")):4.1f}%) | g implícito {("%.1f%%" % c["g_implicito_pct"]) if c["g_implicito_pct"] is not None else "n/d"}')


if __name__ == '__main__':
    main()
