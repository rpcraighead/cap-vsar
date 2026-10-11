"""
CAP V-SAR Agent Coordination Board.

The dispatch board for the Claude / Codex / Antigravity lanes, served as its
own container so it is reachable from anywhere on the lab network instead of
only from the workstation that runs X-Plane.

This is an ENGINEERING surface, in a different trust domain from the
participant console. It must not be mounted on the participant front door.
It binds inside the compose network only; Caddy's engineering listener is what
puts it on the LAN, and that listener is where SSO belongs.

Writes fail closed: with no CAPVSAR_BOARD_TOKEN set, every mutating route
returns 503 rather than accepting anyone who can reach the port.
"""
from __future__ import annotations

import hmac
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware

from .git_sync import GitSync, NullSync
from .settings import (ALLOWED_ORIGINS, BOARD_PATH, BOARD_RELPATH, GIT_AUTHOR_EMAIL,
                       GIT_AUTHOR_NAME, GIT_BRANCH, GIT_REMOTE, GIT_SYNC, GIT_TIMEOUT,
                       PULL_INTERVAL, REPO, STATIC, TOKEN, log)
from .store import BoardStore

sync = (
    GitSync(REPO, GIT_REMOTE, GIT_BRANCH, GIT_AUTHOR_NAME, GIT_AUTHOR_EMAIL, GIT_TIMEOUT)
    if GIT_SYNC else NullSync()
)
store = BoardStore(BOARD_PATH, BOARD_RELPATH, sync, PULL_INTERVAL)


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("board file: %s (relpath %s)", BOARD_PATH, BOARD_RELPATH)
    log.info("git sync: %s", "on" if sync.is_repo() else "OFF - board is a local file only")
    if not TOKEN:
        log.warning("CAPVSAR_BOARD_TOKEN is unset: all writes will be refused with 503")
    if not BOARD_PATH.is_file():
        log.warning("board file does not exist yet at %s", BOARD_PATH)
    yield


app = FastAPI(title="CAP V-SAR Agent Board", docs_url=None, redoc_url=None,
              lifespan=lifespan)

# Exact origins only. An empty list means no CORS headers are emitted at all,
# which is same-origin only - the right default behind the front door.
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.exception_handler(HTTPException)
async def as_error_object(request: Request, exc: HTTPException) -> JSONResponse:
    """The board UI reads `.error`, not FastAPI's default `.detail`."""
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.middleware("http")
async def no_store_api(request: Request, call_next):
    """A cached /api/board is indistinguishable from a board nobody updated."""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Origin"
    return response


def require_write(request: Request) -> None:
    """Gate every mutating route. Deny by default, never fail open."""
    origin = request.headers.get("origin")
    if origin and ALLOWED_ORIGINS and origin.rstrip("/") not in ALLOWED_ORIGINS:
        raise HTTPException(403, "Origin not allowed")
    if not TOKEN:
        raise HTTPException(503, "Writes disabled: set CAPVSAR_BOARD_TOKEN on the service")
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(supplied.encode(), f"Bearer {TOKEN}".encode()):
        raise HTTPException(401, "Valid engineering bearer credential required")


class TaskIn(BaseModel):
    agent: str = Field(min_length=1, max_length=80)
    task: str = Field(min_length=1, max_length=8000)


class ToggleIn(BaseModel):
    index: int = Field(ge=0)
    completed: bool


class RawIn(BaseModel):
    markdown: str = Field(max_length=500_000)


@app.get("/api/health")
async def health() -> JSONResponse:
    """O2-6: unhealthy means unhealthy, so the compose healthcheck can fail.

    The board is only useful with its board file, and with git sync on (the
    deployed default) only if /repo is a real checkout; `GitSync.pull` on a
    non-repo is a quiet no-op, which would otherwise read as a working board
    nobody had written to. A missing write token is NOT a health failure: it
    is a supported read-only configuration.
    """
    board_present = BOARD_PATH.is_file()
    is_repo = sync.is_repo()
    problems = []
    if not board_present:
        problems.append(f"board file missing: {BOARD_PATH}")
    if GIT_SYNC and not is_repo:
        problems.append(f"git sync is on but {REPO} is not a git checkout")
    body = {
        "status": "degraded" if problems else "ok",
        "board_present": board_present,
        "git_sync": is_repo,
        "writes_enabled": bool(TOKEN),
    }
    if problems:
        body["problems"] = problems
    return JSONResponse(body, status_code=503 if problems else 200)


@app.get("/api/board")
async def get_board() -> dict:
    return await run_in_threadpool(store.read)


@app.post("/api/board/task", dependencies=[Depends(require_write)])
async def add_task(body: TaskIn) -> dict:
    board = await run_in_threadpool(store.add_task, body.agent, body.task)
    return {"status": "ok", "board": board}


@app.post("/api/board/toggle", dependencies=[Depends(require_write)])
async def toggle_task(body: ToggleIn) -> dict:
    board, found = await run_in_threadpool(store.toggle_task, body.index, body.completed)
    if not found:
        raise HTTPException(404, f"No task at index {body.index}")
    return {"status": "ok", "board": board}


@app.post("/api/board/raw", dependencies=[Depends(require_write)])
async def save_raw(body: RawIn) -> dict:
    board = await run_in_threadpool(store.save_raw, body.markdown)
    return {"status": "ok", "board": board}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
@app.get("/board.html")
async def index() -> FileResponse:
    return FileResponse(STATIC / "board.html")
