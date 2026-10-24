// Tela: chat com os bots da semana. Cada bot é um agente do projeto e responde só com o arquivo dele.
// O servidor local devolve a resposta com fontes verificadas. O dossiê não tem aba: os tickers citados levam até ele.
import { api } from '../api.js';
import { esc, textoComLinks, dataCurta, dataBr } from '../util.js';
import { cabecalho, icone, tag, tagNv, obj } from '../componentes.js';
import { rolagemHorizontal } from '../rolagem.js';

let bots = [];
let bot = 'analista';       // bot selecionado
const fios = {};            // uma conversa por bot: [{ papel, texto, fontes?, nv?, formato_ok?, erro? }]
let pendente = null;        // id do bot que está respondendo (uma pergunta por vez)
let usarCarteira = false;
let tickers = [];
let rascunho = '';
let timer = null;
const vistas = new Set();   // tarefas agendadas que já viraram mensagem nesta página

export function parar() { clearInterval(timer); timer = null; }

const atual = () => bots.find(b => b.id === bot) || bots[0];
const fio = id => (fios[id] = fios[id] || []);
const ultimaPergunta = id => [...fio(id)].reverse().find(m => m.papel === 'usuario');

// Cartão de bot (kit de design): em tela larga o painel lateral lista os bots com o que cada um lê.
function cartaoBot(x) {
  const ativo = x.id === bot;
  const status = pendente === x.id ? '<span class="sp pill ok run">Respondendo</span>'
    : x.pronto ? '<span class="sp pill ok">Pronto</span>' : '<span class="sp pill warn">Sem arquivo</span>';
  const u = ultimaPergunta(x.id);
  const tarefa = u ? `Última pergunta: ${u.texto}` : `Sem perguntas ainda. Experimente: ${x.sugestoes[0].replace('{t}', tickers[0] || '').replace('{t2}', tickers[1] || '')}`;
  const arquivos = x.arquivos.map(a => (a.existe ? tag(a.nome) : tagNv(`${a.nome}: ausente`))).join('');
  const dados = x.data ? `Dados de ${dataBr(x.data)}` : 'Sem data nos dados';
  return `<button type="button" class="card cartao-bot" data-bot="${esc(x.id)}" aria-pressed="${ativo}">`
    + `<span class="bh"><span class="av${ativo ? ' inv' : ''}" aria-hidden="true">${esc(x.mono)}</span><span><b>${esc(x.nome)}</b><span class="m">${esc(x.descricao)}</span></span>${status}</span>`
    + `<span class="task">${esc(tarefa.length > 110 ? tarefa.slice(0, 107) + '...' : tarefa)}</span>`
    + `<span class="apps">${arquivos}</span><span class="dados-bot">${esc(dados)}</span></button>`;
}

function fontesDe(m) {
  const tags = (m.fontes || []).map(f => tag(f.fonte, f.data)).concat((m.nv || []).map(x => tagNv(`${x}: não verificado`)));
  if (m.formato_ok === false) tags.push(tagNv('formato inesperado, sem fontes'));
  else if (!(m.fontes || []).length) tags.push(tagNv('sem fontes citadas'));
  return `<div class="fontes">${tags.join('')}</div>`;
}

function cartaoAgenda(m, i) {
  const p = m.proposta;
  const kv = (a, v) => `<div class="kv"><span>${a}</span><span>${esc(v)}</span></div>`;
  let rodape;
  if (m.estado === 'pendente') {
    rodape = `<div class="acoes"><button type="button" class="btn g sm" data-acao="agenda-nao" data-i="${i}">Cancelar</button>`
      + `<button type="button" class="btn p sm" data-acao="agenda-sim" data-i="${i}">Confirmar</button></div>`;
  } else if (m.estado === 'confirmado') {
    rodape = `${tag('agendado')}<p class="nota-agenda">Aviso por notificação do Mac e aqui no chat. O Mac e o servidor precisam estar ligados.</p>`;
  } else {
    rodape = tagNv(m.estado === 'erro' ? m.erro || 'não agendado' : 'cancelado');
  }
  return `<div class="card cartao-agenda" role="group" aria-label="Confirmar agendamento"><div class="lab">Agendar mensagem</div>`
    + `${kv('Quando', p.quando_texto)}${kv('Bot', p.nome_bot)}${kv('Pergunta', p.pergunta)}${rodape}</div>`;
}

function bolha(m, b, i) {
  if (m.proposta) return cartaoAgenda(m, i);
  if (m.aviso) return obj('Agendamento', m.texto, { aviso: true });
  if (m.papel === 'usuario') return `<div class="msg u"><div class="bub">${esc(m.texto)}</div></div>`;
  if (m.erro) return obj('Não consegui responder', m.texto, { aviso: true });
  const rot = m.agendada ? `<p class="agendada">Agendada · ${esc(m.agendada)}${m.atrasada ? ' · atrasada' : ''}</p>` : '';
  return `${rot}<div class="msg a"><span class="av t" aria-label="${esc(b.nome)}">${esc(b.mono)}</span><div class="bub">${textoComLinks(m.texto, tickers)}</div></div>${fontesDe(m)}`;
}

function listaHtml() {
  const b = atual();
  const intro = `<div class="msg a"><span class="av t" aria-label="${esc(b.nome)}">${esc(b.mono)}</span><div class="bub"><p><b>${esc(b.nome)}.</b> ${esc(b.descricao)}</p>`
    + '<p>Respondo só com os dados do meu arquivo e digo quando algo não foi verificado.</p></div></div>';
  const dig = pendente === b.id
    ? `<div class="msg a" role="status" aria-label="${esc(b.nome)} está escrevendo"><span class="av t">${esc(b.mono)}</span><div class="bub digitando"><i></i><i></i><i></i></div></div>` : '';
  return intro + fio(b.id).map((m, i) => bolha(m, b, i)).join('') + dig;
}

function sugestoes() {
  const [t, t2] = tickers;
  return atual().sugestoes
    .filter(s => !(s.includes('{t2}') && !t2) && !(s.includes('{t}') && !t))
    .map(s => s.replace('{t2}', t2 || '').replace('{t}', t || ''));
}

function desenhar() {
  const el = document.getElementById('msgs');
  if (!el) return;   // o usuário trocou de aba: o estado fica guardado e volta na próxima visita
  el.innerHTML = listaHtml();
  el.scrollTop = el.scrollHeight;
  const b = document.getElementById('enviar');
  const q = document.getElementById('pergunta');
  if (b && q) b.disabled = pendente !== null || !q.value.trim();
}

async function enviar(texto) {
  texto = texto.trim();
  if (pendente || !texto) return;
  const meu = bot;
  const historico = fio(meu).filter(m => !m.erro && !m.proposta && !m.aviso).map(m => ({ papel: m.papel, texto: m.texto }));
  fio(meu).push({ papel: 'usuario', texto });
  pendente = meu;
  desenhar();
  try {
    // "me manda o resumo segunda às 16" vira um pedido de agendamento (entendido no servidor, sem gastar o Claude)
    const ag = await api.agendaInterpretar(texto, meu);
    if (ag.agendamento) {
      fio(meu).push(ag.entendido ? { papel: 'assistente', proposta: ag.proposta, estado: 'pendente' } : { papel: 'assistente', aviso: true, texto: ag.motivo });
      pendente = null;
      desenhar();
      return;
    }
  } catch (e) { /* sem interpretação: segue como pergunta normal */ }
  try {
    const r = await api.chat(texto, historico, usarCarteira, meu);
    fio(meu).push({ papel: 'assistente', texto: r.resposta, fontes: r.fontes, nv: r.nao_verificado, formato_ok: r.formato_ok });
  } catch (e) {
    fio(meu).push({ papel: 'assistente', erro: true, texto: e.message || 'Não consegui responder.' });
  }
  pendente = null;
  desenhar();
}

async function responderCartao(acao, i) {
  const m = fio(bot)[i];
  if (!m || !m.proposta || m.estado !== 'pendente') return;
  if (acao === 'agenda-nao') { m.estado = 'cancelado'; return desenhar(); }
  try {
    const t = await api.agendaCriar(m.proposta);
    m.estado = 'confirmado';
    m.id = t.id;
  } catch (e) {
    m.estado = 'erro';
    m.erro = e.message;
  }
  desenhar();
}

// Respostas de mensagens agendadas viram mensagens na conversa do bot certo.
async function buscarAgendadas() {
  let ag;
  try { ag = await api.agenda(); } catch (e) { return false; }
  let novas = false;
  let abrir = null;   // conversa que recebeu a primeira resposta nova
  for (const t of ag.tarefas) {
    if (t.vista || vistas.has(t.id) || !['executada', 'falhou', 'perdida'].includes(t.estado)) continue;
    vistas.add(t.id);
    novas = true;
    const f = fio(t.bot);
    if (t.estado === 'executada' && t.resultado) {
      f.push({ papel: 'assistente', texto: t.resultado.resposta, fontes: t.resultado.fontes, nv: t.resultado.nao_verificado,
        formato_ok: t.resultado.formato_ok, agendada: t.quando_texto, atrasada: t.atrasada });
    } else {
      f.push({ papel: 'assistente', erro: true, texto: `A mensagem agendada para ${t.quando_texto} não foi enviada: ${t.erro || 'falha ao responder'}` });
    }
    if (!abrir && t.bot !== bot) abrir = t.bot;
    api.agendaVista(t.id).catch(() => {});
  }
  if (abrir) bot = abrir;   // mostra a resposta sem você precisar procurar o bot
  return novas;
}

export async function render() {
  parar();
  await buscarAgendadas();
  const [s, st, c] = await Promise.all([api.semana(), api.chatStatus(), api.carteira()]);
  bots = st.bots;
  if (!bots.some(b => b.id === bot)) bot = bots[0].id;
  tickers = s.ranking.map(r => r.ticker);
  const b = atual();
  const pilula = st.disponivel ? '<span class="pill ok">Online</span>' : '<span class="pill idle">Offline</span>';
  const barra = bots.map(x => `<button type="button" class="bot" data-bot="${esc(x.id)}" aria-pressed="${x.id === bot}" title="${esc(x.descricao)}">`
    + `<span class="m" aria-hidden="true">${esc(x.mono)}</span>${esc(x.nome)}</button>`).join('');
  const exemplo = `me manda o resumo do ${b.nome} amanhã às 9`;
  const chips = `<button type="button" class="chip" data-preencher="${esc(exemplo)}"${st.disponivel ? '' : ' disabled'}>Agendar uma mensagem</button>` + sugestoes().map(t => `<button type="button" class="chip" data-sug="${esc(t)}"${st.disponivel ? '' : ' disabled'}>${esc(t)}</button>`).join('');
  const toggle = !c.vazio
    ? `<button type="button" class="chip${usarCarteira ? ' on' : ''}" id="usar-carteira" aria-pressed="${usarCarteira}">Usar minha carteira</button>` : '';
  const aviso = !st.disponivel ? obj('Chat indisponível', 'O comando claude não foi encontrado no PATH deste computador.', { aviso: true }) : '';
  const html = cabecalho({ titulo: 'Chat', sub: `${b.nome.toUpperCase()} · SEMANA ${dataCurta(s.data)}`, direita: pilula })
    + `<div class="chat-layout"><aside class="painel-bots" aria-label="Bots">${bots.map(cartaoBot).join('')}</aside><div class="coluna-chat">`
    + `<div class="bots" role="group" aria-label="Bots">${barra}</div>`
    + `<div class="chat"><div class="msgs" id="msgs" role="log" aria-live="polite" aria-label="Conversa com ${esc(b.nome)}">${aviso}${listaHtml()}</div>`
    + `<div class="sugestoes" aria-label="Sugestões">${toggle}${chips}</div>`
    + `<p class="nota-carteira" id="nota-carteira"${usarCarteira ? '' : ' hidden'}>Enviando ao Claude só peso, nota e ação das suas posições, sem quantidades nem valores.</p>`
    + `<form class="compor" id="compor"><textarea id="pergunta" rows="1" maxlength="1000" placeholder="Pergunte ao bot ${esc(b.nome)}" aria-label="Pergunta"${st.disponivel ? '' : ' disabled'}>${esc(rascunho)}</textarea>`
    + `<button type="submit" class="enviar" id="enviar" aria-label="Enviar" disabled>${icone('send')}</button></form>`
    + '<p class="rodape-chat">Respostas de IA sobre os dados da semana. Rótulos são do modelo, não ordens. Não é recomendação.</p></div></div></div>';
  return {
    html,
    montar(raiz, recarregar) {
      const q = raiz.querySelector('#pergunta');
      const f = raiz.querySelector('#compor');
      const ajustar = () => {
        rascunho = q.value;
        q.style.height = 'auto';
        q.style.height = Math.min(q.scrollHeight, 120) + 'px';
        raiz.querySelector('#enviar').disabled = pendente !== null || !q.value.trim();
      };
      q.addEventListener('input', ajustar);
      q.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); f.requestSubmit(); }
      });
      f.addEventListener('submit', e => {
        e.preventDefault();
        const t = q.value;
        q.value = ''; rascunho = ''; ajustar();
        enviar(t);
      });
      raiz.querySelectorAll('[data-sug]').forEach(x => x.addEventListener('click', () => enviar(x.dataset.sug)));
      raiz.querySelectorAll('[data-preencher]').forEach(x => x.addEventListener('click', () => {
        q.value = x.dataset.preencher;
        ajustar();
        q.focus();
        q.setSelectionRange(q.value.length, q.value.length);
      }));
      raiz.querySelector('#msgs').addEventListener('click', e => {
        const b2 = e.target.closest('[data-acao]');
        if (b2) responderCartao(b2.dataset.acao, Number(b2.dataset.i));
      });
      timer = setInterval(async () => { if (await buscarAgendadas()) recarregar(); }, 20000);
      raiz.querySelectorAll('[data-bot]').forEach(x => x.addEventListener('click', () => {
        if (x.dataset.bot === bot) return;
        bot = x.dataset.bot;
        recarregar();   // troca a conversa, as sugestões e o título
      }));
      const tg = raiz.querySelector('#usar-carteira');
      if (tg) tg.addEventListener('click', () => {
        usarCarteira = !usarCarteira;
        tg.classList.toggle('on', usarCarteira);
        tg.setAttribute('aria-pressed', String(usarCarteira));
        raiz.querySelector('#nota-carteira').hidden = !usarCarteira;
      });
      ajustar();
      const m = raiz.querySelector('#msgs');
      m.scrollTop = m.scrollHeight;
      const ativo = raiz.querySelector('.bot[aria-pressed="true"]');
      if (ativo) ativo.scrollIntoView({ inline: 'center', block: 'nearest' });
      const cartao = raiz.querySelector('.cartao-bot[aria-pressed="true"]');
      if (cartao && cartao.offsetParent) cartao.scrollIntoView({ block: 'nearest' });   // painel lateral: mantém o bot ativo à vista
      raiz.querySelectorAll('.bots, .sugestoes').forEach(rolagemHorizontal);
    },
  };
}
