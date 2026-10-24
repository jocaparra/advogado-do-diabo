// Tela 3: objeções do advogado, tese da XP e conferência do auditor.
import { api } from '../api.js';
import { esc, dataBr, dataCurta, ausente } from '../util.js';
import { colunas, cabecalho, voltar, obj, tese, chk, tag, tagNv, estadoVazio } from '../componentes.js';

const ROTULOS = ['Objeção mais forte', 'Segunda objeção'];

export async function render({ ticker }) {
  const o = await api.objecoes(ticker);
  const xp = o.tese_xp && !ausente(o.tese_xp.texto)
    ? tese('Tese da XP', o.tese_xp.texto, `<div>${tag(o.tese_xp.fonte, o.tese_xp.data)}</div>`)
    : estadoVazio('Tese da XP', 'Sem comentário da XP para esta ação no xp.json.');
  const objs = o.objecoes.length
    ? o.objecoes.map((x, i) => obj(ROTULOS[i] || `Objeção ${i + 1}`, x.objecao,
      { meta: `<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center">${tag(x.fonte || 'fonte n/d', x.data)}`
        + (x.forca ? `<span class="tag">força ${esc(x.forca)}</span>` : '') + '</div>'
        + (x.evidencia ? `<details style="font-size:13px;color:var(--muted)"><summary>Evidência</summary><p style="margin:6px 0 0">${esc(x.evidencia)}</p></details>` : '') })).join('')
    : estadoVazio(`Sem objeção para ${o.ticker}`, `O advogado não registrou objeção para esta ação nesta semana. Escopo: ${o.escopo_advogado || 'não informado'}.`, 'sem cobertura');
  const falhas = o.conferencias.filter(c => c.estado !== 'confere');
  const ok = o.conferencias.filter(c => c.estado === 'confere');
  const linha = c => chk(c.estado, c.texto || 'item', `${c.detalhe || ''}${c.detalhe ? ' · ' : ''}${c.fonte}`);
  const linhasCheck = falhas.slice(0, 4).map(linha).join('')
    + (falhas.length > 4 ? `<details style="display:flex;flex-direction:column;gap:10px"><summary class="m" style="font:11.5px var(--mono);color:var(--muted)">Ver mais ${falhas.length - 4}</summary>${falhas.slice(4).map(linha).join('')}</details>` : '')
    + (ok.length ? chk('confere', `${ok.length} ${ok.length === 1 ? 'item confere' : 'itens conferem'}`, 'auditoria.json') : '');
  const auditor = o.conferencias.length
    ? `<div class="card" style="gap:10px"><div class="lab">Conferência do auditor</div>${linhasCheck}</div>`
    : estadoVazio('Conferência do auditor', 'Nenhum item do auditor para esta ação nesta semana.', 'não verificado');
  const gatilho = ausente(o.gatilho_revisao)
    ? `<div class="li" style="margin-top:auto"><div class="tx"><span class="lab">Gatilho de revisão</span>${tagNv('pendente')}</div></div>`
    : `<div class="li" style="margin-top:auto"><div class="tx"><span class="lab">Gatilho de revisão</span><b style="font-size:14px;margin-top:2px">${esc(o.gatilho_revisao)}</b></div></div>`;
  const html = cabecalho({ esquerda: voltar(`#/dossie/${esc(o.ticker)}`), titulo: 'Objeções', sub: `${o.ticker} · SEMANA ${dataCurta(o.data)}`, direita: '<span style="width:40px"></span>', centro: true })
    + `<div class="body">${colunas(xp + objs, auditor + gatilho)}</div>`;
  return { html };
}
