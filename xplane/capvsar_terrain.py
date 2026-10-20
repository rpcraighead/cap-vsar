"""Terrain lookahead for the flight-control bridge. No X-Plane import here.

Ported from the squadron-demo plugin PI_capvsar_terrain_guard.py (2026-10-14),
which published the same numbers as `cap/guard/*` datarefs for a script outside
the sim to act on. Here the scan is part of the bridge's telemetry snapshot, so
the executive that owns the airplane (the AI pilot's controllers or the GFC 700)
reads terrain from the same coherent frame as everything else.

The scan probes the real terrain along the ground track, the centre line plus a
fan either side, out to LOOKAHEAD_NM, and reports the highest ground found and
how far away it is. `terrain_ft(lat, lon)` returns feet MSL or None where the
probe finds nothing.
"""
from __future__ import annotations

import math

LOOKAHEAD_NM = 12.0
STEP_NM = 0.5
FAN_DEG = (-12.0, 0.0, 12.0)
MIN_GS_MPS = 5.0       # below this the ground track is noise; use the heading
REFRESH_S = 1.0        # a scan is ~75 probes; once a second is plenty


def scan(terrain_ft, lat, lon, track_deg, *, lookahead_nm=LOOKAHEAD_NM,
         step_nm=STEP_NM, fan_deg=FAN_DEG):
    """Highest terrain ahead, its distance, and the terrain directly below."""
    under = terrain_ft(lat, lon)
    best_ft, best_nm, hits = -1e9, 0.0, 0
    coslat = max(0.1, math.cos(math.radians(lat)))
    for offset in fan_deg:
        bearing = math.radians(track_deg + offset)
        nm = step_nm
        while nm <= lookahead_nm + 1e-6:
            ft = terrain_ft(lat + nm * math.cos(bearing) / 60.0,
                            lon + nm * math.sin(bearing) / (60.0 * coslat))
            if ft is not None:
                hits += 1
                if ft > best_ft:
                    best_ft, best_nm = ft, nm
            nm += step_nm
    valid = hits > 0
    return {"valid": valid,
            "ahead_max_ft": max(best_ft, 0.0) if valid else 0.0,
            "ahead_max_nm": best_nm if valid else 0.0,
            "under_ft": under if under is not None else 0.0,
            "under_valid": under is not None,
            "lookahead_nm": lookahead_nm}


class TerrainScanner:
    """Rate-limited scan for the telemetry loop; keeps the last result between scans."""

    def __init__(self, terrain_ft, clock, refresh_s=REFRESH_S):
        self.terrain_ft, self.clock, self.refresh_s = terrain_ft, clock, refresh_s
        self.last = None
        self.last_at = None

    def update(self, lat, lon, heading_deg, track_deg, groundspeed_mps):
        now = self.clock()
        if self.last_at is None or now - self.last_at >= self.refresh_s:
            track = track_deg if groundspeed_mps > MIN_GS_MPS else heading_deg
            self.last = scan(self.terrain_ft, lat, lon, track)
            self.last_at = now
        return {**self.last, "age_s": now - self.last_at}


FT_PER_M = 3.28084


def probe_terrain_ft(xp):
    """`terrain_ft(lat, lon)` backed by X-Plane's terrain probe, and its destructor.

    SDK calls stay on the simulator's main thread: call the returned function only
    from a flight-loop callback (the telemetry capture loop does).
    """
    probe = xp.createProbe(xp.ProbeY)

    def terrain_ft(lat, lon):
        x, y, z = xp.worldToLocal(lat, lon, 0.0)
        info = xp.probeTerrainXYZ(probe, x, y, z)
        if info.result != xp.ProbeHitTerrain:
            return None
        _, _, alt_m = xp.localToWorld(info.locationX, info.locationY, info.locationZ)
        return alt_m * FT_PER_M

    return terrain_ft, lambda: xp.destroyProbe(probe)
