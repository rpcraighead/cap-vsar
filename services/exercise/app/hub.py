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

from .roles import public_aircraft, public_scenario
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
        self.truth_clients: set[WebSocket] = set()   # sockets that logged in as instructor

    async def broadcast(self, msg: dict):
        """Send to every console at once, and drop anyone who cannot keep up.

        Sequential awaits meant one wedged tablet blocked the 1 Hz ticker and
        every handler that broadcasts. A half-open socket never raises, so it
        needs a timeout rather than an exception to be noticed.
        """
        if not self.clients:
            return
        text = json.dumps(msg, allow_nan=False)
        await self._deliver([(w, text) for w in list(self.clients)])

    async def _deliver(self, pairs):
        async def send(ws, text):
            try:
                await asyncio.wait_for(ws.send_text(text), self.SEND_TIMEOUT_S)
            except Exception:
                return ws          # dead, wedged, or too slow - same outcome
            return None

        for ws in await asyncio.gather(*(send(w, t) for w, t in pairs)):
            if ws is not None:
                self.clients.discard(ws)
                self.truth_clients.discard(ws)

    def snapshot(self, include_truth: bool = False, include_df: bool = False) -> dict:
        """The one place live state becomes something a browser may receive.

        X2-1: aircraft records carry the plugin's whole `df` dictionary, whose
        bearing_true and distance_nm are a fix on the beacon. They are reduced
        to receiver state here unless the viewer is allowed truth or the
        sortie has been revealed, so no caller has to remember to.
        """
        revealed = bool(self.sortie and self.sortie.get("revealed"))
        allow = include_truth or revealed
        # The map feed never carries the scenario's beacon before reveal, even
        # for an instructor (they read it from /api/scenarios). Live DF is
        # different: the instructor console renders it, so an instructor
        # viewer gets it without the scenario truth.
        allow_df = allow or include_df
        s = {
            "sortie": self.sortie,
            "scenario": None,
            "aircraft": [public_aircraft(a, include_truth=allow_df)
                         for a in self.aircraft.values()],
            "server_time": time.time(),
        }
        if self.scenario:
            s["scenario"] = public_scenario(self.scenario, include_truth=allow)
        return s

    async def broadcast_state(self):
        """Send the state frame, one rendering per kind of viewer (X2-1).

        An instructor console shows live DF; everyone else gets the redacted
        form. Rendering twice (not once per client) keeps the 1 Hz ticker cheap.
        """
        if not self.clients:
            return
        # X2-3: allow_nan=False. A bare NaN is not JSON, every browser's
        # JSON.parse rejects the frame, and it was being sent to all of them
        # once a second. A bad value now raises here, once, where it can be
        # logged, instead of silently breaking every console.
        full = json.dumps({"type": "state", **self.snapshot(include_df=True)},
                          allow_nan=False)
        public = json.dumps({"type": "state", **self.snapshot()},
                            allow_nan=False)
        pairs = [(w, full if w in self.truth_clients else public)
                 for w in list(self.clients)]
        await self._deliver(pairs)


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
            try:
                await hub.broadcast_state()
            except ValueError as e:
                # A value JSON cannot carry (X2-3). Say so every second rather
                # than let the exception end the ticker, which would also stop
                # aircraft expiry for the rest of the exercise.
                log.error("state not broadcast: %s", e)


