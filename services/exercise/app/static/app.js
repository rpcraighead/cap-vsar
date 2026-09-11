const $ = id => document.getElementById(id);

// F-6: nothing escapes server strings on the way out, and any LAN client can
// POST message bodies, bearing notes and callsigns. Escape every server value
// interpolated into HTML. Values already passed through toFixed() or
// Math.round() are provably numeric and are left alone.
const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c =>
  ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

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
      df = d.valid
        ? `<span class="ok">BRG ${Number(d.bearing_rel).toFixed(0)}&deg; rel</span> &middot; ${esc(d.distance_nm)} nm &middot; sig ${(d.signal*100).toFixed(0)}%${suffix}${d.note ? ` <span class="tag">${esc(d.note)}</span>` : ''}`
        : `<span class="no">${esc(d.note || 'no signal')}</span> &middot; ${esc(d.distance_nm)} nm${suffix}`;
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
  bearingLog.unshift(m);
  const lat1 = m.lat * Math.PI/180;
  const R = 40 / 60; // 40 nm ray, in degrees of latitude
  const brg = m.bearing_true * Math.PI/180;
  const lat2 = m.lat + R * Math.cos(brg);
  const lon2 = m.lon + R * Math.sin(brg) / Math.cos(lat1);
  L.polyline([[m.lat, m.lon], [lat2, lon2]],
    {color:'#c00000', weight:2, dashArray:'6,5', opacity:.8}).addTo(bearingLayer);
  $('bearings').innerHTML = bearingLog.map(b =>
    `<div class="brg">${esc(b.callsign)} &rarr; ${b.bearing_true.toFixed(0)}&deg;T${b.note ? ' &middot; ' + esc(b.note) : ''}</div>`
  ).join('');
}

const fmtDur = s => `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;

// -------------------------------------------------------------------- wiring
async function loadScenarios(selectId) {
  const r = await fetch('/api/scenarios'); const list = await r.json();
  $('scenarioSel').innerHTML = list.map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');
  if (selectId) $('scenarioSel').value = selectId;
  const show = () => {
    const s = list.find(x => x.id === $('scenarioSel').value);
    $('scenarioNotes').textContent = s ? s.notes : '';
  };
  $('scenarioSel').onchange = show; show();
}

$('startBtn').onclick = async () => {
  await vsarFetch('/api/sorties', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({scenario_id: $('scenarioSel').value})});
  bearingLayer.clearLayers(); bearingLog.length = 0;
  Object.values(trackLines).forEach(l => map.removeLayer(l)); trackLines = {};
  $('bearings').textContent = 'no bearings logged';
  $('effects').dataset.for = '';
};
$('stopBtn').onclick   = () => vsarFetch('/api/sorties/stop',   {method:'POST'});
$('revealBtn').onclick = () => vsarFetch('/api/sorties/reveal', {method:'POST'});
$('brgAdd').onclick = async () => {
  const cs = $('brgCallsign').value.trim(), v = parseFloat($('brgValue').value);
  if (!cs || isNaN(v)) return;
  const r = await vsarFetch('/api/bearings', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({callsign: cs, bearing_true: v})});
  if (r.ok) $('brgValue').value = '';
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

async function initAuthBadge() {
  try {
    const res = await fetch('/api/auth/me');
    if (res.ok) {
      const data = await res.json();
      if (data.authenticated && $('userBadge')) {
        const title = data.title || (data.role ? data.role.toUpperCase() : 'Instructor');
        const cs = data.callsign ? ` (${data.callsign})` : '';
        $('userBadge').textContent = `\uD83D\uDC64 ${title}${cs}`;
      }
    }
  } catch (e) {}

  if ($('logoutBtn')) {
    $('logoutBtn').onclick = async () => {
      try {
        await fetch('/api/auth/logout', {method: 'POST'});
      } catch (e) {}
      location.href = '/login';
    };
  }
}

setInterval(() => $('clock').textContent = new Date().toUTCString().slice(17, 25) + 'Z', 1000);
nsRenderEffects(); loadScenarios(); connect(); initAuthBadge();
