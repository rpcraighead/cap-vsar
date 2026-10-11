// Aeronautical chart layers, shared by the instructor, mission base and
// debrief views.
//
// Same tile services the flight planner uses
// (flightplanner.rpc-cyberflight.com): the FAA's public ArcGIS caches for the
// sectional and enroute charts, Esri World Imagery, and OSM. URLs come from
// /api/tile-sources so a wing running its own cache can repoint the console
// without editing this file; the table below is the offline fallback.
//
// maxNativeZoom is the deepest zoom the FAA cache actually holds. Past it
// Leaflet upscales the last real tile — blurry but readable — instead of
// requesting tiles that 404 and leave the map black. The flight planner hit
// exactly that bug on IFR Low past z10.

const CHART_FALLBACK = {
  vfr:      'https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services/VFR_Sectional/MapServer/tile/{z}/{y}/{x}',
  ifr_low:  'https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services/IFR_AreaLow/MapServer/tile/{z}/{y}/{x}',
  ifr_high: 'https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services/IFR_High/MapServer/tile/{z}/{y}/{x}',
  sat:      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  osm:      'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
};

const CHART_DEFS = [
  ['vfr',      'VFR Sec',   {attribution: '&copy; FAA VFR Sectional',    minZoom: 5, maxNativeZoom: 12, maxZoom: 15}],
  ['ifr_low',  'IFR Low',   {attribution: '&copy; FAA IFR Low Enroute',  minZoom: 4, maxNativeZoom: 10, maxZoom: 15}],
  ['ifr_high', 'IFR High',  {attribution: '&copy; FAA IFR High Enroute', minZoom: 4, maxNativeZoom: 9,  maxZoom: 15}],
  ['sat',      'Satellite', {attribution: '&copy; Esri World Imagery',   maxZoom: 18}],
  ['osm',      'Street',    {attribution: '&copy; OpenStreetMap',        maxZoom: 19}],
];

// Adds the basemap and its switcher to `map`. `opts.view` namespaces the
// remembered choice so the instructor's sectional does not follow them into
// debrief; `opts.default` is the layer shown before anyone has chosen one.
function capvsarCharts(map, opts) {
  opts = opts || {};
  const store = 'capvsar.chart.' + (opts.view || 'map');
  const layers = {}, buttons = {};

  for (const [id, , cfg] of CHART_DEFS) layers[id] = L.tileLayer(CHART_FALLBACK[id], cfg);

  let active = layers[opts.default] ? opts.default : 'vfr';
  try {
    const saved = localStorage.getItem(store);
    if (saved && layers[saved]) active = saved;
  } catch (e) { /* private window, or site data blocked */ }
  layers[active].addTo(map);

  function select(id) {
    if (id === active || !layers[id]) return;
    map.removeLayer(layers[active]);
    layers[id].addTo(map);
    buttons[active].classList.remove('active');
    buttons[id].classList.add('active');
    active = id;
    try { localStorage.setItem(store, id); } catch (e) { /* nothing to do */ }
  }

  const ctl = L.control({position: 'topright'});
  ctl.onAdd = () => {
    const box = L.DomUtil.create('div', 'chart-switcher');
    for (const [id, label] of CHART_DEFS) {
      const b = L.DomUtil.create('button', 'chart-btn' + (id === active ? ' active' : ''), box);
      b.type = 'button';
      b.textContent = label;
      L.DomEvent.on(b, 'click', L.DomEvent.stop);
      L.DomEvent.on(b, 'click', () => select(id));
      buttons[id] = b;
    }
    L.DomEvent.disableClickPropagation(box);
    L.DomEvent.disableScrollPropagation(box);
    return box;
  };
  ctl.addTo(map);

  // Layers are built from the fallback table first so the map is never blank,
  // then repointed if the server names different services.
  fetch('/api/tile-sources')
    .then(r => r.ok ? r.json() : Promise.reject(r.status))
    .then(src => {
      for (const id of Object.keys(layers))
        if (src[id] && src[id] !== CHART_FALLBACK[id]) layers[id].setUrl(src[id]);
    })
    .catch(() => { /* fallback table stands */ });

  return {layers, select, current: () => active};
}

// F2-1: the Flight Planner link used to be rewritten here to port 8090, which
// the Caddy consolidation stopped publishing. The pages' own href (/planner/)
// is the front door and is left alone.

// ------------------------------------------------------- shared view helpers
// Each of the instructor, mission-base and debrief views used to carry its own
// copy of these. They live here because every one of those pages already loads
// this file; keep them free of page-specific ids so that stays true.

// F-6: nothing escapes server strings on the way out, and any LAN client can
// POST message bodies, bearing notes and callsigns. Escape every server value
// interpolated into HTML. Values already passed through toFixed() or
// Math.round() are provably numeric and are left alone.
const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c =>
  ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

const planeIcon = c => L.divIcon({className:'', iconSize:[26,26], html:
  `<svg width="26" height="26" viewBox="0 0 24 24" style="transform:rotate(${c}deg)">
     <path d="M12 2 L15 11 L22 13 L22 15 L13.5 14 L13 20 L16 22 L16 23 L12 22 L8 23 L8 22 L11 20 L10.5 14 L2 15 L2 13 L9 11 Z"
       fill="#2e5496" stroke="#1f3864" stroke-width="0.8"/></svg>`});

const fmtDur = s => `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;

// Same curve as mission-radio.js's scheduleReconnect (1 s doubling to a 30 s
// ceiling); a test holds the two together. A fixed 2 s retry from every
// console at once is what a restarted console gets hit with otherwise.
function vsarBackoffMs(attempt) {
  return Math.min(30000, 1000 * 2 ** Math.min(attempt, 5));
}

// HH:MM:SSZ in the header. `el` defaults to #clock.
function vsarStartClock(el) {
  const node = () => el || document.getElementById('clock');
  const tick = () => { const n = node(); if (n) n.textContent = new Date().toUTCString().slice(17, 25) + 'Z'; };
  tick();
  return setInterval(tick, 1000);
}

// The console's push socket, reconnecting with backoff. `onOpen(ws)` is where a
// view backfills what it missed; `onMessage(frame)` receives parsed JSON (a
// malformed frame is dropped rather than throwing out of the handler).
function vsarConnect(opts) {
  let attempt = 0;
  const setStatus = (text, cls) => {
    const el = document.getElementById('status');
    if (el) { el.textContent = text; el.className = 'status ' + cls; }
  };
  function open() {
    const ws = new WebSocket(
      `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}${opts.path || '/ws'}`);
    ws.onopen = () => {
      attempt = 0;
      setStatus('live', 'online');
      if (opts.onOpen) opts.onOpen(ws);
    };
    ws.onclose = () => {
      setStatus('reconnecting', 'offline');
      setTimeout(open, vsarBackoffMs(attempt++));
    };
    ws.onmessage = e => {
      let frame;
      try { frame = JSON.parse(e.data); } catch (err) { return; }
      if (opts.onMessage) opts.onMessage(frame);
    };
    return ws;
  }
  return open();
}

// Header badge and Log out button. `fallbackTitle` is shown when the session
// carries no title of its own.
async function vsarInitAuthBadge(fallbackTitle) {
  const badge = document.getElementById('userBadge');
  try {
    const res = await fetch('/api/auth/me');
    if (res.ok) {
      const data = await res.json();
      if (data.authenticated && badge) {
        const title = data.title || (data.role ? data.role.toUpperCase() : fallbackTitle);
        const cs = data.callsign ? ` (${data.callsign})` : '';
        badge.textContent = `👤 ${title}${cs}`;
      }
    }
  } catch (e) { /* the badge keeps its static text */ }

  const logout = document.getElementById('logoutBtn');
  if (logout) {
    logout.onclick = async () => {
      try { await fetch('/api/auth/logout', {method: 'POST'}); } catch (e) { /* leaving anyway */ }
      location.href = '/login';
    };
  }
}

// ------------------------------------------------------------ session gating
// F2-5: this used to keep a shared role token in localStorage for the life of
// the browser profile and ask for it in a browser dialog on any 403 - including from
// roster users who merely lack the role (aircrew on /base). Since X-12/X-13
// the session cookie is the credential, so a refusal means "log in as someone
// who may do this", not "type a secret".
function vsarLoginUrl(pathname, search) {
  return '/login?next=' + encodeURIComponent((pathname || '/') + (search || ''));
}

function vsarGoToLogin() {
  if (location.pathname === '/login') return;
  location.href = vsarLoginUrl(location.pathname, location.search);
}

// fetch() that sends the page to /login on 401/403. The response is returned
// either way, so callers keep their own ok-handling for the failures that are
// not about the session.
async function vsarFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (r.status === 401 || r.status === 403) vsarGoToLogin();
  return r;
}

// F2-9: one message for every failed call used to say "that callsign is not
// reporting a position yet", even for an expired session, a 503 or a 422.
// This words the real failure from the server's own `detail`, with the status
// in front of the operator. `what` is the sentence subject, e.g. 'Bearing not
// logged'. A 401/403 has already sent the page to /login (vsarFetch), so it
// returns '' rather than raising a dialog over the redirect.
async function vsarFailureText(r, what) {
  if (r.status === 401 || r.status === 403) return '';
  let detail = '';
  try {
    const body = await r.json();
    if (typeof body.detail === 'string') detail = body.detail;
    else if (Array.isArray(body.detail))
      detail = body.detail.map(d => (d && d.msg) || '').filter(Boolean).join('; ');
  } catch (e) { /* not JSON */ }
  return `${what} (HTTP ${r.status})${detail ? ': ' + detail : ''}.`;
}

async function vsarReportFailure(r, what) {
  const text = await vsarFailureText(r, what);
  if (text) alert(text);
}
