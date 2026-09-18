# AI-24 — hand-off: ArduPlane accepts guided commands and then ignores them

For whoever picks this up next, cold. Everything you need is here or in the
files named. Read the two "do not" rules first.

## Do not

- **Do not fly anything without a human at the workstation.** This drives a live
  aircraft in X-Plane. Offline work (source reading, code, tests) is safe and is
  where most of this job is. If nobody is watching the simulator, do the offline
  half and stop.
- **Do not widen or bypass `ManeuverGate`.** `services/ai_pilot/maneuvers.py` is
  unchanged by every backend so far; keep it that way. The envelope
  (3,000–6,000 ft indicated, ≥1,000 ft AGL, 90–140 KIAS, ≤35° bank) is the
  safety property, not an obstacle.
- Lane-locked, do not edit: `maneuvers.py`, `maneuver_server.py`,
  `services/ai_pilot/web*`, `fdr*`, `diag*`, `scripts/fly_direct_backend.py`,
  `scripts/fly_card_h0.py`, `docs/BOARD.md`.
- Tests are `unittest` (no pytest on this box). Leave changes uncommitted.

## The problem in one paragraph

On 2026-09-17 ArduPlane flew CAP 487 for the first time. It was in **GUIDED**,
the gate accepted, 33 samples of `executing` ran with **no fault**, bank stayed
inside limits and airspeed stayed in band — but the aircraft flew a **continuous
left circle** (heading 261 → 178 through a full 360° and onward) and **descended
4,616 → 2,974 ft**, tracking neither the commanded heading 300 nor the commanded
altitude 4,500. Both `MAV_CMD_GUIDED_CHANGE_HEADING` and
`MAV_CMD_GUIDED_CHANGE_ALTITUDE` were ACKed `MAV_RESULT_ACCEPTED` — `select()`
raises otherwise, so this is certain. **ArduPilot accepted the commands and did
not act on them**; what it did instead is ModeGuided's default behaviour, which
is to loiter around the point it entered GUIDED at.

Trace: `~/.cache/capvsar/flight-tests/arduplane_backend_20260917-230653.jsonl`
(header carries the full pre-flight block and every constant in force).

## Where to look, in order

ArduPilot source is checked out at `~/.cache/capvsar/ardupilot`, tag
**Plane-4.7.1** (`dbe7921`). Read it; do not trust the wiki, which is behind.

1. **`ArduPlane/mode_guided.cpp`.** `ModeGuided::update()` and `navigate()`.
   Confirm the exact condition under which `guided_state.target_heading` is used
   instead of the loiter path — line ~52 compares it against
   `AP::ahrs().get_yaw_rad()` when `target_heading_type != GUIDED_HEADING_NONE`.
   Then work out what would leave `target_heading_type` as NONE, or leave the
   branch unreached, **after** a command that returned ACCEPTED.
2. **`ArduPlane/GCS_MAVLink_Plane.cpp`**, `handle_command_int_guided_slew_commands`
   (~line 656–750). Check the *order of operations*: what it sets, and whether
   anything later resets it. Note `GUIDED_TIMEOUT` (`Parameters.cpp:1280`,
   default 3.0 s) — the earlier audit concluded it gates forced-RPY/throttle and
   **not** the heading slew, but verify that, because a 3 s timeout would fit
   the observed behaviour exactly.
3. **The `GUIDED_*` PID.** `Parameters.cpp:1187`
   `AP_SUBGROUPINFO(guidedHeading, "GUIDED_", 28, ParametersG2, AC_PID)`.
   `xplane/ardupilot/cap487.parm` currently sets `GUIDED_P 5000`, `GUIDED_I 0`,
   `GUIDED_D 0`. **Those numbers were invented as placeholders** with no
   knowledge of the correct scale. Find AC_PID's own defaults for this subgroup
   and what units the controller works in. A P of the wrong magnitude — or an
   `IMAX`/`FLTE` left at zero — is the prime suspect.
4. **Altitude.** `GUIDED_CHANGE_ALTITUDE` is sent as COMMAND_INT, frame
   `MAV_FRAME_GLOBAL`, `z` in metres **true MSL**, `param3` = 2.5 m/s. Confirm
   against `mavlink_coordinate_frame_to_location_alt_frame`
   (`GCS_Common.cpp:7356`) that GLOBAL → ABSOLUTE is what ArduPlane then flies,
   and check whether TECS is even being given the target. The descent was never
   arrested, so `TECS_*` is unvalidated too (`TECS_CLMB_MAX`/`SINK_MAX` are 2.5).

## How to reproduce offline before touching the simulator

There is a full offline harness. Use it.

```bash
python3 -m unittest discover -s services/ai_pilot/tests -t . 2>&1 | tail -3
```
77 tests, all passing; one pre-existing `test_maneuvers` pytest-import error is
expected and not yours.

`services/ai_pilot/tests/test_arduplane_backend.py` has a `MockLink` that records
every MAVLink frame. Assert on **exactly what bytes go out** — the wire format is
already validated against pymavlink in `test_mavlink_min.py`, so if a frame is
wrong, it is wrong in the *content* the backend chooses, not the encoding.

If you change what `select()` sends, add a packet-intent test for it.

## Running it live (only with a human watching)

X-Plane networking is now correct and must not be re-broken:

| Setting | Value | Why |
|---|---|---|
| Data Output rows | 20 (LatLonAlt) + 136 (JoystickRaw), **network** column | what SITL needs to bootstrap |
| Data Output destination | `127.0.0.1` : `49001` | SITL's listen port |
| `Network → Port we send from (legacy)` | **49501** | X-Plane binds this itself; leaving it at 49001 means X-Plane's own socket eats the data output. **Changing it needs an X-Plane restart.** |

Reset the aircraft (this recipe took a whole session to find — see
`docs/ARDUPLANE_TRIAL.md`):

1. clear a crash: `sim/operation/reset_to_runway`, `sim/operation/fix_all_systems`;
2. **unpause**, then `sim/operation/quick_start`, verify rpm > 700 **with the sim
   running** — an engine cannot spin up with the clock frozen, and rpm reads 0
   regardless of its real state;
3. `scripts/set_air_start.py --airport KRNM --runway 09 --distance-nm 15 --kias 115 --altitude-ft 4500`;
4. hold `sim/flightmodel/position/{P,Q,R,Prad,Qrad,Rrad}` at zero for ~2.5 s
   through the placement transient — placement preserves rotation, so a tumbling
   aeroplane is handed back its tumble (**V2-8**);
5. engage with `sim/cockpit/autopilot/autopilot_mode = 2`. **Mode 1 is flight
   director and flies nothing**; `sim/GPS/g1000n1_ap` is a **toggle**, so pressing
   it on a live autopilot switches it off.

Then:
```bash
python3 scripts/fly_arduplane_backend.py --heading 300 --altitude 4500 \
    --seconds 120 --sim-port-in 49001
```
The launcher owns the SITL process, secures it into LOITER on attach, and on
every exit path parks, stops SITL, clears both X-Plane overrides and re-engages
the GFC 700. That path has now run cleanly many times — trust it, and if you
change the launcher, keep every exit going through `cleanup()`.

Fly **west** over the coastal plain. The 3,000–6,000 ft block with a 1,000 ft
AGL floor does not fit the terrain east of Ramona; the gate paused the sim at
AGL 999 earlier in the session, which is correct but wastes a run.

## Done when

The gate emits **`achieved`** from a stable handoff: heading within 3°, altitude
within 100 ft, bank within 5°, VS within 150 fpm, all held 3 s — trial cases
**T1** and **T2** in `docs/ARDUPLANE_TRIAL.md`. Bank must stay inside
`ROLL_LIMIT_DEG` and the aircraft inside the altitude block throughout.

Record the parameter values that actually worked in the trial log; they are the
deliverable as much as the capture is. Everything in `cap487.parm` is currently
provisional and at least two values in it have already proved badly wrong
(`WP_LOITER_RAD` demanded 80° of bank; `GUIDED_P` is a guess).

## Context worth having

- `services/ai_pilot/README.md` — the backend, the yoke-authority rules, the port map.
- `docs/ARDUPLANE_TRIAL.md` — the trial protocol, the full session log, and the
  handoff design review against the Plane-4.7.1 source (what each mode does, why
  release parks in LOITER, why MANUAL is never used).
- `docs/bugs/AI-21_ARDUPLANE_RELEASE_FIX.md` — the previous hand-off brief, for
  the house style and the safety reasoning behind the detach ordering.
- Tracker: **AI-20** (gate G, open), **AI-21/22/23** (fixed), **AI-24** (this).
- Nothing about ArduPlane may be claimed as working until it is in the trial log
  with a trace filename. Leg 3 flew; it did not capture. Say both.
