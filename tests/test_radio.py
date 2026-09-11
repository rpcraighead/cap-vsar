"""PTT, channel isolation and browser bridge contract regressions."""
import asyncio
import os
import tempfile
import time
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/exercise'))
from app import radio, access

RADIO_JS = (Path(__file__).resolve().parents[1] /
            'services/exercise/app/static/mission-radio.js')


class Output:
    def __init__(self): self.frames = []; self.pending = 0
    def add_sound(self, data): self.frames.append(data)
    def clear_buffer(self): self.pending = 0
    def get_buffer_size(self): return self.pending


class Client:
    def __init__(self):
        self.sound_output = Output()
        self.users = SimpleNamespace(myself={'channel_id': 3})
        self.stopped = False
    def is_alive(self): return not self.stopped
    def stop(self): self.stopped = True
    def join(self, timeout): pass


@pytest.fixture
def sockets(monkeypatch):
    monkeypatch.setenv('CAPVSAR_MUMBLE_HOST', 'test-only')
    monkeypatch.delenv('CAPVSAR_RADIO_ACCESS_CODE', raising=False)
    clients=[]
    async def connect(self, key):
        self.client=Client();clients.append(self.client)
        self.channel_id=3;self.channel_key=key;self.epoch=1
        self.enqueue({'type':'tuned','channel':key,'epoch':1})
    monkeypatch.setattr(radio.MumbleRadio,'connect',connect)
    app=FastAPI();app.include_router(radio.router)
    radio.OPERATORS.clear()
    with TestClient(app) as client: yield client,clients
    assert not radio.SESSIONS
    assert not radio.OPERATORS, 'a shared radio outlived its last face'
    assert all(c.stopped for c in clients)


def join(client):
    sock=client.websocket_connect('/api/radio/stream')
    return sock


def hello(sock, name='TEST BASE'):
    sock.send_json({'action':'join','callsign':name,'channel':'primary'})
    assert sock.receive_json()['type']=='tuned'


def test_no_audio_before_ptt_and_release_stops_audio(sockets):
    client,clients=sockets
    with join(client) as sock:
        hello(sock)
        sock.send_bytes(bytes(1920));sock.send_json({'action':'ping'})
        assert sock.receive_json()['type']=='pong'
        assert not clients[0].sound_output.frames
        sock.send_json({'action':'ptt','active':True,'request':1})
        assert sock.receive_json()['active'] is True
        sock.send_bytes(bytes(1920));sock.send_json({'action':'ptt','active':False,'request':2})
        assert sock.receive_json()['active'] is False
        sock.send_bytes(bytes(1920));sock.send_json({'action':'ping'});sock.receive_json()
        assert len(clients[0].sound_output.frames)==1


def test_browser_sessions_have_independent_microphone_gates(sockets):
    client,clients=sockets
    with join(client) as a,join(client) as b:
        hello(a,'BASE A');hello(b,'BASE B')
        a.send_json({'action':'ptt','active':True,'request':1});a.receive_json()
        a.send_bytes(bytes(1920));a.send_json({'action':'ping'});a.receive_json()
        b.send_bytes(bytes(1920));b.send_json({'action':'ping'});b.receive_json()
        assert len(clients[0].sound_output.frames)==1
        assert clients[1].sound_output.frames==[]


def test_server_enforces_access_code(sockets,monkeypatch):
    client,clients=sockets;monkeypatch.setenv('CAPVSAR_RADIO_ACCESS_CODE','exercise-code')
    with join(client) as sock:
        sock.send_json({'action':'join','callsign':'TEST BASE','accessCode':'wrong'})
        assert sock.receive_json()['type']=='error'
    assert clients==[]


def test_authenticated_session_callsign_overrides_the_claimed_one(sockets, monkeypatch):
    """O-5: a base-role student typing "MISSION BASE" or "INSTRUCTOR" as their
    radio callsign must not be able to impersonate another station - the
    authenticated session's own callsign wins instead."""
    client, clients = sockets
    db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db.close()
    monkeypatch.setenv('CAPVSAR_DB', db.name)
    try:
        access.init_auth_db()
        sess_id = access.create_session('MRO-1', 'base', 'Mission Radio Operator 1', callsign='MRO-1')
        with client.websocket_connect('/api/radio/stream', cookies={access.SESSION_COOKIE: sess_id}) as sock:
            sock.send_json({'action': 'join', 'callsign': 'INSTRUCTOR', 'channel': 'primary'})
            sock.receive_json()
            assert [r.callsign for r in radio.SESSIONS] == ['MRO-1']
    finally:
        os.unlink(db.name)


def test_no_session_falls_back_to_the_claimed_callsign(sockets):
    """RBAC not configured for this exercise (the common case today) must not
    break the radio - the client-supplied callsign is trusted as before."""
    client, clients = sockets
    with join(client) as sock:
        sock.send_json({'action': 'join', 'callsign': 'TEST BASE', 'channel': 'primary'})
        sock.receive_json()
        assert [r.callsign for r in radio.SESSIONS] == ['TEST BASE']


def test_config_does_not_disclose_credentials(sockets,monkeypatch):
    client,_=sockets;monkeypatch.setenv('CAPVSAR_RADIO_ACCESS_CODE','do-not-disclose')
    monkeypatch.setenv('CAPVSAR_MUMBLE_PASSWORD','also-secret')
    response=client.get('/api/radio/config')
    assert response.json()['accessCodeRequired']
    assert 'do-not-disclose' not in response.text and 'also-secret' not in response.text


def test_cross_origin_socket_rejected(sockets):
    from starlette.websockets import WebSocketDisconnect
    client,_=sockets
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/api/radio/stream',headers={'origin':'https://another-site.example'}):pass


def test_bad_pcm_frame_closes_transmission(sockets):
    client,clients=sockets
    with join(client) as sock:
        hello(sock);sock.send_json({'action':'ptt','active':True,'request':1});sock.receive_json()
        sock.send_bytes(bytes(10));assert sock.receive_json()['type']=='error'


def test_server_lease_and_hard_timeout_require_a_new_press():
    gate=radio.TransmitGate()
    assert gate.press(10)
    assert not gate.expired(11.4)
    assert gate.expired(11.6)
    gate.release();gate.press(20)
    gate.renewed=79.9
    assert gate.expired(80)
    gate.locked=True;gate.active=False
    assert not gate.press(81)
    gate.release();assert gate.press(82)


def test_rx_ignores_other_nets_old_epochs_and_half_duplex_tx():
    async def check():
        session=radio.MumbleRadio(None,'BASE');session.channel_id=3;session.epoch=2
        session.deliver_audio(9,4,2,'OTHER NET',bytes(1920))
        session.deliver_audio(9,3,1,'OLD NET',bytes(1920))
        assert session.queue_for(None).empty()
        session.deliver_audio(9,3,2,'SAME NET',bytes(1920))
        assert (await session.queue_for(None).get())['speaker']=='SAME NET'
        assert len(await session.queue_for(None).get())==1928
        session.gate.press(1);session.deliver_audio(9,3,2,'SAME NET',bytes(1920))
        assert session.queue_for(None).empty()
    asyncio.run(check())


def test_tune_invalidates_ptt_and_old_audio_before_ack():
    async def check():
        session=radio.MumbleRadio(None,'BASE');session.client=Client();session.channel_id=3;session.epoch=1
        class Channel(dict):
            def move_in(self):session.client.users.myself['channel_id']=4
        session.client.channels=SimpleNamespace(find_by_tree=lambda path:Channel(channel_id=4))
        session.gate.press(1);session.enqueue(b'old audio')
        await session.tune('alternate')
        assert not session.gate.active
        assert session.channel_id==4 and session.epoch==2
        assert (await session.queue_for(None).get())['type']=='ptt'
        assert (await session.queue_for(None).get())['type']=='tuned'
        assert session.queue_for(None).empty()
    asyncio.run(check())


def test_server_mute_blocks_ptt(sockets):
    client,clients=sockets
    with join(client) as sock:
        hello(sock);clients[0].users.myself['suppress']=True
        sock.send_json({'action':'ptt','active':True,'request':1})
        response=sock.receive_json()
        assert not response['active'] and 'not permitted' in response['reason']


@pytest.mark.parametrize('change', [{'channel_id': 4}, {'mute': True}])
def test_server_move_or_mute_during_transmission_unkeys(sockets, change):
    client, clients = sockets
    with join(client) as sock:
        hello(sock)
        sock.send_json({'action': 'ptt', 'active': True, 'request': 1})
        assert sock.receive_json()['active']
        clients[0].users.myself.update(change)
        sock.send_bytes(bytes(1920))
        assert not sock.receive_json()['active']
        assert clients[0].sound_output.frames == []


def test_browser_radio_rejoins_with_backoff_and_an_audible_alarm():
    source = RADIO_JS.read_text()
    assert 'scheduleReconnect' in source
    assert 'soundDisconnectAlarm' in source
    assert 'Math.min(30000' in source
    assert "addEventListener('close',()=>{if(state.ws===socket)connectionLost" in source
    assert "connectionLost('Mission voice stopped responding." in source
    assert "state.context.addEventListener('statechange'" in source
    assert "context.state==='suspended' && state.wantOnline" in source


# ---------------------------------------------------------------------- X-9
# One Mumble client per browser SOCKET meant an operator with two radio faces
# open burned two of the sixteen server sessions and showed up on the net as
# two separate users - so the same desk could be called, and answer, as two
# different stations.

def wait_until(predicate, timeout=3.0):
    """The server tears a face down on its own loop, so a test that closes a
    socket and asserts immediately is racing it."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_a_second_face_for_one_operator_shares_the_radio(sockets):
    client, clients = sockets
    with join(client) as first:
        hello(first, 'MISSION BASE')
        assert len(clients) == 1 and len(radio.SESSIONS) == 1
        with join(client) as second:
            hello(second, 'MISSION BASE')
            # Same operator: one Mumble client, one session, one user on the net.
            assert len(clients) == 1, 'a second Mumble session was opened'
            assert len(radio.SESSIONS) == 1
            live = next(iter(radio.SESSIONS))
            assert len(live.faces) == 2, 'the second face did not attach'


def test_a_different_operator_still_gets_their_own_radio(sockets):
    client, clients = sockets
    with join(client) as first:
        hello(first, 'MISSION BASE')
        with join(client) as second:
            hello(second, 'MRO 2')
            assert len(clients) == 2
            assert len(radio.SESSIONS) == 2


def test_the_callsign_match_ignores_case_and_spacing(sockets):
    client, clients = sockets
    with join(client) as first:
        hello(first, 'MISSION BASE')
        with join(client) as second:
            hello(second, 'mission  base')
            assert len(clients) == 1


def test_closing_one_face_leaves_the_other_on_the_net(sockets):
    client, clients = sockets
    with join(client) as first:
        hello(first, 'MISSION BASE')
        with join(client) as second:
            hello(second, 'MISSION BASE')
        # The second face closed; the radio must still be up for the first.
        live = next(iter(radio.SESSIONS))
        assert wait_until(lambda: len(live.faces) == 1), 'the face never detached'
        assert not clients[0].stopped, 'closing one tab cut the operator off'
        assert len(radio.SESSIONS) == 1
    # The last face closing takes the Mumble client with it. That teardown is
    # asynchronous on the server side, so the fixture asserts it after the
    # TestClient has drained rather than racing it here.


def test_both_faces_hear_the_same_traffic(sockets):
    client, clients = sockets
    with join(client) as first:
        hello(first, 'MISSION BASE')
        with join(client) as second:
            hello(second, 'MISSION BASE')
            live = next(iter(radio.SESSIONS))
            live.deliver_audio(9, live.channel_id, live.epoch, 'CAP 487', bytes(1920))
            for face in (first, second):
                assert face.receive_json()['speaker'] == 'CAP 487'
                assert len(face.receive_bytes()) == 1928


def test_sharing_does_not_consume_extra_session_slots(sockets, monkeypatch):
    """The cap is on Mumble sessions, which is what the server actually
    limits - not on browser tabs."""
    client, clients = sockets
    monkeypatch.setenv('CAPVSAR_RADIO_MAX_SESSIONS', '1')
    with join(client) as first:
        hello(first, 'MISSION BASE')
        with join(client) as second:
            hello(second, 'MISSION BASE')          # would have been refused
            assert len(radio.SESSIONS) == 1
