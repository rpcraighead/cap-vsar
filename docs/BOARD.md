# CAP V-SAR Agent Coordination Board
> **Quick Start for Agents**: Read this board before starting work. Respect Active File Locks. Check the Dispatch Queue for your tasks. Post completions and breaking contract changes here. Keep entries concise (< 80 lines total).

---

## 1. User Dispatch Queue (Prompt From Here)
*Ron: Write or update tasks below. In your prompt to any agent, simply say:*
> *"Check `docs/BOARD.md` and execute the task assigned to you."*

- [ ] **@Claude**: Complete the CAP 487 C182 model, dimensional correction, visual acceptance, Plane Maker geometry, and prop-lever verification.
- [ ] **@Codex**: Consolidate independent working-tree changes and complete the remaining AI-2 maneuver-server live acceptance without editing aircraft/model paths.
- [x] **@Antigravity (Gemini)**: Build the Flight Data Recorder (FDR) tap and automated post-flight test engine for Becker 517 & RT-600 and CAP Radio diagnostics.

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
