const $ = id => document.getElementById(id);
const map = L.map('map').setView([33.15, -117.18], 11);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom: 18, attribution: '&copy; OpenStreetMap'}).addTo(map);

const EFFECTS = [
  ['radio_horizon',     'Radio horizon',      'Nothing until you climb'],
  ['burst_cadence',     '406 burst cadence',  'Needle updates ~every 50 s, then holds'],
  ['cone_of_confusion', 'Cone of confusion',  'Bearing indeterminate overhead'],
  ['multipath',         'Multipath',          'A confident, wrong bearing'],
];

let state = {}, acLayers = {}, trackLines = {}, beaconMarker = null;
const bearingLayer = L.layerGroup().addTo(map);
const bearingLog = [];
let followed = false;

const planeIcon = c => L.divIcon({className:'', iconSize:[26,26], html:
  `<svg width="26" height="26" viewBox="0 0 24 24" style="transform:rotate(${c}deg)">
     <path d="M12 2 L15 11 L22 13 L22 15 L13.5 14 L13 20 L16 22 L16 23 L12 22 L8 23 L8 22 L11 20 L10.5 14 L2 15 L2 13 L9 11 Z"
       fill="#2e5496" stroke="#1f3864" stroke-width="0.8"/></svg>`});

// ---------------------------------------------------------------- websocket
function connect() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen  = () => { $('status').textContent = 'live'; $('status').className = 'status online'; };
  ws.onclose = () => { $('status').textContent = 'reconnecting'; $('status').className = 'status offline';
                       setTimeout(connect, 2000); };
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.type === 'state')   { state = m; render(); }
    if (m.type === 'bearing') { addBearing(m); }
  };
}

// ------------------------------------------------------------------- render
function render() {
  const s = state.sortie, sc = state.scenario;

  $('sortieBox').innerHTML = s
    ? `<b>${s.name}</b><br><span class="df">${s.stopped ? 'STOPPED' : 'running'} &middot; ${
        fmtDur((state.server_time - s.started))}${s.revealed ? ' &middot; <span class="no">truth revealed</span>' : ''}</span>`
    : 'no sortie running';
  $('startBtn').disabled  = !!(s && !s.stopped);
  $('stopBtn').disabled   = !(s && !s.stopped);
  $('revealBtn').disabled = !s || !!s.revealed;

  // effects
  if (sc && $('effects').dataset.for !== (sc.id || '')) {
    $('effects').dataset.for = sc.id || '';
    $('effects').innerHTML = EFFECTS.map(([k, label, hint]) =>
      `<label title="${hint}"><input type="checkbox" data-k="${k}" ${sc.effects[k] ? 'checked' : ''}> ${label}</label>`
    ).join('');
    $('effects').querySelectorAll('input').forEach(i => i.onchange = () =>
      fetch('/api/sorties/effects', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({[i.dataset.k]: i.checked})}));
  }

  // aircraft list + markers
  const list = state.aircraft || [];
  $('aircraft').innerHTML = list.length ? list.map(a => {
    const d = a.df;
    let df = '<span class="no">no DF</span>';
    if (d) df = d.valid
      ? `<span class="ok">BRG ${d.bearing_rel.toFixed(0)}&deg; rel</span> &middot; ${d.distance_nm} nm &middot; sig ${(d.signal*100).toFixed(0)}%${d.note ? ` <span class="tag">${d.note}</span>` : ''}`
      : `<span class="no">${d.note || 'no signal'}</span> &middot; ${d.distance_nm} nm`;
    return `<div class="ac"><b>${a.callsign}</b> <span class="df">${a.alt_ft.toFixed(0)} ft &middot; hdg ${a.hdg_true.toFixed(0)}&deg;</span>
            <div class="df">${df}</div></div>`;
  }).join('') : 'none reporting';

  const seen = new Set();
  list.forEach(a => {
    seen.add(a.callsign);
    const ll = [a.lat, a.lon];
    if (!acLayers[a.callsign]) {
      acLayers[a.callsign] = L.marker(ll, {icon: planeIcon(a.hdg_true)}).addTo(map).bindTooltip(a.callsign);
      trackLines[a.callsign] = L.polyline([ll], {color:'#2e5496', weight:2, opacity:.65}).addTo(map);
    } else {
      acLayers[a.callsign].setLatLng(ll).setIcon(planeIcon(a.hdg_true));
      trackLines[a.callsign].addLatLng(ll);
    }
    if (!followed) { map.setView(ll, 11); followed = true; }
  });
  Object.keys(acLayers).forEach(k => {
    if (!seen.has(k)) { map.removeLayer(acLayers[k]); delete acLayers[k]; }
  });

  // beacon truth, only once revealed
  if (sc && sc.beacon_lat != null) {
    if (!beaconMarker) {
      beaconMarker = L.circleMarker([sc.beacon_lat, sc.beacon_lon],
        {radius:9, color:'#c00000', weight:3, fillColor:'#c00000', fillOpacity:.35})
        .addTo(map).bindTooltip('BEACON (truth)', {permanent:true, direction:'right'});
    }
  } else if (beaconMarker) {
    map.removeLayer(beaconMarker); beaconMarker = null;
  }
}

function addBearing(m) {
  bearingLog.unshift(m);
  const lat1 = m.lat * Math.PI/180;
  const R = 40 / 60; // 40 nm ray, in degrees of latitude
  const brg = m.bearing_true * Math.PI/180;
  const lat2 = m.lat + R * Math.cos(brg);
  const lon2 = m.lon + R * Math.sin(brg) / Math.cos(lat1);
  L.polyline([[m.lat, m.lon], [lat2, lon2]],
    {color:'#c00000', weight:2, dashArray:'6,5', opacity:.8}).addTo(bearingLayer);
  $('bearings').innerHTML = bearingLog.map(b =>
    `<div class="brg">${b.callsign} &rarr; ${b.bearing_true.toFixed(0)}&deg;T${b.note ? ' &middot; ' + b.note : ''}</div>`
  ).join('');
}

const fmtDur = s => `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;

// -------------------------------------------------------------------- wiring
async function loadScenarios() {
  const r = await fetch('/api/scenarios'); const list = await r.json();
  $('scenarioSel').innerHTML = list.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
  const show = () => {
    const s = list.find(x => x.id === $('scenarioSel').value);
    $('scenarioNotes').textContent = s ? s.notes : '';
  };
  $('scenarioSel').onchange = show; show();
}

$('startBtn').onclick = async () => {
  await fetch('/api/sorties', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({scenario_id: $('scenarioSel').value})});
  bearingLayer.clearLayers(); bearingLog.length = 0;
  Object.values(trackLines).forEach(l => map.removeLayer(l)); trackLines = {};
  $('bearings').textContent = 'no bearings logged';
  $('effects').dataset.for = '';
};
$('stopBtn').onclick   = () => fetch('/api/sorties/stop',   {method:'POST'});
$('revealBtn').onclick = () => fetch('/api/sorties/reveal', {method:'POST'});
$('brgAdd').onclick = async () => {
  const cs = $('brgCallsign').value.trim(), v = parseFloat($('brgValue').value);
  if (!cs || isNaN(v)) return;
  const r = await fetch('/api/bearings', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({callsign: cs, bearing_true: v})});
  if (r.ok) $('brgValue').value = '';
};

setInterval(() => $('clock').textContent = new Date().toUTCString().slice(17, 25) + 'Z', 1000);
loadScenarios(); connect();
