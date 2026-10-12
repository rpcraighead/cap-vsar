// CAP V-SAR charts: inline SVG, no library and no network (a mission base often
// has no internet, and nothing here may come from a CDN).
//
// The first chart is the debrief's bearing error over time. It follows the
// dataviz method D6 adopted (docs/DECISIONS_2026-10-11.md):
//   * one series per aircraft, in fixed slot order; aircraft N wears --ac-N
//     through the .viz-sN classes in debrief.css, never a literal, so
//     data-theme="light" swaps in the light steps (validated separately
//     against the light surface) without a redraw;
//   * 2 px lines, >= 8 px markers with a 2 px surface ring, hairline solid
//     grid, one y axis;
//   * a legend always, direct labels at the line ends (leader lines when they
//     would collide), a crosshair tooltip listing every series, keyboard
//     focus showing the same, and a table view as the accessible twin;
//   * text wears text tokens; the coloured mark beside it carries identity.
// Callsigns and notes come from the server: they reach the DOM through
// textContent and setAttribute only, never as markup.

// BEGIN VIZ PURE
// Symmetric error axis: the smallest of these that holds the data, with its
// tick step. Degrees, so the steps are the ones a navigator counts in.
const VIZ_ERR_STEPS = [[10, 5], [20, 10], [30, 10], [45, 15], [60, 30], [90, 45], [120, 60], [180, 90]];

function vizErrorDomain(maxAbs) {
  const m = Math.min(Math.abs(Number(maxAbs) || 0), 180);
  const [max, step] = VIZ_ERR_STEPS.find(([cap]) => m <= cap) || VIZ_ERR_STEPS[VIZ_ERR_STEPS.length - 1];
  const ticks = [];
  for (let v = -max; v <= max + 1e-9; v += step) ticks.push(v);
  return {max, ticks};
}

// The scale is set by the bulk of the readings, not the wildest one: a
// handful of cone-of-confusion readings at +/-150 would otherwise flatten the
// +/-10 degrees a debrief is about. q-quantile of `values` (0 when empty).
function vizQuantile(values, q) {
  if (!values.length) return 0;
  const v = values.slice().sort((a, b) => a - b);
  return v[Math.min(v.length - 1, Math.max(0, Math.ceil(q * v.length) - 1))];
}

// Elapsed-time ticks (seconds from the start of the replay), on round steps.
const VIZ_TIME_STEPS = [10, 15, 30, 60, 120, 300, 600, 900, 1200, 1800, 3600, 7200, 14400];

function vizTimeStep(span, maxTicks) {
  return VIZ_TIME_STEPS.find(s => span / s <= maxTicks) || VIZ_TIME_STEPS[VIZ_TIME_STEPS.length - 1];
}

function vizTimeTicks(span, maxTicks) {
  const step = vizTimeStep(span, Math.max(1, maxTicks));
  const out = [];
  for (let s = 0; s <= span + 1e-9; s += step) out.push(s);
  return out;
}

const vizScale = (d0, d1, r0, r1) => {
  const k = (r1 - r0) / ((d1 - d0) || 1);
  const f = v => r0 + (v - d0) * k;
  f.invert = r => d0 + (r - r0) / k;
  return f;
};

// The gap past which a line breaks rather than bridging: five typical sample
// intervals, never under 15 s. A receiver that lost the signal for a minute
// should show a minute of nothing, not a straight line across it.
function vizGap(points) {
  const dts = [];
  for (let i = 1; i < points.length; i++) dts.push(points[i].t - points[i - 1].t);
  if (!dts.length) return 15;
  dts.sort((a, b) => a - b);
  return Math.max(15, 5 * dts[Math.floor(dts.length / 2)]);
}

// Split a series into drawable runs: at a time gap, and where the error wraps
// through +/-180 (a needle at 179 then -179 is two degrees apart, not 358).
function vizRuns(points, gap) {
  const runs = [];
  let run = [];
  points.forEach((p, i) => {
    const prev = points[i - 1];
    if (prev && (p.t - prev.t > gap || Math.abs(p.v - prev.v) > 180)) { runs.push(run); run = []; }
    run.push(p);
  });
  if (run.length) runs.push(run);
  return runs;
}

// Index of the point nearest time t in a time-sorted array, or -1.
function vizNearest(points, t) {
  if (!points.length) return -1;
  let lo = 0, hi = points.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (points[mid].t <= t) lo = mid; else hi = mid;
  }
  return Math.abs(points[lo].t - t) <= Math.abs(points[hi].t - t) ? lo : hi;
}

// Direct-label positions: keep the order, at least `gap` apart, inside
// [lo, hi]. Returns the new positions in the input's order.
function vizSpread(ys, gap, lo, hi) {
  const idx = ys.map((y, i) => i).sort((a, b) => ys[a] - ys[b]);
  const out = ys.slice();
  let prev = -Infinity;
  for (const i of idx) { out[i] = Math.max(Math.min(Math.max(ys[i], lo), hi), prev + gap); prev = out[i]; }
  let next = Infinity;
  for (let k = idx.length - 1; k >= 0; k--) {
    const i = idx[k];
    out[i] = Math.min(out[i], hi, next - gap);
    next = out[i];
  }
  return out;
}

// "+4.2°", "−3.0°" (a real minus sign), "0.0°".
function vizSigned(v, digits) {
  const d = digits == null ? 1 : digits;
  const s = Math.abs(v).toFixed(d);
  if (Number(s) === 0) return (0).toFixed(d) + '°';
  return (v > 0 ? '+' : '−') + s + '°';
}

function vizClip(text, n) {
  const s = String(text == null ? '' : text);
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}
// END VIZ PURE

const VIZ_SVG = 'http://www.w3.org/2000/svg';

function vizSvg(tag, attrs, text) {
  const n = document.createElementNS(VIZ_SVG, tag);
  for (const k in attrs || {}) n.setAttribute(k, attrs[k]);
  if (text != null) n.textContent = text;
  return n;
}

function vizHtml(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

const vizSlotClass = slot => 'viz-s' + (slot >= 1 && slot <= 4 ? slot : 0);

// The bearing-error chart.
//
// spec = {
//   x0, x1,                   time domain, epoch seconds (the replay's span)
//   fmtT: t => '12:40',       how a time is written (elapsed replay clock)
//   series: [{label, slot, line: [{t, v, flag?}], dots: [{t, v, detail}]}],
//                             a flagged reading (in the cone) does not set the scale
//   band: 10,                 the +/- "good cut" band, degrees
//   note: '...',              one line under the legend (active effects)
//   empty: '...',             when set, the figure says this instead of plotting
//   onSeek: t => {},          click / Enter on the plot
//   height: 260,
// }
// Returns {figure, setCursor(t), showTable(bool)}.
function vizErrorChart(host, spec) {
  const fig = vizHtml('figure', 'viz');
  const head = vizHtml('div', 'viz-head');
  const legend = vizHtml('ul', 'viz-legend');
  const toggle = vizHtml('button', 'btn viz-toggle', 'Table view');
  toggle.type = 'button';
  toggle.setAttribute('aria-pressed', 'false');
  head.append(legend, toggle);
  const plot = vizHtml('div', 'viz-plot');
  const tip = vizHtml('div', 'viz-tip');
  tip.hidden = true;
  tip.setAttribute('role', 'status');
  const table = vizHtml('div', 'viz-table');
  table.hidden = true;
  const note = vizHtml('p', 'viz-note', spec.note || '');
  note.hidden = !spec.note;
  const offNote = vizHtml('p', 'viz-note');
  offNote.hidden = true;
  fig.append(head, note, offNote, plot, table);
  host.replaceChildren(fig);

  if (spec.empty) {
    head.hidden = true;
    plot.append(vizHtml('p', 'viz-empty', spec.empty));
    return {figure: fig, setCursor() {}, showTable() {}};
  }

  const series = spec.series.map(s => ({...s, line: s.line || [], dots: s.dots || []}));
  series.forEach(s => { s.gap = vizGap(s.line); });
  const fmtT = spec.fmtT || (t => String(Math.round(t - spec.x0)));
  const band = spec.band == null ? 10 : spec.band;

  // One symmetric scale for every series: the 98th percentile of the readings
  // that are not flagged, never tighter than twice the good-cut band. What
  // lies beyond runs off the plot (lines are clipped, logged bearings are
  // pinned to the edge as arrows) and the note says how many.
  const scaleVals = [];
  series.forEach(s => {
    s.line.forEach(p => { if (!p.flag) scaleVals.push(Math.abs(p.v)); });
    s.dots.forEach(p => scaleVals.push(Math.abs(p.v)));
  });
  const dom = vizErrorDomain(Math.max(band * 2, vizQuantile(scaleVals, 0.98)));
  let off = 0, all = 0;
  series.forEach(s => s.line.concat(s.dots).forEach(p => { all++; if (Math.abs(p.v) > dom.max) off++; }));
  if (off) {
    offNote.textContent = `${off} of ${all} readings lie beyond \u00b1${dom.max}\u00b0 and run off the scale; ` +
      'the readout and the table view give their values.';
    offNote.hidden = false;
  }
  const clipId = 'viz-clip-' + (vizErrorChart.count = (vizErrorChart.count || 0) + 1);

  // ---- legend: series in slot order, then the reference marks
  const key = (cls, text) => {
    const li = vizHtml('li');
    li.append(vizHtml('span', cls), document.createTextNode(text));
    legend.append(li);
  };
  series.forEach(s => key('viz-key-line ' + vizSlotClass(s.slot), s.label));
  if (series.some(s => s.dots.length)) key('viz-key-dot', 'logged bearing');
  key('viz-key-band', '±' + band + '° good cut');
  key('viz-key-zero', 'true bearing (0°)');

  let cursorT = null, focusT = null, W = 0, geo = null, svg = null;

  function draw() {
    W = Math.max(320, Math.round(host.clientWidth || plot.clientWidth || 720));
    const H = spec.height || 260;
    const narrow = W < 560;                          // a phone: a slimmer label gutter
    const m = {l: 48, r: narrow ? 76 : 104, t: 10, b: 28};
    const px0 = m.l, px1 = W - m.r, py0 = m.t, py1 = H - m.b;
    const x = vizScale(spec.x0, spec.x1, px0, px1);
    const y = vizScale(-dom.max, dom.max, py1, py0);
    geo = {x, y, px0, px1, py0, py1, W, H};

    svg = vizSvg('svg', {class: 'viz-svg', width: W, height: H, viewBox: `0 0 ${W} ${H}`,
      role: 'img', tabindex: '0',
      'aria-label': `Bearing error over time, ${series.length} aircraft. ` +
        'Arrow keys move the readout, Enter jumps the replay there; the table view lists every value.'});
    const g = cls => { const n = vizSvg('g', {class: cls}); svg.append(n); return n; };
    const defs = vizSvg('defs'), clip = vizSvg('clipPath', {id: clipId});
    clip.append(vizSvg('rect', {x: px0, y: py0 - 2, width: px1 - px0, height: py1 - py0 + 4}));
    defs.append(clip);
    svg.append(defs);
    const yc = v => y(Math.max(-dom.max, Math.min(dom.max, v)));   // pinned to the plot

    // grid and axes: hairline, solid, recessive
    const grid = g('viz-grid');
    const ticks = g('viz-ticks');
    dom.ticks.forEach(v => {
      if (v !== 0) grid.append(vizSvg('line', {x1: px0, x2: px1, y1: y(v), y2: y(v)}));
      ticks.append(vizSvg('text', {x: px0 - 8, y: y(v), 'text-anchor': 'end', 'dominant-baseline': 'middle'},
        vizSigned(v, 0)));
    });
    const span = spec.x1 - spec.x0;
    const xt = vizTimeTicks(span, Math.max(2, Math.floor((px1 - px0) / 80)));
    xt.forEach(s => {
      ticks.append(vizSvg('text', {x: x(spec.x0 + s), y: py1 + 18, 'text-anchor': 'middle'}, fmtT(spec.x0 + s)));
    });
    grid.append(vizSvg('line', {x1: px0, x2: px0, y1: py0, y2: py1}));

    // the good-cut band and the truth line behind the data
    svg.append(vizSvg('rect', {class: 'viz-band', x: px0, width: px1 - px0, y: y(band), height: y(-band) - y(band)}));
    svg.append(vizSvg('line', {class: 'viz-zero', x1: px0, x2: px1, y1: y(0), y2: y(0)}));

    // The replay position: a line with a head, so it is not mistaken for the crosshair.
    const replay = vizSvg('g', {class: 'viz-replay'});
    replay.append(vizSvg('line', {x1: 0, x2: 0, y1: py0, y2: py1}),
                  vizSvg('path', {d: `M-5 ${py0 - 7} h10 l-5 7 Z`}));
    replay.style.display = 'none';
    svg.append(replay);
    geo.replay = replay;

    // lines, then logged bearings on top
    const lines = g('viz-lines');
    lines.setAttribute('clip-path', `url(#${clipId})`);
    series.forEach(s => {
      vizRuns(s.line, s.gap).forEach(run => {
        const d = run.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)} ${y(p.v).toFixed(1)}`).join(' ');
        lines.append(vizSvg('path', {class: 'viz-line ' + vizSlotClass(s.slot),
          d: run.length === 1 ? d + ' l0.01 0' : d}));
      });
    });
    const dots = g('viz-dots');
    series.forEach(s => s.dots.forEach(p => {
      const cx = x(p.t), cy = y(p.v), r = 5;
      const d = Math.abs(p.v) <= dom.max
        ? `M${cx.toFixed(1)} ${(cy - r).toFixed(1)} l${r} ${r} l${-r} ${r} l${-r} ${-r} Z`
        : p.v > 0 ? `M${cx.toFixed(1)} ${py0 - 2} l5 9 h-10 Z`          // off the top: an arrow up
                  : `M${cx.toFixed(1)} ${py1 + 2} l5 -9 h-10 Z`;        // off the bottom: an arrow down
      dots.append(vizSvg('path', {class: 'viz-dot ' + vizSlotClass(s.slot), d}));
    }));

    // end dots and direct labels in the right gutter, leader lines when nudged
    const labels = g('viz-labels');
    const ends = series.map(s => {
      const pts = s.line.length ? s.line : s.dots;
      if (!pts.length) return null;
      const p = pts[pts.length - 1];
      return {s, x: x(p.t), y: yc(p.v), dot: !!s.line.length};
    }).filter(Boolean);
    const placed = vizSpread(ends.map(e => e.y), 16, py0 + 6, py1 - 6);
    ends.forEach((e, i) => {
      if (e.dot) labels.append(vizSvg('circle', {class: 'viz-end ' + vizSlotClass(e.s.slot), cx: e.x, cy: e.y, r: 4}));
      const ly = placed[i];
      // A leader only from a line that ends near the right edge: one drawn
      // across the plot from an aircraft that stopped reporting early would
      // read as a reference line. That label is matched by the legend.
      if (e.x >= px1 - 40 && (Math.abs(ly - e.y) > 2 || e.x < px1 - 8)) {
        labels.append(vizSvg('polyline', {class: 'viz-leader',
          points: `${(e.x + 6).toFixed(1)},${e.y.toFixed(1)} ${px1 + 4},${e.y.toFixed(1)} ${px1 + 12},${ly.toFixed(1)}`}));
      }
      labels.append(vizSvg('text', {class: 'viz-label', x: px1 + 16, y: ly, 'dominant-baseline': 'middle'},
        vizClip(e.s.label, narrow ? 8 : 11)));
    });

    // the hover layer: crosshair, one dot per series, a hit area the size of the plot
    const cross = vizSvg('line', {class: 'viz-cross', y1: py0, y2: py1});
    cross.style.display = 'none';
    svg.append(cross);
    const hover = series.map(s => {
      const c = vizSvg('circle', {class: 'viz-hover ' + vizSlotClass(s.slot), r: 4});
      c.style.display = 'none';
      svg.append(c);
      return c;
    });
    svg.append(vizSvg('rect', {class: 'viz-hit', x: px0, y: py0, width: px1 - px0, height: py1 - py0}));
    geo.cross = cross;
    geo.hover = hover;
    geo.yc = yc;

    svg.addEventListener('pointermove', ev => show(timeAt(ev.clientX)));
    svg.addEventListener('pointerleave', () => { if (document.activeElement !== svg) hide(); });
    svg.addEventListener('click', ev => {
      const t = snap(timeAt(ev.clientX));
      if (t != null && spec.onSeek) spec.onSeek(t);
    });
    svg.addEventListener('focus', () => show(focusT != null ? focusT : (cursorT != null ? cursorT : spec.x0)));
    svg.addEventListener('blur', hide);
    svg.addEventListener('keydown', ev => {
      const stepT = (spec.x1 - spec.x0) / 100;
      const now = focusT != null ? focusT : spec.x0;
      const to = {ArrowRight: now + stepT, ArrowLeft: now - stepT, Home: spec.x0, End: spec.x1}[ev.key];
      if (to != null) { ev.preventDefault(); show(Math.max(spec.x0, Math.min(spec.x1, to))); }
      else if (ev.key === 'Enter' && focusT != null && spec.onSeek) { ev.preventDefault(); spec.onSeek(focusT); }
    });

    plot.replaceChildren(svg, tip);
    setCursor(cursorT);
  }

  function timeAt(clientX) {
    const r = svg.getBoundingClientRect();
    const px = (clientX - r.left) * (geo.W / (r.width || geo.W));
    return Math.max(spec.x0, Math.min(spec.x1, geo.x.invert(px)));
  }

  // The crosshair snaps to the nearest recorded sample of any series.
  function snap(t) {
    let best = null;
    series.forEach(s => [s.line, s.dots].forEach(pts => {
      const i = vizNearest(pts, t);
      if (i >= 0 && (best == null || Math.abs(pts[i].t - t) < Math.abs(best - t))) best = pts[i].t;
    }));
    return best;
  }

  function show(t) {
    const at = snap(t);
    if (at == null) return;
    focusT = at;
    const {x, y} = geo;
    const cx = x(at);
    geo.cross.setAttribute('x1', cx); geo.cross.setAttribute('x2', cx);
    geo.cross.style.display = '';
    const dotTol = (spec.x1 - spec.x0) * 8 / Math.max(1, geo.px1 - geo.px0);   // ~8 px either side
    const rows = [];
    series.forEach((s, k) => {
      const i = vizNearest(s.line, at);
      const p = i >= 0 && Math.abs(s.line[i].t - at) <= s.gap ? s.line[i] : null;
      const j = vizNearest(s.dots, at);
      const d = j >= 0 && Math.abs(s.dots[j].t - at) <= dotTol ? s.dots[j] : null;
      const c = geo.hover[k];
      if (p) { c.setAttribute('cx', x(p.t)); c.setAttribute('cy', geo.yc(p.v)); c.style.display = ''; }
      else c.style.display = 'none';
      rows.push({s, p, d});
    });

    const frag = [vizHtml('div', 'viz-tip-time', fmtT(at))];
    rows.forEach(({s, p, d}) => {
      const row = vizHtml('div', 'viz-tip-row');
      row.append(vizHtml('span', 'viz-key-line ' + vizSlotClass(s.slot)),
        vizHtml('b', null, p ? vizSigned(p.v) : '—'),
        vizHtml('span', 'viz-tip-label', s.label + (p && p.flag ? ' · ' + p.flag : '') + (p ? '' : ' · no reading')));
      frag.push(row);
      if (d) {
        const sub = vizHtml('div', 'viz-tip-row');
        sub.append(vizHtml('span', 'viz-key-dot'), vizHtml('b', null, vizSigned(d.v)),
          vizHtml('span', 'viz-tip-label', 'logged' + (d.detail ? ' · ' + d.detail : '')));
        frag.push(sub);
      }
    });
    tip.replaceChildren(...frag);
    tip.hidden = false;
    const left = cx + 14;
    tip.style.left = (left + 230 > geo.W ? Math.max(0, cx - 244) : left) + 'px';
    tip.style.top = geo.py0 + 'px';
  }

  function hide() {
    if (!geo) return;
    geo.cross.style.display = 'none';
    geo.hover.forEach(c => { c.style.display = 'none'; });
    tip.hidden = true;
  }

  function setCursor(t) {
    cursorT = t;
    if (!geo || !geo.replay) return;
    if (t == null) { geo.replay.style.display = 'none'; return; }
    const cx = geo.x(Math.max(spec.x0, Math.min(spec.x1, t)));
    geo.replay.setAttribute('transform', `translate(${cx.toFixed(1)} 0)`);
    geo.replay.style.display = '';
  }

  // ---- the table view: the same numbers without the picture
  function buildTable() {
    const span = spec.x1 - spec.x0;
    const step = vizTimeStep(span, 120);
    const t1 = vizHtml('table', 'viz-data');
    t1.append(vizHtml('caption', null, `Needle error, sampled every ${fmtStep(step)}`));
    const hr = vizHtml('tr');
    hr.append(vizHtml('th', null, 'Time'));
    series.forEach(s => hr.append(vizHtml('th', null, s.label)));
    const thead = vizHtml('thead'); thead.append(hr);
    const tbody = vizHtml('tbody');
    for (let o = 0; o <= span + 1e-9; o += step) {
      const t = spec.x0 + o;
      const tr = vizHtml('tr');
      tr.append(vizHtml('td', null, fmtT(t)));
      series.forEach(s => {
        const i = vizNearest(s.line, t);
        const p = i >= 0 && Math.abs(s.line[i].t - t) <= step / 2 ? s.line[i] : null;
        tr.append(vizHtml('td', null, p ? vizSigned(p.v) : '—'));
      });
      tbody.append(tr);
    }
    t1.append(thead, tbody);

    const logged = [];
    series.forEach(s => s.dots.forEach(d => logged.push({s, d})));
    logged.sort((a, b) => a.d.t - b.d.t);
    const t2 = vizHtml('table', 'viz-data');
    t2.append(vizHtml('caption', null, 'Logged bearings'));
    const h2 = vizHtml('tr');
    ['Time', 'Aircraft', 'Error', 'Logged'].forEach(h => h2.append(vizHtml('th', null, h)));
    const thead2 = vizHtml('thead'); thead2.append(h2);
    const tbody2 = vizHtml('tbody');
    logged.forEach(({s, d}) => {
      const tr = vizHtml('tr');
      [fmtT(d.t), s.label, vizSigned(d.v), d.detail || ''].forEach(v => tr.append(vizHtml('td', null, v)));
      tbody2.append(tr);
    });
    if (!logged.length) {
      const tr = vizHtml('tr'), td = vizHtml('td', null, 'No bearings were logged.');
      td.setAttribute('colspan', '4'); tr.append(td); tbody2.append(tr);
    }
    t2.append(thead2, tbody2);
    table.replaceChildren(t1, t2);
  }

  function fmtStep(s) { return s < 60 ? `${s} s` : `${s / 60} min`; }

  function showTable(on) {
    if (on && !table.firstChild) buildTable();
    table.hidden = !on;
    plot.hidden = on;
    toggle.textContent = on ? 'Chart view' : 'Table view';
    toggle.setAttribute('aria-pressed', on ? 'true' : 'false');
  }
  toggle.addEventListener('click', () => showTable(table.hidden));

  draw();
  if (typeof ResizeObserver === 'function') {
    let last = W;
    new ResizeObserver(() => {
      const w = Math.round(host.clientWidth || 0);
      if (w && Math.abs(w - last) > 4 && fig.isConnected !== false) { last = w; draw(); }
    }).observe(host);
  }
  return {figure: fig, setCursor, showTable};
}
