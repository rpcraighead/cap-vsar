# Design decisions — 2026-10-11 (UX)

Decided by Claude (Fable) for the proposal in
[`UX_REVIEW_2026-10-11.md`](UX_REVIEW_2026-10-11.md); Ron can overturn any of
them. Same format as [`DECISIONS_2026-10-10.md`](DECISIONS_2026-10-10.md). D5
settles the seat model, D6 the design tokens and the shell. Both exist so that
the Ready room reference screen and the phase 1–3 build do not each invent
their own.

---

## D5. Seats are the unit of membership; roles stay the permission class

### The decision

1. **Ten seats, one table.** `access.SEATS` is the single list: `director`,
   `ic`, `aobd`, `mro`, `evaluator`, `pilot`, `observer`, `scanner`, `udf`,
   `station`. Each row gives the role class it maps to, the landing page, and
   whether the seat belongs to an aircraft (`pilot`, `observer`, `scanner`,
   `station`), a ground team (`udf`) or the base. Nothing else in the code
   enumerates seats.

   | Seat | Role class | Lands on | Belongs to | Net callsign |
   |---|---|---|---|---|
   | director | instructor | `/ready` → `/instructor` | exercise | INSTRUCTOR |
   | ic | base | `/ready` → `/base?mode=ic` | base | MISSION BASE |
   | aobd | base | `/ready` → `/base?mode=aobd` | base | MISSION BASE |
   | mro | base | `/ready` → `/radio` | base | MISSION BASE |
   | evaluator | evaluator (new) | `/ready` → `/debrief` | exercise | — |
   | pilot | aircrew | `/ready` → station page | aircraft | the aircraft's |
   | observer | aircrew | `/ready` → station page | aircraft | the aircraft's |
   | scanner | aircrew | `/ready` → station page | aircraft | the aircraft's |
   | udf | ground_team | `/ready` → `/radio` | ground team | UDF n |
   | station | plugin | — (non-human) | aircraft | — |

2. **A membership is a roster row with a seat.** The `roster` table grows
   `seat`, `exercise_id`, `status` (`invited` / `accepted` / `revoked`),
   `expires`, `short_code`, and keeps `code` as the link token. Rows that
   predate the column get their seat from `access.seat_of(row)`, which
   derives it from `title`/`assigned_name` (the same heuristic the radio's
   `classify_crew` uses today), so nothing breaks on an existing database.
3. **Two credentials per seat.** A **short code**: six characters from the
   Crockford base32 alphabet without I, L, O and U, unique within the
   exercise, typeable on a phone, accepted by `/login` with a rate limit of
   five attempts per minute per address. A **link token**: the existing
   32-hex value, carried only by the QR and the copy-link, consumed through
   `/join/{token}`. The short code never appears in a URL.
4. **Role is resolved per request, from the membership.** A session stores
   the membership id; `get_session_from_request()` joins to the roster row
   and returns its current seat, role, callsign and aircraft. Revoking a
   membership therefore ends access on the next request, including open
   sockets at their next message. Nothing copies a role into the session and
   trusts it later (the identity plan's rule).
5. **`evaluator` is a real role: read-only.** `SATISFIED_BY["evaluator"] =
   ("evaluator", "instructor")`; it satisfies every `any_role` read and the
   debrief, and no mutation. It sees truth only after reveal, exactly like
   base. This resolves the user stories' Open Question 1.
6. **IC, AOBD and MRO share the `base` role.** The seat drives the landing
   page and the base page's default mode; it grants nothing extra. This
   resolves Open Question 2 as the stories recommended. The radio's
   pilot/observer classification reads the seat, not the name, which also
   closes the X2-13 residual once radios are keyed by membership.
7. **An `exercises` row exists now.** `id`, `name`, `date`, `status`,
   `created`. Memberships reference it. One active exercise at a time remains
   the scope; the foreign key is designed in now so past exercises can be
   kept and a director sees only the exercises they are a member of (Open
   Question 3). The environment instructor token stays as the break-glass
   platform credential and is not a membership.
8. **Scanner is a seat** (Open Question 4): it has no system interaction,
   but the roster, the badge sheet and the presence board must show the
   whole crew.
9. **Callsigns follow the seat.** Aircraft seats inherit the aircraft's
   callsign; base seats are `MISSION BASE` on the net, with the seat shown
   in the console; UDF seats are `UDF n`. The join form never asks for a
   callsign.
10. **Presence is a record per membership**, kept in the hub:
    `{membership_id, seat, page, last_seen, on_net, station_seen, checks}`.
    Sources: the WebSocket session (page and last_seen), the radio's session
    table (on_net, matched by callsign today and by membership later), the
    plugin's reports (station_seen, DF power, head type), and self-reported
    checks posted by the participant's page. The Ready room reads it through
    `/api/ready`; the events stream (UX phase 1) will carry its changes.
11. **Readiness checks are defined per seat kind**, computed on the server:

    | Check | Seats | Source | State when unknown |
    |---|---|---|---|
    | joined | all | a session has been seen for the membership | — |
    | on net | base, aircrew, udf | radio session with the seat's callsign | pending |
    | mic | base, udf, mro | self-reported after the headset test | pending |
    | station | aircraft | plugin position for the aircraft within 10 s | pending |
    | DF head | observer | plugin `df.power` with a known `head_type` | pending |
    | briefing | all human seats | self-reported acknowledgement | pending |
    | pattern | pilot | assignment attached to the aircraft (phase 1) | not reported |

    A tile is **ready** when every check that applies is ok; **stale** when the
    station or socket was last seen 10–60 s ago; **lost** beyond 60 s;
    **flying** once the sortie is running and the station reports.

### Why

- The stories describe nine human seats and the running system has five
  roles; every gap in the review's "who is here" section comes from that
  mismatch. Adding seats as data, not as roles, gives the UI what it needs
  without widening any permission.
- Short codes are the only way a badge works without a camera; six Crockford
  characters give 1.07 billion combinations per exercise, enough against a
  rate limit for a roster of tens.
- Per-request resolution is what makes revocation and expiry real; the
  identity plan already requires it.

### What changes where (UX phase 1)

`access.py` (SEATS, `seat_of()`, roster and exercises columns, short code,
per-request resolution, evaluator in SATISFIED_BY and ROLES), `models.py`
(setup payload takes seats), `routers/auth.py` (`/login` short code, join
page as a boarding pass), `routers/ready.py` (new; the Ready room API is
already written against the derived seat), `radio.py` (seat-based crew
classification), `static/setup.*` (seat roster and badge sheet).

## D6. Design tokens and the shell

### The decision

1. **One token file.** `services/exercise/app/static/tokens.css` is the only
   place a colour, font, size, spacing step, radius, z-index or motion value
   is defined. The planner carries a byte-identical copy at
   `services/flightplanner/static/css/tokens.css`; a test asserts equality.
   Pages use tokens by name and never a literal.
2. **Dark by default, light by choice.** `<html>` is dark; `data-theme="light"`
   switches the surfaces and ink. The sim room and the base at night are
   dark; the printable things (badges, ICS forms, the debrief PDF) are
   light by their print stylesheet.
3. **Surfaces are navy-tinted neutrals, not brand blue.** Page `#0e1117`,
   surface `#161b22`, nested `#1d242e`, hairline `#2a3340`; ink `#e6ebf2`,
   secondary `#b7c1cf`, muted `#8b97a8`. Brand lives in the accent (steel
   blue on dark, CAP blue `#2e5496` on light) used for links, focus and the
   selected tab; primary buttons are ink-filled so hue is free for data.
4. **Hue carries identity only for aircraft and status.** Aircraft 1–4 take
   the validated categorical slots in fixed order (`--ac-1..4`: blue,
   orange, aqua, yellow; dark and light values from the dataviz reference
   palette, validated against these surfaces); the same slot colours the
   marker, the track, the card and the chart series. Status is the reserved
   quartet `--good --warning --serious --critical` plus `--info`, always with
   an icon or word. **`--truth`** (magenta) is reserved for the beacon and
   anything derived from it after reveal and is used nowhere else, so a
   magenta mark on any screen means "this is the answer".
5. **Type.** IBM Plex Sans for interface, JetBrains Mono for data
   (callsigns, bearings, times, codes); both already vendored under the
   Open Font License and served locally, never from Google. Scale 12 / 13 /
   14 / 16 / 20 / 28 / 44. Tabular numerals on anything that updates.
6. **Space and shape.** A 4-px scale (4, 8, 12, 16, 24, 32), radius 6 (cards
   10), hairline borders instead of shadows, 44-px minimum touch targets on
   anything a tablet operator presses.
7. **Breakpoints and density.** 600 (phone), 1100 (tablet: sidebars become
   a single column; the shell hides link dots), 1900 (wall: type scales
   1.5× automatically; `data-density="wall"` forces it). Reduced motion is
   honoured.
8. **The shell** (`shell.css`, `shell.js`): one sticky header on every stage:
   brand · exercise name and state · stage tabs for the viewer's role (seat
   later) · spacer · `EXERCISE · NOT A REAL DISTRESS` · link dots (console,
   net; station on aircrew pages) · Zulu clock · identity chip (initials,
   title, callsign; click to sign out). It is built with `textContent` only.
   Pages opt in with `<header id="shell"></header>` and `mountShell()`. The
   Ready room is the first page on the shell; the other pages migrate in UX
   phase 3 and keep their own headers until then.
9. **Component set**, all in `shell.css`: card, panel, pill, dot, button
   (primary / secondary / danger / big), field, tile grid (presence),
   log list, key-value list, toast, two-column page. Anything a phase-1
   screen needs beyond these is added to `shell.css`, not to the page.
10. **Map colours** are tokens too (`--map-track`, `--map-bearing`,
    `--map-cut`, `--map-alert`, `--map-assign`), so Leaflet styling on every
    page agrees.

### Why

- The review counted three visual systems; the cheapest fix is one token
  file and one header, not a framework.
- Reusing the validated palette means the chart work (Opus) and the map
  work agree without another validation pass; the one new colour, truth
  magenta, is far from every slot.
- Dark-first follows the only page people liked, the radio.

### What changes where

`static/tokens.css`, `static/shell.css`, `static/shell.js`,
`static/vendor/fonts/` (this commit); `services/flightplanner/static/css/tokens.css`
copy and its equality test (phase 1); every other page in phase 3.
