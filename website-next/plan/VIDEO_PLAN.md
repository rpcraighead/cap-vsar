# CAP-VSAR website — video loops: shot list, component contract, encode recipes

Short, silent, seamless loops that show the exercise moving. Every clip is a file pair plus a poster under
`website-next/site/assets/video/`: `<id>.webm` (VP9), `<id>.mp4` (H.264, faststart) and `<id>-poster.webp`. Pages
reference clips by id only; a page never breaks when a file is missing (the poster shows, or the slide is left out).

Sources: **browser** = a headless-Chrome recording of the exercise console pages against a local console with example
data (the builder records these); **OBS-XP** = OBS capture of X-Plane 12 (Codex, after T42); **OBS-AM** = OBS capture
of the Air Manager Mission Observer station; **F-4** = the sibling F-4 test programme's own recording; **derived** = made
from an already-reviewed still.

Rules for every clip: no path, email address, access or badge code, LAN address, hostname, real name or roster;
example scenario only (ESCON, the sample callsigns CAP 423 / CAP 415 / CAP 487, `example.org` addresses if any address
is on screen); the Leaflet attribution stays visible on map captures; no X-Plane menus, file dialogs or desktop
chrome; no audio track. Licensing: per CLAIMS_AND_RISKS.md §2 the X-Plane cockpit, the stock G1000 screens and the
C172SP-derived panel are Laminar artwork. Clips marked **[licence]** below show that artwork and need the owner's
decision before they are published; exterior and chase views show the open-licensed FlightGear exterior and are fine;
the Air Manager station is our own faceplates next to a stock display, which should be cropped or kept blank.

## Shot list

| id | page(s) | loop (6–12 s) | source | scenario to capture | must be visible | must not be visible | poster | status |
|---|---|---|---|---|---|---|---|---|
| `c182-approach-cockpit` | Home reel, AI Pilot | 10 s: CAP 487 on short final, flare and touchdown, cockpit view, Gillespie 27R | OBS-XP **[licence]** | the C182T package, AI Mission Pilot flying the landing; clear day | runway, the aim point, the panel | X-Plane UI, menus, FPS counter | the flare, nose high over the numbers | waiting on Codex |
| `c182-chase` | Home reel | 8 s: chase camera behind the C182T (Civil Air Patrol N429CP livery) as the AI pilot flies a banked search pattern over foothill terrain; an AI-controlled segment of a search-pattern run that failed its altitude gate, so never described as a successful pattern trial | OBS-XP | search-pattern run, external view | the N429CP livery, terrain, bank | cockpit, UI | banked over the foothills | **delivered** 2026-10-18 |
| `pattern-turn-map` | Home reel | 10 s: the expanding-square corner flown with the G1000 map showing the pattern legs | OBS-XP **[licence]** (G1000 map) | ESCON square at 4,500 ft, AI pilot | the pattern on the map, the turn | UI | the aircraft symbol at a corner | waiting on Codex |
| `df-needle-homing` | Home reel, DF | 10 s: the Becker 517 face as the needle settles from 40° off to centred while the signal bar climbs | OBS-AM | CAP 423 inbound on the beacon, 121.5, clear path | the 517 face, needle, signal bar | the stock display, Air Manager chrome, desktop | needle 20° right, bar half | waiting on Codex |
| `df-faces` | DF | 8 s: the RT-600 scanning, then decoding a 406 burst: bearing appears, TIMEHOLD counts | OBS-AM | CAP 415, 406.025 | the RT-600 face | as above | bearing just decoded | waiting on Codex |
| `mission-base-plot` | Home reel, DF | 10 s: the Mission Base map with two aircraft tracks moving and two bearing lines being plotted to a crossing near ESCON | browser | sample scenario; two sorties reporting; LOPs from the console's own plot | tracks, two lines of position, the sectional with the Leaflet attribution | the true beacon (hidden until reveal), any roster address | the two lines just crossed | **done** (browser, Part B) |
| `base-radio-link` | Home reel, Comms | 8 s: the Base Radio page receiving traffic: the speaker line lights, the link pill changes from "Clear · direct to base" to "Some static · via Julian repeater" and a Form 110 row appears | browser | injected link messages, example callsigns | control head, the pill, the Form 110 row | real callsigns, codes | the "Some static · via Julian repeater" pill | **done** (browser, Part B) |
| `ready-room-check` | Home reel (optional; not recorded: the open dev console has one presence only, so seats cannot be shown turning ready without a roster) | 8 s: the Ready Room as seats go ready one by one | browser | sample roster, `example.org` | seat tiles turning ready | any real address | 6 of 10 ready | **done** (browser, Part B) |
| `console-effects` | DF, AI Pilot (optional) | 10 s: the Exercise Console with a sortie running; the director switches an effect on and the aircraft DF truth readout changes | browser | sample scenario, sortie running, multipath toggled | the effects list, the truth readout | codes, addresses | the effect just switched on | **done** (browser, Part B) |
| `debrief-scoring` | Home reel, DF | 8 s: the Debrief page: scoring cards and the bearing-error chart drawing | browser | the sample sortie's recorded positions | cards, chart, the 10° band | names | the chart fully drawn | **recorded in Part B** |
| `web-panels` | Home reel (replaces the `base-radio-link` slide, which stays on Comms) | 24.5 s: ten web panels, about 2.7 s each with 0.25 s cross-fades, in the order of a mission: Exercise Setup, Ready Room, Flight Planner (route, then the W&B dialog), Exercise Console (sortie running), AI Pilot instrument deck, airborne maneuver deck, Mission Base (two aircraft, bearing cuts), Base Radio text console (Form 110 rows), Mission Base headset radio (link pill, Form 110 rows), Debrief (scoring, error chart); the last frame cross-dissolves into the first (longer than the usual 6-12 s: approved for this clip) | browser | `qa/record-web-panels.cjs`: local exercise console in dev-open mode (example scenario C-1, scratch DB, built-in generic seats), flight planner, AI Pilot deck (mock, example telemetry injected) and maneuver deck (mock); sessions made with the scratch database's own seat codes, never shown | each page's own layout; Leaflet attribution on the maps | seat codes, tokens, the planner's default SAR datum (it is the hidden beacon), the user guide's first screen (LAN address, hostnames), the Agent Coordination Board (real dispatch queue) | the planned route (Flight Planner) | **done** (browser) |
| `c182-landing-ai` | AI Pilot | 10 s: the AI landing at Montgomery-Gibbs (KMYF) runway 28R, seen from the side: aim point, wheels on about 63 m past it, rollout | OBS-XP | AI landing trial, C182T, Civil Air Patrol N429CP livery | aim point and touchdown, rollout | UI | wheels on | **delivered** 2026-10-18 |
| `gfc-handover` | AI Pilot | 10 s: cockpit: the AI hands to the GFC 700 (AP annunciator comes on), the terrain guard commands a climb at the ridge | OBS-XP **[licence]** | the ridge-crossing trial | the autopilot annunciation, altitude climbing | UI | AP just engaged | waiting on Codex |
| `f4-case1-arrival` | Home reel, AI Pilot | 12 s: the F-4 in the groove to the arrested landing, external view astern of the ship | F-4 | one of the recorded arrests (v55, the 3-wire touchdown) | ship, aircraft, hook down, the stop on deck | any test-programme UI, paths | the moment of touchdown | waiting on the F-4 programme |
| `airplane-panel` | The Airplane | 8 s: a slow pan across the panel to the prop lever and the manifold-pressure gauge on the engine page | OBS-XP **[licence]** | CAP 487 on the ramp, engine running | prop lever, MP and RPM gauge | UI | the engine page | waiting on Codex and the licence decision |
| `agentdeck-workers` | How It's Built | 10 s: a slow pan across the reviewed three-worker screenshot | derived (the already-reviewed, blurred still) | none | the three worker panes | anything not in the reviewed still | the still itself | **done** (derived, Part B) |
| `hero-panel` | Home reel (slide 2) | 6 s: the Mission Observer station panel (G1000 display with the search pattern, audio panel, Becker 517 face, tactical radio) | OBS-AM **[licence]** (the display capture) | the station composite; needle and signal bar alive | Air Manager chrome, desktop, any address | the panel as in `df-becker-517.webp` | **pending** (Codex recording, T22; files will appear in `/tmp/cap-vsar-df/out/`); until then the slide shows the station still `df-becker-517.webp` as its poster (`data-allow-still`) |
| `hero-cockpit` | Home reel | 6 s: cockpit view (scenario to confirm from the recording) | OBS-XP **[licence]** | to confirm | X-Plane UI, menus, FPS counter | to choose | **pending** (Codex recording, T22); no slide yet: caption and alt are written once the clip is reviewed |
| `hero-flight` | Home reel | 6 s: exterior flight view (scenario to confirm from the recording) | OBS-XP | to confirm | UI | to choose | **pending** (Codex recording, T22); no slide yet, as above |

Skipped on purpose: ForeFlight (no real capture of the tablet exists; nothing is faked), CalTopo (plan only).

Captions and alt text (plain CAP language; the alt describes the poster frame, the caption the loop):

| id | caption | alt |
|---|---|---|
| `c182-approach-cockpit` | **Short final, 27R.** The AI Mission Pilot flares CAP 487 over the numbers at Gillespie. | Cockpit view on short final with the runway ahead and the nose rising for the flare. |
| `c182-chase` | **Search pattern.** The AI pilot flying a banked search pattern over foothill terrain, seen from behind. | A high-wing Civil Air Patrol single seen from behind, banked over hills and housing. |
| `pattern-turn-map` | **The expanding square.** A corner of the ESCON pattern, with the legs drawn on the map. | A map display showing a square search pattern with the aircraft symbol at one corner. |
| `df-needle-homing` | **The needle settles.** Inbound on the beacon, the Becker 517's needle swings to centre as the signal climbs. | Direction-finder face with the bearing needle just right of centre and the signal bar half full. |
| `df-faces` | **A 406 burst, decoded.** The RT-600 scans, then shows the bearing and holds it. | RHOTHETA face showing a decoded 406 bearing on the compass rose. |
| `mission-base-plot` | **Two cuts.** Mission Base logs each aircraft's bearing from where it called it and draws the line on the map. | Mission Base map zoomed on the search block with two aircraft markers moving and two cuts in the bearing log. |
| `base-radio-link` | **Heard through the repeater.** The Base Radio tells the Mission Radio Operator how the call is coming in, and logs it. | Base Radio page with a status pill reading Some static, via Julian repeater, above a Form 110 log row. |
| `ready-room-check` | **Who is ready.** Seats turn green as headsets and stations check in. | Ready Room board with seat tiles, most marked ready. |
| `console-effects` | **An effect, mid-sortie.** The director switches on wing blanking and watches each cockpit's bearing and signal in the readout. | Exercise Console with the injected-effects list, wing blanking switched on, and each aircraft's bearing and signal readout. |
| `debrief-scoring` | **Scored.** Closest approach, bearing error and the needle's error over time, per aircraft. | Debrief page with scoring cards and a bearing-error chart. |
| `web-panels` | **The web panels.** Setup, Ready Room, Flight Planner, Exercise Console, AI Pilot decks, Mission Base, Base Radio and Debrief, with example data. | Flight Planner showing a planned route from KSEE through JLI and TRM to KPSP on the sectional chart, with the navigation log below. (The video's aria-label lists all ten panels.) |
| `c182-landing-ai` | **Touchdown at Montgomery-Gibbs (KMYF).** The AI pilot's landing, seen from the side: wheels on about 63 m past the aim point, then rollout. | A high-wing Civil Air Patrol single touching down on a runway, seen from above and the side. |
| `gfc-handover` | **Handing over.** The AI engages the GFC 700 and the terrain guard climbs away from the ridge. | Cockpit view with the autopilot annunciation lit and terrain ahead. |
| `f4-case1-arrival` | **The groove.** The F-4 test programme's jet comes aboard. Simulator characterisation, not a qualification; see the notes on the AI Pilot page. | A jet fighter with hook down on final to a carrier deck, seen from astern. |
| `airplane-panel` | **The 182's panel.** The prop lever and the manifold-pressure gauge the stock 172 never had. | Aircraft panel with the throttle, prop and mixture levers and an engine page showing manifold pressure. |
| `agentdeck-workers` | **Three workers, one evening.** Claude, Codex and Antigravity side by side. | Three terminal panes side by side, each with a file tree and a transcript. |
| `hero-panel` | **The Mission Observer’s station.** A training replica of the Becker SAR-DF 517 direction-finder head, the tactical radio, the audio panel and the display with the search pattern, as simulated. | Mission Observer station panel: the G1000 multifunction display showing the search and rescue mission map with an expanding-square pattern, the audio panel, the Becker SAR-DF 517 training face reading a bearing of 337 with its signal bar, and the Technisonic tactical radio head. |
| `hero-cockpit` | to write once the clip is reviewed | to write once the clip is reviewed |
| `hero-flight` | to write once the clip is reviewed | to write once the clip is reviewed |

## Loop construction

* Length 6–12 s, 1280×720 (the hero can show it at 64 % width on desktop; nothing larger is needed), 30 fps, silent.
* Seamless: either pick in and out points where the picture matches (a needle crossing centre, a track between
  position updates), or cross-dissolve the last 0.3 s into the first 0.3 s (recipe below). Browser recordings are
  scripted so the end state equals the start state where possible (e.g. the pill cycles clear → static → clear).
* Target ≤ 3 MB per WebM and ≤ 5 MB per MP4; the Home reel budget is about 25 MB in total, and the reel loads a
  clip's bytes only when its slide is reached (`preload="metadata"`).
* Poster: a single frame from the clip, exported at 1280×720 WebP quality 80 (about 60–150 KB).

## Encode recipes

Trim, scale, and make the seamless cross-dissolve (`$IN` raw capture, `$ID` clip id, `$START` and `$LEN` in seconds):

```sh
# 1. cut the loop and normalise to 1280x720, 30 fps, no audio
ffmpeg -y -ss "$START" -t "$LEN" -i "$IN" -an -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30" -c:v libx264 -crf 14 -preset slow "/tmp/$ID-cut.mp4"

# 2. seamless loop: cross-dissolve the last 0.3 s into the first 0.3 s (output is LEN-0.3 s long)
ffmpeg -y -i "/tmp/$ID-cut.mp4" -filter_complex "[0:v]split[a][b];[a]trim=0:$(echo "$LEN-0.3"|bc),setpts=PTS-STARTPTS[head];[b]trim=$(echo "$LEN-0.3"|bc),setpts=PTS-STARTPTS[tail];[head][tail]xfade=transition=fade:duration=0.3:offset=$(echo "$LEN-0.6"|bc)[v]" -map "[v]" -an -c:v libx264 -crf 14 "/tmp/$ID-loop.mp4"

# 3a. WebM / VP9, two-pass, no audio
ffmpeg -y -i "/tmp/$ID-loop.mp4" -an -c:v libvpx-vp9 -b:v 0 -crf 33 -row-mt 1 -pass 1 -f null /dev/null
ffmpeg -y -i "/tmp/$ID-loop.mp4" -an -c:v libvpx-vp9 -b:v 0 -crf 33 -row-mt 1 -pass 2 "assets/video/$ID.webm"

# 3b. MP4 / H.264, faststart, no audio
ffmpeg -y -i "/tmp/$ID-loop.mp4" -an -c:v libx264 -crf 23 -preset slow -pix_fmt yuv420p -movflags +faststart "assets/video/$ID.mp4"

# 4. poster from the chosen frame ($POSTER_T seconds in)
ffmpeg -y -ss "$POSTER_T" -i "/tmp/$ID-loop.mp4" -frames:v 1 -c:v libwebp -quality 80 "assets/video/$ID-poster.webp"
```

X-Plane captures from OBS (T42 proof: FFmpeg x11grab window source, NVENC H.264, 1600×900, 30 fps, with the
closed menu bar, the FPS panel and the mouse-control rectangle still in the picture). Measured on the T42 frames:
the menu bar is the top 28 px, the FPS panel sits at x 0–385, y 28–62, the mouse-control rectangle runs from
(690, 114) to (910, 336) with a cross about 20 px across at its centre (800, 225). The recipe first paints out the
rectangle's four thin edges and the cross from their surroundings (`delogo` on 8 px strips, invisible against sky or
sea), then crops the top 64 px away and takes the largest 16:9 window that remains, centred, before scaling:

```sh
# X-Plane 1600x900 OBS capture -> clean 1280x720 (apply before step 1's cut, or fold into its -vf)
XP_CLEAN="delogo=x=686:y=110:w=228:h=8,delogo=x=686:y=332:w=228:h=8,delogo=x=686:y=110:w=8:h=230,delogo=x=906:y=110:w=8:h=230,delogo=x=788:y=213:w=24:h=24,crop=1486:836:57:64,scale=1280:720,fps=30"
ffmpeg -y -ss "$START" -t "$LEN" -i "$IN" -an -vf "$XP_CLEAN" -c:v libx264 -crf 14 -preset slow "/tmp/$ID-cut.mp4"
```

Better still is to record without the overlays: in X-Plane, turn the on-screen frame-rate readout off (Settings →
Data Output, the "frame rate" row's "show in cockpit" box) and keep the pointer outside the simulator window or
over a part of the window that does not draw the mouse-control box (the box appears while the cursor is over the
3-D view); then only the 28 px menu bar needs cropping (`crop=1600:872:0:28` is not 16:9, so use
`crop=1550:872:25:28,scale=1280:720`). If the capture is recorded at a different size, re-measure the overlays on a
frame before trusting these numbers. Audio tracks are dropped (`-an`) in every recipe; the AAC track OBS records is
never published.

Browser recordings: Playwright's `recordVideo` (WebM at the viewport size; set the viewport to 1280×720 and
`deviceScaleFactor 1`) is the raw `$IN`. Pan over a still (the derived clip):

```sh
ffmpeg -y -loop 1 -i how-its-built-agentdeck-workers.webp -t 10 -vf "scale=2560:-2,zoompan=z='1.0':x='min((iw-1280)*on/300,iw-1280)':y='(ih-720)/2':d=1:s=1280x720:fps=30" -c:v libx264 -crf 16 /tmp/agentdeck-workers-cut.mp4
```

## Component contract (built in `assets/css/reel.css` and `assets/js/reel.js`)

```html
<figure class="reel" data-interval="7000" aria-roledescription="carousel" aria-label="Simulator clips">
  <div class="reel-slides">
    <div class="reel-slide" data-duration="14000"> …an inline SVG slide… <p class="slide-caption">…</p></div>
    <div class="reel-slide" data-clip="mission-base-plot">
      <img class="slide-poster" src="assets/video/mission-base-plot-poster.webp" alt="…">
      <video muted playsinline loop preload="metadata" poster="assets/video/mission-base-plot-poster.webp">
        <source src="assets/video/mission-base-plot.webm" type="video/webm">
        <source src="assets/video/mission-base-plot.mp4" type="video/mp4">
      </video>
      <p class="slide-caption"><strong>Two cuts.</strong> …</p>
    </div>
  </div>
  <div class="reel-controls"><button class="reel-prev" type="button">Previous</button><div class="reel-dots" role="group" aria-label="Choose a clip"></div><button class="reel-next" type="button">Next</button></div>
  <p class="reel-live" aria-live="polite"></p>
</figure>
```

A single clip is `<figure class="clip" data-clip="…">` with the same inner video, poster and caption plus its own
Pause button. Behaviour: only the active slide plays; slides cross-fade after their `data-duration` (else the
figure's `data-interval`, default 7 s); an IntersectionObserver pauses everything off-screen; the Home hero's Pause
button (which sets `body.paused`) pauses every reel and clip on the page; `prefers-reduced-motion: reduce` and
Save-Data show posters only and never autoplay or auto-advance; Previous / Next and the dots are keyboard buttons
with accessible names; the caption of the active slide is announced politely; a slide whose video cannot load keeps
its poster, and a slide with neither is removed with its dot. A `.clip` whose video and poster are both missing hides
itself. Until a clip's files exist its slide is simply absent from the reel, so the Home hero shows the map alone. Exception (T22): a
slide marked `data-allow-still` keeps its poster inside a `data-require-video` reel, with the STILL FRAME badge and the caption note;
the hero's `hero-panel` slide uses it so the station panel is in the rotation before its clip exists.


## Delivery list for the simulator clips (Codex, after T42)

Drop each finished pair and its poster straight into `website-next/site/assets/video/`; the pages already reference
these ids and show the slide or figure the moment the files exist (no HTML change needed). Record with the OBS
window source at 1600×900, 30 fps, then run the recipes above: the X-Plane overlay clean-up (`$XP_CLEAN`) in step 1,
the loop (step 2), WebM + MP4 (3a, 3b) and the poster (4). Keep WebM ≤ 3 MB and MP4 ≤ 5 MB; 6–12 s; no audio.

| clip id | files to deliver | source and scenario | poster frame | note |
|---|---|---|---|---|
| `c182-approach-cockpit` | `c182-approach-cockpit.webm`, `.mp4`, `-poster.webp` | OBS-XP, cockpit view, CAP 487 short final and flare on KSEE 27R, AI pilot | the flare | **[licence]** owner decision first |
| `c182-chase` | `c182-chase.webm`, `.mp4`, `-poster.webp` | OBS-XP, chase view, banked search pattern over the foothills, N429CP livery | banked over the foothills | exterior only; **delivered** 2026-10-18 |
| `pattern-turn-map` | `pattern-turn-map.webm`, `.mp4`, `-poster.webp` | OBS-XP, G1000 map on an ESCON square corner | aircraft symbol at a corner | **[licence]**; replaces the planner still |
| `df-needle-homing` | `df-needle-homing.webm`, `.mp4`, `-poster.webp` | OBS-AM, Becker 517 face, needle settling, signal climbing | needle 20° right, bar half | crop to our faceplate; no stock display |
| `df-faces` | `df-faces.webm`, `.mp4`, `-poster.webp` | OBS-AM, RT-600 scan then 406 decode | bearing just decoded | as above |
| `c182-landing-ai` | `c182-landing-ai.webm`, `.mp4`, `-poster.webp` | OBS-XP, side view of the AI landing on KMYF 28R, N429CP livery | wheels on | exterior only; **delivered** 2026-10-18 |
| `gfc-handover` | `gfc-handover.webm`, `.mp4`, `-poster.webp` | OBS-XP, cockpit, AP engages, terrain guard climbs | AP just engaged | **[licence]** |
| `airplane-panel` | `airplane-panel.webm`, `.mp4`, `-poster.webp` | OBS-XP, slow pan to the prop lever and the MP gauge | engine page | **[licence]** |
| `f4-case1-arrival` | `f4-case1-arrival.webm`, `.mp4`, `-poster.webp` | the F-4 programme's recording of a v55 arrest, external astern | touchdown | no test-programme UI or paths |
| `hero-panel` | `hero-panel.webm`, `.mp4`, `-poster.webp` | OBS-AM, the Mission Observer station panel, 6 s | the panel | **[licence]** (G1000 capture); the `-poster.webp` overwrites the station still placed there by T22 |
| `hero-cockpit` | `hero-cockpit.webm`, `.mp4`, `-poster.webp` | OBS-XP, cockpit, 6 s | to choose | **[licence]**; no slide in the page yet |
| `hero-flight` | `hero-flight.webm`, `.mp4`, `-poster.webp` | OBS-XP, exterior, 6 s | to choose | no slide in the page yet |
| `web-panels` | `web-panels.webm` (2.3 MB), `.mp4` (2.0 MB), `-poster.webp` (0.2 MB) | browser, `qa/record-web-panels.cjs`, ten web panels, 24.5 s | the planned route | **delivered** (Home reel slide; the recipes above with VP9 crf 48 and H.264 crf 30 to stay under 2.5 MB) |

Delivered already (browser recordings, T43 Part B): `mission-base-plot`, `base-radio-link`, `console-effects`,
`debrief-scoring`; browser (web-panels pass): `web-panels` (`web-panels.webm`, `.mp4`, `-poster.webp`, 24.5 s, Home reel slide in place of `base-radio-link`); derived: `agentdeck-workers`; simulator (2026-10-18, exterior views, N429CP livery): `c182-chase`
and `c182-landing-ai`, both with posters, both faststart MP4 + WebM. Not recorded: `ready-room-check` (needs a roster the open dev
console does not have), ForeFlight, CalTopo.
