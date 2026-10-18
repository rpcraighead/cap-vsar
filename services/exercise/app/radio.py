"""Browser PCM <-> Mumble bridge. Isolated, momentary-PTT radios per operator.

48 kHz mono signed little-endian PCM, 20 ms frames. Mumble handles Opus.
No audio is stored. Blocking Mumble commands run outside FastAPI's event loop.
"""
from __future__ import annotations

import asyncio
import anyio
import contextlib
import hmac
import json
import logging
import os
import re
import struct
import time
import uuid
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from .roles import any_role, base_or_instructor
from . import access
from .mumble_channels import browser_nets

router = APIRouter()
log = logging.getLogger(__name__)
RATE = 48000
FRAME_BYTES = 1920
MAX_TX_SECONDS = 60
LEASE_SECONDS = 1.5
# O-4: was its own hardcoded copy of four channel names, independently of the
# provisioning script and liable to silently disagree with it. Both now read
# services/exercise/app/mumble_channels.py.
CHANNELS = browser_nets()
SESSIONS: set = set()

# X-9: extra browser faces for the same physical radio share one Mumble client.
# F-10 deliberately gives each operator two physical radios (tactical and
# airband), and therefore two pymumble threads/sessions. The server cap remains
# 16: a fully equipped dual-radio desk reduces the hard maximum to 8 operators.
OPERATORS: dict = {}


def operator_key(callsign: str) -> str:
    return ' '.join(callsign.upper().split())


def radio_key(callsign: str, receiver: str) -> tuple[str, str]:
    return operator_key(callsign), receiver


CHANNEL_ACTIVITY: dict[str, float] = {}

# Mumble username -> the radio that owns it, so the receiving side can look up
# who is speaking when the speaker is one of ours.
BY_USERNAME: dict = {}


@router.get('/api/radio/config', dependencies=[any_role])
def config():
    max_sessions = int(os.getenv('CAPVSAR_RADIO_MAX_SESSIONS', '16'))
    return {"channels": CHANNELS, "sampleRate": RATE, "frameSamples": 960,
            "maxTransmitSeconds": MAX_TX_SECONDS,
            "maxDualRadioOperators": max_sessions // 2,
            "accessCodeRequired": bool(os.getenv('CAPVSAR_RADIO_ACCESS_CODE')),
            "configured": bool(os.getenv('CAPVSAR_MUMBLE_HOST')),
            "securePort": int(os.getenv('CAPVSAR_RADIO_HTTPS_PORT', '443'))}


@router.get('/api/radio/rx', dependencies=[any_role])
def rx_status():
    """Who is keyed on which net: exercise state, so a login is needed to read it."""
    now = time.monotonic()
    return {
        "main_rx": (now - CHANNEL_ACTIVITY.get('primary', 0) < 0.4),
        "guard_rx": (now - CHANNEL_ACTIVITY.get('alternate', 0) < 0.4),
        "channels": {k: (now - v < 0.4) for k, v in CHANNEL_ACTIVITY.items()}
    }


def _blank_ics() -> dict:
    return {
        "mode": "ALL",
        "split_com": False,
        "pilot_isolated": False,
        "copilot_isolated": False,
        "crew_isolated": False,
    }


# The default, console-wide intercom state. The Air Manager instruments read
# this one (flat, unkeyed) from GET /api/radio/ics, so its shape is a contract.
ICS_STATE: dict = _blank_ics()

# Improvement 4: one global dict meant that setting the intercom for one
# aircraft changed it for every aircraft on the net. An aircraft that has been
# given its own state uses it; every other aircraft keeps following ICS_STATE.
ICS_BY_AIRCRAFT: dict[str, dict] = {}


def ics_for(aircraft_id: str | None) -> dict:
    """The intercom state that applies to a radio flying in `aircraft_id`."""
    return ICS_BY_AIRCRAFT.get(aircraft_id or '', ICS_STATE)


def apply_ics(state: dict, data: dict) -> dict:
    mode = str(data.get('mode', state['mode'])).upper()
    if mode in ('ALL', 'PILOT', 'COPILOT', 'CREW'):
        state['mode'] = mode
        state['pilot_isolated'] = (mode == 'PILOT')
        state['copilot_isolated'] = (mode in ('PILOT', 'COPILOT'))
        state['crew_isolated'] = (mode == 'CREW')
    if 'split_com' in data:
        state['split_com'] = bool(data['split_com'])
    return state


def _target_ics(aircraft_id) -> dict:
    """The dict an update should change: the aircraft's own, made on demand."""
    if not aircraft_id:
        return ICS_STATE
    if aircraft_id not in ICS_BY_AIRCRAFT:
        ICS_BY_AIRCRAFT[aircraft_id] = dict(ICS_STATE)
    return ICS_BY_AIRCRAFT[aircraft_id]


def _aircraft_arg(value) -> str:
    if value in (None, ''):
        return ''
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,32}', value):
        raise HTTPException(422, 'aircraft_id must be 1-32 letters, numbers, dots, dashes or underscores.')
    return value


def classify_crew(assigned_name: str | None, callsign: str = '') -> str:
    """'pilot', 'copilot', 'crew' (observer/scanner) or 'other'.

    The roster says what a seat is: its assigned name is "Mission Pilot" or
    "Mission Observer". The old test looked for PILOT or a bare 'MO' inside the
    callsign, which for a roster-issued callsign ("CAP 423" is shared by every
    seat in the aircraft) never matched anything, and which matched "MO" inside
    any word. The callsign is only consulted when there is no roster entry.
    """
    text = (assigned_name or '').strip() or callsign
    up = text.upper()
    if 'COPILOT' in up or 'CO-PILOT' in up:
        return 'copilot'
    if re.search(r'\bPILOT\b', up):
        return 'pilot'
    if re.search(r'\b(OBSERVER|SCANNER|CREW|MO)\b', up):
        return 'crew'
    return 'other'


def ics_blocks(state: dict, listener: str, speaker: str, channel_key: str | None) -> bool:
    """True when the intercom state keeps `speaker` out of `listener`'s ears."""
    if state.get('pilot_isolated'):
        crew = ('crew', 'copilot')
        if (speaker == 'pilot' and listener in crew) or (speaker in crew and listener == 'pilot'):
            return True
    # Split COM drops the mission observer from the FM mission net.
    if (state.get('split_com') and listener == 'crew'
            and channel_key in ('primary', 'alternate')):
        return True
    return False


@router.get('/api/radio/ics')
def ics_status(aircraft: str = ''):
    return dict(ics_for(_aircraft_arg(aircraft)))


@router.post('/api/radio/ics', dependencies=[base_or_instructor])
def update_ics(payload: dict):
    """Set the intercom mode, console-wide or (aircraft_id) for one aircraft."""
    aircraft_id = _aircraft_arg(payload.get('aircraft_id'))
    return dict(apply_ics(_target_ics(aircraft_id), payload))


class TransmitGate:
    """Fail-closed PTT lease, independent of the browser's release events."""
    def __init__(self):
        self.active = False
        self.started = self.renewed = 0.0
        self.locked = False

    def press(self, now):
        if self.locked:
            return False
        if not self.active:
            self.started = now
        self.active = True
        self.renewed = now
        return True

    def release(self):
        self.active = False
        self.locked = False

    def expired(self, now):
        return self.active and (now-self.started >= MAX_TX_SECONDS or
                                now-self.renewed > LEASE_SECONDS)


class MumbleRadio:
    def __init__(self, sock, callsign, receiver='main'):
        self.callsign = callsign
        self.receiver_kind = receiver
        self.log_identity = (f'{callsign} / TACTICAL' if receiver == 'main'
                             else f'{callsign} / AIRBAND')
        self.client = None
        self.loop = asyncio.get_running_loop()
        # Who sits at this radio, from the roster (improvement 4).
        self.aircraft_id = ''
        self.crew_class = classify_crew(None, callsign)
        self.username = None
        self.watchdog_task = None
        self.dropped: dict = {}
        self.drop_reason: dict = {}
        # X-9: every attached face gets its own outbound queue. One slow tablet
        # must not stall the other face on the same desk, and a queue that
        # overflows takes down that face only.
        self.faces: dict = {}
        # A9/A13: the session each face joined with, and whether one was
        # required (False only for the anonymous join of an open dev console).
        self.face_session: dict = {}
        self.attach(sock)
        self.connected = asyncio.Event()
        self.failed = False
        self.closed = False
        self.channel_id = None
        self.channel_key = None
        self.channel_name = None
        self.epoch = 0
        self.gate = TransmitGate()
        self.request = 0
        self.rx_announced = {}
        self.credit = FRAME_BYTES * 5
        self.credit_at = time.monotonic()

    def tuned_ack(self):
        """The join acknowledgement, as this radio currently stands.

        A face attaching to a radio that is already on the net (X-9) never ran
        connect(), so nothing told it which net it had joined - it sat waiting
        for a `tuned` that was only ever sent when the connection was first
        made, and the page hung on "joining".
        """
        return {"type": "tuned", "channel": self.channel_key,
                "epoch": self.epoch, "callsign": self.callsign,
                "name": self.channel_name or self.channel_key,
                "receiver": self.receiver_kind,
                "logIdentity": self.log_identity}

    def queue_for(self, sock):
        """The outbound queue of one attached face."""
        return self.faces[sock]

    def attach(self, sock):
        """Add a browser face to this radio and return its outbound queue."""
        queue = asyncio.Queue(maxsize=32)
        self.faces[sock] = queue
        self.dropped[sock] = asyncio.Event()
        return queue

    def admit(self, sock, session, required):
        """Record the credential a face joined with (A9, A13)."""
        self.face_session[sock] = (session, required)

    def detach(self, sock):
        """Remove one face. True when that was the last one."""
        self.faces.pop(sock, None)
        self.dropped.pop(sock, None)
        self.drop_reason.pop(sock, None)
        self.face_session.pop(sock, None)
        return not self.faces

    def drop_face(self, sock, reason):
        """Disconnect one face and leave the radio and the other faces alone.

        X2-7: a full queue used to set `failed` on the whole radio, which its
        own comment promised not to do - the next face to join then built a
        second Mumble client for the same desk. The slow face is cut off (its
        stream handler raises `reason` and closes its socket) and the rest of
        the desk keeps hearing the net.
        """
        self.faces.pop(sock, None)
        event = self.dropped.get(sock)
        if event is not None and not event.is_set():
            self.drop_reason[sock] = reason
            event.set()

    async def face_dropped(self, sock):
        """Completes (by raising) when this face is dropped by the radio."""
        await self.dropped[sock].wait()
        raise RuntimeError(self.drop_reason.get(sock, 'Radio connection dropped.'))

    def enqueue(self, item):
        if self.closed:
            return
        for sock, queue in list(self.faces.items()):
            if queue.full():
                # Never accumulate delayed speech or silently drop control
                # acks. One wedged face fails on its own; the rest of the desk
                # keeps hearing the net.
                self.drop_face(sock, 'Radio connection too slow. Reconnect to listen.')
                continue
            queue.put_nowait(item)

    def disconnected(self, *args):
        def mark():
            self.failed = True
            self.connected.set()
        self.loop.call_soon_threadsafe(mark)

    def received(self, user, sound):
        # Callback runs on pymumble's thread. Capture immutable packet metadata.
        session = user.get('session', 0)
        channel = user.get('channel_id')
        epoch = self.epoch
        pcm = bytes(sound.pcm)
        # Callbacks do not consume pymumble's per-user sound queue. Drain it
        # after copying this chunk so long exercises cannot accumulate PCM.
        while user.sound.is_sound():
            user.sound.get_sound()
        name = str(user.get('name', 'Station'))[:80]
        self.loop.call_soon_threadsafe(self.deliver_audio, session, channel, epoch, name, pcm)

    def deliver_audio(self, session, channel, epoch, name, pcm):
        if (self.closed or self.gate.active or self.channel_id is None or
                channel != self.channel_id or epoch != self.epoch):
            return
        if not pcm or len(pcm) % 2 or len(pcm) > RATE * 2:
            return

        # Intercom isolation, from this listener's aircraft state. The speaker
        # is another browser radio of ours when we can find it, and then its
        # roster seat decides; an outside Mumble client is judged by its name.
        speaker_radio = BY_USERNAME.get(name)
        speaker = (speaker_radio.crew_class if speaker_radio
                   else classify_crew(None, name))
        if ics_blocks(ics_for(self.aircraft_id), self.crew_class, speaker,
                      self.channel_key):
            return

        now = time.monotonic()
        if self.channel_key:
            CHANNEL_ACTIVITY[self.channel_key] = now
        if now-self.rx_announced.get(session, 0) > .3:
            self.enqueue({"type": "rx", "speaker": name, "session": session,
                          "receiver": self.receiver_kind, "net": self.channel_name})
            self.rx_announced[session] = now
        self.enqueue(struct.pack('<II', epoch, session) + pcm)

    async def connect(self, key):
        import pymumble_py3
        from pymumble_py3.constants import PYMUMBLE_CLBK_CONNECTED, PYMUMBLE_CLBK_DISCONNECTED, PYMUMBLE_CLBK_SOUNDRECEIVED
        host = os.environ['CAPVSAR_MUMBLE_HOST']
        username = f'{self.log_identity} [web-{uuid.uuid4().hex[:6]}]'
        self.username = username
        BY_USERNAME[username] = self
        self.client = pymumble_py3.Mumble(
            host, username, port=int(os.getenv('CAPVSAR_MUMBLE_PORT', '64738')),
            password=os.getenv('CAPVSAR_MUMBLE_PASSWORD', ''), reconnect=False)
        self.client.set_application_string('CAP V-SAR Mission Base')
        self.client.set_receive_sound(True)
        self.client.set_loop_rate(.01)
        self.client.callbacks.set_callback(PYMUMBLE_CLBK_CONNECTED,
            lambda *args: self.loop.call_soon_threadsafe(self.connected.set))
        self.client.callbacks.set_callback(PYMUMBLE_CLBK_DISCONNECTED, self.disconnected)
        self.client.callbacks.set_callback(PYMUMBLE_CLBK_SOUNDRECEIVED, self.received)
        self.client.start()
        await asyncio.wait_for(self.connected.wait(), 10)
        if self.failed or self.client.users.myself is None:
            raise RuntimeError('The mission voice server refused the connection.')
        await self.tune(key)

    def stop_audio(self):
        if self.client and self.client.sound_output:
            self.client.sound_output.clear_buffer()

    def unkey(self, reason=None, locked=False):
        self.gate.release()
        self.gate.locked = locked
        self.stop_audio()
        self.enqueue({"type": "ptt", "active": False, "request": self.request,
                      "reason": reason})

    async def tune(self, key):
        choice = next((c for c in CHANNELS if c['id'] == key), None)
        if choice is None:
            raise ValueError('Unknown exercise net.')
        self.unkey()
        self.channel_id = None   # mute until the server confirms the move
        self.epoch += 1
        self.rx_announced.clear()
        # Remove any queued old-channel audio before acknowledging a retune.
        for sock, queue in list(self.faces.items()):
            retained = []
            while not queue.empty():
                item = queue.get_nowait()
                if isinstance(item, dict) and item.get('type') != 'rx':
                    retained.append(item)
            for item in retained:
                if not queue.full():
                    queue.put_nowait(item)
        path = os.getenv('CAPVSAR_MUMBLE_CHANNEL_PREFIX', '').strip('/')
        tree = ([p for p in path.split('/') if p] if path else []) + [choice['name']]
        channel = self.client.channels.find_by_tree(tree)
        await asyncio.wait_for(asyncio.to_thread(channel.move_in), 4)
        target = channel['channel_id']
        deadline = time.monotonic()+4
        while self.client.users.myself.get('channel_id') != target:
            if self.failed or time.monotonic() > deadline:
                raise RuntimeError('The voice server did not confirm the selected net.')
            await asyncio.sleep(.04)
        self.channel_id, self.channel_key = target, key
        self.channel_name = choice['name']
        self.enqueue(self.tuned_ack())

    async def command(self, data, sock=None):
        action = data.get('action')
        if action == 'tune':
            await self.tune(data.get('channel'))
        elif action == 'ptt':
            request = data.get('request', 0)
            if not isinstance(request, int) or isinstance(request, bool) or not 0 <= request <= 2**31-1:
                raise ValueError('Invalid PTT request.')
            self.request = request
            if data.get('active') is True:
                me = self.client.users.myself
                if (self.channel_id is None or me.get('channel_id') != self.channel_id or
                        me.get('mute') or me.get('suppress')):
                    self.unkey('Transmission is not permitted on this net.')
                elif self.gate.press(time.monotonic()):
                    self.credit, self.credit_at = FRAME_BYTES*5, time.monotonic()
                    self.enqueue({"type": "ptt", "active": True, "request": request})
                else:
                    self.unkey('Release PTT before transmitting again.', locked=True)
            else:
                self.unkey()
        elif action == 'keepalive':
            # Audio arriving on a congested socket cannot renew this lease.
            if self.gate.active:
                self.gate.renewed = time.monotonic()
        elif action == 'ping':
            self.enqueue({"type": "pong"})
        elif action == 'ics':
            # A9 (review T11): this used to rely on the join gate alone, which
            # only asks for *a* session with a callsign. A UDF or an aircrew
            # seat (aircraft_id "") could set PILOT isolation or split COM on
            # the console-wide state every aircraft follows. It now shares
            # POST /api/radio/ics's gate: base or instructor, or the explicitly
            # open dev console. The session is re-read rather than taken from
            # the join (A13), so a revoked badge cannot keep the gate open.
            session = self.face_session.get(sock, (None, True))[0]
            if sock is not None:
                session = await run_in_threadpool(access.get_session_from_request, sock)
            if not access.session_satisfies('base', session):
                raise ValueError('The intercom is set by mission base or the instructor.')
            # A seat in an aircraft changes that aircraft's intercom, not the
            # whole net's.
            state = apply_ics(_target_ics(self.aircraft_id), data)
            self.enqueue({"type": "ics", **state})
        else:
            raise ValueError('Unknown radio command.')

    def transmit(self, pcm):
        now = time.monotonic()
        if self.gate.expired(now):
            self.unkey('PTT released: transmit timer expired.', locked=True)
        if not self.gate.active or self.channel_id is None:
            return
        me = self.client.users.myself
        if (me.get('channel_id') != self.channel_id or me.get('mute') or
                me.get('suppress')):
            self.unkey('Voice server changed your channel or transmit permission.', locked=True)
            return
        if len(pcm) != FRAME_BYTES:
            raise ValueError('Expected one 20 ms mono PCM frame.')
        self.credit = min(FRAME_BYTES*5, self.credit+(now-self.credit_at)*RATE*2)
        self.credit_at = now
        if self.credit < len(pcm) or self.client.sound_output.get_buffer_size() > .18:
            self.unkey('Audio connection is delayed. Release PTT and try again.', locked=True)
            return
        self.credit -= len(pcm)
        self.client.sound_output.add_sound(pcm)

    async def sender(self, sock):
        queue = self.faces[sock]
        while True:
            item = await queue.get()
            send = sock.send_bytes(item) if isinstance(item, bytes) else sock.send_json(item)
            await asyncio.wait_for(send, 3)

    def start_watchdog(self):
        """Start the radio's own watchdog. Called once, by the face that built it."""
        if self.watchdog_task is None:
            self.watchdog_task = asyncio.create_task(self.watchdog())

    async def watchdog(self):
        """X2-7: owned by the radio, not by whichever face opened it.

        It used to be one of the opening face's pump tasks, so when that tab
        closed the desk's other faces were left with no watchdog at all: a
        dead Mumble link or an expired PTT lease went unnoticed. close()
        cancels it; a lost link drops every face.
        """
        while True:
            await asyncio.sleep(.2)
            if self.failed or (self.client and not self.client.is_alive()):
                self.failed = True
                for sock in list(self.faces):
                    self.drop_face(sock, 'Mission voice connection lost. Reconnect to listen.')
                return
            if self.gate.expired(time.monotonic()):
                self.unkey('PTT released: transmit timer expired.', locked=True)

    async def receiver(self, sock):
        while True:
            msg = await sock.receive()
            if msg['type'] == 'websocket.disconnect':
                return
            if msg.get('bytes') is not None:
                self.transmit(msg['bytes'])
            elif msg.get('text') is not None:
                if len(msg['text']) > 2048:
                    raise ValueError('Radio command is too large.')
                data = json.loads(msg['text'])
                if not isinstance(data, dict):
                    raise ValueError('Invalid radio command.')
                await self.command(data, sock)

    async def session_guard(self, sock):
        """A13: a joined face keeps its credential only while the session exists.

        Logout, the 24 h expiry and roster regeneration all delete the session
        row, and none of them used to reach a radio that had joined before.
        Re-read off the event loop (X2-5) every SOCKET_RECHECK_S; a face whose
        session is gone is dropped with a reason, the desk's other faces and the
        Mumble client are left alone.
        """
        _, required = self.face_session.get(sock, (None, False))
        while True:
            await asyncio.sleep(access.SOCKET_RECHECK_S)
            fresh = await run_in_threadpool(access.get_session_from_request, sock)
            if not access.socket_still_admitted(fresh, required=required):
                raise ValueError('Your login has ended. Log in again and reconnect the radio.')

    async def close(self):
        self.closed = True
        self.gate.release()
        self.channel_id = None
        if self.username and BY_USERNAME.get(self.username) is self:
            BY_USERNAME.pop(self.username, None)
        task, self.watchdog_task = self.watchdog_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self.client:
            self.stop_audio()
            with contextlib.suppress(Exception):
                self.client.stop()
            await asyncio.to_thread(self.client.join, 2)


@router.websocket('/api/radio/stream')
async def stream(sock: WebSocket):
    origin = sock.headers.get('origin')
    if origin and urlsplit(origin).netloc != sock.headers.get('host'):
        await sock.close(code=1008)
        return
    await sock.accept()
    radio = None
    tasks = []
    try:
        if not os.getenv('CAPVSAR_MUMBLE_HOST'):
            await sock.send_json({"type": "error", "message": "Mission voice is not configured on this server."})
            return
        # The session cap is checked once the callsign is known (below): until
        # then there is no way to tell a new operator, who needs a Mumble
        # session, from a second face for an operator who already has one and
        # needs nothing (X-9). This used to reject the second face outright
        # whenever the net was full.
        raw = await asyncio.wait_for(sock.receive_text(), 15)
        if len(raw) > 2048:
            raise ValueError('Join request is too large.')
        hello = json.loads(raw)
        if not isinstance(hello, dict) or hello.get('action') != 'join':
            raise ValueError('Join the radio before sending audio.')
        expected = os.getenv('CAPVSAR_RADIO_ACCESS_CODE', '')
        code = hello.get('accessCode', '')
        if not isinstance(code, str) or (expected and not hmac.compare_digest(code.encode(), expected.encode())):
            await sock.send_json({"type": "error", "message": "Incorrect exercise access code."})
            return
        name = hello.get('callsign')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9 ._-]{2,32}', name.strip()):
            raise ValueError('Use a callsign of 2–32 letters, numbers, spaces, dots or dashes.')
        name = name.strip()
        receiver = hello.get('receiver', 'main')
        if receiver not in ('main', 'airband'):
            raise ValueError('Unknown radio receiver.')
        # O-5: an authenticated RBAC session's callsign always overrides
        # whatever the client claims, so a base-role student can't type
        # "MISSION BASE" or "INSTRUCTOR" and impersonate another station on
        # the net.
        #
        # FE-4: that was only half of it. The override applied when a session
        # happened to exist, and nothing required one - so on a console with
        # tokens configured, a socket with no cookie at all kept its claimed
        # callsign. "MISSION BASE" is the join form's own default value, and
        # since X-9 keys a radio by callsign, a stranger typing it attached to
        # the real MRO's Mumble client: heard their net, and raced their PTT
        # acks. The exercise console is gated; its voice net has to be too.
        #
        # X2-4: the fallback to a claimed callsign used to apply whenever
        # CAPVSAR_TOKEN_BASE was unset, which is also what a roster-only
        # production console looks like, so anyone on the LAN could join as
        # "MISSION BASE". It now applies only to an explicitly open dev
        # console (CAPVSAR_DEV_OPEN) with no base credential, the same
        # condition that opens every other endpoint.
        # X2-5: off the event loop, which is also carrying the audio frames.
        session = await run_in_threadpool(access.get_session_from_request, sock)
        if session and session.get('callsign'):
            name = session['callsign']
        elif not (access.dev_open() and 'base' in access.unconfigured()):
            await sock.send_json({
                "type": "error",
                "message": "Log in first: open /login and use your participant "
                           "code, then reconnect the radio."})
            return
        # X-9: a second face for an operator already on the net attaches to
        # the radio they are already using. It costs no extra Mumble session,
        # and the desk stays one station on the net instead of appearing twice.
        key = radio_key(name, receiver)
        existing = OPERATORS.get(key)
        # A13: a session is required unless this is the anonymous join of an
        # open dev console (the elif above is the only other way in).
        required = session is not None
        if existing is not None and not existing.closed and not existing.failed:
            radio, shared = existing, True
            queue = radio.attach(sock)
            radio.admit(sock, session, required)
            # Tell the new face where the radio already is, or it waits for a
            # `tuned` that was sent before it existed.
            queue.put_nowait(radio.tuned_ack())
        else:
            if len(SESSIONS) >= int(os.getenv('CAPVSAR_RADIO_MAX_SESSIONS', '16')):
                raise ValueError('All browser radio connections are occupied.')
            radio, shared = MumbleRadio(sock, name, receiver=receiver), False
            radio.admit(sock, session, required)
            SESSIONS.add(radio)
            OPERATORS[key] = radio
            await radio.connect(hello.get('channel', 'primary'))
            # Who sits here, for the intercom (improvement 4).
            if session:
                radio.aircraft_id = session.get('aircraft_id') or ''
                radio.crew_class = classify_crew(session.get('assigned_name'),
                                                 radio.callsign)
            # The watchdog belongs to the radio (X2-7), not to this face.
            radio.start_watchdog()
        pumps = [radio.sender(sock), radio.receiver(sock), radio.face_dropped(sock),
                 radio.session_guard(sock)]
        tasks = [asyncio.create_task(coro) for coro in pumps]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as exc:
        # No host/password or client-provided exception details are reflected.
        log.warning('Browser radio closed (%s)', type(exc).__name__)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        with contextlib.suppress(Exception):
            await sock.send_json({"type": "error", "message":
                str(exc) if isinstance(exc, ValueError) else
                'Voice connection unavailable. Check the mission server and selected net, then reconnect.'})
    finally:
        # ASGI disconnect/shutdown cancellation must not strand a Mumble client
        # or consume a browser-radio slot for the rest of the exercise.
        with anyio.CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if radio:
                # Only the last face standing takes the Mumble client down
                # with it; closing on the first tab to be shut would have cut
                # the operator off mid-transmission on the other one.
                last = radio.detach(sock)
                if last:
                    try:
                        await radio.close()
                    finally:
                        SESSIONS.discard(radio)
                        key = radio_key(radio.callsign, radio.receiver_kind)
                        if OPERATORS.get(key) is radio:
                            OPERATORS.pop(key, None)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(sock.close(), 1)
