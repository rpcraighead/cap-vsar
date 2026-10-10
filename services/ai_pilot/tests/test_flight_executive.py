"""Offline executive and full-sortie workflow; telemetry is supplied by a peer."""
import pytest

from services.ai_pilot import mavlink_min as mav
from services.ai_pilot.arduplane_mission import FlightFix, GeoPoint, runway_sortie
from services.ai_pilot.flight_adapters import ArduPlaneMissionAdapter, GFC700Adapter, VirtualPilotPower
from services.ai_pilot.flight_executive import (
    Controller, FlightExecutive, FlightTask, Phase, Role, TaskKind,
)
from services.ai_pilot.mission_script import GarminSegment, MissionScript, SortieCriteria
from services.ai_pilot.phase_profiles import PhaseProfiles, RunwayCorridor
from services.ai_pilot.maneuvers import Observation
from services.ai_pilot.tests.test_arduplane_mission import Endpoint
from xplane.capvsar_flight_control_core import CHANNELS, ControlBridge

SESSION = "c" * 32


class Sim:
    def __init__(self):
        self.ap = False
        self.override = False
        self.paused = False
        self.writes = []
        self.controls = {}
    def ap_engaged(self): return self.ap
    def read_trim(self): return 0.0
    def override_state(self): return self.override
    def command_ap_off(self): self.ap = False
    def command_ap_on(self): self.ap = True
    def set_override(self, enabled): self.override = enabled
    def write_control(self, channel, value):
        self.writes.append((channel, value))
        self.controls[channel] = value
    def read_control(self, channel): return self.controls.get(channel)
    def pause(self): self.paused = True


class Backend:
    def select(self, heading, altitude): pass


def candidates(bridge):
    for channel in CHANNELS:
        bridge.candidate(bridge.session, channel,
                         0.25 if channel in ("throttle", "flap") else 0.0)


def build():
    clock = [0.0]
    sim = Sim()
    bridge = ControlBridge(sim, SESSION, clock=lambda: clock[0])
    candidates(bridge)
    peer = Endpoint()
    peer.inject_heartbeat(mav.PLANE_MODE_MANUAL)
    observed = {"telemetry_fresh": True, "candidate_ready": True,
                "on_ground": True, "agl_ft": 0.0, "groundspeed_kt": 0.0,
                "runway_ready": True, "configuration_verified": True,
                "engine_ready": True, "home_verified": True,
                "estimator_origin_verified": True, "human_clearance_confirmed": True,
                "within_fix_m": 9999.0, "approach_stable": False,
                "vvi_fpm": 0.0, "kias": 0.0, "roll_deg": 0.0,
                "altitude_indicated_ft": 4500.0, "age_seconds": 0.0,
                "latitude_deg": 32.8264, "longitude_deg": -116.9643}
    adapter = ArduPlaneMissionAdapter(Backend(), peer, lambda: observed,
                                      offline_protocol=True)
    profiles = PhaseProfiles(
        departure=RunwayCorridor(32.8264, -116.9643, 3000, 0, 140, 0, 35, "fixture"),
        arrival=RunwayCorridor(33.038, -116.907, 3000, 0, 140, 0, 35, "fixture"))
    executive = FlightExecutive(bridge, {Controller.ARDUPLANE: adapter}, phase_profiles=profiles,
                                clock=lambda: clock[0])
    return clock, sim, bridge, peer, observed, executive


def sortie(executive):
    departure = GeoPoint(32.8264, -116.9643, 388.0)
    route = (FlightFix(GeoPoint(32.9, -116.95, 500), 1200),
             FlightFix(GeoPoint(33.0, -116.92, 900), 1400))
    approach = FlightFix(GeoPoint(33.02, -116.91, 1300), 1600)
    landing = GeoPoint(33.038, -116.907, 1395)
    plan = runway_sortie(departure, route, approach, landing, 60)
    criteria = SortieCriteria(200, 100, 10, 5, 1600, 300)
    return MissionScript(executive, plan, criteria), plan


def test_full_sortie_waits_for_independent_observations_not_mock_flight_claims():
    clock, sim, bridge, peer, observed, executive = build()
    script, items = sortie(executive)
    script.start()
    for _ in range(40):
        clock[0] += 0.01
        candidates(bridge)
        active = executive.active_task
        if active:
            kind = active[1].kind
            p = active[1].parameters
            if kind == TaskKind.TAKEOFF:
                observed.update(on_ground=False, agl_ft=1250, kias=110)
            elif kind == TaskKind.WAYPOINT:
                peer.inject(mav.MSG_MISSION_CURRENT, {"seq": p["seq"], "total": len(items),
                                                      "mission_state": 1, "mission_mode": 1})
                peer.inject(mav.MSG_MISSION_ITEM_REACHED, {"seq": p["seq"]})
                observed["within_fix_m"] = 50
            elif kind == TaskKind.APPROACH:
                peer.inject(mav.MSG_MISSION_CURRENT, {"seq": p["seq"], "total": len(items),
                                                      "mission_state": 1, "mission_mode": 1})
                observed["approach_stable"] = True
            elif kind == TaskKind.LAND:
                observed.update(on_ground=True, agl_ft=0,
                                groundspeed_kt=0 if p.get("rollout") else 20,
                                ground_stop_confirmed=bool(p.get("rollout")),
                                latitude_deg=33.038, longitude_deg=-116.907)
        script.tick()
        if script.state == "COMPLETE":
            break
    assert script.state == "COMPLETE"
    assert len([e for e in executive.events if e["status"] == "achieved"]) == len(script.steps)
    assert executive.phase == Phase.ROLLOUT
    assert peer.custom_mode() == mav.PLANE_MODE_AUTO
    assert not sim.override and not sim.paused
    assert executive.controller == Controller.HUMAN


@pytest.mark.parametrize("return_problem", [None, "deferred", "premature",
                                          "old_link", "unarmed"])
def test_planned_garmin_segment_measures_capture_then_renews_arduplane_session(
        return_problem):
    clock, sim, bridge, peer, observed, executive = build()
    script, items = sortie(executive)
    class GarminBackend:
        def select(self, heading, altitude): pass
        def observe(self): return Observation(270, 4500, 1500, 110, 0, 0, 0)
    class Power:
        def ready_for(self, phase): return phase == Phase.TRANSIT
    readback = {"age_seconds": 0, "servos_on": 0, "flight_director_mode": 1,
                "lateral_selected": True, "vertical_selected": True,
                "lateral_active": False, "vertical_active": False}
    executive.adapters[Controller.GFC700] = GFC700Adapter(
        GarminBackend(), lambda: readback, clock=lambda: clock[0])
    executive.power = Power()
    renewals = []
    deferred_polls = []
    def complete_return(active_executive):
        nonlocal peer
        session = "f" * 32
        active_executive.renew_candidate_session(session,
                                                 active_executive.bridge_generation)
        renewals.append(session)
        candidates(bridge)
        if return_problem != "old_link":
            new_peer = Endpoint()
            new_peer.inject_heartbeat(mav.PLANE_MODE_MANUAL,
                base_mode=1 if return_problem == "unarmed" else
                mav.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED | mav.MAV_MODE_FLAG_SAFETY_ARMED)
            active_executive.adapters[Controller.ARDUPLANE].resume_on_new_link(
                new_peer, items, 2)
            peer = new_peer
        if return_problem == "premature":
            peer.inject(mav.MSG_MISSION_CURRENT, {"seq": 2, "total": len(items),
                        "mission_state": 1, "mission_mode": 1})
            peer.inject(mav.MSG_MISSION_ITEM_REACHED, {"seq": 2})
        return session
    class DeferredReturn:
        def poll(self, active_executive):
            deferred_polls.append(clock[0])
            if len(deferred_polls) < 3:
                return None
            return complete_return(active_executive)
        def cancel(self): return []
    def prepare_return(active_executive):
        if return_problem == "deferred":
            return DeferredReturn()
        return complete_return(active_executive)
    script = MissionScript(executive, items, script.criteria,
                           garmin_segment=GarminSegment(3, 270, 4500, 1000,
                                                        prepare_return, 10))
    script.start()
    for _ in range(70):
        clock[0] += 0.2
        candidates(bridge)
        if script.state == "TRANSFERRING_GARMIN":
            readback.update(servos_on=1, flight_director_mode=2,
                            lateral_active=True, vertical_active=True)
        active = executive.active_task
        if active:
            kind, p = active[1].kind, active[1].parameters
            if kind == TaskKind.TAKEOFF:
                observed.update(on_ground=False, agl_ft=1250, kias=110)
            elif kind == TaskKind.WAYPOINT:
                peer.inject(mav.MSG_MISSION_CURRENT, {"seq": p["seq"],
                           "total": len(items), "mission_state": 1, "mission_mode": 1})
                peer.inject(mav.MSG_MISSION_ITEM_REACHED, {"seq": p["seq"]})
                observed["within_fix_m"] = 50
            elif kind == TaskKind.APPROACH:
                peer.inject(mav.MSG_MISSION_CURRENT, {"seq": p["seq"],
                           "total": len(items), "mission_state": 1, "mission_mode": 1})
                observed["approach_stable"] = True
            elif kind == TaskKind.LAND:
                observed.update(on_ground=True, agl_ft=0,
                                groundspeed_kt=0 if p.get("rollout") else 20,
                                ground_stop_confirmed=bool(p.get("rollout")),
                                latitude_deg=33.038, longitude_deg=-116.907)
        script.tick()
        if script.state in ("COMPLETE", "ABORTED_TO_HUMAN"):
            break
    if return_problem not in (None, "deferred"):
        assert script.state == "ABORTED_TO_HUMAN"
        assert executive.status()["controller"] == "HUMAN"
        assert not sim.override and not sim.ap
        return
    assert script.state == "COMPLETE"
    assert script.segment_state == "DONE" and renewals == ["f" * 32]
    if return_problem == "deferred":
        assert len(deferred_polls) == 3
        assert all(event["status"] != "fault" for event in executive.events)
    assert bridge.session == "f" * 32 and SESSION in bridge.used_sessions
    assert any(event["status"] == "achieved" and event.get("task") == "HEADING_ALTITUDE"
               for event in executive.events)
    assert not sim.override and not sim.ap


def test_planned_garmin_segment_refuses_below_floor_and_returns_to_human():
    clock, sim, bridge, peer, observed, executive = build()
    script, items = sortie(executive)
    script = MissionScript(executive, items, script.criteria,
        garmin_segment=GarminSegment(3, 270, 4500, 1500,
                                     lambda _: (_ for _ in ()).throw(
                                         AssertionError("return must not run"))))
    script.start()
    for _ in range(15):
        clock[0] += 0.01
        candidates(bridge)
        active = executive.active_task
        if active:
            kind, p = active[1].kind, active[1].parameters
            if kind == TaskKind.TAKEOFF:
                observed.update(on_ground=False, agl_ft=1250, kias=110)
            elif kind == TaskKind.WAYPOINT:
                peer.inject(mav.MSG_MISSION_CURRENT, {"seq": p["seq"],
                           "total": len(items), "mission_state": 1, "mission_mode": 1})
                peer.inject(mav.MSG_MISSION_ITEM_REACHED, {"seq": p["seq"]})
                observed["within_fix_m"] = 50
        script.tick()
        if script.state == "ABORTED_TO_HUMAN":
            break
    assert script.state == "ABORTED_TO_HUMAN"
    assert executive.status()["controller"] == "HUMAN"
    assert not sim.ap and not sim.override


def test_landing_timeout_requests_go_around_and_never_reports_sortie_complete():
    clock, sim, bridge, peer, observed, executive = build()
    script, items = sortie(executive)
    script.start()
    executive.tick()
    adapter = executive.adapters[Controller.ARDUPLANE]
    adapter.uploader.upload(items)
    adapter.uploader.start_auto()
    adapter.started = True
    observed.update(on_ground=False, agl_ft=100,
                    latitude_deg=33.038, longitude_deg=-116.907)
    # Prove an approach/landing timeout takes an explicit command and measured
    # climb path rather than falling through to an achieved landing.
    executive.phase = Phase.LAND
    task = FlightTask(TaskKind.LAND, {"max_agl_ft": 10,
        "go_around_altitude_m_msl": 1600, "go_around_min_agl_ft": 300},
        0.1, on_timeout="go_around")
    executive.submit_task(executive.lease, 1, task)
    clock[0] = 0.2
    candidates(bridge)
    executive.tick()
    assert executive.status()["task"] == TaskKind.GO_AROUND.value
    assert mav.MAV_CMD_DO_GO_AROUND in peer.sent_commands()
    assert not any(e["status"] == "achieved" and e.get("task") == "LAND"
                   for e in executive.events)


def test_rollout_speed_alone_does_not_confirm_ground_stop():
    _, _, _, _, _, executive = build()
    adapter = executive.adapters[Controller.ARDUPLANE]
    task = FlightTask(TaskKind.LAND,
                      {"rollout": True, "max_groundspeed_kt": 5}, 10)
    observation = {"on_ground": True, "groundspeed_kt": 0}
    assert not adapter.achieved(task, observation)
    observation["ground_stop_confirmed"] = True
    assert adapter.achieved(task, observation)


def test_takeover_during_preparation_never_auto_engages_garmin():
    _, sim, bridge, _, _, executive = build()
    executive.request_mode(Role.AI_MISSION, Phase.TAKEOFF,
                           Controller.ARDUPLANE, "runway_sortie")
    executive.human_takeover("pilot yoke")
    assert executive.status()["controller"] == "HUMAN"
    assert bridge.retired and not sim.override and not sim.ap
    with pytest.raises(ValueError):
        executive.transfer_control(Controller.ARDUPLANE, bridge.generation)


def test_repeated_sequence_and_invalid_role_controller_are_refused():
    _, _, bridge, _, _, executive = build()
    with pytest.raises(ValueError, match="Unsupported"):
        executive.request_mode(Role.AI_MISSION, Phase.LAND, Controller.GFC700, "land")
    executive.request_mode(Role.AI_MISSION, Phase.TAKEOFF,
                           Controller.ARDUPLANE, "runway_sortie")
    executive.transfer_control(Controller.ARDUPLANE, bridge.generation)
    executive.tick()
    before = len(bridge.sink.writes)
    with pytest.raises(ValueError, match="not permitted"):
        executive.submit_task(executive.lease, 1,
                              FlightTask(TaskKind.SET_POWER, {"fraction": 0.5}, 2))
    assert len(bridge.sink.writes) == before
    task = FlightTask(TaskKind.UPLOAD_MISSION, {"items": sortie(executive)[1]}, 10)
    executive.submit_task(executive.lease, 1, task)
    with pytest.raises(ValueError, match="repeated"):
        executive.submit_task(executive.lease, 1, task)


def test_garmin_adapter_needs_servo_and_fd_mode_two_after_commit():
    class GarminBackend:
        def select(self, heading, altitude): pass
        def observe(self): return Observation(270, 4500, 1500, 110, 0, 0, 0)
    state = {"age_seconds": 0, "servos_on": 0, "flight_director_mode": 1,
             "lateral_selected": True, "vertical_selected": True,
             "lateral_active": False, "vertical_active": False}
    adapter = GFC700Adapter(GarminBackend(), lambda: state)
    adapter.prepare(Phase.TRANSIT, "cruise")
    assert adapter.ready()
    with pytest.raises(ValueError, match="did not confirm"):
        adapter.activate()
    state.update(servos_on=1, flight_director_mode=2,
                 lateral_active=True, vertical_active=True)
    adapter.activate()


def test_explicit_arduplane_to_garmin_transfer_requires_power_and_mode_readback():
    clock, sim, bridge, peer, observed, executive = build()
    class GarminBackend:
        def select(self, heading, altitude): pass
        def observe(self): return Observation(270, 4500, 1500, 110, 0, 0, 0)
    class Power:
        def ready_for(self, phase): return phase == Phase.TRANSIT
    readback = {"age_seconds": 0, "servos_on": 0, "flight_director_mode": 1,
                "lateral_selected": True, "vertical_selected": True,
                "lateral_active": False, "vertical_active": False}
    executive.adapters[Controller.GFC700] = GFC700Adapter(GarminBackend(), lambda: readback)
    executive.request_mode(Role.AI_MISSION, Phase.TAKEOFF,
                           Controller.ARDUPLANE, "runway_sortie")
    executive.transfer_control(Controller.ARDUPLANE, bridge.generation)
    executive.tick()
    with pytest.raises(ValueError, match="power/configuration"):
        executive.request_mode(Role.AI_MISSION, Phase.TRANSIT, Controller.GFC700, "cruise")
    executive.power = Power()
    executive.request_mode(Role.AI_MISSION, Phase.TRANSIT, Controller.GFC700, "cruise")
    executive.transfer_control(Controller.GFC700, bridge.generation)
    assert executive.status()["transfer"] == "VERIFYING"
    assert not sim.override and sim.ap
    readback.update(servos_on=1, flight_director_mode=2,
                    lateral_active=True, vertical_active=True)
    executive.tick()
    assert executive.status()["controller"] == "GFC700"
    assert executive.status()["allocation"]["throttle"] == "VIRTUAL_PILOT"
    executive.power = VirtualPilotPower(bridge, lambda: {
        "age_seconds": 0, "throttle": sim.controls.get("throttle"),
        "flap_ratio": sim.controls.get("flap")}, qualified=True)
    executive.submit_task(executive.lease, 1,
                          FlightTask(TaskKind.SET_POWER, {"fraction": 0.42}, 2))
    executive.tick()
    assert sim.controls["throttle"] == 0.42
    assert any(event["status"] == "achieved" and event.get("task") == "SET_POWER"
               for event in executive.events)
    new_session = "f" * 32
    old_generation = bridge.generation
    executive.renew_candidate_session(new_session, old_generation)
    observed.update(on_ground=False, agl_ft=1500, kias=110)
    for channel in CHANNELS:
        bridge.candidate(new_session, channel, 0.25 if channel in ("throttle", "flap") else 0.0)
    executive.request_mode(Role.AI_MISSION, Phase.TRANSIT,
                           Controller.ARDUPLANE, "cruise")
    executive.transfer_control(Controller.ARDUPLANE, bridge.generation)
    assert executive.status()["transfer"] == "VERIFYING"
    executive.tick()
    assert executive.status()["controller"] == "ARDUPLANE"
    assert sim.override and not sim.ap


def test_human_takeover_during_active_sortie_cannot_complete_or_toggle_garmin():
    clock, sim, bridge, peer, observed, executive = build()
    script, _ = sortie(executive)
    script.start()
    script.tick()
    assert sim.override
    executive.human_takeover("pilot yoke")
    script.tick()
    assert script.state == "CANCELED_TO_HUMAN"
    assert not sim.override and not sim.ap


def test_dive_entry_refuses_ordinary_controller_transfer():
    _, sim, bridge, _, observed, executive = build()
    class Power:
        def ready_for(self, phase): return True
    class Garmin:
        def prepare(self, phase, profile): raise AssertionError("should not prepare")
    executive.power = Power()
    executive.adapters[Controller.GFC700] = Garmin()
    executive.request_mode(Role.AI_MISSION, Phase.TAKEOFF,
                           Controller.ARDUPLANE, "runway_sortie")
    executive.transfer_control(Controller.ARDUPLANE, bridge.generation)
    executive.tick()
    observed["vvi_fpm"] = -3706.5
    with pytest.raises(ValueError, match="not stable"):
        executive.request_mode(Role.AI_MISSION, Phase.TRANSIT,
                               Controller.GFC700, "cruise")
    assert sim.override


def test_typed_task_rejects_hidden_truth_and_freezes_parameters():
    with pytest.raises(ValueError, match="Unknown"):
        FlightTask(TaskKind.HEADING_ALTITUDE, {
            "heading_mag": 90, "altitude_indicated_ft": 4500,
            "hidden_beacon_position": (0, 0)}, 10)
    parameters = {"heading_mag": 90, "altitude_indicated_ft": 4500}
    task = FlightTask(TaskKind.HEADING_ALTITUDE, parameters, 10)
    parameters["heading_mag"] = 180
    assert task.parameters["heading_mag"] == 90
    with pytest.raises(TypeError):
        task.parameters["heading_mag"] = 270


def test_sortie_refuses_unobserved_ground_readiness_before_any_authority():
    _, sim, bridge, _, observed, executive = build()
    script, _ = sortie(executive)
    observed["human_clearance_confirmed"] = False
    with pytest.raises(ValueError, match="runway clearance"):
        script.start()
    assert bridge.status()["state"] == "MANUAL"
    assert not sim.writes


def test_independent_bridge_human_takeover_revokes_script_lease():
    _, sim, bridge, _, _, executive = build()
    script, _ = sortie(executive)
    script.start()
    script.tick()
    bridge.human_takeover("physical pilot switch")
    script.tick()
    assert script.state == "CANCELED_TO_HUMAN"
    assert executive.status()["lease"] is None
    assert not sim.override and not sim.ap


def test_rejected_auto_start_faults_sortie_without_takeoff_success():
    _, sim, bridge, peer, _, executive = build()
    script, _ = sortie(executive)
    script.start()
    script.tick()  # upload task started and acknowledged
    peer.ack_overrides[mav.MAV_CMD_DO_SET_MODE] = mav.MAV_RESULT_DENIED
    script.tick()  # upload achieved; rejected AUTO start faults before takeoff
    assert script.state == "FAULTED"
    assert not any(event["status"] == "achieved" and event.get("task") == "TAKEOFF"
                   for event in executive.events)
