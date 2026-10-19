#!/usr/bin/env node
/*
 * record-web-panels.cjs - records the Home hero clip `web-panels`: the web panels of the system, one after another,
 * from local servers with example data only. Writes one raw WebM per panel into $WORK/raw and the cut, cross-faded
 * and encoded files into website-next/site/assets/video/ (web-panels.webm, web-panels.mp4, web-panels-poster.webp).
 *
 * HOW TO RUN (from the repository root; nothing here touches X-Plane or the real console):
 *
 *   python3 -m venv /tmp/wp-venv && /tmp/wp-venv/bin/python -m pip install fastapi "uvicorn[standard]" pydantic \
 *       segno PyJWT cryptography Flask requests pygeomag Markdown
 *   WORK=/tmp/wp-work VENV_PY=/tmp/wp-venv/bin/python NODE_PATH=/tmp/t36-render/node_modules \
 *       node website-next/dev/qa/record-web-panels.cjs [--record] [--encode]     (default: both)
 *   SCENES=base,debrief ... node ...  to re-shoot only some panels (the console then starts a fresh sortie)
 *
 * What it starts (all bound to 127.0.0.1 on ports 18700-18703, each stopped again when the script ends; set
 * PORT_BASE to move them):
 *   18700  exercise console   uvicorn services/exercise app.main:app, CAPVSAR_DEV_OPEN=1, a fresh scratch SQLite file,
 *                             no tokens, voice host set to the placeholder "voice.example.invalid" (never contacted),
 *                             the built-in example scenario "C-1 Palomar ILS - 121.5 ELT at ESCON" and the built-in
 *                             generic seats (CAP 423, MRO 1, UDF 1). The page sessions are made by signing in with the
 *                             scratch database's own generated seat codes; a code is never typed on screen or shown.
 *   18701  flight planner     Flask services/flightplanner, scratch copy of the airport database, tiles offline
 *                             (cached sectional only), console URL pointed at 18700
 *   18702  AI Pilot deck      services/ai_pilot web_server (MOCK mode, no X-Plane), with example telemetry injected into
 *                             the mock client (cruise at 4,500 ft) so the instruments are not all zero
 *   18703  maneuver deck      services/ai_pilot maneuver_server (MOCK: its own static telemetry)
 * Skipped on purpose: the Agent Coordination Board (services/board, ai_pilot board.html) because its content is the
 * real dispatch queue (file locks, paths, a LAN address); the Flight Planner user guide because its first screen
 * lists addresses and host names and the clip would pass 26 s.
 *
 * Browser: system Google Chrome through Playwright (channel "chrome"), headless, 1280x720, deviceScaleFactor 1,
 * recordVideo; each panel is its own context so its own page-load blank is cut away. Aircraft CAP 423 / CAP 415 fly
 * from a feeder thread (one report a second, 4x speed) that runs from sortie start until the sortie is stopped.
 */
'use strict';
const { chromium } = require('playwright');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const net = require('net');
const http = require('http');

const REPO = path.resolve(__dirname, '..', '..', '..');
const SITE_VIDEO = path.join(REPO, 'website-next', 'site', 'assets', 'video');
const WORK = process.env.WORK || '/tmp/web-panels-work';
const VENV_PY = process.env.VENV_PY || 'python3';
const BASE = parseInt(process.env.PORT_BASE || '18700', 10);
const P = { ex: BASE, fp: BASE + 1, ai: BASE + 2, man: BASE + 3 };
const EX = `http://127.0.0.1:${P.ex}`, FP = `http://127.0.0.1:${P.fp}`;
const AI = `http://127.0.0.1:${P.ai}`, MAN = `http://127.0.0.1:${P.man}`;
const SEG = 2.7;          // seconds of each panel taken into the clip
const FADE = 0.25;        // cross-fade between panels
const args = process.argv.slice(2);
const DO_RECORD = args.includes('--record') || !args.includes('--encode');
const DO_ENCODE = args.includes('--encode') || !args.includes('--record');
const ONLY = (process.env.SCENES || '').split(',').filter(Boolean);

const sleep = ms => new Promise(r => setTimeout(r, ms));
const children = [];
function portFree(port) {
  return new Promise(res => { const s = net.createServer(); s.once('error', () => res(false));
    s.once('listening', () => s.close(() => res(true))); s.listen(port, '127.0.0.1'); });
}
function httpOk(url) {
  return new Promise(res => { http.get(url, r => { r.resume(); res(r.statusCode < 500); }).on('error', () => res(false)); });
}
async function waitFor(url, label) {
  for (let i = 0; i < 80; i++) { if (await httpOk(url)) return; await sleep(250); }
  throw new Error('server did not start: ' + label);
}
function start(label, cmd, argv, env, cwd) {
  const log = fs.openSync(path.join(WORK, label + '.log'), 'w');
  const c = spawn(cmd, argv, { cwd, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', ...env }, stdio: ['ignore', log, log] });
  children.push({ label, c });
  return c;
}
async function stopAll() {
  for (const { c } of children) { try { c.kill('SIGTERM'); } catch (e) { /* gone */ } }
  await sleep(1500);
  for (const { c } of children) { try { c.kill('SIGKILL'); } catch (e) { /* gone */ } }
  for (const port of Object.values(P)) {
    if (!(await portFree(port))) console.log('WARNING: port still busy after stop:', port);
  }
}
async function jget(url) { return (await fetch(url)).json(); }
async function jpost(url, body, headers = {}) {
  const r = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json', ...headers }, body: JSON.stringify(body) });
  const text = await r.text(); let j; try { j = JSON.parse(text); } catch (e) { j = { raw: text }; }
  if (!r.ok) throw new Error(`${url} ${r.status} ${text.slice(0, 200)}`);
  return { json: j, headers: r.headers };
}

// ------------------------------------------------------------------ servers
const AI_WRAPPER = `
import sys
sys.path.insert(0, ${JSON.stringify(REPO)})
from services.ai_pilot import web_server as ws
from services.ai_pilot import flight_controller as fcmod
Orig = ws.XPlaneUDPClient
class Seeded(Orig):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        for k2, v in {
            "sim/flightmodel/position/latitude": 32.93, "sim/flightmodel/position/longitude": -116.99,
            "sim/flightmodel/position/elevation": 1372.0, "sim/flightmodel/position/y_agl": 640.0,
            "sim/flightmodel/position/indicated_airspeed": 112.0, "sim/flightmodel/position/groundspeed": 58.0,
            "sim/flightmodel/position/mag_psi": 272.0, "sim/flightmodel/position/psi": 285.0,
            "sim/flightmodel/position/theta": 2.0, "sim/flightmodel/position/phi": -4.0,
            "sim/flightmodel/position/vh_ind_fpm": 120.0,
            "sim/cockpit2/engine/indicators/engine_speed_rpm[0]": 2400.0,
            "sim/cockpit2/engine/indicators/MPR_in_hg[0]": 21.5,
        }.items():
            self.set_mock_dref(k2, v)
ws.XPlaneUDPClient = Seeded
OrigFC = ws.FlightController
class FC(OrigFC):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.phase = fcmod.FlightPhase.CRUISE
ws.FlightController = FC
sys.argv = ["web_server", "--port", "${P.ai}"]
ws.main()
`;

async function startServers() {
  for (const [k, port] of Object.entries(P)) if (!(await portFree(port))) throw new Error(`port ${port} (${k}) is busy`);
  fs.mkdirSync(WORK, { recursive: true });
  const exData = path.join(WORK, 'exdb'); fs.rmSync(exData, { recursive: true, force: true }); fs.mkdirSync(exData, { recursive: true });
  const fpData = path.join(WORK, 'fpdata'); fs.mkdirSync(fpData, { recursive: true });
  fs.copyFileSync(path.join(REPO, 'services/flightplanner/data/aviation_data.db'), path.join(fpData, 'aviation_data.db'));
  start('exercise', VENV_PY, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(P.ex)],
    { CAPVSAR_DB: path.join(exData, 'exercise.db'), CAPVSAR_DEV_OPEN: '1', CAPVSAR_MUMBLE_HOST: 'voice.example.invalid' },
    path.join(REPO, 'services/exercise'));
  start('planner', VENV_PY, ['-c', `from app import app; app.run(host='127.0.0.1', port=${P.fp}, debug=False)`],
    { CAPVSAR_PLANNER_DATA: fpData, CAPVSAR_PRECACHE_CHARTS: '0', CAPVSAR_TILES_OFFLINE: '1', VSAR_CONSOLE_URL: EX },
    path.join(REPO, 'services/flightplanner'));
  start('ai-deck', VENV_PY, ['-c', AI_WRAPPER], {}, REPO);
  start('maneuver-deck', VENV_PY, ['-m', 'services.ai_pilot.maneuver_server', '--port', String(P.man)], {}, REPO);
  await waitFor(EX + '/api/state', 'exercise'); await waitFor(FP + '/', 'planner');
  await waitFor(AI + '/', 'ai deck'); await waitFor(MAN + '/', 'maneuver deck');
}

// ------------------------------------------------------------ exercise seed
const BEACON = { lat: 33.17, lon: -117.0792 };         // example scenario's hidden beacon (never shown until reveal)
const FLIGHTS = [
  { cs: 'CAP 423', lat: 33.10, lon: -117.30, hdg: 70, to: { lat: 33.19, lon: -117.10 }, alt: 4500 },
  { cs: 'CAP 415', lat: 33.31, lon: -117.22, hdg: 125, to: { lat: 33.16, lon: -117.06 }, alt: 5500 },
];
let feeder = null, lastDf = {};
function startFeeder() {
  const t0 = Date.now(), span = 110;                   // seconds to arrive; reports every second
  const tick = async () => {
    const f = Math.min(1, (Date.now() - t0) / 1000 / span);
    for (const a of FLIGHTS) {
      const lat = a.lat + (a.to.lat - a.lat) * f, lon = a.lon + (a.to.lon - a.lon) * f;
      const hdg = (Math.atan2((a.to.lon - a.lon) * Math.cos(33.1 * Math.PI / 180), a.to.lat - a.lat) * 180 / Math.PI + 360) % 360;
      try { const r = await jpost(EX + '/api/positions', { callsign: a.cs, lat, lon, alt_ft: a.alt, hdg_true: hdg, mock: true });
        if (r.json.df) lastDf[a.cs] = r.json.df; } catch (e) { /* sortie stopped */ }
    }
  };
  tick(); feeder = setInterval(tick, 1000);
}
async function seed(codes) {
  const sc = (await jget(EX + '/api/scenarios')).find(s => /Palomar ILS/.test(s.name));
  await jpost(EX + '/api/sorties', { scenario_id: sc.id });
  startFeeder();
}
async function logBearing(cs, errDeg) {
  const df = lastDf[cs]; if (!df || df.bearing_true == null) return false;
  await jpost(EX + '/api/bearings', { callsign: cs, bearing_true: ((df.bearing_true + errDeg) % 360 + 360) % 360, note: '' });
  return true;
}
async function seatCodes() {
  const s = await jget(EX + '/api/setup');
  const find = role => s.roster.find(r => r.role === role).code;
  return { instructor: find('instructor'), base: find('base') };
}
async function sessionCookie(code) {
  const r = await jpost(EX + '/api/auth/login', { code });
  const sc = r.headers.get('set-cookie') || '';
  return sc.match(/capvsar_session=([^;]+)/)[1];
}

// ------------------------------------------------------------------- scenes
const FAKE_RADIO = () => {
  const Real = window.WebSocket;
  window.__radioSockets = [];
  function Fake(url) {
    this.url = url; this.readyState = 0; this.l = {}; this.binaryType = 'arraybuffer';
    window.__radioSockets.push(this);
    setTimeout(() => { this.readyState = 1; this._emit('open', {}); }, 30);
  }
  Fake.prototype.addEventListener = function (t, f) { (this.l[t] = this.l[t] || []).push(f); };
  Fake.prototype._emit = function (t, e) { (this.l[t] || []).forEach(f => f(e)); };
  Fake.prototype._msg = function (o) { this._emit('message', { data: JSON.stringify(o) }); };
  Fake.prototype.send = function (d) {
    const m = JSON.parse(d);
    if (m.action === 'join') setTimeout(() => this._msg({ type: 'tuned', channel: m.channel, epoch: 1 }), 60);
    else if (m.action === 'ping') this._msg({ type: 'pong' });
  };
  Fake.prototype.close = function () { this.readyState = 3; };
  Object.assign(Fake, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 });
  window.WebSocket = function (u, p) { return String(u).includes('/api/radio/stream') ? new Fake(u) : new Real(u, p); };
  Object.assign(window.WebSocket, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 });
  window.__rx = (speaker, quality, pathKind, via) => {
    const s = window.__radioSockets[0];
    s._msg({ type: 'link', speaker, quality, path: pathKind, to_base: true, via_name: via || '' });
    s._msg({ type: 'rx', speaker });
  };
};

// Smooth scroll of the window or of one element over `ms` (an animated scroll the recording can show).
const SCROLL = (sel, to, ms) => new Promise(done => {
  const el = sel ? document.querySelector(sel) : (document.scrollingElement || document.documentElement);
  const from = el.scrollTop, t0 = performance.now();
  const step = now => { const k = Math.min(1, (now - t0) / ms), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    el.scrollTop = from + (to - from) * e; k < 1 ? requestAnimationFrame(step) : done(); };
  requestAnimationFrame(step);
});
const scroll = (p, sel, to, ms) => p.evaluate(`(${SCROLL.toString()})(${JSON.stringify(sel)}, ${to}, ${ms})`);

// Each scene: prep(page) runs before the mark (page load, sign-in, settle); act(page) runs on camera for ~SEG s.
const SCENES = [
  { id: 'setup', url: () => EX + '/setup', role: 'instructor',
    act: async p => { await sleep(1100); await p.click('text=Add aircraft, crew & staff').catch(() => {}); await sleep(1500); } },
  { id: 'ready', url: () => EX + '/ready', role: 'instructor',
    act: async p => { await sleep(500); await scroll(p, null, 130, 1800); await sleep(400); } },
  { id: 'planner', url: () => FP + '/', role: null,
    // (the planner's SAR dialog is left out: its default datum is the scenario's hidden beacon, and zoomed-in tiles are not cached offline)
    prep: async p => { await p.click('#disclaimer-ack'); await sleep(500); await p.click('#calc-btn'); await sleep(2500); },
    act: async p => { await sleep(700); await p.click('#btn-wb'); await sleep(700); await p.click('#calc-wb'); await sleep(1200); } },
  { id: 'console', url: () => EX + '/instructor', role: 'instructor', needSortie: true,
    prep: async p => { await sleep(1200); await p.evaluate(() => map.setView([33.19, -117.16], 11)); await sleep(1500); },
    act: async p => { await sleep(400); await scroll(p, 'aside', 330, 1200); await sleep(1100); } },
  // (no scrolling here: the deck redraws its attitude canvas at 5 Hz and a scroll recorded as tearing frames)
  { id: 'ai-deck', url: () => AI + '/', role: null, act: async () => { await sleep(SEG * 1000); } },
  { id: 'maneuvers', url: () => MAN + '/', role: null,
    act: async p => { await sleep(500); await p.type('input', 'heading 090 magnetic', { delay: 55 }); await sleep(900); } },
  { id: 'base', url: () => EX + '/base', role: 'base', needSortie: true,
    prep: async p => { await sleep(1200); await p.evaluate(() => map.setView([33.19, -117.16], 11)); await logBearing('CAP 423', 2); await sleep(1500); },
    act: async p => { await sleep(700); await logBearing('CAP 415', -3); await sleep(1900); } },
  { id: 'radio-text', url: () => EX + '/radio-legacy', role: 'base', needSortie: true,
    act: async p => { const ptt = await p.locator('#masterPttBtn').boundingBox();
      const hold = async ms => { await p.mouse.move(ptt.x + ptt.width / 2, ptt.y + ptt.height / 2); await p.mouse.down(); await sleep(ms); await p.mouse.up(); await p.mouse.move(1000, 640); };
      await sleep(300); await p.click('text=Radio Check'); await sleep(250); await hold(800); await sleep(350);
      await p.click('text=Copy Bearing'); await sleep(250); await hold(600); await sleep(150); } },
  { id: 'mission-radio', url: () => EX + '/radio', role: 'base', needSortie: true, fakeRadio: true,
    // the page is taller than the frame; scrolled so the status line, talk button and the top of the Form 110 log are in view
    prep: async p => { await p.click('#join'); await sleep(1500); await scroll(p, null, 1190, 10); await sleep(400); },
    act: async p => { await sleep(250); await p.evaluate(() => window.__rx('CAP 423', 'clear', 'direct', ''));
      await sleep(1250); await p.evaluate(() => window.__rx('CAP 415', 'weak', 'repeater', 'Julian')); await sleep(1200); } },
  { id: 'debrief', url: () => EX + '/debrief', role: 'instructor', afterStop: true,
    prep: async p => { await sleep(2500); },
    act: async p => { await sleep(500); await scroll(p, null, 360, 1900); await sleep(300); } },
];

async function recordScene(browser, sc, cookies) {
  const dir = path.join(WORK, 'raw', sc.id); fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1,
    recordVideo: { dir, size: { width: 1280, height: 720 } }, permissions: ['microphone'] });
  if (sc.role) await ctx.addCookies([{ name: 'capvsar_session', value: cookies[sc.role], domain: '127.0.0.1', path: '/', httpOnly: true, secure: true }]);
  const page = await ctx.newPage();
  const t0 = Date.now();   // the recording starts when the page is created
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/404/.test(m.text())) errors.push('console ' + m.text()); });
  if (sc.fakeRadio) await page.addInitScript(FAKE_RADIO);
  await page.goto(sc.url(), { waitUntil: 'load' });
  await sleep(1500);
  if (sc.prep) await sc.prep(page);
  const mark = (Date.now() - t0) / 1000;
  await sc.act(page);
  await sleep(300);
  await ctx.close();
  const vids = fs.readdirSync(dir).filter(f => f.endsWith('.webm'));
  fs.renameSync(path.join(dir, vids[0]), path.join(WORK, 'raw', sc.id + '.webm'));
  fs.writeFileSync(path.join(WORK, 'raw', sc.id + '.json'), JSON.stringify({ mark, errors }));
  console.log(`recorded ${sc.id} mark=${mark.toFixed(2)}s errors=${errors.length ? errors.join(' | ') : 'none'}`);
}

async function record() {
  await startServers();
  const browser = await chromium.launch({ channel: 'chrome', headless: true,
    args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--autoplay-policy=no-user-gesture-required'] });
  try {
    const codes = await seatCodes();
    const cookies = { instructor: await sessionCookie(codes.instructor), base: await sessionCookie(codes.base) };
    const list = SCENES.filter(s => !ONLY.length || ONLY.includes(s.id));
    let sortieOn = false;
    for (const sc of list) {
      if (sc.needSortie && !sortieOn) { await seed(codes); sortieOn = true; await sleep(14000); }
      if (sc.afterStop && sortieOn) {
        await sleep(15000);
        // give the debrief a bearing from each aircraft, then stop and reveal
        await logBearing('CAP 423', 4); await logBearing('CAP 415', -5);
        await jpost(EX + '/api/sorties/stop', {}); await jpost(EX + '/api/sorties/reveal', {});
        clearInterval(feeder); feeder = null; sortieOn = false; await sleep(500);
      }
      await recordScene(browser, sc, cookies);
    }
  } finally {
    if (feeder) clearInterval(feeder);
    await browser.close().catch(() => {});
    await stopAll();
  }
}

// ------------------------------------------------------------------- encode
function ff(argv) {
  const r = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', ...argv], { stdio: 'inherit' });
  if (r.status !== 0) throw new Error('ffmpeg failed: ' + argv.join(' '));
}
function encode() {
  const ids = SCENES.map(s => s.id);
  const segs = [];
  for (const id of ids) {
    const meta = JSON.parse(fs.readFileSync(path.join(WORK, 'raw', id + '.json'), 'utf8'));
    const out = path.join(WORK, 'seg-' + id + '.mp4');
    // the recording starts when the page is created, a hair before the clock for `mark` was taken
    ff(['-ss', (meta.mark + 0.05).toFixed(2), '-t', String(SEG), '-i', path.join(WORK, 'raw', id + '.webm'), '-an',
      '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p',
      '-c:v', 'libx264', '-crf', '14', '-preset', 'slow', out]);
    segs.push(out);
  }
  // cross-fade chain
  const inputs = segs.flatMap(s => ['-i', s]);
  let f = '', prev = '[0:v]', off = 0;
  for (let i = 1; i < segs.length; i++) {
    off += SEG - FADE;
    const out = i === segs.length - 1 ? '[chain]' : `[x${i}]`;
    f += `${prev}[${i}:v]xfade=transition=fade:duration=${FADE}:offset=${off.toFixed(3)}${out};`;
    prev = out;
  }
  f = f.replace(/;$/, '');
  const chain = path.join(WORK, 'chain.mp4');
  ff([...inputs, '-filter_complex', f, '-map', '[chain]', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '14', '-preset', 'slow', chain]);
  const L = segs.length * SEG - (segs.length - 1) * FADE;      // chain length
  // seamless loop: cross-dissolve the last 0.3 s into the first 0.3 s (VIDEO_PLAN step 2)
  const loop = path.join(WORK, 'web-panels-loop.mp4');
  ff(['-i', chain, '-filter_complex',
    `[0:v]split[a][b];[a]trim=0:${(L - 0.3).toFixed(3)},setpts=PTS-STARTPTS[head];[b]trim=${(L - 0.3).toFixed(3)},setpts=PTS-STARTPTS[tail];` +
    `[head][tail]xfade=transition=fade:duration=0.3:offset=${(L - 0.6).toFixed(3)}[v]`,
    '-map', '[v]', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '14', loop]);
  const webm = path.join(SITE_VIDEO, 'web-panels.webm'), mp4 = path.join(SITE_VIDEO, 'web-panels.mp4');
  const poster = path.join(SITE_VIDEO, 'web-panels-poster.webp');
  const pass = path.join(WORK, 'vp9pass');
  ff(['-i', loop, '-an', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuv420p', '-b:v', '0', '-crf', '48', '-row-mt', '1', '-pass', '1', '-passlogfile', pass, '-f', 'null', '/dev/null']);
  ff(['-i', loop, '-an', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuv420p', '-b:v', '0', '-crf', '48', '-row-mt', '1', '-pass', '2', '-passlogfile', pass, webm]);
  ff(['-i', loop, '-an', '-c:v', 'libx264', '-crf', '30', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', mp4]);
  const posterId = process.env.POSTER_SCENE || 'planner';   // the planned route, before the W&B dialog opens
  const posterT = process.env.POSTER_AT || (ids.indexOf(posterId) * (SEG - FADE) + 0.4).toFixed(2);
  ff(['-ss', posterT, '-i', loop, '-frames:v', '1', '-c:v', 'libwebp', '-quality', '80', poster]);
  console.log(`clip length ${(L - 0.3).toFixed(2)} s; poster from ${posterId} at ${posterT} s`);
}

(async () => {
  try {
    if (DO_RECORD) await record();
    if (DO_ENCODE) encode();
  } catch (e) { console.error(e); await stopAll(); process.exitCode = 1; }
})();
