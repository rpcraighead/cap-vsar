"""Constant-speed prop lever: bridge channel, lab authority, schedule, controller frames."""
from dataclasses import replace

import pytest

from services.ai_pilot.aircraft_profiles import C172SP, C182T
from services.ai_pilot.ground_guidance import GroundCommand
from services.ai_pilot.ksee_kmyf_mission import MissionController
from services.ai_pilot.landing_trial import LandingController
from services.ai_pilot.prop_law import FULL, SLEW_PER_S, PropLaw
from services.ai_pilot.search_patterns import CruiseLaw
from services.ai_pilot.tests.test_ksee_kmyf_mission import snapshot as mission_snapshot
from services.ai_pilot.tests.test_landing_trial import snapshot as landing_snapshot
from services.ai_pilot.tests.test_c182t_port import cleared_taxi, observation
from services.ai_pilot.takeoff_guidance import TakeoffGuidance
from services.ai_pilot.tests.test_flight_control_bridge import SESSION, Simulator
from services.ai_pilot.tests.test_surface_lab import lab_setup
from xplane.capvsar_flight_control_core import CHANNELS, ControlBridge
from xplane.capvsar_qualification import PROP_AUTHORITY

# A C182T whose cruise lever is below full, so the schedule has something to do.
GOVERNED = replace(C182T, prop_cruise_ratio=.9)


def cruise(**changes):
    values = {"sim_time_s": 100., "on_ground": 0, "agl_m": 800., "kias": 100.,
              "flap_actual": 0., "vvi_fpm": 0.}
    values.update(changes)
    return values


# --- the schedule ---------------------------------------------------------

def test_fixed_pitch_profile_adds_no_prop_channel():
    law = PropLaw(C172SP)
    assert not law.enabled
    assert law.add_to({"roll": 0.}, cruise()) == {"roll": 0.}


def test_lever_stays_full_forward_until_a_cruise_ratio_is_measured():
    law = PropLaw(C182T)
    assert C182T.constant_speed_prop and C182T.prop_cruise_ratio == FULL
    assert law.step(cruise()) == FULL


def test_cruise_ratio_only_in_level_established_cruise_and_slewed():
    law = PropLaw(GOVERNED)
    law.step(cruise(sim_time_s=100.))
    ratios = [law.step(cruise(sim_time_s=100. + .1 * i)) for i in range(1, 80)]
    assert ratios[0] == pytest.approx(FULL - SLEW_PER_S * .1)       # slewed, not stepped
    assert ratios[-1] == pytest.approx(GOVERNED.prop_cruise_ratio)  # arrives and holds
    assert all(a >= b for a, b in zip(ratios, ratios[1:]))


@pytest.mark.parametrize("change", [
    {"on_ground": 1}, {"agl_m": 100.}, {"kias": 70.}, {"flap_actual": .33},
    {"vvi_fpm": 700.}, {"vvi_fpm": -700.}])
def test_every_other_condition_demands_full_forward(change):
    law = PropLaw(GOVERNED)
    for i in range(80):
        law.step(cruise(sim_time_s=100. + .1 * i))
    assert law.ratio == pytest.approx(GOVERNED.prop_cruise_ratio)
    assert law.target(cruise(**change)) == FULL


def test_cruise_setting_has_hysteresis_on_vertical_speed():
    law = PropLaw(GOVERNED)
    assert law.target(cruise(vvi_fpm=250.)) == GOVERNED.prop_cruise_ratio
    assert law.target(cruise(vvi_fpm=400.)) == GOVERNED.prop_cruise_ratio   # still level enough
    assert law.target(cruise(vvi_fpm=550.)) == FULL
    assert law.target(cruise(vvi_fpm=400.)) == FULL                         # not back until < 300
    assert law.target(cruise(vvi_fpm=250.)) == GOVERNED.prop_cruise_ratio


def test_allow_cruise_false_pins_the_lever_full():
    law = PropLaw(GOVERNED)
    assert law.target(cruise(), allow_cruise=False) == FULL


def test_profile_refuses_a_cruise_ratio_the_bridge_would_reject():
    with pytest.raises(ValueError):
        replace(C182T, prop_cruise_ratio=.3)
    with pytest.raises(ValueError):
        replace(C172SP, prop_cruise_ratio=.9)


# --- controller frames ----------------------------------------------------

def test_takeoff_and_ground_commands_carry_the_lever_only_for_the_governed_prop():
    c182 = TakeoffGuidance(cleared_taxi(), runway="27R", runway_heading_true_deg=282,
                           runway_length_m=1628, field_elevation_ft=388, profile=C182T)
    assert c182.step(observation()).actuator_frame()["prop"] == FULL
    c172 = TakeoffGuidance(cleared_taxi(), runway="27R", runway_heading_true_deg=282,
                           runway_length_m=1628, field_elevation_ft=388, profile=C172SP)
    assert "prop" not in c172.step(observation(flap_ratio=0.)).actuator_frame()
    assert "prop" not in GroundCommand().actuator_frame()
    assert GroundCommand(prop=FULL).actuator_frame()["prop"] == FULL


def test_landing_flies_the_lever_full_forward():
    frame = LandingController("KMYF 28R", profile=C182T).step(landing_snapshot(-3000.))
    assert frame["prop"] == FULL
    assert "prop" not in LandingController("KMYF 28R", profile=C172SP).step(landing_snapshot(-3000.))


def level_snapshots(**changes):
    state = {"on_ground": 0, "agl_m": 1500., "flap_actual": 0., "kias": 100., "vvi_fpm": 0.,
             "altitude_indicated_ft": 5000., **changes}
    return (mission_snapshot(**state, sim_time_s=10. + .1 * i) for i in range(80))


def test_mission_holds_full_in_climb_out_and_lets_cruise_stages_use_the_schedule():
    level = MissionController(stage="mzb_inbound", profile=GOVERNED)
    ratios = [level.step(snap)["prop"] for snap in level_snapshots()]
    assert ratios[-1] == pytest.approx(GOVERNED.prop_cruise_ratio)
    climb = MissionController(stage="runway_climb", profile=GOVERNED)
    assert {climb.step(snap)["prop"] for snap in level_snapshots()} == {FULL}
    assert "prop" not in MissionController(stage="mzb_inbound", profile=C172SP).step(next(level_snapshots()))


def test_cruise_law_frame_has_exactly_the_bridge_channels():
    law = CruiseLaw(GOVERNED)
    frame, _ = law.frame(cruise(heading_true_deg=90., roll_deg=0., roll_rate_dps=0.,
                                altitude_indicated_ft=2000., pitch_deg=2., pitch_rate_dps=0.,
                                beta_deg=0.), 0., 90., 2000., 100., .05)
    assert set(frame) == set(CHANNELS) | {"brake", "prop"}


# --- the bridge -----------------------------------------------------------

def frame_with(controls, wall):
    return dict(session=SESSION, generation=0, sequence=0, expires_at=wall[0] + .15,
                controls=controls)


def test_core_accepts_prop_only_as_a_complete_atomic_channel():
    wall = [10.]
    base = {c: 0. for c in CHANNELS}
    bridge = ControlBridge(Simulator(), SESSION, clock=lambda: wall[0], atomic=True,
                           channels=CHANNELS + ("prop",))
    with pytest.raises(ValueError, match="Complete"):
        bridge.submit_frame(**frame_with(base, wall))
    with pytest.raises(ValueError, match="prop"):
        bridge.submit_frame(**frame_with({**base, "prop": 1.2}, wall))
    bridge.submit_frame(**frame_with({**base, "prop": .9}, wall))
    assert bridge.candidates["prop"][0] == .9
    with pytest.raises(ValueError, match="Invalid actuator channel set"):
        ControlBridge(Simulator(), SESSION, atomic=False, channels=CHANNELS + ("prop",))
    # A fixed-pitch session refuses a frame that carries a lever it does not own.
    fixed = ControlBridge(Simulator(), SESSION, clock=lambda: wall[0], atomic=True)
    with pytest.raises(ValueError, match="Complete"):
        fixed.submit_frame(**frame_with({**base, "prop": 1.}, wall))


def test_lab_authority_adds_a_floored_prop_lever_only_when_configured(monkeypatch, tmp_path):
    valid = {"roll": 0., "pitch": 0., "yaw": 0., "throttle": 1., "flap": 0., "trim": 0.,
             "brake": 1.}
    _, _, plain = lab_setup(monkeypatch, tmp_path)
    plain.validate_controls(valid)
    with pytest.raises(ValueError, match="Complete"):
        plain.validate_controls({**valid, "prop": 1.})
    _, _, governed = lab_setup(monkeypatch, tmp_path, constant_speed_prop=True)
    governed.validate_controls({**valid, "prop": 1.})
    governed.validate_controls({**valid, "prop": PROP_AUTHORITY[0]})
    with pytest.raises(ValueError, match="Complete"):
        governed.validate_controls(valid)
    with pytest.raises(ValueError, match="Surface control limit: prop"):
        governed.validate_controls({**valid, "prop": PROP_AUTHORITY[0] - .01})


def test_sink_writes_the_requested_prop_speed_scaled_across_the_governing_range(monkeypatch, tmp_path):
    """Measured on the CAP 487, 2026-10-15: prop_ratio reads 0.0 and drives nothing; the lever
    is prop_rotation_speed_rad_sec, one-for-one with governed RPM between 2,000 and 2,400."""
    from services.ai_pilot.tests.test_flight_control_plugin import load_plugin
    xp, plugin = load_plugin(monkeypatch, tmp_path)
    lever = "sim/cockpit2/engine/actuators/prop_rotation_speed_rad_sec"
    low, high = 2000 / 9.5493, 2400 / 9.5493
    xp.refs[lever] = [0.] * 8
    xp.refs["sim/aircraft/controls/acf_RSC_mingov_prp"] = low
    xp.refs["sim/aircraft/controls/acf_RSC_redline_prp"] = high
    xp.setDatavf = lambda ref, values, offset, count: xp.refs[ref].__setitem__(
        slice(offset, offset + count), values[:count])
    fixed = plugin.core.sink
    assert "prop" not in fixed.controls
    sink = type(fixed)(prop=True)
    assert sink.controls["prop"] == lever
    sink.write_control("prop", 1.0)
    assert xp.refs[lever][0] * 9.5493 == pytest.approx(2400)
    sink.write_control("prop", .5)
    assert xp.refs[lever][0] * 9.5493 == pytest.approx(2200)      # the authority floor
    assert sink.read_control("prop") == pytest.approx(.5)
    xp.refs["sim/aircraft/controls/acf_RSC_redline_prp"] = 0.      # range unreadable: refuse, don't guess
    with pytest.raises(RuntimeError, match="range unavailable"):
        sink.write_control("prop", .8)
