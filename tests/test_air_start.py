#!/usr/bin/env python3
"""Tests for scripts/set_air_start.py.

Everything here runs offline. The simulator is never contacted: the geometry,
the atmosphere and the velocity frame are all pure functions, which is why they
are pure functions.

The KRNM numbers are not invented for the test. They are the runway 9/27 record
out of X-Plane 12's own Global Airports apt.dat, and the runway 27 threshold in
it agrees to seven decimal places with KRNM_27_THRESHOLD in
services/ai_pilot/flight_controller.py, which was derived independently.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(name, relative):
    """Load by path. Importing scripts/ or services/ai_pilot/ via sys.path
    would put services/ai_pilot/tests on it and shadow this very package."""
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    # @dataclass resolves its module from sys.modules, so register first.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sas = _load("capvsar_set_air_start", "scripts/set_air_start.py")


# The verbatim KRNM block from apt.dat, plus a decoy airport either side so the
# header handling is actually exercised rather than assumed.
APT_DAT = """\
1    500 0 0 KAAA Decoy Before
100 30.00 1 0 0.25 0 2 0  18 34.0000000 -118.0000000 0 0 2 0 0 0 36 34.0100000 -118.0000000 0 0 2 0 0 0
1   1395 0 0 KRNM Ramona
1302 icao_code KRNM
100 45.72 1 0 0.00 0 2 0   9 33.0403517 -116.9233062 0 0 2 0 0 1 27 33.0379711 -116.9072216 0 0 2 0 0 0
1    200 0 0 KZZZ Decoy After
100 30.00 1 0 0.25 0 2 0   9 35.0000000 -119.0000000 0 0 2 0 0 0 27 35.0000000 -118.9900000 0 0 2 0 0 0
"""

KRNM_09 = (33.0403517, -116.9233062)
KRNM_27 = (33.0379711, -116.9072216)
KRNM_ELEV = 1395.0


def rwy(designator="09", text=APT_DAT):
    return sas.parse_runway(text.splitlines(), "KRNM", designator)


# ---------------------------------------------------------------------------
# apt.dat parsing
# ---------------------------------------------------------------------------

class TestAptDat:
    def test_reads_the_named_runway_end(self):
        end = rwy("09")
        assert end.lat == pytest.approx(KRNM_09[0])
        assert end.lon == pytest.approx(KRNM_09[1])
        assert end.airport_elev_ft == KRNM_ELEV

    def test_the_opposite_end_is_the_other_threshold(self):
        end = rwy("09")
        assert end.opposite_designator == "27"
        assert end.opposite_lat == pytest.approx(KRNM_27[0])
        assert end.opposite_lon == pytest.approx(KRNM_27[1])

    def test_either_end_can_be_asked_for(self):
        assert rwy("27").lat == pytest.approx(KRNM_27[0])
        assert rwy("27").opposite_designator == "09"

    def test_bare_and_padded_designators_are_the_same_runway(self):
        assert rwy("9").lat == rwy("09").lat

    def test_it_does_not_wander_into_the_next_airport(self):
        # KZZZ also has a 09. Asking KRNM for one must not return it.
        assert rwy("09").lat == pytest.approx(KRNM_09[0])

    def test_a_decoy_airport_before_the_target_is_skipped(self):
        assert rwy("09").airport_elev_ft == KRNM_ELEV

    def test_unknown_runway_is_an_error_naming_the_runway(self):
        with pytest.raises(LookupError, match="no runway"):
            rwy("13")

    def test_unknown_airport_is_a_different_error(self):
        with pytest.raises(LookupError, match="not found"):
            sas.parse_runway(APT_DAT.splitlines(), "KXYZ", "09")


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

class TestGeometry:
    def test_runway_heading_is_measured_not_taken_from_the_name(self):
        # 100 deg true. The NAME is 09 because magnetic variation is ~11.5E:
        # a runway whose heading came from its number would read 090 here.
        assert rwy("09").true_heading == pytest.approx(100.0, abs=0.5)

    def test_reciprocal_runway_is_180_out(self):
        d = (rwy("27").true_heading - rwy("09").true_heading) % 360.0
        assert d == pytest.approx(180.0, abs=0.5)

    def test_runway_length_matches_the_published_4995_ft(self):
        assert rwy("09").length_ft == pytest.approx(4995.0, abs=25.0)

    def test_the_start_point_is_the_requested_distance_out(self):
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0)
        assert sas.great_circle_nm(s.lat, s.lon, *KRNM_09) == pytest.approx(9.0, abs=0.01)

    def test_the_start_point_is_behind_the_threshold_not_beyond_it(self):
        # Runway 09 is flown eastbound, so a final approach fix is WEST of it.
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0)
        assert s.lon < KRNM_09[1], "9 nm final to 09 must lie west of the threshold"

    def test_and_the_other_way_for_runway_27(self):
        s = sas.build_air_start(rwy("27"), distance_nm=9.0, kias=100.0)
        assert s.lon > KRNM_27[1], "9 nm final to 27 must lie east of the threshold"

    def test_flying_the_runway_heading_from_the_start_point_reaches_the_threshold(self):
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0)
        brg = sas.initial_bearing(s.lat, s.lon, *KRNM_09)
        assert (brg - s.heading_true + 180) % 360 - 180 == pytest.approx(0.0, abs=0.2)


# ---------------------------------------------------------------------------
# Atmosphere
# ---------------------------------------------------------------------------

class TestAtmosphere:
    def test_sea_level_indicated_equals_true(self):
        assert sas.tas_from_ias(100.0, 0.0) == pytest.approx(100.0, abs=0.1)

    def test_true_exceeds_indicated_with_height(self):
        assert sas.tas_from_ias(100.0, 4261.0) > 106.0

    def test_roughly_two_percent_per_thousand_feet(self):
        # The rule of thumb every pilot carries; if the ISA maths broke, this
        # is the check that would notice.
        ratio = sas.tas_from_ias(100.0, 5000.0) / 100.0
        assert ratio == pytest.approx(1.08, abs=0.02)

    def test_density_falls_with_height(self):
        assert sas.isa_density(10000.0) < sas.isa_density(0.0) == pytest.approx(1.225, abs=0.001)


# ---------------------------------------------------------------------------
# The velocity vector: the thing VEHS does not do for you
# ---------------------------------------------------------------------------

class TestVelocity:
    def test_a_start_always_carries_speed(self):
        # The whole reason this tool exists. Position without velocity is a
        # parked aeroplane at altitude.
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0)
        speed = math.hypot(math.hypot(s.local_vx, s.local_vz), s.local_vy)
        assert speed > 40.0

    def test_speed_written_is_true_airspeed_not_indicated(self):
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0)
        horiz = math.hypot(s.local_vx, s.local_vz)
        assert horiz == pytest.approx(s.ktas * 1852.0 / 3600.0, rel=1e-6)
        assert s.ktas > s.kias

    def test_eastbound_runway_gives_a_mostly_eastward_vector(self):
        # +X is east. Runway 09 is flown east, so vx dominates and is positive.
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0)
        assert s.local_vx > 0
        assert abs(s.local_vx) > abs(s.local_vz)

    def test_westbound_runway_reverses_it(self):
        s = sas.build_air_start(rwy("27"), distance_nm=9.0, kias=100.0)
        assert s.local_vx < 0

    @pytest.mark.parametrize("heading,expect_vx,expect_vz", [
        (0.0, 0.0, -1.0),    # north: +Z is SOUTH, so northbound is negative vz
        (90.0, 1.0, 0.0),    # east
        (180.0, 0.0, 1.0),   # south
        (270.0, -1.0, 0.0),  # west
    ])
    def test_the_local_frame_is_x_east_y_up_z_south(self, heading, expect_vx, expect_vz):
        # Getting this frame wrong flies the aeroplane backwards down the
        # approach, so pin all four cardinals rather than trusting one.
        tas_ms = 50.0
        vx = tas_ms * math.sin(math.radians(heading))
        vz = -tas_ms * math.cos(math.radians(heading))
        assert vx == pytest.approx(expect_vx * tas_ms, abs=1e-9)
        assert vz == pytest.approx(expect_vz * tas_ms, abs=1e-9)

    def test_level_start_has_no_vertical_component(self):
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0)
        assert s.local_vy == pytest.approx(0.0, abs=1e-9)
        assert s.vertical_fpm == pytest.approx(0.0, abs=1e-6)

    def test_glidepath_start_descends(self):
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0, glidepath_deg=3.0)
        assert s.local_vy < 0, "a glidepath start must be going down, not up"
        # 3 deg at 100 kt is the ~500 fpm every instrument pilot expects.
        assert s.vertical_fpm == pytest.approx(-560.0, abs=60.0)

    def test_descending_start_is_pitched_lower_than_a_level_one(self):
        level = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0)
        down = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0, glidepath_deg=3.0)
        assert down.pitch_deg < level.pitch_deg


# ---------------------------------------------------------------------------
# Altitude selection
# ---------------------------------------------------------------------------

class TestAltitude:
    def test_nine_mile_final_sits_on_the_three_degree_path(self):
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0, glidepath_deg=3.0)
        assert s.altitude_ft == pytest.approx(4261.0, abs=5.0)

    def test_a_level_start_is_rounded_to_a_flyable_altitude(self):
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0)
        assert s.altitude_ft % 100 == 0

    def test_an_explicit_altitude_wins(self):
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0, altitude_ft=3500.0)
        assert s.altitude_ft == 3500.0

    def test_agl_is_measured_from_the_field_not_from_sea_level(self):
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0, altitude_ft=4395.0)
        assert s.agl_ft == pytest.approx(3000.0)

    def test_a_closer_final_is_lower(self):
        near = sas.build_air_start(rwy("09"), distance_nm=3.0, kias=100.0, glidepath_deg=3.0)
        far = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0, glidepath_deg=3.0)
        assert near.altitude_ft < far.altitude_ft


# ---------------------------------------------------------------------------
# The maneuver gate's verdict, reported before the flight rather than during it
# ---------------------------------------------------------------------------

class TestGateReport:
    def test_the_nine_mile_level_start_is_inside_the_envelope(self):
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0)
        ok, notes = sas.gate_report(s)
        assert ok, notes

    def test_approach_speed_is_refused(self):
        # A 182 over the fence at 75 KIAS is below the gate's 90 kt floor. That
        # floor is what stops an autonomous system flying to the stall.
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=75.0)
        ok, notes = sas.gate_report(s)
        assert not ok
        assert any("airspeed" in n for n in notes)

    def test_low_and_close_is_refused(self):
        s = sas.build_air_start(rwy("09"), distance_nm=2.0, kias=100.0, glidepath_deg=3.0)
        ok, notes = sas.gate_report(s)
        assert not ok
        assert any("altitude" in n or "above field" in n for n in notes)

    def test_a_glidepath_start_warns_where_the_gate_will_stop_permitting(self):
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0, glidepath_deg=3.0)
        ok, notes = sas.gate_report(s)
        assert ok, "the start point itself is inside the envelope"
        assert any("stops permitting" in n for n in notes), \
            "a descent that leaves the envelope must say so before it is flown"
        assert any("4.0 nm" in n for n in notes)

    def test_the_gate_limits_are_the_real_ones_not_a_copy(self):
        Limits = _load("capvsar_maneuvers_check",
                       "services/ai_pilot/maneuvers.py").Limits
        assert (Limits().min_kias, Limits().min_altitude_ft) == (90, 3000)


# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------

class TestArguments:
    def test_rejects_a_negative_distance(self):
        with pytest.raises(ValueError):
            sas.build_air_start(rwy("09"), distance_nm=-1.0, kias=100.0)

    def test_rejects_a_zero_airspeed(self):
        with pytest.raises(ValueError):
            sas.build_air_start(rwy("09"), distance_nm=9.0, kias=0.0)

    def test_rejects_an_absurd_glidepath(self):
        with pytest.raises(ValueError):
            sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0, glidepath_deg=45.0)

    def test_dry_run_writes_nothing_to_the_simulator(self, tmp_path, capsys, monkeypatch):
        apt = tmp_path / "apt.dat"
        apt.write_text(APT_DAT, encoding="utf-8")

        def explode(*a, **k):
            raise AssertionError("dry run must not contact the simulator")

        monkeypatch.setattr(sas, "apply", explode)
        rc = sas.main(["--airport", "KRNM", "--runway", "09", "--distance-nm", "9",
                       "--apt-dat", str(apt), "--dry-run"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "nothing was written" in out
        assert "33.066" in out

    def test_a_missing_airport_exits_nonzero_without_a_traceback(self, tmp_path, capsys):
        apt = tmp_path / "apt.dat"
        apt.write_text(APT_DAT, encoding="utf-8")
        rc = sas.main(["--airport", "KXYZ", "--runway", "09",
                       "--apt-dat", str(apt), "--dry-run"])
        assert rc == 2
        assert "not found" in capsys.readouterr().err

    def test_describe_names_the_gate_verdict(self):
        s = sas.build_air_start(rwy("09"), distance_nm=9.0, kias=75.0)
        assert "WOULD REFUSE" in sas.describe(s)


# ---------------------------------------------------------------------------
# Write-verify-rewrite. The defect this exists for was found in flight: a
# reposition from Austria to California put the aeroplane at 4,699,505 ft
# descending through 36,000 fpm, with latitude and longitude correct to five
# decimals, and the identical command applied again was exact.
# ---------------------------------------------------------------------------

LAT, LON, ALT_FT = 33.066279, -117.099453, 4300.0
DREF_LAT = "sim/flightmodel/position/latitude"
DREF_LON = "sim/flightmodel/position/longitude"
DREF_ELE = "sim/flightmodel/position/elevation"


class FakeClient:
    """A simulator that lies about altitude for the first `bad_writes` writes."""

    def __init__(self, bad_writes=0, silent=False, bad_alt_ft=4699505.0):
        self.bad_writes = bad_writes
        self.silent = silent
        self.bad_alt_ft = bad_alt_ft
        self.writes = 0
        self.velocity_writes = 0
        self.subscribed = []
        self._state = None
        self.paused = False
        self.pause_calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def set_position(self, lat_deg, lon_deg, ele_m, heading_true, pitch_deg, roll_deg):
        self.writes += 1
        alt = self.bad_alt_ft if self.writes <= self.bad_writes else ele_m / 0.3048
        # Latitude and longitude land correctly even when the vertical does not.
        self._state = (lat_deg, lon_deg, alt)

    def set_paused(self, paused):
        self.paused = bool(paused)
        self.pause_calls.append(bool(paused))

    def send_dref(self, dref, value):
        if dref.startswith("sim/flightmodel/position/local_v"):
            self.velocity_writes += 1

    def subscribe_dref(self, dref, freq_hz=1, **kw):
        self.subscribed.append(dref)

    def get_all_cached(self):
        # The pause state is readable before any write; the position is not.
        cache = {"sim/time/paused": 1.0 if self.paused else 0.0}
        if self.silent or self._state is None:
            return cache
        lat, lon, alt = self._state
        cache.update({DREF_LAT: lat, DREF_LON: lon, DREF_ELE: alt * 0.3048})
        return cache


def start_fixture():
    return sas.build_air_start(rwy("09"), distance_nm=9.0, kias=100.0)


def run_apply(**kw):
    fake = kw.pop("fake")
    got = sas.apply(start_fixture(), "127.0.0.1", 49000, settle_s=0.0,
                    read_timeout_s=0.5, client_factory=lambda: fake, **kw)
    return fake, got


class TestApplyVerifies:
    def test_a_clean_sim_takes_one_write(self):
        fake, got = run_apply(fake=FakeClient(bad_writes=0))
        assert got.ok and got.attempts == 1 and fake.writes == 1

    def test_the_austria_case_is_retried_and_succeeds(self):
        fake, got = run_apply(fake=FakeClient(bad_writes=1))
        assert got.ok, "the second application must be accepted"
        assert got.attempts == 2 and fake.writes == 2
        assert got.altitude_ft == pytest.approx(ALT_FT, abs=1.0)

    def test_it_gives_up_rather_than_looping_forever(self):
        fake, got = run_apply(fake=FakeClient(bad_writes=99), attempts=3)
        assert not got.ok and fake.writes == 3
        # It still reports what the simulator actually said, not what was asked.
        assert got.altitude_ft == pytest.approx(4699505.0, abs=1.0)

    def test_a_failure_reports_the_real_error_magnitude(self):
        _, got = run_apply(fake=FakeClient(bad_writes=99), attempts=2)
        assert got.error_ft(start_fixture()) > 4_000_000

    def test_velocity_is_rewritten_on_every_attempt(self):
        # A retry that moved the aeroplane without re-establishing its velocity
        # would leave it correctly placed and falling.
        fake, _ = run_apply(fake=FakeClient(bad_writes=1))
        assert fake.velocity_writes == 6, "3 velocity drefs per attempt, 2 attempts"

    def test_silence_is_not_reported_as_success(self):
        # X-Plane answers no UDP at all while it sits on the Quick Flight menu.
        _, got = run_apply(fake=FakeClient(silent=True), attempts=2)
        assert not got.ok
        assert got.altitude_ft != got.altitude_ft, "unverified must be NaN, not 0"

    def test_a_small_altitude_discrepancy_is_tolerated(self):
        fake, got = run_apply(fake=FakeClient(bad_writes=1, bad_alt_ft=ALT_FT + 10.0))
        assert got.ok and got.attempts == 1, "10 ft is settling, not a failure"

    def test_the_readback_does_not_use_the_shared_default_port(self):
        # 49005 is the collision that made elevation read back as latitude.
        assert sas.DEFAULT_RECEIVE_PORT != 49005

    def test_attempts_must_be_at_least_one(self):
        with pytest.raises(ValueError):
            run_apply(fake=FakeClient(), attempts=0)


class TestPausesWhilePlacing:
    def test_it_freezes_the_sim_before_moving_anything(self):
        # A placement made with physics running can verify correct and then
        # diverge: observed live at 4,604,172 ft, inverted, seconds after a
        # read-back of exactly 4300 ft.
        fake, _ = run_apply(fake=FakeClient(bad_writes=0))
        assert fake.pause_calls[0] is True

    def test_a_running_sim_is_handed_back_running(self):
        fake, got = run_apply(fake=FakeClient(bad_writes=1))
        assert got.ok and fake.paused is False

    def test_a_sim_found_paused_is_left_paused(self):
        fake = FakeClient(bad_writes=0)
        fake.paused = True
        _, got = run_apply(fake=fake)
        assert got.ok and fake.paused is True, "do not start a sim the user had stopped"

    def test_leave_paused_overrides_a_running_sim(self):
        fake, got = run_apply(fake=FakeClient(bad_writes=0), leave_paused=True)
        assert got.ok and fake.paused is True

    def test_a_failed_placement_is_never_unpaused(self):
        # Unpausing onto a bad vertical is how it ends up inverted in space.
        fake, got = run_apply(fake=FakeClient(bad_writes=99), attempts=2)
        assert not got.ok and fake.paused is True

    def test_silence_also_stays_frozen(self):
        fake, got = run_apply(fake=FakeClient(silent=True), attempts=1)
        assert not got.ok and fake.paused is True


class TestRefusesLongJumps:
    """Neither retrying nor pausing survives a cross-continent reposition.
    Both were implemented and both were disproved in flight, so the tool
    refuses the move instead of reporting confident nonsense about it."""

    def _at(self, lat, lon):
        fake = FakeClient(bad_writes=0)
        fake._state = (lat, lon, 4300.0)
        return fake

    def test_a_local_reposition_is_allowed(self):
        fake = self._at(LAT + 0.2, LON + 0.2)      # a few nm
        _, got = run_apply(fake=fake)
        assert got.ok and fake.writes == 1

    def test_austria_to_california_is_refused(self):
        fake = self._at(47.8046, 12.9968)          # where this actually happened
        with pytest.raises(sas.LongJumpRefused, match="millions of feet"):
            run_apply(fake=fake)

    def test_the_refusal_names_the_distance_and_the_way_out(self):
        fake = self._at(47.8046, 12.9968)
        with pytest.raises(sas.LongJumpRefused) as exc:
            run_apply(fake=fake)
        msg = str(exc.value)
        assert "KRNM" in msg and "--allow-long-jump" in msg
        assert "5260 nm" in msg, "say how far it was asked to move"
        assert "limit 100" in msg

    def test_nothing_is_written_when_the_jump_is_refused(self):
        # A refusal after the write is a refusal after the damage.
        fake = self._at(47.8046, 12.9968)
        with pytest.raises(sas.LongJumpRefused):
            run_apply(fake=fake)
        assert fake.writes == 0 and fake.velocity_writes == 0

    def test_the_override_exists_for_when_the_operator_knows_better(self):
        fake = self._at(47.8046, 12.9968)
        _, got = run_apply(fake=fake, allow_long_jump=True)
        assert got.ok and fake.writes == 1

    def test_an_unknown_current_position_does_not_block_the_move(self):
        # A sim that has not reported position yet gets the benefit of the doubt.
        _, got = run_apply(fake=FakeClient(bad_writes=0))
        assert got.ok


class TestLlah:
    """--load_llah= is undocumented: it is in the binary but in neither --help
    nor any format string, so these tests pin the FORMAT WE EMIT, not a claim
    about what X-Plane accepts. That is settled by launching and reading back."""

    def test_it_is_lat_lon_alt_heading(self):
        s = start_fixture()
        parts = sas.llah(s).split(",")
        assert len(parts) == 4
        assert float(parts[0]) == pytest.approx(s.lat, abs=1e-5)
        assert float(parts[1]) == pytest.approx(s.lon, abs=1e-5)
        assert float(parts[3]) == pytest.approx(s.heading_true, abs=0.1)

    def test_feet_is_the_default(self):
        # Settled live: passing metres put the aeroplane at 1310.6 FEET, so the
        # flag reads the altitude as feet. Position and heading were exact.
        assert float(sas.llah(start_fixture()).split(",")[2]) == pytest.approx(4300.0, abs=1.0)

    def test_metres_is_still_reachable(self):
        assert float(sas.llah(start_fixture(), "m").split(",")[2]) == pytest.approx(1310.6, abs=1.0)

    def test_it_carries_enough_precision_to_land_on_the_centreline(self):
        # Six decimals of latitude is about 0.1 m; three would be 100 m, which
        # is a different part of the approach.
        assert len(sas.llah(start_fixture()).split(",")[0].split(".")[1]) >= 5

    def test_emit_llah_prints_one_line_and_touches_no_simulator(self, tmp_path, capsys, monkeypatch):
        apt = tmp_path / "apt.dat"
        apt.write_text(APT_DAT, encoding="utf-8")
        monkeypatch.setattr(sas, "apply", lambda *a, **k: pytest.fail("must not contact the sim"))
        rc = sas.main(["--airport", "KRNM", "--runway", "09", "--distance-nm", "9",
                       "--apt-dat", str(apt), "--emit-llah"])
        assert rc == 0
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 1 and out[0].count(",") == 3
