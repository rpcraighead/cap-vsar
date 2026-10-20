"""A measured performance table: what throttle an airspeed and climb rate need.

The AI pilot's cruise law was a speed-on-throttle loop around one fixed "cruise" power. That is right in
level cruise and wrong anywhere else: handed a fast, climbing airplane it cut the power to idle and fell 30
knots below its target (ESCON runs 4 and 5, 2026-10-15). What it lacks is feed-forward: the throttle the
airplane needs for the speed and vertical speed being asked for. This table is that, measured, per aircraft.

It is measured with the aircraft's own autopilot holding a vertical speed at a fixed throttle
(`scripts/perf_table_sweep.py`): the airspeed that settles is the dependent variable. Each point is
(throttle, vertical speed fpm, settled KIAS) with the prop full forward, which is how the AI pilot flies
except in level cruise. The table is only valid for what it was measured on, so it carries the aircraft-file
hash, the loading and the altitude, and a controller can see how far it is from them.

`throttle_for(kias, vvi_fpm)` inverts the map. For each measured vertical speed it interpolates throttle
against airspeed, then interpolates between vertical speeds. Outside the measured range it holds the
nearest measured throttle and says so (`in_range` False); it never extrapolates a trend it did not measure.
It is a first-order model: the integrator in the control law removes whatever it gets wrong.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

CLIMB_MARGIN = .85            # fraction of the best sustainable climb rate a controller will ask for
MIN_ROWS = 3                  # vertical speeds
# A row needs two measured throttle settings to interpolate between. The climb row nearest an airplane's
# limit legitimately has only two: below them the climb runs out of airspeed (the C172's +400 fpm row,
# 2026-10-15). The table as a whole must still be a real map (MIN_ROWS rows, one of them well measured).
MIN_POINTS_PER_ROW = 2
MIN_POINTS_BEST_ROW = 3
MAX_SPEED_INVERSION_KT = 1.5  # airspeed may not fall with throttle by more than measurement noise


class PerformanceError(ValueError):
    pass


@dataclass(frozen=True)
class PerformanceTable:
    acf_sha256: str
    altitude_ft: float
    mass_kg: float
    conditions: str
    evidence: str
    points: tuple   # ((throttle, vvi_fpm, kias), ...)

    def __post_init__(self):
        if (not isinstance(self.acf_sha256, str) or len(self.acf_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.acf_sha256)):
            raise PerformanceError("performance table needs the SHA-256 of the aircraft file it was measured on")
        for name in ("altitude_ft", "mass_kg"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise PerformanceError("performance %s must be positive" % name)
        if not self.conditions.strip() or not self.evidence.strip():
            raise PerformanceError("performance table must state its conditions and its evidence")
        rows = self.rows()
        if len(rows) < MIN_ROWS:
            raise PerformanceError("performance table needs at least %d vertical speeds" % MIN_ROWS)
        if max(len(row) for row in rows.values()) < MIN_POINTS_BEST_ROW:
            raise PerformanceError("no vertical speed has %d throttle points; the table is too thin to be a map"
                                   % MIN_POINTS_BEST_ROW)
        for vvi, row in rows.items():
            if len(row) < MIN_POINTS_PER_ROW:
                raise PerformanceError("vertical speed %+.0f fpm has %d throttle points; needs %d"
                                       % (vvi, len(row), MIN_POINTS_PER_ROW))
            throttles = [t for t, _ in row]
            if len(set(throttles)) != len(throttles):
                raise PerformanceError("duplicate throttle at %+.0f fpm" % vvi)
            for (_, k0), (_, k1) in zip(row, row[1:]):
                if k1 < k0 - MAX_SPEED_INVERSION_KT:
                    raise PerformanceError("airspeed falls as throttle rises at %+.0f fpm (%.1f then %.1f KIAS)"
                                           % (vvi, k0, k1))
        for t, v, k in self.points:
            if not (0. <= t <= 1. and math.isfinite(v) and 20. <= k <= 250.):
                raise PerformanceError("point (%r, %r, %r) is outside throttle 0-1 / 20-250 KIAS" % (t, v, k))

    def rows(self):
        """{vertical speed: [(throttle, kias), ...] sorted by throttle}."""
        rows = {}
        for t, v, k in self.points:
            rows.setdefault(float(v), []).append((float(t), float(k)))
        return {v: sorted(row) for v, row in sorted(rows.items())}

    def _row_throttle(self, row, kias):
        """Interpolate throttle against airspeed on one row; clamp (and report) outside it."""
        if kias <= row[0][1]:
            return row[0][0], kias >= row[0][1] - 1e-9
        if kias >= row[-1][1]:
            return row[-1][0], kias <= row[-1][1] + 1e-9
        for (t0, k0), (t1, k1) in zip(row, row[1:]):
            if k0 <= kias <= k1:
                if k1 - k0 < 1e-9:
                    return (t0 + t1) / 2, True
                return t0 + (t1 - t0) * (kias - k0) / (k1 - k0), True
        return row[-1][0], False

    def sustainable_vvi(self, kias: float):
        """The best climb rate (fpm) the airplane holds at `kias` with full throttle, from the table.

        Only rows measured at (nearly) full throttle count. The answer never exceeds the highest climb
        rate measured and never goes below the lowest such row: the table does not extrapolate. If even
        the lowest row cannot hold `kias` at full throttle, that lowest row's rate is returned, which for a
        table with a level row means "level flight at best". Returns None if no row reached full throttle.
        """
        candidates = []
        for vvi, row in self.rows().items():
            top_throttle, top_kias = row[-1]
            if top_throttle >= 0.95:
                candidates.append((vvi, top_kias))
        if not candidates:
            return None
        candidates.sort()                                  # ascending climb rate; top speed falls as it rises
        if kias <= candidates[-1][1]:
            return candidates[-1][0]
        if kias >= candidates[0][1]:
            return candidates[0][0]
        for (v0, k0), (v1, k1) in zip(candidates, candidates[1:]):
            if k1 <= kias <= k0:
                return v0 + (v1 - v0) * (k0 - kias) / (k0 - k1) if k0 > k1 else v1
        return candidates[0][0]

    def throttle_for(self, kias: float, vvi_fpm: float):
        """(throttle, in_range): the throttle that holds `kias` at `vvi_fpm` in the measured airplane."""
        rows = self.rows()
        speeds = list(rows)
        vvi = min(max(vvi_fpm, speeds[0]), speeds[-1])
        in_range = speeds[0] - 1e-9 <= vvi_fpm <= speeds[-1] + 1e-9
        lower = max(v for v in speeds if v <= vvi)
        upper = min(v for v in speeds if v >= vvi)
        t_lo, ok_lo = self._row_throttle(rows[lower], kias)
        if upper == lower:
            return t_lo, in_range and ok_lo
        t_hi, ok_hi = self._row_throttle(rows[upper], kias)
        weight = (vvi - lower) / (upper - lower)
        return t_lo + (t_hi - t_lo) * weight, in_range and ok_lo and ok_hi
