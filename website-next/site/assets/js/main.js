(() => {
  const menu = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#primary-nav');
  if (menu && nav) {
    const closeMenu = () => { nav.classList.remove('is-open'); menu.setAttribute('aria-expanded', 'false'); document.body.classList.remove('menu-open'); };
    menu.addEventListener('click', () => {
      const open = menu.getAttribute('aria-expanded') !== 'true';
      menu.setAttribute('aria-expanded', String(open));
      nav.classList.toggle('is-open', open);
      document.body.classList.toggle('menu-open', open);   // T11: no page scroll behind the open sheet
      if (open) nav.querySelector('a')?.focus();
    });
    nav.addEventListener('click', event => { if (event.target.closest('a')) closeMenu(); });
    document.addEventListener('keydown', event => { if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') { closeMenu(); menu.focus(); } });
    window.addEventListener('resize', () => { if (window.innerWidth > 900) closeMenu(); });
  }
  // Native branch disclosures stay usable without scripts; compact them on phones (an inline script in the page
  // does the first pass before paint; this keeps them in step when the viewport changes).
  const compactChart = matchMedia('(max-width: 900px)');
  const setBranches = () => document.querySelectorAll('details.branch').forEach(branch => {
    branch.open = !compactChart.matches;
  });
  setBranches();
  compactChart.addEventListener('change', setBranches);
  // T11: the control's name says what it will do next; no aria-pressed on a button whose name changes.
  const pause = document.querySelector('.pause-control');
  pause?.addEventListener('click', () => {
    const paused = !document.body.classList.contains('paused');
    document.body.classList.toggle('paused', paused);
    pause.textContent = paused ? 'Resume animation and video' : 'Pause animation and video';
  });
  // T11: horizontal scrollers (tables, wide diagrams) are keyboard-reachable only when they actually scroll.
  const scrollers = [...document.querySelectorAll('.table-wrap, .diagram')];
  const syncScrollers = () => scrollers.forEach(el => {
    if (el.scrollWidth > el.clientWidth + 1) {
      el.tabIndex = 0;
      if (el.classList.contains('table-wrap')) {
        el.setAttribute('role', 'region');
        const caption = el.querySelector('caption');
        if (caption && !el.hasAttribute('aria-label')) el.setAttribute('aria-label', caption.textContent.trim());
      }
    } else {
      el.removeAttribute('tabindex');
    }
  });
  syncScrollers();
  window.addEventListener('load', syncScrollers);
  window.addEventListener('resize', syncScrollers);
  // T16: the MFD figure swaps its screen between the captured views; the links open the image without JS.
  document.querySelectorAll('.mfd-figure').forEach(figure => {
    const img = figure.querySelector('.mfd-screen img');
    const opener = figure.querySelector('.mfd-screen .shot-open');
    const live = figure.querySelector('.mfd-live');
    const links = [...figure.querySelectorAll('.mfd-views a')];
    if (!img || !links.length) return;
    links.forEach(link => link.addEventListener('click', event => {
      event.preventDefault();
      const src = link.getAttribute('href'), alt = link.dataset.alt || '';
      img.src = src; img.alt = alt;
      if (opener) { opener.dataset.lightbox = src; opener.dataset.alt = alt; }
      links.forEach(other => { if (other === link) other.setAttribute('aria-current', 'true'); else other.removeAttribute('aria-current'); });
      if (live) live.textContent = `Showing: ${link.textContent.trim()}`;
    }));
  });
  const dialog = document.querySelector('.lightbox');
  const dialogImage = dialog?.querySelector('img');
  const closeButton = dialog?.querySelector('.lightbox-close');
  let returnFocus = null;
  document.querySelectorAll('[data-lightbox]').forEach(button => button.addEventListener('click', () => {
    if (!dialog || !dialogImage) return;
    returnFocus = button;
    dialogImage.src = button.dataset.lightbox;
    dialogImage.alt = button.dataset.alt || '';
    if (dialog.showModal) dialog.showModal(); else dialog.setAttribute('open', '');
    closeButton?.focus();
  }));
  closeButton?.addEventListener('click', () => dialog?.close());
  dialog?.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  dialog?.addEventListener('close', () => returnFocus?.focus());
  dialog?.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    if (closeButton) { event.preventDefault(); closeButton.focus(); }
  });
})();
