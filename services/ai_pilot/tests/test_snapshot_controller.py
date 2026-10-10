import copy
import math
import pytest

from services.ai_pilot.snapshot_controller import SnapshotController
from .test_experiment import snapshot

TARGET = {"heading_mag_deg": 90., "altitude_indicated_ft": 4500., "kias": 100.}


def sample(t):
    s = snapshot(t)
    s["values"].update(pitch_deg=2., beta_deg=.1, roll_rate_dps=0., pitch_rate_dps=0.)
    s["controls"] = dict(roll=0., pitch=0., yaw=0., throttle=.55, flap=0., trim=.1)
    s["frame"] = round(t * 1000) + 1
    return s


def controller():
    return SnapshotController("/stock/c172.acf", "test-session")


def test_transfer_starts_from_measured_controls_without_a_thread_or_native_writer():
    c = controller()
    s = sample(0)
    assert c.step(s, TARGET, 100.) == s["controls"]
    assert c.backend._thread is None and c.buffer.values == {}
    s = sample(.1)
    out = c.step(s, {**TARGET, "heading_mag_deg": 110.}, 100.1)
    assert abs(out["roll"]) <= .04 + 1e-9
    assert set(out) == set(s["controls"])


def test_integrators_depend_on_simulation_duration_not_number_of_frames():
    def run(dt):
        c = controller()
        for i in range(round(2 / dt) + 1):
            s = sample(round(i * dt, 6))
            s["values"].update(altitude_indicated_ft=4490, kias=99)
            c.step(s, TARGET, s["wall_time_s"])
        return c.backend._alt_i, c.backend._throttle_i, c.backend._beta_i
    assert run(.1) == pytest.approx(run(.04), abs=1e-10)


@pytest.mark.parametrize("change", [
    lambda s: s["values"].update(paused=1),
    lambda s: s["values"].update(on_ground=1),
    lambda s: s["values"].update(sim_time_s=-1),
    lambda s: s["values"].update(sim_time_s=1),
    lambda s: s["values"].update(roll_rate_dps=float("nan")),
    lambda s: s["controls"].update(trim=float("nan")),
    lambda s: s.update(frame=1),
    lambda s: s.update(session="old-session"),
    lambda s: s.update(wall_time_s=99),
])
def test_pause_reset_missing_or_stale_data_latches_fault_and_emits_no_more_frames(change):
    c = controller()
    c.step(sample(0), TARGET, 100)
    bad = sample(.1)
    change(bad)
    with pytest.raises((ValueError, KeyError)):
        c.step(bad, TARGET, 100.1)
    assert c.fault and c.buffer.values == {}
    with pytest.raises(ValueError, match="latched"):
        c.step(sample(.2), TARGET, 100.2)


def test_surface_rate_uses_simulation_time_even_when_wall_time_runs_faster():
    c = controller()
    c.step(sample(0), TARGET, 100)
    s = sample(.05)
    s["wall_time_s"] = 100.2
    result = c.step(s, {**TARGET, "heading_mag_deg": 110}, 100.2)
    assert result["roll"] == pytest.approx(.4 * .05)
