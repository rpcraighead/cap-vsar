// Shared by the instructor (app.js) and mission base (base.js) views: one copy
// of the great-circle geometry, so the instructor's bearing ray and the base's
// bearing ray are the same line. Loaded with a plain <script> before either.
// Keep the BEGIN/END markers: tests/test_geodesy.py runs this block under Node.
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
