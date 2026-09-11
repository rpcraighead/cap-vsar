"""
Text traffic between mission base and the aircraft.

Split out of main.py under C15-1.
"""
from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from .. import access
from ..hub import hub
from ..roles import (base_or_instructor, instructor_only, plugin_only,
                     public_scenario)
from ..settings import log
from ..store import _exec, _fetchone, db, db_call, row_to_scenario

from ..models import MessageIn

router = APIRouter()

@router.post("/api/messages", dependencies=[base_or_instructor])
async def send_message(m: MessageIn):
    """Retasking and coordination text. Supplements voice and leaves a record."""
    now = time.time()
    message_id = None
    if hub.sortie and not hub.sortie.get("stopped"):
        # After a sortie is stopped its record is closed: late traffic is
        # broadcast to whoever is still watching but not written into it.
        def go():
            with db() as c:
                return c.execute(
                    "INSERT INTO messages (sortie_id, t, sender, recipient, body)"
                    " VALUES (?,?,?,?,?)",
                    (hub.sortie["id"], now, m.sender, m.recipient, m.body)).lastrowid
        message_id = await db_call(go)
    msg = {"type": "message", "id": message_id, "t": now, "sender": m.sender,
           "recipient": m.recipient, "body": m.body}
    hub.messages.append(msg)
    await hub.broadcast(msg)
    return {"ok": True}


@router.get("/api/messages")
def list_messages(since: float = 0.0):
    """Persisted messages missed by a reconnecting mission-base console."""
    if not hub.sortie:
        return []
    sortie_id = hub.sortie["id"]
    with db() as c:
        return [{"type": "message", **dict(r)} for r in c.execute(
            "SELECT id, t, sender, recipient, body FROM messages"
            " WHERE sortie_id=? AND t>? ORDER BY t, id", (sortie_id, since))]


