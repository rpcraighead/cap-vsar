"""Reduce a climb trace to a card result: steadiest 30-second window.

Read-only. Takes a JSONL trace from scripts/capture_flight_test.py and reports
the achieved climb rate with the ALTITUDE BAND it was measured in, because the
card's targets are sea-level figures and a climb rate without its altitude is
not a result.

Reports the raw measurement, never only a corrected one. On B1 run 2 the raw
figure missed by 13.4% and the sea-level extrapolation by 10.7%, so the verdict
did not depend on the correction - but a reader has to be able to see that for
themselves.

The card says "use a 30-second average rather than a peak" and the target is a
SEA LEVEL figure, so the window's altitude band is reported with the number -
a climb rate without the altitude it was measured at is not a result.
"""
import json, statistics, sys
from pathlib import Path

path = Path(sys.argv[1])
rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
def f(r, k):
    v = r.get(k)
    return v if isinstance(v, (int, float)) else None

rows = [r for r in rows if f(r, "vs_fpm") is not None and f(r, "kias") is not None]
if not rows:
    print("no usable samples"); raise SystemExit(2)
t0 = rows[0]["t"]
for r in rows: r["_t"] = r["t"] - t0

WINDOW = 30.0
best = None
for i, start in enumerate(rows):
    win = [r for r in rows if start["_t"] <= r["_t"] <= start["_t"] + WINDOW]
    if len(win) < 100 or win[-1]["_t"] - win[0]["_t"] < WINDOW * 0.95:
        continue
    vs = [f(r, "vs_fpm") for r in win]
    kias = [f(r, "kias") for r in win]
    spread = max(vs) - min(vs)
    # Prefer the steadiest window; among steady ones prefer the lowest, since
    # the target is at sea level.
    score = spread + win[0]["alt_msl_ft"] * 0.02
    if best is None or score < best[0]:
        best = (score, win, vs, kias)

score, win, vs, kias = best
alt = [f(r, "alt_msl_ft") for r in win]
print("B1 reduction from %s" % path.name)
print("  window       t %.1f..%.1f s, %d samples" % (win[0]["_t"], win[-1]["_t"], len(win)))
print("  altitude     %.0f..%.0f ft MSL (mean %.0f)" % (min(alt), max(alt), statistics.fmean(alt)))
print("  KIAS         mean %.1f  (Vy target 80.0)" % statistics.fmean(kias))
print("  CLIMB RATE   mean %.0f fpm   spread %.0f" % (statistics.fmean(vs), max(vs)-min(vs)))
target, tol = 924.0, 0.10
got = statistics.fmean(vs)
lo, hi = target*(1-tol), target*(1+tol)
print("  target       %.0f fpm +/-%.0f%%  =  %.0f..%.0f" % (target, tol*100, lo, hi))
print("  error        %+.0f fpm  (%+.1f%%)" % (got-target, 100*(got-target)/target))
print("  VERDICT      %s" % ("PASS" if lo <= got <= hi else "MISS"))
print()
print("  NOTE: measured at %.0f ft mean, not sea level. The rate decays with" % statistics.fmean(alt))
print("  altitude, so the true sea-level figure is HIGHER than this.")
