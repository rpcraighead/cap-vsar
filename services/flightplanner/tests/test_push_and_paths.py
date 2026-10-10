#!/usr/bin/env python3
"""
The V-SAR push, and where the database lives (L-9, L-12).

L-9: the push told the operator the scenario had been "broadcast to active
sortie" whether or not one was running, because it inferred that from a 400 the
console stopped returning. It also planted the beacon at sea level, on the
exact datum the crew was about to search around.

L-12: the database was bind-mounted as a FILE, so SQLite's journal and WAL -
written as siblings - landed in the container's own layer instead of on the
host volume.

    pytest services/flightplanner/tests/test_push_and_paths.py
"""
import os
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
PLANNER = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(PLANNER))
sys.path.insert(0, PLANNER)
os.environ.setdefault('CAPVSAR_PRECACHE_CHARTS', '0')
import app as flight_app                                       # noqa: E402


class Reply:
    def __init__(self, status=200, payload=None, text=''):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class BeaconTruth(unittest.TestCase):
    def test_the_beacon_is_moved_off_the_planned_datum(self):
        lat, lon = 33.1700, -117.0790
        blat, blon = flight_app.offset_beacon(lat, lon, 'CAP 487|parallel')
        self.assertNotAlmostEqual(blat, lat, places=4)
        # ...by about the configured distance, not a token nudge.
        nm = ((blat - lat) ** 2 +
              ((blon - lon) * 0.8383) ** 2) ** 0.5 * 60.0
        self.assertAlmostEqual(nm, flight_app.BEACON_OFFSET_NM, delta=0.2)

    def test_the_offset_is_stable_for_the_same_plan(self):
        a = flight_app.offset_beacon(33.17, -117.08, 'seed-one')
        b = flight_app.offset_beacon(33.17, -117.08, 'seed-one')
        c = flight_app.offset_beacon(33.17, -117.08, 'seed-two')
        self.assertEqual(a, b, 're-pushing a sortie teleported the beacon')
        self.assertNotEqual(a, c)

    def test_the_offset_can_be_switched_off(self):
        original = flight_app.BEACON_OFFSET_NM
        flight_app.BEACON_OFFSET_NM = 0.0
        try:
            self.assertEqual(flight_app.offset_beacon(33.17, -117.08, 'x'),
                             (33.17, -117.08))
        finally:
            flight_app.BEACON_OFFSET_NM = original

    def test_elevation_rejects_the_no_data_sentinel(self):
        with patch.object(flight_app.requests, 'get',
                          return_value=Reply(200, {'value': -1000000})):
            self.assertIsNone(flight_app.point_elevation_ft(33.1, -117.0))

    def test_elevation_survives_an_unreachable_service(self):
        with patch.object(flight_app.requests, 'get',
                          side_effect=flight_app.requests.RequestException('down')):
            self.assertIsNone(flight_app.point_elevation_ft(33.1, -117.0))

    def test_elevation_returns_feet(self):
        with patch.object(flight_app.requests, 'get',
                          return_value=Reply(200, {'value': 4310.5})):
            self.assertAlmostEqual(flight_app.point_elevation_ft(33.1, -117.0), 4310.5)


class PushReportsHonestly(unittest.TestCase):
    def setUp(self):
        flight_app.app.config['TESTING'] = True
        self.client = flight_app.app.test_client()
        self.body = {'pattern_type': 'parallel', 'callsign': 'CAP 487',
                     'waypoints': [{'lat': 33.17, 'lon': -117.08},
                                   {'lat': 33.20, 'lon': -117.08}]}

    def _push(self, state_payload, msg_status=200):
        def fake_post(url, **kw):
            return Reply(200, {'id': 'abc'}) if '/api/scenarios' in url \
                else Reply(msg_status, {})

        def fake_get(url, **kw):
            if 'epqs.nationalmap.gov' in url:
                return Reply(200, {'value': 4300.0})
            return Reply(200, state_payload)

        with patch.object(flight_app.requests, 'post', side_effect=fake_post), \
             patch.object(flight_app.requests, 'get', side_effect=fake_get), \
             patch.object(flight_app, '_allow_vsar_export', return_value=True), \
             patch.object(flight_app, '_request_security_error', return_value=None):
            return self.client.post('/api/sar/export-vsar', json=self.body)

    def test_no_sortie_running_is_reported_as_not_persisted(self):
        r = self._push({'sortie': None})
        data = r.get_json()
        self.assertTrue(data['message_broadcast'])
        self.assertFalse(data['message_persisted'],
                         'claimed the message was in the exercise record')
        self.assertFalse(data['sortie_running'])
        self.assertIn('NOT part of any exercise record', data['message'])

    def test_a_running_sortie_is_reported_as_persisted(self):
        r = self._push({'sortie': {'id': 'abc123', 'stopped': None}})
        data = r.get_json()
        self.assertTrue(data['message_persisted'])
        self.assertTrue(data['sortie_running'])

    def test_a_stopped_sortie_does_not_count_as_running(self):
        r = self._push({'sortie': {'id': 'abc123', 'stopped': 1234.0}})
        self.assertFalse(r.get_json()['message_persisted'])

    def test_the_pushed_beacon_is_not_on_the_datum_and_has_elevation(self):
        sent = {}

        def fake_post(url, **kw):
            if '/api/scenarios' in url:
                sent.update(kw.get('json') or {})
            return Reply(200, {'id': 'abc'})

        def fake_get(url, **kw):
            if 'epqs.nationalmap.gov' in url:
                return Reply(200, {'value': 4300.0})
            return Reply(200, {'sortie': {'id': 'x', 'stopped': None}})

        with patch.object(flight_app.requests, 'post', side_effect=fake_post), \
             patch.object(flight_app.requests, 'get', side_effect=fake_get), \
             patch.object(flight_app, '_allow_vsar_export', return_value=True), \
             patch.object(flight_app, '_request_security_error', return_value=None):
            self.client.post('/api/sar/export-vsar', json=self.body)

        self.assertNotAlmostEqual(sent['beacon_lat'], 33.17, places=4)
        self.assertAlmostEqual(sent['beacon_elev_ft'], 4300.0)
        # The alert - what the crew is briefed on - is the centre of the search
        # area (L2-6): here the middle of a two-point box, not its first point.
        self.assertAlmostEqual(sent['alert_lat'], 33.185, places=6)

    def test_an_explicit_search_centre_wins(self):
        sent = {}

        def fake_post(url, **kw):
            if '/api/scenarios' in url:
                sent.update(kw.get('json') or {})
            return Reply(200, {'id': 'abc'})

        body = dict(self.body, search_centre={'lat': 33.4, 'lon': -117.3})
        with patch.object(flight_app.requests, 'post', side_effect=fake_post), \
             patch.object(flight_app.requests, 'get',
                          side_effect=lambda url, **kw: Reply(200, {'value': 100.0})), \
             patch.object(flight_app, '_allow_vsar_export', return_value=True), \
             patch.object(flight_app, '_request_security_error', return_value=None):
            self.client.post('/api/sar/export-vsar', json=body)
        self.assertAlmostEqual(sent['alert_lat'], 33.4, places=6)
        self.assertAlmostEqual(sent['alert_lon'], -117.3, places=6)


class DatabaseLivesInADirectory(unittest.TestCase):
    def test_the_database_path_is_inside_a_directory_not_a_bare_file(self):
        self.assertTrue(os.path.dirname(flight_app.DATABASE_PATH))

    def test_compose_mounts_the_directory(self):
        compose = open(os.path.join(ROOT, 'docker-compose.yml'),
                       encoding='utf-8').read()
        self.assertIn('./services/flightplanner/data:/app/data', compose)
        self.assertNotIn('/aviation_data.db:/app/aviation_data.db', compose,
                         'still mounting the database as a single file')
        self.assertIn('DATABASE_PATH: /app/data/aviation_data.db', compose)

    def test_the_journal_would_land_beside_the_database(self):
        """SQLite writes <db>-wal and <db>-journal as siblings; both must be
        inside the mounted directory, not next to it."""
        d = os.path.dirname(os.path.abspath(flight_app.DATABASE_PATH))
        for suffix in ('-wal', '-journal'):
            self.assertEqual(
                os.path.dirname(os.path.abspath(flight_app.DATABASE_PATH + suffix)), d)


if __name__ == '__main__':
    unittest.main(verbosity=2)
