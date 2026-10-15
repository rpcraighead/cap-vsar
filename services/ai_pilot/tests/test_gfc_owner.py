"""The GFC 700 as a second owner of the mission bridge, end to end on a fake SDK.

Everything runs through the real plugin dispatch (`flight_loop`), the real core
and sink, and a fake X-Plane that models the autopilot toggles that matter:
the heading, vertical-speed and altitude-hold commands flip their state bits, and
engaging vertical speed zeroes the selected rate.
"""
import hashlib
import math
import queue
import sys
import time

import pytest

from services.ai_pilot.gfc_owner import AP_ALT_HOLD, AP_HDG, AP_VS, GfcOwner, GfcOwnerError
from services.ai_pilot.terrain_guard import FT_PER_M, TerrainGuard
from services.ai_pilot.tests.test_flight_control_bridge import SESSION, Simulator
from services.ai_pilot.tests.test_flight_control_plugin import load_plugin
from xplane.capvsar_flight_control_core import ControlBridge
from xplane.capvsar_mission import AIRBORNE_MAX_ALTITUDE_FT
from xplane.capvsar_terrain import TerrainScanner, scan
from xplane.capvsar_telemetry import Telemetry

AP_STATE = "sim/cockpit/autopilot/autopilot_state"
HDG_BUG = "sim/cockpit/autopilot/heading_mag"
ALT_BUG = "sim/cockpit/autopilot/altitude"
VS_BUG = "sim/cockpit/autopilot/vertical_velocity"
THROTTLE = "sim/cockpit2/engine/actuators/throttle_ratio"
LAT, LON = 32.9, -117.0
FRAME = {"roll": 0., "pitch": 0., "yaw": 0., "throttle": .6, "flap": 0., "trim": 0., "brake": 0.}


def ridge_terrain(east_nm, height_ft, floor_ft=500., width_nm=1.0):
    def terrain_ft(lat, lon):
        east = (lon - LON) * 60.0 * math.cos(math.radians(LAT))
        return height_ft if abs(east - east_nm) <= width_nm / 2 else floor_ft
    return terrain_ft


class Rig:
    """A mission-mode plugin on a fake SDK, already ACTIVE under the DIRECT owner."""

    def __init__(self, monkeypatch, tmp_path, *, terrain=None, backstop=None, gfc_owner=True,
                 defer_vs_zero=False):
        self.xp, self.plugin = load_plugin(monkeypatch, tmp_path)
        xp, plugin = self.xp, self.plugin
        # The plugin imports its siblings as top-level modules; use those same
        # classes so its isinstance checks see the lab built here.
        capvsar_mission, capvsar_qualification = (sys.modules["capvsar_mission"],
                                                  sys.modules["capvsar_qualification"])
        aircraft = tmp_path / capvsar_qualification.STOCK_NAME
        aircraft.write_text("stock fixture")
        monkeypatch.setattr(capvsar_qualification, "STOCK_SHA256",
                            hashlib.sha256(aircraft.read_bytes()).hexdigest())
        xp.getNthAircraftModel = lambda _index: (aircraft.name, str(aircraft))
        self.pending_zero = False
        self.defer_vs_zero = defer_vs_zero
        xp.refs.update({AP_STATE: 0, HDG_BUG: 0., ALT_BUG: 0., VS_BUG: 0.,
                        "sim/flightmodel/position/latitude": LAT,
                        "sim/flightmodel/position/longitude": LON,
                        "sim/flightmodel/position/y_agl": 900.,
                        "sim/flightmodel/position/elevation": 4000. / FT_PER_M,
                        "sim/cockpit2/gauges/indicators/altitude_ft_pilot": 4060.,
                        "sim/flightmodel/position/indicated_airspeed": 100.,
                        "sim/flightmodel/position/groundspeed": 51.,
                        "sim/flightmodel/position/hpath": 90.,
                        "sim/flightmodel/position/psi": 90.,
                        "sim/flightmodel/position/mag_psi": 80.,
                        "sim/flightmodel/failures/onground_any": 0,
                        "sim/time/total_flight_time_sec": 100.})
        real_command = xp.commandOnce

        def command(name):
            real_command(name)
            state = int(xp.refs[AP_STATE])
            if name == "sim/autopilot/heading":
                xp.refs[AP_STATE] = state ^ AP_HDG
            elif name == "sim/autopilot/altitude_hold":
                xp.refs[AP_STATE] = (state & ~AP_VS) ^ AP_ALT_HOLD
            elif name == "sim/autopilot/vertical_speed":
                xp.refs[AP_STATE] = (state & ~AP_ALT_HOLD) ^ AP_VS
                if defer_vs_zero:
                    self.pending_zero = True       # the zeroing lands after our write
                else:
                    xp.refs[VS_BUG] = 0.           # engaging VS zeroes the rate
        xp.commandOnce = command
        config = {"aircraft_path": str(aircraft), "expires_unix_s": time.time() + 1000,
                  "gfc_owner": gfc_owner, "protocol": "atomic-v1", "secret": "s" * 64,
                  **({"terrain_backstop_ft": backstop} if backstop else {})}
        plugin.config = {**plugin.config, **config}
        sink = type(plugin.core.sink)(landing=True, toe_brakes=True, gfc=True)
        plugin.core = ControlBridge(sink, SESSION, atomic=True, brake_max=1.,
                                    channels=("roll", "pitch", "yaw", "throttle", "flap", "trim", "brake"))
        scanner = TerrainScanner(terrain, time.monotonic) if terrain else None
        plugin.telemetry = Telemetry(xp, sink, SESSION, terrain=scanner)
        plugin.lab = capvsar_mission.MissionLab(xp, sink, config)
        plugin.lab_sessions.add(SESSION)
        core = plugin.core
        core.submit_frame(SESSION, 0, 1, core.clock() + .18, FRAME)
        prepared = core.prepare("DIRECT", SESSION, 0)
        core.submit_frame(SESSION, prepared["generation"], 2, core.clock() + .18, FRAME)
        core.activate(SESSION, prepared["generation"])
        assert core.state == "ACTIVE"
        plugin.lab.resume_pending = False
        plugin.lab.trial_started = time.monotonic()

    def request(self, action, **fields):
        xp = self.xp
        xp.refs["sim/time/total_flight_time_sec"] += 0.05
        if self.pending_zero:
            xp.refs[VS_BUG], self.pending_zero = 0., False
        self.plugin.capture_loop(0, 0, 1, None)
        answer = queue.Queue(maxsize=1)
        self.plugin.requests.put(({"action": action, **fields}, answer, time.monotonic() + .2))
        self.plugin.flight_loop(0, 0, 0, None)
        result = answer.get_nowait()
        if "error" in result:
            raise RuntimeError(result["error"])
        return result

    request.__doc__ = "BridgeClient.request, minus the socket."

    @property
    def state(self):
        return self.plugin.core.state


@pytest.fixture
def rig(monkeypatch, tmp_path):
    return Rig(monkeypatch, tmp_path)


def owner_for(rig):
    return GfcOwner(rig, sleep=lambda _s: None)


def test_engage_hands_the_airplane_to_the_autopilot_with_modes_taken_by_command(rig):
    owner = owner_for(rig)
    status = owner.engage(heading_mag=80., altitude_ft=4060., vs_fpm=None)
    assert status["state"] == "GFC700" and rig.plugin.core.owner == "GFC700"
    xp = rig.xp
    assert xp.refs[HDG_BUG] == 80. and xp.refs[ALT_BUG] == 4060.
    assert int(xp.refs[AP_STATE]) & AP_HDG and int(xp.refs[AP_STATE]) & AP_ALT_HOLD
    assert xp.refs["sim/operation/override/override_joystick"] == 0   # actuators released
    assert "sim/GPS/g1000n1_ap" in xp.commands
    assert owner.problems(rig.request("snapshot")) == []


def test_modes_are_toggles_so_a_second_selection_does_not_switch_them_off(rig):
    owner = owner_for(rig)
    owner.engage(80., 4060.)
    owner.select(heading_mag=120., altitude_ft=4060.)
    state = int(rig.xp.refs[AP_STATE])
    assert state & AP_HDG and state & AP_ALT_HOLD and rig.xp.refs[HDG_BUG] == 120.


def test_engage_needs_direct_ownership(rig):
    owner = owner_for(rig)
    owner.engage(80., 4060.)
    with pytest.raises(GfcOwnerError, match="needs DIRECT ownership"):
        owner.engage(80., 4060.)


def test_transfer_is_refused_on_the_ground_or_low(rig):
    rig.xp.refs["sim/flightmodel/position/y_agl"] = 100.
    with pytest.raises(RuntimeError, match="established airborne flight"):
        owner_for(rig).engage(80., 4060.)
    assert rig.state == "ACTIVE" and rig.xp.refs["sim/cockpit2/autopilot/servos_on"] == 0


def test_gfc_actions_do_not_exist_unless_the_session_was_staged_for_them(monkeypatch, tmp_path):
    rig = Rig(monkeypatch, tmp_path, gfc_owner=False)
    with pytest.raises(RuntimeError, match="Action unavailable"):
        rig.request("transfer_gfc", generation=rig.plugin.core.generation, ready=True)


def test_autopilot_flight_stays_inside_the_mission_envelope(rig):
    owner_for(rig).engage(80., 4060.)
    rig.xp.refs["sim/flightmodel/position/latitude"] = 31.0     # far outside both boxes
    rig.plugin.capture_loop(0, 0, 2, None)
    assert rig.state in ("PAUSED_FAULT", "FAULT_PAUSE_PENDING")
    assert "telemetry capture failed" in rig.plugin.core.fault_reason.lower()


def test_silent_executive_loses_the_autopilot_to_the_heartbeat_watchdog(rig):
    owner_for(rig).engage(80., 4060.)
    core = rig.plugin.core
    core.last_heartbeat -= 1.0                       # no keepalive for a second
    rig.plugin.flight_loop(0, 0, 0, None)
    assert core.state in ("PAUSED_FAULT", "FAULT_PAUSE_PENDING")
    assert "heartbeat" in core.fault_reason.lower()


def test_hand_back_returns_the_actuators_in_one_callback_with_a_new_session(rig):
    owner = owner_for(rig)
    owner.engage(80., 4060.)
    old_session = rig.plugin.core.session
    session, generation, sequence = owner.hand_back({**FRAME, "throttle": .7})
    core = rig.plugin.core
    assert core.state == "ACTIVE" and core.owner == "DIRECT" and core.session == session
    assert session != old_session and session in rig.plugin.lab_sessions
    assert rig.xp.refs["sim/cockpit2/autopilot/servos_on"] == 0
    assert rig.xp.refs["sim/operation/override/override_joystick"] == 1
    # the loop the runner continues with: exchange under the new session
    reply = rig.request("exchange", session=session, generation=generation, sequence=sequence + 1,
                        expires_at=time.monotonic() + .18, controls={**FRAME, "throttle": .7})
    assert reply["bridge"]["state"] == "ACTIVE"
    assert rig.xp.refs["sim/flightmodel/engine/ENGN_thro_use"][0] == pytest.approx(.7)


def test_hand_back_needs_gfc_ownership_and_a_fresh_session(rig):
    with pytest.raises(RuntimeError, match="requires GFC 700 ownership"):
        owner_for(rig).hand_back(FRAME)
    owner = owner_for(rig)
    owner.engage(80., 4060.)
    with pytest.raises(RuntimeError, match="Fresh hand-back snapshot|new session"):
        rig.request("lab_handback", session=SESSION, controls=FRAME, snapshot_frame=1,
                    snapshot_wall_time_s=time.monotonic() - 5)


def test_the_guard_raises_the_autopilots_altitude_and_orders_full_power(monkeypatch, tmp_path):
    rig = Rig(monkeypatch, tmp_path, terrain=ridge_terrain(3.0, 3600.))
    owner = owner_for(rig)
    owner.engage(80., 4060.)
    guard = TerrainGuard(ceiling_ft=AIRBORNE_MAX_ALTITUDE_FT - 500)
    advice = owner.step(rig.request("snapshot"), heading_mag=80., altitude_ft=4060., guard=guard,
                        cruise_throttle=.7)
    xp = rig.xp
    assert advice.floor_indicated_ft == pytest.approx(5560.)       # 3,600 + 1,500 -> 5,500 MSL
    assert xp.refs[ALT_BUG] == 5560. and xp.refs[VS_BUG] == 700.      # 400 ft of air: urgent
    assert int(xp.refs[AP_STATE]) & AP_VS
    assert xp.refs[THROTTLE][0] == pytest.approx(1.0)
    # once the airplane is well above the ridge the floor holds and power returns to cruise
    xp.refs["sim/flightmodel/position/elevation"] = 5500. / FT_PER_M
    xp.refs["sim/cockpit2/gauges/indicators/altitude_ft_pilot"] = 5560.
    later = owner.step(rig.request("snapshot"), heading_mag=80., altitude_ft=4060., guard=guard,
                       cruise_throttle=.7)
    assert later.floor_indicated_ft == pytest.approx(5560.) and not later.full_power
    assert xp.refs[THROTTLE][0] == pytest.approx(.7)


def test_beyond_the_leash_the_guard_replaces_the_heading_with_a_course_home(monkeypatch, tmp_path):
    rig = Rig(monkeypatch, tmp_path, terrain=ridge_terrain(40., 600.))
    owner = owner_for(rig)
    owner.engage(80., 4060.)
    rig.xp.refs["sim/flightmodel/position/longitude"] = LON + 0.2     # ~10 nm east of the area
    guard = TerrainGuard(leash=(LAT, LON, 8.))
    owner.step(rig.request("snapshot"), heading_mag=80., altitude_ft=4060., guard=guard)
    # home is true 270; magnetic = true - (psi - mag_psi) = 260
    assert rig.xp.refs[HDG_BUG] == pytest.approx(260., abs=1.)


def test_a_selection_the_autopilot_zeroed_is_re_sent_and_a_refusal_is_reported(monkeypatch, tmp_path):
    now = [100.]
    rig = Rig(monkeypatch, tmp_path, defer_vs_zero=True)
    owner = GfcOwner(rig, clock=lambda: now[0], sleep=lambda _s: None)
    owner.engage(80., 4060.)
    owner.select(altitude_ft=6000., vs_fpm=500.)      # engaging VS zeroes the rate, after our write
    snap = rig.request("snapshot")
    assert any("vertical-speed bug" in p for p in owner.problems(snap))
    now[0] += 2.0
    owner.verify(rig.request("snapshot"))              # re-sends
    assert rig.xp.refs[VS_BUG] == 500.
    assert owner.problems(rig.request("snapshot")) == []
    # an autopilot that never takes the heading is reported after MAX_RESELECTS tries
    rig.xp.refs[AP_STATE] = int(rig.xp.refs[AP_STATE]) & ~AP_HDG
    rig.xp.commandOnce = lambda name: None
    owner.selected = {"heading_mag": 200.}
    owner._awaiting = (now[0] - 1, 0)
    with pytest.raises(GfcOwnerError, match="not taken"):
        for _ in range(6):
            now[0] += 2.0
            owner.verify(rig.request("snapshot"))


def test_core_fences_the_selection(rig):
    owner_for(rig).engage(80., 4060.)
    core = rig.plugin.core
    with pytest.raises(ValueError, match="no current Garmin authority"):
        core.gfc_select(SESSION, core.generation - 1, heading_mag=90.)
    with pytest.raises(ValueError, match="no current Garmin authority"):
        core.gfc_select("c" * 32, core.generation, heading_mag=90.)
    for bad in ({"heading_mag": 361.}, {"altitude_ft": 100.}, {"altitude_ft": 5000., "vs_fpm": 2000.},
                {"vs_fpm": 500.}, {}, {"heading_mag": float("nan")}):
        with pytest.raises(ValueError):
            core.gfc_select(core.session, core.generation, **bad)
    assert core.state == "GFC700"                      # a refused request is not a fault
    with pytest.raises(ValueError, match="no current Garmin authority"):
        ControlBridge(Simulator(), SESSION, atomic=True).gfc_select(SESSION, 0, heading_mag=90.)


def test_core_pauses_when_the_autopilot_does_not_read_back_the_selection(rig):
    owner_for(rig).engage(80., 4060.)
    core = rig.plugin.core
    core.sink.gfc_select = lambda *_a: {"heading_bug": 10., "altitude_bug": 0., "vs_bug": 0.}
    with pytest.raises(ValueError, match="not observed"):
        core.gfc_select(core.session, core.generation, heading_mag=90.)
    assert core.state in ("PAUSED_FAULT", "FAULT_PAUSE_PENDING")


def snapshot_for(lab, *, agl_ft=3000., msl_ft=5000., ahead_ft=4900., ahead_nm=1.0, age=0.5):
    return {"values": {"on_ground": 0, "agl_m": agl_ft * .3048, "altitude_msl_m": msl_ft * .3048},
            "terrain": {"valid": True, "ahead_max_ft": ahead_ft, "ahead_max_nm": ahead_nm,
                        "age_s": age, "under_ft": 0.}}


def test_terrain_backstop_pauses_only_when_high_above_the_ground_and_close(rig):
    lab = rig.plugin.lab
    lab.check_terrain(snapshot_for(lab))                    # fence not configured: silent
    lab.terrain_backstop_ft = 200.
    with pytest.raises(ValueError, match="Terrain 4900 ft at 1.0 nm"):
        lab.check_terrain(snapshot_for(lab))
    lab.check_terrain(snapshot_for(lab, ahead_nm=3.0))       # far
    lab.check_terrain(snapshot_for(lab, ahead_ft=4000.))     # 1,000 ft of air
    lab.check_terrain(snapshot_for(lab, agl_ft=400.))        # low: approach, not cruise
    lab.check_terrain(snapshot_for(lab, age=9.))             # stale scan is ignored, not trusted
    with pytest.raises(ValueError, match="terrain_backstop_ft"):
        type(lab)(rig.xp, rig.plugin.core.sink, {**rig.plugin.config, "terrain_backstop_ft": 5})


def test_telemetry_carries_the_terrain_scan_and_the_autopilot_selections(monkeypatch, tmp_path):
    rig = Rig(monkeypatch, tmp_path, terrain=ridge_terrain(4.0, 5200.))
    snap = rig.request("snapshot")
    assert snap["terrain"]["valid"] and snap["terrain"]["ahead_max_ft"] == 5200.
    assert snap["terrain"]["ahead_max_nm"] == pytest.approx(4.0, abs=0.5)
    assert {"ap_state", "ap_heading_bug_deg", "ap_altitude_bug_ft", "ap_vs_bug_fpm",
            "track_true_deg"} <= set(snap["values"])
    assert scan(ridge_terrain(4.0, 5200.), LAT, LON, 90.)["ahead_max_ft"] == 5200.


def test_a_floor_above_the_envelope_ceiling_turns_back_instead_of_pausing_the_sim(monkeypatch, tmp_path):
    rig = Rig(monkeypatch, tmp_path, terrain=ridge_terrain(4.0, 5200.))
    owner = owner_for(rig)
    owner.engage(80., 4060.)
    guard = TerrainGuard(ceiling_ft=AIRBORNE_MAX_ALTITUDE_FT - 500)
    advice = owner.step(rig.request("snapshot"), heading_mag=80., altitude_ft=4060., guard=guard)
    assert advice.turn_back and "ceiling" in advice.reason
    assert rig.state == "GFC700"
