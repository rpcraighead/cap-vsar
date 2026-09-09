// Mission base view. No instructor controls, and no beacon position unless the
// instructor has revealed it for debrief.
const $ = id => document.getElementById(id);
const map = L.map('map').setView([33.15, -117.18], 10);
capvsarCharts(map, {view: 'base'});

let state = {}, acLayers = {}, trackLines = {}, beaconMarker = null,
    alertCircle = null, alertMarker = null;
let sortieId = null;
const bearingLayer = L.layerGroup().addTo(map);
const bearingLog = [], msgLog = [];
let centred = false;

const planeIcon = c => L.divIcon({className:'', iconSize:[26,26], html:
  `<svg width="26" height="26" viewBox="0 0 24 24" style="transform:rotate(${c}deg)">
     <path d="M12 2 L15 11 L22 13 L22 15 L13.5 14 L13 20 L16 22 L16 23 L12 22 L8 23 L8 22 L11 20 L10.5 14 L2 15 L2 13 L9 11 Z"
       fill="#2e5496" stroke="#1f3864" stroke-width="0.8"/></svg>`});

const fmtDur = s => `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;

function connect() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen  = () => { $('status').textContent = 'live'; $('status').className = 'status online'; };
  ws.onclose = () => { $('status').textContent = 'reconnecting'; $('status').className = 'status offline';
                       setTimeout(connect, 2000); };
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.type === 'state')   { state = m; render(); }
    if (m.type === 'bearing') { addBearing(m); }
    if (m.type === 'message') { addMessage(m); }
  };
}

function clearSortieLayers() {
  // Everything drawn here belongs to one sortie. Base staff plotting bearings
  // over the previous exercise's search area is worse than an empty map, and
  // the alert circle used to be created once and kept forever.
  for (const layer of [alertCircle, alertMarker, beaconMarker]) if (layer) map.removeLayer(layer);
  alertCircle = alertMarker = beaconMarker = null;
  Object.values(acLayers).forEach(l => map.removeLayer(l));
  Object.values(trackLines).forEach(l => map.removeLayer(l));
  acLayers = {}; trackLines = {};
  bearingLayer.clearLayers();
  bearingLog.length = 0;
  $('bearings').textContent = 'no bearings logged';
  centred = false;
}

function render() {
  const s = state.sortie, sc = state.scenario;

  // A different sortie means a different search. Reset before drawing anything.
  const id = s ? s.id : null;
  if (id !== sortieId) { clearSortieLayers(); sortieId = id; }

  // ---- alert intake: how the search opens
  if (sc) {
    const revealed = s && s.revealed;
    $('alertBox').innerHTML =
      `<b>${sc.alert_kind || 'Tasking'}</b>
       <div style="margin-top:5px">${sc.alert_text || sc.notes || ''}</div>
       ${sc.alert_radius_nm ? `<div class="df" style="margin-top:6px">search area radius ${sc.alert_radius_nm} nm</div>` : ''}
       ${revealed ? '<div class="df no" style="margin-top:6px">DEBRIEF - beacon truth shown on map</div>' : ''}`;
    if (sc.alert_lat != null && !alertCircle) {
      alertCircle = L.circle([sc.alert_lat, sc.alert_lon],
        {radius: (sc.alert_radius_nm || 5) * 1852, color:'#ed7d31', weight:2,
         dashArray:'8,6', fillColor:'#ed7d31', fillOpacity:.06}).addTo(map);
      alertMarker = L.marker([sc.alert_lat, sc.alert_lon], {icon: L.divIcon({className:'', iconSize:[14,14],
        html:'<div style="width:12px;height:12px;border:2px solid #ed7d31;border-radius:50%"></div>'})})
        .addTo(map).bindTooltip('reported area', {direction:'right'});
      if (!centred) { map.fitBounds(alertCircle.getBounds().pad(0.2)); centred = true; }
    }
  } else {
    $('alertBox').textContent = 'waiting for a sortie to open';
  }

  // ---- status board
  const list = state.aircraft || [];
  $('board').innerHTML = list.length ? list.map(a => {
    const age = state.server_time - a.t;
    const airborne = s ? fmtDur(state.server_time - s.started) : '--:--';
    return `<div class="ac"><b>${a.callsign}</b>
      <span class="tag">${age < 10 ? 'reporting' : Math.round(age) + 's stale'}</span>
      <div class="df">${a.alt_ft.toFixed(0)} ft &middot; hdg ${a.hdg_true.toFixed(0)}&deg;
        &middot; ${a.lat.toFixed(4)}, ${a.lon.toFixed(4)}</div>
      <div class="df">airborne ${airborne}</div></div>`;
  }).join('') : 'no aircraft';

  // ---- aircraft on map
  const seen = new Set();
  list.forEach(a => {
    seen.add(a.callsign);
    const ll = [a.lat, a.lon];
    if (!acLayers[a.callsign]) {
      acLayers[a.callsign] = L.marker(ll, {icon: planeIcon(a.hdg_true)}).addTo(map)
        .bindTooltip(a.callsign, {permanent:true, direction:'top', offset:[0,-8]});
      // An aircraft that went quiet for 30 s and came back keeps its existing
      // track: replacing the polyline orphaned the old one on the map forever.
      if (trackLines[a.callsign]) trackLines[a.callsign].addLatLng(ll);
      else trackLines[a.callsign] = L.polyline([ll], {color:'#2e5496', weight:2, opacity:.6}).addTo(map);
    } else {
      acLayers[a.callsign].setLatLng(ll).setIcon(planeIcon(a.hdg_true));
      trackLines[a.callsign].addLatLng(ll);
    }
    if (!centred) { map.setView(ll, 11); centred = true; }
  });
  Object.keys(acLayers).forEach(k => {
    // Marker goes when the aircraft stops reporting; the track it already flew
    // stays on the map, because that is history base staff still need.
    if (!seen.has(k)) { map.removeLayer(acLayers[k]); delete acLayers[k]; }
  });

  // ---- beacon appears only after the instructor reveals it
  if (sc && sc.beacon_lat != null && !beaconMarker) {
    beaconMarker = L.circleMarker([sc.beacon_lat, sc.beacon_lon],
      {radius:9, color:'#c00000', weight:3, fillColor:'#c00000', fillOpacity:.35})
      .addTo(map).bindTooltip('BEACON (actual)', {permanent:true, direction:'right'});
  } else if ((!sc || sc.beacon_lat == null) && beaconMarker) {
    map.removeLayer(beaconMarker); beaconMarker = null;
  }
}

function addBearing(m) {
  bearingLog.unshift(m);
  const R = 40 / 60;
  const brg = m.bearing_true * Math.PI / 180;
  const lat2 = m.lat + R * Math.cos(brg);
  const lon2 = m.lon + R * Math.sin(brg) / Math.cos(m.lat * Math.PI / 180);
  L.polyline([[m.lat, m.lon], [lat2, lon2]],
    {color:'#c00000', weight:2, dashArray:'6,5', opacity:.8}).addTo(bearingLayer);
  $('bearings').innerHTML = bearingLog.map(b =>
    `<div class="brg">${b.callsign} &rarr; ${b.bearing_true.toFixed(0)}&deg;T${b.note ? ' &middot; ' + b.note : ''}</div>`
  ).join('');
}

function addMessage(m) {
  msgLog.unshift(m);
  $('messages').innerHTML = msgLog.map(x => {
    const t = new Date(x.t * 1000).toUTCString().slice(17, 22);
    return `<div class="brg"><b>${t}Z ${x.sender}</b> &rarr; ${x.recipient}<br>${x.body}</div>`;
  }).join('');
}

$('brgAdd').onclick = async () => {
  const cs = $('brgCallsign').value.trim(), v = parseFloat($('brgValue').value);
  if (!cs || isNaN(v)) return;
  const r = await vsarFetch('/api/bearings', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({callsign: cs, bearing_true: v, note: $('brgNote').value.trim()})});
  if (r.ok) { $('brgValue').value = ''; $('brgNote').value = ''; }
  else { alert('That callsign is not reporting a position yet.'); }
};
$('brgValue').addEventListener('keydown', e => { if (e.key === 'Enter') $('brgAdd').click(); });

$('msgSend').onclick = async () => {
  const body = $('msgBody').value.trim();
  if (!body) return;
  const r = await vsarFetch('/api/messages', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({recipient: $('msgTo').value.trim() || 'ALL', body})});
  if (r.ok) $('msgBody').value = '';
};
$('msgBody').addEventListener('keydown', e => { if (e.key === 'Enter') $('msgSend').click(); });

setInterval(() => $('clock').textContent = new Date().toUTCString().slice(17, 25) + 'Z', 1000);
fetch('/api/messages').then(r => r.json()).then(ms => ms.forEach(addMessage));
connect();
