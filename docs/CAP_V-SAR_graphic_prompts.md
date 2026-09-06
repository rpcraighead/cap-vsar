# CAP V-SAR — image generation prompts
Slide graphic 1: "The training system" (stations, staff, flows)

---

## A note before you paste

Google **Flow** is video-first (Veo). For a still slide graphic the better fit is
**ImageFX / Gemini image generation / Whisk** — the prompt below works unchanged in
any of them. If you do want a short animated version for the conference, there's a
motion clause at the bottom.

**Generate it with NO text.** Every image model still garbles small labels, and a
briefing slide with misspelled labels is worse than no labels. Get clean artwork,
then drop PowerPoint text boxes on top using the label list in section 3. That also
keeps the labels editable when someone asks you to rename a role.

Set the output to **16:9**.

---

## 1. Primary prompt — paste this

A clean modern isometric infographic illustration for a professional aviation
training briefing, 16:9 landscape, on a soft off-white background. It shows a
distributed flight-simulation training system as a connected network of
workstations, viewed from a slightly elevated three-quarter angle.

LEFT GROUP — one aircraft crew of three people at adjacent desks, visibly working
as a team:
- A pilot at a desktop flight simulator: a large widescreen monitor showing a light
  single-engine aircraft cockpit view over coastal terrain, a control yoke mounted
  to the desk edge, rudder pedals on the floor, wearing an aviation headset.
- Beside the pilot, a second crew member at a smaller vertical touchscreen showing a
  round radio direction-finder instrument with a bearing needle and a vertical
  signal-strength bar, plus a small rectangular radio control head with a segment
  display. A notepad and pen beside the screen.
- A third crew member with a tablet showing a simple instrument panel, and a second
  monitor showing an outside view over coastal terrain and hills.
- All three wear aviation headsets with boom microphones.

CENTER — a stylized services element floating slightly above the desk plane: a small
rounded slab or short stack of server cards with a soft glow beneath it,
representing shared network services. Simple and abstract, not a photoreal data
centre.

RIGHT GROUP — two separate remote people, each alone at a laptop, spaced apart from
the crew to read as "somewhere else":
- A staff member at a laptop showing a topographic search-and-rescue map with a small
  aircraft symbol, a shaded search area, and a few plotted bearing lines.
- An instructor positioned slightly higher and apart, at a laptop showing a simple
  control panel of switches and sliders, looking toward the whole scene.

TOP EDGE — a small rounded badge containing a stylized air-traffic-control tower
silhouette with radio waves, connected downward to the pilot, representing an
external live ATC service.

CONNECTIONS — thin, clean, softly glowing lines linking each station to the central
services element and to each other, with small directional dots along them
suggesting flow. Two visually distinct link styles: solid lines for data, and
dashed or beaded lines for voice.

STYLE — flat vector isometric illustration with subtle depth and soft long shadows.
Technical diagram aesthetic. Crisp geometry, generous white space, uncluttered,
calm and understated. Professional enough for a military-auxiliary leadership
briefing. Simplified stylized human figures, not photorealistic portraits.

COLOR — deep navy and medium blue as the primary palette (#1F3864, #2E5496), pale
blue fills (#D9E2F3), off-white background (#F7F8FA), warm grey shadows. Exactly one
restrained red accent (#C00000), used only for the direction-finder needle and a
single highlighted connection line. No other saturated colours.

CRITICAL — no text, no words, no letters, no numbers anywhere in the image. No
signage, no captions, no UI labels, no screen text. Screens show shapes, needles,
maps and panels only.

---

## 2. Negative prompt

text, words, letters, numbers, captions, labels, watermark, logos, brand marks,
military insignia, aircraft registration numbers, cluttered background,
photorealistic human faces, dramatic cinematic lighting, neon, cyberpunk, dark
background, lens flare, heavy gradients, 3D render noise, fisheye distortion,
crowded desks, cables everywhere

---

## 3. Labels to add in PowerPoint afterwards

Place these as text boxes over the finished artwork (Calibri, navy #1F3864, bold for
the role, grey #6B6B6B for the sub-line):

| Position | Label | Sub-line |
|---|---|---|
| Left, pilot | **Mission Pilot** | X-Plane 12 · yoke and pedals · flies the pattern |
| Left, centre | **Mission Observer** | DF head · second COM panel · bearing log |
| Left, right | **Mission Scanner** | Scan discipline · clock-position reports |
| Centre slab | **Shared services** | Scenario (beacon truth) · tracking · mission voice net |
| Right, upper | **Instructor / SET** | Places the beacon · injects effects · signs off tasks |
| Right, lower | **Mission Base staff** | IC · AOBD · MRO — browser only, from anywhere |
| Top badge | **PilotEdge — live ATC** | Human controllers, ZLA · 8am–11pm Pacific |
| Line legend | — | Solid: data · Dashed: voice |

Optional footer strip: *One aircraft crew, one instructor, and mission base — each on
their own machine, anywhere with a connection.*

---

## 4. Variants worth trying

**Warmer / more human.** Append: *"Slightly warmer palette with soft ambient light
from the upper left. Crew members shown in relaxed but attentive postures, one
turning toward another as if speaking on intercom."*

**Flatter / more diagrammatic.** Replace the STYLE paragraph with: *"Strictly flat
2D vector infographic, no isometric perspective, no shadows. Elements arranged as
labelled rounded rectangles connected by orthogonal lines with arrowheads. Icon-led,
in the style of a clean technical systems diagram."* Use this one if the isometric
version comes back too busy for a projector.

**Aircraft-forward.** Append: *"A small stylized high-wing single-engine aircraft
silhouette flying above the scene in the upper left, with a faint dashed search
pattern track beneath it and a small beacon symbol emitting concentric arcs on the
ground."* Good if you want the slide to read as SAR at a glance rather than as IT.

---

## 5. If you do use Flow for a short animated version

Append: *"Subtle continuous motion: small bright dots travelling along the
connection lines from the workstations toward the central services element and
onward to the mapping laptop; the direction-finder needle swinging slowly and
settling; the search area on the map gently pulsing once. Camera almost static with
a very slow push-in. No text appears at any point. 8 seconds, seamless loop."*

Keep it under ten seconds and loop it behind you while you talk — a longer clip
starts competing with you for the room's attention.

---

## 6. Second graphic, if you want a matching pair

A companion "how a signal becomes a bearing" diagram would pair well with this one
and covers the part leadership finds least intuitive:

*Isometric cutaway of coastal terrain with a small beacon on the ground emitting
concentric radio arcs; a light aircraft above at two different altitudes showing a
blocked line-of-sight behind a ridge at the lower altitude and a clear line at the
higher one; a faint reflected signal path bouncing off a second ridge to illustrate
a false bearing. Same palette and flat isometric vector style. No text.*

That one earns its place on a slide because it explains radio horizon, terrain
masking and multipath in a single picture — which is otherwise three paragraphs.
