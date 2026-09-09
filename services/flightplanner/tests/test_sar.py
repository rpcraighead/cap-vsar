#!/usr/bin/env python3
"""
Unit tests for Civil Air Patrol Search & Rescue (SAR) pattern algorithms
and X-Plane 12 .FMS export in N499CP Flight Planner.
"""
import unittest
import math
import sys
import os
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

    def test_xplane_fms_export(self):
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
        self.assertIn("28 +33.187_-117.079 DRCT 5500.000000 33.186600 -117.079200", fms)
        self.assertIn("28 +33.187_-117.059 DRCT 5500.000000 33.186600 -117.059300", fms)
        self.assertNotIn('\r', fms)
        self.assertTrue(fms.endswith('\n'))

    def test_xplane_fms_waypoint_record_structure(self):
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

if __name__ == '__main__':
    unittest.main()
