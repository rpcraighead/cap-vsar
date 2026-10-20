"""Terrain lookahead and the executive's terrain guard (offline, synthetic ground)."""
import math

import pytest

from services.ai_pilot.terrain_guard import CEILING_FT, FT_PER_M, TerrainGuard
from xplane.capvsar_terrain import TerrainScanner, scan

LAT, LON = 33.0, -117.0


def ridge(east_nm, height_ft, floor_ft=500., width_nm=1.0):
    """Flat ground with a north-south ridge `east_nm` east of the start."""
    def terrain_ft(lat, lon):
        east = (lon - LON) * 60.0 * math.cos(math.radians(LAT))
        return height_ft if abs(east - east_nm) <= width_nm / 2 else floor_ft
    return terrain_ft


def test_scan_finds_the_ridge_and_its_distance_along_the_track():
    result = scan(ridge(6.0, 5200.), LAT, LON, 90.0)
    assert result["valid"] and result["ahead_max_ft"] == 5200.
    assert result["ahead_max_nm"] == pytest.approx(6.0, abs=0.5)
    assert result["under_ft"] == 500.


def test_scan_ignores_a_ridge_behind_the_track_and_reports_invalid_without_probes():
    assert scan(ridge(-6.0, 5200.), LAT, LON, 90.0)["ahead_max_ft"] == 500.
    blind = scan(lambda lat, lon: None, LAT, LON, 90.0)
    assert blind["valid"] is False and blind["ahead_max_ft"] == 0.


def test_scanner_is_rate_limited_and_uses_heading_when_nearly_stopped():
    calls, now = [], [0.]

    def terrain_ft(lat, lon):
        calls.append((lat, lon))
        return 500.
    scanner = TerrainScanner(terrain_ft, lambda: now[0], refresh_s=1.0)
    first = scanner.update(LAT, LON, 90., 270., 40.)
    count = len(calls)
    now[0] = 0.4
    again = scanner.update(LAT, LON, 90., 270., 40.)
    assert len(calls) == count and again["age_s"] == pytest.approx(0.4)
    now[0] = 1.5
    scanner.update(LAT, LON, 90., 270., 2.)      # stopped: heading 090, not track 270
    assert calls[-1][1] > LON and first["valid"]


def snapshot(alt_ft, terrain, *, gs_kt=100., lat=LAT, lon=LON, indicated_offset=60.):
    return {"values": {"altitude_msl_m": alt_ft / FT_PER_M,
                       "altitude_indicated_ft": alt_ft + indicated_offset,
                       "groundspeed_mps": gs_kt / 1.94384,
                       "latitude_deg": lat, "longitude_deg": lon},
            "terrain": terrain}


def terrain(ahead_ft, ahead_nm, under_ft=500., valid=True, age_s=0.2):
    return {"valid": valid, "ahead_max_ft": ahead_ft, "ahead_max_nm": ahead_nm,
            "under_ft": under_ft, "age_s": age_s}


def test_distant_high_ground_is_not_a_reason_to_leave_the_search_altitude():
    advice = TerrainGuard().update(snapshot(4000., terrain(5200., 11.)))
    assert advice.valid and advice.floor_indicated_ft is None and not advice.full_power


def test_floor_rises_when_the_climb_must_start_now_and_is_in_indicated_feet():
    advice = TerrainGuard().update(snapshot(4000., terrain(5200., 4.)))
    # ground 5,200 + 1,500 clear target, rounded up to a 500 ft step = 7,000 MSL
    assert advice.floor_indicated_ft == pytest.approx(7000. + 60.)
    assert advice.full_power and advice.climb_fpm == 700 and not advice.turn_back  # below the ground: urgent
    assert advice.clearance_ft == pytest.approx(-1200.)
    assert advice.reason.startswith("terrain 5200 ft at 4.0 nm")


def test_urgent_clearance_climbs_harder():
    advice = TerrainGuard().update(snapshot(5000., terrain(4800., 2.)))
    assert advice.clearance_ft == pytest.approx(200.) and advice.climb_fpm == 700


def test_floor_is_held_then_released_a_step_below_the_ground_ahead():
    guard = TerrainGuard()
    guard.update(snapshot(4000., terrain(5200., 4.)))
    held = guard.update(snapshot(6500., terrain(5200., 4.)))
    assert held.floor_indicated_ft is not None and held.climb_fpm == 500   # 1,800 ft clear: not urgent
    low = guard.update(snapshot(7000., terrain(900., 8.)))
    assert low.floor_indicated_ft is None and "low again" in low.reason


def test_terrain_above_the_ceiling_means_turn_back_not_climb():
    advice = TerrainGuard().update(snapshot(4000., terrain(8000., 3.)))
    assert advice.floor_indicated_ft > CEILING_FT and advice.turn_back
    assert "ceiling" in advice.reason


def test_leash_turns_the_airplane_back_toward_the_area():
    guard = TerrainGuard(leash=(LAT, LON, 8.))
    out = guard.update(snapshot(4000., terrain(600., 5.), lon=LON + 0.2))   # ~9.7 nm east
    assert out.turn_back and out.return_heading_true == pytest.approx(270., abs=1.)
    inside = guard.update(snapshot(4000., terrain(600., 5.), lon=LON + 0.05))
    assert not inside.turn_back


def test_no_terrain_data_keeps_an_existing_floor_and_never_invents_a_descent():
    guard = TerrainGuard()
    guard.update(snapshot(4000., terrain(5200., 4.)))
    blind = guard.update(snapshot(6000., terrain(0., 0., valid=False)))
    assert not blind.valid and blind.floor_indicated_ft == pytest.approx(7060.)
    stale = guard.update(snapshot(6000., terrain(5200., 4., age_s=9.)))
    assert not stale.valid
    assert TerrainGuard().update({"values": snapshot(4000., None)["values"]}).floor_indicated_ft is None


def test_apply_to_altitude_takes_the_higher_of_mission_and_floor():
    guard = TerrainGuard()
    advice = guard.update(snapshot(4000., terrain(5200., 4.)))
    assert guard.apply_to_altitude(4500., advice) == pytest.approx(7060.)
    assert guard.apply_to_altitude(9000., advice) == 9000.
    quiet = TerrainGuard().update(snapshot(4000., terrain(600., 4.)))
    assert TerrainGuard().apply_to_altitude(4500., quiet) == 4500.
