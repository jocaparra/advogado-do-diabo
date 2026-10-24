// Tela 4: minha carteira. O CSV é lido pelo servidor local e fica só em memória.
import { api } from '../api.js';
import { esc, nf, pct, brl } from '../util.js';
import { colunas, cabecalho, icone, score, pill, obj, tag, tagNv, estadoVazio } from '../componentes.js';

let ultimoCsv = null;   // só na memória desta página
let editando = false;
let aviso = '';

const CORES = ['var(--fg)', 'var(--info)', 'var(--muted)', 'var(--line)', 'var(--elevated)'];
const ROT_HOR = { semanas: 'Semanas', meses: 'Meses', anos: 'Anos' };
const ROT_OBJ = { crescimento: 'Crescimento', renda: 'Renda', preservacao: 'Preservação' };

function setores(c) {
  const itens = Object.entries(c.peso_por_setor_pct || {}).sort((a, b) => b[1] - a[1]);
  const topo = itens.slice(0, 4);
  const resto = itens.slice(4).reduce((s, x) => s + x[1], 0);
  if (resto > 0) topo.push(['Outros', Math.round(resto * 10) / 10]);
  return topo;
}

function cartaoConcentracao(c) {
  const its = setores(c);
  if (!its.length) return estadoVazio('Concentração por setor', 'Nenhuma posição com setor conhecido.');
  const barra = its.map((x, i) => `<i style="width:${x[1]}%;background:${CORES[i % CORES.length]}"></i>`).join('');
  const leg = its.map((x, i) => `<div><i style="background:${CORES[i % CORES.length]}"></i>${esc(x[0])}<span>${esc(pct(x[1], 0))}</span></div>`).join('');
  return `<div class="card" style="gap:10px"><div class="lab">Concentração por setor</div><div class="stack">${barra}</div><div class="leg">${leg}</div></div>`;
}

function cartaoPlano(p) {
  if (!p.plano) return `<div class="card nv-box" style="gap:8px"><div class="lab">Plano pessoal · salvo neste computador</div><p style="margin:0;font-size:14px">Sem plano salvo. Os limites usados são os padrões do projeto.</p>${tagNv('pendente')}</div>`;
  const x = p.plano;
  const kv = (a, b) => `<div class="kv"><span>${esc(a)}</span><span>${esc(b)}</span></div>`;
  return `<div class="card" style="gap:8px"><div class="lab">Plano pessoal · salvo neste computador</div>${kv('Horizonte', ROT_HOR[x.horizonte])}${kv('Objetivo', ROT_OBJ[x.objetivo])}`
    + `${kv('Queda tolerada', '-' + nf(x.queda_max_pct, 0) + '%')}${kv('Limite por ação', nf(x.limite_ativo_pct, 0) + '%')}${kv('Limite por setor', nf(x.limite_setor_pct, 0) + '%')}</div>`;
}

function formPlano(p) {
  const x = p.plano || { horizonte: 'meses', objetivo: 'crescimento', ...p.padrao };
  const grupo = (nome, ops, rot, atual) => `<div class="seg2" role="group" aria-label="${nome}" data-grupo="${nome}">`
    + ops.map(o => `<button type="button" class="chip${o === atual ? ' on' : ''}" data-valor="${o}" aria-pressed="${o === atual}">${rot[o]}</button>`).join('') + '</div>';
  const num = (id, rot, v) => `<label style="display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:13.5px">${rot}`
    + `<input id="${id}" inputmode="decimal" value="${esc(String(v).replace('.', ','))}" style="width:84px;min-height:36px;border-radius:var(--r-sm);border:1px solid var(--line);background:var(--surface);color:var(--fg);padding:0 10px;font:13px var(--mono);text-align:right"></label>`;
  return `<div class="card" style="gap:12px"><div class="lab">Editar plano</div><div class="lab" style="text-transform:none">Horizonte</div>${grupo('horizonte', p.horizontes, ROT_HOR, x.horizonte)}`
    + `<div class="lab" style="text-transform:none">Objetivo</div>${grupo('objetivo', p.objetivos, ROT_OBJ, x.objetivo)}`
    + `${num('f-queda', 'Queda tolerada (%)', x.queda_max_pct)}${num('f-ativo', 'Limite por ação (%)', x.limite_ativo_pct)}${num('f-setor', 'Limite por setor (%)', x.limite_setor_pct)}`
    + `<div id="erro-plano" role="alert" style="font-size:13px;color:var(--bad)"></div>`
    + `<div style="display:flex;gap:8px"><button type="button" class="btn g" id="p-apagar" style="flex:1">Apagar plano</button><button type="button" class="btn p" id="p-salvar" style="flex:1">Salvar</button></div></div>`;
}

export async function render() {
  const [c, p] = await Promise.all([api.carteira(), api.plano()]);
  const cab = cabecalho({ titulo: 'Minha carteira', sub: 'CSV · SOMENTE LEITURA',
    direita: `<button type="button" class="ib" id="b-importar" aria-label="Importar CSV">${icone('upload')}</button>` });
  const entrada = '<input type="file" id="arquivo" accept=".csv,.txt,text/csv,text/plain" hidden>';
  const msg = aviso ? obj('Atenção', aviso) : '';
  let corpo;
  if (c.vazio) {
    corpo = `${msg}<div class="card nv-box" style="gap:10px"><div class="lab">Nenhuma carteira importada</div>`
      + `<p style="margin:0;font-size:14px">Importe um CSV com as colunas <span class="mono">ticker;quantidade;preco_medio</span>. O arquivo é lido só neste computador e não é gravado em disco.</p>`
      + `<button type="button" class="btn p" id="b-importar2">${icone('upload')}Importar CSV</button></div>${editando ? formPlano(p) : cartaoPlano(p)}`;
  } else {
    const posicoes = (c.posicoes || []).map(l => `<div class="li">${score(l.nota)}`
      + `<div class="tx"><b>${esc(l.ticker)}</b><span class="m">${l.peso_pct != null ? esc(pct(l.peso_pct, 1)) + ' da carteira' : 'peso n/d'} · ${esc(l.setor || 'fora do ranking')}</span></div>`
      + `<div class="sp">${l.no_ranking ? pill(l.acao_modelo) : tagNv('fora do ranking')}</div></div>`).join('');
    const esq = `<div class="card" style="flex-direction:row;align-items:center;gap:14px">${score(c.nota_media_ponderada, 'width:56px;height:56px;font-size:20px')}`
      + `<div><b style="font-size:15px">Nota da sua carteira</b><span class="m" style="display:block;font-size:12.5px;color:var(--muted)">Média ponderada · ${c.n_posicoes} ${c.n_posicoes === 1 ? 'ação' : 'ações'}</span></div></div>`
      + `${cartaoConcentracao(c)}${(c.alertas || []).map(a => obj('Atenção', a)).join('')}`;
    const dir = `<div class="lab">Posições</div>${posicoes}${editando ? formPlano(p) : cartaoPlano(p)}<div>${tag(c.origem || 'origem n/d')}</div>`;
    corpo = `${msg}${colunas(esq, dir)}`
      + (editando ? '' : `<div class="fab" style="display:flex;gap:8px"><button type="button" class="btn g" id="b-esquecer" style="flex:1">Esquecer</button><button type="button" class="btn p" id="b-plano" style="flex:1">Editar plano</button></div>`);
  }
  if (c.vazio && !editando) corpo += `<div class="fab"><button type="button" class="btn g" id="b-plano" style="width:100%">Editar plano</button></div>`;
  const html = cab + `<div class="body">${corpo}${entrada}</div>`;

  return {
    html,
    montar(raiz, recarregar) {
      const arq = raiz.querySelector('#arquivo');
      const abrir = () => arq.click();
      ['#b-importar', '#b-importar2'].forEach(s => { const b = raiz.querySelector(s); if (b) b.addEventListener('click', abrir); });
      arq.addEventListener('change', async () => {
        const f = arq.files[0];
        if (!f) return;
        if (f.size > 150000) { aviso = 'Arquivo grande demais para um CSV de posições.'; return recarregar(); }
        try { ultimoCsv = await f.text(); await api.importarCarteira(ultimoCsv); aviso = ''; } catch (e) { aviso = e.message; }
        recarregar();
      });
      const es = raiz.querySelector('#b-esquecer');
      if (es) es.addEventListener('click', async () => { ultimoCsv = null; await api.esquecerCarteira(); recarregar(); });
      const pl = raiz.querySelector('#b-plano');
      if (pl) pl.addEventListener('click', () => { editando = true; recarregar(); });
      if (!editando) return;
      raiz.querySelectorAll('[data-grupo]').forEach(g => g.querySelectorAll('.chip').forEach(b => b.addEventListener('click', () => {
        g.querySelectorAll('.chip').forEach(x => { x.classList.toggle('on', x === b); x.setAttribute('aria-pressed', String(x === b)); });
      })));
      const sel = n => (raiz.querySelector(`[data-grupo="${n}"] .chip.on`) || {}).dataset.valor;
      raiz.querySelector('#p-salvar').addEventListener('click', async () => {
        try {
          await api.salvarPlano({ horizonte: sel('horizonte'), objetivo: sel('objetivo'), queda_max_pct: raiz.querySelector('#f-queda').value,
            limite_ativo_pct: raiz.querySelector('#f-ativo').value, limite_setor_pct: raiz.querySelector('#f-setor').value });
          editando = false;
          if (ultimoCsv) await api.importarCarteira(ultimoCsv);  // recalcula com o novo plano
          recarregar();
        } catch (e) { raiz.querySelector('#erro-plano').textContent = e.message; }
      });
      raiz.querySelector('#p-apagar').addEventListener('click', async () => {
        await api.apagarPlano(); editando = false;
        if (ultimoCsv) await api.importarCarteira(ultimoCsv);
        recarregar();
      });
    },
  };
}
