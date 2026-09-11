"""Airborne MO maneuver contract. No model output or scenario truth controls surfaces."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import math
import re
import threading
import time
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class Observation:
    heading_mag: float
    altitude_indicated_ft: float
    agl_ft: float
    kias: float
    roll_deg: float
    vvi_fpm: float
    age_seconds: float


class FlightBackend(Protocol):
    """Replaceable boundary for Garmin/X-Plane or a future ArduPlane adapter."""
    def observe(self) -> Observation: ...
    def select(self, heading_mag: float, altitude_indicated_ft: float) -> None: ...
    def release(self) -> None: ...
    def pause(self) -> None: ...


@dataclass(frozen=True)
class Limits:
    # Prototype exercise envelope, NOT POH limitations or terrain clearance assurance.
    min_altitude_ft: float = 3000
    max_altitude_ft: float = 6000
    min_agl_ft: float = 1000
    min_kias: float = 90
    max_kias: float = 140
    max_bank_deg: float = 35
    max_age_seconds: float = 2
    settle_seconds: float = 3

    def __post_init__(self):
        if not all(math.isfinite(v) for v in asdict(self).values()):
            raise ValueError('Limits must be finite')
        if not (0 <= self.min_altitude_ft < self.max_altitude_ft
                and 0 < self.min_kias < self.max_kias
                and self.min_agl_ft > 0 and 0 < self.max_bank_deg < 90
                and self.max_age_seconds > 0 and self.settle_seconds > 0):
            raise ValueError('Invalid exercise limits')


def parse_maneuver(text: str) -> dict:
    """Small full-match grammar: partial matches, negations and corrections never execute."""
    if not isinstance(text, str):
        raise ValueError('Command must be text')
    text = text.strip().lower()
    match = re.fullmatch(r'(?:turn )?heading (\d{1,3})(?: magnetic)?', text)
    if match:
        return {'heading_mag': int(match[1])}
    match = re.fullmatch(r'(?:maintain|climb to|descend to) (\d{3,5}) feet indicated', text)
    if match:
        return {'altitude_indicated_ft': int(match[1])}
    raise ValueError('Use “heading 090 magnetic” or “maintain 4500 feet indicated”. '
                     'Directional turns, compound instructions and corrections require a new explicit command.')


class ManeuverGate:
    def __init__(self, backend: FlightBackend, limits: Limits = Limits(), clock=time.monotonic):
        self.backend, self.limits, self.clock = backend, limits, clock
        self.lock = threading.RLock()
        self.lease = None
        self.sequence = 0
        self.targets = None
        self.active = None
        self.settled_since = None
        self.events = deque(maxlen=200)

    def _event(self, status, **fields):
        entry = {'status': status, 'time': time.time(), **fields}
        self.events.append(entry)
        return entry

    def _check(self, o):
        if not all(math.isfinite(v) for v in asdict(o).values()):
            raise ValueError('Missing or invalid telemetry')
        l = self.limits
        if not 0 <= o.age_seconds <= l.max_age_seconds:
            raise ValueError('Stale telemetry')
        if not (l.min_kias <= o.kias <= l.max_kias and o.agl_ft >= l.min_agl_ft
                and abs(o.roll_deg) <= l.max_bank_deg
                and l.min_altitude_ft <= o.altitude_indicated_ft <= l.max_altitude_ft):
            raise ValueError('Aircraft outside the configured airborne exercise envelope')

    def acquire(self):
        with self.lock:
            if self.lease:
                raise ValueError('Control already acquired; take over before reacquiring')
            o = self.backend.observe()
            self._check(o)
            self.lease, self.sequence = uuid4().hex, 0
            self.targets = [o.heading_mag % 360, o.altitude_indicated_ft]
            self._event('control_acquired')
            return {'lease': self.lease, 'next_sequence': 1}

    def submit(self, lease, sequence, fields):
        with self.lock:
            try:
                if not self.lease or lease != self.lease:
                    raise ValueError('Control lease absent or revoked')
                if type(sequence) is not int or sequence != self.sequence + 1:
                    raise ValueError('Out-of-order or repeated command')
                if not isinstance(fields, dict) or not fields or set(fields) - {'heading_mag', 'altitude_indicated_ft'}:
                    raise ValueError('Unsupported maneuver fields')
                if any(type(v) not in (int, float) or not math.isfinite(v) for v in fields.values()):
                    raise ValueError('Maneuver values must be finite numbers')
                o = self.backend.observe()
                self._check(o)
                hdg = fields.get('heading_mag', self.targets[0])
                alt = fields.get('altitude_indicated_ft', self.targets[1])
                if not (0 <= hdg <= 360 and self.limits.min_altitude_ft <= alt <= self.limits.max_altitude_ft):
                    raise ValueError('Target outside exercise limits')
                # Current terrain only. No claim of terrain lookahead.
                if o.agl_ft + alt - o.altitude_indicated_ft < self.limits.min_agl_ft:
                    raise ValueError('Target below clearance floor over current terrain')
            except ValueError as error:
                self._event('refused', reason=str(error))
                raise
            command_id = uuid4().hex
            self.sequence = sequence  # Consume even if a backend partially fails; never replay.
            if self.active:
                self._event('superseded', command_id=self.active['command_id'])
            self._event('accepted', command_id=command_id, heading_mag=hdg % 360,
                        altitude_indicated_ft=alt)
            try:
                self.backend.select(hdg % 360, alt)
            except Exception:
                self._fault('Backend failed while selecting maneuver')
                raise ValueError('Backend failure; control revoked, pause requested')
            self.targets = [hdg % 360, alt]
            self.settled_since = None
            self.active = self._event('executing', command_id=command_id,
                heading_mag=hdg % 360, altitude_indicated_ft=alt,
                readback=f'Selected heading {hdg % 360:03.0f} magnetic, altitude {alt:.0f} feet indicated. Awaiting measured capture.')
            return dict(self.active)

    def takeover(self):
        with self.lock:
            self.lease = None
            self.active = None
            self.targets = None
            self.backend.release()
            return self._event('released', readback='Control revoked; autopilot disconnect requested. Verify cockpit indications.')

    def _fault(self, reason):
        self.lease = None
        self.active = None
        self.targets = None
        self._event('fault', reason=reason)
        # Do not blind-climb or disconnect an airborne aircraft on lost telemetry.
        self.backend.pause()

    def tick(self):
        with self.lock:
            if not self.lease:
                return
            try:
                o = self.backend.observe()
                self._check(o)
            except Exception as error:
                self._fault(str(error))
                return
            if self.active:
                hdg, alt = self.targets
                captured = (abs((o.heading_mag - hdg + 180) % 360 - 180) <= 3
                            and abs(o.altitude_indicated_ft - alt) <= 100
                            and abs(o.roll_deg) <= 5 and abs(o.vvi_fpm) <= 150)
                if not captured:
                    self.settled_since = None
                elif self.settled_since is None:
                    self.settled_since = self.clock()
                elif self.clock() - self.settled_since >= self.limits.settle_seconds:
                    self._event('achieved', command_id=self.active['command_id'])
                    self.active = None

    def status(self):
        with self.lock:
            o = asdict(self.backend.observe())
            # Missing observations must serialize as JSON null, not Infinity/NaN.
            o = {k: v if math.isfinite(v) else None for k, v in o.items()}
            return {'owned': bool(self.lease), 'sequence': self.sequence,
                    'observation': o, 'active': self.active,
                    'limits': asdict(self.limits), 'events': list(self.events)}


class XPlaneAutopilotBackend:
    SUBSCRIPTION_REFRESH_SECONDS = 1.0
    DATAREFS = {
        'heading_mag': 'sim/flightmodel/position/mag_psi',
        'altitude_indicated_ft': 'sim/cockpit2/gauges/indicators/altitude_ft_pilot',
        'agl_ft': 'sim/flightmodel/position/y_agl',
        'kias': 'sim/flightmodel/position/indicated_airspeed',
        'roll_deg': 'sim/flightmodel/position/phi',
        'vvi_fpm': 'sim/flightmodel/position/vh_ind_fpm',
    }

    def __init__(self, client, clock=time.monotonic):
        self.client, self.clock = client, clock
        self.samples = {}
        self.lock = threading.Lock()
        self.subscriptions = {
            **self.DATAREFS,
            'ap_state': 'sim/cockpit/autopilot/autopilot_state',
        }
        self.last_subscription_refresh = self.clock()
        for name, ref in self.subscriptions.items():
            def received(ref, value, name=name):
                with self.lock:
                    self.samples[name] = (value, self.clock())
            client.subscribe_dref(ref, freq_hz=10, callback=received)

    def _refresh_subscriptions_if_stale(self, timestamps):
        now = self.clock()
        missing_or_stale = any(
            not math.isfinite(timestamp) or now - timestamp >= self.SUBSCRIPTION_REFRESH_SECONDS
            for timestamp in timestamps
        )
        if not missing_or_stale or now - self.last_subscription_refresh < self.SUBSCRIPTION_REFRESH_SECONDS:
            return
        # Reuse the existing subscription IDs without registering callbacks again.
        for ref in self.subscriptions.values():
            self.client.subscribe_dref(ref, freq_hz=10)
        self.last_subscription_refresh = now

    def observe(self):
        with self.lock:
            values = {name: self.samples.get(name, (float('nan'), -float('inf')))
                      for name in self.DATAREFS}
            ap = self.samples.get('ap_state', (float('nan'), -float('inf')))
        self._refresh_subscriptions_if_stale(
            [value[1] for value in values.values()] + [ap[1]]
        )
        age = max([self.clock() - value[1] for value in values.values()] + [self.clock() - ap[1]])
        return Observation(**{name: value[0] * (3.28084 if name == 'agl_ft' else 1)
                              for name, value in values.items()}, age_seconds=age)

    def select(self, heading_mag, altitude_indicated_ft):
        c = self.client
        current = self.observe().altitude_indicated_ft
        with self.lock:
            state = self.samples.get('ap_state', (float('nan'), 0))[0]
        if not math.isfinite(state):
            raise ValueError('Missing autopilot mode telemetry')
        state = int(state)
        c.send_dref('sim/cockpit2/autopilot/heading_dial_deg_mag_pilot', heading_mag)
        c.send_dref('sim/cockpit2/autopilot/altitude_dial_ft', altitude_indicated_ft)
        # Single-bit mode requests, ordered as documented by Laminar:
        # https://developer.x-plane.com/article/accessing-the-x-plane-autopilot-from-datarefs/
        if not state & 2:
            c.send_dref('sim/cockpit/autopilot/autopilot_state', 2)  # Heading engage
        if abs(altitude_indicated_ft - current) > 100:
            # Commands.txt (X-Plane 12.4.3): G1000 FLC button. FLC couples
            # speed-by-pitch with altitude preselect; do not toggle ALT arm
            # separately on the G1000. AP state bit 8 is speed-by-pitch;
            # bit 64 is its legacy FLC alias (Laminar reference above).
            if not state & (8 | 64):
                c.send_command('sim/GPS/g1000n1_flc')
            # Exercise target, not a POH climb-performance claim. Power is
            # managed by the supervising pilot. Use the always-knots dataref
            # documented in the installed Resources/plugins/DataRefs.txt.
            c.send_dref('sim/cockpit2/autopilot/airspeed_dial_kts', 110)
        elif not state & 16384:
            c.send_dref('sim/cockpit/autopilot/autopilot_state', 16384)  # Hold current altitude
        c.send_dref('sim/cockpit2/autopilot/flight_director_mode', 2)

    def release(self):
        self.client.send_command('sim/autopilot/servos_off_any')

    def pause(self):
        self.client.set_paused(True)
