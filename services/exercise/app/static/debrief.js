// Replay a recorded sortie against beacon truth. Per the plan this is the
// highest-value artefact the system produces, so it always shows the answer.
const $ = id => document.getElementById(id);
const map = L.map('map').setView([33.15, -117.18], 11);
capvsarCharts(map, {view: 'debrief'});

let data = null, t0 = 0, t1 = 0, playing = false, timer = null;
const layers = L.layerGroup().addTo(map);
let acMarker = null, flown = null, beacon = null, ring = null;

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
  acMarker = flown = beacon = ring = null;

  const P = data.positions;
  if (!P.length) { $('sortieInfo').textContent = 'no positions recorded for this sortie'; return; }
  t0 = P[0].t; t1 = P[P.length-1].t;
  $('slider').value = 0;

  // full track, faint, so the shape of the search is visible at a glance
  L.polyline(P.map(p => [p.lat, p.lon]), {color:'#8eaadb', weight:2, opacity:.45}).addTo(layers);
  flown = L.polyline([], {color:'#2e5496', weight:3}).addTo(layers);

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

  // scoring: how close did they get, and how efficiently
  if (data.beacon && data.beacon.lat != null) {
    let best = Infinity, bestT = 0, flownNm = 0;
    P.forEach((p, i) => {
      const d = distNm(p.lat, p.lon, data.beacon.lat, data.beacon.lon);
      if (d < best) { best = d; bestT = p.t - t0; }
      if (i) flownNm += distNm(P[i-1].lat, P[i-1].lon, p.lat, p.lon);
    });
    const direct = distNm(P[0].lat, P[0].lon, data.beacon.lat, data.beacon.lon);
    $('result').innerHTML =
      `<div>closest approach <b>${best.toFixed(2)} nm</b> at ${fmt(bestT)}</div>
       <div class="df">track flown ${flownNm.toFixed(1)} nm &middot; direct line ${direct.toFixed(1)} nm
       &middot; efficiency ${(direct/Math.max(flownNm,0.01)*100).toFixed(0)}%</div>
       <div class="df">${best < 0.5 ? 'overhead the beacon' : best < 2 ? 'localised' : 'did not close'}</div>`;
  } else {
    $('result').innerHTML = '<span class="df">beacon truth was never revealed for this sortie</span>';
  }
  seek(0);
}

function seek(frac) {
  if (!data) return;
  const t = t0 + (t1 - t0) * frac;
  $('tlabel').textContent = fmt(t - t0);

  const upto = data.positions.filter(p => p.t <= t);
  if (upto.length) {
    const p = upto[upto.length-1];
    flown.setLatLngs(upto.map(q => [q.lat, q.lon]));
    if (!acMarker) acMarker = L.marker([p.lat, p.lon], {icon: planeIcon(0)}).addTo(layers);
    else acMarker.setLatLng([p.lat, p.lon]);
    const prev = upto.length > 1 ? upto[upto.length-2] : p;
    const hdg = Math.atan2(p.lon-prev.lon, p.lat-prev.lat) * 180/Math.PI;
    acMarker.setIcon(planeIcon(hdg));
  }

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
