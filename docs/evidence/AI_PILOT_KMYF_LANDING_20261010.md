# KMYF 28R stock-C172 landing engineering trials

2026-10-10 PDT. Branch `feat/ai-pilot-kmyf-landing`. These are attended simulator
engineering trials, not production flight qualification. The pinned stock
C172SP G1000 ACF, installed KMYF 28R runway geometry, fixed loading, and a
temporary expiring landing-mode bridge were used. All runs ended with X-Plane
paused, control overrides released, and both brakes released.

The normal approach aims for 65 KIAS and selects the stock C172 flap detents
10° before 1 NM, 20° by 1 NM, and 30° by 0.5 NM with speed gates. Pitch
controls airspeed; power controls glidepath. A combined 25 ft low / 3 kt slow
entry was flown successfully: the controller lowered the nose while adding
power, then reached the threshold at 63.56 KIAS and 37.2 ft AGL. A separate
61 KIAS short-field mode has not been built or tested.

The flare starts below 17.5 ft AGL. Its initial pitch target now eases in
over 4.5 seconds, while power reduces at a bounded 0.24/s. This removed the
earlier several-foot balloon. A gradual additional nose-up request begins
around 10 ft AGL, roughly the last two seconds, and the independent scorer
requires 5–7° nose-up in the last airborne sample before contact. Main-gear
contact then starts a delayed, symmetric brake ramp capped at 0.32, with
into-wind aileron and runway-heading rudder held through rollout.

For the crosswind trials, the lab configured 12 kt from 250.0° true, 45° left
of the runway's 295.0° true heading. Effective wind measured 12 kt on final
and approximately 8.3–8.4 kt near touchdown because X-Plane attenuated the
surface wind. The controller uses a wing-low slip: cross-track position and
rate drive aileron into the wind; runway heading and yaw rate drive rudder.
The scorer independently checks measured wind, touchdown within 4 m of
centerline, nose within 3° of runway heading, left bank and into-wind aileron
before touchdown, and continued aileron plus heading within 5° during rollout.

| Trial | Result | Pre-touch pitch | Touchdown from threshold / centerline | Max flare rebound | Stop from threshold |
| --- | --- | ---: | ---: | ---: | ---: |
| 26, 12 kt left crosswind | PASS | 5.49° | 427.7 m / 0.93 m right | 0.01 ft | 513.5 m |
| 27, same crosswind repeat | PASS | 5.35° | 439.8 m / 1.46 m right | 0.37 ft | 524.8 m |
| 28, calm regression | PASS | 5.88° | 381.8 m / 0.06 m left | 0.95 ft | 506.6 m |

Both crosswind runs used measured left bank at touchdown (1.15° and 1.29°)
and had pre-touch runway-heading errors of 2.62° and 2.97°. Maximum rollout
heading errors were 2.83° and 3.22°. The bridge's pre-flight-model readback
showed symmetric brake commands peaking at 0.32, and both runs stopped below
2 kt. The second touchdown at 439.8 m is close to the 450 m engineering
limit; wider wind and disturbance margins remain unproven. The calm regression
also passed on the final crosswind-capable controller.

Development failures were retained. Earlier calm runs used a late flare and
met the pitch target, but ballooned about 3.4 ft because approach power
remained high while pitch rose. The eased initial transition reduced rebound
to below 1 ft in the subsequent calm and low/slow runs. Crosswind trial 22
touched down 4.47 m right of centerline and failed the 4 m criterion. Trial
24 touched down 0.71 m right but failed late rollout heading after low-speed
sideslip feedback reversed rudder. Trial 25 missed the 3° touchdown alignment
criterion by about 0.015°. Trials 19, 20, and 23 were startup/weather-readiness
attempts and did not complete scored landings. All are preserved as raw traces.

The [machine-readable evidence](ai_pilot_kmyf_landing_20261010.json) gives
trace paths, SHA-256 hashes, aircraft/scenery identities and independently
replayed outcomes. Raw JSONL traces are under
`/home/ron/.cache/capvsar/ai-pilot/`. Focused controller/bridge tests and the
full AI-pilot suite passed: 464 tests, 22 expected failures, 60 subtests.

This work does not enable production live control or qualify the custom C182,
short-field landing, gusts, stronger crosswinds, manual-yoke takeover, taxi,
takeoff, or stall recovery. The landing bridge remains an attended,
time-limited laboratory mode pinned to the stock C172. After the trials,
X-Plane was stopped, temporary plugin files and socket were removed, and the
original preferences, stock C172 preferences and scenery configuration were
restored byte-for-byte. The simulator backup is at
`/home/ron/X-Plane 12/Output/capvsar-backups/ai-pilot-kmyf-landing-20261010/`.
