# Remediation plan

Companion to [`BUG_TRACKER.md`](BUG_TRACKER.md) (67 items, generated from
`docs/bugs/tracker.json`) and the analysis it came from,
[`PROJECT_REVIEW_2026-09-08.md`](PROJECT_REVIEW_2026-09-08.md).

**Status: plan, not work. Nothing in the tracker is fixed yet.**

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

`O-1`. Codex is mid-flight on this: `.gitignore` landed at 17:22 today and
covers the artifacts the review flagged. Remaining: finish the Gitea/GitHub
push and **install `git` on this machine** so every agent can diff before it
edits. Right now no agent can see what another changed.

**Exit test:** `git log` shows history in this tree; `git status` is clean.

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
