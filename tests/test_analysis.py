"""
Debrief scoring dashboard: /api/sorties/{id}/analysis and the page that draws it
(docs/UX_REVIEW_2026-10-11.md 3.4 and 4.5).

Three layers:

  * the maths in routers/analysis.py on synthetic positions placed with
    app/geo.py, so every expected error is known exactly;
  * the endpoint, including the truth boundary: every number it returns that
    is derived from the beacon is beacon truth in another form (an error plus
    the reported bearing is the true bearing), so it follows /track's rule -
    nothing before reveal, nothing for a non-instructor while the same beacon
    is being flown;
  * the static files: the page is on the shell and the tokens, and viz.js /
    debrief.js behave under Node with a small DOM that can also print the SVG.

    python3 -m pytest tests/test_analysis.py -q
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from test_console import (BASE, BEACON, INSTRUCTOR, PLUGIN, build_app,  # noqa: E402
                          leaks, route_paths, run_sortie)

ROOT = HERE.parent
STATIC = ROOT / "services" / "exercise" / "app" / "static"
NODE = shutil.which("node") or shutil.which("nodejs")

# Fields of an aircraft entry that are derived from the beacon position.
TRUTH_DERIVED = ("df_error", "df_error_stats", "df_invalid", "bearing_error",
                 "bearing_error_stats", "cpa", "first_good_cut", "track")


def analysis_module():
    return sys.modules["app.routers.analysis"]


def geo_module():
    return sys.modules["app.geo"]


def from_beacon(bearing, nm):
    """A point `nm` from the beacon on `bearing` (so the truth back is bearing+180)."""
    return geo_module().move(BEACON["lat"], BEACON["lon"], bearing, nm)


# ------------------------------------------------------------------ the maths
class ErrorMaths(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.main, _, cls.db = build_app()
        cls.an = analysis_module()
        cls.beacon = {"lat": BEACON["lat"], "lon": BEACON["lon"]}

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.db)

    def err(self, reading, bearing_from_beacon, nm=5.0):
        lat, lon = from_beacon(bearing_from_beacon, nm)
        return self.an.signed_error(reading, lat, lon, self.beacon)

    def test_due_north_reading_180_is_no_error(self):
        self.assertAlmostEqual(self.err(180.0, 0.0), 0.0, places=6)

    def test_due_north_reading_170_is_minus_ten(self):
        self.assertAlmostEqual(self.err(170.0, 0.0), -10.0, places=6)
        self.assertAlmostEqual(self.err(190.0, 0.0), 10.0, places=6)

    def test_the_error_wraps_through_north(self):
        # Due south of the beacon the truth is 000: 350 is ten degrees left of
        # it, not 350 degrees right.
        self.assertAlmostEqual(self.err(350.0, 180.0), -10.0, places=6)
        self.assertAlmostEqual(self.err(10.0, 180.0), 10.0, places=6)
        self.assertAlmostEqual(abs(self.err(0.0, 0.0)), 180.0, places=6)

    def test_df_series_reads_df_bearing_true_and_skips_invalid_samples(self):
        north = from_beacon(0.0, 5.0)
        rows = [
            {"t": 1.0, "lat": north[0], "lon": north[1], "df": {"valid": True, "bearing_true": 180.0}},
            {"t": 2.0, "lat": north[0], "lon": north[1], "df": {"valid": True, "bearing_true": 170.0,
                                                                "in_cone": True}},
            {"t": 3.0, "lat": north[0], "lon": north[1], "df": {"valid": False, "bearing_true": 0.0}},
            {"t": 4.0, "lat": north[0], "lon": north[1], "df": {"valid": True}},
            {"t": 5.0, "lat": north[0], "lon": north[1]},
            {"t": 6.0, "lat": north[0], "lon": north[1], "df": {"bearing_true": True}},
        ]
        series, skipped = self.an.df_error_series(rows, self.beacon)
        self.assertEqual([p["t"] for p in series], [1.0, 2.0])
        self.assertAlmostEqual(series[0]["error"], 0.0, places=2)
        self.assertAlmostEqual(series[1]["error"], -10.0, places=2)
        self.assertTrue(series[1]["in_cone"])
        self.assertNotIn("in_cone", series[0])
        self.assertEqual(skipped, 1)

    def test_logged_bearings_use_where_they_were_taken(self):
        east = from_beacon(90.0, 4.0)
        rows = [{"t": 9.0, "lat": east[0], "lon": east[1], "bearing_true": 260.0, "note": "weak"}]
        (b,) = self.an.bearing_error_series(rows, self.beacon)
        truth = geo_module().bearing_true(east[0], east[1], BEACON["lat"], BEACON["lon"])
        self.assertAlmostEqual(b["error"], 260.0 - truth, places=2)
        self.assertEqual(b["note"], "weak")

    def test_closest_point_of_approach(self):
        pts = [dict(zip(("lat", "lon"), from_beacon(0.0, nm)), t=t)
               for t, nm in ((10.0, 5.0), (20.0, 1.5), (30.0, 2.5), (40.0, 1.5))]
        cpa = self.an.closest_approach(pts, self.beacon)
        self.assertAlmostEqual(cpa["nm"], 1.5, places=2)
        self.assertEqual(cpa["t"], 20.0)          # the first time it got that close
        self.assertIsNone(self.an.closest_approach([], self.beacon))

    def test_first_good_cut_is_the_earliest_within_ten_degrees(self):
        errors = [{"t": 40.0, "error": 2.0}, {"t": 10.0, "error": 25.0},
                  {"t": 30.0, "error": -10.0}, {"t": 20.0, "error": -12.0}]
        self.assertEqual(self.an.first_good_cut(errors), {"t": 30.0, "error": -10.0})
        self.assertIsNone(self.an.first_good_cut([{"t": 1.0, "error": 10.5}]))
        self.assertIsNone(self.an.first_good_cut([]))

    def test_track_efficiency_keeps_the_debrief_definition(self):
        # Straight in from 5 nm north to 1 nm north: flown 4, direct 5.
        pts = [dict(zip(("lat", "lon"), from_beacon(0.0, nm)), t=t)
               for t, nm in ((0.0, 5.0), (1.0, 3.0), (2.0, 1.0))]
        tr = self.an.track_efficiency(pts, self.beacon)
        self.assertAlmostEqual(tr["flown_nm"], 4.0, places=2)
        self.assertAlmostEqual(tr["direct_nm"], 5.0, places=2)
        self.assertAlmostEqual(tr["efficiency_pct"], 125.0, places=0)
        # One fix: debrief.js floored the distance flown at 0.01 nm, and so does this.
        (one,) = pts[:1]
        self.assertAlmostEqual(self.an.track_efficiency([one], self.beacon)["efficiency_pct"],
                               5.0 / 0.01 * 100, delta=1.0)

    def test_downsampling_keeps_the_extremes(self):
        series = [{"t": float(i), "error": 0.0} for i in range(5000)]
        series[1234]["error"] = 40.0          # a multipath swing
        series[4321]["error"] = -35.0
        out = self.an.downsample(series, 400)
        self.assertLessEqual(len(out), 420)
        self.assertIn(40.0, [p["error"] for p in out])
        self.assertIn(-35.0, [p["error"] for p in out])
        self.assertEqual([p["t"] for p in out], sorted(p["t"] for p in out))
        short = series[:10]
        self.assertIs(self.an.downsample(short, 400), short)      # short series pass through

    def test_slots_follow_the_roster_not_the_rank(self):
        roster = ["CAP 423", "CAP 424", "CAP 425"]
        got = dict(self.an.assign_slots({"CAP 425", "ZULU 9", "ALPHA 1"}, roster))
        self.assertEqual(got["CAP 425"], 3)       # keeps its roster slot when 423/424 did not fly
        self.assertEqual(got["ALPHA 1"], 1)       # unknown callsigns take the free slots, A-Z
        self.assertEqual(got["ZULU 9"], 2)
        five = dict(self.an.assign_slots({"A1", "A2", "A3", "A4", "A5"}, []))
        self.assertEqual(sorted(v for v in five.values() if v), [1, 2, 3, 4])
        self.assertIsNone(five["A5"])             # no generated fifth hue
        order = [cs for cs, _ in self.an.assign_slots({"CAP 425", "ALPHA 1"}, roster)]
        self.assertEqual(order, ["ALPHA 1", "CAP 425"])   # displayed in slot order


# ------------------------------------------------------------------ endpoint
class AnalysisEndpoint(unittest.TestCase):

    def setUp(self):
        self.main, self.client, self.db = build_app(
            instructor=INSTRUCTOR, base=BASE, plugin=PLUGIN)
        self.instr = {"X-CAPVSAR-Token": INSTRUCTOR}
        self.base = {"X-CAPVSAR-Token": BASE}
        self.plug = {"X-CAPVSAR-Token": PLUGIN}

    def tearDown(self):
        os.unlink(self.db)

    def report(self, callsign, bearing_from_beacon, nm, df_bearing, **df):
        lat, lon = from_beacon(bearing_from_beacon, nm)
        r = self.client.post("/api/positions", headers=self.plug, json={
            "callsign": callsign, "lat": lat, "lon": lon, "alt_ft": 5500.0, "hdg_true": 180.0,
            "df": {"valid": True, "bearing_true": df_bearing, "bearing_rel": 0.0,
                   "signal": 0.5, "distance_nm": nm, **df}})
        self.assertEqual(r.status_code, 200, r.text)

    def log(self, callsign, bearing, note=""):
        r = self.client.post("/api/bearings", headers=self.base,
                             json={"callsign": callsign, "bearing_true": bearing, "note": note})
        self.assertEqual(r.status_code, 200, r.text)

    def fly(self, reveal=False):
        """CAP 1 runs in from the north, CAP 2 sits to the east; base logs three cuts."""
        sid, oid = run_sortie(self.main, self.client, headers=self.instr)
        self.report("CAP 1", 0.0, 5.0, 180.0)          # needle on the truth
        self.log("CAP 1", 200.0)                       # +20: not a good cut
        self.report("CAP 1", 0.0, 3.0, 170.0)          # needle 10 left
        self.log("CAP 1", 185.0, note="steady")        # +5: the first good cut
        self.report("CAP 2", 90.0, 4.0, 300.0, valid=False)   # no signal: skipped
        self.report("CAP 2", 90.0, 4.0, 270.0)
        r = self.client.post("/api/messages", headers=self.base,
                             json={"recipient": "CAP 1", "body": "orbit the cut"})
        self.assertEqual(r.status_code, 200, r.text)
        if reveal:
            self.assertEqual(self.client.post("/api/sorties/reveal", headers=self.instr).status_code, 200)
        return sid, oid

    def get(self, oid, headers):
        r = self.client.get(f"/api/sorties/{oid}/analysis", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def by_cs(self, body):
        return {a["callsign"]: a for a in body["aircraft"]}

    def test_the_route_is_registered(self):
        self.assertIn("/api/sorties/{oid}/analysis", route_paths(self.main.app))

    def test_reads_need_a_credential(self):
        _, oid = self.fly()
        self.assertIn(self.client.get(f"/api/sorties/{oid}/analysis").status_code, (401, 403))
        self.assertEqual(self.client.get("/api/sorties/nope/analysis", headers=self.base).status_code, 404)

    def test_nothing_truth_derived_before_reveal(self):
        _, oid = self.fly()
        for who in (self.base, self.instr):     # not even the instructor: /track's rule
            body = self.get(oid, who)
            self.assertFalse(body["revealed"])
            self.assertEqual(leaks(body), [])
            self.assertNotIn("beacon", body)
            ac = self.by_cs(body)
            self.assertEqual(set(ac), {"CAP 1", "CAP 2"})
            for a in ac.values():
                for k in TRUTH_DERIVED:
                    self.assertIsNone(a[k], f"{a['callsign']}.{k} before reveal")
            # What is not truth still comes back: the counts and the distance flown.
            self.assertEqual(ac["CAP 1"]["counts"], {"positions": 2, "bearings": 2, "messages": 1})
            self.assertAlmostEqual(ac["CAP 1"]["flown_nm"], 2.0, places=1)
            self.assertNotIn("bearing_true", json.dumps(body))

    def test_scores_after_reveal(self):
        _, oid = self.fly(reveal=True)
        body = self.get(oid, self.base)
        self.assertTrue(body["revealed"])
        self.assertFalse(body["withheld"])
        self.assertEqual(body["good_cut_deg"], 10.0)
        self.assertEqual(body["counts"], {"positions": 4, "bearings": 2, "messages": 1})
        a = self.by_cs(body)["CAP 1"]
        self.assertEqual([round(p["error"], 1) for p in a["df_error"]], [0.0, -10.0])
        self.assertEqual([round(b["error"], 1) for b in a["bearing_error"]], [20.0, 5.0])
        self.assertEqual(a["bearing_error"][1]["note"], "steady")
        self.assertAlmostEqual(a["first_good_cut"]["error"], 5.0, places=1)
        self.assertEqual(a["first_good_cut"]["t"], a["bearing_error"][1]["t"])
        self.assertAlmostEqual(a["cpa"]["nm"], 3.0, places=2)
        self.assertEqual(a["cpa"]["t"], a["df_error"][1]["t"])
        self.assertAlmostEqual(a["track"]["efficiency_pct"], 250.0, delta=0.5)
        self.assertEqual(a["df_error_stats"]["n"], 2)
        self.assertAlmostEqual(a["df_error_stats"]["mean_abs"], 5.0, places=1)
        self.assertEqual(a["bearing_error_stats"]["good"], 1)
        b = self.by_cs(body)["CAP 2"]
        self.assertEqual(b["df_invalid"], 1)
        self.assertEqual(len(b["df_error"]), 1)
        self.assertLess(abs(b["df_error"][0]["error"]), 0.2)   # 270 from due east, near enough
        self.assertIsNone(b["first_good_cut"])
        self.assertEqual(b["counts"]["messages"], 0)
        self.assertEqual([x["slot"] for x in body["aircraft"]], [1, 2])

    def test_withheld_from_non_instructors_while_the_same_beacon_flies(self):
        sid, old = self.fly(reveal=True)
        self.client.post("/api/sorties/stop", headers=self.instr)
        r = self.client.post("/api/sorties", json={"scenario_id": sid}, headers=self.instr)
        self.assertEqual(r.status_code, 200, r.text)
        body = self.get(old, self.base)
        self.assertTrue(body["withheld"])
        self.assertFalse(body["revealed"])
        self.assertEqual(leaks(body), [])
        for a in body["aircraft"]:
            for k in TRUTH_DERIVED:
                self.assertIsNone(a[k], f"{a['callsign']}.{k} leaked while withheld")
        # The instructor still can, and once the live sortie is revealed so can base.
        mine = self.by_cs(self.get(old, self.instr))
        self.assertEqual(len(mine["CAP 1"]["df_error"]), 2)
        self.client.post("/api/sorties/reveal", headers=self.instr)
        later = self.by_cs(self.get(old, self.base))
        self.assertEqual(len(later["CAP 1"]["bearing_error"]), 2)

    def test_the_sorties_effects_are_listed(self):
        _, oid = self.fly(reveal=True)
        r = self.client.post("/api/sorties/effects", headers=self.instr,
                             json={"multipath": True, "multipath_offset_deg": 35.0,
                                   "cone_of_confusion": False})
        self.assertEqual(r.status_code, 200, r.text)
        body = self.get(oid, self.base)
        self.assertTrue(body["effects"]["multipath"])
        labels = [e["label"] for e in body["effects_active"]]
        self.assertIn("Multipath (35° offset)", labels)
        self.assertNotIn("Cone of confusion", labels)
        self.assertIn("Radio horizon", labels)


# -------------------------------------------------------------- static files
def src(name):
    return (STATIC / name).read_text()


class DashboardFiles(unittest.TestCase):

    def test_the_page_is_on_the_shell_and_the_tokens(self):
        html = src("debrief.html")
        self.assertIn('<header id="shell"></header>', html)
        for sheet in ("/static/tokens.css", "/static/vendor/fonts/fonts.css",
                      "/static/shell.css", "/static/debrief.css"):
            self.assertIn(f'href="{sheet}"', html)
        self.assertNotIn("style.css", html)        # the old visual system
        self.assertIn('id="sortieSel"', html.split("<main")[0])   # the picker stays in the sidebar
        order = [html.index(f"/static/{f}") for f in ("charts.js", "shell.js", "viz.js", "debrief.js")]
        self.assertEqual(order, sorted(order))
        self.assertEqual(re.findall(r'(?:src|href)="(https?://[^"]+)"', html), [])

    def test_no_literal_colours(self):
        for name in ("debrief.css", "viz.js", "debrief.js"):
            with self.subTest(name=name):
                text = src(name)
                self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", text), [])
                self.assertIsNone(re.search(r"\brgba?\(|\bhsla?\(", text))

    def test_aircraft_and_truth_wear_their_tokens(self):
        css = src("debrief.css")
        for n in (1, 2, 3, 4):
            self.assertIn(f"var(--ac-{n})", css)
        self.assertNotIn("--ac-5", css + src("viz.js"))
        self.assertIn(".viz-zero { stroke: var(--truth)", css)
        self.assertIn("tok('--truth')", src("debrief.js"))

    def test_server_strings_never_become_markup(self):
        viz = src("viz.js")
        self.assertNotRegex(viz, r"innerHTML|outerHTML|insertAdjacentHTML")
        self.assertNotRegex(viz, r"\bfetch\(|https?://(?!www\.w3\.org/2000/svg)")
        dbf = src("debrief.js")
        # One HTML sink is left: the sortie picker's <option> list, built with esc().
        self.assertEqual(len(re.findall(r"\.innerHTML\s*=", dbf)), 1)
        self.assertIn("$('sortieSel').innerHTML", dbf)


# ---------------------------------------------------------- the JS, under Node
# A small DOM that keeps attributes and children, so the SVG viz.js builds can
# be inspected (and printed: `serialize(node)`). Leaflet is a recording stub.
MINI_DOM = r"""
const vm = require('vm'), fs = require('fs');
const STATIC = process.argv[1], files = JSON.parse(process.argv[2]), scenario = process.argv[3];
const rec = {fetches: [], polylines: [], circles: []};
let routes = () => ({ok: false, status: 503, json: async () => ({})});
class El {
  constructor(tag, ns) { this.tagName = tag; this.ns = ns || null; this.attrs = {}; this.children = [];
    this.style = {}; this.listeners = {}; this._text = ''; this.hidden = false; this.className = '';
    this.dataset = {}; this.value = ''; this.id = ''; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  append(...ns) { for (const n of ns) this.children.push(typeof n === 'string' ? new Text(n) : n); }
  appendChild(n) { this.append(n); return n; }
  prepend(...ns) { this.children.unshift(...ns); }
  replaceChildren(...ns) { this.children = []; this._text = ''; this.append(...ns); }
  get firstChild() { return this.children[0] || null; }
  set textContent(v) { this.children = []; this._text = String(v); }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  set innerHTML(v) { this.children = []; this._text = ''; this.html = String(v); }
  addEventListener(k, fn) { (this.listeners[k] ||= []).push(fn); }
  fire(k, ev) { (this.listeners[k] || []).forEach(f => f(ev || {preventDefault() {}})); }
  get classList() { const s = this; return {add: c => { s.className += ' ' + c; }, remove() {}, toggle() {},
    contains: c => s.className.split(/\s+/).includes(c)}; }
  getBoundingClientRect() { return {left: 0, top: 0, width: Number(this.attrs.width) || 900, height: 260}; }
  get clientWidth() { return 900; }
  focus() {}
  get selectedOptions() { return [{text: '2026-10-11 10:00Z — Dashboard test (6 pts)'}]; }
  cls() { return (this.attrs.class || this.className || '').trim(); }
  all(pred, out = []) { for (const c of this.children) if (c instanceof El) { if (pred(c)) out.push(c); c.all(pred, out); } return out; }
  byClass(c) { return this.all(n => n.cls().split(/\s+/).includes(c)); }
}
class Text { constructor(t) { this.data = String(t); } get textContent() { return this.data; } }
const escText = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
function serialize(n) {
  if (n instanceof Text) return escText(n.data);
  const a = Object.entries(n.attrs).map(([k, v]) => ` ${k}="${escText(v).replace(/"/g, '&quot;')}"`).join('');
  const style = Object.entries(n.style).filter(([, v]) => v !== '' && v != null).map(([k, v]) => `${k}:${v}`).join(';');
  const cls = n.className && !n.attrs.class ? ` class="${n.className.trim()}"` : '';
  return `<${n.tagName}${a}${cls}${style ? ` style="${style}"` : ''}${n.hidden ? ' hidden' : ''}>` +
         escText(n._text) + n.children.map(serialize).join('') + `</${n.tagName}>`;
}
const els = {};
const document = {
  getElementById: id => els[id] || (els[id] = Object.assign(new El('div'), {id})),
  createElement: t => new El(t), createElementNS: (ns, t) => new El(t, ns),
  createTextNode: t => new Text(t), activeElement: null, documentElement: new El('html'),
};
const chain = new Proxy(function () {}, {
  get: (t, k) => k === 'then' ? undefined : k === 'getLatLng' ? () => ({lat: 0, lng: 0}) : chain,
  apply: () => chain,
});
const L = new Proxy({}, {get: (t, k) => {
  if (k === 'polyline') return (pts, opts) => { rec.polylines.push({n: pts.length, color: opts.color}); return chain; };
  if (k === 'circleMarker') return (ll, opts) => { rec.circles.push(opts.color); return chain; };
  return () => chain;
}});
const ctx = {document, L, console, JSON, Math, Date, Promise, Set, Map, Object, Array, Number, String,
  parseFloat, isNaN, isFinite, encodeURIComponent, URL, URLSearchParams,
  location: {pathname: '/debrief', search: '', set href(v) {}, get href() { return '/debrief'; }},
  getComputedStyle: () => ({getPropertyValue: n => 'tok(' + n + ')'}),
  fetch: async url => { rec.fetches.push(String(url)); return routes(String(url)); },
  setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  localStorage: {getItem: () => null, setItem() {}}, alert() {}};
ctx.window = ctx; ctx.globalThis = ctx;
vm.createContext(ctx);
for (const f of files) vm.runInContext(fs.readFileSync(STATIC + '/' + f, 'utf8'), ctx, {filename: f});
ctx.api = {rec, els, serialize, El, setRoutes: r => { routes = r; }, run: s => vm.runInContext(s, ctx),
           flush: () => new Promise(r => setImmediate(r))};
(async () => {
  const out = await vm.runInContext('(async () => {' + scenario + '\n})()', ctx);
  console.log(JSON.stringify(out === undefined ? null : out));
})().catch(e => { console.error(e && e.stack || String(e)); process.exit(1); });
"""


def node_run(files, scenario):
    if NODE is None:
        raise unittest.SkipTest("node is not installed")
    proc = subprocess.run([NODE, "-e", MINI_DOM, str(STATIC), json.dumps(files), scenario],
                          capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return json.loads(proc.stdout)


# Two aircraft over ten minutes: CAP 423 converges on the truth with a
# multipath excursion and a wrap through +/-180; CAP 424 sits right of it and
# stops reporting for two minutes. Times are epoch seconds like the server's.
CHART_DATA = r"""
  const T0 = 1760000000;
  const a = [], b = [];
  for (let s = 0; s <= 600; s += 5) {
    let v = 30 * Math.exp(-s / 200) * Math.cos(s / 40);
    if (s >= 300 && s < 340) v = 38;                      // multipath swing
    if (s === 420) v = 170; if (s === 425) v = -175;      // through the tail: a wrap, not a 345 degree swing
    a.push({t: T0 + s, v});
    if (s < 200 || s > 320) b.push({t: T0 + s, v: 6 + 3 * Math.sin(s / 30)});
  }
  const spec = {x0: T0, x1: T0 + 600, fmtT: t => fmtDur(t - T0), band: 10, onSeek: t => { api.sought = t; },
    note: 'Effects on at the end of the sortie: Multipath (40° offset).',
    series: [{label: 'CAP 423', slot: 1, line: a, dots: [{t: T0 + 120, v: 14, detail: '187°T'}, {t: T0 + 500, v: -3, detail: '<b>x</b>'}]},
             {label: 'CAP 424', slot: 2, line: b, dots: []}]};
"""

TRACK_AND_SCORES = r"""
  const T0 = 1760000000;
  const pos = (cs, t, lat) => ({callsign: cs, t: T0 + t, lat, lon: -117, hdg_true: 180});
  const track = {positions: [pos('CAP 425', 0, 34.3), pos('ALPHA 1', 0, 34.4), pos('CAP 425', 60, 34.28),
                             pos('ALPHA 1', 60, 34.38), pos('CAP 425', 120, 34.26), pos('ALPHA 1', 120, 34.36)],
                 bearings: [{callsign: 'CAP 425', t: T0 + 50, lat: 34.3, lon: -117, bearing_true: 181, note: '<img src=x onerror=alert(1)>'}],
                 messages: [{t: T0 + 90, sender: 'MRO 1', recipient: 'CAP 425', body: 'orbit'}],
                 revealed: true, withheld: false, beacon: {lat: 34.2345, lon: -116.8765}, next_since: null};
  const ac = (callsign, slot, extra) => Object.assign({callsign, slot, flown_nm: 2.4,
    counts: {positions: 3, bearings: 0, messages: 0}, df_error: [], df_error_stats: null, df_invalid: 0,
    bearing_error: [], bearing_error_stats: null, cpa: {nm: 3.2, t: T0 + 120}, first_good_cut: null,
    track: {flown_nm: 2.4, direct_nm: 5.1, efficiency_pct: 212.5}}, extra || {});
  const scores = {id: 's1', revealed: true, withheld: false, good_cut_deg: 10, t0: T0, t1: T0 + 120,
    effects: {multipath: true}, effects_active: [{key: 'multipath', label: 'Multipath (40° offset)'}],
    counts: {positions: 6, bearings: 1, messages: 1},
    aircraft: [ac('ALPHA 1', 1), ac('CAP 425', 3, {counts: {positions: 3, bearings: 1, messages: 1},
      df_error: [{t: T0, error: 12}, {t: T0 + 60, error: -4, in_cone: true}, {t: T0 + 120, error: 1}],
      df_error_stats: {n: 3, mean_abs: 5.67, max_abs: 12, good: 2},
      bearing_error: [{t: T0 + 50, error: 4.2, bearing_true: 181, note: '<img src=x onerror=alert(1)>'}],
      bearing_error_stats: {n: 1, mean_abs: 4.2, max_abs: 4.2, good: 1},
      cpa: {nm: 0.4, t: T0 + 120}, first_good_cut: {t: T0 + 50, error: 4.2}})]};
  document.getElementById('sortieSel').value = 's1';
  api.setRoutes(url => {
    if (url === '/api/sorties') return {ok: true, status: 200, json: async () => [{id: 's1', started: T0, name: 'Dashboard test', points: 6}]};
    if (url.includes('/track')) return {ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(track))};
    if (url.includes('/analysis')) return {ok: true, status: 200, json: async () => scores};
    return {ok: false, status: 503, json: async () => ({})};
  });
"""


class VizPure(unittest.TestCase):
    """The BEGIN/END VIZ PURE block of viz.js."""

    def run_pure(self, expr):
        text = src("viz.js")
        block = text[text.index("// BEGIN VIZ PURE"):text.index("// END VIZ PURE")]
        return node_run([], block + f"\nreturn {expr};")

    def test_error_axis_is_symmetric_on_navigator_steps(self):
        out = self.run_pure("[vizErrorDomain(7), vizErrorDomain(35), vizErrorDomain(500)]")
        self.assertEqual(out[0], {"max": 10, "ticks": [-10, -5, 0, 5, 10]})
        self.assertEqual(out[1], {"max": 45, "ticks": [-45, -30, -15, 0, 15, 30, 45]})
        self.assertEqual(out[2], {"max": 180, "ticks": [-180, -90, 0, 90, 180]})

    def test_lines_break_at_gaps_and_at_the_wrap(self):
        out = self.run_pure("""vizRuns([{t: 0, v: 1}, {t: 5, v: 2}, {t: 90, v: 3}, {t: 95, v: 179},
                                       {t: 100, v: -179}], 15).map(r => r.length)""")
        self.assertEqual(out, [2, 2, 1])

    def test_direct_labels_keep_their_order_and_spacing(self):
        out = self.run_pure("vizSpread([100, 104, 98, 250], 16, 10, 240)")
        self.assertEqual(sorted(out, key=lambda y: y)[0], out[2])         # 98 stays the top one
        ys = sorted(out)
        self.assertTrue(all(b - a >= 16 - 1e-9 for a, b in zip(ys, ys[1:])), out)
        self.assertLessEqual(max(out), 240)

    def test_nearest_and_signed(self):
        out = self.run_pure("""[vizNearest([{t: 0}, {t: 10}, {t: 20}], 14), vizNearest([], 3),
                                vizSigned(-3), vizSigned(4.25), vizSigned(-0.01), vizClip('CAP 423 LONGNAME', 8)]""")
        self.assertEqual(out, [1, -1, "−3.0°", "+4.3°", "0.0°", "CAP 423…"])


class VizChart(unittest.TestCase):
    """vizErrorChart under the small DOM: the marks the dataviz method asks for."""

    def test_the_chart_has_its_marks_legend_and_table(self):
        out = node_run(["charts.js", "viz.js"], CHART_DATA + r"""
          const host = document.getElementById('host');
          const c = vizErrorChart(host, spec);
          const svg = host.all(n => n.tagName === 'svg')[0];
          const lines1 = svg.byClass('viz-line').filter(n => n.cls().includes('viz-s1'));
          const lines2 = svg.byClass('viz-line').filter(n => n.cls().includes('viz-s2'));
          const zero = svg.byClass('viz-zero')[0], band = svg.byClass('viz-band')[0];
          const legend = host.byClass('viz-legend')[0].children.map(li => li.textContent);
          const labels = svg.byClass('viz-label').map(n => n.textContent);
          const dots = svg.byClass('viz-dot').length;
          // hover: the crosshair snaps to a sample, and the tooltip lists every series
          svg.fire('pointermove', {clientX: 400});
          const tip = host.byClass('viz-tip')[0];
          const tipRows = tip.byClass('viz-tip-row').length;
          const cross = svg.byClass('viz-cross')[0];
          svg.fire('click', {clientX: 400});
          c.setCursor(T0 + 300);
          const replayX = Number(/translate\(([\d.]+)/.exec(svg.byClass('viz-replay')[0].getAttribute('transform'))[1]);
          const notes = host.byClass('viz-note').map(n => n.hidden ? null : n.textContent);
          c.showTable(true);
          const tables = host.byClass('viz-data');
          const head = tables[0].all(n => n.tagName === 'th').map(n => n.textContent);
          const logged = tables[1].all(n => n.tagName === 'td').map(n => n.textContent);
          return {lines1: lines1.length, lines2: lines2.length, zeroY: Number(zero.getAttribute('y1')),
                  bandTop: Number(band.getAttribute('y')), bandH: Number(band.getAttribute('height')),
                  legend, labels, dots, tipRows, tipHidden: tip.hidden, crossShown: cross.style.display === '',
                  sought: api.sought, replayX, notes, plotHidden: host.byClass('viz-plot')[0].hidden, head, logged,
                  aria: svg.getAttribute('aria-label'), tabindex: svg.getAttribute('tabindex'),
                  ticks: svg.byClass('viz-ticks')[0].children.map(n => n.textContent)};
        """)
        # CAP 423: the wrap through 180 splits its line; CAP 424's two-minute silence splits its own.
        self.assertEqual(out["lines1"], 2)
        self.assertEqual(out["lines2"], 2)
        # 260 px tall, 10 top and 28 bottom margins: zero is the middle of 10..232.
        self.assertAlmostEqual(out["zeroY"], 121.0, places=1)
        self.assertGreater(out["bandH"], 0)
        self.assertAlmostEqual(out["bandTop"] + out["bandH"] / 2, out["zeroY"], places=1)
        self.assertEqual(out["legend"], ["CAP 423", "CAP 424", "logged bearing",
                                         "±10° good cut", "true bearing (0°)"])
        self.assertEqual(out["labels"], ["CAP 423", "CAP 424"])
        self.assertEqual(out["dots"], 2)
        self.assertGreaterEqual(out["tipRows"], 2)
        self.assertFalse(out["tipHidden"])
        self.assertTrue(out["crossShown"])
        self.assertIsNotNone(out["sought"])
        self.assertGreater(out["replayX"], 48)
        self.assertTrue(out["plotHidden"])
        self.assertEqual(out["head"], ["Time", "CAP 423", "CAP 424"])
        self.assertIn("<b>x</b>", out["logged"])          # a note stays text, in the table too
        self.assertIn("table view", out["aria"])
        self.assertEqual(out["tabindex"], "0")
        # The scale follows the bulk of the readings: the multipath swing (38) sets
        # it; the two readings through the tail run off it, and the note says so.
        self.assertIn("+45°", out["ticks"])
        self.assertNotIn("+180°", out["ticks"])
        self.assertIn("2 of 219 readings lie beyond ±45°", out["notes"][1])
        self.assertIn("00:00", out["ticks"])

    def test_an_empty_chart_says_why(self):
        out = node_run(["charts.js", "viz.js"], r"""
          const host = document.getElementById('host');
          vizErrorChart(host, {x0: 0, x1: 10, series: [], empty: 'not revealed yet'});
          return {svg: host.all(n => n.tagName === 'svg').length, text: host.textContent};
        """)
        self.assertEqual(out["svg"], 0)
        self.assertIn("not revealed yet", out["text"])


class DebriefPage(unittest.TestCase):
    """charts.js + viz.js + debrief.js driven with a track and its analysis."""

    def test_cards_chart_marks_and_map_follow_the_slots(self):
        out = node_run(["charts.js", "viz.js", "debrief.js"], TRACK_AND_SCORES + r"""
          await loadList(); for (let i = 0; i < 5; i++) await api.flush();
          const cards = api.els.summary.children;
          const marks = api.els.marks.children;
          marks[0].fire('click');
          const sliderAfterMark = Number(api.els.slider.value);
          const svg = api.els.errChart.all(n => n.tagName === 'svg')[0];
          return {order: api.run('order'), cards: cards.map(c => c.className),
                  titles: cards.map(c => c.byClass('ac-head')[0].textContent),
                  tiles: cards[1].byClass('stat-label').map(n => n.textContent),
                  values: cards[1].byClass('stat-value').map(n => n.textContent),
                  notRecorded: cards[0].byClass('stat-value').filter(n => n.textContent === 'not recorded').length,
                  marks: marks.map(m => m.className), markLabel: marks[0].getAttribute('aria-label'),
                  sliderAfterMark, lines: svg.byClass('viz-line').map(n => n.cls()),
                  polylineColours: [...new Set(api.rec.polylines.map(p => p.color))],
                  beacon: api.rec.circles, note: api.els.errChart.byClass('viz-note')[0].textContent,
                  events: api.els.events.textContent, info: api.els.sortieInfo.textContent};
        """)
        self.assertEqual(out["order"], ["ALPHA 1", "CAP 425"])
        self.assertEqual(out["cards"], ["ac-card s1", "ac-card s3"])     # colour follows the slot, not the rank
        self.assertIn("overhead the beacon", out["titles"][1])
        self.assertEqual(out["tiles"], ["Needle error", "Logged bearing error", "Closest approach",
                                        "First good cut", "Track efficiency", "Ops-normal timing",
                                        "Rejected cuts", "Change since last session"])
        self.assertEqual(out["values"][:5], ["5.7°", "4.2°", "0.40 nm", "00:50", "213%"])
        self.assertEqual(out["notRecorded"], 4)          # no DF on ALPHA 1, plus the three unrecorded measures
        self.assertEqual(out["marks"], ["mark brg s3", "mark msg"])
        self.assertIn("CAP 425 bearing 181", out["markLabel"])
        self.assertAlmostEqual(out["sliderAfterMark"], 50 / 120 * 100, places=3)
        self.assertEqual(out["lines"], ["viz-line viz-s3"])
        self.assertEqual(sorted(out["polylineColours"]), ["tok(--ac-1)", "tok(--ac-3)"])
        self.assertEqual(out["beacon"], ["tok(--truth)"])
        self.assertIn("Multipath (40° offset)", out["note"])
        self.assertIn("<img src=x onerror=alert(1)>", out["events"])   # as text, not as an element
        self.assertIn("6 position reports", out["info"])

    def test_before_reveal_the_cards_say_so(self):
        out = node_run(["charts.js", "viz.js", "debrief.js"], TRACK_AND_SCORES + r"""
          scores.revealed = false;
          scores.aircraft.forEach(a => { for (const k of ['df_error', 'df_error_stats', 'bearing_error',
            'bearing_error_stats', 'cpa', 'first_good_cut', 'track']) a[k] = null; });
          track.beacon = null; track.revealed = false;
          await loadList(); for (let i = 0; i < 5; i++) await api.flush();
          return {values: api.els.summary.children[0].byClass('stat-value').map(n => n.textContent),
                  chart: api.els.errChart.textContent};
        """)
        self.assertEqual(out["values"][:5], ["after reveal"] * 5)
        self.assertIn("not revealed", out["chart"])

    def test_withheld_says_withheld(self):
        out = node_run(["charts.js", "viz.js", "debrief.js"], TRACK_AND_SCORES + r"""
          Object.assign(scores, {revealed: false, withheld: true});
          scores.aircraft.forEach(a => { for (const k of ['df_error', 'df_error_stats', 'bearing_error',
            'bearing_error_stats', 'cpa', 'first_good_cut', 'track']) a[k] = null; });
          Object.assign(track, {beacon: null, revealed: false, withheld: true});
          await loadList(); for (let i = 0; i < 5; i++) await api.flush();
          return {values: api.els.summary.children[0].byClass('stat-value').map(n => n.textContent),
                  chart: api.els.errChart.textContent, beacon: api.rec.circles.length};
        """)
        self.assertEqual(out["values"][:5], ["withheld"] * 5)
        self.assertIn("being flown in a live sortie", out["chart"])
        self.assertEqual(out["beacon"], 0)


if __name__ == "__main__":
    unittest.main()
