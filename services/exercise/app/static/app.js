const $ = id => document.getElementById(id);

// esc(), planeIcon, fmtDur, the socket, clock and auth badge: charts.js.
// The great-circle geometry (bearingDestination): geodesy.js.

const map = L.map('map').setView([33.15, -117.18], 11);
capvsarCharts(map, {view: 'instructor'});

const EFFECTS = [
  ['radio_horizon',     'Radio horizon',      'Nothing until you climb'],
  ['burst_cadence',     '406 burst cadence',  'Needle updates ~every 50 s, then holds'],
  ['cone_of_confusion', 'Cone of confusion',  'Bearing indeterminate overhead'],
  ['multipath',         'Multipath',          'A confident, wrong bearing'],
  ['airframe_shadowing','Wing blanking',      'Banking can shield the selected antenna'],
];

let state = {}, acLayers = {}, trackLines = {}, beaconMarker = null;
const bearingLayer = L.layerGroup().addTo(map);
const bearingLog = [];
let followed = false;

// ---------------------------------------------------------------- websocket
let sortieId = null, lastBearingT = 0;
const seenBearings = new Set();

function connect() {
  vsarConnect({
    onOpen: () => backfill(),
    onMessage: m => {
      if (m.type === 'state')   { state = m; render(); }
      if (m.type === 'bearing') { addBearing(m); }
    },
  });
}

// A new sortie, seen by whichever console pressed Start (or none: this page
// may have been opened mid-sortie, or reloaded). Everything drawn belonged to
// the last one. The aircraft markers go too: render() only builds a track line
// when it builds a marker, so keeping the markers and dropping the lines threw
// on the next position report.
function resetSortieView() {
  bearingLayer.clearLayers(); bearingLog.length = 0;
  seenBearings.clear(); lastBearingT = 0;
  Object.values(trackLines).forEach(l => map.removeLayer(l)); trackLines = {};
  Object.values(acLayers).forEach(l => map.removeLayer(l)); acLayers = {};
  $('bearings').textContent = 'no bearings logged';
  $('effects').dataset.for = '';
}

// F-4 for the instructor: bearings logged while this socket was down.
async function backfill() {
  try {
    const since = Math.max(0, lastBearingT - .001);
    const r = await fetch(`/api/bearings?since=${since}`);
    if (r.ok) (await r.json()).forEach(addBearing);
  } catch (e) { /* the next reconnect tries again */ }
}

// ------------------------------------------------------------------- render
function render() {
  const s = state.sortie, sc = state.scenario;

  const id = s ? s.id : null;
  if (id !== sortieId) { resetSortieView(); sortieId = id; if (id) backfill(); }

  $('sortieBox').innerHTML = s
    ? `<b>${esc(s.name)}</b><br><span class="df">${s.stopped ? 'STOPPED' : 'running'} &middot; ${
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
    ).join('') + `<label title="Physical antenna installation used by the propagation engine">DF antenna
      <select id="liveAntennaProfile"><option value="c182_belly">C182 belly</option><option value="c182_top">C182 top</option></select></label>`;
    $('liveAntennaProfile').value = sc.effects.df_antenna_profile || 'c182_belly';
    $('liveAntennaProfile').onchange = e =>
      vsarFetch('/api/sorties/effects', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({df_antenna_profile: e.target.value})});
    $('effects').querySelectorAll('input').forEach(i => i.onchange = () =>
      vsarFetch('/api/sorties/effects', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({[i.dataset.k]: i.checked})}));
  }

  // aircraft list + markers
  const list = state.aircraft || [];
  $('aircraft').innerHTML = list.length ? list.map(a => {
    const d = a.df;
    let df = '<span class="no">no DF</span>';
    if (d) {
      const detail = [];
      if (Number.isFinite(d.roll_deg)) detail.push(`bank ${d.roll_deg.toFixed(0)}&deg;`);
      if (d.airframe_shadowed)
        detail.push(`airframe ${Number(d.airframe_attenuation_db || 0).toFixed(0)} dB`);
      if (d.rx_open === false && d.valid) detail.push('RX closed / bearing held');
      const suffix = detail.length ? ` &middot; ${detail.join(' &middot; ')}` : '';
      // U-3: a redacted dictionary (receiver state only) has no bearing,
      // distance or signal; show what is there rather than "NaN".
      const nm  = d.distance_nm ? ` &middot; ${esc(d.distance_nm)} nm` : '';
      const sig = Number.isFinite(d.signal) ? ` &middot; sig ${(d.signal*100).toFixed(0)}%` : '';
      df = d.valid
        ? (Number.isFinite(d.bearing_rel)
            ? `<span class="ok">BRG ${Number(d.bearing_rel).toFixed(0)}&deg; rel</span>${nm}${sig}${suffix}${d.note ? ` <span class="tag">${esc(d.note)}</span>` : ''}`
            : `<span class="ok">receiving</span> &middot; <span class="no">bearing withheld for this seat</span>${suffix}`)
        : `<span class="no">${esc(d.note || 'no signal')}</span>${nm}${suffix}`;
    }
    return `<div class="ac"><b>${esc(a.callsign)}</b> <span class="df">${a.alt_ft.toFixed(0)} ft &middot; hdg ${a.hdg_true.toFixed(0)}&deg;</span>
            <div class="df">${df}</div></div>`;
  }).join('') : 'none reporting';

  const seen = new Set();
  list.forEach(a => {
    seen.add(a.callsign);
    const ll = [a.lat, a.lon];
    if (!acLayers[a.callsign]) {
      acLayers[a.callsign] = L.marker(ll, {icon: planeIcon(a.hdg_true)}).addTo(map).bindTooltip(esc(a.callsign));
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
  const key = m.id != null ? `bearing:${m.id}` :
    `bearing:${m.t}:${m.callsign}:${m.bearing_true}`;
  if (seenBearings.has(key)) return;
  seenBearings.add(key); lastBearingT = Math.max(lastBearingT, m.t || 0);
  bearingLog.unshift(m);
  // The same great-circle ray the mission base draws (geodesy.js), not a flat
  // approximation of it.
  const endpoint = bearingDestination(m.lat, m.lon, m.bearing_true, 40);
  L.polyline([[m.lat, m.lon], endpoint],
    {color:'#c00000', weight:2, dashArray:'6,5', opacity:.8}).addTo(bearingLayer);
  $('bearings').innerHTML = bearingLog.map(b =>
    `<div class="brg">${esc(b.callsign)} &rarr; ${b.bearing_true.toFixed(0)}&deg;T${b.note ? ' &middot; ' + esc(b.note) : ''}</div>`
  ).join('');
}

// -------------------------------------------------------------------- wiring
async function loadScenarios(selectId) {
  // F2-9: an expired session or a 503 used to reach r.json() and leave the
  // scenario list empty with nothing said.
  const r = await fetch('/api/scenarios');
  if (!r.ok) {
    $('scenarioNotes').textContent = r.status === 401 || r.status === 403
      ? 'Scenarios unavailable: log in again.'
      : `Scenarios could not be loaded (HTTP ${r.status}).`;
    if (r.status === 401 || r.status === 403) vsarGoToLogin();
    return;
  }
  const list = await r.json();
  $('scenarioSel').innerHTML = list.map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');
  if (selectId) $('scenarioSel').value = selectId;
  const show = () => {
    const s = list.find(x => x.id === $('scenarioSel').value);
    $('scenarioNotes').textContent = s ? s.notes : '';
  };
  $('scenarioSel').onchange = show; show();
}

// The view resets itself when the pushed state names a new sortie
// (resetSortieView), so a Start the server refused leaves the old one on screen.
$('startBtn').onclick = async () => {
  const r = await vsarFetch('/api/sorties', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({scenario_id: $('scenarioSel').value})});
  if (!r.ok) await vsarReportFailure(r, 'Sortie not started');
};
$('stopBtn').onclick = async () => {
  const r = await vsarFetch('/api/sorties/stop', {method:'POST'});
  if (!r.ok) await vsarReportFailure(r, 'Sortie not stopped');
};
$('revealBtn').onclick = async () => {
  const r = await vsarFetch('/api/sorties/reveal', {method:'POST'});
  if (!r.ok) await vsarReportFailure(r, 'Beacon not revealed');
};
$('brgAdd').onclick = async () => {
  const cs = $('brgCallsign').value.trim(), v = parseFloat($('brgValue').value);
  if (!cs || isNaN(v)) return;
  const r = await vsarFetch('/api/bearings', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({callsign: cs, bearing_true: v})});
  if (r.ok) $('brgValue').value = '';
  else await vsarReportFailure(r, 'Bearing not logged');
};

// ------------------------------------------------------------- new scenario
// Two ways in, because an instructor has coordinates sometimes and a chart the
// rest of the time: type lat/lon, or pick the point off the sectional. The pin
// is amber so it is never mistaken for the red truth marker, which still only
// appears after the beacon is revealed.
const pinIcon = L.divIcon({className:'', iconSize:[18,18], iconAnchor:[9,9], html:
  `<div style="width:14px;height:14px;border-radius:50%;background:#e8a33d;
     border:2px solid #8a5a00;box-shadow:0 0 0 2px rgba(255,255,255,.75)"></div>`});

let pickPin = null, picking = false;

const nsMsg = (t, bad) => {
  $('nsMsg').textContent = t || '';
  $('nsMsg').className = 'notes' + (bad ? ' nsMsg-err' : '');
};

function nsMovePin(lat, lon) {
  if (!pickPin) {
    pickPin = L.marker([lat, lon], {icon: pinIcon, draggable: true, zIndexOffset: 500})
      .addTo(map).bindTooltip('new beacon', {direction:'right'});
    pickPin.on('drag', e => {
      const ll = e.target.getLatLng();
      $('nsLat').value = ll.lat.toFixed(6);
      $('nsLon').value = ll.lng.toFixed(6);
    });
  } else {
    pickPin.setLatLng([lat, lon]);
  }
}

function nsSetPicking(on) {
  picking = on;
  $('nsPick').textContent = on ? 'Click the map\u2026' : 'Pick on map';
  $('nsPick').classList.toggle('active', on);
  map.getContainer().classList.toggle('picking', on);
}

map.on('click', e => {
  if (!picking) return;
  $('nsLat').value = e.latlng.lat.toFixed(6);
  $('nsLon').value = e.latlng.lng.toFixed(6);
  nsMovePin(e.latlng.lat, e.latlng.lng);
  nsSetPicking(false);
  nsMsg('');
});

// Typing coordinates moves the pin, but never rewrites what is being typed.
['nsLat', 'nsLon'].forEach(id => $(id).addEventListener('input', () => {
  const la = parseFloat($('nsLat').value), lo = parseFloat($('nsLon').value);
  if (isFinite(la) && isFinite(lo) && Math.abs(la) <= 90 && Math.abs(lo) <= 180)
    nsMovePin(la, lo);
}));

$('nsPick').onclick = () => nsSetPicking(!picking);

$('nsClear').onclick = () => {
  ['nsName', 'nsLat', 'nsLon', 'nsNotes'].forEach(id => $(id).value = '');
  $('nsElev').value = '0';
  if (pickPin) { map.removeLayer(pickPin); pickPin = null; }
  nsSetPicking(false);
  nsMsg('');
};

function nsRenderEffects() {
  const on = {radio_horizon: true, burst_cadence: true, cone_of_confusion: true,
              multipath: false, airframe_shadowing: false};
  $('nsEffects').innerHTML = EFFECTS.map(([k, label, hint]) =>
    `<label title="${hint}"><input type="checkbox" data-k="${k}" ${on[k] ? 'checked' : ''}> ${label}</label>`
  ).join('');
}

$('nsCreate').onclick = async () => {
  const name = $('nsName').value.trim();
  const lat  = parseFloat($('nsLat').value);
  const lon  = parseFloat($('nsLon').value);
  const elev = parseFloat($('nsElev').value);

  if (!name)  return nsMsg('Give the scenario a name.', true);
  if (!isFinite(lat) || Math.abs(lat) > 90)
    return nsMsg('Latitude must be a number between -90 and 90.', true);
  if (!isFinite(lon) || Math.abs(lon) > 180)
    return nsMsg('Longitude must be a number between -180 and 180.', true);
  if (!isFinite(elev))
    return nsMsg('Ground elevation must be a number, in feet MSL.', true);

  // The offset is what multipath swings the false bearing by; the server keeps
  // it alongside the on/off switches.
  const effects = {multipath_offset_deg: 40.0, wing_null_max_loss_db: 24.0,
                   df_antenna_profile: $('nsAntennaProfile').value};
  $('nsEffects').querySelectorAll('input').forEach(i => effects[i.dataset.k] = i.checked);

  nsMsg('creating\u2026');
  const r = await vsarFetch('/api/scenarios', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      name, notes: $('nsNotes').value.trim(),
      beacon_lat: lat, beacon_lon: lon, beacon_elev_ft: elev,
      band: $('nsBand').value, power: 1.0, effects,
    })});

  if (!r.ok) return nsMsg(`Create failed (${r.status}). Check the coordinates and band.`, true);

  const {id} = await r.json();
  await loadScenarios(id);
  if (pickPin) { map.removeLayer(pickPin); pickPin = null; }
  nsSetPicking(false);
  nsMsg(`Created and selected. Press Start sortie to fly it.`);
  $('nsName').value = ''; $('nsNotes').value = '';
};

vsarStartClock();
nsRenderEffects(); loadScenarios(); connect(); vsarInitAuthBadge('Instructor');
