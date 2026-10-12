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
