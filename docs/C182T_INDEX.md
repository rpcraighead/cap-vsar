# CAP 487 Cessna 182T: which document is authoritative for what

The aircraft is built locally by `scripts/build_c182t_package.py` from the
Laminar C172SP G1000 (cockpit and systems) and a pinned GPL FlightGear C182
exterior. These documents describe it; when two disagree, the one listed here
for that subject wins.

| Subject | Authoritative document | Notes |
|---|---|---|
| Sources, hashes, dimensions, stations, unknowns | [C182T_DIMENSION_MASTER.md](C182T_DIMENSION_MASTER.md) + `scripts/c182t_dimension_master.json` | POH 182TPHBUS, TCDS 3A13 Rev 66, Cessna S&D; the JSON is what tests read |
| Exterior licence, donor pin, distribution | [FLIGHTGEAR_C182_GPL_PLAN.md](FLIGHTGEAR_C182_GPL_PLAN.md) | Decision D-7: production licence route out of scope; never redistribute the built package |
| Geometry corrections to the donor mesh | `scripts/c182t_corrections.json` + [C182T_MEASUREMENT_HARNESS.md](C182T_MEASUREMENT_HARNESS.md) | Prop diameter, main-wheel track, horizontal tail span |
| ACF parameters (speeds, weights, engine, prop, gear, travels) | `ACF_PATCHES` in `scripts/build_c182t_package.py` | Every value cites its source in-line; `tests/test_c182t_acf_sources.py` pins them to the master |
| Flight-model performance and calibration | [C182T_FLIGHT_MODEL_CALIBRATION.md](C182T_FLIGHT_MODEL_CALIBRATION.md) | B1/C1/C2 results by date and ACF hash |
| Performance targets | [C182T_FLIGHT_TEST_CARD.md](C182T_FLIGHT_TEST_CARD.md) | POH-sourced; who flies, conditions |
| Handling cards (H0-H7) | [C182T_HANDLING_TEST_MATRIX.md](C182T_HANDLING_TEST_MATRIX.md), [C182T_H0_CONTROL_LAW_FINDINGS.md](C182T_H0_CONTROL_LAW_FINDINGS.md) | Controller-in-the-loop, not airframe characterisation |
| Paint | [C182_CAP_LIVERY_ADAPTATION.md](C182_CAP_LIVERY_ADAPTATION.md) | CAP 487 default; N429CP named livery |
| Review findings and their status | [C182T_REVIEW_2026-10-11.md](C182T_REVIEW_2026-10-11.md) + tracker cluster C18 (`A2-n`) in `docs/bugs/tracker.json` | |
| AI pilot on the C182T | `docs/C182T_AI_PILOT_PORT_2026-10-11.md` on the AI pilot branch | `services/ai_pilot/aircraft_profiles.py` holds the C182T speeds |
| History | `CHANGELOG.md` | Records what was true when written; later entries supersede |

Ground and flight checks are scripted: `scripts/c182t_ground_check.py`
(wheel geometry, static RPM, propeller screenshots) and
`scripts/c182t_perf_card.py` (C1, B1, C2 on the aircraft's own autopilot);
evidence lands in `~/.cache/capvsar/flight-tests/` and the summaries in
`docs/evidence/c182t-2026-10-11/`.
