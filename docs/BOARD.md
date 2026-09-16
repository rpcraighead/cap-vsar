# CAP V-SAR Agent Coordination Board
> **Quick Start for Agents**: Read this board before starting work. Respect Active File Locks. Check the Dispatch Queue for your tasks. Post completions and breaking contract changes here. Keep entries concise (< 80 lines total).

---

## 1. User Dispatch Queue (Prompt From Here)
*Ron: Write or update tasks below. In your prompt to any agent, simply say:*
> *"Check `docs/BOARD.md` and execute the task assigned to you."*

**Pending**

- [ ] **@Claude**: Complete the CAP 487 C182 model, dimensional correction, visual acceptance, Plane Maker geometry, and prop-lever verification.
- [ ] **@Codex**: Consolidate independent working-tree changes and complete the remaining AI-2 maneuver-server live acceptance without editing aircraft/model paths.
- [ ] **@Codex**: Fly card H0 run 6 to first valid data point: establish the 90+ KIAS level reference condition so the gate permits a start, then capture the trace. Report the stabilized reference values and whether run 6 produced a data point or a sixth defect. Do not edit aircraft/model paths.
- [ ] **@Antigravity (Gemini)**: do the integration work for the web console. look for ui improvements and document
- [ ] **@Antigravity (Gemini)**: Close O-7b (P1): the g1000-mfd-watchdog wrapper is built and passes offline tests but is unverified live. Run a one-hour flight-station session and confirm the MFD never freezes, that ~/Air Manager/log.txt shows reconnects with recovered video, and that video_stream_add() re-arms on timeout. Record the result in the tracker and post a receipt.

**Closed** (full detail in the tracker and CHANGELOG; receipts in section 4)

- [x] **@Antigravity (Gemini)**: Build the Flight Data Recorder (FDR) tap and post-flight diagnostic engine. DONE.
- [x] **@Claude**: P0 X-10, X-11 — instructor backdoor closed, `enforce()` no longer fails open. DONE `944f093`.
- [x] **@Codex JOB A**: P0 L-15 — planner forwards the caller identity instead of its own instructor token. DONE `0705780`.
- [x] **@Codex JOB B**: P0 AI-7 — AI Pilot deck is loopback by default, credentialed writes, no-store on `/api/*`. DONE `4fec7b4`.
- [x] **@Codex JOB C**: P1 X-12, X-13, X-14 — session, badge and radio-net hardening. DONE `5cadad0`.
- [x] **@Codex**: P0 O-8 — participant apps behind one HTTPS front door, live on ms01. DONE `472d3bb`, `43f2267`.

---

## 2. Active Agent Lane Status & File Locks
*Declare files currently being edited to prevent concurrent edit collisions. Do not edit paths locked by another agent.*

| Agent | Current Work / Focus | Locked Paths (DO NOT TOUCH) | Status |
|---|---|---|---|
| **Claude** | CAP 487 C182 model and aircraft acceptance | `xplane/**`, `scripts/*c182*`, `tests/test_engine.py`, `tests/test_flightgear_c182.py`, `docs/C182T_DIMENSION_MASTER.md`, `docs/FLIGHTGEAR_C182_GPL_PLAN.md` | ACTIVE / User confirmed |
| **Codex** | Next: H0 run 6; AI-2 live acceptance | — | IDLE / Ready |
| **Antigravity (Gemini)** | Next: O-7b live MFD watchdog verification; web console UI pass | `services/ai_pilot/fdr*`, `services/ai_pilot/diag*`, `services/ai_pilot/web*` | IDLE / Ready |

---

## 3. Contract Changes & Interface Broadcasts
*Announce changes to datarefs, network ports, or API contracts here so other agents stay aligned.*

- **[2026-09-11 | Antigravity] FDR & Diagnostic Engine**: Flight Data Recorder runs at 4–10 Hz (JSONL in `logs/fdr/`). REST endpoints at `/api/fdr/status`, `/api/fdr/start`, `/api/fdr/stop`, `/api/fdr/analyze`, `/api/fdr/reports`. Post-flight engine evaluates Becker 517 vs RT-600 406 coverage, cone of confusion, spherical bearing math, and CAP radio hygiene.
- **[2026-09-11 | Codex] AI Pilot Maneuver Server**: Live aircraft control is restricted to `services.ai_pilot.maneuver_server` with lease tokens and automatic pause on telemetry loss.
- **[2026-09-13 | Codex, supersedes 2026-09-11] AI Pilot Web Deck**: Engineering deck on `8088` is now **loopback-only by default** — `--expose` is required for a network bind, mutating routes require `CAPVSAR_AI_PILOT_TOKEN` (Bearer), browser origins must be listed with `--allow-origin`, and `/api/*` sends `Cache-Control: no-store`. REST at `/api/telemetry`, `/api/checklists`, `/api/chat`, `/api/board`, `/api/fdr/*`. This deck stays OFF the participant front door (different trust domain).
- **[2026-09-10 | Claude] Signal Link Budget**: `cap/df/signal` is calibrated as 0.0..1.0 link budget (NOT percent). Slant range accounts for height delta.
- **[2026-09-14 | Codex] O-8 front door**: Participant web traffic is Caddy 80/443 only; apps share `https://192.0.2.151/`, planner is `/planner/`, and backend 8700/8090 are private.

---

## 4. Completed Handoffs & Results Log (Last 5)
*Agents append a 1-2 line receipt here when completing a task, before updating CHANGELOG.md.*

- **2026-09-15 [Claude]**: `pytest` at the repo root collected nothing (SystemExit during import aborted the run). Guarded the four script-style files in `tests/` and scoped collection to `tests/` via `pytest.ini`. One command now runs the whole suite: 227 passed, 1 skipped, 23 subtests.
- **2026-09-14 [Codex O-8]**: Single HTTPS portal deployed on ms01; one roster login reached portal/base/planner, 8700/8090 refused, plugin HTTPS passed, and full preflight passed. Tests: planner 93+17 subtests, auth 38+6, radio 21.
- **2026-09-13 [Codex JOB B]**: AI-7 implementation complete: loopback default, explicit --expose/--allow-origin, CAPVSAR_AI_PILOT_TOKEN bearer writes, API no-store, board timestamp/error state; engineering only. Pytest: 88 passed + 9 subtests (temporary security/UI harness), 4 socket setups blocked by sandbox; legacy POST tests need credential fixtures outside this lane. 8088 NOT killed/restarted: restart with local token required to activate protection; changes uncommitted for Claude review.
- **2026-09-13 [Codex JOB C]**: Closed X-12/X-13/X-14: Secure cookies, no JSON/query session secrets, CSRF-confirmed joins, 128-bit badge suffixes, hashed/pruned/revoked sessions, base/instructor ICS gate; pytest 58 passed (37 auth + 21 radio), 6 subtests, using /tmp/capvsar_test_wakeup.py for sandbox TestClient wakeup hang; HTTPS and badge reissue required, old sessions revoked; working tree only, no restart.
- **2026-09-13 [Codex JOB A]**: Closed L-15 in flightplanner: caller-only console credentials, instructor validation on mutations, no escalating fallback, fail-closed auth/redirects; planner pytest: 88 passed + 17 subtests. Working tree only; no services restarted; browser sessions require shared origin.
- **2026-09-13 [Claude]**: Closed X-10 and X-11 (944f093). /join/ADMIN no longer mints an Exercise Director session, and enforce() denies instead of failing open. 140 tests, 23 subtests.

---

## 5. Standing Rules for All Agents
1. **Zero Branch Isolation**: All three agents work on the same working tree. Never commit or edit files outside your assigned lane without checking locks.
2. **Read Before Writing**: Check `docs/BOARD.md` and the head of `CHANGELOG.md` at session start.
3. **Verify Claims**: Verify facts against the real tree rather than assuming prompt claims still hold.
4. **Keep Board Trim**: When updating, keep completed items to the last 5 so this file stays under 80 lines.
