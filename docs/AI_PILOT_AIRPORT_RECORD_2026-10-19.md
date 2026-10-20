# AI pilot airport records (2026-10-19)

## What was built

`services/ai_pilot/airports/builder.py` streams the configured apt.dat files and retains only the requested airport block. It builds a JSON-friendly record for each runway end with a value and provenance for each field, plus source values, disagreements, and missing fields. `schema.py` defines the lightweight record types. The builder reads apt.dat runway rows, VGSI rows, traffic-flow and frequency rows, CIFP `RWY:` records, X-Plane earth_nav glide-slope rows, the local FAA NASR extract, and the local Chart Supplement text. It uses only the standard library.

Chart Supplement text is treated as untrusted. Parsed values from it are marked low confidence and the source quotes are retained. The builder decodes X-Plane NAV1200 glide-slope rows using the documented combined field (glide angle × 100,000 plus true course), and retains the raw field and decoded course for audit. See the [X-Plane NAV1200 specification](https://developer.x-plane.com/wp-content/uploads/2016/10/XP-NAV1200-Spec.pdf). The installed `earth_nav.dat` identifies itself as NAV1200, cycle 2406. For the four flown runways, the published VGSI angle remains the preferred input where present.

The apt.dat row 100 parser records the runway-end threshold, displaced-threshold distance, blast-pad length, and markings/approach/TDZ/REIL codes with row provenance. The default apt.dat order uses Global Airports as the base and the installed KSAN v3.0 scenery as an overlay, matching the existing KSAN table entry. The installed custom KSEE apt.dat is included as a comparison-only source: its values appear in disagreements, but do not override the Global Airports geometry used by the existing KSEE table. The builder reports the active geometry source and comparison-only paths explicitly.

The CLI is `scripts/build_airport_record.py ICAO [--runway END] [--json PATH]`. It accepts a four-character ICAO code, prints the record and validation report as JSON, and lowers its process priority before parsing. Example smoke command:

```sh
nice -n 10 python3 scripts/build_airport_record.py KAVX --runway 22 --json /tmp/kavx-airport-record.json
```

## Legacy geometry check

`RunwayGeometry.from_record(record)` constructs the existing geometry type from a runway-end record. Its default aim-point mode preserves the historical displacement input and the constructor's existing 25 ft offset. The optional `aim_point_mode="tch"` selects the proposed TCH formula explicitly; it is not the default. `tch_aim_point_m()` implements the formula.

The synthetic fixture test compares the builder output to the four in-tree `RUNWAYS` entries. Threshold and far-end coordinates match to under 1 m; airport elevation, legacy displacement value, and width match exactly. The table itself was not edited.

| Runway | Legacy elevation (ft) | Legacy displacement slot (m) | Width (m) | Actual table aim point (m) | TCH / angle | Proposed TCH aim (m) |
|---|---:|---:|---:|---:|---:|---:|
| KMYF 28R | 424 | 366 | 46.02 | 373.62 | 41 ft / 3.0° | 604.45 |
| KSAN 27 | 17 | 552 | 61.02 | 559.62 | 66 ft / 3.5° | 880.91 |
| KSEE 27R | 388 | 215 | 29.87 | 222.62 | 45 ft / 4.5° | 389.28 |
| KCRQ 24 | 331 | 305 | 45.72 | 312.62 | 54 ft / 3.2° | 294.39 |

The task description calls KCRQ 24's 305 m value an aim point. In the current code, 305 m is stored in `displaced_threshold_m`, and `RunwayGeometry.__init__` adds 25 ft to every input. Its actual current aim point is therefore 312.62 m. The builder preserves that code behavior and also records the physical displacement as 0 m. The TCH proposal uses the physical 0 m value, not the legacy 305 m compatibility slot.

## Four flown airports: validation findings

The JSON validation report contains side-by-side legacy and proposed TCH aim points for every runway end, with `default_mode: legacy`; the enclosing record carries full per-field source values and disagreements. The main differences are:

| Runway | Selected geometry | Disagreements and source values |
|---|---|---|
| KMYF 28R | Global Airports apt.dat; threshold `(32.8128249, -117.1311307)`, far end `(32.8181752, -117.1447205)` | Airport elevation: apt.dat 424 ft, NASR 427.3 ft, Chart Supplement 427 ft. Displacement: apt.dat 366 m vs CIFP/NASR/chart 365.4552 m. Width: apt.dat 46.02 m vs NASR 45.72 m. Threshold elevation: CIFP 422 ft vs NASR 427.3 ft. CIFP threshold coordinate is 364.63 m from the selected apt.dat coordinate; NASR is 1.19 m away. |
| KSAN 27 | KSAN v3.0 custom apt.dat; threshold `(32.73136873, -117.18062185)`, far end `(32.73659395, -117.20217254)` | Global apt.dat's runway-27 endpoint is 551.47 m from the custom endpoint; global/custom displacement is 551/552 m and width is 60.96/61.02 m. CIFP is within 0.90 m of the custom endpoint; FAA NASR coordinates instead agree with Global Airports. Threshold elevation: CIFP 15 ft vs NASR 16.4 ft. The custom apt.dat flow assigns left traffic to runway 27 for its easterly-wind flow, while NASR and the supplement say right traffic. |
| KSEE 27R | Global Airports apt.dat; threshold `(32.8263994, -116.9642836)`, far end `(32.8294697, -116.9812827)` | The comparison-only custom KSEE apt.dat endpoint is 3.31 m away and gives width 30.48 m vs Global's 29.87 m. CIFP is 211.52 m from the selected endpoint; NASR is 3.70 m away. Displacement: apt.dat 215 m vs CIFP/NASR/chart 215.1888 m. Airport elevation: apt.dat/chart 388 ft vs NASR 387.5 ft. Threshold elevation: CIFP 376 ft vs NASR 387.5 ft. |
| KCRQ 24 | Global Airports apt.dat; threshold `(33.1295232, -117.2722025)`, far end `(33.1269806, -117.2879522)` | Physical displacement is 0 m in apt.dat and CIFP; the NASR displacement field is blank. Airport elevation is 331 ft in apt.dat/chart vs 330.5 ft in NASR. Threshold elevation is 326 ft in CIFP vs 326.3 ft in NASR. The 305 m legacy slot is an explicit compatibility value, not a sourced physical displacement. |

The decoded earth_nav GS angles are 3.0° for KMYF 28R and 3.2° for KCRQ 24; each agrees with its VGSI, NASR, and Chart Supplement angle. KSAN 27 and KSEE 27R have no matching GS row in this earth_nav cycle, so their proposed TCH calculations use the sourced 3.5° and 4.5° VGSI angles.

The design review's KMYF traffic finding is confirmed: apt.dat has no `1101` pattern assignment for either 28R or 10R, while NASR and the Chart Supplement identify both as right traffic. The report keeps the absent apt.dat assignment visible as missing and records the FAA sources separately. At KSEE, apt.dat also has no pattern-flow assignment for 27R; NASR and the supplement say right traffic. KCRQ's apt.dat, NASR, and supplement all say right traffic for 24.

The KMYF and KSEE CIFP runway coordinates differ materially from the selected apt.dat endpoints. The builder reports the exact values instead of choosing CIFP coordinates for geometry. The differences may involve endpoint/displaced-threshold conventions or nav-data currency; this pass did not adjudicate their cause.

## Additional airport smoke checks

The builder was run against eight airport/runway cases spanning seven airports outside the pinned set, plus the pinned KSEE parallel runway, with different runway characteristics:

| Airport/end | Derived sample fields | Could not derive |
|---|---|---|
| KASE 33 (sloped) | 7,835 ft airport elevation; 305 m displacement; 2.0% down gradient; right traffic in NASR/chart | TCH, VGSI angle, GS angle, apt.dat end-specific pattern assignment |
| KAVX 22 (short) | 1,601 ft; no displacement; 1.8% up SW; 39 ft TCH; 3.0° VGSI; right traffic from apt.dat/NASR/chart | ILS GS angle |
| KTVL 18 (displaced) | 6,264 ft; 244 m displacement; 48 ft TCH; 3.0° VGSI | ILS GS angle, gradient, apt.dat end-specific pattern assignment, supplement right-traffic flag |
| KSEE 27R (parallel runways) | 388 ft; 215 m displacement; 0.5% up E; 45 ft TCH; 4.5° VGSI | ILS GS angle, apt.dat end-specific pattern assignment |
| KMMH 27 (right traffic) | 7,126 ft; 45 ft TCH; 3.0° VGSI; right traffic in apt.dat/NASR/chart; 1.0% up W | ILS GS angle |
| KJAC 19 (mountain/high field) | 6,451 ft; 53 ft TCH; 3.0° VGSI and ILS GS; apt.dat says right while NASR says left | Gradient, supplement traffic flag |
| KTRM 12 (multiple conditional flows) | −115 ft; 25 ft TCH; 3.0° VGSI; conditional left traffic in apt.dat and NASR; 0.3% up NW | ILS GS angle, supplement traffic flag |
| KPAE 16R (parallel runways) | 604 ft; 45.72 m width; no displacement; 3.0° VGSI and ILS GS; right traffic in apt.dat/NASR | TCH, gradient, Chart Supplement traffic flag |

The missing list is runway-end-specific. NAV1200 provides decodable GS angles for KJAC 19 and KPAE 16R; the other six smoke-test ends have no matching GS row. Gradient is available where the Chart Supplement's runway-level phrasing can be associated safely with an end.

## Archived replay check

The existing `scripts/ai_pilot_landing.py score TRACE` mechanism was run against every archived landing trace found under `~/.cache/capvsar/ai-pilot/` and `docs/evidence/`. With the legacy runway table and the current observer, 94 of 124 traces produced score objects identical to their archived scores; there were no scoring errors. The observer file's SHA-256 was unchanged during the pass (`a54823463b7ce7db3a7f9db5fa1bee06ea13ca07b10881ed40ab672997b7aab5`). No TCH mode is selected.

The 30 non-identical traces are:

- Six archived snapshots do not contain the observer's required `actuator_readback` field: `kmyf-landing-trial-01-20261010.jsonl`, `kmyf-landing-trial-02-20261010.jsonl`, `kmyf-landing-trial-03-20261010.jsonl`, `kmyf-landing-trial-04-20261010.jsonl`, `kmyf-landing-trial-05-20261010.jsonl`, and `kmyf-landing-trial-06-20261010.jsonl`. The current scorer reports `Malformed landing snapshot: 'actuator_readback'` at the first frame.
- Sixteen scores differ on touchdown criteria: `kmyf-landing-trial-08-20261010.jsonl`, `kmyf-landing-trial-37-direct-right12-less-bank-20261010.jsonl`, `kmyf-landing-trial-45-direct-right12-progressive-aileron-20261010.jsonl`, `kmyf-landing-trial-35-direct-right12-repeat-20261010.jsonl`, `kmyf-landing-trial-11-right15-20261010.jsonl`, `kmyf-landing-trial-39-direct-right12-flare-damping-20261010.jsonl`, `kmyf-landing-trial-36-direct-right12-yaw70-20261010.jsonl`, `kmyf-landing-trial-09-20261010.jsonl`, `kmyf-landing-trial-41-direct-right12-vvi-rate-20261010.jsonl`, `kmyf-landing-trial-10-20261010.jsonl`, `kmyf-landing-trial-43-direct-left12-current-20261010.jsonl`, `kmyf-landing-trial-07-20261010.jsonl`, `kmyf-landing-trial-52-direct-right15-20261010.jsonl`, `kmyf-landing-trial-60-direct-right15-true-aimpoint-20261010.jsonl`, `kmyf-landing-trial-42-direct-right12-integral-decay-20261010.jsonl`, and `landing_c182_kcrq24_20261019d.jsonl`. The worktree contains another agent's in-progress observer edit changing the touchdown window from a fixed 400 ft to `profile.touchdown_window_ft`; this accounts for the changed touchdown acceptance results. That protected file was not edited here.
- Five archived passes are rejected by the current flare check: `kmyf-landing-trial-15-right15-lateflare-20261010.jsonl`, `kmyf-landing-trial-13-left15-delayedflare-20261010.jsonl`, `kmyf-landing-trial-12-delayedflare-20261010.jsonl`, `kmyf-landing-trial-14-lateflare-20261010.jsonl`, and `kmyf-landing-trial-16-low25-slow3-20261010.jsonl` (current reason: `Flare balloon exceeded 1.5 ft`).
- Three traces keep the same overall outcome but have different archived touchdown/diagnostic fields: `kmyf-landing-trial-17-smoothflare-20261010.jsonl`, `kmyf-landing-trial-18-low25-slow3-right15-smoothflare-20261010.jsonl`, and `kmyf-landing-trial-22-crosswind-left12-45-20261010.jsonl`.

These differences were recorded without changing the observer or forcing scores to match. All score files were read-only.

## Verification

- New airport-record tests use synthetic apt.dat, CIFP, earth_nav, NASR, and Chart Supplement fixtures; they do not read the installed X-Plane data.
- CLI smoke command: `nice -n 10 python3 scripts/build_airport_record.py KAVX --runway 22 --json /tmp/kavx-airport-record.json` produced valid JSON with the selected runway and validation report.
- Full-suite test counts are recorded in `.agentdeck/tasks/T1.result.md`.

No simulator or bridge was started.
