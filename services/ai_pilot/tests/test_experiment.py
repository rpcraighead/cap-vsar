import pytest

from services.ai_pilot.experiment import CycleObserver, Recorder, Scenario, score_trace


def snapshot(t, heading=90):
    return {"schema": "capvsar.telemetry.v1", "session": "test-session", "frame": round(t * 10) + 1,
            "phase": "after_flight_model", "wall_time_s": 100 + t, "age_s": 0.02,
            "aircraft": {"name": "Cessna_172SP_G1000.acf", "path": "/stock/c172.acf"},
            "values": {"sim_time_s": t, "paused": 0, "on_ground": 0, "heading_mag_deg": heading,
                       "altitude_indicated_ft": 4500, "kias": 100, "roll_deg": 0,
                       "vvi_fpm": 0, "agl_m": 1200}}


def complete_trace():
    # Predeclared synthetic truth: 11s level, 4s turn, 11s captured, 4s return,
    # then 11s recovered. Stop recording at the observer's end-of-trial boundary.
    for tick in range(411):
        t = tick / 10
        heading = 90 if t <= 11 else (90 + (t - 11) * 5 if t < 15 else
                  (110 if t <= 26 else (110 - (t - 26) * 5 if t < 30 else 90)))
        yield snapshot(t, heading)


def test_observer_requires_observed_maneuver_and_recovery():
    observer = CycleObserver()
    for snap in complete_trace():
        observer.observe(snap)
        if observer.outcome != "INCOMPLETE":
            break
    assert observer.outcome == "PASS"
    assert [x["phase"] for x in observer.transitions] == ["establish", "maneuver", "recover"]
    assert observer.transitions[-1]["sim_time_s"] > 39


def test_level_flight_cannot_pass_a_turn_card():
    observer = CycleObserver(Scenario(phase_deadline_s=15))
    for tick in range(280):
        observer.observe(snapshot(tick / 10))
    assert observer.outcome == "FAIL" and "maneuver" in observer.reason


@pytest.mark.parametrize("alter", [
    lambda s: s["values"].update(paused=1),
    lambda s: s["values"].update(on_ground=1),
    lambda s: s["values"].update(kias=float("nan")),
    lambda s: s["values"].update(roll_deg=36),
    lambda s: s["values"].update(agl_m=100),
    lambda s: s["values"].update(sim_time_s=-1),
    lambda s: s.update(wall_time_s=101),
    lambda s: s.update(session="different"),
    lambda s: s["aircraft"].update(path="/other/c172.acf"),
    lambda s: s.update(frame=1),
    lambda s: s.pop("values"),
])
def test_intervention_gap_or_bad_data_invalidates_trial(alter):
    observer = CycleObserver()
    observer.observe(snapshot(0))
    bad = snapshot(0.1)
    alter(bad)
    assert observer.observe(bad)["outcome"] == "FAIL"


def test_settle_timer_restarts_after_excursion():
    observer = CycleObserver()
    for tick in range(151):
        s = snapshot(tick / 10)
        if tick == 90:
            s["values"]["kias"] = 104
        observer.observe(s)
    assert observer.report()["phase"] == "establish"
    assert not observer.transitions


def test_heading_wrap_is_handled():
    observer = CycleObserver(Scenario(heading_mag_deg=359))
    for tick in range(101):
        observer.observe(snapshot(tick / 10, heading=1))
    assert observer.report()["phase"] == "maneuver"


def test_replay_ignores_controller_success_and_requires_complete_trace(tmp_path):
    path = tmp_path / "trace.jsonl"
    recorder = Recorder(path, {"purpose": "scored-cycle", "scenario": Scenario().manifest()})
    recorder.write("snapshot", snapshot(0))
    recorder.write("end", {"controller_claim": "PASS"})
    recorder.close()
    assert score_trace(path)["outcome"] == "INCOMPLETE"
    with pytest.raises(FileExistsError):
        Recorder(path, {})


def test_replay_reproduces_measured_pass_and_detects_truncation(tmp_path):
    path = tmp_path / "trace.jsonl"
    recorder = Recorder(path, {"purpose": "scored-cycle", "scenario": Scenario().manifest()})
    observer = CycleObserver()
    for snap in complete_trace():
        recorder.write("snapshot", snap)
        observer.observe(snap)
        if observer.outcome != "INCOMPLETE":
            break
    recorder.write("end", {})
    recorder.close()
    result = score_trace(path)
    assert result["outcome"] == "PASS" and result["transitions"] == observer.transitions
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n")
    assert score_trace(path)["outcome"] == "INCOMPLETE"
    path.write_text("\n".join(lines[:-1]) + '\n{"kind":')
    assert score_trace(path)["outcome"] == "FAIL"


def test_readiness_trace_cannot_be_misreported_as_flight_pass(tmp_path):
    path = tmp_path / "observe.jsonl"
    recorder = Recorder(path, {"purpose": "telemetry-qualification"})
    recorder.write("end", {"outcome": "OBSERVATION_PASS"})
    recorder.close()
    assert score_trace(path)["outcome"] == "FAIL"


def test_overlapping_capture_bands_rejected():
    with pytest.raises(ValueError, match="overlap"):
        Scenario(turn_deg=5)


@pytest.mark.parametrize("line", ['null', '[]', '{"kind":"manifest","payload":null}'])
def test_invalid_record_shape_is_reported_as_failure(tmp_path, line):
    path = tmp_path / "invalid.jsonl"
    path.write_text(line + "\n")
    assert score_trace(path)["outcome"] == "FAIL"
