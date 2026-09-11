"""
Live exercise state and the console fan-out (C15-1).

The hub is the one piece of the console that is genuinely shared mutable
state: the running sortie, its scenario, the aircraft last heard from, and
every connected browser. The 1 Hz ticker that expires stale aircraft lives
here too, because it is the same state seen on a timer.
"""
from __future__ import annotations

import asyncio
import json
import time

from .roles import public_scenario
from .settings import log

class Hub:
    SEND_TIMEOUT_S = 1.0        # a console that cannot take a frame in a second
                                # is not going to catch up on the next one

    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.aircraft: dict[str, dict] = {}
        self.sortie: dict | None = None
        self.scenario: dict | None = None
        self.messages: list[dict] = []

    async def broadcast(self, msg: dict):
        """Send to every console at once, and drop anyone who cannot keep up.

        Sequential awaits meant one wedged tablet blocked the 1 Hz ticker and
        every handler that broadcasts. A half-open socket never raises, so it
        needs a timeout rather than an exception to be noticed.
        """
        if not self.clients:
            return
        text = json.dumps(msg)

        async def send(ws):
            try:
                await asyncio.wait_for(ws.send_text(text), self.SEND_TIMEOUT_S)
            except Exception:
                return ws          # dead, wedged, or too slow - same outcome
            return None

        for ws in await asyncio.gather(*(send(w) for w in list(self.clients))):
            if ws is not None:
                self.clients.discard(ws)

    def snapshot(self, include_truth: bool = False) -> dict:
        s = {
            "sortie": self.sortie,
            "scenario": None,
            "aircraft": list(self.aircraft.values()),
            "server_time": time.time(),
        }
        if self.scenario:
            revealed = bool(self.sortie and self.sortie.get("revealed"))
            s["scenario"] = public_scenario(
                self.scenario, include_truth=include_truth or revealed)
        return s


hub = Hub()



async def ticker():
    """Push state to consoles, and expire aircraft that stop reporting."""
    while True:
        await asyncio.sleep(1.0)
        now = time.time()
        stale = [k for k, a in hub.aircraft.items() if now - a["t"] > 30]
        for k in stale:
            hub.aircraft.pop(k, None)
        if hub.clients:
            await hub.broadcast({"type": "state", **hub.snapshot()})


