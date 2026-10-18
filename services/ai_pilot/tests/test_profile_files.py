"""Aircraft profiles as data: the migration proof, and the loader's strictness."""
from dataclasses import replace
import json
from pathlib import Path
import shutil

import pytest

from services.ai_pilot import aircraft_profiles
from services.ai_pilot.aircraft_profiles import C172SP, C182T, PROFILES, AircraftProfile, profile_for
from services.ai_pilot.profile_loader import PROFILE_DIR, ProfileError, load_profile, load_profiles
from services.ai_pilot.tests import golden_profiles
from scripts.ai_pilot_experiment import stage_observer, validate_staged_profile


# --- the migration: moving the numbers to files changed none of them ----------------------------

def test_the_files_load_to_profiles_equal_to_the_old_python_definitions():
    # Everything the Python literals carried. The measured `performance` table did not exist then; it is
    # new data a file may add, and is tested in test_performance.py.
    assert replace(load_profile(PROFILE_DIR / "c172sp.toml"), performance=None) == golden_profiles.C172SP
    assert replace(load_profile(PROFILE_DIR / "c182t.toml"), performance=None) == golden_profiles.C182T


def test_the_registry_is_built_from_the_files_and_the_module_attributes_still_work():
    assert set(PROFILES) == {"C172SP", "C182T"}
    assert C172SP is PROFILES["C172SP"] and C182T is PROFILES["C182T"]
    assert profile_for("Cessna_182T_G1000.acf") is C182T and profile_for("C172SP") is C172SP
    assert C172SP.tuning_validated is False and C182T.tuning_validated is False
    assert C182T.constant_speed_prop and not C172SP.constant_speed_prop
    assert C182T.landing_toe_brakes and C172SP.landing_toe_brakes
    assert C182T.flare_start_agl_ft == 28. and C172SP.flare_start_agl_ft == 17.5


def test_every_profile_in_the_directory_is_a_valid_profile():
    for profile in load_profiles().values():
        assert isinstance(profile, AircraftProfile) and profile.sources.get("tuning")


def test_staged_surface_profile_checks_aircraft_hash_prop_and_takeoff_flap():
    inv = {"aircraft": {"path": "/sim/Cessna_182T_G1000.acf", "sha256": "a"*64}}
    config = {"mode": "surface", "aircraft_path": inv["aircraft"]["path"],
              "aircraft_sha256": inv["aircraft"]["sha256"],
              "constant_speed_prop": True, "surface_takeoff_flap_ratio": C182T.takeoff_flap_ratio}
    validate_staged_profile(config, C182T, inv, mode="surface")
    for changed in ({**config, "constant_speed_prop": False},
                    {**config, "surface_takeoff_flap_ratio": 0.},
                    {**config, "aircraft_sha256": "b"*64}):
        with pytest.raises(ValueError, match="Staged|aircraft"):
            validate_staged_profile(changed, C182T, inv, mode="surface")


def test_staged_landing_config_selects_toe_brakes_for_c182_profile():
    inv = {"aircraft": {"path": "/sim/Cessna_182T_G1000.acf", "sha256": "a"*64}}
    config = {"mode": "landing", "aircraft_path": inv["aircraft"]["path"],
              "aircraft_sha256": inv["aircraft"]["sha256"],
              "constant_speed_prop": True, "landing_toe_brakes": True}
    validate_staged_profile(config, C182T, inv, mode="landing")
    with pytest.raises(ValueError, match="brake path"):
        validate_staged_profile({**config, "landing_toe_brakes": False}, C182T, inv, mode="landing")
    from xplane.capvsar_qualification import STOCK_SHA256
    c172_inventory = {"aircraft": {"path": "/sim/Cessna_172SP_G1000.acf",
                                    "sha256": STOCK_SHA256}}
    c172_config = {"mode": "landing", "aircraft_path": c172_inventory["aircraft"]["path"],
                   "aircraft_sha256": c172_inventory["aircraft"]["sha256"],
                   "constant_speed_prop": False, "landing_toe_brakes": True}
    validate_staged_profile(c172_config, C172SP, c172_inventory, mode="landing")


def test_stage_mission_gfc_envelope_is_trial_specific(monkeypatch, tmp_path):
    from xplane import capvsar_qualification
    monkeypatch.setattr(capvsar_qualification, "aircraft_identity_ok", lambda *_args: True)
    aircraft = tmp_path / "Cessna_172SP_G1000.acf"
    aircraft.write_text("test aircraft")
    destination = tmp_path / "gfc-stage"
    stage_observer(destination, aircraft, mode="mission", gfc_trial_envelope=True)
    config = json.loads((destination / "capvsar_flight_control_config.json").read_text())
    assert config["gfc_trial_envelope"] is True
    assert config["airborne_max_altitude_ft"] == 8500.
    assert config["extra_airborne_boxes"] == [[33., 33.35, -116.85, -116.70]]


# --- strictness: an aircraft file must state everything and nothing may be misspelt -----------

@pytest.fixture
def lab(tmp_path):
    """A scratch copy of the C182T file to damage."""
    path = tmp_path / "x.toml"
    shutil.copy(PROFILE_DIR / "c182t.toml", path)
    return path


def damaged(path, old, new, count=1):
    text = path.read_text()
    assert text.count(old) >= 1, old
    path.write_text(text.replace(old, new, count))
    return path


def test_a_missing_value_is_an_error_not_a_default_inherited_from_the_c172(lab):
    damaged(lab, "cruise_base = 0.55\n", "")
    with pytest.raises(ProfileError, match=r"\[throttle\] is missing 'cruise_base'.*nothing is inherited"):
        load_profile(lab)


@pytest.mark.parametrize("table", ["landing", "engine", "throttle", "envelope", "prop", "flaps", "vfe"])
def test_a_missing_section_is_an_error(lab, table):
    text = lab.read_text()
    lab.write_text(text.replace("\n[%s]\n" % table, "\n[renamed_%s]\n" % table, 1))
    with pytest.raises(ProfileError):
        load_profile(lab)


def test_unknown_sections_and_keys_are_errors_so_a_typo_cannot_fall_back_to_a_default(lab):
    damaged(lab, "cruise_base = 0.55", "cruise_basee = 0.55")
    with pytest.raises(ProfileError, match="unknown key"):
        load_profile(lab)
    other = lab.with_name("y.toml")
    other.write_text(lab.read_text().replace("cruise_basee", "cruise_base") + "\n[surprise]\nx = 1\n")
    with pytest.raises(ProfileError, match="unknown section"):
        load_profile(other)


@pytest.mark.parametrize("old,new,match", [
    ("vr = 55.0", 'vr = "fast"', "must be a number"),
    ("vr = 55.0", "vr = true", "must be a number"),
    ("constant_speed = true", "constant_speed = 1", "must be true or false"),
    ("threshold_kias = [64.0, 72.0]", "threshold_kias = [64.0]", "list of two numbers"),
    ('stage_names = ["10deg", "20deg", "38deg"]', 'stage_names = ["10deg"]', "three names"),
    ('key = "C182T"', 'key = ""', "non-empty string"),
])
def test_wrong_types_are_errors_that_name_the_file_and_the_key(lab, old, new, match):
    damaged(lab, old, new)
    with pytest.raises(ProfileError, match=match) as error:
        load_profile(lab)
    assert "x.toml" in str(error.value)


def test_the_physics_checks_still_apply_to_a_file(lab):
    # a flap gate that would select flaps above Vfe
    damaged(lab, "max_kias = 95.0", "max_kias = 150.0")
    with pytest.raises(ProfileError, match="above Vfe"):
        load_profile(lab)


def test_a_fixed_pitch_aircraft_cannot_claim_a_prop_cruise_setting(lab):
    damaged(lab, "constant_speed = true", "constant_speed = false")
    damaged(lab, "cruise_ratio = 1.0", "cruise_ratio = 0.9")
    with pytest.raises(ProfileError, match="fixed-pitch"):
        load_profile(lab)


def test_a_profile_must_say_where_its_numbers_came_from(lab):
    text = lab.read_text()
    head = text[:text.index("\n[sources]\n") + 1]
    lab.write_text(head)
    with pytest.raises(ProfileError, match=r"\[sources\]"):
        load_profile(lab)
    lab.write_text(head + '[sources]\nhandbook = "p. 1"\n')
    with pytest.raises(ProfileError, match="'tuning' entry"):
        load_profile(lab)


def test_landing_gates_need_the_exact_fields(lab):
    damaged(lab, "inside_m = 1852.0\n", "")
    with pytest.raises(ProfileError, match="landing gate needs exactly"):
        load_profile(lab)


def test_unreadable_or_invalid_toml_is_a_profile_error(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("this is = = not toml")
    with pytest.raises(ProfileError, match="cannot read profile"):
        load_profile(bad)
    with pytest.raises(ProfileError, match="cannot read profile"):
        load_profile(tmp_path / "missing.toml")


# --- adding an aircraft is adding a file ------------------------------------------------------------

def test_a_new_aircraft_is_a_new_file_and_duplicates_are_refused(tmp_path):
    directory = tmp_path / "profiles"
    directory.mkdir()
    shutil.copy(PROFILE_DIR / "c172sp.toml", directory / "c172sp.toml")
    text = (PROFILE_DIR / "c182t.toml").read_text()
    (directory / "c182t.toml").write_text(text)
    third = text.replace('key = "C182T"', 'key = "N999"').replace(
        'acf_name = "Cessna_182T_G1000.acf"', 'acf_name = "Other.acf"')
    (directory / "n999.toml").write_text(third)
    assert set(load_profiles(directory)) == {"C172SP", "C182T", "N999"}
    (directory / "copy.toml").write_text(text)
    with pytest.raises(ProfileError, match="duplicate profile key"):
        load_profiles(directory)
    with pytest.raises(ProfileError, match="no aircraft profiles"):
        load_profiles(tmp_path)


def test_the_module_no_longer_carries_the_numbers():
    source = Path(aircraft_profiles.__file__).read_text()
    assert "AircraftProfile(\n    key=" not in source and "vr_kias=55." not in source


# --- no controller defaults to a particular aircraft -------------------------------------------------

def test_no_controller_or_observer_takes_a_default_aircraft():
    """A new aircraft must never silently fly C172 numbers: every controller and observer that reads
    a profile requires one from its caller (removed 2026-10-15; they defaulted to the C172SP)."""
    import inspect
    from services.ai_pilot.ground_guidance import TaxiGuidance
    from services.ai_pilot.ksee_kmyf_mission import MissionController
    from services.ai_pilot.landing_trial import LandingController, LandingObserver
    from services.ai_pilot.runway_entry import RunwayEntryGuidance
    from services.ai_pilot.search_patterns import CruiseLaw, SearchPatternController
    from services.ai_pilot.takeoff_guidance import TakeoffGuidance
    for cls in (TaxiGuidance, MissionController, LandingController, LandingObserver, RunwayEntryGuidance,
                SearchPatternController, TakeoffGuidance, CruiseLaw):
        parameter = inspect.signature(cls).parameters["profile"]
        assert parameter.default is inspect.Parameter.empty, cls.__name__
    with pytest.raises(TypeError, match="profile"):
        MissionController("runway_climb")
    with pytest.raises(TypeError, match="profile"):
        LandingController("KMYF 28R")


def test_no_module_source_names_a_default_aircraft_in_a_signature():
    import re
    root = Path(aircraft_profiles.__file__).parent
    offenders = [p.name for p in root.glob("*.py")
                 if re.search(r"profile\s*(:\s*\w+)?\s*=\s*(C172SP|C182T)\b", p.read_text())]
    assert offenders == []


@pytest.mark.parametrize("script", ["ai_pilot_pattern.py", "ai_pilot_ksee_kmyf.py", "ai_pilot_surface.py",
                                    "ai_pilot_landing.py", "ai_pilot_experiment.py"])
def test_the_runners_refuse_to_start_without_a_named_aircraft(script):
    import subprocess
    import sys
    scripts = Path(aircraft_profiles.__file__).parents[2] / "scripts"
    args = {"ai_pilot_pattern.py": ["--config", "c", "--output", "o", "--pattern", "parallel", "--lat", "0", "--lon", "0"],
            "ai_pilot_ksee_kmyf.py": ["--config", "c", "--output", "o"],
            "ai_pilot_surface.py": ["--config", "c", "--output", "o"],
            "ai_pilot_landing.py": ["fly", "--config", "c", "--output", "o"],
            "ai_pilot_experiment.py": ["observe", "--config", "c", "--output", "o"]}[script]
    done = subprocess.run([sys.executable, str(scripts / script), *args], capture_output=True, text=True, timeout=60)
    assert done.returncode == 2 and "--profile" in done.stderr, done.stderr[-400:]
