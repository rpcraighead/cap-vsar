// Replay a recorded sortie against beacon truth. Per the plan this is the
// highest-value artefact the system produces, so it always shows the answer.
const $ = id => document.getElementById(id);
const map = L.map('map').setView([33.15, -117.18], 11);
capvsarCharts(map, {view: 'debrief'});

let data = null, t0 = 0, t1 = 0, playing = false, timer = null;
const layers = L.layerGroup().addTo(map);
let beacon = null, ring = null;

// One sortie can have three aircraft airborne at once. Everything below is
// per-callsign: a single shared track polyline zig-zagged between aircraft,
// and summing consecutive points across them made "track flown" and closest
// approach meaningless - which is the scoring the evaluator reads at debrief.
const AC_COLORS = ['#2e5496', '#c55a11', '#548235', '#7030a0', '#bf8f00'];
let groups = {}, order = [], acMarkers = {}, flownLines = {};

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

const planeIcon = c => L.divIcon({className:'', iconSize:[26,26], html:
  `<svg width="26" height="26" viewBox="0 0 24 24" style="transform:rotate(${c}deg)">
     <path d="M12 2 L15 11 L22 13 L22 15 L13.5 14 L13 20 L16 22 L16 23 L12 22 L8 23 L8 22 L11 20 L10.5 14 L2 15 L2 13 L9 11 Z"
       fill="#2e5496" stroke="#1f3864" stroke-width="0.8"/></svg>`});

const fmt = s => `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;
const R_NM = 3440.065;
const distNm = (a, b, c, d) => {
  const r = Math.PI/180, dla=(c-a)*r, dlo=(d-b)*r;
  const h = Math.sin(dla/2)**2 + Math.cos(a*r)*Math.cos(c*r)*Math.sin(dlo/2)**2;
  return 2*R_NM*Math.asin(Math.min(1, Math.sqrt(h)));
};

async function loadList() {
  const list = await (await fetch('/api/sorties')).json();
  $('sortieSel').innerHTML = list.map(s => {
    const d = new Date(s.started*1000).toISOString().slice(0,16).replace('T',' ');
    return `<option value="${s.id}">${d}Z — ${s.name} (${s.points} pts)</option>`;
  }).join('') || '<option value="">no sorties recorded</option>';
  if (list.length) load($('sortieSel').value);
}

async function load(id) {
  if (!id) return;
  data = await (await fetch(`/api/sorties/${id}/track`)).json();
  layers.clearLayers();
  beacon = ring = null;
  acMarkers = {}; flownLines = {};

  const P = data.positions;
  if (!P.length) { $('sortieInfo').textContent = 'no positions recorded for this sortie'; return; }
  t0 = P[0].t; t1 = P[P.length-1].t;
  $('slider').value = 0;

  groups = groupByCallsign(P);
  order = Object.keys(groups).sort();
  order.forEach((cs, i) => {
    const col = AC_COLORS[i % AC_COLORS.length];
    // faint full track per aircraft, so the shape of each search is visible
    L.polyline(groups[cs].map(p => [p.lat, p.lon]),
               {color: col, weight: 2, opacity: .35}).addTo(layers);
    flownLines[cs] = L.polyline([], {color: col, weight: 3}).addTo(layers);
  });

  if (data.beacon && data.beacon.lat != null) {
    beacon = L.circleMarker([data.beacon.lat, data.beacon.lon],
      {radius:9, color:'#c00000', weight:3, fillColor:'#c00000', fillOpacity:.35})
      .addTo(layers).bindTooltip('BEACON (actual)', {permanent:true, direction:'right'});
    ring = L.circle([data.beacon.lat, data.beacon.lon],
      {radius: 1852, color:'#c00000', weight:1, dashArray:'4,6', fill:false}).addTo(layers);
  }

  const b = L.latLngBounds(P.map(p => [p.lat, p.lon]));
  if (beacon) b.extend(beacon.getLatLng());
  map.fitBounds(b.pad(0.15));

  $('sortieInfo').innerHTML =
    `<b>${$('sortieSel').selectedOptions[0].text.split(' — ')[1] || ''}</b>
     <div class="df">${P.length} position reports over ${fmt(t1-t0)}
     &middot; ${data.bearings.length} bearing cuts &middot; ${data.messages.length} messages</div>`;

  // Scoring, per aircraft: how close each got, and how efficiently it searched.
  if (data.beacon && data.beacon.lat != null) {
    $('result').innerHTML = order.map((cs, i) => {
      const G = groups[cs];
      let best = Infinity, bestT = 0, flownNm = 0;
      G.forEach((p, j) => {
        const d = distNm(p.lat, p.lon, data.beacon.lat, data.beacon.lon);
        if (d < best) { best = d; bestT = p.t - t0; }
        if (j) flownNm += distNm(G[j-1].lat, G[j-1].lon, p.lat, p.lon);
      });
      const direct = distNm(G[0].lat, G[0].lon, data.beacon.lat, data.beacon.lon);
      const verdict = best < 0.5 ? 'overhead the beacon'
                    : best < 2   ? 'localised' : 'did not close';
      return `<div style="border-left:3px solid ${AC_COLORS[i % AC_COLORS.length]};padding-left:8px;margin-bottom:8px">
         <div><b>${cs}</b> — closest approach <b>${best.toFixed(2)} nm</b> at ${fmt(bestT)}</div>
         <div class="df">track flown ${flownNm.toFixed(1)} nm &middot; direct line ${direct.toFixed(1)} nm
         &middot; efficiency ${(direct/Math.max(flownNm,0.01)*100).toFixed(0)}%</div>
         <div class="df">${verdict}</div></div>`;
    }).join('');
  } else {
    $('result').innerHTML = '<span class="df">beacon truth was never revealed for this sortie</span>';
  }
  seek(0);
}

function seek(frac) {
  if (!data) return;
  const t = t0 + (t1 - t0) * frac;
  $('tlabel').textContent = fmt(t - t0);

  order.forEach(cs => {
    const upto = groups[cs].filter(p => p.t <= t);
    if (!upto.length) return;
    const p = upto[upto.length-1];
    flownLines[cs].setLatLngs(upto.map(q => [q.lat, q.lon]));
    const prev = upto.length > 1 ? upto[upto.length-2] : p;
    const hdg = headingOf(p, prev);
    if (!acMarkers[cs]) {
      acMarkers[cs] = L.marker([p.lat, p.lon], {icon: planeIcon(hdg)}).addTo(layers)
        .bindTooltip(cs, {permanent:true, direction:'top', offset:[0,-8]});
    } else {
      acMarkers[cs].setLatLng([p.lat, p.lon]).setIcon(planeIcon(hdg));
    }
  });

  const ev = [];
  data.bearings.filter(b => b.t <= t).forEach(b =>
    ev.push({t: b.t, s: `${b.callsign} bearing ${b.bearing_true.toFixed(0)}&deg;T${b.note ? ' — ' + b.note : ''}`}));
  data.messages.filter(m => m.t <= t).forEach(m =>
    ev.push({t: m.t, s: `<b>${m.sender} &rarr; ${m.recipient}</b> ${m.body}`}));
  ev.sort((a,b) => b.t - a.t);
  $('events').innerHTML = ev.length
    ? ev.map(e => `<div class="brg">${fmt(e.t - t0)} &nbsp; ${e.s}</div>`).join('')
    : '—';
}

$('slider').oninput = e => seek(e.target.value / 100);
$('sortieSel').onchange = e => { stop(); load(e.target.value); };
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

setInterval(() => $('clock').textContent = new Date().toUTCString().slice(17,25) + 'Z', 1000);
loadList();
