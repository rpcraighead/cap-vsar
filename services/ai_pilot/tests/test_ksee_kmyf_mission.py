"""Key chart gates and the runway-rollout envelope found by the live sortie."""
import time
from types import SimpleNamespace

import pytest

from services.ai_pilot.ksee_kmyf_mission import MissionController
from xplane.capvsar_mission import MissionLab


def snapshot(**changes):
    values = {
        "sim_time_s": 10., "latitude_deg": 32.8288,
        "longitude_deg": -116.978, "altitude_indicated_ft": 789.,
        "kias": 74., "heading_true_deg": 281., "heading_mag_deg": 270.,
        "roll_deg": 0., "roll_rate_dps": 0., "pitch_deg": 5.,
        "pitch_rate_dps": 0., "vvi_fpm": 500., "beta_deg": 0.,
        "groundspeed_mps": 38., "nav1_frequency_10khz": 11195,
        "nav1_lateral_valid": 1, "nav1_glideslope_flag": 0,
        "nav1_hdef_dots": 0., "nav1_vdef_dots": 0., "nav1_dme_nm": 7.,
    }
    values.update(changes)
    return {"values": values, "controls": {"trim": 0.}}


def test_departure_turn_waits_for_790_ft():
    controller = MissionController()
    controller.step(snapshot())
    assert controller.stage == "runway_climb"
    controller.step(snapshot(sim_time_s=10.1, altitude_indicated_ft=790.))
    assert controller.stage == "pgy_intercept"
    assert controller.last_diagnostics["target_true_deg"] == 73.


def test_pilot_directed_bakel_vector_at_3500_ft():
    controller = MissionController("missed_270")
    controller.step(snapshot(latitude_deg=32.82, longitude_deg=-117.19,
                             altitude_indicated_ft=3499., heading_true_deg=281.,
                             heading_mag_deg=270.))
    assert controller.stage == "missed_270"
    controller.step(snapshot(sim_time_s=10.1, latitude_deg=32.82,
                             longitude_deg=-117.19, altitude_indicated_ft=3500.,
                             heading_true_deg=281., heading_mag_deg=270.))
    assert controller.stage == "retry_bakel"
    assert controller.last_diagnostics["target_alt_ft"] == 5000.


def test_live_direct_bakel_applies_without_stage_pause():
    controller = MissionController("mzb_inbound")
    live = snapshot(paused=0, on_ground=0, altitude_indicated_ft=3500.,
                    latitude_deg=32.82, longitude_deg=-117.19)
    accepted = controller.retask({"kind": "direct", "fix": "BAKEL",
                                  "altitude_ft": 5000.}, live)
    controller.step(live)
    assert accepted["stage"] == "retry_bakel"
    assert controller.last_diagnostics["target_alt_ft"] == 5000.
    assert controller.last_diagnostics["distance_nm"] > 1


def test_live_heading_and_altitude_update():
    controller = MissionController("mzb_inbound")
    live = snapshot(paused=0, on_ground=0, altitude_indicated_ft=4500.)
    controller.retask({"kind": "heading", "heading_mag_deg": 90.,
                       "altitude_ft": 5000.}, live)
    controller.step(live)
    assert controller.last_diagnostics["target_true_deg"] == 101.
    controller.retask({"kind": "altitude", "altitude_ft": 5500.}, live)
    controller.step(snapshot(**{**live["values"], "sim_time_s": 10.1}))
    assert controller.last_diagnostics["target_alt_ft"] == 5500.


@pytest.mark.parametrize("task", [
    {"kind": "direct", "fix": "CARIF", "altitude_ft": 5000.},
    {"kind": "direct", "fix": "BAKEL", "altitude_ft": 3000.},
    {"kind": "heading", "heading_mag_deg": 361., "altitude_ft": 5000.},
    {"kind": "altitude", "altitude_ft": float("nan")},
])
def test_live_retask_rejects_invalid_commands(task):
    with pytest.raises(ValueError):
        MissionController("mzb_inbound").retask(
            task, snapshot(paused=0, on_ground=0, altitude_indicated_ft=4500.))


def test_live_retask_rejects_final_and_low_departure():
    live = snapshot(paused=0, on_ground=0, altitude_indicated_ft=5000.)
    with pytest.raises(ValueError):
        MissionController("ils").retask(
            {"kind": "direct", "fix": "BAKEL", "altitude_ft": 5000.}, live)
    with pytest.raises(ValueError):
        MissionController("pgy_inbound").retask(
            {"kind": "heading", "heading_mag_deg": 90., "altitude_ft": 5000.},
            snapshot(paused=0, on_ground=0, altitude_indicated_ft=2000.))


def test_ils_glideslope_above_calls_for_more_descent():
    common = dict(latitude_deg=32.76774, longitude_deg=-117.0166,
                  altitude_indicated_ft=2600., heading_true_deg=295.,
                  heading_mag_deg=284., pitch_deg=0., vvi_fpm=-400.)
    high = MissionController("ils")
    low = MissionController("ils")
    high.step(snapshot(**common, nav1_vdef_dots=1.))
    low.step(snapshot(**common, nav1_vdef_dots=-1.))
    assert high.last_diagnostics["target_vvi_fpm"] < low.last_diagnostics["target_vvi_fpm"]
    assert high.last_diagnostics["target_vvi_fpm"] == pytest.approx(
        low.last_diagnostics["target_vvi_fpm"] - 180.)


def test_lost_ils_signal_commands_missed_approach_in_same_frame():
    controller = MissionController("ils")
    command = controller.step(snapshot(latitude_deg=32.77, longitude_deg=-117.02,
                                       altitude_indicated_ft=2400.,
                                       nav1_glideslope_flag=1))
    assert controller.stage == "missed_runway"
    assert controller.transitions[-1]["reason"] == "ILS signal lost on final"
    assert command["throttle"] == 1.


def test_unstable_final_goes_around_without_fault_pause():
    from xplane.capvsar_landing import RUNWAYS
    runway = RUNWAYS["KMYF 28R"]
    distance = 1.1 * 1852
    lat = runway.threshold[0]-distance*runway.unit_n/111132.92
    lon = runway.threshold[1]-distance*runway.unit_e/runway.m_per_deg_lon
    controller = MissionController("ils")
    command = controller.step(snapshot(latitude_deg=lat, longitude_deg=lon,
                                       altitude_indicated_ft=900., nav1_vdef_dots=1.5))
    assert controller.stage == "missed_runway"
    assert controller.transitions[-1]["reason"] == "ILS unstable at 1.2 NM"
    assert command["throttle"] == 1.


def test_rollout_envelope_accepts_zero_kias_only_on_kmyf_runway():
    lab = MissionLab.__new__(MissionLab)
    lab.verify_identity = lambda: None
    lab.trial_started = time.monotonic()
    lab.resume_pending = False
    lab.previous_sim = None
    values = {"paused": 0, "on_ground": 1, "latitude_deg": 32.8146,
              "longitude_deg": -117.1356, "altitude_indicated_ft": 433.,
              "kias": 0., "groundspeed_mps": .8, "roll_deg": 0.,
              "pitch_deg": 4., "sim_time_s": 1.}
    lab.check_flight({"values": values}, SimpleNamespace(state="ACTIVE"))
    with pytest.raises(ValueError, match="envelope"):
        lab.check_flight({"values": {**values, "longitude_deg": -117.10,
                                     "sim_time_s": 2.}}, SimpleNamespace(state="ACTIVE"))
