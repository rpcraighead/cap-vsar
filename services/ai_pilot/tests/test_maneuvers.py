"""Maneuver boundaries tested independently of the simulator flight model."""
from dataclasses import replace
import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer

import pytest

from services.ai_pilot.maneuvers import (
    Limits, ManeuverGate, Observation, XPlaneAutopilotBackend, parse_maneuver,
)
from services.ai_pilot.maneuver_server import Handler
from services.ai_pilot.xplane_udp import XPlaneUDPClient


class Backend:
    def __init__(self):
        self.o = Observation(359, 4500, 2000, 110, 0, 0, 0)
        self.writes = []
    def observe(self): return self.o
    def select(self, heading, altitude): self.writes.append(('select', heading, altitude))
    def release(self): self.writes.append(('release',))
    def pause(self): self.writes.append(('pause',))


@pytest.fixture
def setup():
    b = Backend()
    g = ManeuverGate(b)
    lease = g.acquire()['lease']
    return b, g, lease


@pytest.mark.parametrize('text', ['do not take off', 'do not turn heading 090',
    'heading 030 not 130', 'heading 030 and descend to 3000', 'turn left heading 090',
    '045', 'KSEE runway 27r', 'cleared for takeoff', 'heading 090 true',
    'descend to 3000 feet AGL', 'heading 090; reset', 'cancel that'])
def test_ambiguous_or_unsupported_text_cannot_execute(text, setup):
    b, g, lease = setup
    with pytest.raises(ValueError):
        g.submit(lease, 1, parse_maneuver(text))
    assert not b.writes


def test_explicit_grammar():
    assert parse_maneuver('heading 090 magnetic') == {'heading_mag': 90}
    assert parse_maneuver('maintain 4500 feet indicated') == {'altitude_indicated_ft': 4500}


@pytest.mark.parametrize('fields', [{'heading_mag': 361}, {'heading_mag': -1},
    {'heading_mag': float('nan')}, {'altitude_indicated_ft': float('inf')},
    {'heading_mag': True}, {'heading_mag': '90'}, {'altitude_indicated_ft': 2000},
    {'vs_fpm': 1000}, {}, {'heading_mag': 90, 'beacon_lat': 33}])
def test_invalid_fields_no_writes(fields, setup):
    b, g, lease = setup
    with pytest.raises(ValueError): g.submit(lease, 1, fields)
    assert not b.writes


def test_stale_sample_revokes_and_pauses(setup):
    b, g, lease = setup
    b.o = replace(b.o, age_seconds=3)
    g.tick()
    assert b.writes == [('pause',)]
    assert not g.status()['owned']
    with pytest.raises(ValueError): g.submit(lease, 1, {'heading_mag': 90})


def test_takeover_and_old_lease(setup):
    b, g, lease = setup
    g.submit(lease, 1, {'heading_mag': 90})
    g.takeover()
    new_lease = g.acquire()['lease']
    assert new_lease != lease
    with pytest.raises(ValueError): g.submit(lease, 2, {'heading_mag': 180})
    assert b.writes == [('select', 90, 4500), ('release',)]


def test_replay_and_parallel_ownership_refused(setup):
    b, g, lease = setup
    with pytest.raises(ValueError): g.acquire()
    g.submit(lease, 1, {'heading_mag': 90})
    with pytest.raises(ValueError): g.submit(lease, 1, {'heading_mag': 180})
    assert len(b.writes) == 1


def test_completion_requires_stable_measured_capture(setup):
    b, g, lease = setup
    clock = [0.0]
    g.clock = lambda: clock[0]
    g.submit(lease, 1, {'heading_mag': 1})  # wrap-around error is two degrees
    g.tick()
    clock[0] = 2
    g.tick()
    assert g.status()['active']['status'] == 'executing'
    b.o = replace(b.o, roll_deg=10)
    g.tick()  # resets settling interval
    b.o = replace(b.o, roll_deg=0)
    clock[0] = 3
    g.tick()
    clock[0] = 6
    g.tick()
    assert g.status()['active'] is None
    assert g.status()['events'][-1]['status'] == 'achieved'


def test_current_terrain_descent_check(setup):
    b, g, lease = setup
    b.o = replace(b.o, agl_ft=1200)
    with pytest.raises(ValueError, match='clearance floor'):
        g.submit(lease, 1, {'altitude_indicated_ft': 3500})
    assert not b.writes


def test_backend_failure_consumes_and_revokes(setup):
    b, g, lease = setup
    def fail(*args): raise OSError('failed after one write')
    b.select = fail
    with pytest.raises(ValueError, match='Backend failure'):
        g.submit(lease, 1, {'heading_mag': 90})
    assert g.sequence == 1
    assert g.lease is None
    assert b.writes == [('pause',)]


def test_callback_freshness_is_per_field_and_commands_are_not_observations():
    c = XPlaneUDPClient(mock=True)
    clock = [10.0]
    backend = XPlaneAutopilotBackend(c, clock=lambda: clock[0])
    gate = ManeuverGate(backend)
    with pytest.raises(ValueError): gate.acquire()
    for name, value in dict(heading_mag=90, altitude_indicated_ft=4500,
                            agl_ft=2000/3.28084, kias=110, roll_deg=0, vvi_fpm=0).items():
        c.set_mock_dref(backend.DATAREFS[name], value)
    c.set_mock_dref('sim/cockpit/autopilot/autopilot_state', 0)
    lease = gate.acquire()['lease']
    gate.submit(lease, 1, {'heading_mag': 180})
    assert backend.observe().heading_mag == 90
    clock[0] = 13
    c.set_mock_dref(backend.DATAREFS['heading_mag'], 180)
    assert backend.observe().age_seconds == 3
    gate.tick()
    assert not gate.lease


def test_missing_live_observations_renew_subscriptions_without_duplicate_callbacks():
    c = XPlaneUDPClient(mock=True)
    clock = [10.0]
    calls = []
    original_subscribe = c.subscribe_dref

    def record(ref, freq_hz=10, callback=None):
        calls.append((ref, callback))
        return original_subscribe(ref, freq_hz=freq_hz, callback=callback)

    c.subscribe_dref = record
    backend = XPlaneAutopilotBackend(c, clock=lambda: clock[0])
    initial_count = len(calls)
    assert initial_count == len(backend.subscriptions)
    assert all(callback is not None for _, callback in calls)

    clock[0] = 10.5
    backend.observe()
    assert len(calls) == initial_count

    clock[0] = 11.1
    backend.observe()
    assert len(calls) == initial_count * 2
    assert all(callback is None for _, callback in calls[initial_count:])


@pytest.mark.parametrize('target', [4000, 5000])
def test_altitude_change_uses_g1000_flc_and_knots_target(target):
    c = XPlaneUDPClient(mock=True)
    backend = XPlaneAutopilotBackend(c)
    c.set_mock_dref(backend.DATAREFS['altitude_indicated_ft'], 4500)
    c.set_mock_dref('sim/cockpit/autopilot/autopilot_state', 0)
    writes = []
    c.send_dref = lambda ref, val: writes.append((ref, val))
    c.send_command = lambda cmd: writes.append(('command', cmd))
    backend.select(90, target)
    assert [v for r, v in writes if r.endswith('/autopilot_state')] == [2]
    assert ('command', 'sim/GPS/g1000n1_flc') in writes
    assert ('sim/cockpit2/autopilot/airspeed_dial_kts', 110) in writes
    assert writes.index(('sim/cockpit2/autopilot/altitude_dial_ft', target)) < writes.index(('command', 'sim/GPS/g1000n1_flc'))
    assert not any('vvi_dial' in ref for ref, _ in writes)


def test_http_validation_and_control_cycle(setup):
    b, g, old_lease = setup
    g.takeover()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.gate = g
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    def post(path, data):
        req = Request(f'http://127.0.0.1:{server.server_port}{path}',
                      data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urlopen(req) as r: return r.status, json.load(r)
        except HTTPError as e: return e.code, json.load(e)
    try:
        assert post('/api/maneuver', [1])[0] == 400
        status, result = post('/api/acquire', {})
        assert status == 200
        lease = result['lease']
        assert post('/api/maneuver', dict(lease=lease, sequence=1, text='do not take off'))[0] == 400
        assert post('/api/maneuver', dict(lease=lease, sequence=1, text='heading 090 magnetic'))[0] == 200
        assert post('/api/takeover', {})[0] == 200
        assert post('/api/maneuver', dict(lease=lease, sequence=2, text='heading 180 magnetic'))[0] == 400
        assert post('/api/phase', {'phase': 'TAKEOFF_ROLL'})[0] == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_existing_modes_are_not_toggled_off():
    c = XPlaneUDPClient(mock=True)
    backend = XPlaneAutopilotBackend(c)
    c.set_mock_dref(backend.DATAREFS['altitude_indicated_ft'], 4500)
    c.set_mock_dref('sim/cockpit/autopilot/autopilot_state', 2 | 8 | 32)
    writes = []
    c.send_dref = lambda ref, val: writes.append((ref, val))
    c.send_command = lambda cmd: writes.append(('command', cmd))
    backend.select(100, 5000)
    assert not [r for r, v in writes if r.endswith('/autopilot_state')]
    assert not [r for r, v in writes if r == 'command']
