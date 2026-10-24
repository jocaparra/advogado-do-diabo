// Verifica o front-end sem navegador: tema, escape de HTML e componentes puros. Saída: JSON com falhas.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath, pathToFileURL } from 'node:url';

const aqui = path.dirname(fileURLToPath(import.meta.url));
const app = path.resolve(aqui, '../../app');
const falhas = [];
const igual = (nome, obtido, esperado) => {
  if (JSON.stringify(obtido) !== JSON.stringify(esperado)) falhas.push(`${nome}: obtido ${JSON.stringify(obtido)}, esperado ${JSON.stringify(esperado)}`);
};
const ok = (nome, cond) => { if (!cond) falhas.push(nome); };

// ---- tema.js rodando com um DOM mínimo ----
function rodarTema({ guardado = null, sistemaClaro = false, consulta = '' } = {}) {
  const attrs = {};
  const botoes = {};
  const ouvintes = [];
  const doc = {
    documentElement: { getAttribute: k => (k in attrs ? attrs[k] : null), setAttribute: (k, v) => { attrs[k] = String(v); } },
    getElementById: id => botoes[id] || (botoes[id] = { attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } }),
    addEventListener: (ev, fn) => ouvintes.push(fn),
  };
  const mem = guardado ? { 'adv-theme': guardado } : {};
  const ctx = {
    document: doc, URLSearchParams, location: { search: consulta },
    localStorage: { getItem: k => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = v; } },
    matchMedia: () => ({ matches: sistemaClaro }),
  };
  vm.runInNewContext(fs.readFileSync(path.join(app, 'tema.js'), 'utf8'), ctx);
  ouvintes.forEach(fn => fn());
  return { tema: attrs['data-theme'], claroPressionado: botoes['t-light']?.attrs['aria-pressed'], escuroPressionado: botoes['t-dark']?.attrs['aria-pressed'], mem, clicar: id => botoes[id].onclick() };
}

let t = rodarTema({ sistemaClaro: false });
igual('claro é o padrão mesmo com o sistema em escuro', t.tema, 'light');
igual('botão Claro marcado', t.claroPressionado, 'true');
igual('botão Escuro desmarcado', t.escuroPressionado, 'false');
igual('escolha salva é respeitada', rodarTema({ guardado: 'dark' }).tema, 'dark');
igual('valor salvo inválido cai no claro', rodarTema({ guardado: 'roxo' }).tema, 'light');
igual('?tema=dark força escuro', rodarTema({ consulta: '?tema=dark' }).tema, 'dark');
t = rodarTema({});
t.clicar('t-dark');
igual('clicar em Escuro grava a escolha', t.mem['adv-theme'], 'dark');

// ---- util e componentes ----
const util = await import(pathToFileURL(path.join(app, 'js/util.js')).href);
const comp = await import(pathToFileURL(path.join(app, 'js/componentes.js')).href);

igual('esc neutraliza HTML', util.esc('<img src=x onerror="a()">&\''), '&lt;img src=x onerror=&quot;a()&quot;&gt;&amp;&#39;');
ok('ausente: null', util.ausente(null));
ok('ausente: "não verificado (motivo)"', util.ausente('Não verificado (sem fonte)'));
ok('ausente: zero não é ausente', !util.ausente(0));
igual('dataBr', util.dataBr('2026-10-05'), '05/10/2026');
igual('nf pt-BR', util.nf(21.44, 1), '21,4');
igual('nf rejeita não numérico', util.nf('abc', 1), null);
igual('pct com sinal', util.pct(2.14, 1, true), '+2,1%');

igual('nota alta', /score hi/.test(comp.score(7)), true);
igual('nota média', /score mid/.test(comp.score(5.9)), true);
igual('nota baixa', /score lo/.test(comp.score(3.1)), true);
ok('nota ausente vira n/d, sem cor', /n\/d/.test(comp.score(null)) && !/hi|mid|lo/.test(comp.score(null)));
igual('pill comprar', /pill ok/.test(comp.pill('comprar')), true);
igual('pill aguardar', /pill warn/.test(comp.pill('Aguardar')), true);
igual('pill evitar', /pill bad/.test(comp.pill('evitar')), true);
ok('pill desconhecido vira não verificado', /tag nv/.test(comp.pill(null)));
igual('certeza média = 2 barras', (comp.cert('média').match(/class="on"/g) || []).length, 2);
igual('certeza baixa = 1 barra', (comp.cert('baixa').match(/class="on"/g) || []).length, 1);
igual('certeza ausente não desenha', comp.cert(null), '');
ok('tag mostra fonte e data', comp.tag('CVM ITR', '2026-08-14').includes('CVM ITR · 14/08/2026'));
ok('tag escapa a fonte', !comp.tag('<b>x</b>', null).includes('<b>'));
ok('fonte ausente vira tracejada', /tag nv/.test(comp.fonte('não verificado', null)));
ok('obj escapa o texto', !comp.obj('K', '<script>x</script>').includes('<script>'));

const cen = { bear: { valor: 28 }, base: { valor: 41 }, bull: { valor: 55 } };
const r = comp.scen(cen, 36);
ok('régua: bear em 20%', r.includes('left:20.0%"><b>R$ 28'));
ok('régua: bull em 87%', r.includes('left:87.0%"><b>R$ 55'));
ok('régua: marcador do preço', r.includes('preço R$ 36'));
ok('régua sem preço não quebra', !comp.scen(cen, null).includes('preço'));
const fora = comp.scen({ bear: { valor: 6 }, base: { valor: 9 }, bull: { valor: 14 } }, 49);
ok('preço acima do bull não sai da escala', [...fora.matchAll(/left:([\d.]+)%/g)].every(m => +m[1] >= 0 && +m[1] <= 100));

const g = comp.chart([{ bot: 1, ibov: 0.5, rotulo: '05/10' }, { bot: 2, ibov: 1, rotulo: '12/10' }], 'teste');
ok('gráfico tem Bot e Ibovespa', g.includes('var(--fg)') && g.includes('var(--info)'));
ok('gráfico com um ponto só não quebra', comp.chart([{ bot: 1, ibov: 1, rotulo: 'x' }], 't').includes('polyline'));

// ---- chat: texto da resposta e abas ----
const tk = ['AAAA3', 'BBBB4'];
const t1 = util.textoComLinks('Veja aaaa3 e BBBB4.\n\nSegundo parágrafo, ZZZZ3 não existe.', tk);
ok('ticker conhecido vira link para o dossiê', t1.includes('<a href="#/dossie/AAAA3">aaaa3</a>') && t1.includes('<a href="#/dossie/BBBB4">BBBB4</a>'));
ok('ticker desconhecido não vira link', !t1.includes('ZZZZ3</a>') && t1.includes('ZZZZ3'));
igual('dois parágrafos', (t1.match(/<p>/g) || []).length, 2);
const t2 = util.textoComLinks('<img src=x onerror=alert(1)> AAAA3 <script>x</script>', tk);
ok('resposta do modelo não injeta HTML', !t2.includes('<img') && !t2.includes('<script') && t2.includes('&lt;img'));
ok('link só de ticker conhecido mesmo com HTML ao redor', t2.includes('<a href="#/dossie/AAAA3">AAAA3</a>'));
igual('texto vazio não gera parágrafo', util.textoComLinks('   ', tk), '');
ok('ticker com href malicioso não passa', !util.textoComLinks('a"onmouseover=x AAAA3', tk).includes('onmouseover=x"'));

const index = fs.readFileSync(path.join(app, 'index.html'), 'utf8');
const abas = [...index.matchAll(/data-aba="([a-z]+)"/g)].map(m => m[1]);
igual('abas na ordem', abas, ['semana', 'chat', 'carteira', 'desempenho', 'rotina']);
ok('não há mais aba de Dossiê', !abas.includes('dossie') && !/>Dossiê</.test(index));
const appjs = fs.readFileSync(path.join(app, 'js/app.js'), 'utf8');
ok('dossiê continua roteável, ligado à aba da semana', /dossie: 'semana'/.test(appjs) && /objecoes: 'semana'/.test(appjs));
const semanaJs = fs.readFileSync(path.join(app, 'js/telas/semana.js'), 'utf8');
ok('clicar na ação da semana leva ao dossiê', semanaJs.includes('#/dossie/${r.ticker}'));

// ---- chat: bots e catálogo ----
const chatJs = fs.readFileSync(path.join(app, 'js/telas/chat.js'), 'utf8');
ok('chat tem uma conversa por bot', /const fios = \{\}/.test(chatJs) && /fio\(meu\)/.test(chatJs));
ok('chat envia o bot escolhido ao servidor', /api\.chat\(texto, historico, usarCarteira, meu\)/.test(chatJs));
ok('erro do chat usa o componente de aviso, não cor própria', /obj\('Não consegui responder'/.test(chatJs));
const apiJs = fs.readFileSync(path.join(app, 'js/api.js'), 'utf8');
ok('api.chat leva o bot', /chat: \(pergunta, historico, carteira, bot\)/.test(apiJs));
const catalogo = fs.readFileSync(path.join(app, 'catalogo.html'), 'utf8');
for (const c of ['class="bot"', 'class="bub"', 'class="fontes"', 'digitando', 'class="compor"', 'class="enviar"']) ok(`catálogo mostra ${c}`, catalogo.includes(c));
ok('catálogo e app carregam chat.css', catalogo.includes('chat.css') && index.includes('chat.css'));
ok('catálogo não lista mais a aba Dossiê', !/>Dossiê</.test(catalogo.replace(/<h3>[^<]*<\/h3>/g, '')));

// ---- faixas que rolam: mouse, roda, teclado e bordas ----
const { rolagemHorizontal } = await import(pathToFileURL(path.join(app, 'js/rolagem.js')).href);

function faixa({ largura = 300, visivel = 100, botoes = 4 } = {}) {
  const ouv = {};
  const props = {};
  const itens = Array.from({ length: botoes }, (_, i) => ({ i, focado: false, focus() { this.focado = true; foco = this; }, scrollIntoView() {} }));
  let foco = null;
  const el = {
    scrollLeft: 0, scrollWidth: largura, clientWidth: visivel, classes: new Set(),
    classList: { add: c => el.classes.add(c), remove: c => el.classes.delete(c) },
    style: { setProperty: (k, v) => { props[k] = v; } },
    addEventListener: (t, fn, o) => { (ouv[t] = ouv[t] || []).push({ fn, o }); },
    querySelectorAll: () => itens, setPointerCapture() { el.capturado = true; },
  };
  const emite = (tipo, e) => { e = { preventDefault() { e.prevenido = true; }, stopPropagation() { e.parou = true; }, ...e }; (ouv[tipo] || []).forEach(h => h.fn(e)); return e; };
  rolagemHorizontal(el);
  return { el, props, itens, emite, ouv, foco: () => foco };
}

let f = faixa();
igual('bordas: começo sem esmaecido à esquerda e com à direita', [f.props['--fe'], f.props['--fd']], ['0', '1']);
f.el.scrollLeft = 100; f.emite('scroll', {});
igual('bordas: no meio, as duas', [f.props['--fe'], f.props['--fd']], ['1', '1']);
f.el.scrollLeft = 200; f.emite('scroll', {});
igual('bordas: no fim, só à esquerda', [f.props['--fe'], f.props['--fd']], ['1', '0']);
f = faixa({ largura: 100, visivel: 100 });
igual('sem overflow: sem esmaecido', [f.props['--fe'], f.props['--fd']], ['0', '0']);

f = faixa();
let e = f.emite('wheel', { deltaX: 0, deltaY: 60 });
ok('roda vertical rola a faixa para a direita', f.el.scrollLeft === 60 && e.prevenido);
e = f.emite('wheel', { deltaX: 0, deltaY: -20 });
ok('roda para cima volta', f.el.scrollLeft === 40 && e.prevenido);
f.el.scrollLeft = 200;
e = f.emite('wheel', { deltaX: 0, deltaY: 50 });
ok('no fim, a roda segue para a página (não prende o usuário)', !e.prevenido && f.el.scrollLeft === 200);
f.el.scrollLeft = 0;
e = f.emite('wheel', { deltaX: 0, deltaY: -50 });
ok('no começo, a roda para cima segue para a página', !e.prevenido);
e = faixa().emite('wheel', { deltaX: 40, deltaY: 5 });
ok('gesto horizontal do trackpad fica com o navegador', !e.prevenido);
e = faixa({ largura: 100, visivel: 100 }).emite('wheel', { deltaX: 0, deltaY: 50 });
ok('sem overflow, a roda não é interceptada', !e.prevenido);

f = faixa(); f.el.scrollLeft = 50;
f.emite('pointerdown', { pointerType: 'mouse', button: 0, clientX: 200, pointerId: 1 });
f.emite('pointermove', { pointerId: 1, clientX: 197 });
ok('movimento abaixo do limiar não é arrasto', f.el.scrollLeft === 50 && !f.el.classes.has('arrastando'));
f.emite('pointermove', { pointerId: 1, clientX: 150 });
ok('arrastar para a esquerda rola para a direita', f.el.scrollLeft === 100 && f.el.classes.has('arrastando') && f.el.capturado);
f.emite('pointerup', { pointerId: 1 });
ok('soltar encerra o arrasto', !f.el.classes.has('arrastando'));
e = f.emite('click', {});
ok('o clique depois de arrastar é descartado', e.prevenido && e.parou);
e = f.emite('click', {});
ok('o clique seguinte volta a funcionar', !e.prevenido);

f = faixa();
f.emite('pointerdown', { pointerType: 'mouse', button: 0, clientX: 100, pointerId: 1 });
f.emite('pointermove', { pointerId: 1, clientX: 98 });
f.emite('pointerup', { pointerId: 1 });
e = f.emite('click', {});
ok('clique sem arrastar não é descartado', !e.prevenido);

f = faixa();
f.emite('pointerdown', { pointerType: 'touch', button: 0, clientX: 200, pointerId: 2 });
f.emite('pointermove', { pointerId: 2, clientX: 100 });
ok('toque fica com a rolagem nativa', f.el.scrollLeft === 0 && !f.el.classes.has('arrastando'));
f.emite('pointerdown', { pointerType: 'mouse', button: 2, clientX: 200, pointerId: 3 });
f.emite('pointermove', { pointerId: 3, clientX: 100 });
ok('botão direito não arrasta', f.el.scrollLeft === 0);
f.emite('pointerdown', { pointerType: 'mouse', button: 0, clientX: 200, pointerId: 4 });
f.emite('pointercancel', { pointerId: 4 });
f.emite('pointermove', { pointerId: 4, clientX: 100 });
ok('cancelar o ponteiro encerra o arrasto', f.el.scrollLeft === 0);

f = faixa();
const alvo = f.itens[1];
e = f.emite('keydown', { key: 'ArrowRight', target: alvo });
ok('seta direita foca o próximo', f.foco() === f.itens[2] && e.prevenido);
f.emite('keydown', { key: 'ArrowLeft', target: alvo });
ok('seta esquerda foca o anterior', f.foco() === f.itens[0]);
f.emite('keydown', { key: 'End', target: alvo });
ok('End vai ao último', f.foco() === f.itens[3]);
e = f.emite('keydown', { key: 'ArrowRight', target: f.itens[3] });
ok('seta direita no último não faz nada além de segurar a rolagem', f.foco() === f.itens[3] && e.prevenido);
e = f.emite('keydown', { key: 'a', target: alvo });
ok('outras teclas passam', !e.prevenido);
ok('faixa nula não quebra', rolagemHorizontal(null) === undefined);

const chatJs2 = fs.readFileSync(path.join(app, 'js/telas/chat.js'), 'utf8');
ok('chat aplica a rolagem na barra de bots e nas perguntas', /querySelectorAll\('\.bots, \.sugestoes'\)\.forEach\(rolagemHorizontal\)/.test(chatJs2));
const cssChat = fs.readFileSync(path.join(app, 'chat.css'), 'utf8');
ok('CSS: arrastar com cursor e sem seleção de texto', /cursor:grab/.test(cssChat) && /user-select:none/.test(cssChat) && /\.arrastando/.test(cssChat));
ok('CSS: rolagem sem vazar para a página', /overscroll-behavior-x:contain/.test(cssChat));

// ---- agendamento: chat, rotina, api e catálogo ----
const chatJs3 = fs.readFileSync(path.join(app, 'js/telas/chat.js'), 'utf8');
ok('chat pergunta ao servidor se a mensagem é um agendamento antes de usar o Claude', chatJs3.indexOf('api.agendaInterpretar') < chatJs3.indexOf('api.chat(texto'));
ok('agendamento só é criado depois do botão Confirmar', /data-acao="agenda-sim"/.test(chatJs3) && /api\.agendaCriar\(m\.proposta\)/.test(chatJs3) && !/agendaCriar\([^)]*\).*interpretar/.test(chatJs3));
ok('cartão de agendamento só age quando pendente', /m\.estado !== 'pendente'\) return/.test(chatJs3));
ok('chat para o polling ao sair da aba', /export function parar\(\)/.test(chatJs3) && /chat\.parar\(\)/.test(fs.readFileSync(path.join(app, 'js/app.js'), 'utf8')));
ok('mensagens de agendamento não entram no histórico enviado ao Claude', /!m\.proposta && !m\.aviso/.test(chatJs3));
ok('resposta agendada vai para a conversa do bot que a recebeu', /const f = fio\(t\.bot\)/.test(chatJs3));
const rotinaJs = fs.readFileSync(path.join(app, 'js/telas/rotina.js'), 'utf8');
ok('rotina lista e cancela mensagens agendadas', /api\.agenda\(\)/.test(rotinaJs) && /api\.agendaCancelar/.test(rotinaJs));
const apiJs2 = fs.readFileSync(path.join(app, 'js/api.js'), 'utf8');
for (const fn of ['agenda:', 'agendaInterpretar:', 'agendaCriar:', 'agendaCancelar:', 'agendaVista:']) ok(`api tem ${fn}`, apiJs2.includes(fn));
ok('api.agendaCriar manda só bot, pergunta e quando', /agendaCriar: p => req\('POST', '\/api\/agenda', \{ bot: p\.bot, pergunta: p\.pergunta, quando: p\.quando \}\)/.test(apiJs2));
const cat2 = fs.readFileSync(path.join(app, 'catalogo.html'), 'utf8');
ok('catálogo mostra o cartão de agendamento', cat2.includes('cartao-agenda') && cat2.includes('class="agendada"'));

// ---- layout web e cartão de bot (kit de design) ----
const appCss = fs.readFileSync(path.join(app, 'app.css'), 'utf8');
const baseCss = fs.readFileSync(path.join(app, 'base.css'), 'utf8');
const chatCss2 = fs.readFileSync(path.join(app, 'chat.css'), 'utf8');
ok('web: menu lateral e aviso legal no topo a partir de 960 px', /@media \(min-width:960px\)/.test(appCss) && /grid-template-areas:"marca aviso" "abas main" "tema main"/.test(appCss));
ok('web: abas viram menu vertical com item ativo invertido', /\.tabs\{grid-area:abas;[^}]*flex-direction:column/.test(appCss) && /\.tabs a\.on\{background:var\(--inv\)/.test(appCss));
ok('tablet: coluna central um pouco mais larga', /@media \(min-width:520px\) and \(max-width:959px\)/.test(appCss));
ok('celular não muda: duas colunas só em tela larga', /\.colunas,\.col\{display:contents\}/.test(appCss));
ok('chat: painel de cartões só a partir de 1180 px', /@media \(min-width:1180px\)/.test(chatCss2) && /\.painel-bots\{display:none\}/.test(chatCss2));
for (const c of ['.bh{', '.av{', '.av.inv{', '.task{', '.apps{']) ok(`base.css traz ${c} do kit de design`, baseCss.includes(c));
ok('cartão de bot mostra status, arquivos lidos e data dos dados', /pill warn">Sem arquivo/.test(chatJs3) && /a\.existe \? tag\(a\.nome\) : tagNv/.test(chatJs3) && /Dados de \$\{dataBr/.test(chatJs3));
ok('cartão de bot é botão com aria-pressed (teclado e leitor de tela)', /<button type="button" class="card cartao-bot"[^`]*aria-pressed/.test(chatJs3));
ok('catálogo traz o cartão de bot', cat2.includes('<h3>Cartão de bot</h3>') && cat2.includes('class="bh"'));
for (const t of ['dossie.js', 'objecoes.js', 'carteira.js', 'desempenho.js', 'rotina.js']) {
  ok(`${t} usa duas colunas na web`, /colunas\(/.test(fs.readFileSync(path.join(app, 'js/telas', t), 'utf8')));
}

// nenhuma cor ou raio solto nos CSS do app (só tokens.css define valores)
for (const f of ['base.css', 'app.css', 'catalogo.css', 'chat.css']) {
  const css = fs.readFileSync(path.join(app, f), 'utf8');
  ok(`${f} sem cor hexadecimal solta`, !/#[0-9a-fA-F]{3,8}\b/.test(css));
  ok(`${f} sem 999px solto`, !/999px/.test(css));
}

console.log(JSON.stringify({ falhas }));
process.exit(falhas.length ? 1 : 0);
