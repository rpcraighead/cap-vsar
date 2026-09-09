HOW WE MODELED A DIRECTION FINDER FOR CIVIL AIR PATROL TRAINING
Terrain, wing shadowing, and knowing where the beacon really is

If you've ever ridden along on a real CAP search and rescue sortie, you know
the Becker SAR-DF 517 doesn't just hand you a bearing and let you fly home. It
lies to you a little, all the time, in ways that are physically real: a ridge
between you and the beacon, the wrong wing down in a turn, a signal that only
exists for 440 milliseconds every 50 seconds. Training a Mission Observer to
read through that noise is most of the job. So when I set out to build a
Becker SAR-DF 517 and RHOTHETA RT-600 for our CAP V-SAR training simulator, the
part that mattered wasn't the faceplate — it was making the receiver wrong in
the same ways the real one is wrong.

This post is about the two effects that made the biggest difference:
terrain masking and wing shadowing (the "wing null" CAP crews are taught to
fly), plus where the beacon a student is chasing actually comes from and how
the result ends up on the instrument.

WHY THE ENGINE HAD TO LIVE INSIDE X-PLANE

Air Manager, which drives the instrument faceplates, is Lua running in its own
sandbox. It has no access to real terrain and no network stack. So the
propagation model doesn't live there — it lives in an XPPython3 plugin
(`PI_capvsar_df.py`) running inside X-Plane itself, publishing a small set of
`cap/df/*` datarefs that the faceplates just read. That's the only place a
ridge between the aircraft and the beacon can actually be seen, because it's
the only place the scenery is loaded.

TERRAIN: ASKING THE SIM WHAT'S IN THE WAY

The line-of-sight check is almost embarrassingly literal. Every update, the
plugin samples 24 points along the straight path between the aircraft and the
beacon, probes X-Plane's actual terrain mesh at each one with
`XPLMProbeTerrainXYZ`, and compares the ground elevation to where a straight
ray between the two points would be at that fraction of the distance:

    ground = self.terrain_ft(lat, lon)
    ray = b_ft + (ac_ft - b_ft) * fr
    if ground > ray + 50.0:      # 50 ft margin for probe noise
        return True              # blocked

If any sample point's terrain pokes up more than 50 feet above the straight
ray (the margin is just probe noise), the signal is masked and `cap/df/blocked`
goes true. No digital elevation model, no precomputed viewshed — it's asking
the flight sim's own mesh, live, which means the exact ridge a student is
flying near is the one that can actually shadow the beacon. Fly the search
area on the other side of that ridge and the signal comes back, exactly like
it would in the airplane.

WING SHADOWING: TEACHING THE "WING NULL" TECHNIQUE

The more interesting effect is airframe shadowing — what CAP's Mission
Inflight Guide describes as flying a bank until the signal nulls, then reading
direction from which wing is down. It's a real DF technique, and it only works
if your simulated receiver actually goes quiet when the real one would.

The geometry lives in `airframe_shadow_loss_db()`. Each tick it takes the
aircraft's roll and pitch (`phi`/`theta` off the sim) and rotates the
aircraft-to-beacon ray out of a heading-level frame into the aircraft's own
body coordinates — forward, right, and up relative to the airframe, not the
ground:

    forward_b = forward_h * cos(pitch) + up_h * sin(pitch)
    right_b   = right_h * cos(roll) - up_after_pitch * sin(roll)
    up_b      = right_h * sin(roll) + up_after_pitch * cos(roll)

From there it projects that ray onto a simplified wing/fuselage silhouette —
a rectangle for the wing, a narrower rectangle for the fuselage, both with
softened (`smoothstep`) edges so a bank produces an audible fade instead of a
binary switch. A belly-mounted antenna profile nulls when the ray has to travel
*upward* through that silhouette to reach the antenna; a top-mounted profile
reverses the sense. That's the whole trick behind "lower the near wing, the
beacon is under it" versus "raise the far wing" depending on where the antenna
actually lives on the airframe — both installations fall out of the same
function, with no special-cased turn direction.

Two details matter more than the geometry itself:

- **It's applied before signal saturation, not after.** Terrain loss and
  airframe loss both eat into the raw field strength before it's clamped, so a
  strong, close beacon can still partially punch through shielding that would
  fully null a weak one — which is also how real receivers behave.
- **The null closes the receiver, not just the display.** `cap/df/rx_open` is
  instantaneous and ungated by TIMEHOLD; both instruments' audio is driven
  directly from it, so a held bearing on the needle never keeps a dead signal
  audible. The student hears the null the instant it happens, separately from
  whether the bearing display is still showing the last good reading.

Neither faceplate shows an artificial "WING NULL" warning. The Becker and
RT-600 share one Lua binding that subscribes to `airframe_shadowed` and
`airframe_attenuation_db` purely for the instructor's debug view — what the
student sees is the same signal bar, squelch behavior, and bearing spread
dropping out that they'd get from a real set losing the signal. The training
value is in the receiver being honestly wrong, not in a hint.

WHERE THE BEACON ACTUALLY COMES FROM

None of this means anything if the beacon location is fake in an obvious way,
so it doesn't come from a random-in-a-circle generator. The instructor console
has a scenario editor with two ways to place it: type a lat/lon directly, or
click a point on the sectional and drag an amber pin into place. That amber
pin is deliberately a different color from the red "truth" marker — the truth
marker only appears on the instructor's map after the scenario is revealed,
so during the exercise the beacon location exists only in the scenario record
and in the physics the DF engine is quietly running against. Students are
flying against a real, instructor-placed point on the chart, seen only through
what the propagation model lets the receiver hear — the same information gap
a real search crew works with.

WHAT ENDS UP ON THE INSTRUMENT

All of the above collapses down to a handful of read-only datarefs —
`bearing_rel`, `signal`, `spread`, `blocked`, `airframe_shadowed`, `rx_open` —
that the Becker 517 and RT-600 faceplates both subscribe to through one shared
Lua library. The compass rose was rebuilt to match the manual's own way of
showing confidence: a solid marker at the averaged bearing, hollow markers at
each un-averaged extreme, so the gap between them *is* the trust signal, read
at a glance, exactly like Fig 3-3 in the Becker manual. Everything upstream of
that — the terrain probe, the body-coordinate rotation, the beacon an
instructor placed by hand — exists so that one needle and one signal bar have
something honest to show.

It's validated against 55 engine test cases offline (opposite banks, top and
belly installations, combined terrain-plus-airframe masking, strong-signal
penetration, live-versus-held bearing state) before it ever touches the
instruments, but the real test is flying it: bank away from a beacon under a
belly-mounted 517, listen to it die exactly when the geometry says it should,
and bank back.
