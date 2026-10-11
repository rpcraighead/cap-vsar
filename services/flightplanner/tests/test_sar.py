#!/usr/bin/env python3
"""
Unit tests for Civil Air Patrol Search & Rescue (SAR) pattern algorithms
and X-Plane 12 .FMS export in CAP 487 Flight Planner.
"""
import unittest
import fcntl
import inspect
import math
import sys
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import types
for mod in ['flask', 'requests']:
    try:
        __import__(mod)
    except ImportError:
        m = types.ModuleType(mod)
        if mod == 'flask':
            m.Flask = lambda *args, **kwargs: type('App', (), {'route': lambda *a, **kw: lambda fn: fn, 'run': lambda *a, **kw: None})()
            m.request = type('Req', (), {'json': {}})()
            m.jsonify = lambda d: d
            m.send_from_directory = lambda *a, **kw: None
            m.render_template = lambda *a, **kw: ''
            m.abort = lambda *a, **kw: None
        elif mod == 'requests':
            m.get = lambda *a, **kw: type('Resp', (), {'status_code': 200, 'content': b'', 'json': lambda: {}})()
            m.post = lambda *a, **kw: type('Resp', (), {'status_code': 200, 'json': lambda: {}})()
        sys.modules[mod] = m

from app import (
    destination_point,
    generate_expanding_square,
    generate_creeping_line,
    generate_parallel_track,
    generate_xplane_fms_content,
    gc_dist,
    bearing
)
import app as flight_app

class TestSARPatterns(unittest.TestCase):

    def test_destination_point_cardinal(self):
        # 60 NM North from 33.0, -117.0 should increase latitude by ~1 degree (60 nm per deg)
        lat2, lon2 = destination_point(33.0, -117.0, 60.0, 0.0)
        self.assertAlmostEqual(lat2, 34.0, delta=0.05)
        self.assertAlmostEqual(lon2, -117.0, delta=0.01)

    def test_destination_point_distance_accuracy(self):
        # Go 10 NM at 045 deg, measure gc_dist back
        lat0, lon0 = 33.17, -117.0792
        lat1, lon1 = destination_point(lat0, lon0, 10.0, 45.0)
        measured_dist = gc_dist(lat0, lon0, lat1, lon1)
        measured_brg = bearing(lat0, lon0, lat1, lon1)
        self.assertAlmostEqual(measured_dist, 10.0, places=2)
        self.assertAlmostEqual(measured_brg, 45.0, delta=0.5)

    def test_expanding_square_geometry(self):
        datum_lat, datum_lon = 33.17, -117.0792
        spacing = 1.0
        legs = 8
        wpts = generate_expanding_square(datum_lat, datum_lon, spacing_nm=spacing, num_legs=legs, initial_heading=0.0, turn_dir='right')
        
        # Point 0 is DATUM, plus 8 leg endpoints = 9 points total
        self.assertEqual(len(wpts), 9)
        self.assertEqual(wpts[0]['identifier'], 'DATUM')
        self.assertEqual(wpts[1]['identifier'], 'SS01')
        self.assertEqual(wpts[8]['identifier'], 'SS08')

        # Check leg length progression: 1, 1, 2, 2, 3, 3, 4, 4 * spacing
        expected_lengths = [0.0, 1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 4.0, 4.0]
        actual_lengths = [w['leg_dist_nm'] for w in wpts]
        self.assertEqual(actual_lengths, expected_lengths)

        # Check headings: 000, 090, 180, 270, 000, 090, 180, 270
        expected_headings = [0.0, 0.0, 90.0, 180.0, 270.0, 0.0, 90.0, 180.0, 270.0]
        actual_headings = [w['heading_true'] for w in wpts]
        self.assertEqual(actual_headings, expected_headings)

    def test_expanding_square_left_turns(self):
        datum_lat, datum_lon = 33.17, -117.0792
        wpts = generate_expanding_square(datum_lat, datum_lon, spacing_nm=1.0, num_legs=4, initial_heading=0.0, turn_dir='left')
        # Left turns: 000 -> 270 -> 180 -> 090
        expected_headings = [0.0, 0.0, 270.0, 180.0, 90.0]
        actual_headings = [w['heading_true'] for w in wpts]
        self.assertEqual(actual_headings, expected_headings)

    def test_creeping_line_generation(self):
        start_lat, start_lon = 33.10, -117.20
        end_lat, end_lon = 33.25, -117.00
        wpts = generate_creeping_line(start_lat, start_lon, end_lat, end_lon, sweep_width_nm=4.0, spacing_nm=1.0, max_legs=4)
        
        # 4 sweeps = 8 waypoints
        self.assertEqual(len(wpts), 8)
        self.assertEqual(wpts[0]['identifier'], 'CS01')
        self.assertEqual(wpts[-1]['identifier'], 'CS08')

    def test_parallel_track_generation(self):
        corner_lat, corner_lon = 33.15, -117.10
        wpts = generate_parallel_track(corner_lat, corner_lon, length_nm=4.0, width_nm=3.0, axis_heading=90.0, spacing_nm=1.0)
        self.assertGreaterEqual(len(wpts), 5)
        self.assertEqual(wpts[0]['identifier'], 'PS01')

    @patch('app.get_airport', return_value={'latitude': 32.8262, 'longitude': -116.9724, 'elevation': 388})
    def test_xplane_fms_export(self, airport):
        wpts = [
            {'identifier': 'SS01', 'lat': 33.1866, 'lon': -117.0792},
            {'identifier': 'SS02', 'lat': 33.1866, 'lon': -117.0593}
        ]
        with patch('app.get_utc_now', return_value=datetime(2026, 9, 8, tzinfo=timezone.utc)):
            fms = generate_xplane_fms_content('KSEE', 'KCRQ', wpts, cruise_alt=5500)
        
        self.assertIn("1100 Version", fms)
        self.assertIn("CYCLE 2609", fms)
        self.assertIn("ADEP KSEE", fms)
        self.assertIn("ADES KCRQ", fms)
        self.assertIn("28 SS01 DRCT 5500.000000 33.186600 -117.079200", fms)
        self.assertIn("28 SS02 DRCT 5500.000000 33.186600 -117.059300", fms)
        self.assertNotIn('\r', fms)
        self.assertTrue(fms.endswith('\n'))

    @patch('app.get_airport', return_value={'latitude': 32.8262, 'longitude': -116.9724, 'elevation': 388})
    def test_xplane_fms_waypoint_record_structure(self, airport):
        wpts = [
            {'identifier': 'DATUM', 'lat': 33.1700, 'lon': -117.0792},
            {'identifier': 'SS01', 'lat': 33.1866, 'lon': -117.0792}
        ]
        fms = generate_xplane_fms_content('KSEE', 'KCRQ', wpts, cruise_alt=5500)
        lines = fms.splitlines()
        numenr_index = next(i for i, line in enumerate(lines) if line.startswith('NUMENR '))
        records = lines[numenr_index + 1:]
        waypoint_records = records[1:-1]

        self.assertEqual(int(lines[numenr_index].split()[1]), len(records))
        self.assertEqual(len(records), len(wpts) + 2)
        for record in waypoint_records:
            fields = record.split()
            self.assertEqual(len(fields), 6)
            self.assertEqual(fields[0], '28')
            self.assertEqual(fields[2], 'DRCT')
            self.assertEqual(fields[3], '5500.000000')

    def test_fms_unknown_airports_return_json_400(self):
        for role, departure, destination, results in (
            ('ADEP', 'UNKNOWN', 'KSEE', [None]),
            ('ADES', 'KSEE', 'UNKNOWN', [{'latitude': 32.8, 'longitude': -117, 'elevation': 388}, None]),
        ):
            with self.subTest(role=role), patch('app.get_airport', side_effect=results):
                response = flight_app.app.test_client().post('/api/sar/export-fms', json={
                    'departure': departure, 'destination': destination,
                    'waypoints': [{'identifier': 'DATUM', 'lat': 33.17, 'lon': -117.079}],
                })
                self.assertEqual(response.status_code, 400)
                self.assertIn(role, response.json['error'])
                self.assertIn('UNKNOWN', response.json['error'])
                self.assertNotIn('content', response.json)

    @patch('app.get_airport', return_value={'latitude': 32.8262, 'longitude': -116.9724, 'elevation': 388})
    def test_fms_sanitizes_labels_without_changing_coordinates(self, airport):
        text = generate_xplane_fms_content('KSEE', 'KSEE', [
            {'identifier': 'ss04\n1 FAKE', 'lat': 33.123456, 'lon': -117.654321},
            {'identifier': '', 'lat': 33.123456, 'lon': -117.654321},
        ])
        records = [line.split() for line in text.splitlines() if line.startswith('28 ')]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][1], 'SS04_1_FAKE')
        for record in records:
            self.assertEqual(len(record), 6)
            self.assertEqual(record[4:], ['33.123456', '-117.654321'])
        self.assertIn('1 KSEE ADEP 388.0 32.826200 -116.972400', text)

    def test_parallel_four_nm_box_has_four_centered_tracks(self):
        points = generate_parallel_track(0, 0, 4, 4, 0, 1)
        self.assertEqual(len(points), 8)
        offsets = [gc_dist(0, 0, 0, point['lon']) for point in points[::2]]
        for actual, expected in zip(offsets, (0.5, 1.5, 2.5, 3.5)):
            self.assertAlmostEqual(actual, expected, delta=0.01)
        self.assertAlmostEqual(offsets[-1] + 0.5, 4, delta=0.01)
        self.assertTrue(all('heading_mag' in point for point in points))

    def test_parallel_fractional_width_rounds_up(self):
        self.assertEqual(len(generate_parallel_track(0, 0, 4, 4.1, 0, 1)), 10)
        self.assertEqual(len(generate_parallel_track(0, 0, 4, 0.4, 0, 1)), 2)

    def test_creeping_coverage_flag_and_headings(self):
        response = flight_app.app.test_client().post('/api/sar/generate-pattern', json={
            'pattern_type': 'creeping_line', 'datum_lat': 0, 'datum_lon': 0,
            'end_lat': 0.2, 'end_lon': 0, 'spacing_nm': 1, 'num_legs': 2,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['coverage_truncated'])
        self.assertTrue(all('heading_mag' in point for point in response.json['waypoints']))

    def test_cruise_interpolates_altitude_and_rpm(self):
        result = flight_app.get_cruise(5000, 2350, 20.5)
        self.assertAlmostEqual(result['true_airspeed'], (124 + 128 + 126 + 131 + 128 + 133 + 130 + 135) / 8)
        self.assertAlmostEqual(result['fuel_flow_gph'], (10.7 + 11.4 + 11.1 + 11.7 + 11.0 + 11.7 + 11.4 + 12.1) / 8)

    def test_impossible_headwind_and_tailwind(self):
        with self.assertRaisesRegex(ValueError, 'ground speed'):
            flight_app.wind_corr(0, 90, 0, 100)
        self.assertEqual(flight_app.wind_corr(0, 90, 180, 20)[1], 110)
        with self.assertRaisesRegex(ValueError, 'Crosswind'):
            flight_app.wind_corr(0, 90, 90, 100)

    def test_impossible_route_returns_error_not_zero_fuel(self):
        airport = lambda ident: (0 if ident == 'START' else 1, 0, 'airport', {'elevation': 0})
        with patch('app.get_coords', side_effect=airport), patch('app.get_cruise', return_value={
            'true_airspeed': 90, 'fuel_flow_gph': 9,
        }), patch('app.fetch_winds_aloft', return_value={'levels': {6500: {'direction': 0, 'speed': 100}}}):
            response = flight_app.app.test_client().post('/api/calculate-route', json={
                'departure': 'START', 'destination': 'END',
            })
        self.assertEqual(response.status_code, 400)
        self.assertIn('ground speed', response.json['error'])
        self.assertNotIn('totals', response.json)

    def test_runway_tailwind_increases_distance(self):
        self.assertEqual(flight_app.calc_takeoff(3100, 0, 20, -4)['ground_roll'], int(825 * 1.2))
        self.assertEqual(flight_app.calc_landing(0, 20, -4)['ground_roll'], int(600 * 1.2))

    def test_cap487_poh_sample_and_cg_envelope(self):
        self.assertEqual(flight_app.DEFAULT_AIRCRAFT, 'CAP 487')
        aircraft = flight_app.AIRCRAFT_DATABASE['CAP 487']
        self.assertEqual((aircraft['usable_fuel'], aircraft['max_takeoff_weight']), (87, 3100))
        client = flight_app.app.test_client()
        empty = client.post('/api/weight-balance', json={}).json
        self.assertEqual((empty['total_weight'], empty['moment_1000']), (1924, 70.9))
        for weight, forward in ((2250, 33), (2475, 34.25), (2700, 35.5), (2900, 38.2), (3100, 40.9)):
            result = client.post('/api/weight-balance', json={'empty_weight': weight, 'empty_moment': weight * 42 / 1000}).json
            self.assertAlmostEqual(result['cg_forward_limit'], forward)
        loaded = client.post('/api/weight-balance', json={'pilot_weight': 180, 'fuel_gallons': 87}).json
        self.assertEqual(loaded['total_weight'], 2626)
        self.assertAlmostEqual(loaded['moment_1000'], 101.8)

    def test_cap487_cruise_and_endurance_from_poh(self):
        cruise = flight_app.get_cruise(6000, 2400, 20)
        self.assertEqual((cruise['power_percent'], cruise['true_airspeed'], cruise['fuel_flow_gph']), (65, 130, 11.4))
        with self.assertRaises(ValueError):
            flight_app.get_cruise(6000, 2500, 20)
        with self.assertRaisesRegex(ValueError, '80%'):
            flight_app.get_cruise(4000, 2400, 24)
        airport = (33, -117, 'airport', {'elevation': 0})
        with patch('app.get_coords', return_value=airport), patch('app.fetch_winds_aloft', return_value={'levels': {6000: {'direction': 0, 'speed': 0}}}):
            response = flight_app.app.test_client().post('/api/calculate-route', json={
                'departure': 'KSEE', 'destination': 'KSEE', 'cruise_altitude': 6000,
                'rpm': 2400, 'manifold_pressure': 20,
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['full_fuel_endurance_hours'], 6.66)
        self.assertGreaterEqual(response.json['full_fuel_endurance_hours'], 5.5)
        self.assertEqual(response.json['totals']['taxi_fuel'], 1.7)

    def test_exercise_page_uses_182t_defaults(self):
        html = flight_app.app.test_client().get('/').get_data(as_text=True)
        self.assertNotIn('N499CP', html)
        self.assertIn('id="wb-empty-weight" value="1924"', html)
        self.assertIn('id="wb-fuel" value="87" max="87"', html)
        self.assertIn('id="mp-select"', html)

    def test_doc_pages_do_not_carry_the_real_172s_registration(self):
        """The planner computes CAP 487 182T figures only; N499CP is a real 172S.

        The index page is covered above. The rendered doc pages share
        templates/guide.html, which was missed by the L-7 rename.
        """
        client = flight_app.app.test_client()
        for slug in flight_app.DOCS:
            with self.subTest(slug=slug):
                html = client.get(f'/guide/{slug}').get_data(as_text=True)
                self.assertNotIn('N499CP', html)
                self.assertIn('CAP 487 Flight Planner', html)

    def test_runway_outside_table_is_json_error(self):
        client = flight_app.app.test_client()
        for endpoint in ('takeoff', 'landing'):
            for data in ({'pressure_altitude': 7000}, {'temperature': 45}, {'headwind': -11}):
                with self.subTest(endpoint=endpoint, data=data):
                    response = client.post('/api/performance/' + endpoint, json=data)
                    self.assertEqual(response.status_code, 400)
                    self.assertIn('error', response.json)


class TestSARRequestBounds(unittest.TestCase):
    def setUp(self):
        # These tests call handlers directly with a request double. Keep the
        # JSON boundary a double too, whether or not Flask is installed.
        self.enterContext(patch.object(flight_app, 'jsonify', side_effect=lambda value: value))

    @staticmethod
    def request(payload):
        return types.SimpleNamespace(
            json=payload,
            get_json=lambda **kw: payload,
            get_data=lambda: b'{}',
            is_json=True,
            headers={'Origin': 'http://localhost'},
            host_url='http://localhost/',
            remote_addr='127.0.0.1',
        )

    def test_parallel_track_rejects_oversized_dimensions_by_name(self):
        for field in ('length_nm', 'width_nm'):
            payload = {
                'pattern_type': 'parallel_track',
                'datum': '@33.17,-117.08',
                'spacing_nm': 1.0,
                'length_nm': 5.0,
                'width_nm': 4.0,
                field: 51.0,
            }
            with self.subTest(field=field), patch.object(
                    flight_app, 'request', self.request(payload)):
                body, status = flight_app.sar_generate()
                self.assertEqual(status, 400)
                self.assertIn(field, body['error'])

    def test_parallel_track_rejects_excessive_sweep_count(self):
        payload = {
            'pattern_type': 'parallel_track',
            'datum': '@33.17,-117.08',
            'spacing_nm': 0.1,
            'length_nm': 5.0,
            'width_nm': 30.0,
        }
        with patch.object(flight_app, 'request', self.request(payload)):
            body, status = flight_app.sar_generate()
        self.assertEqual(status, 400)
        self.assertIn('width_nm', body['error'])
        self.assertIn('sweeps', body['error'])


class TestAviationDatabaseUpdateLock(unittest.TestCase):
    def test_second_worker_does_not_start_a_database_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, 'aviation.update.lock')
            with open(lock_path, 'a+') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(flight_app, 'DATABASE_UPDATE_LOCK_PATH', lock_path,
                                  create=True), patch.object(
                                      flight_app.threading, 'Thread') as thread:
                    started = flight_app.start_database_update()
                self.assertFalse(started)
                thread.assert_not_called()

    def test_database_row_errors_are_logged(self):
        source = inspect.getsource(flight_app.download_database)
        self.assertNotIn('except: pass', source)
        self.assertIn('log_msg(', source)

    def test_update_progress_is_shared_between_workers(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
                flight_app, 'DATABASE_UPDATE_STATUS_PATH',
                os.path.join(tmp, 'aviation.update.json')):
            flight_app._publish_update_status(
                in_progress=True, progress=40, message='Downloading runways...')
            local_status = flight_app.update_status
            try:
                flight_app.update_status = {
                    'in_progress': False, 'progress': 0, 'message': ''}
                self.assertEqual(flight_app._read_update_status(), {
                    'in_progress': True, 'progress': 40,
                    'message': 'Downloading runways...'})
            finally:
                flight_app.update_status = local_status


class TestPlannerSecurity(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(flight_app, 'jsonify', side_effect=lambda value: value))
        self.enterContext(patch.object(flight_app.requests, 'get', return_value=types.SimpleNamespace(
            status_code=200, json=lambda: {'authenticated': True, 'role': 'instructor'})))
        if hasattr(flight_app, '_vsar_export_attempts'):
            flight_app._vsar_export_attempts.clear()

    @staticmethod
    def request(payload=None, *, origin='http://localhost', is_json=True,
                token='caller-key', remote_addr='127.0.0.1'):
        headers = {}
        if origin is not None:
            headers['Origin'] = origin
        if token is not None:
            headers['X-CAPVSAR-Token'] = token
        return types.SimpleNamespace(
            cookies={},
            json=payload,
            get_json=lambda **kw: payload,
            get_data=lambda: b'{}',
            is_json=is_json,
            headers=headers,
            host_url='http://localhost/',
            remote_addr=remote_addr,
        )

    @staticmethod
    def export_payload(**overrides):
        payload = {
            'pattern_type': 'parallel_track',
            'callsign': 'CAP499',
            'departure': 'KSEE',
            'destination': 'KCRQ',
            'waypoints': [{'lat': 33.17, 'lon': -117.0792}],
        }
        payload.update(overrides)
        return payload

    @staticmethod
    def response(status=200, text='ok'):
        return types.SimpleNamespace(status_code=status, text=text)

    def test_database_update_rejects_plain_form_post(self):
        req = self.request({}, is_json=False)
        with patch.object(flight_app, 'request', req), patch.object(
                flight_app, 'start_database_update') as start:
            body, status = flight_app.trigger_update()
        self.assertEqual(status, 415)
        self.assertIn('JSON', body['error'])
        start.assert_not_called()

    def test_database_update_rejects_cross_origin_json(self):
        req = self.request({}, origin='https://attacker.example')
        with patch.dict(os.environ, {'CAPVSAR_TOKEN_INSTRUCTOR': 'instructor-key'}), \
                patch.object(flight_app, 'request', req), patch.object(
                    flight_app, 'start_database_update') as start:
            body, status = flight_app.trigger_update()
        self.assertEqual(status, 403)
        self.assertIn('same-origin', body['error'])
        start.assert_not_called()

    def test_export_rejects_oversized_free_text_by_field(self):
        for field, maximum in (('callsign', 24), ('pattern_type', 40),
                               ('departure', 8), ('destination', 8)):
            req = self.request(self.export_payload(**{field: 'X' * (maximum + 1)}))
            with self.subTest(field=field), patch.object(
                    flight_app, 'request', req), patch.object(
                        flight_app.requests, 'post') as post:
                body, status = flight_app.sar_export_vsar()
                self.assertEqual(status, 400)
                self.assertIn(field, body['error'])
                post.assert_not_called()

    def test_export_forwards_caller_token_to_both_console_writes(self):
        req = self.request(self.export_payload())
        with patch.dict(os.environ, {
                'CAPVSAR_TOKEN_INSTRUCTOR': 'instructor-key',
                'CAPVSAR_TOKEN_BASE': 'base-key',
        }), patch.object(flight_app, 'request', req), patch.object(
                flight_app.requests, 'post', side_effect=[self.response(), self.response()]) as post:
            body = flight_app.sar_export_vsar()
        self.assertTrue(body['success'])
        self.assertEqual(post.call_args_list[0].kwargs['headers'],
                         {'X-CAPVSAR-Token': 'caller-key'})
        self.assertEqual(post.call_args_list[1].kwargs['headers'],
                         {'X-CAPVSAR-Token': 'caller-key'})

    def test_export_reports_an_instructor_token_rejection(self):
        req = self.request(self.export_payload())
        with patch.dict(os.environ, {'CAPVSAR_TOKEN_INSTRUCTOR': 'wrong-key'}), \
                patch.object(flight_app, 'request', req), patch.object(
                    flight_app.requests, 'post', return_value=self.response(403, 'forbidden')):
            body, status = flight_app.sar_export_vsar()
        self.assertEqual(status, 403)
        self.assertIn('denied scenario creation', body['error'])

    def test_export_is_rate_limited_per_client(self):
        req = self.request(self.export_payload(), remote_addr='192.0.2.10')
        with patch.object(flight_app, 'request', req), patch.object(
                flight_app.requests, 'post', return_value=self.response()):
            flight_app._vsar_export_attempts.clear()
            for _ in range(flight_app.VSAR_EXPORT_RATE_LIMIT):
                response = flight_app.sar_export_vsar()
                self.assertTrue(response['success'])
            body, status = flight_app.sar_export_vsar()
        self.assertEqual(status, 429)
        self.assertIn('rate limit', body['error'].lower())

if __name__ == '__main__':
    unittest.main()
