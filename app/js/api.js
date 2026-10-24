// Cliente da API local (src/servidor.py). Escritas levam X-Adv, que o servidor exige.
async function req(metodo, caminho, corpo) {
  const opt = { method: metodo, headers: {} };
  if (metodo !== 'GET') {
    opt.headers['X-Adv'] = '1';
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(corpo || {});
  }
  const r = await fetch(caminho, opt);
  let j = null;
  try { j = await r.json(); } catch (e) { /* sem corpo */ }
  if (!r.ok) {
    const e = new Error((j && j.erro) || (j && j.mensagem) || `erro ${r.status}`);
    e.status = r.status;
    throw e;
  }
  return j;
}

export const api = {
  semana: () => req('GET', '/api/semana'),
  dossie: tk => req('GET', `/api/dossie/${encodeURIComponent(tk)}`),
  objecoes: tk => req('GET', `/api/objecoes/${encodeURIComponent(tk)}`),
  desempenho: () => req('GET', '/api/desempenho'),
  rotina: () => req('GET', '/api/rotina'),
  iniciarRotina: () => req('POST', '/api/rotina/iniciar', { confirmar: true }),
  carteira: () => req('GET', '/api/minha-carteira'),
  importarCarteira: csv => req('POST', '/api/minha-carteira', { csv }),
  esquecerCarteira: () => req('DELETE', '/api/minha-carteira'),
  chatStatus: () => req('GET', '/api/chat/status'),
  chat: (pergunta, historico, carteira, bot) => req('POST', '/api/chat', { pergunta, historico, carteira, bot }),
  agenda: () => req('GET', '/api/agenda'),
  agendaInterpretar: (texto, bot) => req('POST', '/api/agenda/interpretar', { texto, bot }),
  agendaCriar: p => req('POST', '/api/agenda', { bot: p.bot, pergunta: p.pergunta, quando: p.quando }),
  agendaCancelar: id => req('DELETE', `/api/agenda/${encodeURIComponent(id)}`),
  agendaVista: id => req('POST', `/api/agenda/${encodeURIComponent(id)}/vista`),
  plano: () => req('GET', '/api/plano'),
  salvarPlano: p => req('PUT', '/api/plano', p),
  apagarPlano: () => req('DELETE', '/api/plano'),
};
