// Mission base view. No instructor controls, and no beacon position unless the
// instructor has revealed it for debrief.
const $ = id => document.getElementById(id);

// F-6: nothing escapes server strings on the way out, and any LAN client can
// POST message bodies, bearing notes and callsigns. Escape every server value
// interpolated into HTML. Values already passed through toFixed() or
// Math.round() are provably numeric and are left alone.
const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c =>
  ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

const map = L.map('map').setView([33.15, -117.18], 10);
capvsarCharts(map, {view: 'base'});

let state = {}, acLayers = {}, trackLines = {}, beaconMarker = null,
    alertCircle = null, alertMarker = null;
let sortieId = null;
const bearingLayer = L.layerGroup().addTo(map);
const bearingCutLayer = L.layerGroup().addTo(map);
const bearingLog = [], msgLog = [];
const seenBearings = new Set(), seenMessages = new Set();
let lastBearingT = 0, lastMessageT = 0;
let centred = false;

// BEGIN F-8 PURE GEODESY
// Browser deployment boundary: these functions derive from app/geo.py's
// great-circle conventions. tests/test_geodesy.py executes this exact block
// against the same fixture as the Python authority so the two cannot drift.
const BASE_R_NM = 3440.065;
const vCross = (a, b) => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
const vUnit = v => {
  const n = Math.hypot(...v);
  return n > 1e-15 ? v.map(x => x / n) : null;
};
const gcDistanceNm = (lat1, lon1, lat2, lon2) => {
  const r = Math.PI / 180, p1 = lat1 * r, p2 = lat2 * r;
  const dp = (lat2 - lat1) * r, dl = (lon2 - lon1) * r;
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * BASE_R_NM * Math.asin(Math.min(1, Math.sqrt(h)));
};
const bearingDestination = (lat, lon, bearing, distanceNm) => {
  const r = Math.PI / 180, b = bearing * r, d = distanceNm / BASE_R_NM, p = lat * r;
  const p2 = Math.asin(Math.sin(p) * Math.cos(d) + Math.cos(p) * Math.sin(d) * Math.cos(b));
  const l2 = lon * r + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p),
    Math.cos(d) - Math.sin(p) * Math.sin(p2));
  return [p2 / r, ((l2 / r + 540) % 360) - 180];
};
const bearingIntersection = (first, second, maxRangeNm = 40) => {
  const pathPlane = row => {
    const r = Math.PI / 180, lat = Number(row.lat) * r, lon = Number(row.lon) * r;
    const b = ((Number(row.bearing_true) % 360) + 360) % 360 * r;
    const point = [Math.cos(lat) * Math.cos(lon), Math.cos(lat) * Math.sin(lon), Math.sin(lat)];
    const north = [-Math.sin(lat) * Math.cos(lon), -Math.sin(lat) * Math.sin(lon), Math.cos(lat)];
    const east = [-Math.sin(lon), Math.cos(lon), 0];
    const tangent = north.map((x, i) => x * Math.cos(b) + east[i] * Math.sin(b));
    return [point, tangent, vCross(point, tangent)];
  };
  const [p1, d1, n1] = pathPlane(first), [p2, d2, n2] = pathPlane(second);
  const crossing = vUnit(vCross(n1, n2));
  if (!crossing) return null;
  const candidates = [];
  for (const q of [crossing, crossing.map(x => -x)]) {
    if (d1.reduce((s, x, i) => s + x * q[i], 0) <= 1e-12 ||
        d2.reduce((s, x, i) => s + x * q[i], 0) <= 1e-12) continue;
    const point = [Math.asin(Math.max(-1, Math.min(1, q[2]))) * 180 / Math.PI,
      Math.atan2(q[1], q[0]) * 180 / Math.PI];
    const ranges = [gcDistanceNm(first.lat, first.lon, ...point),
      gcDistanceNm(second.lat, second.lon, ...point)];
    if (ranges.every(x => x <= maxRangeNm)) candidates.push([ranges[0] + ranges[1], point]);
  }
  candidates.sort((a, b) => a[0] - b[0]);
  return candidates.length ? candidates[0][1] : null;
};
const bearingCutPolygon = (bearings, maxRangeNm = 40) => {
  const points = [];
  bearings.forEach((first, i) => bearings.slice(i + 1).forEach(second => {
    const point = bearingIntersection(first, second, maxRangeNm);
    if (point && !points.some(old => gcDistanceNm(...point, ...old) < .01)) points.push(point);
  }));
  if (points.length < 3) return points;
  const centreLat = points.reduce((s, p) => s + p[0], 0) / points.length;
  const lonX = points.reduce((s, p) => s + Math.cos(p[1] * Math.PI / 180), 0);
  const lonY = points.reduce((s, p) => s + Math.sin(p[1] * Math.PI / 180), 0);
  const centreLon = Math.atan2(lonY, lonX) * 180 / Math.PI;
  return points.sort((a, b) => {
    const angle = p => {
      const dl = ((p[1] - centreLon + 540) % 360) - 180;
      return Math.atan2(dl * Math.cos(centreLat * Math.PI / 180), p[0] - centreLat);
    };
    return angle(a) - angle(b);
  });
};
const bearingCallsignChoices = aircraft => [...new Set(aircraft
  .map(a => String(a.callsign || '').trim()).filter(Boolean))].sort();
// END F-8 PURE GEODESY

// BEGIN F-8 BEARING UI POLICY
// State ownership:
// - aircraft is console/sortie state supplied by the live state push;
// - selected is the operator's in-progress bearing entry and must survive it;
// - the cut input is derived console state, bounded to the three newest LOBs
//   per aircraft so coarse early bearings age out while a moving aircraft can
//   still create a cut by taking bearings from successive positions.
const MAX_CUT_BEARINGS_PER_CALLSIGN = 3;
function bearingCallsignModel(aircraft, selectedValue) {
  const active = [...new Set(aircraft.map(row => String(row.callsign || '').trim())
    .filter(Boolean))].sort();
  const prior = String(selectedValue || '').trim();
  const stale = Boolean(prior && !active.includes(prior));
  const options = active.map(value => ({value, stale:false}));
  if(stale) options.push({value:prior, stale:true});
  return {options, selected:prior || active[0] || '', stale};
}
function bearingCallsignNeedsRebuild(renderedOptions, model) {
  return JSON.stringify(renderedOptions) !== JSON.stringify(model.options);
}
function recentBearingsForCut(bearings, maximum=MAX_CUT_BEARINGS_PER_CALLSIGN) {
  const counts = new Map(), limit = Math.max(1, Number(maximum) || 1);
  return bearings.filter(row => {
    const callsign = String(row.callsign || '').trim();
    const count = counts.get(callsign) || 0;
    if(count >= limit) return false;
    counts.set(callsign, count + 1);
    return true;
  });
}
// END F-8 BEARING UI POLICY

function ensureBearingCallsignSelect() {
  const old = $('brgCallsign');
  if (!old || old.tagName === 'SELECT') return old;
  const select = document.createElement('select');
  select.id = old.id;
  select.setAttribute('aria-label', 'Reporting aircraft');
  old.replaceWith(select);
  return select;
}

function syncBearingCallsigns(aircraft) {
  const select = ensureBearingCallsignSelect();
  if (!select) return;
  const model = bearingCallsignModel(aircraft, select.value);
  const rendered = [...select.options].filter(option => option.value).map(option => ({
    value:option.value, stale:option.dataset.stale === 'true',
  }));
  // render() runs every second. Leaving an unchanged select alone keeps an
  // open dropdown open and preserves the operator's in-progress choice.
  if(!bearingCallsignNeedsRebuild(rendered, model)) return;
  select.replaceChildren();
  const prompt = document.createElement('option');
  prompt.value = '';
  prompt.textContent = model.options.length ? 'select aircraft' : 'no aircraft reporting';
  prompt.disabled = true;
  select.appendChild(prompt);
  model.options.forEach(({value, stale}) => {
    const option = document.createElement('option');
    option.value = value;
    option.dataset.stale = String(stale);
    option.textContent = stale ? `${value} (not currently reporting)` : value;
    select.appendChild(option);
  });
  select.value = model.selected;
  select.classList.toggle('stale', model.stale);
  select.title = model.stale ? 'Selected aircraft is not currently reporting' : '';
}

function renderBearingCut() {
  bearingCutLayer.clearLayers();
  const cuts = bearingCutPolygon(recentBearingsForCut(bearingLog));
  cuts.forEach(point => L.circleMarker(point,
    {radius:5, color:'#7a1fa2', weight:2, fillColor:'#fff', fillOpacity:.9})
    .addTo(bearingCutLayer).bindTooltip('pairwise bearing cut'));
  if (cuts.length >= 3) L.polygon(cuts,
    {color:'#7a1fa2', weight:2, fillColor:'#b768d4', fillOpacity:.16})
    .addTo(bearingCutLayer).bindTooltip('bearing confidence area');
}

const planeIcon = c => L.divIcon({className:'', iconSize:[26,26], html:
  `<svg width="26" height="26" viewBox="0 0 24 24" style="transform:rotate(${c}deg)">
     <path d="M12 2 L15 11 L22 13 L22 15 L13.5 14 L13 20 L16 22 L16 23 L12 22 L8 23 L8 22 L11 20 L10.5 14 L2 15 L2 13 L9 11 Z"
       fill="#2e5496" stroke="#1f3864" stroke-width="0.8"/></svg>`});

const fmtDur = s => `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;

function connect() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen  = () => { $('status').textContent = 'live'; $('status').className = 'status online'; backfill(); };
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
  bearingCutLayer.clearLayers();
  bearingLog.length = 0;
  msgLog.length = 0;
  seenBearings.clear(); seenMessages.clear();
  lastBearingT = lastMessageT = 0;
  $('bearings').textContent = 'no bearings logged';
  $('messages').textContent = 'no messages';
  centred = false;
}

function render() {
  const s = state.sortie, sc = state.scenario;

  // A different sortie means a different search. Reset before drawing anything.
  const id = s ? s.id : null;
  if (id !== sortieId) { clearSortieLayers(); sortieId = id; if (id) backfill(); }

  // ---- alert intake: how the search opens
  if (sc) {
    const revealed = s && s.revealed;
    $('alertBox').innerHTML =
      `<b>${esc(sc.alert_kind || 'Tasking')}</b>
       <div style="margin-top:5px">${esc(sc.alert_text || sc.notes || '')}</div>
       ${sc.alert_radius_nm ? `<div class="df" style="margin-top:6px">search area radius ${esc(sc.alert_radius_nm)} nm</div>` : ''}
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
    return `<div class="ac"><b>${esc(a.callsign)}</b>
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
        .bindTooltip(esc(a.callsign), {permanent:true, direction:'top', offset:[0,-8]});
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
  syncBearingCallsigns(list);

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
  const key = m.id != null ? `bearing:${m.id}` :
    `bearing:${m.t}:${m.callsign}:${m.bearing_true}`;
  if (seenBearings.has(key)) return;
  seenBearings.add(key); lastBearingT = Math.max(lastBearingT, m.t || 0);
  bearingLog.unshift(m);
  const endpoint = bearingDestination(m.lat, m.lon, m.bearing_true, 40);
  L.polyline([[m.lat, m.lon], endpoint],
    {color:'#c00000', weight:2, dashArray:'6,5', opacity:.8}).addTo(bearingLayer);
  renderBearingCut();
  $('bearings').innerHTML = bearingLog.map(b =>
    `<div class="brg">${esc(b.callsign)} &rarr; ${b.bearing_true.toFixed(0)}&deg;T${b.note ? ' &middot; ' + esc(b.note) : ''}</div>`
  ).join('');
}

function addMessage(m) {
  const key = m.id != null ? `message:${m.id}` :
    `message:${m.t}:${m.sender}:${m.recipient}:${m.body}`;
  if (seenMessages.has(key)) return;
  seenMessages.add(key); lastMessageT = Math.max(lastMessageT, m.t || 0);
  msgLog.unshift(m);
  $('messages').innerHTML = msgLog.map(x => {
    const t = new Date(x.t * 1000).toUTCString().slice(17, 22);
    return `<div class="brg"><b>${t}Z ${esc(x.sender)}</b> &rarr; ${esc(x.recipient)}<br>${esc(x.body)}</div>`;
  }).join('');
}

async function backfill() {
  try {
    const messageSince = Math.max(0, lastMessageT - .001);
    const bearingSince = Math.max(0, lastBearingT - .001);
    const [messages, bearings] = await Promise.all([
      fetch(`/api/messages?since=${messageSince}`).then(r => r.ok ? r.json() : []),
      fetch(`/api/bearings?since=${bearingSince}`).then(r => r.ok ? r.json() : []),
    ]);
    messages.forEach(addMessage); bearings.forEach(addBearing);
  } catch {}
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

async function initAuthBadge() {
  try {
    const res = await fetch('/api/auth/me');
    if (res.ok) {
      const data = await res.json();
      if (data.authenticated && $('userBadge')) {
        const title = data.title || (data.role ? data.role.toUpperCase() : 'Base Staff');
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
connect(); initAuthBadge();
