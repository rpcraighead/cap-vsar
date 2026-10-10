# ArduPlane bounded SITL trial — CONOPS gate G

**Status:** protocol only. The backend is built and tested offline
(`services/ai_pilot/arduplane_backend.py`, `tests/test_arduplane_backend.py`,
`tests/test_sitl_lifecycle.py`); **nothing below has been flown.** The AI-21
fixes from the design review are in (LOITER/FBWA hand-back, launcher-owned
SITL, detach ordering), so the cases below reflect the corrected design. Running this trial is a decision for the
technical lead with Mission Pilot validators (AI Mission Pilot CONOPS §15), not
something an agent starts on its own.

The CONOPS names exactly two outcomes, and the trial must end in one of them:

> A bounded SITL trial either demonstrates X-Plane 12 compatibility, CAP 487
> tuning and coherent takeover, or records why the X-Plane autopilot remains
> the backend.

The rule the whole trial is built around (CONOPS §7.2): *only one backend may
command the aircraft; the simulated Garmin autopilot and ArduPlane must never
drive the same control surfaces at the same time.*

## What is attached to what

```
X-Plane 12 ──UDP 49001──▶ ArduPlane SITL (--model xplane) ──TCP 5760──▶ fly_arduplane_backend.py
   ▲  ▲                          │                                              │
   │  └──── DREF writes ─────────┘ (yoke ratios, throttle, override_joystick=1) │
   └────────────── RREF 49260 (observe) + CMND pause_on / servos_off_any ───────┘
```

* SITL sets `sim/operation/override/override_joystick=1`. **While SITL is
  alive, the physical yoke reaches X-Plane only through ArduPilot's RC
  passthrough**, and only for the axes mapped in `xplane_plane_cap487.json`.
* The backend observes X-Plane, not ArduPilot; ArduPilot's telemetry is used
  for sanity checks and for the pilot's RC input.
* Heading: gate speaks magnetic, ArduPilot flies true; offset measured live.
  Altitude: gate measures indicated, ArduPilot flies true MSL; offset measured
  at engagement and re-measured if the aircraft levels short.

## Pre-checks (all must pass before `gate.acquire()`)

| # | Check | How | Pass |
|---|---|---|---|
| P1 | X-Plane network ports | `grep -E '_rcv_port|_snd_port' "X-Plane 12/Output/preferences/X-Plane.prf"` | `49000` / `49001` |
| P2 | No other writer | `maneuver_server` not running; `fly_direct_backend.py` / `fly_card_h0.py` not running; GFC 700 disengaged | launcher refuses if the controller lock is held |
| P3 | SITL built at the pinned revision | `scripts/setup_ardupilot_sitl.sh --check` | reports source/venv/build present, names the tag |
| P4 | Joystick axis map | In X-Plane, Settings → Joystick: note which raw axis index is pitch and which is roll; run the launcher `--dry-run`, then live with `--axis-pitch N --axis-roll M` and confirm the pre-flight block shows the axes moving with the yoke | both axes change sign with yoke deflection |
| P5 | SITL attached to *this* aircraft | pre-flight block `ArduPilot − X-Plane true` | within ±100 ft (launcher refuses otherwise, exit 4) |
| P6 | Altimeter set | pre-flight block `indicated → true altitude` | within ±50 ft; record the value |
| P7 | Parameters loaded | SITL started with `--defaults xplane/ardupilot/cap487.parm`; in MAVProxy `param show FS_*`, `param show AIRSPEED_*`, `param show ROLL_LIMIT_DEG` | failsafes 0; `AIRSPEED_MIN 46.3` / `AIRSPEED_MAX 72` / `AIRSPEED_CRUISE 56.6` (m/s — a 22 m/s default `AIRSPEED_MAX` means the parm file did not load); `ROLL_LIMIT_DEG 25`; `TECS_CLMB_MAX 2.5` |
| P8 | Heartbeat and streams | pre-flight block heartbeat age, rc age, gpi age | all < 1 s |
| P9 | Entry condition | aircraft trimmed, 90–140 KIAS, ≥1000 ft AGL, 3000–6000 ft indicated, wings level | launcher refuses otherwise, exit 2 |

Record the pre-flight block verbatim in the trial log (the launcher writes it
into the JSONL trace header).

## Cases

Each case is one launcher run. Traces land in `~/.cache/capvsar/flight-tests/arduplane_backend_*.jsonl`.

| Case | Command | What happens | Evidence for PASS | Evidence for FAIL |
|---|---|---|---|---|
| T0 attach while paused | pause X-Plane, start SITL, watch for DATA and heartbeats | decides whether SITL can be attached without the ~2 s idle-throttle window | heartbeat and `GLOBAL_POSITION_INT` arrive while paused | nothing arrives → SITL must be attached with the sim running |
| T1 heading capture | `--heading <current+60>` | GUIDED, `GUIDED_CHANGE_HEADING` with 3 m/s² centripetal limit (~17° bank, ~3°/s at 110 KIAS) | gate `achieved`; bank ≤25 deg throughout; time to capture recorded | no capture in 60 s, bank >25, gate fault |
| T3a takeover latch | after any T3, without restarting the launcher, submit a new command (only possible once wired to the deck) | backend refuses `select` until `release()` | HTTP 400 / `ValueError` "Pilot took over" | ArduPlane re-enters GUIDED over the pilot |
| T2 altitude capture | `--altitude <current+500>` | `GUIDED_CHANGE_ALTITUDE` at 2.5 m/s | `achieved`; VVI within ±600 fpm; at most one re-target; final indicated within ±40 ft | re-target loop, overshoot >150 ft, KIAS out of 90–140 |
| T3 takeover by yoke | during T1, deflect the yoke ~10 % | backend releases: `HEADING_TYPE_DEFAULT`, then **LOITER** (or **FBWA** if the stick was proven at engagement) | trace `fault` names RC or yoke; ArduPlane parks within 0.5 s; in FBWA the **aircraft follows the yoke**, in LOITER it holds itself while you sort the RC map | aircraft departs, or FBWA does not follow the yoke → RC map wrong → STOP, fix P4 |
| T4 override after detach | after T3, read the launcher's final line | the launcher stops SITL, clears both overrides, then engages the GFC 700 | `override_joystick` reads 0 after release and the GFC 700 holds the aircraft | override still 1 → SITL did not stop → STOP |
| T5 takeover by API | during T1, Ctrl-C | `gate.takeover()` → `release()` → launcher detach | ArduPlane parked (LOITER/FBWA), no pause, SITL stopped, overrides 0, GFC 700 holding | pause was sent, SITL left running, or override still 1 |
| T6 X-Plane telemetry loss | during T1, block UDP 49260 (or pause the RREF relay as in AI-2) | gate fault → `pause_on` | X-Plane paused within 2.5 s; ArduPlane mode **unchanged** | mode change on lost telemetry |
| T7 SITL killed | during T1, `kill` the arduplane process | heartbeat lost → `pause_on` **and** `override_joystick=0`, `override_throttles=0` | X-Plane paused; after un-pausing, the yoke flies the aircraft | yoke dead after un-pause → the override clear did not take → STOP |
| T7a hand-back after a fault | after T6 (SITL alive), Ctrl-C the launcher | `release()` still parks although the backend had paused | launcher's final line names the park mode and reports the overrides cleared | ArduPlane still GUIDED → STOP, do not un-pause |
| T8 G1000 engaged while GUIDED | during T1, press AP on the G1000 | backend releases (parks ArduPlane) | trace fault "autopilot engaged"; only one controller writing afterwards | both still writing (surfaces fighting) |

Envelope faults (T6-style) must pause; takeovers (T3/T5/T8) must release and
must not pause. A case that inverts that is a FAIL regardless of what the
aircraft did.

## Recording the outcome

Add to the trial log, then to the tracker item **AI-20** and `CHANGELOG.md`:

1. ArduPilot revision (`git -C ~/.cache/capvsar/ardupilot describe --tags`), X-Plane build, CAP 487 package hash.
2. The pre-flight block for every run.
3. Per case: PASS/FAIL with the trace filename and the numbers above.
4. The `GUIDED_*`, `TECS_*`, `ROLL_LIMIT_DEG` values actually used (they are provisional in `cap487.parm`).
5. The gate G decision in the CONOPS's own words: *adopt* (ArduPlane demonstrated X-Plane 12 compatibility, CAP 487 tuning and coherent takeover) or *the X-Plane autopilot remains the backend, because …*.

Nothing in this document, the README or the CHANGELOG may claim a live result
until step 5 has been written by the person who flew it.

---

# Trial log

## 2026-09-17 — controller handoff session. Legs 1 and 2 flown; ArduPlane NOT flown

Ron authorized the trial and asked for a handoff chain starting with the
X-Plane autopilot. SITL was built but never attached to the aircraft, so
**gate G remains open and no ArduPlane result is claimed.** What the session
did produce is a set of findings about the handoff itself, which is the part
of gate G the CONOPS calls "coherent takeover".

Environment: X-Plane 12.4.3, CAP 487, airborne west of KRNM. ArduPilot
`Plane-4.7.1` (`dbe7921`) built to `~/.cache/capvsar/ardupilot/build/sitl/bin/arduplane`.

### Flown

| Leg | Controller | Commanded | Captured | Result |
|---|---|---|---|---|
| 1 | `XPlaneAutopilotBackend` via `maneuver_server --live` | hdg 210, 4500 ft | hdg 209.3, alt 4500, AGL 4497, roll +0.8, VS −0 | **achieved** (`control_acquired → accepted → executing → achieved`) |
| 2 | `XPlaneDirectBackend` via `scripts/fly_direct_backend.py` | hdg 240, 3600 ft | hdg 240.6, alt 3594→3603, 110.0 KIAS, roll −0.6, VS +1 fpm | **achieved**; trace `direct_backend_20260917-211851.jsonl` |
| 3 | `ArduPlaneBackend` | — | — | **not flown** |

Leg 2 took the aircraft directly from a live GFC 700 and its capture was the
tighter of the two — airspeed held to a tenth of a knot, VS +1 fpm.

### Findings

**F1 — the aircraft does not hold itself between controllers (operational, important).**
Releasing the X-Plane autopilot and *then* starting the next tool left a ~30 s
gap with nothing flying. CAP 487 departed within seconds: 70° bank and
−3,700 fpm on the first occurrence, inverted (roll +121°, pitch +65°, 24 KIAS)
on the second. Both required a pause and a full recovery.
The handoff must be **overlapped, not sequential**: every backend already
disengages the previous one itself as it takes control
(`sim/autopilot/servos_off_any` in both `XPlaneAutopilotBackend.release` and
`XPlaneDirectBackend.select`). Leg 2 done this way was seamless. Any trial
procedure, and any future `--backend` switch on the deck, must preserve that
ordering — leave the incumbent engaged until the successor takes it.
This also constrains the ArduPlane leg specifically: SITL seizes
`override_joystick` when it attaches, so it cannot coexist with the GFC 700,
and the handoff to and from ArduPlane is a **process lifecycle**, not a mode
change. Start SITL with the simulator paused.

**F2 — the gate's fault path fired for real and paused the simulator.**
Not a drill: AGL reached 999 ft against the 1,000 ft floor, the gate revoked
the lease and sent `pause_on`. From the outside this looks like frozen
telemetry, which is worth knowing before someone debugs the wrong thing.
Corollary: the 3,000–6,000 ft block with a 1,000 ft AGL floor is tight over
the terrain east of Ramona. Fly the trial **west over the coastal plain**;
`--distance-nm 15` on KRNM runway 09 puts the aircraft where the block works.

**F3 — `scripts/set_air_start.py` does not zero body rates, and that is why a
recovered aircraft re-departs.** Repositioning preserves P/Q/R, so placing a
tumbling aeroplane hands it back its rotation. Three placements in a row
departed immediately. Holding
`sim/flightmodel/position/{P,Q,R,Prad,Qrad,Rrad}` at zero for ~2.5 s through
the transient is what finally produced stable flight, every time thereafter.
Recommend the tool damp rates as part of placement. Second, smaller trap: it
does not touch the power controls — the aircraft was placed with the throttle
closed and the prop lever back and flew as a glider. Its own warning covers
the engine but not the throttle/prop state.

**F4 — engage G1000 modes with the commands, not `autopilot_state` bits.**
Writing mode bits to `sim/cockpit/autopilot/autopilot_state` left the GFC 700
in **ROL/PIT** — Ron caught this from the cockpit annunciation, and it
explained a slow circling climb that ignored the heading bug entirely.
`sim/GPS/g1000n1_hdg` / `_flc` / `_alt` engage the real modes.
`sim/GPS/g1000n1_ap` **toggles**: pressing it with the autopilot already on
switched it off and dropped the aircraft into a 1,200 fpm descent. Check
`servos_on` before pressing it. The shipped `XPlaneAutopilotBackend` already
uses the command form for FLC, which is the correct pattern.

**F5 — pymavlink cannot be installed on this workstation.** Its C extension
needs Python headers that are not present, so the wheel build fails. The
stdlib codec decision is what makes the ArduPlane backend runnable here at
all; a pymavlink dependency would have been a hard blocker. `setup_ardupilot_sitl.sh`
now treats pymavlink/MAVProxy as optional and reports the loss of the
`sim_vehicle.py` path.

**F6 — ArduPlane is the wrong tool for an ILS (scope finding).** Asked whether
ArduPlane could fly the KMYF ILS 28R from BAKEL at 4,600 ft and land:
ArduPilot navigates by GPS and baro and has **no localizer or glideslope
receiver**, so such an approach would be a GPS overlay of the procedure, not
the ILS — a crew would be told they flew an ILS while the box ignored the
signal. Both the fix and the facility are real in the navdata (BAKEL
32.776839/−116.844378; IMYF 111.95 with glideslope), so the scenario is
well-posed — but the correct instrument for it is the aircraft's own GFC 700
flying a coupled approach, not ArduPlane. It would also need the MAVLink
mission protocol (absent from `mavlink_min.py` by design), and an approach
envelope distinct from the exercise envelope, since an ILS to minimums
violates both the altitude block and the AGL floor. Autonomous landing
remains "Outside initial release" per the CONOPS.

## 2026-09-17 (late) — first successful SITL attach; ArduPlane departed on contact

X-Plane restarted with the networking corrected. **SITL connected to CAP 487 for
the first time.** Leg 3 still did not fly, but the failure moved from "no
connection" to "connected, and the autopilot did the wrong thing", which is a
different and more useful problem.

### What finally made X-Plane talk to SITL

Three settings had to be right at once, and only the third was discoverable
from the preferences file:

1. **Data Output rows** 20 (LatLonAlt) and 136 (JoystickRaw) ticked in the
   **network** column (`_Binet20`, `_Binet136`).
2. **The destination** on the *Data Output* tab — not the Network tab — set to
   `127.0.0.1` and the port SITL listens on.
3. **`Network → UDP PORTS → "Port we send from (legacy)"` moved off 49001.**
   X-Plane binds its own send-from port, and it was 49001 — precisely the port
   ArduPilot SITL binds to receive. Moving it to 49501 freed 49001.
   **This change requires an X-Plane restart**, which is why several earlier
   attempts tested a configuration that was not yet live.

Confirmed by binding 49001 directly: 122 packets, `DATA*`, rows 20 and 136.

Two dead ends worth recording so nobody repeats them: the
`networking_disclose_*` flags in `Miscellaneous.prf` are disclosure settings,
**not** feature switches; and the `_snd_ip_str_N`/`_snd_pt_str_N` slots in
`X-Plane.prf` get auto-populated with the ports of clients that talk to
X-Plane, so they look like configuration and are not.

### The attach itself

Pre-flight block, first time it has ever been fully populated:

```
ArduPilot heartbeat age    0.07 s   mode 11   ARMED
magnetic -> true offset    +10.5 deg
indicated -> true altitude -81 ft
ArduPilot - X-Plane true   +2 ft     (SITL link sanity, gpi age 0.07 s)
RC roll/pitch/yaw at rest  None us
override_joystick          1.0
```

The MAVLink path works end to end: heartbeat, armed bit, `GLOBAL_POSITION_INT`
agreeing with X-Plane's true altitude to **2 ft** — so SITL is attached to this
aircraft, and `mavlink_min.py` decodes it correctly. The stdlib codec is
validated live.

But **mode 11 is RTL**, and the SITL log shows `Home: -35.363262 149.165237` —
Canberra, ArduPilot's built-in default. On taking the joystick and throttle
override, ArduPlane immediately banked toward a home point on the other side of
the planet: roll **-80 deg**, vertical speed **-4370 fpm**, within seconds.
Tracked as **AI-23**.

The gate did its job and refused: *"Aircraft outside the configured airborne
exercise envelope."* But `gate.acquire()` sat outside the launcher's
try/finally, so `cleanup()` never ran and SITL kept flying the aircraft down
from 4,474 ft to 1,825 ft at 183 KIAS until the process was killed by hand.
Tracked and fixed as **AI-22** — the same class of defect as AI-21: a path
where SITL outlives its supervisor.

### What this changes for the next attempt

* T0 revised: SITL cannot be attached while X-Plane is paused (no Data Output
  while paused), and attaching while running hands it an aircraft it will fly
  somewhere immediately unless its mode is already safe.
* The launcher must **refuse**, not warn, on an unexpected ArduPilot mode, and
  force a known mode before the aircraft can depart (AI-23).
* `cap487.parm` needs `INITIAL_MODE`, and Home must be set from the X-Plane
  position or avoided by choosing a mode that does not use it.

## 2026-09-17 (late) — LEG 3 FLOWN. ArduPlane commanded CAP 487; no capture

**ArduPlane flew the aircraft.** Trace
`~/.cache/capvsar/flight-tests/arduplane_backend_20260917-230653.jsonl`.
ArduPilot `Plane-4.7.1` (`dbe7921`), X-Plane 12.4.3, CAP 487, west of KRNM.

Commanded heading 300 / 4,500 ft from a stable GFC 700 handoff at 4,677 ft,
110 KIAS, wings level.

| Aspect | Result |
|---|---|
| Secure on attach | **LOITER** — AI-23 fix held, no RTL, no departure |
| Gate | **accepted**, lease issued, 33 samples of `executing` |
| ArduPilot mode | **GUIDED** throughout |
| Bank | −22° to −30°, **inside** the gate's 35° — the `WP_LOITER_RAD` fix worked as calculated |
| Airspeed | 97–114 KIAS, inside 90–140 |
| Faults | **none**; ran the full 120 s and ended "flight complete" |
| Detach | **clean**: SITL stopped, both overrides → 0, GFC 700 re-engaged (AP, ALT), `hand_back_mode: LOITER` |
| **Capture** | **NO.** Heading swept 261 → 178 through a full 360° and kept going; altitude fell 4,616 → 2,974 ft. Neither commanded value was tracked. |

So the whole safety chain ran end to end on a live aircraft with no runaway and
no manual intervention — but ArduPlane was **loitering in GUIDED**, not honouring
the guided slew commands. Both were ACKed `ACCEPTED` (`select()` raises
otherwise), so ArduPilot took the commands and did not act on them. Open as
**AI-24**; hand-off brief in `docs/bugs/AI-24_ARDUPLANE_GUIDED_TUNING.md`.

The aircraft finished at 2,974 ft — below the gate's own 3,000 ft floor —
which is worth noting: an uncommanded descent leaves the exercise envelope in
about ninety seconds.

### What had to be fixed to get this far, all in one session

| Problem | Fix |
|---|---|
| X-Plane sent no Data Output to SITL | Rows 20 + 136 network-ticked; destination on the **Data Output** tab; and **`Network → "Port we send from (legacy)"` moved off 49001**, which X-Plane binds itself. **Needs an X-Plane restart.** |
| SITL attached in RTL with Home in Canberra, 80° bank | `secure_on_attach()` (Home here + LOITER before anything else) and `INITIAL_MODE 12` (**AI-23**) |
| A refused `gate.acquire()` left SITL flying the aircraft into the ground | acquire/submit moved inside the try/finally (**AI-22**) |
| LOITER commanded 80° of bank | `WP_LOITER_RAD` 60 m → **800 m**; at 110 KIAS that is ~22°, inside `ROLL_LIMIT_DEG 25` |
| Air start left a glider | reset now does a ground `sim/operation/quick_start`, verifies rpm, and confirms avionics |
| rpm always read 0 | **never verify an engine while the simulator is paused** — it cannot spin up with the clock frozen |

### Reset procedure that works (use this, it took all evening to find)

1. clear a crash: `sim/operation/reset_to_runway` then `sim/operation/fix_all_systems`;
2. **unpause**, then `sim/operation/quick_start`, and verify rpm > 700 with the sim running;
3. `scripts/set_air_start.py --airport KRNM --runway 09 --distance-nm 15 --kias 115 --altitude-ft 4500`;
4. hold `sim/flightmodel/position/{P,Q,R,Prad,Qrad,Rrad}` at zero for ~2.5 s through the placement transient (**V2-8**);
5. engage with `sim/cockpit/autopilot/autopilot_mode = 2`. Mode **1 is flight director and flies nothing**; `g1000n1_ap` is a **toggle**, so pressing it on a live autopilot switches it off.

Fly **west** over the coastal plain: the 3,000–6,000 ft block with a 1,000 ft
AGL floor does not fit the terrain east of Ramona.

### Still open

Leg 3 captured nothing (**AI-24**); cases T1–T8 unflown; gate G undecided. `xplane_plane_cap487.json` joystick axis
indices (pre-check P4) remain unverified. Gate G is **not** decided.

## 2026-09-17 — handoff design review against the Plane-4.7.1 source

Ron stopped the Leg 3 attempt and asked for a review instead: the three
controllers, the ArduPlane design, how they hand off, and the ArduPilot
fixed-wing logic double-checked. Everything below is from the checked-out
source at `~/.cache/capvsar/ardupilot` (`dbe7921`, Plane-4.7.1), file:line
given; nothing is from docs or memory. It supersedes T4, which is now
answered from code, and it changes the ArduPlane backend's release design
(tracker **AI-21**).

### What each controller actually holds in X-Plane

| Controller | Writes | `select()` disengages the incumbent? | `release()` leaves the aircraft… |
|---|---|---|---|
| GFC 700 (`XPlaneAutopilotBackend`) | X-Plane's own AP servos | n/a (it *is* the aircraft's autopilot) | free: `servos_off_any`, trim and throttle as they were |
| Test pilot (`XPlaneDirectBackend`) | `sim/cockpit2/controls/yoke_*`, throttle, trim readback, 10 Hz | yes — `servos_off_any` first | free: yoke 0, throttle 0.45, trim kept |
| ArduPlane (`ArduPlaneBackend` + SITL) | SITL writes `sim/joystick/yoke_*`, `ENGN_thro_use[0]`, `flap_ratio` **every frame in every mode, armed or not**, holding `override_joystick=1` / `override_throttles=1` re-sent every frame (`SIM_XPlane.cpp:632-635`, `:684-688`) | yes — backend sends `servos_off_any` before the first MAVLink write; SITL itself never touches the GFC 700 | **still owned by SITL** in whatever mode it was left; only stopping SITL frees it, and stopping it leaves the override **latched at 1 with the last yoke values** — there is no destructor or exit hook in `SIM_XPlane.*` |

Tonight's F1 stands and is now explained for every pair: a "free" aircraft
departs within seconds; the only handoffs that worked were the ones where the
successor took the aircraft *from a controller still flying it*.

### Handoff matrix

| From → To | Works as built? | What happens in the gap | Required procedure |
|---|---|---|---|
| GFC 700 → test pilot | **yes (Leg 2)** | none — the direct backend's `select()` drops the servos and flies in the same call | leave the AP engaged, start `fly_direct_backend.py` |
| test pilot → GFC 700 | **no** | `release()` neutralises → free aircraft; departed twice tonight | the direct launcher needs a `--park` option: on exit engage HDG+ALT at the current state via the `g1000n1_*` commands, *then* exit |
| GFC 700 → ArduPlane | **no, as built** | SITL boots MANUAL; with no valid RC, `Plane::get_throttle_input` returns 0 (`reverse_thrust.cpp:132-137`) and the failsafe zeroes the stick inputs (`radio.cpp:197-200`); SITL maps that to `ENGN_thro_use=0.0` and yoke trim on every frame from the first DATA packet — **the engine goes to idle the moment SITL attaches**, and the SITL yoke writes fight the AP servos until `select()` runs | the launcher must own the SITL process: start it, wait for heartbeat + `GLOBAL_POSITION_INT` + the `xplane_internal_version` RREF (the first ~1 s decodes gyros with the XP11 convention until that reply lands, `SIM_XPlane.cpp:458-467`, `:591-609`), then `select()` at once so GUIDED's auto-throttle takes over. Window ≈ 2 s of idle. Alternative, to be tested as T0: attach with X-Plane paused — SITL sends nothing until DATA arrives (`:379-386`), but whether paused X-Plane emits DATA rows is not in either codebase |
| ArduPlane → human (D-3) | **unsafe as designed** | `release()` → MANUAL. `ModeManual::update()` passes raw stick to the surfaces with no limits (`mode_manual.cpp:4-15`). With the rig's axes unmapped, an axis reading 0 through `input_min 0.2 / input_max 0.8` gives PWM ≈ 667 and the inverted throttle axis ≈ 2333 (`SIM_XPlane.cpp:497-498`, `AP_RCProtocol_FDM.cpp:39`), which clamp to the channel limits: **full aileron and full throttle**. With no joystick row at all, `rcin[]` is uninitialised (`SIM_Aircraft.h:251`) and RC is never seen: throttle 0, surfaces to trim, unstabilised | release to **LOITER** by default — the only mode of the three that flies itself with no RC (auto-throttle via TECS). Hand to MANUAL or FBWA *only* when the backend measured a valid, centred RC position at engagement (`_rc_rest` not None). FBWA is the right human mode once the stick is proven (wings-level at zero input, `mode_fbwa.cpp:6-16`, limits by `ROLL_LIMIT_DEG`/`PTCH_LIM_*`); MANUAL should never be the default |
| ArduPlane → GFC 700 / test pilot | **no, as built** | SITL keeps writing in any mode; after `kill`, override stays 1 and the yoke is latched | ArduPlane LOITER (parking) → stop SITL → write both overrides to 0 → engage HDG+ALT with the `g1000n1_*` commands — all in one script, the gap is the script's own latency |
| any → pause (fault) | yes | the backend sends `pause_on`; SITL's writes stop within 200 ms of DATA ceasing (`SIM_XPlane.cpp:567-585`) | unchanged. Open item: SITL heartbeats are scheduled on sim time, so a paused X-Plane may also silence the heartbeat and trip `_lost_ardupilot` (which clears the overrides — harmless here, and correct if SITL had died) |

### ArduPlane modes as used by the design

* **GUIDED** — ArduPlane flying. Entry loiters about the current position and adopts the *current* altitude (`mode_guided.cpp:4-27`, `commands.cpp:91`), so `select()` immediately overriding altitude and heading is the right shape. Heading target is **true** (`mode_guided.cpp:52-53`, compared to `ahrs.get_yaw_rad()`), so the backend's live `psi − mag_psi` conversion is correct.
* **LOITER** — ArduPlane parking: auto-throttle, self-navigating, RC-independent. Should be the default release and the mode SITL is left in before it is stopped.
* **FBWA** — human with a verified yoke. Attitude-stabilised, limited, throttle from the stick.
* **MANUAL** — raw passthrough. Only meaningful with a proven RC map; never a default.

### Source checks on the backend's assumptions

| Assumption in the backend | Source | Verdict |
|---|---|---|
| `ARMING_REQUIRE 0` is enough; no arm command needed | `AP_Arming.cpp:306` `is_armed()` returns true when arming not required; the disarmed throttle-zero block (`servos.cpp:892`) therefore does not fire | **correct**. `ARMING_CHECK` no longer exists in 4.7 (`ARMING_SKIPCHK`, `AP_Arming.cpp:201,227`); not used, fine. Preflight should still assert the armed bit in HEARTBEAT `base_mode` |
| `GUIDED_CHANGE_*` accepted only in GUIDED, `MAV_RESULT_FAILED` otherwise | `GCS_MAVLink_Plane.cpp:659-661,680-682,713-715` | correct |
| heading param3 is a rate in deg/s | `GCS_MAVLink_Plane.cpp:745` `MAX(param3, 0.05f)` is a **centripetal acceleration m/s²**, bank limit `atan(a/g)` at `mode_guided.cpp:60`; 0 → 0.05 → ~0.3° bank, i.e. cannot turn | fixed in the review pass (`HEADING_ACCEL_M_S2 = 3.0` ≈ 17° bank). Add a test that it is never sent as 0 |
| `HEADING_TYPE_DEFAULT` clears the hold | `GCS_MAVLink_Plane.cpp:736-738` → `GUIDED_HEADING_NONE`, reverts to loiter navigation | correct |
| altitude `z` metres, frame GLOBAL = AMSL, `param3` m/s, 0 → default | `:701`, `GCS_Common.cpp:7356` (GLOBAL→ABSOLUTE), `:706-708` (0 → 10 m/s) | correct; **`z == 0` or `-1` is DENIED** (`:685`) — add a guard |
| COMMAND_INT is required | `GCS_Common.cpp:5294,5340`: COMMAND_LONG is converted with frame **GLOBAL_RELATIVE_ALT** | correct and necessary — a COMMAND_LONG altitude would be relative to home |
| heartbeat can be requested at 5 Hz | `GCS_Common.cpp:1045`, `:7114-7120` special-cases HEARTBEAT; `:3222-3230` | correct |
| `GLOBAL_POSITION_INT.alt` is AMSL mm | `GCS_Common.cpp:6115-6117`, EKF location ×10 | correct |
| `GUIDED_P/I/D` are real parameters | `Parameters.cpp:1187` `AP_SUBGROUPINFO(guidedHeading, "GUIDED_", …)` | correct (also `GUIDED_FF`, `_IMAX`, `_FLT*`) |
| `cap487.parm` names | all present: `AIRSPEED_CRUISE/MIN/MAX` (m/s), `PTCH_LIM_MAX/MIN_DEG`, `ROLL_LIMIT_DEG`, `TECS_CLMB_MAX`, `TECS_SINK_MAX/MIN`, `THR_FAILSAFE`, `FS_SHORT/LONG_ACTN`, `FS_GCS_ENABL`, `SIM_SPEEDUP` | correct. Keep `FS_GCS_ENABL 0`: the GCS failsafe is independent of `THR_FAILSAFE` (`system.cpp:383-395`) and would RTL on our heartbeat loss |
| `override_joystick` after release (T4) | SITL re-sends the `fixed` overrides every frame while alive; nothing resets them on exit | **answered from source**: clearing is futile while SITL lives and mandatory after it stops. `_lost_ardupilot` is right; the launcher must do the same on normal detach |
| SITL leaves X-Plane's Data Output alone | `deselect_code` (`:323-332`) USELs any row it did not ask for | it does not — any Data Output rows a user had enabled are switched off at attach. None are enabled today (`X-Plane.prf`), so no effect, but record it |

### Changes required before Leg 3 (AI-21)

1. ~~`release()` mode selection: LOITER by default; FBWA only with a valid `_rc_rest`.~~ **Done 2026-09-17.**
2. ~~Launcher owns the SITL process; detach parks, stops SITL, clears the overrides, engages the GFC 700.~~ **Done 2026-09-17** (`services/ai_pilot/sitl_lifecycle.py`, one `cleanup()` on every exit path).
3. ~~Guard `guided_change_altitude` against `z ∈ {0, −1}`; test that heading accel is never 0.~~ **Done 2026-09-17.**
4. ~~Preflight asserts the HEARTBEAT armed bit.~~ **Done 2026-09-17** (launcher refuses with exit 5 when disarmed).
5. `fly_direct_backend.py --park` so test pilot → GFC 700 has no gap (separate item; Codex's lane on the H-cards, so propose, do not edit).
6. Trial case **T0**: does a paused X-Plane emit Data Output? Decides whether SITL can be attached paused.
