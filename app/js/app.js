// Roteador por hash. Cada tela devolve { html, montar? }; erros viram um cartão, nunca uma tela vazia.
import { api } from './api.js';
import { erro } from './componentes.js';
import * as semana from './telas/semana.js';
import * as dossie from './telas/dossie.js';
import * as chat from './telas/chat.js';
import * as objecoes from './telas/objecoes.js';
import * as carteira from './telas/carteira.js';
import * as desempenho from './telas/desempenho.js';
import * as rotina from './telas/rotina.js';

const telas = { semana, chat, dossie, objecoes, carteira, desempenho, rotina };
// Dossiê e objeções não têm aba: abrem a partir da lista da semana ou do chat.
const ABA = { semana: 'semana', chat: 'chat', dossie: 'semana', objecoes: 'semana', carteira: 'carteira', desempenho: 'desempenho', rotina: 'rotina' };
const ABAS_PROPRIAS = ['semana', 'chat', 'carteira', 'desempenho', 'rotina'];
let origem = '#/semana';   // última aba visitada: o botão Voltar do dossiê volta para ela
const raiz = document.getElementById('view');
let atual = null;

function rota() {
  const [, nome = 'semana', param = ''] = location.hash.split('/');
  const tela = telas[nome] ? nome : 'semana';
  return { tela, ticker: /^[A-Za-z0-9]{4,7}$/.test(param) ? param.toUpperCase() : null };
}

async function desenhar(foco) {
  const r = rota();
  if ((r.tela === 'dossie' || r.tela === 'objecoes') && !r.ticker) { location.replace('#/semana'); return; }
  if (ABAS_PROPRIAS.includes(r.tela)) origem = `#/${r.tela}`;
  const id = Symbol();
  atual = id;
  document.querySelectorAll('.tabs a').forEach(a => {
    const on = a.dataset.aba === ABA[r.tela];
    a.classList.toggle('on', on);
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  document.body.dataset.tela = r.tela;
  let saida;
  try { saida = await telas[r.tela].render({ ticker: r.ticker, origem }); } catch (e) {
    saida = { html: erro(e.message || 'Falha ao ler os dados.') };
  }
  if (atual !== id) return;  // outra navegação chegou antes
  raiz.innerHTML = saida.html;
  if (saida.montar) saida.montar(raiz, () => desenhar(false));
  if (foco) { raiz.focus({ preventScroll: true }); window.scrollTo(0, 0); }
}

window.addEventListener('hashchange', () => { rotina.parar(); chat.parar(); desenhar(true); });
desenhar(true);
