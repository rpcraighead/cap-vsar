# Website handoff (2026-10-19)

Site source: `website-next/site/` (static HTML/CSS/JS). Plans: `website-next/plan/`. Build notes: `website-next/dev/BUILD_REPORT.md`,
`website-next/dev/HOSTING_AND_PLANNER_NOTES.md`. Checks: `website-next/dev/qa/*.cjs` (Playwright + system Chrome; see their headers).

## Done today
- Home hero reel: the `base-radio-link` slide (4th playing slide) was replaced by `web-panels`, a 24.5 s loop through ten web panels
  (Setup, Ready Room, Flight Planner, Exercise Console, AI Pilot deck, maneuver deck, Mission Base, Base Radio, Mission Base headset radio,
  Debrief). Recorder: `dev/qa/record-web-panels.cjs`. `hero-panel` and `c182-chase` slides unchanged; `base-radio-link` still on `comms.html`.
- New pages `hosting.html` (architecture diagram, what runs where, per-seat needs, "can the workstation run it all", Wi-Fi) and
  `flight-planner.html` (origin, what it does now, search-pattern dialog, W&B). Linked from every page's header/footer nav and SITEMAP.md.
- Checks: t39 605 pass, t43 36 pass, t45 83 pass.

## Open items
- `dev/qa/t37-check.cjs` fails one assertion: its label regex rejects the Home chart label "Mission Base · Ready Room · a base-staff seat"
  because of the word "seat". The rule is stale, not the page; update the regex.
- Exercise guide section 6.2 says "Push to V-SAR" sends the pattern to the Mission Base map. The planner code sends only the scenario
  (alert centre, 5 NM radius, offset beacon) and a broadcast. Fix the guide (docs/guide sources), not the site.
- Planner threw "Cannot read properties of null (reading 'style')" once when the SAR dialog was opened during recording; cause not chased.
- Not verified: Safari/MP4 playback; everything running at once with a room of devices on Wi-Fi; real Wi-Fi-drop reconnect test.
- Hosting page claims (frame times, idle load, planner push) should get rows in `plan/CLAIMS_AND_RISKS.md` (evidence in HOSTING_AND_PLANNER_NOTES.md).
- Hero clips still missing on disk (slides skipped): `c182-approach-cockpit`, `pattern-turn-map`, `df-needle-homing`.
- Board and flight-planner guide were deliberately NOT recorded (real dispatch queue / LAN address on screen).
- Separate from the website: the C182T prop-from-cockpit display issue is still open (see the uncommitted prop tests and
  `scripts/convert_flightgear_c182.py` WIP in this worktree, which is not part of the website work).

## Prompt to continue
> Continue the CAP-VSAR website work. Read `website-next/dev/HANDOFF.md` first, then `website-next/plan/VIDEO_PLAN.md` and
> `website-next/plan/CLAIMS_AND_RISKS.md`. Start with the open items in the handoff: fix the stale t37 label regex, add the
> CLAIMS_AND_RISKS rows for the hosting page, and re-run t37/t39/t43/t45 (serve `website-next/site` with
> `python3 -m http.server 8765 --bind 127.0.0.1`; t45 uses 8791; `NODE_PATH=/tmp/t36-render/node_modules` or reinstall Playwright).
> Then ask me what to do next. Do not touch the C182T converter/builder or the other uncommitted aircraft work.
