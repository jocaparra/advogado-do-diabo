// Faixas que rolam na horizontal (barra de bots, sugestões): dedo (nativo), arrastar com o mouse,
// roda do mouse e setas do teclado, com um esmaecido nas bordas que indica que há mais conteúdo.
const LIMIAR_ARRASTO = 5;   // px: abaixo disso é clique, não arrasto

export function rolagemHorizontal(el) {
  if (!el) return;
  let inicio = null;        // { x, esq, id } enquanto o botão do mouse está apertado
  let arrastou = false;

  const atualizarBordas = () => {
    const max = el.scrollWidth - el.clientWidth;
    el.style.setProperty('--fe', max > 1 && el.scrollLeft > 1 ? '1' : '0');
    el.style.setProperty('--fd', max > 1 && el.scrollLeft < max - 1 ? '1' : '0');
  };

  // Roda do mouse (vertical) vira rolagem horizontal, mas só enquanto ainda há para onde rolar.
  el.addEventListener('wheel', e => {
    if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;   // gesto já horizontal (trackpad): nativo
    const max = el.scrollWidth - el.clientWidth;
    if (max <= 1) return;
    const vaiParaDireita = e.deltaY > 0;
    if ((vaiParaDireita && el.scrollLeft >= max - 1) || (!vaiParaDireita && el.scrollLeft <= 0)) return;
    e.preventDefault();
    el.scrollLeft += e.deltaY;
  }, { passive: false });

  // Arrastar com o mouse. Toque e caneta usam a rolagem nativa do navegador.
  el.addEventListener('pointerdown', e => {
    if (e.pointerType !== 'mouse' || e.button !== 0) return;
    inicio = { x: e.clientX, esq: el.scrollLeft, id: e.pointerId };
    arrastou = false;
  });
  el.addEventListener('pointermove', e => {
    if (!inicio || e.pointerId !== inicio.id) return;
    const dx = e.clientX - inicio.x;
    if (!arrastou && Math.abs(dx) < LIMIAR_ARRASTO) return;
    if (!arrastou) {
      arrastou = true;
      el.classList.add('arrastando');
      if (el.setPointerCapture) { try { el.setPointerCapture(e.pointerId); } catch (err) { /* ponteiro já liberado */ } }
    }
    el.scrollLeft = inicio.esq - dx;
  });
  const soltar = e => {
    if (!inicio || (e && e.pointerId !== inicio.id)) return;
    inicio = null;
    el.classList.remove('arrastando');
  };
  el.addEventListener('pointerup', soltar);
  el.addEventListener('pointercancel', soltar);
  // Depois de arrastar, o clique que o navegador dispara ao soltar não pode apertar o botão sob o cursor.
  el.addEventListener('click', e => {
    if (arrastou) { e.preventDefault(); e.stopPropagation(); arrastou = false; }
  }, true);

  // Setas, Home e End movem o foco entre os botões da faixa; o navegador rola até o foco.
  el.addEventListener('keydown', e => {
    const itens = [...el.querySelectorAll('button:not(:disabled)')];
    const i = itens.indexOf(e.target);
    if (i < 0) return;
    const destinos = { ArrowRight: itens[i + 1], ArrowLeft: itens[i - 1], Home: itens[0], End: itens[itens.length - 1] };
    if (!(e.key in destinos)) return;            // outras teclas seguem o comportamento normal
    e.preventDefault();
    const destino = destinos[e.key];             // nas pontas não há vizinho: o foco fica onde está
    if (destino) { destino.focus(); destino.scrollIntoView({ inline: 'nearest', block: 'nearest' }); }
  });

  el.addEventListener('scroll', atualizarBordas, { passive: true });
  if (typeof window !== 'undefined') window.addEventListener('resize', atualizarBordas);
  atualizarBordas();
  if (typeof requestAnimationFrame === 'function') requestAnimationFrame(atualizarBordas);   // depois do layout
  return atualizarBordas;
}
