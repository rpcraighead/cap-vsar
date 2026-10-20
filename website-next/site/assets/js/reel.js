// T43: reels and clips. Vanilla JS, no libraries. Plays only the visible, active slide; cross-fades on a timer;
// pauses off-screen and with the page's Pause control; posters only under reduced motion or Save-Data; keeps a
// poster when a clip is missing and drops a slide that has neither.
// T11: inactive slides leave the accessibility tree (aria-hidden + inert); rotation holds while the pointer or focus
// is inside; the live region speaks only on user navigation; only the active and next clips preload; a blocked
// play() makes the clip button honest; poster-only clips say so in their caption.
// T22: a slide marked data-allow-still keeps its poster inside a data-require-video reel (the Home hero's station
// panel until its clip lands); it still gets the STILL FRAME badge and caption note.
(() => {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const saveData = () => !!(navigator.connection && navigator.connection.saveData);
  const postersOnly = () => reduced.matches || saveData();
  const pagePaused = () => document.body.classList.contains('paused');

  // Resolve a slide's media: 'video' when the clip loads, 'poster' when only the poster does, 'skip' otherwise.
  function probe(slide) {
    const video = slide.querySelector('video');
    const poster = slide.querySelector('.slide-poster');
    if (!video) return Promise.resolve(slide.querySelector('svg') ? 'static' : 'skip');
    const posterOk = new Promise(resolve => {
      if (!poster) return resolve(false);
      poster.loading = 'eager';   // a lazy poster below the fold would otherwise never report
      if (poster.complete) return resolve(poster.naturalWidth > 0);
      poster.addEventListener('load', () => resolve(true), {once: true});
      poster.addEventListener('error', () => resolve(false), {once: true});
    });
    const videoOk = new Promise(resolve => {
      if (video.readyState >= 1) return resolve(true);
      if (video.error) return resolve(false);
      if (postersOnly()) { video.preload = 'none'; resolve(false); return; }
      // T22: a freshly parsed <video> reports NETWORK_NO_SOURCE (3) until the browser reaches a stable state, so the
      // "every source already failed" shortcut waits one task; checked synchronously it dropped real clips whenever the
      // script ran in the same task as the parser (small documents, iframes, some reloads).
      setTimeout(() => {
        if (video.readyState >= 1) return resolve(true);
        if (video.error || video.networkState === 3) return resolve(false);   // NETWORK_NO_SOURCE: every source already failed
        const sources = [...video.querySelectorAll('source')];
        let failed = 0;
        const fail = () => { failed += 1; if (failed >= Math.max(sources.length, 1)) resolve(false); };
        sources.forEach(s => s.addEventListener('error', fail, {once: true}));
        video.addEventListener('error', () => resolve(false), {once: true});
        video.addEventListener('loadedmetadata', () => resolve(true), {once: true});
        setTimeout(() => resolve(video.readyState >= 1), 8000);
        video.load();
      }, 0);
    });
    return Promise.all([videoOk, posterOk]).then(([v, p]) => (v ? 'video' : p ? 'poster' : 'skip'));
  }

  class Reel {
    constructor(fig) {
      this.fig = fig;
      this.single = fig.classList.contains('clip');
      this.slides = this.single ? [fig] : [...fig.querySelectorAll('.reel-slide')];
      this.live = fig.querySelector('.reel-live');
      this.dots = fig.querySelector('.reel-dots');
      this.index = 0; this.timer = null; this.visible = false; this.userPaused = false; this.hold = false;
      this.interval = +fig.dataset.interval || 7000;
      Promise.all(this.slides.map(probe)).then(states => this.start(states));
    }
    start(states) {
      this.slides = this.slides.filter((slide, i) => {
        let state = states[i];
        if (state === 'poster' && this.fig.hasAttribute('data-require-video') && !slide.hasAttribute('data-allow-still')) state = 'skip';
        if (state === 'skip') { if (this.single) this.fig.hidden = true; else slide.remove(); return false; }
        slide.dataset.state = state === 'static' ? 'static' : state;
        if (state === 'poster') this.markStill(slide);
        return true;
      });
      if (!this.slides.length) return;
      this.fig.dataset.slides = String(this.slides.length);
      this.fig.dataset.ready = 'true';
      if (this.single) {
        const button = this.fig.querySelector('.clip-pause');
        const video = this.fig.querySelector('video');
        this.button = button;
        if (button) {
          if (this.fig.dataset.state !== 'video' || postersOnly()) button.hidden = true;
          button.addEventListener('click', () => { this.userPaused = !this.userPaused; this.syncButton(); this.apply(); });
          this.syncButton();
        }
        if (video) video.addEventListener('error', () => { this.fig.dataset.state = 'poster'; if (button) button.hidden = true; });
      } else {
        this.slides.forEach((slide, i) => slide.setAttribute('aria-label', `Slide ${i + 1} of ${this.slides.length}`));
        this.buildControls();
        // Rotation holds while the pointer or keyboard focus is inside the reel; the clip itself keeps playing.
        const hold = on => { this.hold = on; this.apply(); };
        this.fig.addEventListener('pointerenter', () => hold(true));
        this.fig.addEventListener('pointerleave', () => hold(false));
        this.fig.addEventListener('focusin', () => hold(true));
        this.fig.addEventListener('focusout', e => { if (!this.fig.contains(e.relatedTarget)) hold(false); });
      }
      const io = new IntersectionObserver(entries => { this.visible = entries[0].isIntersecting; this.apply(); }, {threshold: .25});
      io.observe(this.fig);
      new MutationObserver(() => this.apply()).observe(document.body, {attributes: true, attributeFilter: ['class']});
      reduced.addEventListener('change', () => this.apply());
      this.show(0, true);
    }
    // A poster standing in for a clip says so: a badge, and a note on the caption that described motion.
    markStill(slide) {
      if (!slide.querySelector('.clip-note, .reel-note')) {
        const note = document.createElement('p');
        note.className = this.single ? 'clip-note' : 'reel-note';
        note.textContent = 'Still frame';
        (slide.querySelector('.clip-stage') || slide).appendChild(note);
      }
      const caption = slide.querySelector('.clip-caption, .slide-caption');
      if (caption && !caption.querySelector('.still-note')) {
        const more = document.createElement('span');
        more.className = 'still-note';
        more.textContent = 'Still frame; the moving clip is not yet available.';
        caption.appendChild(more);
      }
    }
    syncButton() {
      if (this.button) this.button.textContent = this.userPaused ? 'Play clip' : 'Pause clip';
    }
    buildControls() {
      const prev = this.fig.querySelector('.reel-prev'), next = this.fig.querySelector('.reel-next');
      prev?.addEventListener('click', () => this.show(this.index - 1));
      next?.addEventListener('click', () => this.show(this.index + 1));
      if (this.dots) {
        this.dots.innerHTML = '';
        this.slides.forEach((slide, i) => {
          const dot = document.createElement('button');
          dot.type = 'button'; dot.className = 'reel-dot';
          dot.setAttribute('aria-label', `Slide ${i + 1} of ${this.slides.length}: ${this.caption(slide)}`);
          dot.addEventListener('click', () => this.show(i));
          this.dots.appendChild(dot);
        });
        this.dots.addEventListener('keydown', e => {
          if (e.key === 'ArrowRight') { e.preventDefault(); this.show(this.index + 1); this.dots.children[this.index]?.focus(); }
          if (e.key === 'ArrowLeft') { e.preventDefault(); this.show(this.index - 1); this.dots.children[this.index]?.focus(); }
        });
      }
    }
    caption(slide) {
      const c = slide.querySelector('.slide-caption');
      return c ? c.textContent.trim() : (slide.querySelector('svg title')?.textContent || 'Map');
    }
    // show(i): by the user unless `initial` (first paint) or `auto` (the timer); only user moves are announced.
    show(i, initial, auto) {
      const n = this.slides.length; if (!n) return;
      this.index = ((i % n) + n) % n;
      this.slides.forEach((slide, k) => {
        const active = k === this.index;
        if (!this.single) {
          slide.classList.toggle('is-active', active);
          slide.setAttribute('aria-hidden', String(!active));
          slide.inert = !active;
        }
        const video = slide.querySelector('video');
        if (video && !active) video.pause();
      });
      // Fetch only what is about to be seen: the active clip and the one after it.
      [this.slides[this.index], this.slides[(this.index + 1) % n]].forEach(slide => {
        const video = slide.querySelector('video');
        if (video && slide.dataset.state === 'video' && !postersOnly()) video.preload = 'auto';
      });
      if (this.dots) [...this.dots.children].forEach((d, k) => { if (k === this.index) d.setAttribute('aria-current', 'true'); else d.removeAttribute('aria-current'); });
      if (this.live && !initial && !auto) this.live.textContent = this.caption(this.slides[this.index]);
      this.apply();
    }
    // Decide, from every rule at once, whether the active slide should be playing and whether the timer runs.
    apply() {
      clearTimeout(this.timer); this.timer = null;
      const slide = this.slides[this.index]; if (!slide) return;
      const video = slide.querySelector('video');
      const canPlay = this.visible && !pagePaused() && !this.userPaused && !postersOnly();
      if (video && slide.dataset.state === 'video') {
        if (canPlay) {
          video.play().catch(() => {
            // Autoplay refused (Low Power Mode, policy): show the truth on the button instead of a stale "Pause".
            if (this.single && !this.userPaused) { this.userPaused = true; this.syncButton(); }
          });
        } else video.pause();
      }
      if (!this.single && this.slides.length > 1 && canPlay && !this.hold) {
        const wait = +slide.dataset.duration || this.interval;
        this.timer = setTimeout(() => this.show(this.index + 1, false, true), wait);
      }
    }
  }

  document.querySelectorAll('.reel, .clip').forEach(fig => new Reel(fig));
})();
