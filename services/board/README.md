# Agent Coordination Board (`services/board`)

The Claude / Codex / Antigravity dispatch board, as its own container, so it is
reachable from any machine on the lab network instead of only from the
workstation.

## Why this exists

The board was four routes bolted onto the AI Pilot deck
(`services/ai_pilot/web_server.py`). That deck imports the X-Plane UDP client,
the flight controller and the C182 checklists, so it can only run on the
workstation sitting next to X-Plane — which meant the board could only be
opened there. This service is the board and nothing else: it parses and writes
`docs/BOARD.md`, and has no simulator dependencies at all.

## What it is not

**It is not the dispatcher.** `scripts/dispatch_board.py` runs the queued prompt
through each agent's headless CLI, and those CLIs live on the workstation with
their own credentials and sandboxes, editing a shared working tree under the
board's path-lock rules. That stays where it is. This container gives you the
*queue* over the network; starting an agent is still done where the agent runs.

**It is not participant-facing.** The board carries the lane locks, every
dispatch prompt and every handoff. It is an engineering surface in a different
trust domain from the exercise console, which is why Caddy serves it on its own
`8443` listener and never from the participant front door on `443`.

## How the board stays one board

`docs/BOARD.md` is a file in this repository, read by agents from their own
checkouts. If this container wrote to a private volume the two would drift
apart within the hour. So it keeps a git working clone of its own:

- a read pulls (`--ff-only`, coalesced to at most one pull per
  `CAPVSAR_BOARD_PULL_INTERVAL` seconds, default 15);
- a write pulls, edits, then commits **only `docs/BOARD.md`** and pushes, with
  one rebase-and-retry if someone else pushed in between.

Every failure is reported in `/api/board` under `sync` and shown in the page
header. A board that has quietly stopped syncing must not look like a board
nobody wrote to.

The commit stages a single explicit pathspec, never `-A`: agents leave work in
progress in their trees and a board edit must not sweep it up.

## One-time setup on ms01

1. **Give the board a clone of its own.** Never point it at an agent's live
   working tree — it commits and pushes.

   ```bash
   cd /srv/capvsar                     # wherever the stack is checked out
   git clone ssh://git@192.0.2.121:2222/ron/capvsar.git services/board/repo
   ```

2. **Create a Gitea deploy key with write access** for `ron/capvsar`, and put
   the private half where compose expects it:

   ```bash
   mkdir -p services/board/secrets && chmod 700 services/board/secrets
   ssh-keygen -t ed25519 -N '' -C 'capvsar-board' -f services/board/secrets/id_ed25519
   ssh-keyscan -p 2222 192.0.2.121 > services/board/secrets/known_hosts
   # then add services/board/secrets/id_ed25519.pub to the repo's deploy keys,
   # with "Enable write access" ticked
   ```

   Both paths are gitignored. `StrictHostKeyChecking` stays on — this key can
   write to the monorepo.

3. **Set the write credential** in `.env`:

   ```bash
   echo "CAPVSAR_BOARD_TOKEN=$(openssl rand -hex 24)" >> .env
   ```

   Leaving it unset does not open the board up — every mutating route returns
   `503` and the service says so at startup and in `/api/health`.

4. **Build and start:**

   ```bash
   docker compose up -d --build board radio-https
   ```

5. **Verify** — from another machine on the LAN:

   ```bash
   curl -sk https://192.0.2.151:8443/api/health
   # {"status":"ok","board_present":true,"git_sync":true,"writes_enabled":true}
   ```

   Then open `https://192.0.2.151:8443/` and check the header reads
   **Git: in sync**. Tick a task and confirm the commit lands in Gitea.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `CAPVSAR_BOARD_TOKEN` | *(unset)* | Bearer credential for every write. Unset ⇒ all writes `503`. |
| `CAPVSAR_BOARD_ORIGINS` | *(empty)* | Exact browser origins allowed to write cross-origin. Empty ⇒ same-origin only. |
| `CAPVSAR_BOARD_REPO` | `/repo` | The git working clone inside the container. |
| `CAPVSAR_BOARD_FILE` | `docs/BOARD.md` | Board path relative to the clone; also the `git add` pathspec, so it must stay relative. |
| `CAPVSAR_BOARD_GIT_SYNC` | `1` | `0` turns the service into a plain file editor (what the tests use). |
| `CAPVSAR_BOARD_PULL_INTERVAL` | `15` | Seconds between pulls on reads. Writes always pull first regardless. |
| `CAPVSAR_BOARD_GIT_REMOTE` / `_BRANCH` | `origin` / `main` | Where it pulls and pushes. |
| `CAPVSAR_BOARD_GIT_TIMEOUT` | `30` | Seconds before a git call is called failed. |

## Adding SSO

`services/exercise/Caddyfile` has a commented `forward_auth` block on the 8443
listener. It is the same Authentik outpost pattern already running for LibreNMS
on cainfra01, and it needs a provider and application created in Authentik for
this host before it will work. Per decision **D-1**, that is the intended login
path for LAN-only consoles; the board's own bearer token stays as the second
gate either way.

## Tests

```bash
cd services/board && python -m pytest tests/ -q
```

The git-backed cases build a real bare repo and clone in a temp directory, so
they exercise the actual pull/commit/push path rather than a mock.

## Retiring the old copy

`services/ai_pilot` still serves its own `/api/board*` routes and
`static/board.html` against the same file. That is deliberate for now — those
files are in a locked agent lane. Once this container is live, the lane owner
should delete the board routes, `board_manager.py` and `static/board.html` from
`ai_pilot`, leaving the deck to telemetry, checklists and the FDR. A task for
that is queued on the board.
