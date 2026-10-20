"""
Exercise console front end: behaviour tests that run the real browser JS under
Node (F2-2 .. F2-12 of docs/PROJECT_REVIEW_2026-10-10.md section 3, and the
improvements made alongside them).

There is no browser here. Each test loads the shipped files into a `vm` context
with a stub DOM, a stub Leaflet, a fake WebSocket, a fake fetch and fake
timers, then drives them the way a page would. Where a function is pure the
file marks it with BEGIN/END comments and the test runs just that block, the
way tests/test_geodesy.py does. A few fixes are only expressible as structure
(which function a timeout handler calls); those are string assertions, each
paired with a check that the assertion fails without the fix.

    python3 -m pytest tests/test_console_frontend.py -q
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "services" / "exercise" / "app" / "static"
NODE = shutil.which("node") or shutil.which("nodejs")


def src(name: str) -> str:
    return (STATIC / name).read_text()


def block(name: str, marker: str) -> str:
    text = src(name)
    start = text.index(f"// BEGIN {marker}")
    end = text.index(f"// END {marker}")
    return text[start:end]


# --------------------------------------------------------------------- harness
# Everything a page needs from its host, as recording stubs. `run()` loads the
# named files in order into one shared global scope (as <script> tags would),
# then evaluates the scenario with that scope's top-level names visible.
HARNESS = r"""
const vm = require('vm');
const fs = require('fs');
const STATIC = process.argv[1];
const files = JSON.parse(process.argv[2]);
const scenario = process.argv[3];

const rec = {fetches: [], sockets: [], timeouts: [], intervals: [], alerts: [],
             polylines: [], nav: []};
let routes = () => ({ok: true, status: 200, json: async () => []});

const chain = new Proxy(function () {}, {
  get: (t, k) => k === 'then' ? undefined : k === 'getLatLng' ? () => ({lat: 0, lng: 0}) : chain,
  apply: () => chain,
});
const L = new Proxy({}, {get: (t, k) => {
  if (k === 'polyline') return (pts, opts) => { rec.polylines.push({pts, opts}); return chain; };
  return () => chain;
}});

const elStore = {};
const els = new Proxy(elStore, {get: (t, k) => t[k] || (t[k] = makeEl(String(k)))});
function makeEl(id) {
  const store = {id, dataset: {}, style: {}, children: [], textContent: '', innerHTML: '',
    value: '', checked: false, options: [], querySelectorAll: () => [], querySelector: () => null, selectedOptions: [{text: ''}],
    classList: {add() {}, remove() {}, toggle() {}, contains: () => false}};
  return new Proxy(store, {
    get(t, k) { if (k in t) return t[k]; if (typeof k === 'symbol') return undefined;
                return (t[k] = function () { return undefined; }); },
    set(t, k, v) { t[k] = v; return true; },
  });
}
const document = {
  getElementById: id => els[id],
  createElement: () => makeEl('created'),
  createTextNode: text => makeEl('text'),   // shell.js and debrief.js build with text nodes
  activeElement: null,
  querySelector: () => null, querySelectorAll: () => [],
  addEventListener() {},
};
class FakeSocket {
  constructor(url) { this.url = url; this.closed = false; rec.sockets.push(this); }
  close() { this.closed = true; }
  send() {}
}
const location = {protocol: 'http:', host: 'console:8700', hostname: 'console',
  pathname: '/base', search: '?tab=1', origin: 'http://console:8700',
  set href(v) { rec.nav.push(v); }, get href() { return 'http://console:8700/base?tab=1'; }};
const ctx = {
  document, location, L, console, JSON, Math, Date, Promise, Set, Map, Object, Array,
  Number, String, parseFloat, isNaN, isFinite, encodeURIComponent, URL, URLSearchParams,
  WebSocket: FakeSocket,
  fetch: async (url, opts) => { rec.fetches.push(String(url)); return routes(String(url), opts || {}); },
  alert: m => rec.alerts.push(String(m)),
  confirm: () => true,
  setTimeout: (fn, ms) => { rec.timeouts.push({fn, ms}); return rec.timeouts.length; },
  clearTimeout() {},
  setInterval: (fn, ms) => { rec.intervals.push({fn, ms}); return rec.intervals.length; },
  clearInterval() {},
  localStorage: {getItem: () => null, setItem() {}, removeItem() {}},
  navigator: {}, prompt: () => { throw new Error('prompt() must not be used'); },
};
ctx.window = ctx; ctx.globalThis = ctx;
vm.createContext(ctx);
for (const f of files) vm.runInContext(fs.readFileSync(STATIC + '/' + f, 'utf8'), ctx, {filename: f});
const api = {rec, els, ctx, run: s => vm.runInContext(s, ctx),
             setRoutes: r => { routes = r; },
             flush: () => new Promise(r => setImmediate(r))};
ctx.api = api;   // the scenario runs inside the page's own global scope
(async () => {
  const out = await vm.runInContext('(async () => {' + scenario + '\n})()', ctx);
  console.log(JSON.stringify(out === undefined ? null : out));
})().catch(e => { console.error(e && e.stack || String(e)); process.exit(1); });
"""


def run(files, scenario):
    """Load `files` into one scope and evaluate `scenario`; return its JSON."""
    if NODE is None:
        raise unittest.SkipTest("node is not installed")
    proc = subprocess.run([NODE, "-e", HARNESS, str(STATIC), json.dumps(files), scenario],
                          capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return json.loads(proc.stdout)


def run_block(code: str, expression: str):
    if NODE is None:
        raise unittest.SkipTest("node is not installed")
    proc = subprocess.run([NODE, "-e", code + f"\nconsole.log(JSON.stringify({expression}));"],
                          capture_output=True, text=True, timeout=15)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return json.loads(proc.stdout)


# ------------------------------------------------------------------------ A / C
class SharedViewHelpers(unittest.TestCase):
    """Improvement A: one copy of esc / planeIcon / fmtDur / the socket / the
    clock / the auth badge, in charts.js."""

    VIEWS = ("app.js", "base.js", "debrief.js")
    MOVED = ("esc", "planeIcon", "fmtDur", "fmt", "initAuthBadge")

    def test_the_helpers_live_in_charts_js(self):
        charts = src("charts.js")
        for name in ("const esc =", "const planeIcon =", "const fmtDur =",
                     "function vsarConnect(", "function vsarStartClock(",
                     "async function vsarInitAuthBadge(", "function vsarBackoffMs("):
            self.assertIn(name, charts)

    def test_the_views_do_not_carry_their_own_copies(self):
        for view in self.VIEWS:
            text = src(view)
            with self.subTest(view=view):
                for name in self.MOVED:
                    self.assertIsNone(
                        re.search(rf"^(?:const|let|function)\s+{name}\b", text, re.M),
                        f"{view} redefines {name}")
                self.assertNotIn("new WebSocket", text)
                self.assertNotIn("/api/auth/me", text)
                self.assertNotIn("toUTCString().slice(17, 25)", text)

    def test_every_page_loads_charts_js_before_its_view(self):
        for page, view in (("index.html", "app.js"), ("base.html", "base.js"),
                           ("debrief.html", "debrief.js"), ("radio.html", "radio.js")):
            html = src(page)
            with self.subTest(page=page):
                self.assertLess(html.index("/static/charts.js"), html.index("/static/" + view))

    def test_every_page_script_set_loads_without_a_redeclaration(self):
        """Classic scripts share one global lexical scope: a view that still
        declares esc/planeIcon/fmtDur would be a SyntaxError that kills the
        whole page."""
        # debrief.html loads shell.js and viz.js between charts.js and debrief.js.
        for views in (["charts.js", "geodesy.js", "app.js"], ["charts.js", "geodesy.js", "base.js"],
                      ["charts.js", "shell.js", "viz.js", "debrief.js"], ["charts.js", "radio.js"]):
            with self.subTest(views=views):
                self.assertEqual(run(views, "return 'loaded';"), "loaded")

    def test_the_helpers_work(self):
        out = run(["charts.js"], r"""
          api.els.userBadge = {textContent: ''};
          api.setRoutes(() => ({ok: true, status: 200, json: async () => ({authenticated: true, role: 'base', callsign: 'MRO 1'})}));
          await vsarInitAuthBadge('Base Staff');
          const roleBadge = api.els.userBadge.textContent;
          api.setRoutes(() => ({ok: true, status: 200, json: async () => ({authenticated: true, title: 'Exercise Director'})}));
          await vsarInitAuthBadge('Base Staff');
          vsarStartClock(api.els.clock = {textContent: ''});
          return {esc: esc(`<a href="x" onclick='y'>&</a>`), dur: fmtDur(125.9),
                  roleBadge, titleBadge: api.els.userBadge.textContent,
                  clock: api.els.clock.textContent, ticks: api.rec.intervals.length};
        """)
        self.assertEqual(out["esc"], "&lt;a href=&quot;x&quot; onclick=&#39;y&#39;&gt;&amp;&lt;/a&gt;")
        self.assertEqual(out["dur"], "02:05")
        self.assertIn("BASE (MRO 1)", out["roleBadge"])
        self.assertIn("Exercise Director", out["titleBadge"])
        self.assertRegex(out["clock"], r"^\d\d:\d\d:\d\dZ$")
        self.assertEqual(out["ticks"], 1)


class ReconnectBackoff(unittest.TestCase):
    """Improvement C: the exponential backoff mission-radio.js already had, for
    app.js, base.js and radio.js (all via vsarConnect)."""

    def test_it_is_the_same_curve_as_the_mission_radio(self):
        radio = src("mission-radio.js")
        formula = re.search(r"const delay=(Math\.min\(30000,[^;]+\));", radio).group(1)
        theirs = run_block("const state={reconnectAttempt:0};",
                           "[0,1,2,3,4,5,6,9].map(n=>{state.reconnectAttempt=n;return %s})" % formula)
        ours = run(["charts.js"], "return [0,1,2,3,4,5,6,9].map(vsarBackoffMs);")
        self.assertEqual(theirs, ours)
        self.assertEqual(ours, [1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000])

    def test_a_dropped_socket_retries_with_growing_delays_and_resets_on_open(self):
        out = run(["charts.js"], r"""
          const seen = [];
          vsarConnect({onOpen: () => seen.push('open'), onMessage: m => seen.push(m.type)});
          const drop = () => { api.rec.sockets[api.rec.sockets.length - 1].onclose(); };
          drop(); drop();   // closes with no open in between -> attempt 0, 1
          const first = api.rec.timeouts.map(t => t.ms);
          // run the pending retry: a new socket, which opens and delivers a frame
          api.rec.timeouts[1].fn();
          const sock = api.rec.sockets[api.rec.sockets.length - 1];
          sock.onopen(); sock.onmessage({data: '{"type":"state"}'}); sock.onmessage({data: 'not json'});
          drop();
          return {first, afterOpen: api.rec.timeouts[api.rec.timeouts.length - 1].ms, seen,
                  url: api.rec.sockets[0].url, status: api.els.status.textContent};
        """)
        self.assertEqual(out["first"], [1000, 2000])
        self.assertEqual(out["afterOpen"], 1000, "a successful open must reset the backoff")
        self.assertEqual(out["seen"], ["open", "state"], "a malformed frame is dropped, not thrown")
        self.assertEqual(out["url"], "ws://console:8700/ws")
        self.assertEqual(out["status"], "reconnecting")

    def test_no_view_retries_on_a_fixed_timer_any_more(self):
        for view in ("app.js", "base.js", "radio.js"):
            text = src(view)
            with self.subTest(view=view):
                self.assertNotRegex(text, r"setTimeout\(connect(WebSocket)?,\s*\d+\)")
                self.assertIn("vsarConnect(", text)

    def test_the_instructor_backfills_what_it_missed(self):
        """F-4 for the instructor: on every socket open it asks for bearings it
        has not seen, and a bearing delivered by both paths is drawn once."""
        out = run(["charts.js", "geodesy.js", "app.js"], r"""
          const bearing = (id, t) => ({type: 'bearing', id, callsign: 'CAP 1', t, lat: 33, lon: -117, bearing_true: 90, note: ''});
          api.setRoutes(url => {
            if (url.startsWith('/api/bearings')) return {ok: true, status: 200, json: async () => [bearing(1, 100), bearing(2, 101)]};
            return {ok: true, status: 200, json: async () => []};
          });
          const sock = api.rec.sockets[0];
          sock.onopen();
          await api.flush(); await api.flush();
          sock.onmessage({data: JSON.stringify(bearing(2, 101))});      // duplicate of a backfilled row
          sock.onmessage({data: JSON.stringify(bearing(3, 102))});
          const drawn = api.rec.polylines.length;
          sock.onclose(); api.rec.timeouts[api.rec.timeouts.length - 1].fn();
          api.rec.sockets[1].onopen();
          await api.flush();
          return {drawn, queries: api.rec.fetches.filter(u => u.startsWith('/api/bearings'))};
        """)
        self.assertEqual(out["drawn"], 3, "ids 1,2,3 each drawn exactly once")
        self.assertEqual(out["queries"][0], "/api/bearings?since=0")
        self.assertRegex(out["queries"][1], r"^/api/bearings\?since=10[12]")

    def test_a_new_sortie_clears_the_instructor_view(self):
        out = run(["charts.js", "geodesy.js", "app.js"], r"""
          const frame = id => ({type: 'state', sortie: {id, name: 'S', started: 0}, server_time: 1,
            scenario: {id: 'sc', effects: {}}, aircraft: [{callsign: 'CAP 1', lat: 33, lon: -117, alt_ft: 1, hdg_true: 0}]});
          const sock = api.rec.sockets[0];
          sock.onmessage({data: JSON.stringify(frame('a'))});
          sock.onmessage({data: JSON.stringify({type: 'bearing', id: 1, callsign: 'CAP 1', t: 5, lat: 33, lon: -117, bearing_true: 10})});
          const before = api.els.bearings.innerHTML;
          // the second sortie's first push must reset the view, then keep rendering
          sock.onmessage({data: JSON.stringify(frame('b'))});
          sock.onmessage({data: JSON.stringify(frame('b'))});
          return {before, after: api.els.bearings.textContent};
        """)
        self.assertIn("CAP 1", out["before"])
        self.assertEqual(out["after"], "no bearings logged")


class InstructorRayUsesSharedGeodesy(unittest.TestCase):
    """Improvement B: the instructor's ray is the same great circle the base
    draws, from one shared file."""

    def test_both_pages_load_the_shared_file_before_their_view(self):
        for page, view in (("index.html", "app.js"), ("base.html", "base.js")):
            html = src(page)
            with self.subTest(page=page):
                self.assertLess(html.index("/static/geodesy.js"), html.index("/static/" + view))

    def test_the_instructor_ray_ends_where_the_base_ray_ends(self):
        out = run(["charts.js", "geodesy.js", "app.js"], r"""
          api.rec.sockets[0].onmessage({data: JSON.stringify({type: 'bearing', id: 1, callsign: 'A', t: 1,
            lat: 61.17, lon: -149.99, bearing_true: 45, note: ''})});
          const ray = api.rec.polylines[0].pts[1];
          return {ray, expected: bearingDestination(61.17, -149.99, 45, 40),
                  flat: [61.17 + (40/60) * Math.cos(Math.PI/4), -149.99 + (40/60) * Math.sin(Math.PI/4) / Math.cos(61.17 * Math.PI/180)]};
        """)
        for a, b in zip(out["ray"], out["expected"]):
            self.assertAlmostEqual(a, b, places=9)
        # at 61 N the old flat-earth shortcut ends a visible distance away
        self.assertGreater(abs(out["flat"][0] - out["expected"][0]), 0.003)

    def test_the_flat_earth_ray_is_gone(self):
        self.assertNotIn("Math.cos(lat1)", src("app.js"))
        self.assertIn("bearingDestination(", src("app.js"))


# ------------------------------------------------------------------ F2-5, F2-9
class SessionGating(unittest.TestCase):
    """F2-5: no role token in localStorage, no prompt(); a refusal sends the
    page to /login with where it was."""

    def test_the_token_path_is_gone(self):
        charts = src("charts.js")
        for gone in ("prompt(", "vsar-role-token", "X-CAPVSAR-Token", "vsarToken", "vsarSetToken"):
            self.assertNotIn(gone, charts)
        for view in ("app.js", "base.js"):
            self.assertNotIn("vsarToken", src(view))

    def test_a_refusal_redirects_to_login_with_next(self):
        out = run(["charts.js"], r"""
          const res = {};
          for (const status of [200, 401, 403, 500]) {
            api.rec.nav.length = 0;
            api.setRoutes(() => ({ok: status === 200, status}));
            const r = await vsarFetch('/api/bearings', {method: 'POST'});
            res[status] = {nav: api.rec.nav.slice(), returned: r.status};
          }
          api.ctx.location.pathname = '/login'; api.rec.nav.length = 0;
          api.setRoutes(() => ({ok: false, status: 403}));
          await vsarFetch('/x');
          res.onLogin = api.rec.nav.slice();
          res.url = vsarLoginUrl('/base', '?a=1&b=2');
          res.noToken = api.rec.fetches.length;
          return res;
        """)
        self.assertEqual(out["200"]["nav"], [])
        self.assertEqual(out["500"]["nav"], [])
        for status in ("401", "403"):
            self.assertEqual(out[status]["nav"], ["/login?next=%2Fbase%3Ftab%3D1"])
            self.assertEqual(out[status]["returned"], int(status), "callers still see the response")
        self.assertEqual(out["onLogin"], [], "no redirect loop from the login page")
        self.assertEqual(out["url"], "/login?next=%2Fbase%3Fa%3D1%26b%3D2")

    def test_it_would_notice_the_prompt_coming_back(self):
        out = run(["charts.js"], "return typeof vsarSetToken;")
        self.assertEqual(out, "undefined")


class FailureMessages(unittest.TestCase):
    """F2-9: the real status and server text, not 'callsign not reporting'."""

    def test_helper_words_each_failure(self):
        out = run(["charts.js"], r"""
          const mk = (status, body) => ({status, json: async () => { if (body === undefined) throw new Error('x'); return body; }});
          return [
            await vsarFailureText(mk(404, {detail: 'no position on record for that aircraft'}), 'Bearing not logged'),
            await vsarFailureText(mk(503, undefined), 'Bearing not logged'),
            await vsarFailureText(mk(422, {detail: [{msg: 'Input should be a valid number'}]}), 'Bearing not logged'),
            await vsarFailureText(mk(403, {detail: 'forbidden'}), 'Bearing not logged'),
          ];
        """)
        self.assertEqual(out[0], "Bearing not logged (HTTP 404): no position on record for that aircraft.")
        self.assertEqual(out[1], "Bearing not logged (HTTP 503).")
        self.assertEqual(out[2], "Bearing not logged (HTTP 422): Input should be a valid number.")
        self.assertEqual(out[3], "", "an auth failure is already redirecting; no dialog over it")

    def test_base_reports_the_real_failure(self):
        out = run(["charts.js", "geodesy.js", "base.js"], r"""
          api.els.brgCallsign = {value: 'CAP 1', tagName: 'INPUT'};
          api.els.brgValue.value = '90';
          api.els.brgNote.value = '';
          api.setRoutes(() => ({ok: false, status: 503, json: async () => ({detail: 'database is busy'})}));
          await api.els.brgAdd.onclick();
          return api.rec.alerts;
        """)
        self.assertEqual(len(out), 1)
        self.assertIn("HTTP 503", out[0])
        self.assertIn("database is busy", out[0])
        self.assertNotIn("not reporting a position", out[0])

    def test_instructor_load_scenarios_and_stop_reveal_check_ok(self):
        out = run(["charts.js", "geodesy.js", "app.js"], r"""
          api.setRoutes(url => url === '/api/scenarios'
            ? {ok: false, status: 503, json: async () => { throw new Error('html'); }}
            : {ok: false, status: 500, json: async () => ({detail: 'boom'})});
          await api.run('loadScenarios()');
          const notes = api.els.scenarioNotes.textContent;
          await api.els.stopBtn.onclick();
          await api.els.revealBtn.onclick();
          await api.els.startBtn.onclick();
          return {notes, alerts: api.rec.alerts};
        """)
        self.assertIn("HTTP 503", out["notes"])
        self.assertEqual(len(out["alerts"]), 3)
        self.assertTrue(all("HTTP 500" in a and "boom" in a for a in out["alerts"]))


# ------------------------------------------------------------------------ F2-6
class LoginNext(unittest.TestCase):
    """F2-6: only a same-origin relative path is followed after login."""

    def safe_next(self, value):
        code = block("login.js", "F2-6 PURE NEXT URL")
        return run_block(code, f"safeNext({json.dumps(value)}, 'https://console')")

    def test_relative_paths_are_followed(self):
        for ok in ("/base", "/setup", "/", "/radio?model=efj5300", "/debrief#top"):
            with self.subTest(next=ok):
                self.assertEqual(self.safe_next(ok), ok)

    def test_everything_else_is_refused(self):
        for bad in ("//evil.example/x", "///evil.example", "/\\evil.example", "/\t/evil.example",
                    "/\n/evil.example", "https://evil.example/", "http://console/base",
                    "javascript:alert(1)", "data:text/html,x", "evil.example", "base", "",
                    "\\\\evil.example", " /base", None, 5):
            with self.subTest(next=bad):
                self.assertIsNone(self.safe_next(bad))

    def test_the_login_uses_it(self):
        text = src("login.js")
        self.assertIn('safeNext(urlParams.get("next"))', text)
        self.assertNotIn('const nextUrl = urlParams.get("next")', text)

    def test_the_login_page_carries_no_shortcut_codes(self):
        """Improvement F: removed from the file, not stripped on the way out."""
        html, js, css = src("login.html"), src("login.js"), src("style.css")
        for code in ("INSTR-1", "MRO-1", "OBS-423", "UDF-1"):
            self.assertNotIn(code, html)
        self.assertNotIn("login-shortcuts", html)
        self.assertNotIn("btn-code-shortcut", js)
        self.assertNotIn("btn-code-shortcut", css)
        self.assertIn('maxlength="128"', html)
        self.assertNotIn("login-shortcuts-section", (ROOT / "services/exercise/app/routers/auth.py").read_text())


# ----------------------------------------------------------------------- F2-10
class SetupPage(unittest.TestCase):
    def test_the_decorative_scenario_control_is_gone(self):
        html, js = src("setup.html"), src("setup.js")
        self.assertNotIn("exScenario", html + js)
        self.assertNotIn("Target Exercise Scenario", html)
        self.assertNotIn("/api/scenarios", js)
        self.assertNotIn("scenarioDesc", html + js)


# ------------------------------------------------------------------------ F2-7
DEBRIEF_FIXTURE = r"""
  const pos = (cs, t, lat) => ({callsign: cs, t, lat, lon: -117, hdg_true: 90});
  const sorties = [{id: 's1', started: 1000, name: 'First', points: 4}, {id: 's2', started: 2000, name: 'Empty', points: 0}];
  const tracks = {
    s1: {positions: [pos('A', 0, 33), pos('A', 10, 33.1), pos('B', 0, 34), pos('B', 10, 34.1)], bearings: [], messages: [], beacon: null},
    s2: {positions: [], bearings: [], messages: [], beacon: null},
  };
  api.els.sortieSel = {value: 's1', selectedOptions: [{text: 'x — First'}], innerHTML: ''};
  api.els.slider.value = '50'; api.els.speed.value = '1';
  api.setRoutes(url => {
    if (url === '/api/sorties') return {ok: true, status: 200, json: async () => sorties};
    const m = url.match(/\/api\/sorties\/([^/]+)\/track/);
    if (m && tracks[m[1]]) return {ok: true, status: 200, json: async () => tracks[m[1]]};
    return {ok: false, status: 503, json: async () => ({})};
  });
"""


class Debrief(unittest.TestCase):
    """F2-7."""

    def test_selecting_a_sortie_with_no_positions_does_not_leave_the_old_aircraft(self):
        # viz.js: debrief.html loads it before debrief.js, which draws its chart with it.
        out = run(["charts.js", "viz.js", "debrief.js"], DEBRIEF_FIXTURE + r"""
          await loadList(); for (let i = 0; i < 5; i++) await api.flush();   // loadList() -> load('s1')
          const loaded = api.run('order.length');
          await api.run("load('s2')");
          let threw = null;
          try { api.run('seek(0.5)'); } catch (e) { threw = String(e); }
          return {loaded, order: api.run('order.length'), groups: api.run('Object.keys(groups).length'),
                  threw, info: api.els.sortieInfo.textContent};
        """)
        self.assertEqual(out["loaded"], 2)
        self.assertEqual(out["order"], 0, "stale callsigns must not survive")
        self.assertEqual(out["groups"], 0)
        self.assertIsNone(out["threw"])
        self.assertIn("no positions", out["info"])

    def test_failed_fetches_are_reported_not_thrown(self):
        # viz.js: debrief.html loads it before debrief.js, which draws its chart with it.
        out = run(["charts.js", "viz.js", "debrief.js"], r"""
          api.setRoutes(() => ({ok: false, status: 503, json: async () => { throw new Error('html'); }}));
          await api.run('loadList()');
          const list = api.els.sortieInfo.textContent;
          await api.run("load('s9')");
          const track = api.els.sortieInfo.textContent;
          api.setRoutes(() => { throw new Error('network'); });
          await api.run('loadList()');
          return {list, track, offline: api.els.sortieInfo.textContent};
        """)
        self.assertIn("HTTP 503", out["list"])
        self.assertIn("HTTP 503", out["track"])
        self.assertIn("unreachable", out["offline"])


# ------------------------------------------------------------- F2-2 / 11 / pagehide
class MissionRadioFailureScope(unittest.TestCase):
    """The airband radio is the SECONDARY receiver. These are structural: the
    handlers need a live voice stack, so what is asserted is which function each
    one calls, and each assertion is shown to fail on the old code."""

    @classmethod
    def setUpClass(cls):
        cls.js = src("mission-radio.js")

    @staticmethod
    def join_timeout(js):
        return re.search(r"airband\.timeout=setTimeout\(.*?,15000\);", js).group(0)

    @staticmethod
    def pong_watchdog(js):
        return re.search(r"if\(airband\.online&&Date\.now\(\)-airband\.lastPong>6000\)[^\n]*", js).group(0)

    @staticmethod
    def bad_frame(js):
        return js[js.index("let message; try{"):js.index("if(message.type==='tuned')")]

    def test_the_airband_join_timeout_only_drops_the_airband_radio(self):
        handler = self.join_timeout(self.js)
        self.assertIn("airbandLost(", handler)
        self.assertNotIn("connectionLost(", handler)

    def test_the_airband_pong_timeout_only_drops_the_airband_radio(self):
        watchdog = self.pong_watchdog(self.js)
        self.assertIn("airbandLost(", watchdog)
        self.assertNotIn("connectionLost(", watchdog)
        self.assertNotIn("return", watchdog, "the tactical radio's ping must still go out")

    def test_a_malformed_control_frame_retries_instead_of_giving_up(self):
        frame = self.bad_frame(self.js)
        self.assertNotIn("disconnect()", frame)
        self.assertIn("connectionLost(", frame)
        self.assertIn("airbandLost(", frame)

    def test_pagehide_releases_ptt_but_keeps_the_wish_to_be_online(self):
        # disconnect() is what clears wantOnline, so pagehide must not call it.
        self.assertRegex(self.js, r"function disconnect\(\) \{\s*state\.wantOnline=false")
        handler = re.search(r"window\.addEventListener\('pagehide',[^\n]*", self.js).group(0)
        self.assertIn("releaseAll", handler)
        self.assertNotIn("disconnect", handler)

    def test_the_checks_fail_on_the_old_code(self):
        old_join = self.js.replace("airbandLost('The airband connection timed out.')",
                                   "connectionLost('The airband connection timed out.')")
        self.assertNotIn("airbandLost(", self.join_timeout(old_join))
        old_pong = self.js.replace("airbandLost('Airband radio stopped responding.')",
                                   "{connectionLost('Airband radio stopped responding.');return;}")
        self.assertNotIn("airbandLost(", self.pong_watchdog(old_pong))
        old_frame = self.js.replace("catch{  // F2-11", "catch{disconnect();  // F2-11")
        self.assertIn("disconnect()", self.bad_frame(old_frame))
        old_hide = self.js.replace("window.addEventListener('pagehide',()=>releaseAll());",
                                   "window.addEventListener('pagehide',disconnect);")
        self.assertIn("disconnect", re.search(r"window\.addEventListener\('pagehide',[^\n]*", old_hide).group(0))


# ------------------------------------------------------------------- F2-3 / F2-4
FAKE_DOM = r"""
class Node {
  constructor(tag) { this.tag = tag; this.className = ''; this.children = []; this.parent = null;
    this._text = ''; this.handlers = {}; }
  get firstChild() { return this.children[0] || null; }
  get lastChild() { return this.children[this.children.length - 1] || null; }
  set textContent(v) { this.children.forEach(c => c.parent = null); this.children = []; this._text = String(v); }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  insertBefore(c, ref) { c.parent = this; const i = ref ? this.children.indexOf(ref) : this.children.length;
    this.children.splice(i, 0, c); return c; }
  removeChild(c) { this.children.splice(this.children.indexOf(c), 1); c.parent = null; return c; }
  contains(n) { return n === this || this.children.some(c => c.contains(n)); }
  addEventListener(type, fn) { (this.handlers[type] ||= []).push(fn); }
  fire(type) { (this.handlers[type] || []).forEach(f => f()); }
}
const doc = {activeElement: null, createElement: t => new Node(t)};
const entry = (n, extra = {}) => Object.assign({id: 'e' + n, t: 1.7e9 + n, from: 'CAP ' + n, to: 'NET',
  traffic: '', outgoing: false, net: 'PRIMARY', seconds: null}, extra);
const texts = body => body.children.map(r => r.children.map(c => c.textContent).join('|'));
"""


class Form110(unittest.TestCase):
    """F2-3 (the table must not be rebuilt under the MRO's cursor) and F2-4
    (the log survives a reload)."""

    @classmethod
    def setUpClass(cls):
        cls.store = block("mission-radio.js", "F2-4 PURE FORM 110 STORE")
        cls.view = block("mission-radio.js", "F2-3 PURE FORM 110 VIEW")
        cls.js = src("mission-radio.js")

    def go(self, body, expression):
        return run_block(FAKE_DOM + self.store + self.view + body, expression)

    # -- F2-4
    def test_the_log_round_trips_through_session_storage(self):
        out = self.go(r"""
          const mem = {}; const storage = {setItem: (k, v) => { mem[k] = v; }, getItem: k => mem[k] ?? null};
          const log = [entry(2, {traffic: 'KMYF wx 3 miles', outgoing: true, seconds: 4.2}), entry(1)];
          const ok = saveCommLog(storage, log);
        """, "(() => ({ok, back: loadCommLog(storage), same: JSON.stringify(loadCommLog(storage)) === JSON.stringify(log)}))()")
        self.assertTrue(out["ok"])
        self.assertTrue(out["same"])
        self.assertEqual(out["back"][0]["traffic"], "KMYF wx 3 miles")

    def test_unreadable_or_hostile_storage_restores_an_empty_log(self):
        out = self.go("", r"""({
          empty: loadCommLog({getItem: () => null}),
          junk: loadCommLog({getItem: () => '{not json'}),
          wrongVersion: loadCommLog({getItem: () => '{"v":2,"entries":[{"t":1}]}'}),
          notArray: loadCommLog({getItem: () => '{"v":1,"entries":"x"}'}),
          throwsOnRead: loadCommLog({getItem: () => { throw new Error('blocked'); }}),
          throwsOnWrite: saveCommLog({setItem: () => { throw new Error('quota'); }}, [entry(1)]),
          cleaned: restoreCommLog(JSON.stringify({v: 1, entries: [
            {t: 5, from: {x: 1}, traffic: 7, outgoing: 'yes', seconds: 'NaN'}, null, {from: 'no time'}, 'str']})),
        })""")
        for key in ("empty", "junk", "wrongVersion", "notArray", "throwsOnRead"):
            self.assertEqual(out[key], [], key)
        self.assertFalse(out["throwsOnWrite"])
        self.assertEqual(len(out["cleaned"]), 1)
        row = out["cleaned"][0]
        self.assertEqual((row["from"], row["traffic"], row["outgoing"], row["seconds"]), ("", "", False, None))

    def test_the_log_is_trimmed_to_the_limit_when_saved(self):
        out = self.go("", r"JSON.parse(serializeCommLog(Array.from({length: 600}, (_, i) => entry(i)))).entries.length")
        self.assertEqual(out, 500)

    def test_every_change_is_saved_and_the_page_restores_on_load(self):
        self.assertRegex(self.js, r"const commLog = loadCommLog\(")
        log_entry = self.js[self.js.index("function logEntry"):self.js.index("function renderLog")]
        self.assertIn("persistCommLog()", log_entry)
        clear = self.js[self.js.index("$('logClear')"):self.js.index("$('logAdd')")]
        self.assertIn("persistCommLog()", clear)
        # typing into a traffic cell is saved too (the row's onEdit)
        self.assertIn("form110Insert(document, body, entry, persistCommLog", self.js)
        out = self.go(r"""
          const mem = {}; const storage = {setItem: (k, v) => { mem[k] = v; }, getItem: k => mem[k] ?? null};
          const e = entry(1); const row = form110Row(doc, e, () => saveCommLog(storage, [e]));
          const cell = row.children[5]; cell.textContent = '  wx passed  ';
          cell.fire('input');
        """, "loadCommLog(storage)[0].traffic")
        self.assertEqual(out, "wx passed")

    # -- F2-3
    def test_a_new_entry_is_inserted_without_touching_the_existing_rows(self):
        out = self.go(r"""
          const body = new Node('tbody'); body.appendChild(form110Empty(doc));
          const a = form110Insert(doc, body, entry(1), null);
          const typing = a.children[5]; doc.activeElement = typing;
          const b = form110Insert(doc, body, entry(2), null);
          const c = form110Insert(doc, body, entry(3), null);
        """, "({rows: body.children.length, newestFirst: body.firstChild === c, oldKept: body.children[2] === a, "
             "cellKept: a.children[5] === typing, stillAttached: body.contains(typing), noPlaceholder: !texts(body).some(t => t.startsWith('No traffic'))})")
        self.assertEqual(out["rows"], 3)
        for key in ("newestFirst", "oldKept", "cellKept", "stillAttached", "noPlaceholder"):
            self.assertTrue(out[key], key)

    def test_a_rebuild_refuses_to_run_while_a_traffic_cell_has_focus(self):
        out = self.go(r"""
          const log = [entry(2), entry(1)];
          const body = new Node('tbody');
          form110Rebuild(doc, body, log, null);
          const rowsBefore = body.children.slice();
          doc.activeElement = rowsBefore[0].children[5];
          const skipped = form110Rebuild(doc, body, log, null);
          const untouched = body.children.every((r, i) => r === rowsBefore[i]);
          doc.activeElement = null;
          const ran = form110Rebuild(doc, body, log, null);
          const rebuilt = body.children.every((r, i) => r !== rowsBefore[i]);
        """, "({skipped, untouched, ran, rebuilt, text: texts(body)[0]})")
        self.assertFalse(out["skipped"])
        self.assertTrue(out["untouched"])
        self.assertTrue(out["ran"])
        self.assertTrue(out["rebuilt"])
        self.assertIn("CAP 2", out["text"])

    def test_the_table_is_capped_and_shows_an_empty_state(self):
        out = self.go(r"""
          const body = new Node('tbody');
          for (let i = 0; i < 12; i++) form110Insert(doc, body, entry(i), null, 10);
          const capped = body.children.length;
          const empty = new Node('tbody'); form110Rebuild(doc, empty, [], null);
        """, "({capped, oldestDropped: !texts(body).some(t => t.includes('CAP 0|') || t.includes('CAP 1|')), empty: texts(empty)})")
        self.assertEqual(out["capped"], 10)
        self.assertTrue(out["oldestDropped"])
        self.assertEqual(out["empty"], ["No traffic logged yet."])

    def test_a_logged_transmission_inserts_a_row_not_a_rebuild(self):
        log_entry = self.js[self.js.index("function logEntry"):self.js.index("function renderLog")]
        self.assertIn("form110Insert(", log_entry)
        self.assertNotIn("renderLog(", log_entry)
        # ...and the detector would notice the old behaviour coming back
        regressed = log_entry.replace("form110Insert(document, body, entry, persistCommLog, LOG_LIMIT)", "renderLog()")
        self.assertIn("renderLog(", regressed)

    def test_traffic_text_never_reaches_innerhtml(self):
        view = self.view
        self.assertNotIn(".innerHTML", view)
        self.assertIn("textContent = entry.traffic", view)


# --------------------------------------------------------------------------- F2-12
class LegacyConsole(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = src("radio.js")

    def keys(self, element):
        return run_block(block("radio.js", "F2-12 PURE KEY POLICY"), f"spaceKeysPtt({element})")

    def test_space_only_keys_the_radio_when_nothing_else_wants_it(self):
        self.assertTrue(self.keys("null"))
        self.assertTrue(self.keys("{tagName: 'BODY'}"))
        self.assertTrue(self.keys("{tagName: 'DIV', getAttribute: () => null}"))
        self.assertTrue(self.keys("{tagName: 'DIV', getAttribute: () => 'false'}"))
        for tag in ("INPUT", "SELECT", "TEXTAREA", "BUTTON", "input"):
            with self.subTest(tag=tag):
                self.assertFalse(self.keys("{tagName: '%s'}" % tag))
        self.assertFalse(self.keys("{tagName: 'DIV', isContentEditable: true}"))
        self.assertFalse(self.keys("{tagName: 'DIV', getAttribute: () => ''}"))
        self.assertFalse(self.keys("{tagName: 'TD', getAttribute: () => 'true'}"))

    def test_the_listeners_use_the_policy_not_a_bare_input_check(self):
        self.assertNotIn("activeElement.tagName !== 'INPUT'", self.js)
        keydown = self.js[self.js.index("window.addEventListener('keydown'"):self.js.index("window.addEventListener('keyup'")]
        self.assertIn("spaceKeysPtt(", keydown)

    def send(self, ok, raises=False):
        func = self.js[self.js.index("async function sendCommsMessage"):self.js.index("// CAP FORM 110 COMMUNICATIONS LOG")]
        func = func[:func.rindex("// ----")]
        script = r"""
          const logged = [], alerts = [];
          const activeRadio = 'apx', apx = {zoneIdx: 0, chanIdx: 0};
          const APX_ZONES = [{channels: [{name: 'TAC 1', freq: '121.5 MHz'}]}];
          const ICOM_PRESETS = [], icom = {};
          const box = {value: '', trim() { return this.value.trim(); }};
          const $ = id => ({value: id === 'msgRecipient' ? '' : box.value});
          const addForm110Entry = e => logged.push(e);
          const alert = m => alerts.push(m);
          const fetch = async () => { if (%s) throw new Error('offline'); return {ok: %s, status: 503}; };
          """ % ("true" if raises else "false", "true" if ok else "false") + func + r"""
          await sendCommsMessage('RTB now');
          console.log(JSON.stringify({logged: logged.length, alerts}));
        """
        proc = subprocess.run([NODE, "-e", "(async () => {" + script + "})()"],
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    @unittest.skipIf(NODE is None, "node is not installed")
    def test_a_message_the_console_refused_is_not_logged_as_sent(self):
        refused = self.send(ok=False)
        self.assertEqual(refused["logged"], 0)
        self.assertEqual(len(refused["alerts"]), 1)
        self.assertIn("NOT sent", refused["alerts"][0])
        self.assertIn("HTTP 503", refused["alerts"][0])

    @unittest.skipIf(NODE is None, "node is not installed")
    def test_an_unreachable_console_is_not_logged_either(self):
        unreachable = self.send(ok=False, raises=True)
        self.assertEqual(unreachable["logged"], 0)
        self.assertIn("unreachable", unreachable["alerts"][0])

    @unittest.skipIf(NODE is None, "node is not installed")
    def test_a_delivered_message_is_logged_once(self):
        delivered = self.send(ok=True)
        self.assertEqual(delivered, {"logged": 1, "alerts": []})


# ----------------------------------------------------------------------- F2-8, G
class HelpPage(unittest.TestCase):
    def test_the_secure_link_follows_the_address_the_page_was_opened_on(self):
        html = src("radio-help.html")
        self.assertNotRegex(html, r"\d+\.\d+\.\d+\.\d+")
        self.assertIn('id="secureRadio"', html)
        out = run_block("""
          const link = {href: '/radio'};
          const document = {getElementById: id => id === 'secureRadio' ? link : null};
          const location = {hostname: '192.0.2.7'};
        """ + re.search(r"<script>(.*?)</script>", html, re.S).group(1), "link.href")
        self.assertEqual(out, "https://192.0.2.7/radio")
        v6 = run_block("""
          const link = {href: '/radio'};
          const document = {getElementById: () => link};
          const location = {hostname: '::1'};
        """ + re.search(r"<script>(.*?)</script>", html, re.S).group(1), "link.href")
        self.assertEqual(v6, "https://[::1]/radio")

    def test_the_docs_describe_the_dual_radio_and_the_log(self):
        for text in (src("radio-help.html"), (ROOT / "docs/mission-base-radio/README.md").read_text()):
            lowered = text.lower()
            self.assertIn("airband", lowered)
            self.assertIn("form 110", lowered)
            self.assertIn("eight", lowered)
            self.assertNotIn("one active radio connection", lowered)
            self.assertNotIn("listens to one selected net at a time", lowered)
        readme = (ROOT / "docs/mission-base-radio/README.md").read_text()
        self.assertNotIn("192.0.2.151/radio", readme)
        self.assertIn("sessionStorage", readme)
        self.assertNotIn("this new page does not automatically transcribe voice to it", readme)


# ------------------------------------------------------------------ T20 / B8
class OidcAndSignOut(unittest.TestCase):
    """T20 + B8: Google OIDC sign-in on /login, per-seat email invites on
    /setup, and POST /api/auth/logout in shell.js."""

    def test_shell_sign_out_posts_to_logout_then_redirects(self):
        shell = src("shell.js")
        self.assertNotIn("id.href = '/api/auth/logout'", shell)
        self.assertIn("fetch('/api/auth/logout'", shell)
        self.assertIn("method: 'POST'", shell)
        self.assertIn("location.href = '/login'", shell)

    def test_login_page_implements_oidc_provider_contract_and_errors(self):
        html, js = src("login.html"), src("login.js")
        self.assertIn('id="oidcSection"', html)
        self.assertIn('id="oidcLoginBtn"', html)
        self.assertIn('id="oidcDivider"', html)
        self.assertIn("Sign in with a badge code (offline / field use)", html)
        self.assertIn("/api/auth/providers", js)
        for code in ("oidc_cancelled", "oidc_failed", "no_seat", "invalid_code", "instructor_required"):
            self.assertIn(code, js, f"missing error handler for {code}")

    def test_setup_page_implements_seat_emails_and_invite_flow(self):
        html, js = src("setup.html"), src("setup.js")
        self.assertIn('id="directorEmailInput"', html)
        self.assertIn('id="inviteList"', html)
        self.assertIn('id="offlineBadgeFallback"', html)
        self.assertIn("Offline fallback: badge cards", html)
        for token in ("Copy sign-in link", "Email this invite", "mailto:",
                      "last_login_via", "Not signed in yet", "applyServer422Errors"):
            self.assertIn(token, js, f"setup.js missing {token}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

