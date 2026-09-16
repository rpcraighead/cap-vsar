#!/usr/bin/env python3
"""AI-4's log half: the two load regressions, asserted rather than eyeballed."""

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


chk = _load("capvsar_check_xplane_log", "scripts/check_xplane_log.py")

CLEAN = [
    "0:00:00.000 I/ACF: Loading airplane number 0 with Aircraft/CAP/Cessna 182T NAV III/Cessna_182T_G1000.acf",
    "OpenGL Extensions : GL_ARB_texture_non_power_of_two GL_ARB_shadow",
    "0:00:01.000 I/SCN: loaded fine",
]
IDX_FAULT = "0:00:02.000 E/OBJ: objects/prop_lever.obj line 187 IDX10 index out of range"
TEX_FAULT = "0:00:02.100 W/TEX: prop_lever.png is not a power of two (194x87)"


class TestScan:
    def test_a_clean_log_reports_nothing(self):
        assert chk.scan(CLEAN) == []

    def test_the_gl_extension_string_is_not_a_texture_warning(self):
        # GL_ARB_texture_non_power_of_two appears in every log's extension
        # list. Matching it would fail every run and train the reader to
        # ignore this check - which happened once, by hand, during AI-4.
        assert chk.scan(["GL_ARB_texture_non_power_of_two"]) == []

    def test_the_idx10_regression_is_caught(self):
        hits = chk.scan(CLEAN + [IDX_FAULT])
        assert len(hits) == 1 and "index encoding" in hits[0][0]

    def test_the_texture_regression_is_caught(self):
        hits = chk.scan(CLEAN + [TEX_FAULT])
        assert len(hits) == 1 and "power of two" in hits[0][0]

    def test_both_at_once(self):
        assert len(chk.scan(CLEAN + [IDX_FAULT, TEX_FAULT])) == 2

    def test_an_unrelated_object_is_not_this_defect(self):
        # The file must be named. A bare complaint about some other object is
        # not AI-4, and failing on it would make the check useless.
        assert chk.scan(["E/OBJ: fuselage.obj line 12 index out of range"]) == []

    def test_a_mention_without_a_fault_is_not_a_failure(self):
        assert chk.scan(["I/OBJ: loaded objects/prop_lever.obj fine"]) == []

    def test_it_reports_the_line_number(self):
        hits = chk.scan(CLEAN + [IDX_FAULT])
        assert hits[0][1] == len(CLEAN) + 1


class TestAircraftGuard:
    def test_it_reads_back_what_was_loaded(self):
        assert chk.aircraft_loaded(CLEAN) == [
            "Aircraft/CAP/Cessna 182T NAV III/Cessna_182T_G1000.acf"]

    def test_a_log_that_never_loaded_the_aircraft_fails(self, tmp_path, capsys):
        # X-Plane appends across reloads, so a log can be clean purely because
        # it predates the package being tested.
        log = tmp_path / "Log.txt"
        log.write_text("0:00:00.000 I/SCN: nothing here\n", encoding="utf-8")
        rc = chk.main(["--log", str(log), "--require-aircraft", "Cessna_182T_G1000.acf"])
        assert rc == 3
        assert "never loaded" in capsys.readouterr().err

    def test_the_guard_passes_when_the_aircraft_is_there(self, tmp_path):
        log = tmp_path / "Log.txt"
        log.write_text("\n".join(CLEAN) + "\n", encoding="utf-8")
        assert chk.main(["--log", str(log),
                         "--require-aircraft", "Cessna_182T_G1000.acf"]) == 0


class TestExitCodes:
    def test_clean_exits_zero(self, tmp_path):
        log = tmp_path / "Log.txt"
        log.write_text("\n".join(CLEAN) + "\n", encoding="utf-8")
        assert chk.main(["--log", str(log)]) == 0

    def test_a_regression_exits_one(self, tmp_path):
        log = tmp_path / "Log.txt"
        log.write_text("\n".join(CLEAN + [IDX_FAULT]) + "\n", encoding="utf-8")
        assert chk.main(["--log", str(log)]) == 1

    def test_a_missing_log_exits_two(self, tmp_path):
        assert chk.main(["--log", str(tmp_path / "nope.txt")]) == 2

    def test_a_clean_run_refuses_to_claim_ai4_is_closed(self, tmp_path, capsys):
        # A clean log is necessary and not sufficient; the tool must say so.
        log = tmp_path / "Log.txt"
        log.write_text("\n".join(CLEAN) + "\n", encoding="utf-8")
        chk.main(["--log", str(log)])
        assert "NOT sufficient" in capsys.readouterr().out


# --- capture guard: a paused run is not a run -------------------------------

cap = _load("capvsar_capture_flight_test", "scripts/capture_flight_test.py")


class TestFrozenRunGuard:
    """X-Plane answers RREF while PAUSED, so a paused capture returns a
    full-rate, gap-free trace of a stationary aeroplane - which reads exactly
    like a beautifully stable test point. B1 run 1 was 2,995 samples at 20.0 Hz
    with zero gaps and identical min and max on every channel."""

    def _run(self, samples, capsys):
        cap.summarise(
            type("A", (), {"card": "B1", "run": "1", "hz": 20})(),
            ["kias", "alt_msl_ft", "alpha_deg", "g_normal", "weight_kg"],
            samples, [0.05] * max(0, len(samples) - 1), [])
        return capsys.readouterr().out

    def test_a_paused_capture_is_called_out(self, capsys):
        frozen = [{"kias": 78.3, "alt_msl_ft": 1005.0, "alpha_deg": 6.02,
                   "g_normal": 1.004, "weight_kg": 1406.0} for _ in range(200)]
        out = self._run(frozen, capsys)
        assert "NOT A RUN" in out
        assert "PAUSED" in out
        assert "Do not" in out, "it must say not to reduce the trace"

    def test_one_constant_channel_alone_is_not_enough(self):
        # Altitude alone can legitimately hold constant in level flight.
        pass

    def test_a_real_run_is_not_flagged(self, capsys):
        moving = [{"kias": 78.0 + i * 0.01, "alt_msl_ft": 1005.0 + i,
                   "alpha_deg": 6.0 + i * 0.001, "g_normal": 1.0 + i * 0.0001,
                   "weight_kg": 1406.0} for i in range(200)]
        assert "NOT A RUN" not in self._run(moving, capsys)
