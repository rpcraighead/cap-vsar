"""Surface lab reset, braking and telemetry containment."""
import hashlib
from pathlib import Path
import time
import types

import pytest

from xplane import capvsar_qualification, capvsar_surface
from .test_flight_control_plugin import load_plugin


def lab_setup(monkeypatch, tmp_path, **extra):
    xp, plugin = load_plugin(monkeypatch, tmp_path)
    aircraft = tmp_path / capvsar_qualification.STOCK_NAME
    aircraft.write_text("stock fixture")
    monkeypatch.setattr(capvsar_qualification, "STOCK_SHA256",
                        hashlib.sha256(aircraft.read_bytes()).hexdigest())
    xp.getNthAircraftModel = lambda _index: (aircraft.name, str(aircraft))
    config = {"aircraft_path": str(aircraft), "expires_unix_s": time.time()+1000,
              "parking": "KSEE East Transient Parking 12", **extra}
    plugin.core.sink.brakes = ("sim/cockpit2/controls/left_brake_ratio",
                               "sim/cockpit2/controls/right_brake_ratio")
    plugin.core.sink.toe_brake_override = "sim/operation/override/override_toe_brakes"
    plugin.core.sink.controls["brake"] = plugin.core.sink.brakes[0]
    return xp, plugin, capvsar_surface.SurfaceLab(xp, plugin.core.sink, config)


def test_surface_reset_uses_terrain_probe_and_releases_to_braked_parking(monkeypatch, tmp_path):
    xp, plugin, lab = lab_setup(monkeypatch, tmp_path)
    xp.refs.update({"sim/time/paused": 1,
                    "sim/flightmodel/position/latitude": 32.824456,
                    "sim/flightmodel/position/longitude": -116.968545})
    xp.worldToLocal = lambda *_args: (100., 130., 200.)
    xp.createProbe = lambda *_args: "probe"
    xp.probeTerrainXYZ = lambda *_args: types.SimpleNamespace(
        result=0, locationX=100., locationY=118., locationZ=200.)
    xp.ProbeY = 0
    xp.ProbeHitTerrain = 0
    xp.destroyProbe = lambda *_args: None
    xp.localToWorld = lambda *_args: (32.824456, -116.968545, 118.)
    xp.setDatad = xp.setDataf
    xp.setDatavf = lambda ref, values, _offset, _count: xp.refs.update({ref: list(values)})
    result = lab.reset(plugin.core)
    assert result["local_position_m"] == [100., 119.5, 200.]
    assert xp.refs["sim/cockpit2/controls/left_brake_ratio"] == .35
    assert xp.refs["sim/cockpit2/controls/right_brake_ratio"] == .35
    assert "sim/operation/quick_start" in xp.commands
    checkpoint = lab.reset(plugin.core, checkpoint="D8 hold")
    assert checkpoint["latitude_deg"] == capvsar_surface.HOLD[0]
    assert checkpoint["parking"] == "D8 hold diagnostic checkpoint"
    with pytest.raises(ValueError, match="Unknown KSEE surface diagnostic checkpoint"):
        lab.reset(plugin.core, checkpoint="runway")


def test_surface_lab_rejects_takeoff_controls_outside_profile(monkeypatch, tmp_path):
    _, _, lab = lab_setup(monkeypatch, tmp_path)
    valid = {"roll": 0., "pitch": 0., "yaw": 0., "throttle": 1.,
             "flap": 0., "trim": 0., "brake": 1.}
    lab.validate_controls(valid)
    with pytest.raises(ValueError, match="Surface control limit"):
        lab.validate_controls({**valid, "yaw": 1.1})
    with pytest.raises(ValueError, match="Surface control limit"):
        lab.validate_controls({**valid, "flap": .1})


def test_ground_contact_agl_filter_tolerates_small_negative_noise(monkeypatch, tmp_path):
    _, plugin, lab = lab_setup(monkeypatch, tmp_path)
    plugin.core.state = "ACTIVE"
    lab.trial_started = time.monotonic()
    values = {"paused": 0, "parking_brake_ratio": 0., "latitude_deg": 32.824456,
              "longitude_deg": -116.968545, "agl_m": -.002,
              "kias": 0., "groundspeed_mps": .1,
              "roll_deg": 0., "pitch_deg": 5., "sim_time_s": 1.}
    lab.check_flight({"values": values}, plugin.core)
    with pytest.raises(ValueError, match="envelope"):
        lab.check_flight({"values": {**values, "agl_m": -2., "sim_time_s": 2.}},
                         plugin.core)
