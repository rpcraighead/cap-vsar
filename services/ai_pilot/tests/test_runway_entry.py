"""Runway entry must remain distinct from taxi and takeoff authority."""
from services.ai_pilot.aircraft_profiles import C172SP
import unittest
import math

from services.ai_pilot.ground_guidance import GroundObservation, TaxiPoint
from services.ai_pilot.runway_entry import RunwayEntryGeometry, RunwayEntryGuidance
from services.ai_pilot.taxi import (
    ClearanceSource, RoutePurpose, TaxiCoordinator, TaxiLeg, TaxiPhase, TaxiRoute,
)


class RunwayEntryTests(unittest.TestCase):
    def setUp(self):
        taxi = TaxiCoordinator("parking", towered=True)
        taxi.load_route(TaxiRoute(RoutePurpose.OUTBOUND,
                                  (TaxiLeg("parking", "27R hold"),)))
        taxi.authorize_taxi(ClearanceSource.ATC)
        taxi.complete_leg()
        self.taxi = taxi
        geom = RunwayEntryGeometry(TaxiPoint(0, 0), TaxiPoint(0, 50),
                                   TaxiPoint(-30, 50), 270, 30)
        self.guide = RunwayEntryGuidance(taxi, geom, profile=C172SP)

    def obs(self, **change):
        values = dict(east_m=0, north_m=0, heading_true_deg=0,
                      groundspeed_mps=0, on_ground=True, paused=False)
        values.update(change)
        return GroundObservation(**values)

    def test_line_up_and_wait_stops_before_takeoff(self):
        self.assertEqual(self.guide.step(self.obs()).throttle, 0)
        self.taxi.authorize_departure_runway("27R", ClearanceSource.ATC,
                                             line_up_and_wait=True)
        self.assertGreater(self.guide.step(self.obs()).throttle, 0)
        corner = self.guide.step(self.obs(north_m=49, groundspeed_mps=1))
        self.assertEqual(corner.reason, "lineup")
        self.assertLess(corner.yaw, 0)
        done = self.guide.step(self.obs(east_m=-30, north_m=50,
                                        heading_true_deg=270))
        self.assertEqual((done.throttle, done.brake), (0., .35))
        self.assertEqual(self.taxi.phase, TaxiPhase.HOLDING_IN_POSITION)
        self.taxi.authorize_departure_runway("27R", ClearanceSource.ATC,
                                             takeoff=True)
        self.assertEqual(self.taxi.directive().action, "takeoff")

    def test_direct_takeoff_clearance_allows_lineup_but_checks_width(self):
        self.taxi.authorize_departure_runway("27R", ClearanceSource.ATC,
                                             takeoff=True)
        self.guide.step(self.obs())
        self.guide.step(self.obs(north_m=49, groundspeed_mps=1))
        stop = self.guide.step(self.obs(east_m=-20, north_m=65,
                                        heading_true_deg=270))
        self.assertEqual(stop.throttle, 0)
        self.assertIn("runway width", stop.reason)
        self.assertEqual(self.guide.step(self.obs()).throttle, 0)

    def test_close_misaligned_lineup_creeps_until_heading_gate_is_met(self):
        self.taxi.authorize_departure_runway("27R", ClearanceSource.ATC,
                                             takeoff=True)
        self.guide.step(self.obs())
        self.guide.step(self.obs(north_m=49, groundspeed_mps=1))

        align = self.guide.step(self.obs(east_m=-27.5, north_m=50,
                                         heading_true_deg=264))
        self.assertEqual(align.reason, "lineup")
        self.assertGreater(align.yaw, 0)
        self.assertGreater(align.throttle, 0)
        self.assertEqual(align.brake, 0)
        self.assertEqual(self.guide.phase, "lineup")

        slow = self.guide.step(self.obs(east_m=-27.5, north_m=50,
                                        heading_true_deg=265.5,
                                        groundspeed_mps=.8))
        self.assertEqual(slow.reason, "slow for 27R line-up")
        self.assertEqual(slow.brake, .06)
        self.assertEqual(self.guide.phase, "lineup")

        align = self.guide.step(self.obs(east_m=-27.5, north_m=50,
                                         heading_true_deg=266.5,
                                         groundspeed_mps=.3))
        self.assertEqual(align.reason, "lineup")
        braking = self.guide.step(self.obs(east_m=-27.5, north_m=50,
                                           heading_true_deg=267.2,
                                           groundspeed_mps=.8))
        self.assertEqual(braking.reason, "brake at 27R lineup point")
        done = self.guide.step(self.obs(east_m=-27.5, north_m=50,
                                        heading_true_deg=267.2,
                                        groundspeed_mps=.4))
        self.assertEqual(done.reason, "27R lineup complete")
        self.assertEqual((done.throttle, done.brake), (0., .35))
        self.assertEqual(self.guide.phase, "complete")

    def test_moving_c182_creep_uses_runway_coordinates_past_the_point(self):
        self.taxi.authorize_departure_runway("27R", ClearanceSource.ATC, takeoff=True)
        self.guide.step(self.obs())
        self.guide.step(self.obs(north_m=49, groundspeed_mps=1))
        east, north, heading, speed = -26., 50., 263., .8
        dt = .5
        final = None
        for _ in range(120):
            command = self.guide.step(self.obs(east_m=east, north_m=north,
                                               heading_true_deg=heading,
                                               groundspeed_mps=speed))
            self.assertNotIn("fault", command.reason.lower())
            if command.reason == "27R lineup complete":
                final = command
                break
            yaw_gain_deg_s = .12 / .107
            heading = (heading + command.yaw*yaw_gain_deg_s*dt) % 360.
            rad = math.radians(heading)
            east += speed*math.sin(rad)*dt
            north += speed*math.cos(rad)*dt
            if command.reason == "lineup" and speed > .3:
                speed = .3
            if command.brake > 0:
                speed = max(0., speed - .8*dt)
        self.assertIsNotNone(final)
        self.assertEqual(self.guide.phase, "complete")
        self.assertLess(abs((heading - 270. + 180.) % 360. - 180.), 3.5)
        along = -(east - self.guide.geometry.centerline_entry.east_m)
        cross = north - self.guide.geometry.centerline_entry.north_m
        self.assertGreater(along, 28.)
        self.assertLess(along, 43.)
        self.assertLess(abs(cross), 1.)
        self.assertLessEqual(speed, .5)

    def test_lineup_faults_after_along_track_stop_gate(self):
        self.taxi.authorize_departure_runway("27R", ClearanceSource.ATC, takeoff=True)
        self.guide.step(self.obs())
        self.guide.step(self.obs(north_m=49, groundspeed_mps=1))
        command = self.guide.step(self.obs(east_m=-46., north_m=50., heading_true_deg=270.))
        self.assertEqual(command.reason, "overshot the 27R line-up point")
        self.assertEqual(self.guide.phase, "lineup")

    def test_lineup_keeps_reverse_heading_capture_latch(self):
        self.taxi.authorize_departure_runway("27R", ClearanceSource.ATC, takeoff=True)
        self.guide.step(self.obs())
        self.guide.step(self.obs(north_m=49, groundspeed_mps=1))
        command = self.guide.step(self.obs(east_m=-20., north_m=50., heading_true_deg=90.))
        self.assertEqual(command.reason, "runway entry heading outside capture")
        self.assertEqual(self.guide.phase, "lineup")


if __name__ == "__main__":
    unittest.main()
