// Tela 5: desempenho das recomendações passadas contra o Ibovespa e o CDI.
import { api } from '../api.js';
import { esc, nf, pct, dataCurta, dataBr } from '../util.js';
import { colunas, cabecalho, chart, obj, tag, tagNv, estadoVazio } from '../componentes.js';

let horizonte = '4_semanas';
const ROT = { '1_semana': '1 sem', '4_semanas': '4 sem', '12_semanas': '12 sem' };

export async function render() {
  const d = await api.desempenho();
  if (!d.disponivel) return { html: cabecalho({ titulo: 'Desempenho', sub: 'RECOMENDAÇÕES PASSADAS' }) + `<div class="body">${estadoVazio('Sem avaliação', d.motivo)}</div>` };
  const h = d.horizontes[horizonte];
  const minObs = d.minimos.observacoes, minSem = d.minimos.semanas;
  const chips = Object.keys(ROT).map(k => `<button type="button" class="chip${k === horizonte ? ' on' : ''}" data-hz="${k}" aria-pressed="${k === horizonte}">${ROT[k]}</button>`).join('');
  const serie = h.serie_comprar.map(p => ({ ...p, rotulo: dataCurta(p.semana) }));
  const graf = serie.length
    ? `<div class="card" style="gap:8px"><div class="lab">Retorno médio das recomendações Comprar, por semana</div>${chart(serie, `Retorno médio do bot e do Ibovespa em ${serie.length} semanas de recomendação, horizonte ${ROT[horizonte]}`)}`
      + `<div class="leg" style="flex-direction:row;gap:14px;flex-wrap:wrap"><div><i style="background:var(--fg)"></i>Bot</div><div><i style="background:var(--info)"></i>Ibovespa</div><div><i style="background:var(--muted)"></i>CDI: n/v</div></div></div>`
    : estadoVazio('Retorno contra o Ibovespa', `Nenhuma recomendação Comprar venceu neste horizonte. ${h.pendentes} observações ainda aguardam vencer.`, 'pendente');
  const kv = (a, b) => `<div class="kv"><span>${a}</span><span>${b}</span></div>`;
  const tabela = h.media_bot !== null
    ? `<div class="card" style="gap:0">${kv('Bot', esc(pct(h.media_bot, 1, true)))}${kv('Ibovespa', esc(pct(h.media_ibov, 1, true)))}${kv('CDI', tagNv('não verificado'))}</div>` : '';
  const pequena = h.observacoes < minObs || h.semanas < minSem;
  const alerta = pequena
    ? obj('Amostra pequena', `${h.observacoes} de ${minObs} observações em ${h.semanas} ${h.semanas === 1 ? 'semana' : 'semanas'} (mínimo ${minSem}). Não conclua nada ainda.`, { aviso: true }) : '';
  const html = cabecalho({ titulo: 'Desempenho', sub: `RECOMENDAÇÕES PASSADAS · ${d.semanas_no_historico} ${d.semanas_no_historico === 1 ? 'SEMANA' : 'SEMANAS'}` })
    + `<div class="body"><div class="seg2" role="group" aria-label="Horizonte">${chips}</div>${colunas(graf, tabela + alerta)}<div>${tag('avaliacao.json', d.data)}</div></div>`;
  return {
    html,
    montar(raiz, recarregar) {
      raiz.querySelectorAll('[data-hz]').forEach(b => b.addEventListener('click', () => { horizonte = b.dataset.hz; recarregar(); }));
    },
  };
}
