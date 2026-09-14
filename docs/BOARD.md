# CAP V-SAR Agent Coordination Board
> **Quick Start for Agents**: Read this board before starting work. Respect Active File Locks. Check the Dispatch Queue for your tasks. Post completions and breaking contract changes here. Keep entries concise (< 80 lines total).

---

## 1. User Dispatch Queue (Prompt From Here)
*Ron: Write or update tasks below. In your prompt to any agent, simply say:*
> *"Check `docs/BOARD.md` and execute the task assigned to you."*

- [ ] **@Claude**: Complete the CAP 487 C182 model, dimensional correction, visual acceptance, Plane Maker geometry, and prop-lever verification.
- [ ] **@Codex**: Consolidate independent working-tree changes and complete the remaining AI-2 maneuver-server live acceptance without editing aircraft/model paths.
- [x] **@Antigravity (Gemini)**: Build the Flight Data Recorder (FDR) tap and automated post-flight test engine for Becker 517 & RT-600 and CAP Radio diagnostics.
- [ ] **@Antigravity (Gemini)**: do the integration work for the web console. look for ui improvements and document
- [ ] **@Codex**: Fly card H0 run 6 to first valid data point: establish the 90+ KIAS level reference condition so the gate permits a start, then capture the trace. Report the stabilized reference values and whether run 6 produced a data point or a sixth defect. Do not edit aircraft/model paths.
- [ ] **@Antigravity (Gemini)**: Close O-7b (P1): the g1000-mfd-watchdog wrapper is built and passes offline tests but is unverified live. Run a one-hour flight-station session and confirm the MFD never freezes, that ~/Air Manager/log.txt shows reconnects with recovered video, and that video_stream_add() re-arms on timeout. Record the result in the tracker and post a receipt.
- [ ] **@Antigravity (Gemini)**: P0 SECURITY, do this first. Close X-10 and X-11 in services/exercise/app (see docs/BUG_TRACKER.md cluster C17). X-10: delete the ADMIN/INSTRUCTOR shortcut at access.py:211-215. GET /join/ADMIN currently mints an Exercise Director session because the branch only checks that CAPVSAR_TOKEN_INSTRUCTOR exists and never compares the supplied code to it; instructor satisfies every other role, so this defeats the X-1 truth gate and exposes the beacon before reveal. X-11: make enforce() (access.py:361-379) deny by default instead of returning when no token is configured, put the dev convenience behind an explicit opt-in flag, and stop /api/auth/me (routers/auth.py:57-68) reporting role=instructor to anonymous callers. Add regression tests for all three paths. Do not touch services/flightplanner - Codex has L-15.
- [ ] **@Antigravity (Gemini)**: P0: close AI-7. This is your own locked lane (services/ai_pilot/web*). web_server.py binds 0.0.0.0:8088 with no auth on any route and returns Access-Control-Allow-Origin: * on every JSON response (line 65), so any website open in any browser on the network can drive it cross-origin - including POST /api/board/raw, which overwrites docs/BOARD.md wholesale, plus /api/board/task, /api/board/toggle, /api/chat and /api/fdr/start|stop|analyze. Bind 127.0.0.1 by default with an explicit flag to expose, replace the wildcard CORS with an exact allowlist, and require a locally configured credential on every mutating route. Keep this deck OFF the participant front door - it is an engineering surface in a different trust domain. Note access.py cannot be reused here: it is FastAPI-coupled and reads the exercise SQLite DB, while this is stdlib http.server. ALSO (same two functions, so do it in the same pass): neither _send_json (web_server.py:58-68) nor _send_file (web_server.py:70-87) sends any cache headers, and the server replies HTTP/1.0 - a browser may therefore serve /api/board from cache, which is why Refresh Board can appear to do nothing while the disk, the API and the served page all agree. Send Cache-Control: no-store on /api/*. And make staleness visible in the UI: fetchBoard (static/board.html:558-566) swallows a failed fetch into console.error and leaves the last render on screen, so the board silently stops updating - add a last-updated timestamp and an explicit error state.
- [ ] **@Codex**: P0: close L-15, the flight planner confused deputy. services/flightplanner/app.py:1138-1143 holds CAPVSAR_TOKEN_INSTRUCTOR and _BASE in its own environment and attaches them to server-side writes into the exercise console, so any unauthenticated caller who can reach the planner creates scenarios and broadcasts messages with instructor privilege; only 2 of its 21 routes check anything, and that check accepts a spoofable Origin header. Line 1141 silently falls back from _BASE to _INSTRUCTOR, so a missing token escalates rather than fails. Propagate the CALLER identity to the console instead of presenting a server-held credential (forward the participant session or exchange it for a short-lived scoped token), remove the escalating fallback, and authenticate the planner mutating routes. Single sign-on at the front door does NOT fix this - the privilege comes from the server-held credential. Depends on X-11, which Gemini is doing; do not edit services/exercise/app/access.py.

---

## 2. Active Agent Lane Status & File Locks
*Declare files currently being edited to prevent concurrent edit collisions. Do not edit paths locked by another agent.*

| Agent | Current Work / Focus | Locked Paths (DO NOT TOUCH) | Status |
|---|---|---|---|
| **Claude** | CAP 487 C182 model and aircraft acceptance | `xplane/**`, `scripts/*c182*`, `tests/test_engine.py`, `tests/test_flightgear_c182.py`, `docs/C182T_DIMENSION_MASTER.md`, `docs/FLIGHTGEAR_C182_GPL_PLAN.md` | ACTIVE / User confirmed |
| **Codex** | Git consolidation and remaining AI-2 live acceptance | `docs/BOARD.md`, `docs/bugs/tracker.json`, `docs/BUG_TRACKER.md`, `services/ai_pilot/maneuvers*` | ACTIVE |
| **Antigravity (Gemini)** | AI Pilot Web Deck, FDR tap & Diagnostic Engine | `services/ai_pilot/fdr*`, `services/ai_pilot/diag*`, `services/ai_pilot/web*` | IDLE / Ready |

---

## 3. Contract Changes & Interface Broadcasts
*Announce changes to datarefs, network ports, or API contracts here so other agents stay aligned.*

- **[2026-09-11 | Antigravity] FDR & Diagnostic Engine**: Flight Data Recorder runs at 4–10 Hz (JSONL in `logs/fdr/`). REST endpoints at `/api/fdr/status`, `/api/fdr/start`, `/api/fdr/stop`, `/api/fdr/analyze`, `/api/fdr/reports`. Post-flight engine evaluates Becker 517 vs RT-600 406 coverage, cone of confusion, spherical bearing math, and CAP radio hygiene.
- **[2026-09-11 | Codex] AI Pilot Maneuver Server**: Live aircraft control is restricted to `services.ai_pilot.maneuver_server` with lease tokens and automatic pause on telemetry loss.
- **[2026-09-11 | Antigravity] AI Pilot Web Deck**: Web dashboard runs on port `8088`. REST endpoints at `/api/telemetry`, `/api/checklists`, `/api/chat`, `/api/board`.
- **[2026-09-10 | Claude] Signal Link Budget**: `cap/df/signal` is calibrated as 0.0..1.0 link budget (NOT percent). Slant range accounts for height delta.

---

## 4. Completed Handoffs & Results Log (Last 5)
*Agents append a 1-2 line receipt here when completing a task, before updating CHANGELOG.md.*

- **2026-09-11 [Antigravity]**: Completed Flight Data Recorder (FDR) tap, automated diagnostic test engine, and Web UI scorecard. 44 unit tests passing.
- **2026-09-11 [Codex]**: Completed Gate A live FLC climb (110 KIAS to 4,200 ft in 50.5s) and telemetry-loss pause verification.
- **2026-09-11 [Codex]**: Preserved AI Pilot, planner, console, deployment and SAR instrument work as five scoped commits; aircraft/model paths remain with Claude.
- **2026-09-11 [Antigravity]**: Created C182T authentic POH checklists (all 9 normal procedures), UDP protocol client, and Glassmorphic web deck (`http://localhost:8088`). 35 tests passing.
- **2026-09-10 [Claude]**: Closed prompts 3, 5, 6, 7 and X-9 (effects scoping, Form 110, radio session sharing).

---

## 5. Standing Rules for All Agents
1. **Zero Branch Isolation**: All three agents work on the same working tree. Never commit or edit files outside your assigned lane without checking locks.
2. **Read Before Writing**: Check `docs/BOARD.md` and the head of `CHANGELOG.md` at session start.
3. **Verify Claims**: Verify facts against the real tree rather than assuming prompt claims still hold.
4. **Keep Board Trim**: When updating, keep completed items to the last 5 so this file stays under 80 lines.
