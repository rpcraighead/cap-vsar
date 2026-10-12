// Ready room (docs/UX_REVIEW_2026-10-11.md §4.3). Reads /api/ready every few
// seconds, keeps a socket open so the console knows this seat is here, and
// renders the presence board with createElement/textContent only.
(function () {
  'use strict';

  const CHECK_LABELS = { joined: 'joined', on_net: 'on net', mic: 'headset', station: 'station',
                         df_head: 'DF head', briefing: 'briefing' };
  const STATUS_LABELS = { invited: 'invited', joined: 'joined', on_net: 'on the net', ready: 'ready',
                          flying: 'flying', stale: 'station stale', lost: 'lost' };
  const STATUS_DOT = { invited: '', joined: 'info', on_net: 'good', ready: 'good', flying: 'good',
                       stale: 'warning', lost: 'critical' };
  const GROUP_ORDER = ['exercise', 'base', 'aircraft', 'ground'];
  const GROUP_LABELS = { exercise: 'Exercise staff', base: 'Mission base', ground: 'Ground teams' };

  const $ = id => document.getElementById(id);
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function zulu(t) {
    return new Date(t * 1000).toISOString().slice(11, 16) + 'Z';
  }

  let me = null;

  async function api(url, opts) {
    const r = await fetch(url, Object.assign({ credentials: 'same-origin' }, opts || {}));
    if (r.status === 401 || r.status === 403) { location.href = '/login?next=' + encodeURIComponent(location.pathname); return null; }
    if (!r.ok) return null;
    return r.json();
  }

  // The socket is the presence signal; frames are not needed here.
  let ws = null, backoff = 1000;
  function keepSocket() {
    try {
      ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws?page=ready');
      ws.onopen = () => { backoff = 1000; };
      ws.onclose = () => { setTimeout(keepSocket, backoff); backoff = Math.min(backoff * 2, 15000); };
    } catch (e) { setTimeout(keepSocket, 5000); }
  }

  function tile(s) {
    const t = el('article', 'tile ' + s.status);
    if (s.ac_slot) t.dataset.ac = String(s.ac_slot);
    const who = el('div', 'who');
    who.append(el('b', null, s.name || s.title || s.label), el('span', 'callsign', s.callsign || ''));
    const seat = el('div', 'seat', s.label);
    const state = el('div', 'state');
    const dot = el('span', 'dot ' + (STATUS_DOT[s.status] || ''));
    const words = STATUS_LABELS[s.status] || s.status;
    const ago = s.seen_ago != null ? ` · seen ${s.seen_ago < 60 ? Math.round(s.seen_ago) + ' s' : Math.round(s.seen_ago / 60) + ' min'} ago` : '';
    state.append(dot, el('span', null, words + ago));
    const checks = el('div', 'checks');
    Object.entries(s.checks).forEach(([k, v]) => checks.append(el('span', 'check ' + v, CHECK_LABELS[k] || k)));
    t.append(who, seat, state, checks);
    return t;
  }

  function renderGroups(seats) {
    const host = $('groups');
    host.textContent = '';
    const groups = new Map();
    seats.filter(s => s.seat !== 'station').forEach(s => {
      const key = s.kind === 'aircraft' ? 'aircraft:' + (s.aircraft_id || s.callsign) : s.kind;
      if (!groups.has(key)) groups.set(key, { kind: s.kind, label: s.kind === 'aircraft' ? s.callsign : GROUP_LABELS[s.kind], slot: s.ac_slot, seats: [] });
      groups.get(key).seats.push(s);
    });
    const ordered = [...groups.values()].sort((a, b) => GROUP_ORDER.indexOf(a.kind) - GROUP_ORDER.indexOf(b.kind) || (a.slot || 0) - (b.slot || 0));
    ordered.forEach(g => {
      const sec = el('section', 'group');
      const h = el('h3');
      if (g.kind === 'aircraft' && g.slot) {
        const sw = el('span', 'dot'); sw.style.background = `var(--ac-${g.slot})`; h.append(sw);
      }
      const ready = g.seats.filter(s => s.status === 'ready' || s.status === 'flying').length;
      h.append(el('span', null, g.label || 'Seats'), el('span', 'count', `${ready}/${g.seats.length}`));
      const grid = el('div', 'tiles');
      g.seats.forEach(s => grid.append(tile(s)));
      sec.append(h, grid);
      host.append(sec);
    });
    if (!ordered.length) host.append(el('p', 'empty', 'No seats yet. The Exercise Director creates the roster on the Setup page.'));
  }

  function renderBrief(st) {
    $('exName').textContent = st.exercise.name;
    const sc = st.scenario;
    $('scName').textContent = sc ? `${sc.name} · ${sc.band} MHz` : 'no scenario selected';
    $('scName').className = sc ? '' : 'empty';
    const al = $('alert');
    al.textContent = '';
    if (sc && (sc.alert_text || sc.alert_kind)) {
      al.append(el('b', null, sc.alert_kind || 'Alert'));
      al.append(el('div', 'small', sc.alert_text || ''));
      if (sc.alert_radius_nm) al.append(el('div', 'xs muted', `search area radius ${sc.alert_radius_nm} nm`));
    } else {
      al.append(el('span', 'empty', 'The alert is briefed when the sortie starts.'));
    }
    const ch = $('channels');
    ch.textContent = '';
    (st.channels || []).forEach(c => { ch.append(el('b', null, c.label || c.id), el('span', null, c.name || '')); });

    const s = st.sortie;
    const pill = $('sortiePill');
    pill.textContent = '';
    const dot = el('span', 'dot ' + (s && !s.stopped ? 'good' : ''));
    pill.append(dot, el('span', null, s ? (s.stopped ? 'sortie stopped' : 'sortie running') : 'standing by'));

    const acts = $('actions');
    acts.textContent = '';
    const mine = (st.me && st.me.checks) || {};
    const attest = (check, label, done) => {
      const b = el('button', 'btn big' + (done ? '' : ' primary'), done ? `✓ ${label}` : label);
      b.disabled = !!done;
      b.onclick = async () => { await api('/api/ready/check', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ check, ok: true }) }); refresh(); };
      return b;
    };
    if (st.me && st.me.role && st.me.role !== 'instructor') {
      acts.append(attest('briefing', 'I have read the briefing', mine.briefing));
      acts.append(attest('mic', 'Headset tested on the radio page', mine.mic));
      const r = el('a', 'btn', 'Open the radio'); r.href = '/radio'; acts.append(r);
    }
    if (st.me && st.me.role === 'instructor') {
      const blocking = st.summary.blocking.length;
      const start = el('a', 'btn big ' + (blocking ? '' : 'primary'), blocking ? `Start anyway (${blocking} not ready)` : 'Start the sortie');
      start.href = '/instructor';
      acts.append(start);
      const setup = el('a', 'btn', 'Roster and badges'); setup.href = '/setup'; acts.append(setup);
    }
  }

  async function renderLobby(st) {
    const ul = $('lobby');
    if (!st.sortie) return;
    const msgs = await api('/api/messages?since=0');
    if (!msgs) return;
    ul.textContent = '';
    if (!msgs.length) { ul.append(el('li', 'empty', 'No messages yet.')); return; }
    msgs.slice(-12).forEach(m => {
      const li = el('li');
      const body = el('span');
      body.append(el('span', 'from', m.sender), document.createTextNode(m.body));
      li.append(el('time', null, zulu(m.t)), body);
      ul.append(li);
    });
  }

  async function refresh() {
    const st = await api('/api/ready');
    if (!st) return;
    me = st.me;
    $('readyN').textContent = st.summary.ready;
    $('totalN').textContent = st.summary.total;
    $('count').textContent = `${st.seats.length} seats`;
    $('bar').style.width = st.summary.total ? (100 * st.summary.ready / st.summary.total) + '%' : '0%';
    const bl = $('blocking');
    bl.textContent = '';
    st.summary.blocking.slice(0, 8).forEach(b => bl.append(el('li', null, b)));
    renderGroups(st.seats);
    renderBrief(st);
    renderLobby(st);
  }

  window.mountShell && window.mountShell({ page: '/ready' });
  keepSocket();
  refresh();
  setInterval(refresh, 3000);
})();
