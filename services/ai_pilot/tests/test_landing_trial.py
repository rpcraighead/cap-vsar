"""Landing brake lease, geometry and independent touchdown/stop criteria."""
from services.ai_pilot.aircraft_profiles import C172SP
import math

import pytest

from xplane.capvsar_flight_control_core import CHANNELS, ControlBridge
from xplane.capvsar_landing import (AIRPORT_ELEV_FT, FAR_END, GLIDEPATH_AIMPOINT_M,
                                   HEADING_TRUE_DEG, RUNWAYS, RUNWAY_LENGTH_M,
                                   THRESHOLD, runway_coordinates)
from services.ai_pilot.landing_trial import LandingController, LandingObserver, TOUCHDOWN_MIN_M


def test_kmyf_28r_geometry_uses_installed_runway_direction():
    assert runway_coordinates(*THRESHOLD) == pytest.approx((0, 0))
    along, cross = runway_coordinates(*FAR_END)
    assert along == pytest.approx(RUNWAY_LENGTH_M)
    assert cross == pytest.approx(0, abs=1e-8)
    assert 294 < HEADING_TRUE_DEG < 296
    assert 1390 < RUNWAY_LENGTH_M < 1420
    assert GLIDEPATH_AIMPOINT_M == pytest.approx(373.62)


def test_unflared_glidepath_intersects_new_aimpoint():
    c = LandingController(profile=C172SP)
    c.step(snapshot(0, agl_ft=50., gs_kt=65.))
    assert c.last_commands["target_altitude_ft"] == pytest.approx(
        AIRPORT_ELEV_FT + GLIDEPATH_AIMPOINT_M * math.tan(math.radians(3.)) * 3.28084)
    c.step(snapshot(GLIDEPATH_AIMPOINT_M, agl_ft=20., gs_kt=65., sim=1.1, frame=2))
    assert c.last_commands["target_altitude_ft"] == pytest.approx(AIRPORT_ELEV_FT)


def test_ksan_27_uses_installed_runway_and_displaced_threshold():
    runway = RUNWAYS["KSAN 27"]
    assert runway.coordinates(*runway.threshold) == pytest.approx((0, 0))
    assert runway.coordinates(*runway.far_end) == pytest.approx((runway.length_m, 0), abs=1e-8)
    assert runway.length_m == pytest.approx(2101.6, abs=1.)
    assert runway.heading_true_deg == pytest.approx(286.04, abs=.1)
    assert runway.aimpoint_m == pytest.approx(559.62)
    controller = LandingController(runway.name, profile=C172SP)
    controller.step(snapshot(0, agl_ft=55., runway=runway.name,
                             heading_deg=runway.heading_true_deg))
    assert controller.last_commands["target_altitude_ft"] == pytest.approx(
        17. + runway.aimpoint_m * math.tan(math.radians(3.)) * 3.28084)
    observer = LandingObserver(15., -90., runway.name, profile=C172SP)
    assert observer.wind_from_true_deg == pytest.approx(196.04, abs=.1)


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
             beta_deg=0., roll_deg=0., roll_control=0., runway="KMYF 28R"):
    from xplane.capvsar_landing import M_PER_DEG_LAT
    geometry = RUNWAYS[runway]
    north = along * geometry.unit_n - cross * geometry.unit_e
    east = along * geometry.unit_e + cross * geometry.unit_n
    return {"schema": "capvsar.telemetry.v1", "phase": "after_flight_model",
            "session": "a" * 32, "frame": frame, "wall_time_s": sim,
            "aircraft": {"name": "Cessna_172SP_G1000.acf", "path": "/sim/stock"},
            "override_state": True, "ap_engaged": False,
            "actuator_readback": {"wall_time_s": sim-.02, "frame_sequence": frame,
                                  "bridge_state": "ACTIVE", "brake_left": brake,
                                  "brake_right": brake},
            "controls": {"trim": 0., "brake": brake, "roll": roll_control},
            "values": {"sim_time_s": sim, "paused": 0,
                       "latitude_deg": geometry.threshold[0] + north / M_PER_DEG_LAT,
                       "longitude_deg": geometry.threshold[1] + east / geometry.m_per_deg_lon,
                       "altitude_msl_m": (geometry.airport_elev_ft + agl_ft) / 3.28084,
                       "agl_m": agl_ft / 3.28084,
                       "heading_true_deg": heading_deg, "kias": gs_kt,
                       "groundspeed_mps": gs_kt / 1.94384,
                       "vvi_fpm": vvi, "roll_deg": roll_deg, "pitch_deg": pitch_deg,
                       "roll_rate_dps": 0., "pitch_rate_dps": 0., "beta_deg": beta_deg,
                       "flap_actual": flap,
                       "wind_mps": wind_mps, "wind_from_true_deg": wind_from_true_deg,
                       "brake_left": 0., "brake_right": 0., "on_ground": ground}}


def test_brake_stays_off_in_air_then_moderate_after_touchdown():
    c = LandingController(profile=C172SP)
    assert c.step(snapshot(-500))["brake"] == 0
    touchdown = snapshot(100, ground=1, gs_kt=58, sim=2, frame=2, agl_ft=0)
    assert c.step(touchdown)["brake"] == 0
    later = snapshot(200, ground=1, gs_kt=40, sim=4, frame=3, agl_ft=0)
    assert .15 <= c.step(later)["brake"] <= .35


def test_flare_begins_below_half_the_prior_agl_trigger():
    c = LandingController(profile=C172SP)
    c.step(snapshot(40, agl_ft=20))
    assert c.phase == "approach"
    c.step(snapshot(45, agl_ft=17, sim=1.1, frame=2))
    assert c.phase == "flare"


def test_last_two_seconds_gradually_increase_nose_up_command():
    c = LandingController(profile=C172SP)
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
    c = LandingController(profile=C172SP)
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
        c = LandingController(profile=C172SP)
        c.start_sim = 0.
        c.last_sim = 9.9
        c.last_throttle = .3
        return c.step(snapshot(-1000, gs_kt=speed, agl_ft=height, sim=10.))
    assert command(speed=60, height=220)["pitch"] < command(speed=70, height=220)["pitch"]
    assert command(speed=65, height=300)["throttle"] < command(speed=65, height=170)["throttle"]
    assert LandingController(profile=C172SP).step(snapshot(-1000, cross=-10))["roll"] > 0
    assert LandingController(profile=C172SP).step(snapshot(-1000, cross=10))["roll"] < 0


def test_low_and_slow_commands_nose_down_and_more_power_together():
    def command(speed, height):
        c = LandingController(profile=C172SP)
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
    centered = LandingController(profile=C172SP).step(snapshot(100, agl_ft=12, **wind))
    right_of_center = LandingController(profile=C172SP).step(snapshot(100, cross=5, agl_ft=12, **wind))
    misaligned = LandingController(profile=C172SP).step(snapshot(
        100, agl_ft=12, heading_deg=HEADING_TRUE_DEG + 5, **wind))
    ground = LandingController(profile=C172SP).step(snapshot(100, ground=1, agl_ft=0, **wind))
    assert centered["roll"] < 0
    assert right_of_center["roll"] < centered["roll"]
    assert misaligned["yaw"] < centered["yaw"]
    assert ground["roll"] < 0
    slow_rollout = LandingController(profile=C172SP).step(snapshot(
        300, ground=1, gs_kt=5, agl_ft=0, heading_deg=HEADING_TRUE_DEG - 4,
        beta_deg=25, **wind))
    assert slow_rollout["yaw"] > 0


def test_direct_right_crosswind_reverses_aileron_side():
    wind = {"wind_mps": 12 * .514444,
            "wind_from_true_deg": (HEADING_TRUE_DEG + 90) % 360}
    air = LandingController(profile=C172SP).step(snapshot(100, agl_ft=12, **wind))
    ground = LandingController(profile=C172SP).step(snapshot(100, ground=1, agl_ft=0, **wind))
    assert air["roll"] > 0
    assert ground["roll"] > 0
    assert LandingObserver(12, 90, profile=C172SP).wind_side == 1


@pytest.mark.parametrize("offset,windward", [(-90, -1), (90, 1)])
def test_rollout_aileron_continues_then_increases_as_speed_falls(offset, windward):
    wind = {"wind_mps": 12 * .514444,
            "wind_from_true_deg": (HEADING_TRUE_DEG + offset) % 360}
    c = LandingController(profile=C172SP)
    air = c.step(snapshot(300, agl_ft=1., gs_kt=53., **wind))
    touchdown = c.step(snapshot(301, ground=1, agl_ft=0., gs_kt=52.,
                                sim=1.05, frame=2, **wind))
    slowed = c.step(snapshot(420, ground=1, agl_ft=0., gs_kt=25.,
                            sim=3., frame=3, **wind))
    taxi_speed = c.step(snapshot(470, ground=1, agl_ft=0., gs_kt=3.,
                                sim=6., frame=4, **wind))
    assert abs(touchdown["roll"] - air["roll"]) < .08
    assert 0 < windward * air["roll"] < windward * touchdown["roll"]
    assert windward * touchdown["roll"] < windward * slowed["roll"]
    assert windward * slowed["roll"] < windward * taxi_speed["roll"] <= .30


def test_wing_low_slip_does_not_cancel_runway_heading_rudder():
    wind = {"wind_mps": 12 * .514444,
            "wind_from_true_deg": HEADING_TRUE_DEG - 90,
            "heading_deg": HEADING_TRUE_DEG - 4}
    no_slip = LandingController(profile=C172SP).step(snapshot(150, agl_ft=12, beta_deg=0, **wind))
    slip = LandingController(profile=C172SP).step(snapshot(150, agl_ft=12, beta_deg=5, **wind))
    assert slip["yaw"] == pytest.approx(no_slip["yaw"])


def test_observer_requires_runway_touchdown_moderate_braking_and_stop():
    o = LandingObserver(profile=C172SP)
    for i, (along, flap) in enumerate(((-2000, 1/3), (-1300, 2/3), (-500, 1.),
                                       (-50, 1.), (2, 1.)), 1):
        assert o.observe(snapshot(along, flap=flap, agl_ft=50, gs_kt=65, pitch_deg=6.,
                                  sim=1. + .1 * (i - 1), frame=i))["outcome"] == "INCOMPLETE"
    assert o.observe(snapshot(400, ground=1, gs_kt=65, sim=1.5, frame=6, agl_ft=0))["outcome"] == "INCOMPLETE"
    for i in range(7, 22):
        assert o.observe(snapshot(400+(i-6)*20, ground=1, gs_kt=max(4, 65-i*3),
                                  brake=.3, sim=1. + .1 * (i - 1), frame=i, agl_ft=0))["outcome"] == "INCOMPLETE"
    assert o.observe(snapshot(800, ground=1, gs_kt=1.5, brake=.25, sim=3.1, frame=22,
                              agl_ft=0))["outcome"] == "PASS"
    early = LandingObserver(profile=C172SP)
    early.observe(snapshot(-50))
    assert early.observe(snapshot(-10, ground=1, sim=1.1, frame=2, agl_ft=0))["outcome"] == "FAIL"
    displaced = LandingObserver(profile=C172SP)
    for i, (along, flap) in enumerate(((-2000, 1/3), (-1300, 2/3),
                                       (-500, 1.), (2, 1.)), 1):
        displaced.observe(snapshot(along, flap=flap, agl_ft=50., gs_kt=65.,
                                   pitch_deg=6., sim=1. + .1 * (i - 1), frame=i))
    displaced.observe(snapshot(350, agl_ft=2., pitch_deg=6., sim=1.4, frame=5))
    short = displaced.observe(snapshot(TOUCHDOWN_MIN_M - 1., ground=1, agl_ft=0.,
                                       pitch_deg=6., sim=1.5, frame=6))
    assert short["reason"] == "Touchdown outside acceptance window"
    flat = LandingObserver(profile=C172SP)
    for i, (along, flap) in enumerate(((-2000, 1/3), (-1300, 2/3),
                                       (-500, 1.), (2, 1.)), 1):
        flat.observe(snapshot(along, flap=flap, agl_ft=50, gs_kt=65,
                              pitch_deg=3.5, sim=1. + .1 * (i - 1), frame=i))
    assert flat.observe(snapshot(100, ground=1, gs_kt=65, sim=1.4,
                                 frame=5, agl_ft=0))["outcome"] == "FAIL"


def test_crosswind_observer_rejects_crabbed_touchdown():
    o = LandingObserver(12, -45, profile=C172SP)
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
    report = o.observe(snapshot(400, ground=1, agl_ft=0, gs_kt=52,
                                sim=2.5, frame=16, **wind))
    assert report["outcome"] == "FAIL"
    assert report["reason"] == "Crosswind touchdown alignment not demonstrated"
