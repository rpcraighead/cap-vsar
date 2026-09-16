#!/usr/bin/env python3
"""A measurement loop must refuse an aeroplane that is not flying the condition.

Written after a C2 mixture sweep recorded eleven rows of 0.0 HP and concluded
"peak power at mixture 0.80" while the aircraft spun into the sea. The engine
had stopped before the first row.
"""

from __future__ import annotations

import importlib.util
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


g = _load("capvsar_flight_condition_guard", "scripts/flight_condition_guard.py")

HEALTHY = {
    g.ConditionGuard.CRASHED: 0.0,
    g.ConditionGuard.RUNNING: 1.0,
    g.ConditionGuard.RPM: 2400.0,
    g.ConditionGuard.ALT: 7000 * 0.3048,
    g.ConditionGuard.KIAS: 130.0,
    g.ConditionGuard.ROLL: 1.0,
    g.ConditionGuard.PITCH: 2.0,
}


class FakeClient:
    def __init__(self, cache):
        self.cache = dict(cache)
        self.subscribed = []

    def subscribe_dref(self, ref, freq_hz=1, **kw):
        self.subscribed.append(ref)

    def get_all_cached(self):
        return self.cache


def guard(**overrides):
    cache = dict(HEALTHY)
    cache.update(overrides)
    return g.ConditionGuard(FakeClient(cache), alt_ft=7000)


class TestGuard:
    def test_a_healthy_condition_passes(self):
        guard().check()

    def test_a_crash_is_refused(self):
        with pytest.raises(g.ConditionLost, match="CRASHED"):
            guard(**{g.ConditionGuard.CRASHED: 1.0}).check()

    def test_a_stopped_engine_is_refused(self):
        # THE ACTUAL FAILURE: RPM 0 on every row of a mixture sweep, unnoticed.
        with pytest.raises(g.ConditionLost, match="engine stopped"):
            guard(**{g.ConditionGuard.RPM: 0.0}).check()

    def test_rpm_is_trusted_over_the_running_flag(self):
        # ENGN_running can lag; an engine turning zero is turning zero.
        with pytest.raises(g.ConditionLost, match="engine stopped"):
            guard(**{g.ConditionGuard.RPM: 0.0,
                     g.ConditionGuard.RUNNING: 1.0}).check()

    def test_a_spin_is_refused_by_roll(self):
        with pytest.raises(g.ConditionLost, match="roll"):
            guard(**{g.ConditionGuard.ROLL: 175.9}).check()

    def test_a_dive_is_refused_by_pitch(self):
        with pytest.raises(g.ConditionLost, match="pitch"):
            guard(**{g.ConditionGuard.PITCH: -55.0}).check()

    def test_low_airspeed_is_refused(self):
        with pytest.raises(g.ConditionLost, match="airspeed"):
            guard(**{g.ConditionGuard.KIAS: 20.0}).check()

    def test_drifting_off_the_test_altitude_is_refused(self):
        # The C2 attempt was 1,400 ft below its condition before anything
        # took hold of it, and measured anyway.
        with pytest.raises(g.ConditionLost, match="altitude"):
            guard(**{g.ConditionGuard.ALT: 5611 * 0.3048}).check()

    def test_small_altitude_excursions_are_tolerated(self):
        guard(**{g.ConditionGuard.ALT: 7200 * 0.3048}).check()

    def test_every_fault_is_reported_not_just_the_first(self):
        faults = guard(**{g.ConditionGuard.RPM: 0.0,
                          g.ConditionGuard.ROLL: 175.9,
                          g.ConditionGuard.KIAS: 5.0}).faults()
        assert len(faults) >= 3

    def test_it_subscribes_to_indexed_array_datarefs(self):
        # Without the [0] these return a silent 0.0, which once reported a
        # dead engine at full throttle.
        c = FakeClient(HEALTHY)
        g.ConditionGuard(c)
        assert any(r.endswith("[0]") for r in c.subscribed)
        assert g.ConditionGuard.RPM.endswith("[0]")
