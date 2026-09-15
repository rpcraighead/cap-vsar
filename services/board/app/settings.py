"""
Everything the board service reads from its environment, in one place.

The board used to be four routes bolted onto the AI Pilot deck, which meant it
could only run on the workstation: importing `services.ai_pilot` pulls in the
X-Plane UDP client, the flight controller and the C182 checklists, none of
which exist in a container. This service is the board on its own.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

STATIC = Path(__file__).parent / "static"

# The repository working clone the board file lives in. In the container this
# is a volume holding a real clone of capvsar, because the board is a file
# under version control and not a database.
REPO = Path(os.environ.get("CAPVSAR_BOARD_REPO", "/repo"))

# Path of the board file, relative to REPO. Relative on purpose: it is also the
# pathspec handed to `git add`, so it must never be absolute.
BOARD_RELPATH = os.environ.get("CAPVSAR_BOARD_FILE", "docs/BOARD.md")
BOARD_PATH = REPO / BOARD_RELPATH

# Git sync makes the container's clone the shared board rather than a private
# copy. Turned off, the service is a plain file editor - which is what the
# tests want, and what a local run without a deploy key can do.
GIT_SYNC = os.environ.get("CAPVSAR_BOARD_GIT_SYNC", "1") not in ("0", "false", "no", "")
GIT_REMOTE = os.environ.get("CAPVSAR_BOARD_GIT_REMOTE", "origin")
GIT_BRANCH = os.environ.get("CAPVSAR_BOARD_GIT_BRANCH", "main")
GIT_AUTHOR_NAME = os.environ.get("CAPVSAR_BOARD_GIT_NAME", "CAP V-SAR Board")
GIT_AUTHOR_EMAIL = os.environ.get("CAPVSAR_BOARD_GIT_EMAIL", "board@capvsar.invalid")
GIT_TIMEOUT = int(os.environ.get("CAPVSAR_BOARD_GIT_TIMEOUT", "30"))

# A pull on every read would put a network round trip in front of a 3-second
# poll from every open tab. Pulls are coalesced to at most one per interval.
PULL_INTERVAL = float(os.environ.get("CAPVSAR_BOARD_PULL_INTERVAL", "15"))

# Writes fail closed. An unset token disables every mutating route rather than
# leaving them open - the X-11 lesson from the exercise console, which returned
# early and accepted anyone when no token was configured.
TOKEN = os.environ.get("CAPVSAR_BOARD_TOKEN", "")

# Exact http(s) origins, comma separated, no trailing slashes. Empty means
# same-origin only, which is the correct default behind the Caddy front door.
ALLOWED_ORIGINS = tuple(
    o.strip().rstrip("/")
    for o in os.environ.get("CAPVSAR_BOARD_ORIGINS", "").split(",")
    if o.strip()
)

LOG_LEVEL = os.environ.get("CAPVSAR_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
log = logging.getLogger("capvsar.board")
