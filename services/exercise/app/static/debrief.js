// Replay a recorded sortie against beacon truth, and score it.
//
// The replay (map, slider, events) comes from /api/sorties/{id}/track. The
// scoring (a card of measures per aircraft and the bearing-error chart) comes
// from /api/sorties/{id}/analysis, which does the geometry on the server with
// app/geo.py and makes the same truth decision /track makes; this file no
// longer measures anything itself.
//
// Colours are tokens (docs/DECISIONS_2026-10-11.md D6): aircraft N wears
// --ac-N on its track, marker, card, chart line and slider marks, in roster
// order; the beacon wears --truth. Server strings reach the page through
// textContent, setAttribute or esc(), never raw markup (F-6).
const $ = id => document.getElementById(id);

// esc(), planeIcon and fmtDur come from charts.js; vizErrorChart from viz.js.

if (typeof mountShell === 'function') mountShell({page: '/debrief'});

const map = L.map('map').setView([33.15, -117.18], 11);
capvsarCharts(map, {view: 'debrief'});

let data = null, scores = null, chart = null, t0 = 0, t1 = 0, playing = false, timer = null;
const layers = L.layerGroup().addTo(map);
let beacon = null, ring = null;

// One sortie can have three aircraft airborne at once. Everything below is
// per-callsign: a single shared track polyline zig-zagged between aircraft,
// and summing consecutive points across them made "track flown" and closest
// approach meaningless - which is the scoring the evaluator reads at debrief.
let groups = {}, order = [], slots = {}, acMarkers = {}, flownLines = {};
let eventsShown = -1;

const groupByCallsign = P => {
  const g = {};
  for (const p of P) (g[p.callsign || 'UNKNOWN'] ||= []).push(p);
  return g;
};

// The plugin records true heading; use it when it is there. Falling back to
// the track between two fixes needs the longitude scaled by cos(latitude),
// which the old inline calculation omitted - about 10 degrees of error at 33N.
const headingOf = (p, prev) => {
  if (typeof p.hdg_true === 'number') return p.hdg_true;
  const r = Math.PI / 180;
  const dx = (p.lon - prev.lon) * Math.cos(p.lat * r);
  return Math.atan2(dx, p.lat - prev.lat) * 180 / Math.PI;
};

// A token's value for Leaflet, which writes colours into SVG attributes, where
// var() does not work. Empty outside a browser.
function tok(name) {
  try { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  catch (e) { return ''; }
}
const slotOf = cs => slots[cs] || 0;
const acColor = cs => tok(slotOf(cs) ? `--ac-${slotOf(cs)}` : '--muted');

function make(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

// F2-7: neither fetch checked .ok or caught, so a 403/503 either threw out of
// the page or painted "undefined" into the selector. Say what failed.
function debriefStatus(text) { $('sortieInfo').textContent = text; }

async function loadList() {
  let list;
  try {
    const r = await vsarFetch('/api/sorties');
    if (!r.ok) { debriefStatus(`Sorties could not be loaded (HTTP ${r.status}).`); return; }
    list = await r.json();
  } catch (e) { debriefStatus('Sorties could not be loaded: the console is unreachable.'); return; }
  $('sortieSel').innerHTML = list.map(s => {
    const d = new Date(s.started*1000).toISOString().slice(0,16).replace('T',' ');
    return `<option value="${esc(s.id)}">${d}Z — ${esc(s.name)} (${esc(s.points)} pts)</option>`;
  }).join('') || '<option value="">no sorties recorded</option>';
  if (list.length) load($('sortieSel').value);
}

// Forget the previous sortie before anything about the next one is known. The
// early return below used to leave the old callsigns in `order`, so seek()
// went on indexing a `groups` that no longer held them, on every 250 ms tick.
function clearSortie() {
  stop();
  data = scores = chart = null; groups = {}; order = []; slots = {}; acMarkers = {}; flownLines = {};
  eventsShown = -1;
  layers.clearLayers(); beacon = ring = null;
  $('summary').replaceChildren();
  $('errChart').replaceChildren();
  $('marks').replaceChildren();
  $('events').textContent = '—';
  $('sortieInfo').textContent = '';
  $('tlabel').textContent = fmtDur(0);
  $('slider').value = 0;
}

// X-8 pages /track; the first page alone used to end a long sortie's replay
// early. Follow next_since until the server says there is no more.
async function fetchTrack(id) {
  const url = `/api/sorties/${encodeURIComponent(id)}/track`;
  const r = await vsarFetch(url);
  if (!r.ok) return {status: r.status};
  const first = await r.json();
  let page = first;
  for (let n = 0; page.next_since != null && n < 200; n++) {
    const more = await vsarFetch(`${url}?since=${encodeURIComponent(page.next_since)}`);
    if (!more.ok) break;
    const next = await more.json();
    if (!next.positions || !next.positions.length) break;
    first.positions.push(...next.positions);
    page = next;
  }
  return {body: first};
}

// The scoring never throws: a failure is something to say on the page.
async function fetchScores(id) {
  try {
    const r = await vsarFetch(`/api/sorties/${encodeURIComponent(id)}/analysis`);
    if (!r.ok) return {error: `Scoring could not be loaded (HTTP ${r.status}).`};
    return {body: await r.json()};
  } catch (e) { return {error: 'Scoring could not be loaded: the console is unreachable.'}; }
}

let loadSeq = 0;
async function load(id) {
  if (!id) return;
  clearSortie();
  const mine = ++loadSeq;
  const scoring = fetchScores(id);
  let loaded;
  try {
    const got = await fetchTrack(id);
    if (got.status) { debriefStatus(`That sortie could not be loaded (HTTP ${got.status}).`); return; }
    loaded = got.body;
  } catch (e) { debriefStatus('That sortie could not be loaded: the console is unreachable.'); return; }
  if (mine !== loadSeq) return;   // a newer selection superseded this one
  data = loaded;

  const P = data.positions;
  if (!P.length) { data = null; debriefStatus('no positions recorded for this sortie'); return; }
  t0 = P[0].t; t1 = P[P.length-1].t;
  $('slider').value = 0;

  // Colour follows the aircraft, so the slots are known before anything is drawn.
  const sc = await scoring;
  if (mine !== loadSeq) return;
  scores = sc.body || null;
  groups = groupByCallsign(P);
  const ranked = scores ? scores.aircraft.map(a => a.callsign).filter(cs => groups[cs]) : [];
  order = ranked.concat(Object.keys(groups).filter(cs => !ranked.includes(cs)).sort());
  if (scores) scores.aircraft.forEach(a => { if (a.slot) slots[a.callsign] = a.slot; });
  else order.forEach((cs, i) => { if (i < 4) slots[cs] = i + 1; });

  order.forEach(cs => {
    const col = acColor(cs);
    // faint full track per aircraft, so the shape of each search is visible
    L.polyline(groups[cs].map(p => [p.lat, p.lon]),
               {color: col, weight: 2, opacity: .35}).addTo(layers);
    flownLines[cs] = L.polyline([], {color: col, weight: 3}).addTo(layers);
  });

  if (data.beacon && data.beacon.lat != null) {
    const truth = tok('--truth');
    beacon = L.circleMarker([data.beacon.lat, data.beacon.lon],
      {radius:9, color: truth, weight:3, fillColor: truth, fillOpacity:.35})
      .addTo(layers).bindTooltip('BEACON (actual)', {permanent:true, direction:'right'});
    ring = L.circle([data.beacon.lat, data.beacon.lon],
      {radius: 1852, color: truth, weight:1, dashArray:'4,6', fill:false}).addTo(layers);
  }

  const b = L.latLngBounds(P.map(p => [p.lat, p.lon]));
  if (beacon) b.extend(beacon.getLatLng());
  map.fitBounds(b.pad(0.15));

  const info = $('sortieInfo');
  info.replaceChildren(
    make('b', null, $('sortieSel').selectedOptions[0].text.split(' — ')[1] || ''),
    make('div', 'small muted', `${P.length} position reports over ${fmtDur(t1-t0)} · ` +
      `${data.bearings.length} bearing cuts · ${data.messages.length} messages`));

  renderSummary(sc);
  renderChart(sc);
  renderMarks();
  seek(0);
}

// ------------------------------------------------------------ scoring cards
// The six measures of docs/USE_CASE_SAREX_REHEARSAL.md, per aircraft. The ones
// the console does not record yet say so rather than showing a blank.
function tile(label, value, sub, quiet) {
  const t = make('div', 'stat' + (quiet ? ' quiet' : ''));
  t.append(make('div', 'stat-label', label), make('div', 'stat-value', value));
  if (sub) t.append(make('div', 'stat-sub', sub));
  return t;
}

function verdictPill(nm) {
  // Status colour only with an icon and a word (D6).
  const [cls, icon, word] = nm < 0.5 ? ['good', '✓', 'overhead the beacon']
                          : nm < 2   ? ['', '◎', 'localised']
                          : ['warning', '!', 'did not close'];
  const p = make('span', 'pill' + (cls ? ' ' + cls : ''));
  p.append(make('span', 'pill-icon', icon), document.createTextNode(word));
  return p;
}

function renderSummary(sc) {
  const host = $('summary');
  if (!sc.body) { host.replaceChildren(make('p', 'muted', sc.error)); return; }
  const s = sc.body;
  const hidden = !s.revealed;
  // Withheld: a live sortie is flying this beacon and the viewer is not the instructor.
  const [held, why] = s.withheld ? ['withheld', 'while this beacon is being flown']
                                 : ['after reveal', 'needs the beacon position'];
  const cards = s.aircraft.map(a => {
    const card = make('article', 'ac-card s' + (a.slot || 0));
    const head = make('header', 'ac-head');
    const name = make('h3');
    name.append(make('span', 'ac-swatch s' + (a.slot || 0)), document.createTextNode(a.callsign));
    head.append(name);
    if (a.cpa) head.append(verdictPill(a.cpa.nm));
    const c = a.counts;
    card.append(head, make('div', 'ac-counts',
      `${c.positions} positions · ${c.bearings} bearings · ${c.messages} messages`));

    const tiles = make('div', 'stats');
    const df = a.df_error_stats, be = a.bearing_error_stats, g = s.good_cut_deg;
    if (hidden) {
      tiles.append(tile('Needle error', held, why, true),
                   tile('Logged bearing error', held, why, true),
                   tile('Closest approach', held, why, true),
                   tile('First good cut', held, why, true),
                   tile('Track efficiency', held, `flown ${a.flown_nm.toFixed(1)} nm`, true));
    } else {
      tiles.append(
        df ? tile('Needle error', `${df.mean_abs.toFixed(1)}°`,
                  `mean |error| of ${df.n} readings · worst ${df.max_abs.toFixed(0)}°`)
           : tile('Needle error', 'not recorded', 'no DF readings with this track', true),
        be ? tile('Logged bearing error', `${be.mean_abs.toFixed(1)}°`,
                  `mean |error| of ${be.n} · ${be.good} within ${g}°`)
           : tile('Logged bearing error', 'none logged', 'no bearings from this aircraft', true),
        a.cpa ? tile('Closest approach', `${a.cpa.nm.toFixed(2)} nm`, `at ${fmtDur(a.cpa.t - t0)}`)
              : tile('Closest approach', 'not recorded', 'no positions', true),
        a.first_good_cut
          ? tile('First good cut', fmtDur(a.first_good_cut.t - t0),
                 `${vizSigned(a.first_good_cut.error)} · first bearing within ${g}°`)
          : tile('First good cut', 'none', be ? `no bearing within ${g}°` : 'no bearings logged', true),
        a.track ? tile('Track efficiency', `${a.track.efficiency_pct.toFixed(0)}%`,
                       `direct ${a.track.direct_nm.toFixed(1)} nm ÷ flown ${a.track.flown_nm.toFixed(1)} nm`)
                : tile('Track efficiency', 'not recorded', 'no positions', true));
    }
    tiles.append(tile('Ops-normal timing', 'not recorded', 'no ops-normal log yet', true),
                 tile('Rejected cuts', 'not recorded', 'the bearing log has no reject flag', true),
                 tile('Change since last session', 'not recorded', 'cross-session view not built', true));
    card.append(tiles);
    return card;
  });
  host.replaceChildren(...cards);
  if (!cards.length) host.append(make('p', 'muted', 'No aircraft reported in this sortie.'));
}

// ---------------------------------------------------------- bearing-error chart
function renderChart(sc) {
  const host = $('errChart');
  const s = sc.body;
  const spec = {x0: t0, x1: Math.max(t1, t0 + 1), fmtT: t => fmtDur(Math.max(0, t - t0)),
                series: [], band: s ? s.good_cut_deg : 10, onSeek: seekTo};
  if (!s) spec.empty = sc.error;
  else if (s.withheld) spec.empty = 'Withheld: this beacon is being flown in a live sortie. ' +
    'It appears here once that sortie is revealed.';
  else if (!s.revealed) spec.empty = 'Bearing error is measured against the beacon, ' +
    'which this sortie has not revealed yet.';
  else {
    spec.series = s.aircraft.map(a => ({
      label: a.callsign, slot: a.slot,
      line: (a.df_error || []).map(p => ({t: p.t, v: p.error, flag: p.in_cone ? 'in cone' : ''})),
      dots: (a.bearing_error || []).map(b => ({t: b.t, v: b.error,
        detail: `${Number(b.bearing_true).toFixed(0)}°T` + (b.note ? ' · ' + b.note : '')})),
    }));
    if (!spec.series.some(x => x.line.length || x.dots.length))
      spec.empty = 'No DF readings or logged bearings were recorded in this sortie.';
    const fx = s.effects_active.map(e => e.label);
    spec.note = fx.length
      ? `Effects on at the end of the sortie: ${fx.join(', ')}. When each was switched is not recorded yet.`
      : 'No effects were on at the end of the sortie.';
  }
  chart = vizErrorChart(host, spec);
}

// ------------------------------------------------------------- slider marks
// Logged bearings (aircraft colour) and messages (ink) along the replay
// slider; click one to jump there. The thumb is 16 px (debrief.css), so a mark
// at fraction f sits where the thumb's centre would.
function renderMarks() {
  const host = $('marks');
  const span = Math.max(t1 - t0, 1);
  const mark = (t, cls, label) => {
    const f = Math.max(0, Math.min(1, (t - t0) / span));
    const m = make('button', 'mark ' + cls);
    m.type = 'button';
    m.style.left = `calc(8px + (100% - 16px) * ${f.toFixed(5)})`;
    m.setAttribute('aria-label', label);
    m.title = label;
    m.addEventListener('click', () => seekTo(t));
    return m;
  };
  const marks = [];
  data.bearings.forEach(b => marks.push(mark(b.t, 'brg s' + slotOf(b.callsign),
    `${fmtDur(b.t - t0)} ${b.callsign} bearing ${Number(b.bearing_true).toFixed(0)}°T`)));
  data.messages.forEach(m => marks.push(mark(m.t, 'msg',
    `${fmtDur(m.t - t0)} message ${m.sender} to ${m.recipient}`)));
  host.replaceChildren(...marks);
}

function seekTo(t) {
  if (!data) return;
  const v = Math.max(0, Math.min(100, (t - t0) / Math.max(t1 - t0, 1) * 100));
  $('slider').value = v;
  seek(v / 100);
}

function seek(frac) {
  if (!data) return;
  const t = t0 + (t1 - t0) * frac;
  $('tlabel').textContent = fmtDur(t - t0);
  if (chart) chart.setCursor(t);

  order.forEach(cs => {
    const upto = groups[cs].filter(p => p.t <= t);
    if (!upto.length) return;
    const p = upto[upto.length-1];
    flownLines[cs].setLatLngs(upto.map(q => [q.lat, q.lon]));
    const prev = upto.length > 1 ? upto[upto.length-2] : p;
    const icon = L.divIcon({className: 'ac-icon s' + slotOf(cs), iconSize: [26, 26],
                            html: planeIcon(headingOf(p, prev)).options.html});
    if (!acMarkers[cs]) {
      acMarkers[cs] = L.marker([p.lat, p.lon], {icon}).addTo(layers)
        .bindTooltip(esc(cs), {permanent:true, direction:'top', offset:[0,-8]});
    } else {
      acMarkers[cs].setLatLng([p.lat, p.lon]).setIcon(icon);
    }
  });
  renderEvents(t);
}

// Newest first. Rebuilt only when the set of events up to `t` changes, not on
// every 250 ms tick.
function renderEvents(t) {
  const ev = [];
  data.bearings.filter(b => b.t <= t).forEach(b => ev.push({t: b.t, who: b.callsign, slot: slotOf(b.callsign),
    text: `bearing ${Number(b.bearing_true).toFixed(0)}°T${b.note ? ' — ' + b.note : ''}`}));
  data.messages.filter(m => m.t <= t).forEach(m => ev.push({t: m.t, who: `${m.sender} → ${m.recipient}`,
    text: m.body}));
  if (ev.length === eventsShown) return;
  eventsShown = ev.length;
  ev.sort((a, b) => b.t - a.t);
  const host = $('events');
  if (!ev.length) { host.textContent = '—'; return; }
  host.replaceChildren(...ev.map(e => {
    const li = make('li');
    const body = make('span');
    const who = make('span', 'from', e.who);
    if (e.slot) who.prepend(make('span', 'ac-swatch s' + e.slot));
    body.append(who, document.createTextNode(e.text));
    li.append(make('time', null, fmtDur(e.t - t0)), body);
    return li;
  }));
}

$('slider').oninput = e => seek(e.target.value / 100);
$('sortieSel').onchange = e => { load(e.target.value); };
$('play').onclick = () => playing ? stop() : start();

function start() {
  playing = true; $('play').textContent = 'Pause';
  const step = () => {
    let v = parseFloat($('slider').value) + (parseFloat($('speed').value) * 100) / Math.max(t1-t0, 1) * 0.25;
    if (v >= 100) { v = 100; stop(); }
    $('slider').value = v; seek(v/100);
  };
  timer = setInterval(step, 250);
}
function stop() { playing = false; $('play').textContent = 'Play'; clearInterval(timer); }

loadList();
