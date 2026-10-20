"""Taxi guidance must honor authority, physical corridor and stop boundaries."""
from services.ai_pilot.aircraft_profiles import C172SP
import unittest

from services.ai_pilot.ground_guidance import (
    GroundObservation, TaxiGuidance, TaxiPoint,
)
from services.ai_pilot.taxi import (
    ClearanceSource, RoutePurpose, TaxiCoordinator, TaxiLeg, TaxiPhase, TaxiRoute,
)


class TaxiGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.taxi = TaxiCoordinator("ramp", towered=True)
        self.route = TaxiRoute(RoutePurpose.OUTBOUND, (TaxiLeg("ramp", "hold short"),))
        self.taxi.load_route(self.route)
        self.guide = TaxiGuidance(self.taxi, self.route,
                                  {"ramp":TaxiPoint(0,0),
                                   "hold short":TaxiPoint(0,100)}, profile=C172SP)

    def observation(self, **changes):
        values = dict(east_m=0, north_m=0, heading_true_deg=0,
                      groundspeed_mps=0, on_ground=True, paused=False)
        values.update(changes)
        return GroundObservation(**values)

    def test_taxi_clearance_controls_movement_but_not_departure(self):
        self.assertEqual(self.guide.step(self.observation()).throttle, 0)
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        command = self.guide.step(self.observation())
        self.assertGreater(command.throttle, 0)
        self.assertLessEqual(command.throttle, .28)
        self.assertEqual(command.brake, 0)
        self.guide.step(self.observation(north_m=99,groundspeed_mps=.2))
        self.assertEqual(self.taxi.phase, TaxiPhase.HOLDING_SHORT_DEPARTURE)
        self.assertEqual(self.guide.step(self.observation(north_m=99)).throttle, 0)
        with self.assertRaises(PermissionError):
            self.taxi.mark_airborne()

    def test_overspeed_and_off_corridor_latch_stop(self):
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        self.assertEqual(self.guide.step(self.observation(groundspeed_mps=9)).brake,.35)
        self.assertEqual(self.guide.step(self.observation()).throttle,0)
        second = TaxiGuidance(self.taxi,self.route,self.guide.points, profile=C172SP)
        self.assertEqual(second.step(self.observation(east_m=6)).brake,.35)
        self.assertEqual(second.step(self.observation()).throttle,0)

    def test_brake_before_endpoint_and_reject_airborne_state(self):
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        command=self.guide.step(self.observation(north_m=98,groundspeed_mps=3))
        self.assertEqual(command.throttle,0)
        self.assertGreater(command.brake,0)
        second=TaxiGuidance(self.taxi,self.route,self.guide.points, profile=C172SP)
        self.assertEqual(second.step(self.observation(on_ground=False)).brake,.35)

    def test_slow_rolling_turn_from_parking_heading(self):
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        turn = self.guide.step(self.observation(heading_true_deg=60))
        self.assertAlmostEqual(turn.throttle, .24)
        self.assertLess(turn.yaw, 0)
        self.assertLessEqual(abs(turn.yaw), 1.)
        slow = self.guide.step(self.observation(heading_true_deg=60,
                                                groundspeed_mps=2))
        self.assertEqual((slow.throttle, slow.brake), (0., .15))

    def test_sharp_corner_steering_begins_before_node(self):
        route = TaxiRoute(RoutePurpose.OUTBOUND,
                          (TaxiLeg("ramp", "corner"), TaxiLeg("corner", "hold short")))
        taxi = TaxiCoordinator("ramp", towered=True)
        taxi.load_route(route)
        taxi.authorize_taxi(ClearanceSource.ATC)
        guide = TaxiGuidance(taxi, route, {"ramp": TaxiPoint(0, 0),
                                          "corner": TaxiPoint(0, 30),
                                          "hold short": TaxiPoint(30, 30)},
                             corridor_half_width_m=10., profile=C172SP)
        turn = guide.step(self.observation(north_m=22, groundspeed_mps=1))
        self.assertGreater(turn.yaw, .5)
        self.assertGreater(turn.throttle, 0)
        brake = guide.step(self.observation(north_m=22, groundspeed_mps=2.5))
        self.assertGreater(brake.brake, 0)


if __name__ == "__main__":
    unittest.main()
