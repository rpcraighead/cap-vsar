"""PTT, channel isolation and browser bridge contract regressions."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/exercise'))
from app import radio


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
    with TestClient(app) as client: yield client,clients
    assert not radio.SESSIONS
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
        assert session.outgoing.empty()
        session.deliver_audio(9,3,2,'SAME NET',bytes(1920))
        assert (await session.outgoing.get())['speaker']=='SAME NET'
        assert len(await session.outgoing.get())==1928
        session.gate.press(1);session.deliver_audio(9,3,2,'SAME NET',bytes(1920))
        assert session.outgoing.empty()
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
        assert (await session.outgoing.get())['type']=='ptt'
        assert (await session.outgoing.get())['type']=='tuned'
        assert session.outgoing.empty()
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
