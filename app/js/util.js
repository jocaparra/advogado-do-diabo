// Formatação e escape. Todo texto vindo dos arquivos passa por esc() antes de virar HTML.
const MESES = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'];

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function norm(s) {
  return String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').trim().toLowerCase();
}

// Valor ausente: nulo, vazio ou o texto "não verificado" dos agentes.
export function ausente(v) {
  return v === null || v === undefined || v === '' || /^n[ãa]o verificado/i.test(String(v));
}

export function nf(v, casas = 1) {
  if (typeof v !== 'number' || !isFinite(v)) return null;
  return v.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

export function brl(v, casas = 2) {
  const n = nf(v, casas);
  return n === null ? null : 'R$ ' + n;
}

export function pct(v, casas = 1, sinal = false) {
  const n = nf(v, casas);
  if (n === null) return null;
  return (sinal && v > 0 ? '+' : '') + n + '%';
}

// 2026-10-05 -> 05/10/2026 (outros formatos voltam sem mudança)
export function dataBr(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso ?? ''));
  return m ? `${m[3]}/${m[2]}/${m[1]}` : String(iso ?? '');
}

export function dataCurta(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso ?? ''));
  return m ? `${m[3]}/${m[2]}` : String(iso ?? '');
}

export function dataExtensa(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso ?? ''));
  return m ? `${m[3]} ${MESES[+m[2] - 1]} ${m[1]}` : '';
}

export function lembrar(chave, valor) {
  try { if (valor === undefined) return sessionStorage.getItem(chave); sessionStorage.setItem(chave, valor); } catch (e) { /* sem armazenamento */ }
  return null;
}

// Texto de resposta -> HTML seguro: escapa tudo, separa parágrafos e liga cada ticker conhecido ao dossiê.
export function textoComLinks(texto, tickers) {
  const conhecidos = new Set(tickers || []);
  return String(texto ?? '').split(/\n{2,}/).map(par => {
    const html = esc(par.trim()).replace(/\b[A-Za-z]{4}\d{1,2}\b/g, t => (
      conhecidos.has(t.toUpperCase()) ? `<a href="#/dossie/${t.toUpperCase()}">${t}</a>` : t));
    return `<p>${html.replace(/\n/g, '<br>')}</p>`;
  }).filter(p => p !== '<p></p>').join('');
}
