"""PTT, channel isolation and browser bridge contract regressions."""
import asyncio
import os
import shutil
import subprocess
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
    # Start every radio test from a console with no roles configured, whatever
    # ran before. test_console.py and test_setup_auth.py's build_app() sets
    # CAPVSAR_TOKEN_* directly in os.environ rather than through monkeypatch
    # and never clears them, so in a combined run those tokens leaked in here.
    # That was harmless until FE-4 made the join gate depend on them, at which
    # point this file's results depended on which files pytest had already
    # collected. A test whose outcome depends on its neighbours is not a test.
    for role in ('INSTRUCTOR', 'BASE', 'PLUGIN'):
        monkeypatch.delenv(f'CAPVSAR_TOKEN_{role}', raising=False)
    # X2-4: a console with no tokens is an open dev console only when that is
    # said out loud. Tests that want the production behaviour delenv this.
    monkeypatch.setenv('CAPVSAR_DEV_OPEN', '1')
    monkeypatch.delenv('CAPVSAR_ENV', raising=False)
    clients=[]
    async def connect(self, key):
        self.client=Client();clients.append(self.client)
        self.channel_id=3;self.channel_key=key;self.channel_name=key;self.epoch=1
        self.enqueue(self.tuned_ack())
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


def hello(sock, name='TEST BASE', channel='primary', receiver='main'):
    sock.send_json({'action':'join','callsign':name,'channel':channel,
                    'receiver':receiver})
    response = sock.receive_json()
    assert response['type']=='tuned'
    return response


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


def test_roster_only_console_refuses_a_sessionless_join(sockets, monkeypatch):
    """X2-4: no CAPVSAR_TOKEN_BASE is also what a production console that
    authenticates by roster code looks like. Without the explicit dev flag a
    socket with no session is refused, whatever callsign it claims."""
    monkeypatch.delenv('CAPVSAR_DEV_OPEN')
    client, clients = sockets
    with join(client) as sock:
        sock.send_json({'action': 'join', 'callsign': 'MISSION BASE', 'channel': 'primary'})
        reply = sock.receive_json()
        assert reply['type'] == 'error' and 'Log in' in reply['message']
        assert not radio.SESSIONS


def test_no_session_falls_back_to_the_claimed_callsign(sockets):
    """On an explicitly open dev console (CAPVSAR_DEV_OPEN) the radio stays
    usable without a login.

    FE-4 narrowed this: the fallback used to apply whenever a session happened
    to be absent, including on a console with roles configured, which is what
    let a stranger join as "MISSION BASE". X2-4 narrowed it again: it applies
    only to a console that has been opened on purpose."""
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


# --------------------------------------------------------------------- F-10

def test_one_operator_gets_two_independent_radios_and_keys_the_selected_net(sockets):
    client, clients = sockets
    with join(client) as tactical, join(client) as airband:
        tactical_ack = hello(tactical, 'MISSION BASE', 'primary', 'main')
        airband_ack = hello(airband, 'MISSION BASE', 'alternate', 'airband')
        assert tactical_ack['receiver'] == 'main'
        assert airband_ack['receiver'] == 'airband'
        assert len(clients) == 2 and len(radio.SESSIONS) == 2

        radios = {item.receiver_kind: item for item in radio.SESSIONS}
        assert radios['main'].log_identity == 'MISSION BASE / TACTICAL'
        assert radios['airband'].log_identity == 'MISSION BASE / AIRBAND'

        airband.send_json({'action':'ptt','active':True,'request':7})
        assert airband.receive_json()['active'] is True
        airband.send_bytes(bytes(1920))
        airband.send_json({'action':'ping'})
        assert airband.receive_json()['type'] == 'pong'
        assert clients[0].sound_output.frames == []
        assert clients[1].sound_output.frames == [bytes(1920)]


def test_dual_radio_operator_uses_two_of_the_sixteen_slots(sockets, monkeypatch):
    client, clients = sockets
    monkeypatch.setenv('CAPVSAR_RADIO_MAX_SESSIONS', '2')
    with join(client) as tactical, join(client) as airband:
        hello(tactical, 'MISSION BASE', 'primary', 'main')
        hello(airband, 'MISSION BASE', 'alternate', 'airband')
        with join(client) as another_operator:
            another_operator.send_json({'action':'join','callsign':'MRO 2',
                                        'channel':'primary','receiver':'main'})
            response = another_operator.receive_json()
            assert response['type'] == 'error'
            assert 'occupied' in response['message']
        assert len(clients) == 2 and len(radio.SESSIONS) == 2


def test_receive_event_carries_the_radio_log_identity():
    async def check():
        session = radio.MumbleRadio(None, 'MISSION BASE', receiver='airband')
        session.channel_id = 4
        session.channel_key = 'alternate'
        session.channel_name = 'Mission Net ALTERNATE'
        session.epoch = 1
        session.deliver_audio(12, 4, 1, 'CAP 487', bytes(1920))
        announcement = await session.queue_for(None).get()
        assert announcement == {
            'type': 'rx', 'speaker': 'CAP 487', 'session': 12,
            'receiver': 'airband', 'net': 'Mission Net ALTERNATE',
        }
    asyncio.run(check())


def test_browser_mix_keeps_tactical_and_airband_volumes_independent():
    source = RADIO_JS.read_text()
    start = source.index('// BEGIN F-10 PURE RADIO MIX')
    end = source.index('// END F-10 PURE RADIO MIX')
    block = source[start:end]
    script = block + "\nconsole.log(JSON.stringify(radioMixLevels(80, 25)));"
    import json
    import subprocess
    result = subprocess.run(['node', '-e', script], text=True,
                            capture_output=True, check=True)
    assert json.loads(result.stdout) == {'main': 0.8, 'airband': 0.25}


# -- review follow-ups on F-10 ------------------------------------------------
# Three defects found reviewing F-10 before merge. Each is a decision extracted
# into the pure block so it can be executed, not grepped.

def _radio_mix_block():
    source = RADIO_JS.read_text()
    start = source.index('// BEGIN F-10 PURE RADIO MIX')
    end = source.index('// END F-10 PURE RADIO MIX')
    return source[start:end]


def _run_js(expression):
    import json
    import subprocess
    script = _radio_mix_block() + f'\nconsole.log(JSON.stringify({expression}));'
    result = subprocess.run(['node', '-e', script], text=True,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_keying_one_radio_does_not_suppress_the_other_radios_traffic():
    """The airband transmission must still reach the CAP Form 110 log."""
    # Keying tactical suppresses tactical rx only.
    assert _run_js("rxIsSuppressed(true, 'main', 'main')") is True
    assert _run_js("rxIsSuppressed(true, 'main', 'airband')") is False
    # And the reverse.
    assert _run_js("rxIsSuppressed(true, 'airband', 'airband')") is True
    assert _run_js("rxIsSuppressed(true, 'airband', 'main')") is False
    # Not transmitting suppresses nothing.
    assert _run_js("rxIsSuppressed(false, 'main', 'main')") is False


def test_a_secondary_receiver_failure_is_scoped_to_that_receiver():
    """Operator nine's refused airband join must not drop their tactical net."""
    assert _run_js("failureScope('airband')") == 'airband'
    assert _run_js("failureScope('main')") == 'console'
    assert _run_js("failureScope(undefined)") == 'console'


def test_the_two_radios_are_never_left_on_the_same_net():
    """Both on one net re-creates the X-9 symptom: the desk twice on the net,
    doubled audio, and the operator's own transmission back in their headset."""
    nets = "['primary','alternate','base','briefing']"
    # Already distinct: nothing moves.
    assert _run_js(f"distinctNetResolution('primary','alternate',{nets},'main')") is None
    # Collision: the radio the operator did NOT touch is the one that moves.
    assert _run_js(f"distinctNetResolution('primary','primary',{nets},'main')") == {
        'radio': 'airband', 'net': 'alternate'}
    assert _run_js(f"distinctNetResolution('primary','primary',{nets},'airband')") == {
        'radio': 'main', 'net': 'alternate'}
    # A single-channel server cannot satisfy the rule; it must not crash or
    # invent a net that does not exist.
    assert _run_js("distinctNetResolution('only','only',['only'],'main')") == {
        'radio': 'airband', 'net': 'only'}
    assert _run_js("distinctNetResolution('','',[],'main')") is None


# --------------------------------------------------------------------- F-11

def _sidetone_block():
    source = RADIO_JS.read_text()
    start = source.index('// BEGIN F-11 PURE SIDETONE PLAN')
    end = source.index('// END F-11 PURE SIDETONE PLAN')
    return source[start:end]


def _run_sidetone_js(expression):
    import json
    import subprocess
    script = _sidetone_block() + f'\nconsole.log(JSON.stringify({expression}));'
    result = subprocess.run(['node', '-e', script], text=True,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_each_radio_uses_its_own_grant_and_release_tones():
    assert _run_sidetone_js("transmitTonePlan('main','grant')") == {
        'tone': 'p25-chirp', 'speechDelayMs': 115}
    assert _run_sidetone_js("transmitTonePlan('main','release')") == {
        'tone': 'p25-tail', 'speechDelayMs': 0}
    assert _run_sidetone_js("transmitTonePlan('airband','grant')") == {
        'tone': 'am-click', 'speechDelayMs': 15}
    assert _run_sidetone_js("transmitTonePlan('airband','release')") == {
        'tone': 'am-squelch-burst', 'speechDelayMs': 0}


def test_grant_plan_puts_the_tone_before_live_microphone_audio():
    assert _run_sidetone_js("transmitGrantSequence('main')") == [
        {'action': 'tone', 'tone': 'p25-chirp', 'atMs': 0},
        {'action': 'speech', 'atMs': 115},
    ]
    assert _run_sidetone_js("transmitGrantSequence('airband')") == [
        {'action': 'tone', 'tone': 'am-click', 'atMs': 0},
        {'action': 'speech', 'atMs': 15},
    ]


# --------------------------------------------------------------------- F-12

def _monitor_block():
    source = RADIO_JS.read_text()
    start = source.index('// BEGIN F-12 PURE MONITOR POLICY')
    end = source.index('// END F-12 PURE MONITOR POLICY')
    return source[start:end]


def _run_monitor_js(expression):
    import json
    import subprocess
    script = _monitor_block() + f'\nconsole.log(JSON.stringify({expression}));'
    result = subprocess.run(['node', '-e', script], text=True,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_mon_toggle_changes_only_the_selected_radio():
    assert _run_monitor_js(
        "monitorStatesAfterToggle({main:false,airband:false},'main')") == {
            'main': True, 'airband': False}
    assert _run_monitor_js(
        "monitorStatesAfterToggle({main:true,airband:false},'airband')") == {
            'main': True, 'airband': True}


def test_mon_open_passes_audio_that_normal_squelch_rejects():
    assert _run_monitor_js("squelchPasses(false,0.004)") is False
    assert _run_monitor_js("squelchPasses(true,0.004)") is True
    assert _run_monitor_js("squelchPasses(false,0.04)") is True


def test_efj_mon_artwork_has_an_executable_hit_region():
    assert _run_monitor_js("controlHeadMonitorHit('efj5300')") == [
        'Monitor / open squelch', 489, 32, 94, 50, 'mon']
    assert _run_monitor_js("controlHeadMonitorHit('apx4500')") is None


# --------------------------------------------------------------- FE-4 / FE-6

def _configured(monkeypatch):
    """A console with roles configured, and a throwaway auth database."""
    db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db.close()
    monkeypatch.setenv('CAPVSAR_DB', db.name)
    monkeypatch.setenv('CAPVSAR_TOKEN_BASE', 'base-token')
    monkeypatch.setenv('CAPVSAR_TOKEN_INSTRUCTOR', 'instructor-token')
    access.init_auth_db()
    return db.name


def test_join_without_a_session_is_refused_when_roles_are_configured(sockets, monkeypatch):
    """FE-4: the voice net has to be gated wherever the console is.

    "MISSION BASE" is the join form's own default value, and since X-9 keys a
    radio by callsign, a stranger typing it attached to the real MRO's Mumble
    client - heard their net and raced their PTT acks. Before this change the
    socket below was accepted and took the claimed callsign.
    """
    client, clients = sockets
    db = _configured(monkeypatch)
    try:
        with client.websocket_connect('/api/radio/stream') as sock:
            sock.send_json({'action': 'join', 'callsign': 'MISSION BASE',
                            'channel': 'primary'})
            reply = sock.receive_json()
            assert reply['type'] == 'error'
            assert 'log in first' in reply['message'].lower()
        assert not radio.SESSIONS, 'a refused join still opened a Mumble client'
    finally:
        os.unlink(db)


def test_join_with_a_session_uses_the_session_callsign(sockets, monkeypatch):
    client, clients = sockets
    db = _configured(monkeypatch)
    try:
        sess = access.create_session('X7QM-2FBX', 'base', 'Mission Radio Operator 1',
                                     callsign='MRO 1')
        with client.websocket_connect(
                '/api/radio/stream',
                cookies={access.SESSION_COOKIE: sess}) as sock:
            sock.send_json({'action': 'join', 'callsign': 'MISSION BASE',
                            'channel': 'primary'})
            assert sock.receive_json()['type'] == 'tuned'
            assert [r.callsign for r in radio.SESSIONS] == ['MRO 1']
    finally:
        os.unlink(db)


def test_ics_is_not_a_public_control(sockets, monkeypatch):
    """FE-6: anyone on the LAN could mute every observer station mid-search.

    POST {"split_com": true} and every callsign containing MO/OBSERVER stopped
    hearing the mission net, with nothing to say why.
    """
    client, _ = sockets
    db = _configured(monkeypatch)
    try:
        before = client.get('/api/radio/ics').json()
        r = client.post('/api/radio/ics', json={'split_com': True})
        assert r.status_code == 403, 'ICS accepted an unauthenticated caller'
        assert client.get('/api/radio/ics').json() == before

        ok = client.post('/api/radio/ics', json={'split_com': True},
                         headers={'X-CAPVSAR-Token': 'base-token'})
        assert ok.status_code == 200
        assert ok.json()['split_com'] is True
    finally:
        radio.ICS_STATE.update({'mode': 'ALL', 'split_com': False,
                                'pilot_isolated': False,
                                'copilot_isolated': False,
                                'crew_isolated': False})
        os.unlink(db)


def test_ics_is_refused_when_no_roles_are_configured_unless_the_console_is_deliberately_open(sockets, monkeypatch):
    """X-11 (deny by default) replaced FE-6's "documented local mode stays open":
    no roles configured now means refused, and an open console is a deliberate
    CAPVSAR_DEV_OPEN choice."""
    client, _ = sockets
    for name in ('CAPVSAR_DEV_OPEN', 'CAPVSAR_TOKEN_INSTRUCTOR', 'CAPVSAR_TOKEN_BASE', 'CAPVSAR_TOKEN_PLUGIN'):
        monkeypatch.delenv(name, raising=False)  # no roles and not open, whatever an earlier test left behind
    try:
        assert client.post('/api/radio/ics', json={'mode': 'PILOT'}).status_code == 503
        monkeypatch.setenv('CAPVSAR_DEV_OPEN', '1')
        assert client.post('/api/radio/ics', json={'mode': 'PILOT'}).status_code == 200
    finally:
        radio.ICS_STATE.update({'mode': 'ALL', 'split_com': False,
                                'pilot_isolated': False,
                                'copilot_isolated': False,
                                'crew_isolated': False})


def test_only_unrecoverable_server_errors_stop_the_radio_reconnecting():
    """FE-5: a Mumble restart must not leave every browser radio dark.

    The client used to call disconnect() on any {"type":"error"}, which clears
    wantOnline, so F-4's auto-rejoin never fired. F-4 therefore only covered a
    socket that died silently; the commonest real failure - the voice server
    bouncing - arrives as an error frame and killed the radio for the rest of
    the exercise.

    This drives the real classifier out of mission-radio.js rather than
    asserting on its source text.
    """
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed; JS classifier not exercised')

    harness = r'''
      const fs = require('fs');
      const src = fs.readFileSync(process.argv[1], 'utf8');
      // Pull out the classifier and its table, which are self-contained.
      const table = src.match(/const FATAL_ERRORS = \[[\s\S]*?\];/);
      const fn = src.match(/function isFatalError\(message\) \{[\s\S]*?\n\}/);
      if (!table || !fn) { console.log('MISSING'); process.exit(0); }
      eval(table[0] + '\n' + fn[0]);
      const fatal = [
        'Incorrect exercise access code.',
        'Log in first: open /login and use your participant code, then reconnect the radio.',
        'All browser radio connections are occupied.',
        'Mission voice is not configured on this server.',
      ];
      const retry = [
        'Mission voice connection lost. Reconnect to listen.',
        'Voice connection unavailable. Check the mission server and selected net, then reconnect.',
        'Audio connection is delayed. Release PTT and try again.',
        'The voice server did not confirm the selected net.',
      ];
      const bad = [];
      fatal.forEach(m => { if (!isFatalError(m)) bad.push('should be fatal: ' + m); });
      retry.forEach(m => { if (isFatalError(m)) bad.push('should retry: ' + m); });
      console.log(bad.length ? 'FAIL ' + bad.join(' | ') : 'OK');
    '''
    out = subprocess.run([node, '-e', harness, str(RADIO_JS)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    result = out.stdout.strip()
    assert result != 'MISSING', 'isFatalError/FATAL_ERRORS not found in mission-radio.js'
    assert result == 'OK', result


def test_the_error_branch_routes_through_the_classifier():
    """The handler must consult isFatalError rather than always disconnecting."""
    src = RADIO_JS.read_text()
    assert "message.type==='error'" in src
    branch = src.split("message.type==='error'", 1)[1][:120]
    assert 'handleServerError' in branch, (
        'the error branch does not go through handleServerError: ' + branch)
    assert 'connectionLost' in src.split('function handleServerError', 1)[1][:600], (
        'handleServerError never schedules a reconnect')
