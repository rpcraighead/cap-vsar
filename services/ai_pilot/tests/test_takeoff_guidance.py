"""Takeoff gates with a synthetic stock-C172 observation stream."""
import unittest

from services.ai_pilot.takeoff_guidance import TakeoffGuidance, TakeoffObservation
from services.ai_pilot.taxi import (
    ClearanceSource, RoutePurpose, TaxiCoordinator, TaxiLeg, TaxiRoute, TaxiPhase,
)


class TakeoffGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.taxi = TaxiCoordinator("ramp", towered=True)
        self.taxi.load_route(TaxiRoute(RoutePurpose.OUTBOUND,
                                       (TaxiLeg("ramp", "27R hold short"),)))
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        self.taxi.complete_leg()
        self.assertEqual(self.taxi.phase, TaxiPhase.HOLDING_SHORT_DEPARTURE)
        self.pilot = TakeoffGuidance(self.taxi, runway="27R",
                                     runway_heading_true_deg=282,
                                     runway_length_m=1628, field_elevation_ft=388)

    def observation(self, **changes):
        values = dict(sim_time_s=0, along_runway_m=10, cross_runway_m=0,
                      heading_true_deg=282, kias=0, groundspeed_mps=0,
                      on_ground=True, agl_ft=0, altitude_msl_ft=388,
                      climb_distance_nm=0, pitch_deg=0, pitch_rate_dps=0,
                      roll_deg=0, engine_rpm=2300, flap_ratio=0)
        values.update(changes)
        return TakeoffObservation(**values)

    def clear(self):
        self.taxi.authorize_departure_runway("27R", ClearanceSource.ATC,
                                             takeoff=True)

    def test_clearance_alignment_and_liftoff_are_distinct(self):
        self.assertEqual(self.pilot.step(self.observation()).throttle, 0)
        self.clear()
        self.assertEqual(self.pilot.step(self.observation(cross_runway_m=4)).throttle, 0)
        roll = self.pilot.step(self.observation())
        self.assertEqual((roll.phase, roll.throttle, roll.target_kias),
                         ("roll", 1., 55.))
        rotate = self.pilot.step(self.observation(sim_time_s=12, kias=55,
                                                  groundspeed_mps=28,
                                                  along_runway_m=300))
        self.assertEqual(rotate.phase, "rotate")
        self.assertGreater(rotate.pitch, roll.pitch)
        self.assertEqual(self.taxi.phase, TaxiPhase.CLEARED_FOR_TAKEOFF)
        climb = self.pilot.step(self.observation(sim_time_s=14, kias=63,
                                                 on_ground=False, agl_ft=10,
                                                 altitude_msl_ft=400,
                                                 along_runway_m=420))
        self.assertEqual((climb.phase, climb.target_kias), ("climb", 62.))
        self.assertEqual(self.taxi.phase, TaxiPhase.AIRBORNE)
        at_2000 = self.pilot.step(self.observation(sim_time_s=110, kias=72,
                                                   on_ground=False, agl_ft=1612,
                                                   altitude_msl_ft=2000,
                                                   climb_distance_nm=3))
        self.assertEqual(at_2000.target_kias, 74.)

    def test_runway_excursion_or_low_power_rejects_and_latches(self):
        self.clear()
        self.pilot.step(self.observation())
        rejected = self.pilot.step(self.observation(sim_time_s=3,
                                                    cross_runway_m=11))
        self.assertEqual(rejected.phase, "rejected")
        self.assertEqual((rejected.throttle, rejected.brake), (0., 1.))
        self.assertTrue(rejected.intervention_required)
        self.assertEqual(self.pilot.step(self.observation()).phase, "rejected")

    def test_departure_gradient_deficit_requires_intervention(self):
        self.clear()
        self.pilot.step(self.observation())
        self.pilot.step(self.observation(sim_time_s=14, kias=62, on_ground=False,
                                         agl_ft=30, altitude_msl_ft=418))
        command = self.pilot.step(self.observation(sim_time_s=40, kias=62,
                                                   on_ground=False, agl_ft=150,
                                                   altitude_msl_ft=538,
                                                   climb_distance_nm=.5))
        self.assertEqual(command.phase, "climb")
        self.assertTrue(command.intervention_required)
        self.assertEqual(command.throttle, 1.)

    def test_takeoff_command_validates_trim(self):
        self.clear()
        command = self.pilot.step(self.observation())
        with self.assertRaises(ValueError):
            command.actuator_frame(float("nan"))

    def test_runway_roll_uses_full_rudder_authority_for_drift(self):
        self.clear()
        self.pilot.step(self.observation())
        correction = self.pilot.step(self.observation(sim_time_s=2,
                                                      heading_true_deg=272,
                                                      cross_runway_m=-2,
                                                      groundspeed_mps=8))
        self.assertEqual(correction.phase, "roll")
        self.assertGreater(correction.yaw, .6)

    def test_early_climb_retains_positive_pitch_at_high_airspeed(self):
        self.clear()
        self.pilot.step(self.observation())
        self.pilot.step(self.observation(sim_time_s=12, kias=70,
                                         on_ground=False, agl_ft=6,
                                         pitch_deg=5, altitude_msl_ft=394))
        command = self.pilot.step(self.observation(sim_time_s=13, kias=75,
                                                   on_ground=False, agl_ft=8,
                                                   pitch_deg=2, altitude_msl_ft=396))
        self.assertEqual(command.phase, "climb")
        self.assertGreater(command.pitch, .3)
        correction = self.pilot.step(self.observation(sim_time_s=14, kias=75,
                                                      on_ground=False, agl_ft=10,
                                                      pitch_deg=7, altitude_msl_ft=398,
                                                      heading_true_deg=270,
                                                      cross_runway_m=-3))
        self.assertGreater(correction.roll, 0)


if __name__ == "__main__":
    unittest.main()
