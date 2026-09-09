"""Browser PCM <-> Mumble bridge. One isolated, momentary-PTT radio per socket.

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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
log = logging.getLogger(__name__)
RATE = 48000
FRAME_BYTES = 1920
MAX_TX_SECONDS = 60
LEASE_SECONDS = 1.5
CHANNELS = [
    {"id": "primary", "label": "PRIMARY", "name": "Mission Net PRIMARY"},
    {"id": "alternate", "label": "ALTERNATE", "name": "Mission Net ALTERNATE"},
    {"id": "base", "label": "MISSION BASE", "name": "Mission Base"},
    {"id": "briefing", "label": "BRIEFING", "name": "Briefing Room"},
]
SESSIONS: set = set()
CHANNEL_ACTIVITY: dict[str, float] = {}


@router.get('/api/radio/config')
def config():
    return {"channels": CHANNELS, "sampleRate": RATE, "frameSamples": 960,
            "maxTransmitSeconds": MAX_TX_SECONDS,
            "accessCodeRequired": bool(os.getenv('CAPVSAR_RADIO_ACCESS_CODE')),
            "configured": bool(os.getenv('CAPVSAR_MUMBLE_HOST')),
            "securePort": int(os.getenv('CAPVSAR_RADIO_HTTPS_PORT', '8743'))}


@router.get('/api/radio/rx')
def rx_status():
    now = time.monotonic()
    return {
        "main_rx": (now - CHANNEL_ACTIVITY.get('primary', 0) < 0.4),
        "guard_rx": (now - CHANNEL_ACTIVITY.get('alternate', 0) < 0.4),
        "channels": {k: (now - v < 0.4) for k, v in CHANNEL_ACTIVITY.items()}
    }


ICS_STATE: dict = {
    "mode": "ALL",
    "split_com": False,
    "pilot_isolated": False,
    "copilot_isolated": False,
    "crew_isolated": False,
}


@router.get('/api/radio/ics')
def ics_status():
    return dict(ICS_STATE)


@router.post('/api/radio/ics')
def update_ics(payload: dict):
    mode = str(payload.get('mode', ICS_STATE['mode'])).upper()
    if mode in ('ALL', 'PILOT', 'COPILOT', 'CREW'):
        ICS_STATE['mode'] = mode
        ICS_STATE['pilot_isolated'] = (mode == 'PILOT')
        ICS_STATE['copilot_isolated'] = (mode in ('PILOT', 'COPILOT'))
        ICS_STATE['crew_isolated'] = (mode == 'CREW')
    if 'split_com' in payload:
        ICS_STATE['split_com'] = bool(payload['split_com'])
    return dict(ICS_STATE)


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
    def __init__(self, sock, callsign):
        self.sock = sock
        self.callsign = callsign
        self.client = None
        self.loop = asyncio.get_running_loop()
        self.outgoing = asyncio.Queue(maxsize=32)
        self.connected = asyncio.Event()
        self.failed = False
        self.closed = False
        self.channel_id = None
        self.channel_key = None
        self.epoch = 0
        self.gate = TransmitGate()
        self.request = 0
        self.rx_announced = {}
        self.credit = FRAME_BYTES * 5
        self.credit_at = time.monotonic()

    def enqueue(self, item):
        if self.closed:
            return
        if self.outgoing.full():
            # Never accumulate delayed speech or silently drop control acks.
            self.failed = True
            return
        self.outgoing.put_nowait(item)

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

        # Check ICS isolation: PILOT mode isolates pilot from copilot/crew path
        if ICS_STATE.get('pilot_isolated'):
            spk_u = name.upper()
            self_u = self.callsign.upper()
            is_spk_pilot = ('PILOT' in spk_u and 'COPILOT' not in spk_u)
            is_self_pilot = ('PILOT' in self_u and 'COPILOT' not in self_u)
            is_spk_crew = ('OBSERVER' in spk_u or 'COPILOT' in spk_u or 'CREW' in spk_u or 'MO' in spk_u)
            is_self_crew = ('OBSERVER' in self_u or 'COPILOT' in self_u or 'CREW' in self_u or 'MO' in self_u)
            if (is_spk_pilot and is_self_crew) or (is_spk_crew and is_self_pilot):
                return

        # Split COM drops MO from FM mission net
        if ICS_STATE.get('split_com'):
            self_u = self.callsign.upper()
            if ('MO' in self_u or 'OBSERVER' in self_u) and self.channel_key in ('primary', 'alternate'):
                return

        now = time.monotonic()
        if self.channel_key:
            CHANNEL_ACTIVITY[self.channel_key] = now
        if now-self.rx_announced.get(session, 0) > .3:
            self.enqueue({"type": "rx", "speaker": name, "session": session})
            self.rx_announced[session] = now
        self.enqueue(struct.pack('<II', epoch, session) + pcm)

    async def connect(self, key):
        import pymumble_py3
        from pymumble_py3.constants import PYMUMBLE_CLBK_CONNECTED, PYMUMBLE_CLBK_DISCONNECTED, PYMUMBLE_CLBK_SOUNDRECEIVED
        host = os.environ['CAPVSAR_MUMBLE_HOST']
        username = f'{self.callsign} [web-{uuid.uuid4().hex[:6]}]'
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
        retained = []
        while not self.outgoing.empty():
            item = self.outgoing.get_nowait()
            if isinstance(item, dict) and item.get('type') != 'rx':
                retained.append(item)
        for item in retained:
            self.enqueue(item)
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
        self.enqueue({"type": "tuned", "channel": key, "epoch": self.epoch,
                      "callsign": self.callsign, "name": choice['name']})

    async def command(self, data):
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
            mode = str(data.get('mode', ICS_STATE['mode'])).upper()
            if mode in ('ALL', 'PILOT', 'COPILOT', 'CREW'):
                ICS_STATE['mode'] = mode
                ICS_STATE['pilot_isolated'] = (mode == 'PILOT')
                ICS_STATE['copilot_isolated'] = (mode in ('PILOT', 'COPILOT'))
                ICS_STATE['crew_isolated'] = (mode == 'CREW')
            if 'split_com' in data:
                ICS_STATE['split_com'] = bool(data['split_com'])
            self.enqueue({"type": "ics", **ICS_STATE})
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

    async def sender(self):
        while True:
            item = await self.outgoing.get()
            send = self.sock.send_bytes(item) if isinstance(item, bytes) else self.sock.send_json(item)
            await asyncio.wait_for(send, 3)

    async def watchdog(self):
        while True:
            await asyncio.sleep(.2)
            if self.failed or (self.client and not self.client.is_alive()):
                raise RuntimeError('Mission voice connection lost. Reconnect to listen.')
            if self.gate.expired(time.monotonic()):
                self.unkey('PTT released: transmit timer expired.', locked=True)

    async def receiver(self):
        while True:
            msg = await self.sock.receive()
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
                await self.command(data)

    async def close(self):
        self.closed = True
        self.gate.release()
        self.channel_id = None
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
        if len(SESSIONS) >= int(os.getenv('CAPVSAR_RADIO_MAX_SESSIONS', '16')):
            await sock.send_json({"type": "error", "message": "All browser radio connections are occupied."})
            return
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
        if len(SESSIONS) >= int(os.getenv('CAPVSAR_RADIO_MAX_SESSIONS', '16')):
            raise ValueError('All browser radio connections are occupied.')
        radio = MumbleRadio(sock, name.strip())
        SESSIONS.add(radio)
        await radio.connect(hello.get('channel', 'primary'))
        tasks = [asyncio.create_task(fn()) for fn in (radio.sender, radio.receiver, radio.watchdog)]
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
                try:
                    await radio.close()
                finally:
                    SESSIONS.discard(radio)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(sock.close(), 1)
