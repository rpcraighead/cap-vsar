# T36 build report

> Moved on 2026-10-18 (T11) from `site/BUILD_REPORT.md` to `website-next/dev/` so it is not deployed with the web root. The QA scripts now live in `dev/qa/` and write their captures to `dev/screenshots/`; paths below that say `screenshots/` or `qa/` refer to those folders.

## Delivered

- `index.html`: complete Home page with copy-led sections, original animated map art, six mission tiles, an 11-seat responsive ICS chart, six approved screenshots with CAP-context alt text and captions, the training progression illustration and four learning cards, straight-talk callout, CTAs and footer.
- `comms.html`, `df.html`, `foreflight.html`, `caltopo.html`, `ai-pilot.html`, `airplane.html`, `how-its-built.html`: linked placeholder pages with the shared header/footer and “Coming next.” `coms.html` is also present as a compatibility alias.
- `assets/css/style.css`, `assets/js/main.js`: offline styles and menu, pause, and lightbox behavior. The CSS starts with the STYLE.md tokens; fonts fall back to local system faces.
- `assets/brand/logo.svg`, `assets/brand/favicon.png`: direction A Bearing logo and icon export.
- `assets/img/`: six current captures named `comms-base-dual.webp`, `mission-base-lops.webp`, `exercise-console.webp`, `exercise-ready-room.webp`, `df-becker-517.webp`, and `debrief-scoring.webp`. All are WebP and at most 1600 px wide.
- `screenshots/home-desktop-full.png`, `screenshots/home-mobile-full.png`.

## Verification

- Ran `nice -n 10 node /tmp/t36-render/capture.cjs` with Playwright using system Google Chrome 155.0.8059.79. The script opened the site over HTTP and `file://`, checked page errors, local links, image loads, viewport overflow, headings, reduced motion, menu and lightbox behavior, then saved full-page captures.
- `file://`: document and all image assets loaded. HTTP: started `python3 -m http.server 8765 --bind 127.0.0.1`; the Home page and its local CSS, JS, logo, favicon and screenshots returned 200; stopped the server with Ctrl-C.
- Desktop viewport 1440×900; full-page image 1440×9194. Mobile viewport 390×844; full-page image 390×11412. Viewed both captures after the final CSS changes. Document width matched each viewport; no horizontal overflow, unloaded images or console/page errors.
- Accessibility sanity check: one H1, headings in sequence, main/header/nav/footer landmarks, alt attributes on every `<img>` (empty alt only for decorative lightbox placeholder), visible focus ring, keyboard-operable `details` nodes and 44px controls. Tested menu open/Escape close and lightbox open/Escape close/focus return. Reduced-motion emulation showed the converged bearings and ellipse with beacon animation disabled.
- Contrast ratios recalculated from the shipped colors: text on dark 15.73:1; muted text on dark 7.64:1; cyan on dark 9.15:1; orange on dark 6.53:1; ink on paper 14.37:1; muted ink on paper 6.32:1; green on paper 4.53:1; ink on orange CTA 5.75:1. Small node labels and learning-card eyebrows use ink on paper panels to keep their contrast above 4.5:1.
- The required blocked-address, hostname, callsign-prefix, email-domain and unresolved-marker source scan returned no matches. The only URL-shaped text in HTML/CSS/JS is the SVG namespace declaration; there are no remote script, stylesheet, font, image or data requests and no outbound links.

## Claims and release notes

No Home factual claim marked for verification or needing evidence is shown as fact. Home §7’s contact address and public GitHub URL remain unverified, so the contact and source actions are omitted. No source URL or real email is included. Other needs-evidence items in the plan (ForeFlight feed, owner credentials and F-4 carrier operations) do not appear on Home; linked subpages remain placeholders. The Home caption shortens the Becker model label to comply with the explicit forbidden-string scan.

The official Civil Air Patrol disclaimer from STYLE.md and the exact trademark acknowledgement are in every page footer. The Bearing mark is used via one logo asset path; no official CAP insignia appears.

## Worth a second look

The linked subpages are intentionally placeholders, and the exercise guide, contact, and sanitized source links await verified destinations. The org chart is dense on phones, though it stacks into branch lists, and the map illustration is deliberately schematic; a visual refinement pass could improve its terrain and route detail.

# T37 — Home visual refinement

## Changes

- Redrew the original inline hero SVG in `index.html`: layered terrain tints, paired ridge contours, grid ticks, roads, four beacon-centred range rings, faint expanding-square track, two aircraft and two prominent crossing cyan bearings. Subtle dashed bearing sweeps animate around the aircraft; the solid bearings remain visible from the first frame. The orange ELT has a radial glow, slow 50-second brightening, and a 12-second expanding ripple. All movement uses CSS transform/opacity; no libraries or remote assets. Reduced motion shows fully drawn bearings and a glowing still beacon. Pause/Resume controls all map animation. The exact simulated-distress disclaimer remains visible.
- Removed visible seat identifiers and software paths from all 11 cards. Internal identifiers remain only in `data-seat`. Screens now use plain names: Mission Base, Flight Planner, Ready Room, Base Radio, Exercise Console, Debrief, X-Plane simulator, Air Manager panels + G1000, and Second screen or tablet. Role descriptions and the approved Home prose remain unchanged.
- Rebuilt branches as native `details` disclosures: open on desktop, compact and closed initially at ≤900px, with 56px branch targets and ≥44px duty targets. Duties remain keyboard-operable, and all branches start open without JavaScript. Desktop Air Operations uses a wider, two-column crew group to avoid the former long, sparse chart.
- Increased the shared header wordmark from 138px to 180px and header height to 72px; adjusted shared HTML dimensions. Preserved screenshot proportions and aligned complete images at the top of consistent frames. Fixed the existing lightbox's forward-Tab focus escape. Added the missing `stations` anchor to the existing How It's Built placeholder; its content remains Coming next.
- Files: `index.html`, `assets/css/style.css`, `assets/js/main.js`; shared logo dimensions in `comms.html`, `coms.html`, `df.html`, `foreflight.html`, `caltopo.html`, `ai-pilot.html`, `airplane.html`, `how-its-built.html`; `qa/t37-check.cjs`; this report and the captures below. No plan, brand source, service, old website or simulator files were edited.

## Verification

- Started `nice -n 10 python3 -m http.server 8765 --bind 127.0.0.1` in `website-next/site/`, then ran `NODE_PATH=/tmp/t36-render/node_modules nice -n 10 node website-next/site/qa/t37-check.cjs` from the repository root using system Google Chrome and the existing Playwright installation. Final result: **112 checks passed**. Stopped the HTTP server after verification.
- HTTP Home and every linked placeholder loaded with 200 responses; local images, CSS, JS and favicon loaded. No browser console/page errors, failed HTTP resources or external requests. `file://` loaded local assets and branch behavior correctly without overflow. No-JavaScript native branch/duty disclosures also worked.
- Checked 320, 390, 600, 768, 900, 1024, 1200 and 1440px widths: document width matched viewport width. Phone screenshot strip scrolls inside its own row. Desktop/mobile have one H1, ordered headings, landmarks, image alt attributes, all 11 cards, no technical path labels, and ≥44px chart controls. Enter opens a branch, Space opens a duty, and keyboard focus has a visible ring. Menu Escape closes and returns focus. Lightbox opens, retains Tab focus, closes on Escape, and returns focus. Pause/Resume and reduced-motion still state passed.
- Contrast recalculated from shipped colors: text/dark **15.73:1**, muted/dark **7.64:1**, cyan/dark **9.15:1**, orange/dark **6.53:1**, ink/paper **14.37:1**, muted/paper **6.32:1**, green/paper **4.53:1**, ink/orange CTA **5.75:1**, map labels/dark halo **14.45:1**, ELT label/halo **12.19:1**, screen names/card **6.83:1**. The map's opaque dark text halo keeps terrain from changing label contrast.
- Published HTML/CSS/JS/logo scan passed for blocked address, hostname, callsign-prefix, email-domain and unresolved-marker strings. The SVG namespace is the sole URL-shaped source reference; no external resources or outbound links. Civil Air Patrol remains descriptive copy/disclaimer text, never a substituted logo or site brand. Original Bearing mark and schematic map only; no CAP insignia or chart tile imagery was introduced.
- Rechecked plan claims: unverified contact address, public source URL and guide destination remain omitted; no ForeFlight position-feed, owner credentials, F-4 carrier, current test-total or public-GitHub-status claim is presented as fact. Official disclaimer and trademark acknowledgement remain in every footer.
- Regenerated full-page captures at desktop **1440×900** (image **1440×7175**) and mobile **390×844** (image **390×8511**). Viewed the before captures, final full-page overviews, hero, chart, screenshot strip, expanded mobile chart and reduced-motion still. Used `nice -n 10 python3 -I` with Pillow to crop the actual full-page PNGs, avoiding sticky-header artifacts in element captures. Iterated on map brightness/label halos, chart proportions, collapsed branch borders and screenshot fitting.

## Screenshots and evidence

- `screenshots/home-desktop-full.png`
- `screenshots/home-mobile-full.png`
- `screenshots/t37-desktop-hero.png`, `t37-desktop-org.png`, `t37-desktop-strip.png`, `t37-desktop-overview.png`
- `screenshots/t37-mobile-hero.png`, `t37-mobile-org.png`, `t37-mobile-org-expanded.png`, `t37-mobile-strip.png`, `t37-mobile-overview.png`
- `screenshots/t37-reduced-motion-hero.png`
- `screenshots/t37-qa.json` — assertions, layout measurements, screen names and contrast figures.

## Assumptions and remaining weaknesses

The map is intentionally schematic, with fixed aircraft/report positions and moving sweep guides so the crossing bearings are clear throughout the loop. It is original art, not a geographic or navigation product. Compact branches default closed at tablet/phone widths; without scripts they remain expanded for access. Approved descriptive copy was retained instead of shortened.

The approved hero copy plus the separate map makes the mobile hero taller than one screen. Screenshot UI details still need the lightbox for comfortable reading. Desktop branch heights are naturally uneven, although the wider crew group substantially reduces blank space. The linked detail pages, including the hardware destination, remain placeholders; contact, guide and source links still await verified destinations. Automated checks are accessibility sanity checks, not a screen-reader audit. No merges, commits, pushes, rebases or branch switches were performed.

# T39 — the seven detail pages

## Delivered

- `comms.html`: the base station hero figure, the aircraft radios (TDFM-136B and GMA 1347 replicas, the Mission Observer station composite), the Base Radio page (tactical and airband faces, the current page), ground teams, how reach is simulated with the original signal-paths diagram (base antenna at Gillespie Field, repeater on the Julian VORTAC, a direct path, a repeater path, a low aircraft blocked by the ridge, the radio horizon), the voice-net channel table, and the honest-limits callout. Adds the plain-language note that the console's settings are "Radio reach" and "Radio conditions" (Normal to Very poor) and that the Base Radio page shows Clear / Some static / Weak and choppy / Barely readable with the path, and that the repeater plays no part in DF.
- `coms.html`: kept as an alias. It now carries a zero-second `meta refresh` to `comms.html`, a canonical link and a visible "Go to Comms" button, with the shared header and footer.
- `df.html`: both heads (station captures and face previews), the comparison table, the propagation cutaway diagram (ray, sample ticks, ridge above the ray, wing-null fan, the earth's curve, legend chips), the techniques-and-traps list with the three-panel wing null / cone of confusion / reflection diagram (with a base-map inset showing the bad cut), the Exercise Console and Debrief captures, and the "what the DF does not see" callout linking to the reach section on Comms.
- `foreflight.html`: a short planned / being-proven page. No setup steps, no feed claim, the planner caution verbatim.
- `caltopo.html`: the roadmap page, marked "plan only" in the first line and in a chip, with the truth-boundary paragraph and the status.
- `ai-pilot.html`: the ESCON pattern capture, the three layers verbatim with the original three-layer diagram ("no model in the control loop" as a bold line between judgement and the controller, the independent observer beside the controller, the simulator beside the autopilot layer), the flight-instructor section without a name, the operational concepts, the proven / flown / not yet table with status chips, and the F-4 section rendered as a "demonstration in progress" note that claims nothing.
- `airplane.html`: the recipe verbatim with the original build-recipe diagram (cockpit and systems, exterior, the numbers card, the build script, CAP 487 as the result; outline drawings only), the G1000 additions, the measured performance table with a small at-a-glance table, and the licensing callout.
- `how-its-built.html`: the three-models section with the original workflow diagram (commander, AgentDeck, three worker lanes with review and fix-with-a-failing-test arrows, the shared changelog and knowledge base bar, the full-suite gate, the sanitised public copy, and the flown-in-the-sim loop), dev/QA/test, working to their strengths, and the `#stations` hardware table that Home already links to.
- Every page: the shared header with the current page marked in the main and footer navigation, the V-SAREX pill pointing at Home's org chart, the exact footer disclaimers, and a "Next" link at the bottom following the navigation order (DF offers Comms and AI Pilot as the copy deck says).
- `assets/css/style.css`: a T39 block for the detail pages: title block, reading column, single and paired figures, the 240 px detail figure, dark diagram frames (also inside paper sections), scrolling spec tables, status chips (proven / flown / planned / not yet), the live and ok callout tones, the channel list, the next-page bar, and the visually hidden heading used for figure-only sections.
- `assets/img/`: ten new WebP captures, all at most 1600 px wide: `comms-base-apx.webp`, `comms-base-icom.webp`, `comms-mission-radio.webp`, `comms-tdfm-136b.webp`, `comms-gma-1347-com-row.webp` (the COM / MIC block cropped from the audio-panel preview), `mo-station-layout.webp` (the generated composite, where the stock display is a blank placeholder), `df-becker-517-face.webp`, `df-rt600-face.webp`, `df-rt600.webp`, `planner-escon-square.webp`. The Home captures are reused where the plan says so.
- `qa/t39-check.cjs`: the browser gate for the detail pages (overflow, errors, external requests, headings, alt text, current-page marks, diagram title/desc, next links, 44 px targets, lightbox and menu behaviour, focus ring, the alias redirect, `file://` loads, reduced motion, contrast of the new colour pairs, full-page captures).

## Copy decisions

- Copy is from COPY.md verbatim, with these exceptions: the `[VERIFY]` markers are not rendered; "Becker SAR-DF 517" is written "Becker 517" because the required forbidden-string scan rejects `SAR-` (the Home build made the same change); the DF page prefixes the callsign sentence with "In the sample exercise," as the claims register asks; the ForeFlight lede and status are rewritten as planned / being proven per the owner's decision; the F-4 section is a no-claim note; the Comms reach section adds the three new facts the task allows; the Home caption for the dual station is reused on Comms; captions the deck does not supply (the tactical face, the airband face, Base Radio today, the station composite, the two face previews, the ESCON square) are one-line factual descriptions of what is shown.
- Omitted as the owner decided: the contact address and any mailto, the public source link and any repository URL, the owner's name, the sign-in and setup captures, the ForeFlight setup steps, the "Read the engineering notes" and "Watch the landing" buttons, the test totals and the "is the GitHub copy live" statement. No LAN address, hostname, badge code, email or external resource appears.

## Verification

- After the owner's "sim finished": started `nice -n 10 python3 -m http.server 8765 --bind 127.0.0.1` in `website-next/site/`, ran `NODE_PATH=/tmp/t36-render/node_modules nice -n 10 node qa/t39-check.cjs` (system Google Chrome via the existing Playwright install), and stopped the server by port owner afterwards (port confirmed free). Final result: **531 checks passed, 0 failed** (`screenshots/t39-qa.json`).
- Per page at desktop 1440×900 and mobile 390×844: HTTP 200; document width equal to the viewport with no element past the right edge outside a scroll container; one H1, header/nav/main/footer landmarks, alt on every image, every image decoded, headings in order; the current page marked twice (main and footer nav); every diagram with `role="img"`, `title` and `desc`; a next-page link; no button under 44 px; nothing animating inside `main`; no console or page errors; no request leaving the local origin; no failed response; every local link, fragment and target resolving; lightbox opening on the first figure and closing on Escape with focus returned; the phone menu opening and closing on Escape; a visible focus ring on the first focused link.
- `coms.html` redirects to `comms.html`. `file://` loads of `comms.html` and `ai-pilot.html` render the stylesheet and every image at full width. Reduced-motion emulation on `df.html`: no animations.
- Contrast from the shipped colours: text/dark 15.73:1, muted/dark 7.64:1, muted on card 7.1:1, cyan/dark 9.15:1, cyan-soft/dark 12.26:1, orange-soft/dark 8:1, green/dark 8.44:1, ink/paper 14.37:1, ink-muted/paper 6.32:1, green-deep/paper 4.53:1, the paper status chips 5.46:1 and 6.01:1, diagram notes on the dark frame 7.64:1, ink on orange CTA 5.75:1. Diagram captions use literal light colours so they stay readable inside paper sections.
- Source scan on all nine pages: no `192.168.`, `ms01`, `SAR-`, `INSTR-`, `UDF-`, `@cap.gov`, `[VERIFY`, `mailto:`, repository or tunnel names; the SVG namespace is the only URL-shaped string. Markup balanced; the footer disclaimer, the trademark line and "Not for operational use" verbatim on every page; the copy deck sentences spot-checked verbatim.
- Viewed every capture as banded contact sheets (Pillow, `nice -n 10 python3 -I`), then the six diagrams at native resolution and three phone-width diagram element captures. Fixes made from viewing: label collisions in the signal-paths, propagation, traps, three-layer, recipe and workflow diagrams; the recipe card's number lines; the alias page's doubled closing tags; caption colour inside paper sections; and on phones the diagrams now scroll sideways at a 900 px minimum width (caption says so) instead of shrinking to unreadable text. The font bumps that pushed labels out of their boxes were removed.

## Screenshots

`screenshots/<page>-desktop-full.png` and `screenshots/<page>-mobile-full.png` for `comms`, `df`, `foreflight`, `caltopo`, `ai-pilot`, `airplane` and `how-its-built` (desktop pages 2,020–9,064 px tall; mobile 2,436–8,972 px), plus `screenshots/t39-qa.json`.

## Still unproven, and where it is handled

- ForeFlight position feed (claim 16): the page says planned / being proven and carries no steps.
- F-4 carrier operations (claim 22): the AI Pilot page's section claims nothing until a trace or recording is on file.
- Owner's credentials (claim 20): "a flight instructor and squadron commander" without a name, on How It's Built and AI Pilot.
- Contact address, public source URL and whether the GitHub copy is live (claims 29, Home §7): omitted on every page; the How It's Built sentence that a script builds the public copy is the sanitizer's purpose, not a statement that the copy is live.
- Test totals (claim 34): not quoted.
- The AI-pilot trace plot the asset plan suggested is not possible from the repository: the evidence files hold hashes and summaries, not traces.

## Worth a second look

The DF page writes "Becker 517" where the deck says "Becker SAR-DF 517", for the forbidden-string scan. Captions the deck did not supply were written by the builder as one-line descriptions. On phones the six diagrams scroll sideways; the hint is in the caption. The exercise guide link in the footer is still the "when published" placeholder from the Home build. No commits were made for the website files.

# T41 — ForeFlight as a native feature; the F-4 carrier landings from the evidence; AgentDeck figures

## Changes

- `foreflight.html`: rewritten as a real page. What it is (X-Plane's own output to mapping apps, ForeFlight named by X-Plane's manual), why it matters (the deck's consistency paragraph, verbatim, plus the Mission Observer's and Mission Pilot's use), how it fits the exercise (simulator supplies position and attitude; crew flies the plan; base sees the same airplane; crews on the squadron's private link take part from wherever they are on it), and a setup section limited to product-level facts from the vendors' documents: X-Plane Settings → Network, the mobile-apps section with "every device on the network" or "a single device by its address", fixed ports; ForeFlight Devices → X-Plane → enable; X-Plane expects the tablet on the same local network and ForeFlight documents plain UDP on its published port with a note that broadcast does not suit every network or firewall; a tunnel is not a local network, so the single-device option is the one to expect on the private link, to be confirmed on the link. No address, port number or peer of ours. A footer line acknowledges ForeFlight as its owner's product with no affiliation or endorsement. The "planned" chip and status section are gone; no other page had called it planned.
- `ai-pilot.html`: the F-4 section is now "Arrested carrier landings, Case I", written from the sibling `f4-phantom` project's README and results tables (read-only): a separate F-4 test programme on the same ideas flies the unchanged Laminar F-4 Phantom II through a full Case I arrival to an arrested landing; headline "more than two approaches in three" with 12 arrested landings in 15 completed approaches on the final three control-law versions as the supporting figure; 3 in 5 on the stock hook with the hook-angle explanation; "not a CAP mission; proof the method transfers". The callout beside it carries the required caveats in plain words: simulator characterisation, not a Navy qualification or a real-aircraft procedure; set-up position about three miles behind the ship, not a catapult launch; a private test ship at a steady speed in calm air; arrestment recognised from the aircraft slowing to a stop on deck because the simulator exposes no wire signal; every attempt recorded with no dropped frames and a safe hand-back. The status table gained the row "flown, scored from recorded traces". The page does not say the CAP-VSAR C172/C182 pilot flew the carrier, and quotes neither 9 of 10 nor 5 of 5 as a headline. No local path appears in visible text.
- `how-its-built.html`: a new "At the desk" section with two AgentDeck figures and plain captions: `assets/img/how-its-built-agentdeck-workers.webp` (the three-worker view, 1600×668) and `assets/img/how-its-built-agentdeck-board.webp` (778×592, the dashboard's Workers list and Tasks list only). A footer line names AgentDeck as the programme's own coordination tool and the assistant products as their owners'.
- `../plan/CLAIMS_AND_RISKS.md`: claim 16 marked OK as a native X-Plane feature with the vendor documents as the basis; claim 22 rewritten to point at the sibling project's evidence (`README.md`, `runs/upwind-tuning-2026-10-12.md` results sections, per-attempt `runs/*.json`, `project.json`, commits through `e75d7dd`), the figures quoted, the caveats, and what would move it to proven; the decisions list updated.
- Builder: a per-page footer notice placed after the shared trademark line; `assets/css/style.css`: `.figure-board` width.

## Screenshot review (the two AgentDeck captures)

- Three-worker view (`Screenshot From 2026-10-17 20-03-27.png`, 2493×1041): viewed in full. Tilde paths, model names, task text and usage meters are publishable. Four lines in the Codex pane printed full home-directory paths of cache files, and one line in the Antigravity pane printed a full home-directory path in a command; those regions were Gaussian-blurred to unreadability (checked by viewing the blurred image at full size). No user names elsewhere, no email addresses, no credentials, no prices.
- Dashboard (`Screenshot From 2026-10-17 20-02-40.png`, 1078×891): the Orchestrator transcript pane (left) and the Plans block (subscription plans and prices) were cropped out entirely; the published image is the Workers list stacked above the Tasks list, with the partially cut last task row dropped. Nothing else from that folder was used.

## Verification

- Vendor documents read: X-Plane 12 desktop manual, "Using X-Plane with Mobile Apps" (https://www.x-plane.com/manuals/desktop/): ForeFlight named among the apps; the device "running on the same local network as the computer running X-Plane"; set up in the Network tab of Settings; a choice between a single device by address and all devices; fixed port numbers. ForeFlight developer page (https://www.foreflight.com/support/network-gps/): simulators send GPS packets on UDP port 49002, GPS once per second, attitude at 4–10 Hz; broadcast "will be seen by all iPads on the network" but "is not appropriate for all simulator setups or network/firewall configurations". ForeFlight's help-centre article on connecting X-Plane (https://support.foreflight.com/hc/en-us/articles/204115525) and the UDP protocol article (https://support.foreflight.com/hc/en-us/articles/204115005) are referenced but their bodies could not be read directly (the help centre serves a bot challenge to automated fetches); the page states only what the readable documents support. No vendor document addresses tunnels or VPNs; the page states the principle and tells crews to confirm on their own link.
- F-4 evidence read (read-only, nothing modified): `~/Documents/Codex/f4-phantom/README.md` and `runs/upwind-tuning-2026-10-12.md` lines ~147–300; figures and caveats quoted from them as listed above.
- Static gate (nine pages) clear, now also scanning for `/home/`. Browser gate re-run after each change, server stopped by port owner: **535 checks passed, 0 failed**; full-page captures regenerated for every page (`foreflight` 1440×4012 / 390×4919, `ai-pilot` 1440×6748 / 390×7638, `how-its-built` 1440×5796 / 390×5714). Viewed: the ForeFlight page at both widths, the F-4 section and status row at both widths, the How It's Built figures at both widths, and both prepared AgentDeck images at full size.


# T43 Part A — video loops: plan, reel component, wiring (light work only)

## Delivered

- `../plan/VIDEO_PLAN.md`: the shot list (15 clip ids across Home, Comms, DF, AI Pilot, The Airplane, How It's Built; ForeFlight and CalTopo skipped on purpose), per clip the loop, source, scenario, what must and must not be visible, poster frame, caption and alt text, status; loop rules (6–12 s, 1280×720, 30 fps, silent, matched ends or a 0.3 s cross-dissolve, ≤ 3 MB WebM / ≤ 5 MB MP4); ffmpeg recipes (cut and normalise, xfade loop, two-pass VP9, H.264 faststart, poster); the component contract. Clips that would show Laminar cockpit or G1000 artwork are marked **[licence]** for the owner's decision (CLAIMS_AND_RISKS §2).
- `assets/css/reel.css`, `assets/js/reel.js`: the reel and clip component (contract in STYLE.md): active-slide-only playback, timed cross-fade, IntersectionObserver pause, the page Pause control honoured through `body.paused`, posters only under reduced motion or Save-Data, keyboard Previous / Next / dots with accessible names and arrow keys, polite caption announcements, missing-clip fallback to the poster with a STILL badge, missing-everything slides removed, `data-require-video` for the hero.
- `index.html`: the hero map is now the first slide of `figure.reel.hero-reel`, followed by the eight planned Home slides. Because the hero requires a real clip, the page today renders exactly as before (map only, controls hidden); slides appear as their files land. The hero caption moved to the top-right so slide captions and controls own the bottom-right; the scrim gradient stays over the headline.
- Clip figures on the pages, by id: Comms `base-radio-link`; DF `df-needle-homing`, `df-faces`, `mission-base-plot`, `console-effects`, `debrief-scoring`; AI Pilot `c182-landing-ai`, `gfc-handover`, `f4-case1-arrival`; The Airplane `airplane-panel`; How It's Built `agentdeck-workers`. Figures with a poster show it with the STILL badge; figures without one are `data-state="pending"` and hidden until their clip loads.
- Placeholder posters (1280×720 WebP) made only from already-published or already-reviewed stills: `mission-base-plot`, `base-radio-link` (the T38 radio capture with the link pill), `ready-room-check`, `console-effects`, `debrief-scoring`, `df-needle-homing`, `df-faces`, `agentdeck-workers`, `pattern-turn-map` (the planner's ESCON square as a stand-in until the G1000 clip exists). No poster for the cockpit, chase, landing, hand-over, panel or F-4 clips: nothing exists to make one from, so those slides stay absent.
- `../plan/STYLE.md`: Reel and Clip rows in the component table.

## Checks (static only, by the CPU rule)

HTML well-formed on all nine pages, no external request, forbidden-string scan clear, every referenced poster present, `reel.js` parses; every page loads `reel.css` and `reel.js`. Browser behaviour (autoplay, pause, reduced motion, off-screen) is verified in Part B.


# T43 Part B — browser clips recorded, encoded, wired and verified

## Recordings

- A local exercise console (dev-open, example seed scenario "C-1 Palomar ILS - 121.5 ELT at ESCON", a fresh scratch database, an example-only instructor token, voice host placeholder) served four scripted scenes to headless Chrome through Playwright's `recordVideo` at 1280×720 (the Debrief and Console scenes at 1280×752/768 so the page header could be cropped off). Positions for the sample aircraft CAP 423 and CAP 415 were posted through the plugin endpoint with the console's own synthesised DF, two bearings logged through the base endpoint, the sortie stopped and revealed for Debrief, and the Base Radio scene driven through the real join flow with the T38 fake WebSocket and injected `rx` / `link` messages. The server was stopped by port owner after each run (port confirmed free). No real roster, address, code or LAN detail existed on that console.
- Every raw take was reviewed frame by frame (one frame a second) before cutting, and every encoded loop again at half-second steps. Fixes from viewing: the Mission Base map zoomed onto the search block (the default view sat over the Pacific); the Console scene re-shot with the instructor header so the aircraft readout shows bearings instead of "withheld", its side panel scrolled so effects and readout share the frame, the page header cropped, and the loop ended before a panel re-render that shifts the content; the Base Radio scene cycles clear → static → choppy → clear so the loop closes on itself; the Debrief header cropped.
- Encoded with the plan's recipes (`t43_encode.sh` in the session scratchpad: cut and normalise, 0.3 s cross-dissolve loop, two-pass VP9 crf 33, H.264 crf 23 faststart, poster at the chosen frame). The AgentDeck clip is a 10 s pan over the already-reviewed, blurred still.

## Clip status

| clip id | WebM | MP4 | poster | status |
|---|---|---|---|---|
| `c182-approach-cockpit` | — | — | — | no files; slide/figure hidden until delivered |
| `c182-chase` | — | — | — | no files; slide/figure hidden until delivered |
| `pattern-turn-map` | — | — | 212 KB | poster only (STILL badge); clip awaited |
| `df-needle-homing` | — | — | 47 KB | poster only (STILL badge); clip awaited |
| `df-faces` | — | — | 46 KB | poster only (STILL badge); clip awaited |
| `mission-base-plot` | 1547 KB | 855 KB | 283 KB | clip live (WebM + MP4 + poster) |
| `base-radio-link` | 145 KB | 153 KB | 23 KB | clip live (WebM + MP4 + poster) |
| `ready-room-check` | — | — | 60 KB | poster only; not recorded (no roster on the dev console) |
| `console-effects` | 1265 KB | 777 KB | 250 KB | clip live (WebM + MP4 + poster) |
| `debrief-scoring` | 593 KB | 455 KB | 73 KB | clip live (WebM + MP4 + poster) |
| `c182-landing-ai` | — | — | — | no files; slide/figure hidden until delivered |
| `gfc-handover` | — | — | — | no files; slide/figure hidden until delivered |
| `f4-case1-arrival` | — | — | — | no files; slide/figure hidden until delivered |
| `airplane-panel` | — | — | — | no files; slide/figure hidden until delivered |
| `agentdeck-workers` | 783 KB | 328 KB | 103 KB | clip live (WebM + MP4 + poster) |

Total shipped: WebM 4336 KB, MP4 2570 KB. All loops 9.7–11.7 s, 1280×720, 30 fps, silent.

## Wiring and gates

- The Home hero reel now has four live slides: the map, then Mission Base, Base Radio and Debrief (the Console clip is on the DF page; the reel's other planned slides stay hidden until their files land). The DF page shows the Mission Base, Console and Debrief clips playing and the two DF-face figures as posters with the STILL badge; How It's Built shows the AgentDeck pan; Comms shows the Base Radio clip. The hero's slide caption was moved above the reel controls after the desktop capture showed them overlapping.
- `qa/t43-check.cjs` (new): hero reel initialised with the map first and only existing clips as slides, at most one video playing, Next / dots / arrow keys move slides and announce captions, the hero Pause control pauses every reel video and Resume restarts it, scrolling the reel off-screen pauses it and back on-screen resumes it, reduced motion shows posters only with nothing playing or advancing (Home and DF), clip figures resolve to video or poster (pending ones hidden), poster-only clips carry the badge and hide their button, a live clip plays in view, pauses on its button and off-screen, no console or page errors (expected 404s for not-yet-delivered clips excluded), and a hero capture on slide two at both widths. Result: **36 checks passed, 0 failed**.
- `qa/t39-check.cjs`: **535 passed, 0 failed** (clip 404s excluded; reels excluded from the no-animation rule). `qa/t37-check.cjs` (Home): passes (same exclusion added to its HTTP and `file://` listeners). Captures regenerated for every page; Home and DF at both widths viewed as banded sheets, plus the hero on slide two at both widths.
- Page weight as measured by the reel gate (every response from the local origin, with the reel stepped through its slides so every clip loaded): Home desktop 7.3 MB, Home mobile 7.6 MB, DF desktop 8.0 MB. The reel loads only metadata until a slide is reached, so a visitor who stays on the map pays for none of the clips.

## Waiting on Codex (simulator, Air Manager, F-4)

The delivery list at the end of `../plan/VIDEO_PLAN.md` names the nine remaining clip ids, their three files each, the scenario, the poster frame and which ones need the owner's licence decision; the plan now also carries the X-Plane overlay clean-up and crop recipe measured on the T42 frames (menu bar 28 px, FPS panel at 0–385 × 28–62, mouse-control box (690,114)–(910,336) with its cross at (800,225)).

# Home hero: `web-panels` clip (replaces the Base Radio slide)

- **Change.** In `site/index.html` the hero slide `data-clip="base-radio-link"` was replaced by one slide `data-clip="web-panels"` (`data-duration="24500"`, poster + WebM/MP4 sources, alt and aria-label, short caption). Nothing else in the file changed (the other slides are byte-identical). The `base-radio-link` files and its Comms figure are untouched. The hero reel now plays: the map, `hero-panel`, `c182-chase`, `web-panels`, `debrief-scoring`.
- **Clip.** 24.5 s, 1280x720, 30 fps, silent, ten panels at about 2.7 s with 0.25 s cross-fades, the last 0.3 s dissolving into the first: Exercise Setup, Ready Room, Flight Planner (route, then the W&B dialog), Exercise Console (sortie running, aircraft readout), AI Pilot instrument deck, airborne maneuver deck (text typed, not executed), Mission Base (two aircraft, two bearing cuts), Base Radio text console (Form 110 rows from the PTT), Mission Base headset radio (link pill "Clear, direct to base" then "Some static, via Julian repeater", Form 110 rows), Debrief (scoring cards, bearing-error chart). Files: `web-panels.webm` 2,297,708 bytes (VP9 crf 48, yuv420p), `web-panels.mp4` 1,974,537 bytes (H.264 crf 30, faststart), `web-panels-poster.webp` 209,358 bytes (the planned route).
- **How it was made.** `qa/record-web-panels.cjs` (header says how to run it) starts its own local servers on 127.0.0.1:18700-18703 (exercise console in dev-open mode on a scratch database with the example scenario and its generic seats, flight planner with a scratch copy of the airport database and tiles offline, the AI Pilot deck and the maneuver deck in mock mode), signs in with the scratch database's own seat codes (never shown), feeds CAP 423 / CAP 415 positions once a second with the console's synthesised DF, logs bearings, records each panel in its own Playwright `recordVideo` context in system Chrome, then cuts, cross-fades and encodes with ffmpeg. All servers were stopped afterwards (ports confirmed free).
- **Left out and why.** The Agent Coordination Board (`services/board`, `ai_pilot/static/board.html`): its content is the real dispatch queue (file locks, repository paths, a LAN address); nothing is faked. The Flight Planner user guide: its first screen lists a LAN address and host names and a tenth/eleventh panel would take the clip past 26 s. The planner's SAR dialog was avoided because its default datum is the example scenario's hidden beacon. The AI Pilot deck shows mock telemetry with example values injected (cruise, 4,500 ft, 112 kt) so the instruments are not all zero; the maneuver deck is the mock's own static values.
- **Checked.** Every panel viewed frame by frame in the raw takes and in the encoded loop (no path, email, access or badge code, LAN address, host name, real name or roster on screen; the Ready Room shows only the built-in generic seats). Served `site/` with `python3 -m http.server` on a free port and loaded `/` in system Chrome at 1280 and 375 px: the reel lists map, hero-panel, c182-chase, web-panels, debrief-scoring; the web-panels slide reaches `state=video`, plays from the WebM (currentTime advances), no console errors beyond the 404s for clips that are still pending, no horizontal overflow at either width. Screenshots: `screenshots/web-panels-hero-desktop.png`, `screenshots/web-panels-hero-mobile.png`. The existing gates (`t37`, `t39`, `t43`) were not re-run.

