import hashlib
import queue
import time
import pytest

from xplane import capvsar_qualification as lab_module
from .test_flight_control_plugin import load_plugin
from .test_snapshot_controller import sample


def setup_lab(monkeypatch, tmp_path):
    xp, plugin = load_plugin(monkeypatch, tmp_path)
    aircraft = tmp_path / lab_module.STOCK_NAME
    aircraft.write_text("fixture")
    monkeypatch.setattr(lab_module, "STOCK_SHA256", hashlib.sha256(aircraft.read_bytes()).hexdigest())
    xp.getNthAircraftModel = lambda index: (aircraft.name, str(aircraft))
    config = {"aircraft_path": str(aircraft), "expires_unix_s": time.time() + 1000}
    return xp, plugin, config, lab_module.QualificationLab(xp, plugin.core.sink, config)


def test_lab_pins_aircraft_hash_path_and_expiry(monkeypatch, tmp_path):
    xp, plugin, config, lab = setup_lab(monkeypatch, tmp_path)
    for expiry in (0, time.time() + 15000):
        with pytest.raises(ValueError):
            lab_module.QualificationLab(xp, plugin.core.sink, {**config, "expires_unix_s": expiry})
    xp.getNthAircraftModel = lambda index: ("other.acf", "/other.acf")
    with pytest.raises(ValueError, match="aircraft"):
        lab.verify_identity()
    assert not xp.writes


def test_reset_cannot_write_while_flying_or_owning_controls(monkeypatch, tmp_path):
    xp, plugin, _, lab = setup_lab(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="pause"):
        lab.reset(plugin.core)
    xp.refs["sim/time/paused"] = 1
    xp.refs["sim/operation/override/override_joystick"] = 1
    with pytest.raises(ValueError, match="released"):
        lab.reset(plugin.core)
    assert xp.writes == []


@pytest.mark.parametrize("controls", [
    {"roll": 0}, {"roll": .4, "pitch": 0, "yaw": 0, "throttle": .5, "flap": 0, "trim": 0},
    {"roll": 0, "pitch": 0, "yaw": 0, "throttle": .5, "flap": .1, "trim": 0},
    {"roll": 0, "pitch": 0, "yaw": 0, "throttle": .5, "flap": 0, "trim": float("nan")},
])
def test_lab_authority_is_narrower_than_native_ranges(monkeypatch, tmp_path, controls):
    _, _, _, lab = setup_lab(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        lab.validate_controls(controls)


def test_lab_watches_pause_reset_and_aircraft_independently_of_controller(monkeypatch, tmp_path):
    xp, plugin, _, lab = setup_lab(monkeypatch, tmp_path)
    plugin.core.state = "ACTIVE"
    lab.trial_started = time.monotonic()
    lab.check_flight(sample(1), plugin.core)
    with pytest.raises(ValueError, match="time"):
        lab.check_flight(sample(.5), plugin.core)
    s = sample(2)
    s["values"]["paused"] = 1
    with pytest.raises(ValueError, match="envelope"):
        lab.check_flight(s, plugin.core)


def test_local_reset_sets_position_velocity_and_normalized_orientation_only_between_trials(monkeypatch, tmp_path):
    xp, plugin, _, lab = setup_lab(monkeypatch, tmp_path)
    xp.refs.update({"sim/time/paused": 1, "sim/flightmodel/position/latitude": 32.7,
                    "sim/flightmodel/position/longitude": -117.2})
    xp.worldToLocal = lambda *args: (100., 1371.6, -200.)
    xp.setDatad = xp.setDataf
    xp.setDatavf = lambda ref, values, offset, count: xp.refs.update({ref: list(values)})
    reset = lab.reset(plugin.core)
    import math
    q = xp.refs["sim/flightmodel/position/q"]
    assert sum(x*x for x in q) == pytest.approx(1.)
    assert reset["local_position_m"] == [100., 1371.6, -200.]
    vx, vz = [xp.refs["sim/flightmodel/position/local_v"+axis] for axis in "xz"]
    assert math.degrees(math.atan2(vx, -vz)) == pytest.approx(101.)
    assert "sim/operation/quick_start" in xp.commands
    assert "sim/operation/override/override_planepath" not in xp.refs


def test_resume_initialization_has_a_deadline_and_requires_bounded_truth(monkeypatch, tmp_path):
    _, plugin, _, lab = setup_lab(monkeypatch, tmp_path)
    clock = [0.]
    monkeypatch.setattr(lab_module.time, "monotonic", lambda: clock[0])
    plugin.core.state = "ACTIVE"
    lab.trial_started = 0.
    lab.resume_pending = True
    s = sample(1)
    s["values"].update(kias=0., tas_mps=55.)
    lab.check_flight(s, plugin.core)
    assert lab.resume_pending
    s["values"]["tas_mps"] = 0.
    with pytest.raises(ValueError, match="envelope"):
        lab.check_flight(s, plugin.core)
    lab.resume_pending = True
    s["values"]["tas_mps"] = 55.
    clock[0] = 2.1
    with pytest.raises(ValueError, match="envelope"):
        lab.check_flight(s, plugin.core)
    lab.resume_pending = True
    s["values"]["paused"] = 1
    with pytest.raises(ValueError, match="Resume"):
        lab.check_flight(s, plugin.core)


def test_aircraft_change_stops_writes_before_next_flight_model(monkeypatch, tmp_path):
    xp, plugin, _, lab = setup_lab(monkeypatch, tmp_path)
    plugin.lab = lab
    for channel in ("roll", "pitch", "yaw", "throttle", "flap", "trim"):
        plugin.core.candidate(plugin.core.session, channel, 0.)
    plugin.core.prepare("DIRECT", plugin.core.session, 0)
    plugin.core.activate(plugin.core.session, 1)
    before = [entry for entry in xp.writes if entry[0].startswith("sim/joystick/yoke")]
    xp.getNthAircraftModel = lambda index: ("other.acf", "/other.acf")
    plugin.flight_loop(0, 0, 2, None)
    assert plugin.core.retired and plugin.core.pause_confirmed
    assert [entry for entry in xp.writes if entry[0].startswith("sim/joystick/yoke")] == before


def test_lab_start_transfers_and_resumes_in_one_flight_callback(monkeypatch, tmp_path):
    xp, plugin, _, lab = setup_lab(monkeypatch, tmp_path)
    plugin.lab = lab
    plugin.core.atomic = True
    xp.refs["sim/time/paused"] = 1
    controls = {"roll": 0., "pitch": 0., "yaw": 0., "throttle": .55, "flap": 0., "trim": 0.}
    now = time.monotonic()
    plugin.snapshot = {"frame": 42, "wall_time_s": now}
    reply = queue.Queue(maxsize=1)
    plugin.requests.put_nowait(({"action": "lab_start", "session": plugin.core.session,
                                 "controls": controls, "snapshot_frame": 42,
                                 "snapshot_wall_time_s": now}, reply))
    plugin.flight_loop(0, 0, 1, None)
    status = reply.get_nowait()
    assert status["state"] == "ACTIVE" and status["generation"] == 1
    assert status["frame_sequence"] == 2
    assert xp.refs["sim/operation/override/override_joystick"] == 1
    assert "sim/operation/pause_off" in xp.commands
    assert lab.trial_started is not None


def test_lab_start_rejects_stale_source_before_ownership(monkeypatch, tmp_path):
    xp, plugin, _, lab = setup_lab(monkeypatch, tmp_path)
    plugin.lab = lab
    plugin.core.atomic = True
    xp.refs["sim/time/paused"] = 1
    controls = {"roll": 0., "pitch": 0., "yaw": 0., "throttle": .55, "flap": 0., "trim": 0.}
    now = time.monotonic()
    plugin.snapshot = {"frame": 42, "wall_time_s": now}
    reply = queue.Queue(maxsize=1)
    plugin.requests.put_nowait(({"action": "lab_start", "session": plugin.core.session,
                                 "controls": controls, "snapshot_frame": 41,
                                 "snapshot_wall_time_s": now - .25}, reply))
    plugin.flight_loop(0, 0, 1, None)
    assert "Fresh qualification snapshot" in reply.get_nowait()["error"]
    assert plugin.core.state == "MANUAL"
    assert xp.refs["sim/operation/override/override_joystick"] == 0
    assert "sim/operation/pause_off" not in xp.commands


def test_lab_start_failure_after_activation_pauses_and_retires(monkeypatch, tmp_path):
    xp, plugin, _, lab = setup_lab(monkeypatch, tmp_path)
    plugin.lab = lab
    plugin.core.atomic = True
    xp.refs["sim/time/paused"] = 1
    monkeypatch.setattr(lab, "resume", lambda core: (_ for _ in ()).throw(ValueError("resume failed")))
    controls = {"roll": 0., "pitch": 0., "yaw": 0., "throttle": .55, "flap": 0., "trim": 0.}
    now = time.monotonic()
    plugin.snapshot = {"frame": 42, "wall_time_s": now}
    reply = queue.Queue(maxsize=1)
    plugin.requests.put_nowait(({"action": "lab_start", "session": plugin.core.session,
                                 "controls": controls, "snapshot_frame": 42,
                                 "snapshot_wall_time_s": now}, reply))
    plugin.flight_loop(0, 0, 1, None)
    assert "resume failed" in reply.get_nowait()["error"]
    assert plugin.core.retired and plugin.core.pause_confirmed
    assert xp.refs["sim/operation/override/override_joystick"] == 0
