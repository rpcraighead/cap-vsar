# CAP-VSAR — identity directions

## Recommendation

Choose **A / Bearing**. Two crossing direction-finder bearings meeting at an orange beacon express the simulator's central task: turn a signal into a position. The circular range rings connect directly to the proposed operations-room interface, while the open geometry keeps the beacon and crossing lines recognizable at 32 pixels. It also offers a useful visual vocabulary for maps, briefing panels, and loading states without borrowing official insignia. B / Wing + Pulse is the strongest aviation-first alternative; C / Chart tile emphasizes search planning and works especially well as an application tile.

## Three original directions

| Folder | Mark | Character |
| --- | --- | --- |
| `a-bearing/` | Two concentric range rings, crossing DF bearings, orange beacon | Precise, operational, direct |
| `b-wing-pulse/` | Original asymmetric folded wing above two signal arcs | Airborne, light, energetic |
| `c-chart-tile/` | Rounded chart tile, sparse grid, expanding-square search trace | Methodical, practical, map-led |

These are identity proposals for an unofficial virtual SAR simulator. The wing is an original geometric silhouette; none of the marks contains an official emblem, star, propeller, shield, tri-color device, aircraft likeness, or third-party product mark.

## Colors

| Role | On night | On briefing paper | Use |
| --- | --- | --- | --- |
| Background | `#111C28` | `#F4F1E8` | Charcoal navy / warm briefing paper |
| Wordmark / tagline | `#F4F1E8` | `#111C28` | Primary identity lettering |
| Bearing / wing / search trace | `#72D4DB` | `#176573` | Cyan / deep chart teal |
| Secondary bearing / rings / grid / arcs | `#9CB99F` | `#42694F` | Sectional-chart green |
| Beacon | `#FF8A42` | `#A9410C` | Safety orange / deep signal orange |
| One-color white | `#FFFFFF` | — | Transparent artwork, dark substrate |
| One-color black | — | `#000000` | Transparent artwork, light substrate |

Light artwork uses darker accent equivalents so thin lines remain distinct on paper. The chart grid uses 48% opacity in full color; its one-color variants omit the grid to preserve the search trace at small sizes. White and black artwork uses only the named solid ink plus transparency, with no gray fills. Preview-only surfaces also use `#0B141E`, `#16232F`, and muted interface neutrals; these are presentation chrome, not extra logo colors.

## Clear space and minimum sizes

- Measure using the icon's **128 × 128 unit** drawing grid. Keep at least **12 units** of clear space outside the visible mark or lettering: about 9.4% of the icon canvas width. Increase this to 24 units for prominent hero placements. Do not count a dark or paper background plate as visible artwork when measuring.
- Supplied SVG canvases include the minimum internal breathing room. Retain their view boxes and aspect ratios. The 24-unit corner radius on the full-color icon is a background plate, separate from the chart tile's own outline.
- **Icon minimum: 32 × 32 CSS pixels**, with a native 32-pixel PNG supplied. Use the SVG or a higher-resolution PNG on high-density displays. Below 32 pixels, use a simple orange status dot in the interface rather than shrink the full mark.
- **Wordmark logo minimum: 240 CSS pixels wide.** Choose `logo-*.svg` for navigation bars and compact headers.
- **Tagline lockup minimum: 640 CSS pixels wide** on screen, or approximately 100 mm in print. Below that width, use the logo and place the tagline as ordinary page text. The preview's comparison cards use the logo; its expandable full-size section shows the 728-pixel tagline lockups.
- Avoid adjacent range rings or grid lines within the clear space. In map-heavy layouts, give the logo a solid background panel.

## Lettering and supporting typography

The wordmark is an original condensed geometric alphabet made from filled paths. The exact sentence-case tagline is original monoline path lettering. **Every SVG is self-contained: no `<text>`, embedded raster, font reference, external resource, or script.** The tagline reads:

> Run the whole search before anyone leaves the ground.

For later site work, a condensed placard sans such as Barlow Condensed or Oswald can support headlines, a plain sans can carry body copy, and a monospace face can display frequencies. Those are suggestions only; these deliverables load no fonts. The standalone HTML preview uses the viewer's installed system fonts for explanatory copy. Do not recreate the logo by typing its name in a substitute font.

## Do / don't

| Do | Don't |
| --- | --- |
| Use the matching dark or light asset on its intended background. | Place pale accents on paper, or dark accents directly on a night background. |
| Keep the beacon as the single orange focal point. | Add orange outlines, extra beacons, or competing warning glows. |
| Scale proportionally and preserve spacing. | Stretch, rotate, add shadows, recolor individual letters, or put texture inside the mark. |
| Use white or black artwork for single-ink reproduction. | Treat the full-color artwork as a grayscale conversion. |
| Use icon-only assets for favicons and app tiles. | Squeeze the wordmark or tagline into an icon. |
| Present the simulator as an unofficial training tool. | Add official Civil Air Patrol insignia, wing/star/propeller devices, tri-color shields, or Garmin / X-Plane / Laminar marks. |
| Label simulated instrumentation and training context clearly in the eventual site. | Present the identity as approval, certification, or operational affiliation. |

## Required disclaimer

**Unofficial training tool. Not affiliated with or endorsed by Civil Air Patrol.**

Place this line in the site footer and on downloads or briefing materials near the product identity. It is already included in the preview and each SVG's accessible description; metadata does not replace a visible disclaimer in the eventual site.

## Deliverable map

Open **`preview.html`** directly in a browser. It contains all artwork inline, needs no server or network, compares the three directions on dark and light, shows actual 32-pixel icons and white / black versions, and includes an expandable section with full-size tagline lockups.

Each direction folder has the same structure:

| Filename | Contents |
| --- | --- |
| `logo-dark.svg`, `logo-light.svg` | Full-color mark + CAP-VSAR wordmark, 728 × 192 view box |
| `logo-white.svg`, `logo-black.svg` | Solid one-color logo on transparency |
| `icon-dark.svg`, `icon-light.svg` | Square 128 × 128 icon-only mark with matching background plate |
| `icon-white.svg`, `icon-black.svg` | Square icon-only mark on transparency |
| `lockup-dark.svg`, `lockup-light.svg` | Horizontal mark + wordmark + exact tagline, 728 × 208 view box |
| `lockup-white.svg`, `lockup-black.svg` | Solid one-color horizontal tagline lockup on transparency |
| `png/logo-{variant}.png` | Raster rendering of each logo at 728 × 192 |
| `png/lockup-{variant}.png` | Raster rendering of each tagline lockup at 728 × 208 |
| `png/icon-{variant}-{32,180,512}.png` | Native favicon / touch-icon / app-icon PNG exports |

The four variant names are `dark`, `light`, `white`, and `black`. Total: **36 SVGs + 60 PNG exports**. `export-manifest.json` lists every PNG, its source SVG, and dimensions. `qa-contact-sheet.png` shows all treatments with actual 32-pixel icons; `qa-hero-lockups.png` shows all six full-color tagline lockups at native size.

Rebuild with `python3 website-next/brand/build_brand.py` from the repository root. The generator uses original path geometry, system **librsvg + Cairo** for rasterization, and Pillow for the QA sheets. The `rsvg-convert`, ImageMagick, and Inkscape command-line programs were unavailable, so the same installed librsvg engine is called directly through its C API. A local DejaVu font labels the raster QA sheets only; it is not used by any logo or lockup.

Assumptions: all three directions share a consistent wordmark to make the symbol comparison fair; the dark assets use a solid night panel, and white / black assets use transparent backgrounds. The proposals are static, as requested. Selection and integration into the site are separate from this identity study.
