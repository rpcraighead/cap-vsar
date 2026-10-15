"""Runway entry must remain distinct from taxi and takeoff authority."""
from services.ai_pilot.aircraft_profiles import C172SP
import unittest

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


if __name__ == "__main__":
    unittest.main()
