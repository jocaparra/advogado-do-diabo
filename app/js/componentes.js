// Componentes da tabela do DESIGN.md. Cada função devolve HTML; texto externo passa por esc().
import { esc, norm, ausente, nf, brl, dataBr } from './util.js';

export const icone = id => `<svg class="i" aria-hidden="true"><use href="#${id}"/></svg>`;

const ACAO = { comprar: ['ok', 'Comprar'], aguardar: ['warn', 'Aguardar'], evitar: ['bad', 'Evitar'] };

export function pill(acao) {
  const a = ACAO[norm(acao)];
  return a ? `<span class="pill ${a[0]}">${a[1]}</span>` : tagNv('sem ação');
}

// Faixas da nota (premissa de interface, não do modelo): verde a partir de 7, âmbar a partir de 4.
export function score(nota, estilo = '') {
  const e = estilo ? ` style="${estilo}"` : '';
  if (typeof nota !== 'number') return `<span class="score"${e}>n/d</span>`;
  const cl = nota >= 7 ? 'hi' : nota >= 4 ? 'mid' : 'lo';
  return `<span class="score ${cl}"${e}>${nf(nota, 1)}</span>`;
}

export function cert(c) {
  const n = { alta: 3, media: 2, baixa: 1 }[norm(c)];
  if (!n) return '';
  const barras = [1, 2, 3].map(i => `<i${i <= n ? ' class="on"' : ''}></i>`).join('');
  return `<span class="cert" title="certeza ${esc(norm(c))}">${barras}</span>`;
}

export function certTexto(c) {
  const n = { alta: 3, media: 2, baixa: 1 }[norm(c)];
  if (!n) return tagNv('certeza não informada');
  const barras = [1, 2, 3].map(i => `<i${i <= n ? ' class="on"' : ''}></i>`).join('');
  return `<span class="cert">${barras}&nbsp;${esc(String(c).toLowerCase())}</span>`;
}

export const tag = (fonte, data) =>
  `<span class="tag">${esc(fonte)}${data ? ' · ' + esc(dataBr(data)) : ''}</span>`;

export const tagNv = (texto = 'não verificado') => `<span class="tag nv">${esc(texto)}</span>`;

export function fonte(f, data) {
  return ausente(f) ? tagNv('não verificado') : tag(f, data);
}

export function delta(d) {
  if (d === 'discorda') return '<span class="delta d">DISCORDA</span>';
  if (d === 'concorda') return '<span class="delta c">CONCORDA</span>';
  return '';
}

export function obj(rotulo, texto, { aviso = false, meta = '' } = {}) {
  const cor = aviso ? ' style="border-left-color:var(--warn)"' : '';
  const k = aviso ? ' style="color:var(--warn)"' : '';
  return `<div class="obj"${cor}><span class="k"${k}>${esc(rotulo)}</span><p>${esc(texto)}</p>${meta}</div>`;
}

export function tese(rotulo, texto, meta = '') {
  return `<div class="thesis"><span class="k">${esc(rotulo)}</span><p>${esc(texto)}</p>${meta}</div>`;
}

const CHK = { confere: ['y', 'check'], nao_confere: ['n', 'x'], nao_verificado: ['q', null] };

export function chk(estado, texto, meta) {
  const [cl, ic] = CHK[estado] || CHK.nao_verificado;
  const dot = ic ? `<span class="d ${cl}">${icone(ic)}</span>` : `<span class="d ${cl}">?</span>`;
  return `<div class="chk">${dot}<div>${esc(texto)}${meta ? `<span class="m">${esc(meta)}</span>` : ''}</div></div>`;
}

export function passo(p) {
  const rot = { ok: ['ok', 'ok'], agora: ['ok run', 'agora'], fila: ['idle', 'fila'] }[p.estado] || ['idle', 'fila'];
  const arq = p.arquivo || (p.arquivos && p.arquivos.length ? `${p.arquivos.length} arquivos` : '');
  return `<div class="step"><span class="pill ${rot[0]}" style="padding:2px 8px">${rot[1]}</span>${esc(p.nome)}`
    + (arq ? `<span class="st tag">${esc(arq)}</span>` : '') + '</div>';
}

export function item({ href, nota, titulo, meta, direita }) {
  const abre = href ? `<a class="li" href="${esc(href)}">` : '<div class="li">';
  const fecha = href ? '</a>' : '</div>';
  return `${abre}${score(nota)}<div class="tx"><b>${esc(titulo)}</b><span class="m">${esc(meta)}</span></div>`
    + `<div class="sp">${direita}</div>${fecha}`;
}

// Régua de cenários. Escala como na referência: bear em 20% e bull em 87% quando o preço está entre eles.
export function scen(cen, preco) {
  const v = { bear: cen.bear.valor, base: cen.base.valor, bull: cen.bull.valor };
  const todos = [v.bear, v.base, v.bull].concat(typeof preco === 'number' ? [preco] : []);
  const lo = Math.min(...todos);
  const hi = Math.max(...todos);
  const pos = x => (hi === lo ? 50 : 20 + ((x - lo) / (hi - lo)) * 67);
  const fmt = x => brl(x, x >= 10 ? 0 : 2);
  const pts = ['bear', 'base', 'bull'].map(k => `<div class="pt" style="left:${pos(v[k]).toFixed(1)}%"><b>${esc(fmt(v[k]))}</b>${k}</div>`).join('');
  const px = typeof preco === 'number'
    ? `<div class="px" style="left:${pos(preco).toFixed(1)}%"></div><div class="pxl" style="left:${pos(preco).toFixed(1)}%">preço ${esc(fmt(preco))}</div>` : '';
  const a = pos(Math.min(v.bear, v.bull));
  return `<div class="scen" role="img" aria-label="Valor justo: bear ${esc(fmt(v.bear))}, base ${esc(fmt(v.base))}, bull ${esc(fmt(v.bull))}">`
    + `<div class="rail"></div><div class="rng" style="left:${a.toFixed(1)}%;width:${(pos(Math.max(v.bear, v.bull)) - a).toFixed(1)}%"></div>${pts}${px}</div>`;
}

export function cabecalho({ esquerda = '', titulo, sub = '', direita = '', centro = false }) {
  const miolo = `<div${centro ? ' style="text-align:center"' : ''}><h4${centro ? ' style="font-size:18px"' : ''}>${esc(titulo)}</h4>`
    + (sub ? `<small>${esc(sub)}</small>` : '') + '</div>';
  return `<div class="hd">${esquerda}${miolo}${direita}</div>`;
}

export const voltar = href => `<a class="ib" href="${esc(href)}" aria-label="Voltar">${icone('back')}</a>`;

export function estadoVazio(titulo, texto, tagTxt = 'pendente') {
  return `<div class="card nv-box"><div class="lab">${esc(titulo)}</div><p style="margin:0;font-size:14px">${esc(texto)}</p>${tagNv(tagTxt)}</div>`;
}

export function erro(msg) {
  return `<div class="body">${obj('Não consegui ler os dados', msg)}</div>`;
}

// Gráfico de desempenho: Bot sólido, Ibovespa em azul, CDI tracejado (só quando houver série de CDI).
export function chart(serie, rotuloAria) {
  const X0 = 28, X1 = 296, Y0 = 20, Y1 = 130;
  const vals = serie.flatMap(p => [p.bot, p.ibov]).concat([0]);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (hi === lo) { hi += 1; lo -= 1; }
  const y = v => Y1 - ((v - lo) / (hi - lo)) * (Y1 - Y0);
  const x = i => (serie.length === 1 ? X1 : X0 + (i / (serie.length - 1)) * (X1 - X0));
  const pts = k => serie.map((p, i) => `${x(i).toFixed(1)},${y(p[k]).toFixed(1)}`).join(' ');
  const ticks = [hi, (hi + lo) / 2, lo].map(t => ({ t, y: y(t) }));
  const grade = ticks.map(t => `<line class="gl" x1="${X0}" y1="${t.y.toFixed(1)}" x2="${X1}" y2="${t.y.toFixed(1)}"/>`
    + `<text x="0" y="${(t.y + 3).toFixed(1)}">${esc(nf(t.t, 1))}%</text>`).join('');
  const zero = `<line class="gl" x1="${X0}" y1="${y(0).toFixed(1)}" x2="${X1}" y2="${y(0).toFixed(1)}"/>`;
  const ult = serie.length - 1;
  return `<svg class="chart" viewBox="0 0 300 150" role="img" aria-label="${esc(rotuloAria)}">${grade}${zero}`
    + `<polyline fill="none" stroke="var(--fg)" stroke-width="2.2" stroke-linejoin="round" points="${pts('bot')}"/>`
    + `<polyline fill="none" stroke="var(--info)" stroke-width="2" stroke-linejoin="round" points="${pts('ibov')}"/>`
    + `<circle cx="${x(ult).toFixed(1)}" cy="${y(serie[ult].bot).toFixed(1)}" r="3.5" fill="var(--fg)"/>`
    + `<text x="${X0}" y="146">${esc(serie[0].rotulo)}</text><text x="${serie.length > 1 ? 250 : 262}" y="146">${esc(serie[ult].rotulo)}</text></svg>`;
}

// Duas colunas só em tela larga; no celular os blocos seguem em uma coluna, na mesma ordem.
export function colunas(esq, dir) {
  return `<div class="colunas"><div class="col">${esq}</div><div class="col">${dir}</div></div>`;
}
