#!/usr/bin/env python3
"""Tests for scripts/fly_search_grid.py. Pattern geometry only; no simulator."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


grid = _load("capvsar_fly_search_grid", "scripts/fly_search_grid.py")

# The C-1 test scenario beacon: services/exercise/app/settings.py SEED.
LAT, LON = 33.1700, -117.0792


def pattern(track=90.0, spacing=1.0, leg=6.0, legs=5):
    return grid.parallel_track(LAT, LON, track, spacing, leg, legs)


class TestPattern:
    def test_two_waypoints_per_leg(self):
        assert len(pattern(legs=5)) == 10

    def test_the_datum_sits_on_the_middle_leg(self):
        # The reason leg count is forced odd. With five legs the third is the
        # datum's own track, and its two ends straddle the datum.
        pts = pattern(legs=5, leg=6.0)
        mid = [p for p in pts if p.leg == 3]
        for p in mid:
            assert grid.great_circle_nm(p.lat, p.lon, LAT, LON) == pytest.approx(3.0, abs=0.05)

    def test_an_even_leg_count_is_refused(self):
        with pytest.raises(ValueError, match="odd"):
            pattern(legs=4)

    def test_legs_are_the_requested_length(self):
        for p in pattern(leg=6.0, legs=5):
            pass
        pts = pattern(leg=6.0, legs=5)
        for i in range(0, len(pts), 2):
            assert grid.great_circle_nm(pts[i].lat, pts[i].lon,
                                        pts[i + 1].lat, pts[i + 1].lon) == pytest.approx(6.0, abs=0.05)

    def test_adjacent_legs_are_one_spacing_apart(self):
        pts = pattern(spacing=1.0, legs=5)
        for i in range(0, len(pts) - 2, 2):
            a, b = pts[i], pts[i + 2]
            # Compare leg midpoints rather than corners: consecutive legs run
            # opposite ways, so start-to-start is a diagonal.
            sep = grid.great_circle_nm(a.lat, a.lon, b.lat, b.lon)
            assert sep > 0.5

    def test_legs_alternate_direction(self):
        # A pattern whose legs all ran the same way would deadhead between them.
        pts = pattern(track=90.0, legs=5)
        h1 = grid.initial_bearing(pts[0].lat, pts[0].lon, pts[1].lat, pts[1].lon)
        h2 = grid.initial_bearing(pts[2].lat, pts[2].lon, pts[3].lat, pts[3].lon)
        assert abs(((h1 - h2 + 180) % 360) - 180) == pytest.approx(180.0, abs=1.0)

    def test_legs_run_on_the_requested_track(self):
        pts = pattern(track=90.0, legs=5)
        h = grid.initial_bearing(pts[0].lat, pts[0].lon, pts[1].lat, pts[1].lon)
        assert h == pytest.approx(90.0, abs=0.5)

    def test_a_different_track_rotates_the_pattern(self):
        pts = pattern(track=0.0, legs=5)
        h = grid.initial_bearing(pts[0].lat, pts[0].lon, pts[1].lat, pts[1].lon)
        assert h == pytest.approx(0.0, abs=0.5)

    def test_the_pattern_is_symmetric_about_the_datum(self):
        pts = pattern(legs=5, spacing=1.0)
        first = min(grid.great_circle_nm(p.lat, p.lon, LAT, LON) for p in pts if p.leg == 1)
        last = min(grid.great_circle_nm(p.lat, p.lon, LAT, LON) for p in pts if p.leg == 5)
        assert first == pytest.approx(last, abs=0.05)

    def test_a_single_leg_is_allowed(self):
        assert len(pattern(legs=1)) == 2

    @pytest.mark.parametrize("bad", [dict(spacing=0.0), dict(leg=0.0), dict(spacing=-1.0)])
    def test_nonsense_dimensions_are_refused(self, bad):
        with pytest.raises(ValueError):
            pattern(**bad)


class TestCoverage:
    def test_width_is_spacing_times_the_gaps_not_the_legs(self):
        # Five legs have four gaps. Counting legs overstates coverage by one
        # spacing, which is how a search ends up with an unflown strip.
        assert grid.coverage(1.0, 6.0, 5)[0] == pytest.approx(4.0)

    def test_area_is_width_by_leg_length(self):
        assert grid.coverage(1.0, 6.0, 5)[1] == pytest.approx(24.0)

    def test_one_leg_sweeps_no_width(self):
        assert grid.coverage(1.0, 6.0, 1)[0] == pytest.approx(0.0)


class TestDescribe:
    def test_it_converts_the_track_to_magnetic(self):
        # The heading bug is magnetic and every bearing computed is true.
        text = grid.describe(pattern(), LAT, LON, 90.0, 1.0, 6.0, 5, 11.5)
        assert "90 true" in text and "78 magnetic" in text

    def test_it_reports_the_swept_area(self):
        text = grid.describe(pattern(), LAT, LON, 90.0, 1.0, 6.0, 5, 11.5)
        assert "4.0 nm wide" in text and "24.0 square nm" in text

    def test_it_does_not_share_set_air_start_s_receive_port(self):
        assert grid.DEFAULT_RECEIVE_PORT != 49005
        assert grid.DEFAULT_RECEIVE_PORT != _load(
            "sas_port_check", "scripts/set_air_start.py").DEFAULT_RECEIVE_PORT
