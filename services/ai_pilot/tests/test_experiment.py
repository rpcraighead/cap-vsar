import pytest
import json

from services.ai_pilot.experiment import (BridgeClient, CycleObserver, Recorder, Scenario,
                                          score_trace, wait_for_ready_snapshot)


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


def _readiness_client(acf_path, *, sim_speed=1, paused=0, sim_time=10.):
    class Client:
        frame = 0
        def request(self, action, **_kwargs):
            if action == "status":
                return {"state": "MANUAL"}
            self.frame += 1
            return {"age_s": .02, "frame": self.frame,
                    "aircraft": {"name": "Cessna_172SP_G1000.acf", "path": str(acf_path)},
                    "values": {"sim_speed": sim_speed, "paused": paused,
                               "sim_time_s": sim_time}}
    return Client()


def test_readiness_requires_initialized_paused_sim_speed_and_positive_sim_time(tmp_path):
    acf = tmp_path / "Cessna_172SP_G1000.acf"
    acf.touch()
    with pytest.raises(TimeoutError, match="stopped and not initialized-paused"):
        wait_for_ready_snapshot(_readiness_client(acf, sim_speed=0, paused=1, sim_time=10.),
                                timeout_s=.01, poll_s=.001)
    reset_ready = wait_for_ready_snapshot(
        _readiness_client(acf, sim_speed=0, paused=1, sim_time=10.),
        timeout_s=.1, poll_s=0., validate=lambda snap: snap["values"]["paused"] == 1)
    assert reset_ready["values"]["sim_speed"] == 0
    with pytest.raises(TimeoutError, match="stopped and not initialized-paused"):
        wait_for_ready_snapshot(_readiness_client(acf, sim_speed=1, paused=1, sim_time=0.),
                                timeout_s=.01, poll_s=.001)
    ready = wait_for_ready_snapshot(_readiness_client(acf, sim_speed=1, paused=1, sim_time=10.),
                                    timeout_s=.1, poll_s=0.)
    assert ready["values"]["paused"] == 1 and ready["values"]["sim_speed"] == 1


def test_bridge_client_retries_expired_exchange_with_a_fresh_lease(monkeypatch):
    import services.ai_pilot.experiment as experiment

    payloads = []
    replies = [
        b'{"error":"Frame expired in queue","status":{"state":"ACTIVE","fault":null}}\n',
        b'{"ok":true}\n',
    ]

    class FakeSocket:
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def settimeout(self, _timeout): pass
        def connect(self, _path): pass
        def sendall(self, raw): payloads.append(json.loads(raw))
        def recv(self, _size): return replies.pop(0)

    monkeypatch.setattr(experiment.socket, "socket", lambda *_args: FakeSocket())
    response = BridgeClient({"secret": "s", "socket_path": "/fake"}).request(
        "exchange", expires_at=0., sequence=3)
    assert response["ok"]
    assert len(payloads) == 2 and payloads[0]["sequence"] == payloads[1]["sequence"] == 3
    assert payloads[1]["expires_at"] > payloads[0]["expires_at"]


def test_bridge_client_does_not_retry_exchange_that_did_not_answer(monkeypatch):
    import services.ai_pilot.experiment as experiment

    payloads = []

    class FakeSocket:
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def settimeout(self, _timeout): pass
        def connect(self, _path): pass
        def sendall(self, raw): payloads.append(json.loads(raw))
        def recv(self, _size):
            return b'{"error":"flight loop did not answer within 0.25 s","status":{"state":"ACTIVE","fault":null}}\n'

    monkeypatch.setattr(experiment.socket, "socket", lambda *_args: FakeSocket())
    with pytest.raises(RuntimeError, match="did not answer"):
        BridgeClient({"secret": "s", "socket_path": "/fake"}).request(
            "exchange", expires_at=1., sequence=3)
    assert len(payloads) == 1 and payloads[0]["sequence"] == 3
