// CAP V-SAR shell header (docs/DECISIONS_2026-10-11.md, D6).
//
// mountShell({page}) fills <header id="shell"> with the brand, the exercise
// name and date, the stage tabs this seat may use, the EXERCISE marking, link
// state, a Zulu clock and the viewer's identity chip. It reads /api/auth/me
// and /api/state once and keeps the clock and link dots alive. Everything is
// built with textContent: no server string reaches HTML unescaped.
(function () {
  'use strict';

  // Stage tabs per role. A seat narrows this further on the server later
  // (D5); for now the role is what the session carries.
  const STAGES = {
    instructor: [['Ready room', '/ready'], ['Console', '/instructor'], ['Mission base', '/base'],
                 ['Radio', '/radio'], ['Debrief', '/debrief'], ['Plan', '/planner/'], ['Setup', '/setup']],
    evaluator:  [['Ready room', '/ready'], ['Debrief', '/debrief']],
    base:       [['Ready room', '/ready'], ['Mission base', '/base'], ['Radio', '/radio'], ['Plan', '/planner/'], ['Debrief', '/debrief']],
    aircrew:    [['Ready room', '/ready'], ['Mission base', '/base'], ['Radio', '/radio'], ['Debrief', '/debrief']],
    ground_team:[['Ready room', '/ready'], ['Radio', '/radio']],
    anonymous:  [['Ready room', '/ready']],
  };

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function zulu(d) {
    return d.toISOString().slice(11, 19) + 'Z';
  }

  function initials(s) {
    return (s || '?').split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase();
  }

  async function getJSON(url) {
    try {
      const r = await fetch(url, { credentials: 'same-origin' });
      if (!r.ok) return null;
      return await r.json();
    } catch (e) { return null; }
  }

  window.mountShell = async function mountShell(opts) {
    const page = (opts && opts.page) || location.pathname;
    const host = document.getElementById('shell');
    if (!host) return;
    host.className = 'shell';
    host.textContent = '';

    const brand = el('div', 'shell-brand');
    brand.append(el('b', null, 'CAP V-SAR'), el('span', null, 'virtual SAR exercise'));
    const ex = el('div', 'shell-exercise');
    const exName = el('b', null, 'Exercise');
    const exSub = el('span', null, '');
    ex.append(exName, exSub);
    const nav = el('nav', 'shell-nav');
    const spacer = el('div', 'shell-spacer');
    const tag = el('span', 'shell-tag', 'EXERCISE · NOT A REAL DISTRESS');
    const links = el('div', 'shell-links');
    const apiDot = el('span', 'dot'), netDot = el('span', 'dot');
    const apiL = el('span'); apiL.append(apiDot, document.createTextNode('console'));
    const netL = el('span'); netL.append(netDot, document.createTextNode('net'));
    links.append(apiL, netL);
    const clock = el('span', 'shell-clock', zulu(new Date()));
    const id = el('a', 'shell-id'); id.href = '/login';
    const avatar = el('span', 'avatar', '?');
    const idText = el('span', null, 'not signed in');
    const idSub = el('small', null, '');
    id.append(avatar, idText, idSub);
    host.append(brand, ex, nav, spacer, tag, links, clock, id);

    setInterval(() => { clock.textContent = zulu(new Date()); }, 1000);

    const me = await getJSON('/api/auth/me');
    const role = (me && me.role) || 'anonymous';
    (STAGES[role] || STAGES.anonymous).forEach(([label, href]) => {
      const a = el('a', null, label);
      a.href = href;
      if (href === page || (href !== '/' && page.startsWith(href))) a.setAttribute('aria-current', 'page');
      nav.append(a);
    });
    if (me && me.role) {
      avatar.textContent = initials(me.callsign || me.title || me.role);
      idText.textContent = me.title || me.role;
      idSub.textContent = me.callsign ? ' · ' + me.callsign : '';
      id.href = '/api/auth/logout';
      id.title = 'Sign out';
    }

    async function refresh() {
      const st = await getJSON('/api/state');
      apiDot.className = 'dot ' + (st ? 'good' : 'critical');
      if (st) {
        const s = st.sortie;
        exName.textContent = (s && s.name) || (st.scenario && st.scenario.name) || 'No sortie running';
        exSub.textContent = s ? (s.stopped ? 'stopped' : 'running') + (s.revealed ? ' · truth revealed' : '') : 'standing by';
      }
      const rx = await getJSON('/api/radio/rx');
      netDot.className = 'dot ' + (rx ? (rx.main_rx || rx.guard_rx ? 'good' : 'info') : 'critical');
      netDot.title = rx ? 'mission net reachable' : 'mission net unreachable';
    }
    refresh();
    setInterval(refresh, 5000);
    return { me };
  };
})();
