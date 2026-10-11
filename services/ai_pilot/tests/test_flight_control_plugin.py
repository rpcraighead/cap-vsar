"""Fake XPPython3 SDK: candidate callbacks and actuator readbacks are stateful."""
import importlib.util
import json
from pathlib import Path
import queue
import sys
import types

from xplane.capvsar_flight_control_core import CHANNELS

SESSION = "d" * 32


class FakeXP(types.ModuleType):
    Type_Float = 1
    FlightLoop_Phase_AfterFlightModel = 1
    FlightLoop_Phase_BeforeFlightModel = 0

    def __init__(self):
        super().__init__("xp")
        self.refs = {
            "sim/operation/override/override_joystick": 0,
            "sim/operation/override/override_throttles": 0,
            "sim/cockpit2/autopilot/flight_director_mode": 1,
            "sim/cockpit2/autopilot/servos_on": 0,
            "sim/time/paused": 0,
            "sim/flightmodel/engine/ENGN_thro_use": [0.0] * 16,
            "sim/cockpit2/engine/actuators/throttle_ratio": [0.0] * 16,
        }
        self.accessors = {}
        self.writes = []
        self.commands = []

    def findDataRef(self, name):
        if name.endswith("ENGN_thro_use[0]"):
            return None
        return name
    def findCommand(self, name): return name
    def getDatai(self, ref): return self.refs.get(ref, 0)
    def getDataf(self, ref): return self.refs.get(ref, 0.0)
    def getDatad(self, ref): return self.refs.get(ref, 0.0)
    def getNthAircraftModel(self, index): return ("Cessna_172SP_G1000.acf", "/sim/Cessna_172SP_G1000.acf")
    def getVersions(self): return (12403, 400, 3)
    def createFlightLoop(self, callback, phase): return (callback, phase)
    def scheduleFlightLoop(self, loop, interval): pass
    def destroyFlightLoop(self, loop): pass
    def getDatavf(self, ref, values, offset, count):
        values[:count] = self.refs.get(ref, [0.] * 16)[offset:offset + count]
        return count
    def getDatavi(self, ref, values, offset, count):
        return self.getDatavf(ref, values, offset, count)
    def setDatai(self, ref, value):
        assert ref != "sim/time/paused", "Pause is a read-only dataref"
        self.refs[ref] = value
        self.writes.append((ref, value))
    def setDataf(self, ref, value):
        assert ref not in ("sim/flightmodel/engine/ENGN_thro_use", "sim/cockpit2/engine/actuators/throttle_ratio")
        self.refs[ref] = value
        self.writes.append((ref, value))
    def setDatavf(self, ref, values, offset, count):
        assert ref in ("sim/flightmodel/engine/ENGN_thro_use", "sim/cockpit2/engine/actuators/throttle_ratio")
        self.refs[ref][offset:offset + count] = values[:count]
        self.writes.append((ref, values[0]))
    def commandOnce(self, name):
        self.commands.append(name)
        if name == "sim/GPS/g1000n1_ap":
            self.refs["sim/cockpit2/autopilot/servos_on"] = 1
            self.refs["sim/cockpit2/autopilot/flight_director_mode"] = 2
        elif name == "sim/autopilot/servos_off_any":
            self.refs["sim/cockpit2/autopilot/servos_on"] = 0
            self.refs["sim/cockpit2/autopilot/flight_director_mode"] = 1
        elif name == "sim/operation/pause_on":
            self.refs["sim/time/paused"] = 1
    def registerDataAccessor(self, name, kind, writable, **callbacks):
        self.accessors[name] = callbacks
        return name
    def unregisterDataAccessor(self, name): self.accessors.pop(name)
    def log(self, message): pass


def load_plugin(monkeypatch, tmp_path, *, activate_fake=True, mode=None):
    fake = FakeXP()
    monkeypatch.setitem(sys.modules, "xp", fake)
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3] / "xplane"))
    path = Path(__file__).parents[3] / "xplane/PI_capvsar_flight_control.py"
    spec = importlib.util.spec_from_file_location("fake_flight_control_plugin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"session": SESSION, "secret": "s" * 64, "mode": mode,
                                  "socket_path": f"/tmp/capvsar-flight-control-{SESSION}.sock"}))
    module.CONFIG = config
    if activate_fake:
        module.LIVE_PLUGIN_QUALIFIED = True  # fake SDK only; production constant stays closed
    plugin = module.PythonInterface()
    plugin.XPluginStart()
    return fake, plugin


def test_plugin_remains_inert_with_config_until_attended_qualification(monkeypatch, tmp_path):
    fake, plugin = load_plugin(monkeypatch, tmp_path, activate_fake=False)
    assert plugin.core is None and fake.accessors == {}
    assert plugin.XPluginEnable() == 1
    assert fake.writes == []
    plugin.XPluginStop()


def test_plugin_standby_candidates_do_not_touch_native_controls(monkeypatch, tmp_path):
    fake, plugin = load_plugin(monkeypatch, tmp_path)
    for channel in CHANNELS:
        ref = plugin.core.prefix + channel
        fake.accessors[ref]["writeFloat"](None, 0.2 if channel in ("throttle", "flap") else 0.0)
    assert not fake.writes
    answer = queue.Queue(maxsize=1)
    plugin.requests.put_nowait(({"action": "prepare", "owner": "ARDUPLANE",
                                "session": SESSION, "expected_generation": 0}, answer))
    plugin.flight_loop(0, 0, 0, None)
    assert answer.get()["state"] == "PREPARING"
    assert not fake.writes
    plugin.core.activate(SESSION, 1)
    assert fake.refs["sim/operation/override/override_joystick"] == 1
    assert any(ref == "sim/joystick/yoke_roll_ratio" for ref, _ in fake.writes)
    plugin.core.human_takeover("pilot")
    assert fake.refs["sim/operation/override/override_joystick"] == 0
    assert "sim/GPS/g1000n1_ap" not in fake.commands
    plugin.XPluginStop()


def test_plugin_fd_only_readback_does_not_claim_ap_engagement(monkeypatch, tmp_path):
    fake, plugin = load_plugin(monkeypatch, tmp_path)
    assert plugin.core.sink.ap_engaged() is False
    fake.refs["sim/cockpit2/autopilot/servos_on"] = 1
    assert plugin.core.sink.ap_engaged() is None
    plugin.XPluginStop()


def test_surface_sink_owns_toe_brakes_and_releases_them(monkeypatch, tmp_path):
    fake, plugin = load_plugin(monkeypatch, tmp_path)
    sink = type(plugin.core.sink)(landing=True, toe_brakes=True)
    sink.set_override(True)
    sink.write_control("brake", .7)
    assert sink.override_state() is True
    assert sink.read_brakes() == (.7, .7)
    assert fake.refs["sim/operation/override/override_toe_brakes"] == 1
    sink.set_override(False)
    assert sink.override_state() is False
    assert sink.read_brakes() == (0., 0.)
    plugin.XPluginStop()


def test_plugin_registers_fresh_candidate_namespace_on_verified_garmin_return(monkeypatch, tmp_path):
    fake, plugin = load_plugin(monkeypatch, tmp_path)
    for channel in CHANNELS:
        fake.accessors[plugin.core.prefix + channel]["writeFloat"](None, 0.0)
    plugin.core.prepare("ARDUPLANE", SESSION, 0)
    plugin.core.activate(SESSION, 1)
    plugin.core.transfer_gfc(1, ready=True)
    plugin.core.tick()
    assert plugin.core.status()["state"] == "GFC700"
    new_session = "f" * 32
    response = queue.Queue(maxsize=1)
    plugin.requests.put_nowait(({"action": "renew_session", "session": new_session,
                                "expected_generation": plugin.core.generation}, response))
    plugin.flight_loop(0, 0, 0, None)
    assert response.get()["session"] == new_session
    old = f"cap/flight_control/candidate/{SESSION}/roll"
    new = f"cap/flight_control/candidate/{new_session}/roll"
    assert old in fake.accessors and new in fake.accessors
    fake.accessors[old]["writeFloat"](None, 1.0)
    assert "roll" not in plugin.core.candidates
    fake.accessors[new]["writeFloat"](None, 0.25)
    assert plugin.core.candidates["roll"][0] == 0.25
    answer = queue.Queue(maxsize=1)
    plugin.requests.put_nowait(({"action": "set_virtual_aux", "channel": "throttle",
                                "value": 0.45, "session": new_session,
                                "expected_generation": plugin.core.generation}, answer))
    plugin.flight_loop(0, 0, 0, None)
    assert answer.get()["observed"] == 0.45
    assert fake.refs["sim/cockpit2/engine/actuators/throttle_ratio"][0] == 0.45
    plugin.XPluginStop()
