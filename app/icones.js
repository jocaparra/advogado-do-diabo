// Sprite de ícones (traços da referência). Uso: <svg class="i"><use href="#scale"/></svg>
(function () {
  var paths = {
    scale: 'M12 3v18M5 21h14M5 7h14M5 7l-3 7a3 3 0 0 0 6 0ZM19 7l-3 7a3 3 0 0 0 6 0Z',
    list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
    file: 'M6 3h8l5 5v13H6ZM14 3v5h5M9 13h6M9 17h6',
    wallet: 'M4 7h15a1 1 0 0 1 1 1v11H5a1 1 0 0 1-1-1ZM4 7V6a2 2 0 0 1 2-2h11M16 13h.01',
    chart: 'M3 17l6-6 4 4 8-8M15 7h6v6',
    cog: 'M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6',
    alert: 'M12 3 2 20h20ZM12 10v5M12 18h.01',
    check: 'M20 6 9 17l-5-5',
    x: 'M18 6 6 18M6 6l12 12',
    back: 'm15 18-6-6 6-6',
    play: 'M7 4l13 8-13 8Z',
    upload: 'M12 16V4M7 9l5-5 5 5M4 20h16',
    chat: 'M21 12a8 8 0 0 1-11.6 7.1L3 21l1.9-5.4A8 8 0 1 1 21 12Z',
    send: 'M22 2 11 13M22 2l-7 20-4-9-9-4Z'
  };
  var ns = 'http://www.w3.org/2000/svg';
  var svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('width', '0');
  svg.setAttribute('height', '0');
  svg.setAttribute('aria-hidden', 'true');
  svg.style.position = 'absolute';
  Object.keys(paths).forEach(function (id) {
    var sym = document.createElementNS(ns, 'symbol');
    sym.setAttribute('id', id);
    sym.setAttribute('viewBox', '0 0 24 24');
    var p = document.createElementNS(ns, 'path');
    p.setAttribute('d', paths[id]);
    sym.appendChild(p);
    svg.appendChild(sym);
  });
  document.body.insertBefore(svg, document.body.firstChild);
})();
