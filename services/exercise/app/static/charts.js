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

// ---------------------------------------------------------------- role token
// Controlling a sortie, logging a bearing or sending a message needs the role
// token for that seat (CAPVSAR_TOKEN_INSTRUCTOR / _BASE on the console). The
// operator is asked once and it is kept for this browser only.
//
// While no tokens are configured on the server nothing here is exercised: the
// server answers those calls as before, and the operator is never prompted.
const VSAR_TOKEN_KEY = 'vsar-role-token';

function vsarToken() {
  try { return localStorage.getItem(VSAR_TOKEN_KEY) || ''; } catch (e) { return ''; }
}

function vsarSetToken(v) {
  try { v ? localStorage.setItem(VSAR_TOKEN_KEY, v) : localStorage.removeItem(VSAR_TOKEN_KEY); }
  catch (e) { /* private window: token lives for this page only */ }
}

// fetch() plus the token header, retried once if the server rejects it so a
// wrong or stale token can be corrected without a reload.
async function vsarFetch(url, opts = {}, retry = true) {
  const token = vsarToken();
  const headers = Object.assign({}, opts.headers || {});
  if (token) headers['X-CAPVSAR-Token'] = token;
  const r = await fetch(url, Object.assign({}, opts, {headers}));
  if (r.status === 403 && retry) {
    const entered = prompt(token
      ? 'That exercise token was refused. Enter the token for this seat:'
      : 'This action needs the exercise token for this seat:');
    if (entered) {
      vsarSetToken(entered.trim());
      return vsarFetch(url, opts, false);
    }
  }
  return r;
}
