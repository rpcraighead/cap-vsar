# Teaching an AI test pilot to land in X-Plane

Working notes for a video about the attended CAP V-SAR AI-pilot landing experiments, updated 2026-10-10 PDT. The subject is the stock X-Plane 12 C172SP G1000 at KMYF runway 28R. These are simulator engineering trials, not evidence that an AI can safely fly a real airplane. The controller flies through a time-limited, bounded simulator bridge; an independent observer scores the recorded flight.

## The story

The original goal was much larger than landing: an AI pilot and test pilot that could taxi, take off, cruise, land, enter a stall, recover, and report what happened. We split the problem. The language model helps choose tasks and interpret results, while a local, deterministic controller handles the continuous flying. The first repeatable flight cycles led to a dedicated KMYF landing trial.

Ron acted as the flight instructor while watching the simulator. His corrections were operational, specific, and often exposed defects that a simple pass/fail score missed:

1. Establish 65 KIAS on final, with 61 KIAS reserved for a later short-field mode. Use 10°, 20°, then 30° flaps as the airplane approaches.
2. Pitch controls airspeed; power controls glidepath. If low and slow, lower the nose **and** add power.
3. Make the flare gradual. Delay its start, avoid the initial balloon, and continue raising the nose in the last two seconds. Touch down about 5–7° nose-up.
4. In a crosswind, use aileron into the wind to hold centerline and rudder to keep the fuselage aligned with the runway. Continue through touchdown. As rollout speed falls, increase aileron input because it loses effectiveness.
5. Start with 12 kt from 45° left, then direct 12 kt crosswinds. Raise the configured direct crosswind to 15 kt to compensate for X-Plane's near-ground wind attenuation.
6. Look at the *usable* runway, not just the simulator's touchdown coordinates. KMYF 28R has a 366 m displaced threshold in the installed airport data. Ron identified a touchdown on that line and asked to move the **unflared 3° glidepath aimpoint** 25 ft farther down the runway. The flare then carries the airplane farther before contact. This is an aimpoint change, not a request to move the flare itself.

The last correction matters because the initial engineering scorer allowed contact anywhere from the physical runway end to 450 m. It could therefore call a landing successful even when contact was at or before the displaced threshold. The revised scorer requires contact at least 25 ft beyond that threshold. Guidance and reset geometry now use that same aimpoint, and the later scored trials below use the corrected geometry.

## What the simulator showed

The earlier 45°-left, configured 12 kt trials passed twice and a calm regression passed. On the later direct 12 kt trials with progressive windward aileron, one left and one right run passed all recorded touchdown and full-stop checks. The left run touched down 1.09 m left of centerline at 5.99° nose-up and stopped 1.16 m left. The right run touched down 0.32 m left at 5.71° nose-up and stopped 0.63 m right. Both used moderate symmetric braking, peaking at 0.32 of full command. These were individual successful runs, not a consistency campaign.

Configured 12 kt winds were approximately 12 kt on final but about 8.3 kt at contact in X-Plane. A configured 15 kt direct-left trial later passed, with about 10.5 kt measured at contact. Its touchdown was 405 m from the physical runway end, at 5.83° nose-up and 2.60 m left of centerline. Direct-right 15 kt runs exposed harder problems: the rudder was initially at its bounded limit yet the nose remained more than 3° off runway heading; later tuning reduced that error, but several contacts landed too near or before the displaced threshold.

After the aimpoint and alignment corrections, a first alternating direct-left/right 15 kt campaign recorded six consecutive scored passes; its seventh attempt was interrupted by the simulator bridge before touchdown and is not a landing failure. A sound-enabled restart had one unscored startup attempt, then a completed right-crosswind landing whose rollout heading missed the 5° limit by 0.045°. The next eight alternating left/right landings all passed the touchdown and full-stop checks. This is promising repeat performance, but a fresh uninterrupted 10/10 gate and the seeded randomized ±90° campaign were not completed. Ron stopped the runs at this point. See [direct-crosswind evidence](evidence/AI_PILOT_DIRECT_CROSSWIND_20261010.md).

Every scored run records the aircraft identity, configured and measured wind, flap stages, threshold speed and height, touchdown position and attitude, sideslip and control commands, flare rebound, rollout alignment, brake symmetry, and complete stop. The bridge pauses X-Plane and releases control after each trial. Failed attempts remain in the trace archive. Raw JSONL traces are under `/home/ron/.cache/capvsar/ai-pilot/`; relevant direct-crosswind runs include trials 44, 45, 51, and 52–58. Earlier results and trace hashes are in [the KMYF landing evidence](evidence/AI_PILOT_KMYF_LANDING_20261010.md).

## Useful visual sequence

- Show the cockpit and runway on final, with 65 KIAS and the 10°/20°/30° flap schedule.
- Overlay two simple arrows: pitch to correct airspeed; power to correct glidepath. For low and slow, show both nose-down and added power.
- Replay an early flare balloon beside a later smooth flare. Show AGL, pitch, vertical speed, and touchdown pitch on screen.
- Use a runway plan view to show wing-low aileron holding centerline while rudder aligns the nose. Keep the control indicators visible through contact and rollout; show aileron increasing as speed falls.
- Compare configured wind to X-Plane's measured near-ground wind. Label the numbers clearly.
- Mark the physical runway end, 366 m displaced threshold, the new aimpoint 25 ft beyond it, and actual touchdown marks. This is the instructor catch that changed the acceptance test.
- Close the landing segment with the honest state: corrected-aimpoint direct 15 kt landings passed on both sides, including eight consecutive scored passes, but one narrow rollout failure and an interrupted run mean the formal consistency gate and randomized ±90° campaign remain open.

Capture note: the last test X-Plane window measured 1280×923 pixels, not 1920×1080 or 16:9. Set the simulator or capture canvas explicitly before making a 1080p video.

The next planned airport is KRNM for taxi and takeoff engineering trials. That work is separate from, and does not imply completion of, the KMYF landing qualification.
