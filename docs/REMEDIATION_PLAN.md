# Remediation plan

Companion to [`BUG_TRACKER.md`](BUG_TRACKER.md), generated from
`docs/bugs/tracker.json`, and the analysis it came from,
[`PROJECT_REVIEW_2026-09-08.md`](PROJECT_REVIEW_2026-09-08.md).

> **Status as of 2026-09-13: mostly done, and this file is the plan, not the
> record.** `docs/bugs/tracker.json` is the source of truth for what is fixed.
> It now holds **101 items, 18 open** — the original 67 plus items found while
> working, including the eight identity and access findings in cluster C17.
>
> This document froze on 2026-09-08 and said "nothing in the tracker is fixed
> yet", which stopped being true almost immediately. The wave structure and its
> reasoning below are still the plan of record and worth reading; the item
> counts and the "nothing is fixed" framing are not. Where the two disagree,
> the tracker wins.
>
> | Wave | Closed | Still open |
> |---|---|---|
> | 0 — make the work safe | 3 / 8 | `X-12`, `X-13`, `X-14`, `L-15`, `AI-7` (all C17) |
> | 1 — session 1 can run | 10 / 11 | `O-8` |
> | 2 — session 2, full mission | 19 / 20 | `O-7b` |
> | 3 — dress rehearsal and live day | 33 / 41 | `A-1`, `AI-2`, `AI-4`, `D-5`, `F-8`, `F-10`, `F-11`, `L-7a` |
> | 4 — after the SAREX | 18 / 21 | `F-12`, `F-13`, `L-10` |
>
> **The critical path in §2 below is closed.** `O-1` (git), `X-1`/`P-2` (the
> truth serializer and the plugin's keyed route), `X-2` (RBAC), `O-2` (station
> identity), `P-1` (the terrain ray) and `L-2` (the authed planner push) are all
> fixed. Wave 0 reopened later, on 2026-09-13, because the identity audit found
> access-control defects the original review had not: `X-10` and `X-11` are now
> fixed, and the five above are not.
>
> Two caveats the table cannot carry. `A-1`'s flight-model corrections are
> verified statically only — correct values confirmed by dataref after reload,
> none verified in flight. And `D-5` gates any public push: manufacturer artwork
> is still in git history, which `git rm --cached` did not rewrite.

## 1. How this is ordered

Two axes, and they disagree in useful ways:

- **Severity** is what the review measured: how broken a thing is.
- **Waves** are what the schedule demands: what has to work by the next
  rehearsal session in [`USE_CASE_SAREX_REHEARSAL.md`](USE_CASE_SAREX_REHEARSAL.md).

Where they disagree, the wave wins. `O-5` (Mumble ACLs) is a high-severity
security gap but nothing in session 1 or 2 needs it, so it sits in wave 3.
`L-1` (broken `.fms` export) is one severity step lower but the AOBD exports
flight plans in session 1, so it is wave 1. Fix what the next session needs.

The wave dates are anchored to the illustrative calendar in the use case
(T-14 / T-7 / T-2 before a 17 Oct 2026 SAREX). **Re-anchor them to the real
exercise date before using this as a schedule.**

## 2. The critical path

Everything else can move. This cannot:

```
O-1  git works
  └── X-1  truth serializer ──┬── P-2  plugin truth endpoint ── O-2  station identity ── 3 aircraft
      X-2  role tokens ───────┘                                      │
                                                                     └── L-2  authed planner push
  P-1  terrain ray  (independent, one line, do it first)
  O-3  bootstrap ── O-4  Mumble channels ── F-5  CA cert ── radio works on exercise day
```

`X-1` and `P-2` are the same piece of work seen from two ends: one filter that
hides truth from people, one endpoint that gives it to the plugin. Doing them
apart means writing the serializer twice. `X-2` shares the same file and the
same middleware, so it belongs in the same PR. That PR is the single most
important change in this program — do it once, carefully, with tests.

## 3. Waves

Each wave has an exit test. Do not start the next wave until the current one
passes its test, because every later wave assumes it.

### Wave 0 — make the work safe (now, ½ day)

`O-1` is **done**: git works, history is in the tree, and every agent can diff
before it edits.

Wave 0 then **reopened on 2026-09-13**, which is worth recording because of why.
The original review read the console's access control as present but
unconfigured (`X-2`, closed by the RBAC system). An identity audit run against
the working tree found that it was not merely unconfigured — it was bypassable.
`X-10` accepted the literal codes `ADMIN` and `INSTRUCTOR` as participant codes
whenever an instructor token existed, without ever comparing the caller's input
to it, so `GET /join/ADMIN` returned an Exercise Director session to anyone who
could reach the console; and because instructor satisfies every other role, that
also defeated `X-1`, the truth gate the whole teaching mechanism rests on.
`X-11` was the matching fail-open: a missing token opened an endpoint instead of
closing it, and `.env.example` shipped every token blank.

Both are fixed. The lesson for the rest of this plan is that "a control exists"
and "a control holds" are different claims, and only the second is worth an exit
test.

Still open in wave 0, all cluster C17: `X-12` (session cookie without `Secure`,
session id returned to JavaScript, a `GET` that creates a session), `X-13`
(guessable roster codes, unhashed sessions, no revocation on roster
regeneration), `X-14` (`POST /api/radio/ics` ungated), `L-15` (the planner
performs console writes with a server-held instructor credential), and `AI-7`
(the AI Pilot deck on `0.0.0.0:8088` with no auth and wildcard CORS).

**Exit test:** `git log` shows history in this tree and `git status` is clean —
both hold. For the C17 items: no unauthenticated caller can obtain a privileged
session, cause a console write, or read beacon truth before reveal, demonstrated
by running the attack rather than by reading the code.

### Wave 1 — session 1 can run (10 items, ~4 days)

Nothing flies in session 1, but the base, the planner and the voice net must
work, and the truth model has to hold from the start — a leak discovered in
session 2 invalidates session 1's training.

| Cluster | Items | Why now |
|---|---|---|
| C2 Truth & roles | `X-1`, `P-2`, `X-2` | The whole teaching mechanism, plus the plugin is deaf without it |
| C3 (partial) | `P-1` | One line; terrain masking is inverted until it lands |
| C5 Bootstrap | `O-3`, `O-4`, `F-5` | Nobody can stand up a stack or join a net without these |
| C6 Offline | `F-1` | Trivial, and a base with no internet has no base view |
| C4 Station kit | `O-2` | Three stations exist only on paper until this lands |
| C10 (partial) | `L-1` | The AOBD exports `.fms` in session 1 |

**Exit test:** a clean clone plus bootstrap brings up all four services; three
stations with different `station.ini` files show as three aircraft on `/base`;
an unrevealed sortie leaks no coordinate from any endpoint while the cockpit DF
still works; an exported pattern loads in X-Plane 12; the MRO joins each of the
four nets from a tablet.

### Wave 2 — session 2, full mission (17 items, ~5 days)

Session 2 is three aircraft airborne with effects injected and a debrief that
has to mean something.

| Cluster | Items | Why now |
|---|---|---|
| C3 Engine | `P-3`, `P-4`, `P-5` | The injected effects are the lesson; TIMEHOLD and radio horizon are wrong |
| C7 Console | `X-3`, `X-4`, `X-5`, `X-7` | Restart, slow client or a SQLite fsync each break a live exercise |
| C8 Debrief | `F-2`, `F-3` | Three-aircraft debrief is meaningless until tracks are grouped |
| C9 Radio | `F-4` | A Wi-Fi blip silently drops the base station off the net |
| C10/C11 Planner | `L-2`, `L-3`, `L-4` | Retasking mid-flight uses the push path |
| C12 Instruments | `I-1`, `I-2`, `O-7b` | CPU headroom, real errors visible, MFD stays live for an hour |
| C5 Ops | `O-6` | First session where losing the record would actually cost something |

**Exit test:** a 90-minute three-aircraft sortie with all six effects injected,
a mid-exercise container restart, and a debrief that produces per-aircraft CPA
and bearing error — with the Form 110 and the bearing log intact.

### Wave 3 — dress rehearsal and live day (25 items, ~6 days)

Fidelity, offline operation, and the paperwork the SET and the MRO need.

Highlights: `F-9` (Form 110 on the Mumble console, then retire
`/radio-legacy`), `L-8` (offline planner maps), `L-5`/`L-6`/`L-7` (coverage
maths, performance tables, and the 172S-data-under-a-182T-label bug),
`I-3`–`I-6` (instrument behaviour including the missing electrical bus),
`O-5`/`O-7a` (voice ACLs, licence confirmation), `D-1`–`D-4` (the record,
including a LICENSE now that this is going public), and `X-6`/`X-8` (console
hygiene).

**Exit test:** the dress rehearsal runs start to finish with the base's
internet unplugged, and produces a Form 110, a debrief export and a clean
preflight check.

### Wave 4 — after the SAREX (14 items)

Architecture (`C15-1` console split, `C15-2` geodesy consolidation), the Lua
execution harness (`I-9a`), contract corrections (`P-10`, `P-11`), realism
(`P-13`), and then CalTopo phase 2 per
[`CALTOPO_PHASE2_PLAN.md`](CALTOPO_PHASE2_PLAN.md) — which depends on `X-1`,
`O-2` and the `tracking` router from `C15-1`, so it genuinely cannot start
earlier.

## 4. Working it with three agents

The repo has three AI tools and a human in it. The tracker's cluster owner
hints exist because of that; two agents in `main.py` at once will produce
exactly the silent divergence the changelog convention was built to prevent.

- **One cluster, one agent, one PR.** Clusters are drawn so they don't share
  files. The two exceptions are called out: **C2 must land before C7** (both
  are `main.py`), and **C10 before C11** (both are `app.py`).
- **Codex keeps the radio.** It wrote `radio.py`, `mission-radio.js` and the
  worklets and has the most context; `C9` and the radio half of `C5` are its
  natural lane.
- **The plugin is a single file with no other writers**, so `C3` and `C4` can
  run fully parallel to anything in the console.
- **Docs clusters (`C14`) are safe in parallel** with everything.
- Every merged cluster gets a CHANGELOG entry naming the tracker IDs it
  closes, and the JSON's `status` field moves to `fixed`. That is how the next
  agent knows without re-reading the code.

## 5. Verification, not assertion

The review found several changelog claims that the code contradicted, so each
tracker item carries a **Done when** line that is a test, not an opinion.
Three of them should become permanent regression tests, because they are the
failures that would otherwise recur silently:

1. **Truth leak test** — with a running unrevealed sortie, no GET response
   from any endpoint contains a coordinate within 100 m of the beacon. Run it
   against every new endpoint, including the CalTopo relay later.
2. **Non-flat terrain test** — a ridge stub at 30/60/90 % of path, asserting
   blocked and clear in both directions. `tests/xp.py` returns one constant
   height today, which is why `P-1` survived.
3. **Preflight smoke script** — `/api/health`, Mumble channels present, tiles
   reachable, CA cert served. Run before every session, not just the live day.

There is no test coverage at all on `main.py` today, so wave 1 should add the
first one alongside the serializer.

## 6. Effort summary

| Wave | Items | Rough effort | Gate |
|---|---|---|---|
| 0 | 1 | ½ day | git works |
| 1 | 10 | ~4 days | Session 1 can run |
| 2 | 17 | ~5 days | Session 2 can run |
| 3 | 25 | ~6 days | Dress rehearsal + live day |
| 4 | 14 | ~6 days + CalTopo | Post-exercise |

Waves 0–2 — the point at which a three-aircraft rehearsal is genuinely
possible — are about **nine to ten focused days**. That is the number worth
planning around; waves 3 and 4 can absorb slip without cancelling anything.
