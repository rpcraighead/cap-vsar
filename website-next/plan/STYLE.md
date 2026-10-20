# CAP-VSAR website — style tokens and components

Theme: "ops room at night". Charcoal-navy ground, safety-orange for the beacon and anything that signals, cyan and
sectional-green as secondary, light "briefing paper" panels for long reading. Visual language from the sectional
chart, range rings and DF bearing lines. Static HTML/CSS only; no frameworks required. System font stacks only (T11,
2026-10-18): no web font is shipped and no third-party font request is made; the condensed headline face is
whatever condensed sans the visitor's system has, and the H1 wraps with `text-wrap: balance` instead of hard breaks.

## Design tokens (CSS custom properties)

```css
:root {
  /* ground */
  --bg:            #0B1220;   /* charcoal-navy page background */
  --bg-2:          #111A2B;   /* raised surfaces, header, cards */
  --bg-3:          #182338;   /* hover / inset */
  --line:          #27344A;   /* hairlines, range rings */
  --line-strong:   #3A4A66;

  /* text on dark */
  --text:          #E6ECF2;
  --text-muted:    #9AA7B5;
  --text-faint:    #6B7A8C;

  /* signals */
  --orange:        #FF6A13;   /* safety orange: beacon, ELT, alerts, primary CTA */
  --orange-soft:   #FF8A47;
  --orange-glow:   rgba(255,106,19,.35);
  --cyan:          #27C7D9;   /* bearing lines, links, live state */
  --cyan-soft:     #7FE0EA;
  --green:         #7FBF4D;   /* sectional green: ok, ready, terrain lowlands */
  --green-deep:    #356B2A;   /* T11: was #3F7A32; 5.6:1 on paper, 5.2:1 on the proven-chip tint */
  --yellow:        #E9D45C;   /* sectional yellow: towns on the hero map only */
  --magenta:       #C8328B;   /* sectional magenta: sparingly, one accent on the hero map */

  /* briefing paper (light panels) */
  --paper:         #F3EFE6;
  --paper-2:       #E9E3D6;
  --paper-line:    #CFC7B7;
  --ink:           #15202B;
  --ink-muted:     #4B5868;

  /* type */
  --font-head:  "Arial Narrow", "Roboto Condensed", "Helvetica Neue", Arial, system-ui, sans-serif;   /* placard headlines, 700; system faces only (T11) */
  --font-body:  system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono:  ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;  /* frequencies, callsigns, seat ids */

  /* type scale (rem) */
  --fs-hero:   clamp(2.6rem, 6vw, 4.6rem);
  --fs-h1:     clamp(2.25rem, 4.6vw, 3.4rem);   /* page titles (T11) */
  --fs-h2:     clamp(1.75rem, 3vw, 2.35rem);    /* section headings; h2 no longer shares the h1 size (T11) */
  --fs-h3:     1.25rem;
  --fs-body:   1.0625rem;      /* 17px */
  --fs-small:  .9375rem;
  --fs-mono:   .95rem;
  --lh-body:   1.6;
  --measure:   66ch;           /* max line length for body copy */

  /* spacing (4-pt base) */
  --s-1: .25rem; --s-2: .5rem; --s-3: .75rem; --s-4: 1rem; --s-6: 1.5rem;
  --s-8: 2rem;   --s-12: 3rem; --s-16: 4rem;  --s-24: 6rem;
  --section-y: clamp(3rem, 8vw, 6rem);
  --gutter:    clamp(1rem, 4vw, 2.5rem);
  --max-w:     1200px;

  --radius:    6px;            /* chips, buttons */
  --radius-lg: 12px;           /* cards, panels */
  --shadow:    0 8px 30px rgba(0,0,0,.35);
  /* focus (T11): a 3px solid outline in --cyan (--ink on paper), offset 3px; inset with a --bg band on image buttons and reel dots; no box-shadow ring */
}
```

Light panel (`.paper`): sets `--bg: var(--paper); --bg-2: var(--paper-2); --line: var(--paper-line);
--text: var(--ink); --text-muted: var(--ink-muted);` so components inside inherit without variants. Orange and
cyan keep their values on paper (both pass contrast on #F3EFE6 at the sizes used below; see accessibility).

## Components

| component | notes |
|---|---|
| **Header / nav** | Sticky, `--bg-2`, 72px tall, hairline bottom. Left: logo mark (28px) + wordmark "CAP-VSAR" in `--font-head`. Center/right: the eight nav links; current page underlined in `--orange`. At ≤ 900px a "Menu" button opens a full-height sheet (no hamburger-only icon; the word "Menu"). Skip link "Skip to content" first in DOM. |
| **Hero** | Full-viewport section (min-height 88vh), the H1 animation as an absolutely positioned SVG behind a left-aligned copy column (max 34rem). Copy sits on a translucent `--bg` scrim (`rgba(11,18,32,.72)`) with `backdrop-filter: blur(6px)` fallback-safe. Two buttons. A small mono caption bottom-right: "ESCON · 121.5 MHz · simulated". |
| **Section** | `padding-block: var(--section-y)`; eyebrow (mono, `--cyan`, uppercase, letter-spacing .08em), H2, lede (`--text-muted`, max `--measure`). Alternate dark / paper sections; never two paper sections adjacent (How It's Built was corrected in T11). |
| **Card** | `--bg-2`, hairline, `--radius-lg`, 24px padding; optional icon slot top; title H3; body; optional mono footer line. Grid: `repeat(auto-fit, minmax(240px, 1fr))`. Learning-law cards: a 4px `--orange` left bar and the law's name as the eyebrow. |
| **Callout** | Three tones: `.callout--signal` (orange bar, for "what it is not" / cautions), `.callout--live` (cyan bar, status), `.callout--ok` (green bar). Title + short body; no icons needed. |
| **Figure with caption** | `<figure>` with the image at full column width, hairline frame, `--radius`; `<figcaption>` in `--font-body` small, `--text-muted`, starting with a bold lead ("Mission Base."). Click opens a lightbox (plain JS, Esc closes, focus trapped, `aria-modal`). Every image has alt text written as what a CAP member sees, not "screenshot of". |
| **Reel** | `<figure class="reel">` of ordered `.reel-slide`s (an inline SVG, or a poster `<img>` plus a muted, looping `<video>` with WebM and MP4 sources), `.reel-controls` (Previous, dots, Next; 44px targets; dots carry `aria-current` and the slide's caption as their name), a visually hidden `aria-live="polite"` caption. Styles in `assets/css/reel.css`, behaviour in `assets/js/reel.js`: only the active, on-screen slide plays; cross-fade (0.8 s) after `data-duration` or the figure's `data-interval` (7 s); IntersectionObserver pauses off-screen; the page's Pause control (`body.paused`) pauses every reel; reduced motion and Save-Data show posters only; a slide whose clip is missing keeps its poster (a STILL FRAME badge and a caption note saying the moving clip is not yet available), one with neither is removed; inactive slides are `aria-hidden` and `inert`, each slide is a named group ("Slide n of N"), rotation holds while the pointer or focus is inside, and the live region speaks only after Previous, Next or a dot (T11); `data-require-video` (the Home hero) drops poster-only slides. Captions sit on a dark gradient at the slide's foot; text `#E6ECF2` on ≥ `rgba(11,18,32,.92)`. |
| **Clip** | `<figure class="clip" data-clip="<id>">` with `.clip-stage` (poster + video) and `.clip-controls` (caption, Pause/Play button with `aria-pressed`). Same fallbacks as the reel; a clip with neither file hides itself (`data-state="pending"` keeps it hidden without JS). `.clip-grid` places two side by side. File names: `assets/video/<id>.webm`, `<id>.mp4`, `<id>-poster.webp` (see VIDEO_PLAN.md). |
| **Org-chart node** | 180–220px wide, `--bg-2`, 2px top bar colored by branch (Air Ops `--cyan`, Communications `--orange`, Ground `--green`, Exercise control `--text-muted` dashed), title in `--font-head`, abbreviation chip in mono (`IC`, `AOBD`, `MRO`), screen chip in mono (`/base`), and a hidden "what they do" paragraph revealed on hover/focus/tap (`<details>`-based so it works without JS). Connectors are SVG lines in `--line-strong`; the chart is an SVG at ≥ 900px and a stacked list below. |
| **Spec table** | `--font-mono` for values, `--font-body` for labels; zebra rows at 4% white; sticky first column on narrow screens with horizontal scroll inside a `.table-wrap`. |
| **Button** | Primary: `--orange` fill, `--ink` text, 600 weight, `--radius`, 44px min height. Secondary: 1px `--cyan` outline, `--cyan` text. Hover: 6% lighter; focus: the outline above. Never more than one primary per section. |
| **Status chip** | mono, uppercase: `.chip--proven` (green), `.chip--flown` (cyan), `.chip--planned` (muted outline), `.chip--verify` (orange outline, text "NEEDS EVIDENCE") — the last must not ship on the public site. |
| **Footer** | `--bg-2`, three columns: (1) wordmark + one-line description; (2) the eight nav links + "Exercise guide" + "Source on GitHub"; (3) the disclaimer block (below) and "Not for operational use". Last line: "© 2026 the CAP-VSAR contributors · Apache-2.0 source". |

**Disclaimer block (every page footer, verbatim):**
> CAP-VSAR is an unofficial training project built by Civil Air Patrol members. It is not an official Civil Air
> Patrol product and is not endorsed by Civil Air Patrol. "Civil Air Patrol" and "CAP" identify the organization
> this training is for; no CAP seal, emblem or wing patch is used here. Everything on this site is simulation: it
> is not for real flight planning, real direction finding or a real search.

## Hero animation rules

* SVG + CSS animations only (no canvas, no video): bearing lines are `<line>`s with `stroke-dasharray` reveal;
  the ELT pulse is a `<circle>` scale/opacity keyframe; aircraft move along `<animateMotion>` paths. Total loop
  ~24 s, GPU-cheap (transform/opacity only).
* `@media (prefers-reduced-motion: reduce)`: all animation off; the SVG shows the converged end state.
* A "Pause animation" control (text button, bottom-left of the hero) is always present and keyboard reachable.
* The map art is stylised, not an FAA tile: no attribution problem, no text that could be mistaken for a chart.

## Accessibility

* Contrast (computed, T11): body `--text` on `--bg` 15.7:1; `--text-muted` on `--bg` 7.6:1; `--orange` on `--bg`
  6.5:1 (text ≥ 1rem 600 or chips only); `--cyan` on `--bg` 9.2:1; `--ink` on `--paper` 14.4:1; `--green-deep`
  (#356B2A) on `--paper` 5.6:1; `--orange` on `--paper` 2.5:1 (decorative bars only, never text); `--cyan` on
  `--paper` 1.8:1 (never cyan text or cyan focus rings on paper; use `--green-deep` or `--ink`). Builder verifies
  with a checker before shipping.
* Focus visible on every interactive element (3px outline, see the token note); skip link; landmarks (`header nav main footer`);
  one H1 per page; headings in order.
* Alt text: every figure describes what is shown in CAP terms; decorative illustrations `alt=""` with the
  caption carrying meaning; the org chart SVG has a `<title>` and the stacked list is the accessible version.
* Lightbox and menu: Esc closes, focus returns, `aria-expanded` on toggles.
* Animation respects reduced motion (above); nothing flashes faster than 3 Hz (the ELT blink is 1 per 50 s with a
  0.5 s brighten).
* Mono for callsigns and frequencies, but never for whole paragraphs.

## Mobile rules

* Breakpoints: ≤ 600 (phone), 601–900 (tablet), > 900 (desktop). Base styles are the phone layout.
* 16px side gutter minimum; no horizontal page scroll; tables scroll inside their wrapper.
* Hero copy column full width on phones, the animation lighter (half the aircraft, no ellipse) and the scrim
  solid; the "Pause" control stays.
* Org chart: stacked branch lists on phones (IC, then each branch as a group), SVG chart from 900px up.
* Screenshot strip: horizontal snap-scroll row on phones with 85% width cards; grid on tablet and up.
* Buttons full width on phones; tap targets ≥ 44px.
* Images: `loading="lazy"` below the fold, `width`/`height` set, WebP with PNG fallback, the largest hero-adjacent
  screenshot ≤ 400 KB.

## Files the builder produces

As built (T11, 2026-10-18): `website-next/site/index.html` plus one file per page, `site/assets/css/style.css` (tokens +
components) and `site/assets/css/reel.css`, `site/assets/js/main.js` (menu, lightbox, hero pause, scroller focus) and
`site/assets/js/reel.js` (reels and clips), `site/assets/img/`, `site/assets/video/`, `site/assets/brand/`. No `fonts/`
folder: system font stacks only. Development material (QA scripts, captures, build report) lives in `website-next/dev/`,
outside the web root.
