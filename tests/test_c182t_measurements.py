"""Donor-free metrology regression tests; optional live-donor test is explicit."""
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import measure_c182t as m
from convert_flightgear_c182 import AC3DParser
from tests.test_flightgear_c182 import SIMPLE_AC3D

FIXTURE=Path(__file__).parent/'fixtures/c182t_landmarks.json'

class Measurements(unittest.TestCase):
    def setUp(self):
        self.f=json.loads(FIXTURE.read_text())
        self.master=json.loads(m.MASTER.read_text())

    def result(self):return m.report(self.f,self.master)

    def test_fixture_targets_and_hard_prop_bound(self):
        r=self.result();c={x['id']:x for x in r['comparisons']}
        self.assertEqual(r['donor_commit'], self.f['donor_commit'])
        self.assertEqual(r['corrections_applied'], self.f['corrections_applied'])
        self.assertEqual(len(c),10)
        # A-1 stage 3: the propeller correction closed this certification bound.
        # It measured 79.255 in at stage 2, outside the TCDS 77.5-79.0 band.
        self.assertEqual(c['propeller_diameter']['status'],'pass')
        self.assertAlmostEqual(c['propeller_diameter']['measured']['in'],79.0,places=2)
        self.assertLessEqual(c['propeller_diameter']['measured']['in'],79.0)
        # Closed 2026-09-15 by main_wheel_track_to_poh, after settling the
        # POH reading as centre-to-centre by inference - see that correction's
        # rationale, which records that it was NOT read off the drawing.
        self.assertEqual(c['main_wheel_track']['status'],'pass')
        self.assertAlmostEqual(c['main_wheel_track']['measured']['in'],108.0,places=2)
        # Closed 2026-09-15 by horizontal_tail_span_to_poh: a region transform
        # on the tail with the root as a fixed point. Was 'fail' at +2.16%.
        self.assertEqual(c['horizontal_tail_span']['status'],'pass')
        self.assertAlmostEqual(c['horizontal_tail_span']['measured']['in'],140.0,places=2)
        # The wings must be untouched by that transform - they live in the same
        # object as the stabiliser tip caps, which is what blocked it before.
        self.assertEqual(c['wing_span']['numeric_result'],'within_bounds')
        self.assertEqual(c['wing_span']['status'],'provisional')
        self.assertEqual(c['wing_span']['numeric_result'],'within_bounds')
        self.assertEqual(c['propeller_ground_clearance']['numeric_result'],'within_bounds')
        self.assertEqual(c['overall_height']['numeric_result'],'outside_bounds')
        self.assertFalse(r['release_acceptance'])

    def test_nine_unknowns_have_no_invented_values(self):
        r=self.result()
        self.assertEqual(len(r['unknowns']),9)
        for u in r['unknowns']:
            self.assertEqual(u['status'],'unmeasured');self.assertIsNone(u['measured'])
        self.assertEqual(len(r['stations']),15)
        self.assertTrue(all(s['measured'] is None for s in r['stations']))

    def test_missing_landmark_fails(self):
        del self.f['landmarks']['spinner_apex']
        with self.assertRaisesRegex(ValueError,'landmark'): self.result()

    def test_missing_named_object_fails_strict_parser_pipeline(self):
        root=AC3DParser(SIMPLE_AC3D).parse()
        with self.assertRaisesRegex(ValueError,'Required landmark objects missing'):
            m.extract([o for o in m.converter.flatten(root) if o.surfaces])

    def test_broken_symmetry_fails(self):
        self.f['landmarks']['main_right_axle']['point_m'][0]+=.05
        with self.assertRaisesRegex(ValueError,'symmetry'): self.result()

    def test_ground_pose_rotates_nose_contact_onto_main_plane(self):
        angle,pivot,pose=m.pose_for(self.f['landmarks'])
        self.assertGreater(abs(angle),.05)
        self.assertAlmostEqual(pose(self.f['landmarks']['nose_contact']['point_m'])[1],0,places=12)
        self.assertAlmostEqual(pose(pivot)[1],0,places=12)
        self.assertLess(self.result()['ground_pose']['main_contact_residual_m'],.001)

    def test_propeller_bound_not_percentage_tolerance(self):
        for inches in (77.49,77.5,78,79,79.01):
            self.f['prop_radius_m']=inches*.0254/2
            c=next(c for c in self.result()['comparisons'] if c['id']=='propeller_diameter')
            self.assertEqual(c['status'],'pass' if 77.5<=inches<=79 else 'fail')

    def test_accepted_dimension_regression_fails(self):
        # Synthetic accepted prop, then a regression beyond the certification bound.
        self.f['prop_radius_m']=78*.0254/2
        m.assert_accepted(self.result(),['propeller_diameter'])
        self.f['prop_radius_m']=79.1*.0254/2
        with self.assertRaisesRegex(ValueError,'Accepted dimension regression'):
            m.assert_accepted(self.result(),['propeller_diameter'])

    def test_no_cache_access_in_fixture_report(self):
        with patch.object(m,'load_donor',side_effect=AssertionError('donor accessed')):
            r=self.result()
        self.assertEqual(r['aircraft'],'CAP 487')

    def test_bad_pin_and_nonfinite_values_fail(self):
        self.f['donor_archive_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'pin'):self.result()
        self.f=json.loads(FIXTURE.read_text())
        self.f['prop_radius_m']=float('nan')
        with self.assertRaisesRegex(ValueError,'radius'):self.result()

    def test_bounds_do_not_confuse_strobe_and_billboard(self):
        b=self.f['bounds']
        self.assertNotIn('Strobe',b['all_rendered']['objects'])
        self.assertIn('NavLightGreen',b['all_rendered']['objects'])
        self.assertNotIn('NavLightGreen',b['structural']['objects'])
        self.assertGreater(b['all_rendered']['bounds_m'][0][1], b['structural']['bounds_m'][0][1])

    def test_deterministic_json_and_overlays(self):
        with tempfile.TemporaryDirectory() as name:
            d=Path(name);m.write_overlays(self.result(),d)
            first={p.name:p.read_bytes() for p in d.iterdir()}
            m.write_overlays(self.result(),d)
            self.assertEqual(first,{p.name:p.read_bytes() for p in d.iterdir()})
            self.assertEqual(set(first),{'side.svg','front.svg','top.svg'})
            self.assertNotIn(b'no mesh correction', first['side.svg'])

    @unittest.skipUnless(os.environ.get('CAPVSAR_TEST_LIVE_DONOR'), 'optional explicit live donor comparison')
    def test_fixture_matches_live_donor(self):
        # Core tests above never skip. Set env only for this separate integration check.
        objects,applied=m.load_donor(Path(os.environ['CAPVSAR_TEST_LIVE_DONOR']))
        live=m.extract(objects,applied)
        self.assertEqual(json.loads(json.dumps(live)),self.f)


class PersistentCacheTests(unittest.TestCase):
    def test_defaults_are_durable(self):
        import fetch_flightgear_c182 as fetch
        self.assertEqual(fetch.DEFAULT_DONOR.parent,Path.home()/'.cache/capvsar')
        self.assertEqual(fetch.DEFAULT_ARCHIVE.parent,fetch.DEFAULT_DONOR.parent)

    def test_bad_cached_archive_rejected_before_extraction(self):
        import fetch_flightgear_c182 as fetch
        with tempfile.TemporaryDirectory() as name:
            archive=Path(name)/'bad.tar.gz';archive.write_bytes(b'bad archive')
            with patch.object(fetch,'DEFAULT_ARCHIVE',archive),patch.object(fetch,'_extract_archive') as extract:
                with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                    fetch.fetch_donor(Path(name)/'donor')
                extract.assert_not_called()

if __name__=='__main__':unittest.main()
