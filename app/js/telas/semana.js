// Tela 1: carteira da semana.
import { api } from '../api.js';
import { esc, norm, dataExtensa, dataBr } from '../util.js';
import { cabecalho, item, pill, cert, delta, tag, tagNv, estadoVazio, obj } from '../componentes.js';

let filtro = 'todas';

function linha(r) {
  const xp = r.rating_xp ? `XP: ${String(r.rating_xp).toLowerCase()}` : 'XP: sem rating';
  if (r.sem_dados) {
    return item({ href: `#/dossie/${r.ticker}`, nota: null, titulo: r.ticker, meta: `${r.setor || 'setor n/d'} · sem nota nesta semana`, direita: tagNv('não verificado') });
  }
  const direita = pill(r.acao) + (r.diferenca === 'discorda' ? delta('discorda') : cert(r.certeza));
  return item({ href: `#/dossie/${r.ticker}`, nota: r.nota, titulo: r.ticker, meta: `${r.setor || 'setor n/d'} · ${xp}`, direita });
}

export async function render() {
  let s;
  try { s = await api.semana(); } catch (e) {
    if (e.status === 404) return { html: cabecalho({ titulo: 'Semana' }) + `<div class="body">${estadoVazio('Sem análise', 'Nenhuma semana com sintese.json foi encontrada. Rode a rotina semanal.')}</div>` };
    throw e;
  }
  const discordo = s.ranking.filter(r => r.diferenca === 'discorda').length;
  const semDados = s.ranking.filter(r => r.sem_dados).length;
  const chip = (id, txt) => `<button type="button" class="chip${filtro === id ? ' on' : ''}" data-filtro="${id}" aria-pressed="${filtro === id}">${txt}</button>`;
  const lista = () => {
    const r = s.ranking.filter(x => filtro === 'todas' || (filtro === 'discordo' ? x.diferenca === 'discorda' : x.sem_dados));
    return r.length ? r.map(linha).join('') : `<div class="m" style="color:var(--muted);text-align:center;padding:16px 0">Nenhuma ação neste filtro.</div>`;
  };
  const html = cabecalho({ titulo: 'Semana', sub: `${dataExtensa(s.data)} · ${s.ranking.length} AÇÕES` })
    + `<div class="body"><div class="seg2" role="group" aria-label="Filtro">${chip('todas', 'Todas')}${chip('discordo', `Discordo ${discordo}`)}${chip('sem', `Sem dados ${semDados}`)}</div>`
    + `<div id="lista" style="display:flex;flex-direction:column;gap:12px">${lista()}</div>`
    + `<div style="text-align:center">${tag('sintese.json', s.data)}</div>`
    + `<div class="m" style="font-size:11.5px;color:var(--muted);text-align:center;margin-top:auto">Rótulos são do modelo, não ordens. Ignoram seu perfil, patrimônio e impostos.</div></div>`;
  return {
    html,
    montar(raiz) {
      raiz.querySelectorAll('[data-filtro]').forEach(b => b.addEventListener('click', () => {
        filtro = b.dataset.filtro;
        raiz.querySelectorAll('[data-filtro]').forEach(x => {
          x.classList.toggle('on', x === b); x.setAttribute('aria-pressed', String(x === b));
        });
        raiz.querySelector('#lista').innerHTML = lista();
      }));
    },
  };
}
