// Mission base view. No instructor controls, and no beacon position unless the
// instructor has revealed it for debrief.
const $ = id => document.getElementById(id);

// esc(), planeIcon, fmtDur, the socket, clock and auth badge: charts.js.

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


// The great-circle geometry (bearingDestination, bearingCutPolygon, ...) is in
// geodesy.js, shared with the instructor view.

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

function connect() {
  vsarConnect({
    onOpen: () => backfill(),
    onMessage: m => {
      if (m.type === 'state')   { state = m; render(); }
      if (m.type === 'bearing') { addBearing(m); }
      if (m.type === 'message') { addMessage(m); }
    },
  });
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
  else { await vsarReportFailure(r, 'Bearing not logged'); }
};
$('brgValue').addEventListener('keydown', e => { if (e.key === 'Enter') $('brgAdd').click(); });

$('msgSend').onclick = async () => {
  const body = $('msgBody').value.trim();
  if (!body) return;
  const r = await vsarFetch('/api/messages', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({recipient: $('msgTo').value.trim() || 'ALL', body})});
  if (r.ok) $('msgBody').value = '';
  else await vsarReportFailure(r, 'Message not sent');
};
$('msgBody').addEventListener('keydown', e => { if (e.key === 'Enter') $('msgSend').click(); });

vsarStartClock();
connect(); vsarInitAuthBadge('Base Staff');
