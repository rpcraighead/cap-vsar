"""Landing brake lease, geometry and independent touchdown/stop criteria."""
import math

import pytest

from xplane.capvsar_flight_control_core import CHANNELS, ControlBridge
from xplane.capvsar_landing import (FAR_END, HEADING_TRUE_DEG, RUNWAY_LENGTH_M,
                                   THRESHOLD, runway_coordinates)
from services.ai_pilot.landing_trial import LandingController, LandingObserver


def test_kmyf_28r_geometry_uses_installed_runway_direction():
    assert runway_coordinates(*THRESHOLD) == pytest.approx((0, 0))
    along, cross = runway_coordinates(*FAR_END)
    assert along == pytest.approx(RUNWAY_LENGTH_M)
    assert cross == pytest.approx(0, abs=1e-8)
    assert 294 < HEADING_TRUE_DEG < 296
    assert 1390 < RUNWAY_LENGTH_M < 1420


def test_atomic_landing_frame_caps_brake_and_fault_releases_it():
    class Sink:
        def __init__(self):
            self.override = False
            self.paused = False
            self.brake = 0.
        def ap_engaged(self): return False
        def override_state(self): return self.override
        def set_override(self, enabled):
            self.override = enabled
            if not enabled: self.brake = 0.
        def write_control(self, channel, value):
            if channel == "brake": self.brake = value
        def pause(self): self.paused = True
        def is_paused(self): return self.paused
    now = [0.]
    sink = Sink()
    bridge = ControlBridge(sink, "a" * 32, clock=lambda: now[0], atomic=True,
                           channels=CHANNELS + ("brake",))
    controls = {c: 0. for c in CHANNELS + ("brake",)}
    controls["throttle"] = .25
    controls["brake"] = .32
    bridge.submit_frame(bridge.session, 0, 1, .18, controls)
    bridge.prepare("DIRECT", bridge.session, 0)
    bridge.submit_frame(bridge.session, 1, 2, .18, controls)
    bridge.activate(bridge.session, 1)
    assert sink.override and sink.brake == .32
    controls["brake"] = .36
    with pytest.raises(ValueError, match="brake"):
        bridge.submit_frame(bridge.session, 1, 3, .18, controls)
    now[0] = .19
    bridge.tick()
    assert sink.paused and not sink.override and sink.brake == 0.
    assert bridge.status()["retired"]


def snapshot(along, cross=0., ground=0, gs_kt=70., brake=0., sim=1., frame=1,
             agl_ft=100., vvi=-350., flap=1., pitch_deg=2.,
             wind_mps=0., wind_from_true_deg=HEADING_TRUE_DEG, heading_deg=HEADING_TRUE_DEG,
             beta_deg=0., roll_deg=0., roll_control=0.):
    from xplane.capvsar_landing import M_PER_DEG_LAT, M_PER_DEG_LON, UNIT_N, UNIT_E
    north = along * UNIT_N - cross * UNIT_E
    east = along * UNIT_E + cross * UNIT_N
    return {"schema": "capvsar.telemetry.v1", "phase": "after_flight_model",
            "session": "a" * 32, "frame": frame, "wall_time_s": sim,
            "aircraft": {"name": "Cessna_172SP_G1000.acf", "path": "/sim/stock"},
            "override_state": True, "ap_engaged": False,
            "actuator_readback": {"wall_time_s": sim-.02, "frame_sequence": frame,
                                  "bridge_state": "ACTIVE", "brake_left": brake,
                                  "brake_right": brake},
            "controls": {"trim": 0., "brake": brake, "roll": roll_control},
            "values": {"sim_time_s": sim, "paused": 0,
                       "latitude_deg": THRESHOLD[0] + north / M_PER_DEG_LAT,
                       "longitude_deg": THRESHOLD[1] + east / M_PER_DEG_LON,
                       "altitude_msl_m": (424 + agl_ft) / 3.28084,
                       "agl_m": agl_ft / 3.28084,
                       "heading_true_deg": heading_deg, "kias": gs_kt,
                       "groundspeed_mps": gs_kt / 1.94384,
                       "vvi_fpm": vvi, "roll_deg": roll_deg, "pitch_deg": pitch_deg,
                       "roll_rate_dps": 0., "pitch_rate_dps": 0., "beta_deg": beta_deg,
                       "flap_actual": flap,
                       "wind_mps": wind_mps, "wind_from_true_deg": wind_from_true_deg,
                       "brake_left": 0., "brake_right": 0., "on_ground": ground}}


def test_brake_stays_off_in_air_then_moderate_after_touchdown():
    c = LandingController()
    assert c.step(snapshot(-500))["brake"] == 0
    touchdown = snapshot(100, ground=1, gs_kt=58, sim=2, frame=2, agl_ft=0)
    assert c.step(touchdown)["brake"] == 0
    later = snapshot(200, ground=1, gs_kt=40, sim=4, frame=3, agl_ft=0)
    assert .15 <= c.step(later)["brake"] <= .35


def test_flare_begins_below_half_the_prior_agl_trigger():
    c = LandingController()
    c.step(snapshot(40, agl_ft=20))
    assert c.phase == "approach"
    c.step(snapshot(45, agl_ft=17, sim=1.1, frame=2))
    assert c.phase == "flare"


def test_last_two_seconds_gradually_increase_nose_up_command():
    c = LandingController()
    c.phase = "flare"
    c.flare_started_sim = 1.
    c.flare_entry_pitch = 3.
    c.last_throttle = .05
    c.trim = -.1
    commands = []
    for frame, height in enumerate((10., 7., 4., 1.), 1):
        s = snapshot(350, agl_ft=height, vvi=-220., pitch_deg=3.5,
                     sim=5. + frame * .05, frame=frame)
        commands.append(c.step(s)["pitch"])
    assert commands == sorted(commands)
    assert commands[-1] > commands[0]


def test_initial_flare_pitch_target_eases_in():
    c = LandingController()
    c.phase = "flare"
    c.flare_started_sim = 1.
    c.flare_entry_pitch = 0.
    c.trim = -.3
    targets = []
    for frame, sim in enumerate((1.1, 2.5, 3.5), 1):
        c.step(snapshot(100, agl_ft=15., vvi=-300., pitch_deg=0.,
                        sim=sim, frame=frame))
        targets.append(c.last_pitch_target)
    assert 0 < targets[0] < targets[1] < targets[2]
    assert targets[1] - targets[0] > targets[0]


def test_approach_uses_pitch_for_speed_and_power_for_glidepath():
    def command(*, speed, height):
        c = LandingController()
        c.start_sim = 0.
        c.last_sim = 9.9
        c.last_throttle = .3
        return c.step(snapshot(-1000, gs_kt=speed, agl_ft=height, sim=10.))
    assert command(speed=60, height=220)["pitch"] < command(speed=70, height=220)["pitch"]
    assert command(speed=65, height=300)["throttle"] < command(speed=65, height=170)["throttle"]
    assert LandingController().step(snapshot(-1000, cross=-10))["roll"] > 0
    assert LandingController().step(snapshot(-1000, cross=10))["roll"] < 0


def test_low_and_slow_commands_nose_down_and_more_power_together():
    def command(speed, height):
        c = LandingController()
        c.start_sim = 0.
        c.last_sim = 9.9
        c.last_throttle = .3
        return c.step(snapshot(-1000, gs_kt=speed, agl_ft=height, sim=10.))
    on_path = command(65, 250)
    low_and_slow = command(60, 215)
    assert low_and_slow["pitch"] < on_path["pitch"]
    assert low_and_slow["throttle"] > on_path["throttle"]


def test_left_crosswind_uses_left_aileron_and_rudder_for_runway_heading_through_rollout():
    wind = {"wind_mps": 12 * .514444,
            "wind_from_true_deg": HEADING_TRUE_DEG - 45}
    centered = LandingController().step(snapshot(100, agl_ft=12, **wind))
    right_of_center = LandingController().step(snapshot(100, cross=5, agl_ft=12, **wind))
    misaligned = LandingController().step(snapshot(
        100, agl_ft=12, heading_deg=HEADING_TRUE_DEG + 5, **wind))
    ground = LandingController().step(snapshot(100, ground=1, agl_ft=0, **wind))
    assert centered["roll"] < 0
    assert right_of_center["roll"] < centered["roll"]
    assert misaligned["yaw"] < centered["yaw"]
    assert ground["roll"] < 0
    slow_rollout = LandingController().step(snapshot(
        300, ground=1, gs_kt=5, agl_ft=0, heading_deg=HEADING_TRUE_DEG - 4,
        beta_deg=25, **wind))
    assert slow_rollout["yaw"] > 0


def test_observer_requires_runway_touchdown_moderate_braking_and_stop():
    o = LandingObserver()
    for i, (along, flap) in enumerate(((-2000, 1/3), (-1300, 2/3), (-500, 1.),
                                       (-50, 1.), (2, 1.)), 1):
        assert o.observe(snapshot(along, flap=flap, agl_ft=50, gs_kt=65, pitch_deg=6.,
                                  sim=1. + .1 * (i - 1), frame=i))["outcome"] == "INCOMPLETE"
    assert o.observe(snapshot(60, ground=1, gs_kt=65, sim=1.5, frame=6, agl_ft=0))["outcome"] == "INCOMPLETE"
    for i in range(7, 22):
        assert o.observe(snapshot(60+(i-6)*20, ground=1, gs_kt=max(4, 65-i*3),
                                  brake=.3, sim=1. + .1 * (i - 1), frame=i, agl_ft=0))["outcome"] == "INCOMPLETE"
    assert o.observe(snapshot(500, ground=1, gs_kt=1.5, brake=.25, sim=3.1, frame=22,
                              agl_ft=0))["outcome"] == "PASS"
    early = LandingObserver()
    early.observe(snapshot(-50))
    assert early.observe(snapshot(-10, ground=1, sim=1.1, frame=2, agl_ft=0))["outcome"] == "FAIL"
    flat = LandingObserver()
    for i, (along, flap) in enumerate(((-2000, 1/3), (-1300, 2/3),
                                       (-500, 1.), (2, 1.)), 1):
        flat.observe(snapshot(along, flap=flap, agl_ft=50, gs_kt=65,
                              pitch_deg=3.5, sim=1. + .1 * (i - 1), frame=i))
    assert flat.observe(snapshot(100, ground=1, gs_kt=65, sim=1.4,
                                 frame=5, agl_ft=0))["outcome"] == "FAIL"


def test_crosswind_observer_rejects_crabbed_touchdown():
    o = LandingObserver(12, -45)
    wind = {"wind_mps": 12 * .514444,
            "wind_from_true_deg": HEADING_TRUE_DEG - 45,
            "heading_deg": HEADING_TRUE_DEG - 4,
            "roll_deg": -2., "roll_control": -.1, "pitch_deg": 6.}
    for i, (along, flap) in enumerate(((-2000, 1/3), (-1300, 2/3),
                                       (-500, 1.), (2, 1.)), 1):
        assert o.observe(snapshot(along, flap=flap, agl_ft=50, gs_kt=65,
                                  sim=1. + .1 * (i - 1), frame=i, **wind))["outcome"] == "INCOMPLETE"
    for i in range(5, 16):
        assert o.observe(snapshot(50 + i, agl_ft=12 - .2 * i, gs_kt=60,
                                  sim=1. + .1 * (i - 1), frame=i, **wind))["outcome"] == "INCOMPLETE"
    report = o.observe(snapshot(100, ground=1, agl_ft=0, gs_kt=52,
                                sim=2.5, frame=16, **wind))
    assert report["outcome"] == "FAIL"
    assert report["reason"] == "Crosswind touchdown alignment not demonstrated"
