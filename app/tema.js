// Alternador de tema. Claro é o padrão; a escolha do usuário (Escuro/Claro) fica salva neste navegador.
(function () {
  var root = document.documentElement;
  var KEY = 'adv-theme';

  function atual() {
    return root.getAttribute('data-theme') || 'light';
  }

  function sync() {
    var t = atual();
    var d = document.getElementById('t-dark');
    var l = document.getElementById('t-light');
    if (d) d.setAttribute('aria-pressed', String(t === 'dark'));
    if (l) l.setAttribute('aria-pressed', String(t === 'light'));
  }

  function definir(t) {
    root.setAttribute('data-theme', t);
    try { localStorage.setItem(KEY, t); } catch (e) {}
    sync();
  }

  try {
    var q = new URLSearchParams(location.search).get('tema');   // ?tema=light|dark força o tema (conferência visual)
    if (q === 'light' || q === 'dark') localStorage.setItem(KEY, q);
  } catch (e) {}

  try {
    var s = localStorage.getItem(KEY);
    if (s === 'light' || s === 'dark') root.setAttribute('data-theme', s);
  } catch (e) {}
  if (!root.getAttribute('data-theme')) root.setAttribute('data-theme', 'light');   // padrão, mesmo com o sistema em escuro

  document.addEventListener('DOMContentLoaded', function () {
    var d = document.getElementById('t-dark');
    var l = document.getElementById('t-light');
    if (d) d.onclick = function () { definir('dark'); };
    if (l) l.onclick = function () { definir('light'); };
    sync();
  });
})();
