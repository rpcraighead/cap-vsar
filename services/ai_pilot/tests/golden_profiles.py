"""Golden copies of the two aircraft profiles exactly as they were written in Python before they
moved to TOML (feat/aircraft-profile-config, 2026-10-15). The migration test asserts that the files
load to profiles EQUAL to these, so moving the data cannot change a value. Delete this module, and
the test that uses it, once the TOML files have been through a flight campaign of their own."""
from services.ai_pilot.aircraft_profiles import AircraftProfile, FlapGate


C172SP = AircraftProfile(
    key="C172SP",
    acf_name="Cessna_172SP_G1000.acf",
    display_name="X-Plane 12 stock Cessna 172SP G1000",
    vr_kias=55., vx_kias=62., vy_kias=74., climb_enroute_kias=85.,
    cruise_kias=100., approach_initial_kias=100., approach_intermediate_kias=95.,
    approach_clean_kias=80., ils_final_kias=73., final_approach_kias=65.,
    missed_kias=74., vfe_kias=((1/3, 110.), (1., 85.)), va_kias=105.,
    takeoff_flap_ratio=0., flap_retract_kias=70., flap_retract_agl_ft=300.,
    search_kias=90.,
    tuning_validated=True,
    sources={
        "vr/vx/vy": "bundled X-Plane_C172_Pilot_Operating_Manual.pdf: rotate 55, Vx 62, Vy 74 KIAS "
                    "(docs/C172_KSEE_KMYF_IFR_TRIAL.md)",
        "vfe/va": "same manual: flaps 10 deg 110 KIAS, 10-30 deg 85 KIAS; Va 105 KIAS at 2550 lb",
        "other speeds": "controller values flown on the 2026-10-11 KSEE-KMYF sortie "
                        "(services/ai_pilot/ksee_kmyf_mission.py, landing_trial.py)",
        "tuning": "C172 trials 2026-10-10/11; the 62-68 KIAS threshold window and 5-7 deg "
                  "touchdown pitch are LandingObserver engineering criteria",
    },
)


C182T = AircraftProfile(
    key="C182T",
    acf_name="Cessna_182T_G1000.acf",
    display_name="CAP 487 Cessna 182T NAV III (local prototype package)",
    # POH Section 4, Normal Takeoff: flaps UP-20 deg (10 deg preferred), lift
    # nosewheel at 50-60 KIAS, climb 70 KIAS (flaps 20) / 80 KIAS (flaps up).
    vr_kias=55.,
    # POH Section 4 / Section 5: Vx 65 KIAS and Vy 80 KIAS at sea level.
    vx_kias=65., vy_kias=80.,
    # POH Section 4, Enroute Climb: 85-95 KIAS at 23 in.hg / 2400 RPM.
    climb_enroute_kias=90.,
    # Exercise cruise: the README's FLC exercise target; inside the 55-80 %
    # power band of POH Section 4 Cruise and the 90-140 KIAS exercise envelope.
    cruise_kias=110.,
    approach_initial_kias=100., approach_intermediate_kias=95.,
    # POH Section 4, Normal Landing: 70-80 KIAS flaps up; flaps 10 deg below
    # 140, 10-20 deg below 120, 20-FULL below 100; 60-70 KIAS flaps FULL.
    approach_clean_kias=85., ils_final_kias=80., final_approach_kias=68.,
    # POH Section 4, Balked Landing: full power, flaps 20 deg, 55 KIAS, retract
    # slowly after a safe altitude and 70 KIAS. 70 KIAS (the flaps-20 climb
    # speed of Normal Takeoff) is used for the controller's missed-approach
    # climb rather than 55, which is an obstacle-clearance speed.
    missed_kias=70.,
    # POH Section 2, Figure 2-1: Vfe 140 (up-10), 120 (10-20), 100 (20-FULL).
    vfe_kias=((1/3, 140.), (2/3, 120.), (1., 100.)),
    # POH Section 2: Va 110 KIAS at 3100 lb.
    va_kias=110.,
    # Normal takeoff with 10 deg, retracted above 70 KIAS (POH Short Field
    # Takeoff item 9) once clear of the runway environment.
    takeoff_flap_ratio=1/3, flap_retract_kias=70., flap_retract_agl_ft=300.,
    # CAP visual search speed for the 182 (training value, not a POH figure).
    search_kias=100.,
    # --- tuning: C172 values moved up by the final-approach speed difference ---
    final_speed_add_kias=5.,
    threshold_kias=(64., 72.),
    landing_flap_gates=(FlapGate(1/3, 1852., 95.), FlapGate(2/3, 926., 85.),
                        FlapGate(1., 0., 0.)),
    flap_stage_names=("10deg", "20deg", "38deg"),
    touchdown_pitch_deg=(5., 8.),
    touchdown_max_groundspeed_kt=80.,
    missed_flap_ratio=2/3, ils_flap_ratio=1/3,
    min_roll_rpm=2000.,
    # The C172 taxi law, unchanged; the IO-540's idle thrust and the governed
    # propeller will move it (measure on the first taxi-only trial).
    taxi_base_throttle=.16, taxi_speed_gain=.08, taxi_max_throttle=.28,
    cruise_base_throttle=.55, ils_base_throttle=.48, approach_base_throttle=.28,
    envelope_kias=(80., 140.),
    # 3-blade McCauley constant-speed prop (ACF _prop_type 1, governor 2400 RPM).
    # Cruise ratio is full forward until the cruise-cycle trial measures the
    # lever-to-RPM map (docs/C182T_AI_PILOT_PROP_2026-10-15.md).
    constant_speed_prop=True, prop_cruise_ratio=1.,
    tuning_validated=False,
    sources={
        "handbook": "Cessna 182T NAV III GFC 700 AFCS information manual, P/N 182TPHBUS, "
                    "SHA-256 ba64adab5d6ed543f73b330f24301e72fdaba4f729c3661075fa55173fd2705c",
        "vr": "Section 4 Normal Takeoff: lift nosewheel at 50-60 KIAS (55 used)",
        "vx/vy": "Section 4 Maximum Performance Climb: 80 KIAS SL; Section 5 Vx 65 KIAS SL",
        "climb_enroute": "Section 4 Enroute Climb: 85-95 KIAS",
        "landing": "Section 4 Normal Landing: 70-80 KIAS flaps up, 60-70 KIAS flaps FULL",
        "missed": "Section 4 Balked Landing: flaps 20, 55 KIAS; retract above 70 KIAS",
        "vfe/va": "Section 2 Figure 2-1",
        "acf": "scripts/build_c182t_package.py ACF_PATCHES: Vs 51, Vso 41, Vx 65, Vy 80, "
               "Vfe 140/100, Vno 140, Vne 175; flap detents 10/20/38 deg",
        "tuning": "NOT VALIDATED: base throttles, flap gates, threshold window and touchdown "
                  "pitch are the C172 criteria shifted to the C182T speeds; see "
                  "docs/C182T_AI_PILOT_PORT_2026-10-11.md",
    },
)
