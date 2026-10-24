// Tela 2: dossiê da ação.
import { api } from '../api.js';
import { esc, nf, pct, dataBr, ausente } from '../util.js';
import { colunas, cabecalho, voltar, pill, score, certTexto, delta, scen, chk, fonte, tag, tagNv, icone, estadoVazio } from '../componentes.js';

function metrica(m) {
  if (m.valor === null) return `<div class="nv-box"><small>${esc(m.rotulo)}</small><b style="color:var(--warn)">n/v</b></div>`;
  const v = m.unidade === '%' ? pct(m.valor, 1) : nf(m.valor, 1);
  return `<div><small>${esc(m.rotulo)}</small><b>${esc(v)}</b></div>`;
}

export async function render({ ticker, origem = '#/semana' }) {
  const d = await api.dossie(ticker);
  // Métricas com a mesma fonte e data dividem uma tag só.
  const grupos = new Map();
  d.metricas.forEach(m => {
    const k = m.valor === null ? 'nv' : `${m.fonte}|${m.data}`;
    if (!grupos.has(k)) grupos.set(k, { m, nomes: [] });
    grupos.get(k).nomes.push(m.rotulo);
  });
  const tags = [...grupos.values()].map(g => g.m.valor === null
    ? tagNv(`${g.nomes.join(', ')}: não verificado`) : tag(`${g.nomes.join(', ')}: ${g.m.fonte}`, g.m.data)).join('');
  const metricas = `<div class="metrics">${d.metricas.map(metrica).join('')}</div><div style="display:flex;flex-wrap:wrap;gap:6px">${tags}</div>`;
  const resumo = `<div class="card" style="flex-direction:row;align-items:center;gap:14px">${score(d.nota, 'width:56px;height:56px;font-size:20px')}`
    + `<div style="display:flex;flex-direction:column;gap:6px"><b style="font-size:15px">Nota do modelo</b>${certTexto(d.certeza)}`
    + `<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center"><span class="m" style="font-size:12.5px;color:var(--muted)">XP: ${esc(String(d.rating_xp || 'sem rating').toLowerCase())}</span>${delta(d.diferenca)}</div></div></div>`;
  const val = d.valuation
    ? `<div class="card" style="gap:8px"><div class="lab">Valuation em cenários</div>${scen(d.valuation.cenarios, d.valuation.preco)}`
      + (d.valuation.ke_implicito_pct !== null || d.valuation.g_implicito_pct !== null
        ? `<div class="m" style="font:11.5px var(--mono);color:var(--muted);margin-top:4px">Implícito no preço: ke ${esc(pct(d.valuation.ke_implicito_pct) || 'n/v')} · crescimento ${esc(pct(d.valuation.g_implicito_pct) || 'n/v')}</div>` : '')
      + `<div>${tag(d.valuation.fonte, d.valuation.data)}</div></div>`
    : estadoVazio('Valuation em cenários', 'Sem valuation nesta semana: dossie.json não foi gerado ou a ação não tem demonstrações na CVM.');
  const lista = d.checklist.map(c => {
    const ok = c.status === 'preenchido' && !ausente(c.valor);
    return chk(ok ? 'confere' : 'nao_verificado', ok ? `${c.rotulo}: ${c.valor}` : c.rotulo,
      ok ? `${c.fonte || 'fonte n/d'}${c.data ? ' · ' + dataBr(c.data) : ''}` : 'pendente · sem fonte na semana');
  }).join('');
  const check = d.checklist.length
    ? `<div class="card" style="gap:10px"><div class="lab">Checklist do setor ${esc(d.setor || '')}</div>${lista}</div>`
    : estadoVazio(`Checklist do setor ${d.setor || ''}`.trim(), 'Checklist pendente: dossie.json não foi gerado nesta semana.');
  const html = cabecalho({ esquerda: voltar(origem), titulo: d.ticker, sub: `DOSSIÊ · ${(d.setor || 'SETOR N/D').toUpperCase()}`, direita: pill(d.acao), centro: true })
    + `<div class="body">${colunas(resumo + metricas, val + check)}`
    + `<div class="fab"><a class="btn p" style="width:100%" href="#/objecoes/${esc(d.ticker)}">${icone('scale')}Ver objeções</a></div></div>`;
  return { html };
}
