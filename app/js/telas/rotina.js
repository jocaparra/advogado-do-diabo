// Tela 6: rotina semanal. O botão só dispara depois de uma confirmação explícita.
import { api } from '../api.js';
import { esc, dataCurta } from '../util.js';
import { colunas, cabecalho, passo, obj, icone, estadoVazio, tag } from '../componentes.js';

let confirmando = false;
let retorno = '';
let timer = null;

export function parar() { clearInterval(timer); timer = null; }

const ESTADO = { agendada: ['idle', 'agendada'], executada: ['ok', 'enviada'], falhou: ['bad', 'falhou'], perdida: ['warn', 'perdida'], cancelada: ['idle', 'cancelada'] };

function cartaoAgenda(tarefas, nomes) {
  const ativas = tarefas.filter(t => t.estado === 'agendada');
  const outras = tarefas.filter(t => t.estado !== 'agendada').slice(-5).reverse();
  if (!tarefas.length) {
    return `<div class="card nv-box" style="gap:8px"><div class="lab">Mensagens agendadas</div>`
      + '<p style="margin:0;font-size:14px">Nenhuma. No chat, escreva por exemplo: <span class="mono">me manda o resumo do Risco segunda às 16</span>.</p></div>';
  }
  const linha = t => {
    const [cl, rot] = ESTADO[t.estado] || ['idle', t.estado];
    const botao = t.estado === 'agendada'
      ? `<button type="button" class="btn g sm" data-cancelar="${esc(t.id)}" aria-label="Cancelar mensagem de ${esc(t.quando_texto)}">Cancelar</button>` : '';
    const nota = t.estado === 'falhou' || t.estado === 'perdida' ? `<span class="m" style="display:block;font:11.5px var(--mono);color:var(--muted)">${esc(t.erro || '')}</span>` : '';
    return `<div class="step" style="align-items:flex-start"><span class="pill ${cl}" style="padding:2px 8px">${rot}</span>`
      + `<div style="min-width:0"><b style="font-weight:600">${esc(t.quando_texto)}</b> · ${esc(nomes[t.bot] || t.bot)}`
      + `<span class="m" style="display:block;font-size:12.5px;color:var(--muted);overflow-wrap:anywhere">${esc(t.pergunta)}</span>${nota}</div>`
      + `<span class="st">${botao}</span></div>`;
  };
  return `<div class="card" style="padding:6px 16px"><div class="lab" style="padding:10px 0 2px">Mensagens agendadas · ${ativas.length} ${ativas.length === 1 ? 'ativa' : 'ativas'}</div>`
    + ativas.concat(outras).map(linha).join('') + '</div>';
}

export async function render() {
  const [r, ag, st] = await Promise.all([api.rotina(), api.agenda().catch(() => ({ tarefas: [] })), api.chatStatus().catch(() => ({ bots: [] }))]);
  const nomes = Object.fromEntries((st.bots || []).map(b => [b.id, b.nome]));
  const rodando = r.job.estado === 'rodando';
  const sufixo = r.semana ? r.semana.replace(/^semana_(\d{4})(\d{2})(\d{2}).*/, (m, a, b, c) => `${c}/${b}`) : 'n/d';
  const pill = rodando ? '<span class="pill ok run">Rodando</span>'
    : r.job.estado === 'falhou' ? '<span class="pill bad">Falhou</span>'
      : r.job.estado === 'concluido' ? '<span class="pill ok">Concluído</span>' : '<span class="pill idle">Parado</span>';
  const passos = r.passos.map(passo).join('');
  const cmd = confirmando
    ? `<div class="obj" style="border-left-color:var(--warn)"><span class="k" style="color:var(--warn)">Confirmar</span><p>Isto dispara os agentes de verdade (/semana): leva tempo, usa a web e consome o seu uso do Claude Code. Continuar?</p>`
      + `<div style="display:flex;gap:8px"><button type="button" class="btn g" id="r-cancelar" style="flex:1">Cancelar</button><button type="button" class="btn p" id="r-confirmar" style="flex:1">Rodar</button></div></div>`
    : `<button type="button" class="btn p" id="r-rodar" style="width:100%"${rodando ? ' disabled' : ''}>${icone('play')}Rodar semana</button>`;
  const html = cabecalho({ titulo: 'Rotina', sub: `SEMANA ${sufixo} · ${r.concluidas} DE ${r.total} ETAPAS`, direita: pill })
    + `<div class="body">${retorno ? obj('Aviso', retorno, { aviso: true }) : ''}`
    + colunas(`<div class="card" style="padding:6px 16px">${passos}</div>`,
      cartaoAgenda(ag.tarefas, nomes)
      + `<div class="li"><div class="tx"><span class="lab">Princípios</span><span class="m" style="margin-top:4px;color:var(--fg);font-size:13px">Sem dado inventado. Toda informação com fonte e data. Contas feitas em código, não pelo modelo.</span></div></div>`)
    + `<div class="fab">${cmd}</div></div>`;
  return {
    html,
    montar(raiz, recarregar) {
      const q = s => raiz.querySelector(s);
      raiz.querySelectorAll('[data-cancelar]').forEach(b => b.addEventListener('click', async () => {
        try { await api.agendaCancelar(b.dataset.cancelar); } catch (e) { retorno = e.message; }
        recarregar();
      }));
      if (q('#r-rodar')) q('#r-rodar').addEventListener('click', () => { confirmando = true; recarregar(); });
      if (q('#r-cancelar')) q('#r-cancelar').addEventListener('click', () => { confirmando = false; recarregar(); });
      if (q('#r-confirmar')) q('#r-confirmar').addEventListener('click', async () => {
        confirmando = false;
        try { retorno = (await api.iniciarRotina()).mensagem; } catch (e) { retorno = e.message; }
        recarregar();
      });
      parar();
      if (rodando) timer = setInterval(recarregar, 5000);
    },
  };
}
