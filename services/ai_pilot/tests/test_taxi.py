"""FAA-grounded policy tests for the AI Mission Pilot taxi coordinator."""

from __future__ import annotations

import unittest

from services.ai_pilot.taxi import (
    ClearanceSource,
    RoutePurpose,
    Surface,
    TaxiCoordinator,
    TaxiLeg,
    TaxiPhase,
    TaxiRoute,
)


def leg(start, end, surface=Surface.TAXIWAY, runway=None):
    return TaxiLeg(start=start, end=end, surface=surface, runway=runway)


class TaxiCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.taxi = TaxiCoordinator(start_point="CAP ramp spot 4", towered=True)
        self.outbound = TaxiRoute(
            purpose=RoutePurpose.OUTBOUND,
            legs=(
                leg("CAP ramp spot 4", "A1", Surface.APRON),
                leg("A1", "A-RWY17", Surface.TAXIWAY),
            ),
        )

    def clear_and_depart(self):
        self.taxi.load_route(self.outbound)
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        while self.taxi.phase is TaxiPhase.TAXIING_OUT:
            self.taxi.complete_leg()
        self.taxi.authorize_departure_runway("17", ClearanceSource.ATC, takeoff=True)
        self.taxi.mark_airborne()

    def test_towered_airport_holds_until_taxi_clearance_is_received(self):
        self.taxi.load_route(self.outbound)
        directive = self.taxi.directive()
        self.assertEqual(directive.action, "hold")
        self.assertIn("taxi clearance", directive.reason)

    def test_taxi_clearance_does_not_authorize_departure_runway_entry(self):
        self.taxi.load_route(self.outbound)
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        while self.taxi.phase is TaxiPhase.TAXIING_OUT:
            self.taxi.complete_leg()

        self.assertEqual(self.taxi.phase, TaxiPhase.HOLDING_SHORT_DEPARTURE)
        with self.assertRaisesRegex(PermissionError, "takeoff or line-up"):
            self.taxi.authorize_departure_runway("17", ClearanceSource.ATC)

        self.taxi.authorize_departure_runway(
            "17", ClearanceSource.ATC, takeoff=True
        )
        self.assertEqual(self.taxi.phase, TaxiPhase.CLEARED_FOR_TAKEOFF)

    def test_towered_departure_runway_rejects_crew_inferred_authority(self):
        self.taxi.load_route(self.outbound)
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        while self.taxi.phase is TaxiPhase.TAXIING_OUT:
            self.taxi.complete_leg()
        with self.assertRaisesRegex(PermissionError, "ATC"):
            self.taxi.authorize_departure_runway(
                "17", ClearanceSource.CREW_TRAFFIC_CHECK, takeoff=True
            )

    def test_line_up_and_wait_never_implies_takeoff_clearance(self):
        self.taxi.load_route(self.outbound)
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        while self.taxi.phase is TaxiPhase.TAXIING_OUT:
            self.taxi.complete_leg()

        self.taxi.authorize_departure_runway(
            "17", ClearanceSource.ATC, line_up_and_wait=True
        )
        self.assertEqual(self.taxi.phase, TaxiPhase.CLEARED_TO_LINE_UP)
        self.assertEqual(self.taxi.directive().action, "line_up_and_wait")

        self.taxi.mark_lined_up()
        self.assertEqual(self.taxi.phase, TaxiPhase.HOLDING_IN_POSITION)
        self.assertEqual(self.taxi.directive().action, "hold")

        self.taxi.authorize_departure_runway(
            "17", ClearanceSource.ATC, takeoff=True
        )
        self.assertEqual(self.taxi.phase, TaxiPhase.CLEARED_FOR_TAKEOFF)
        self.assertEqual(self.taxi.directive().action, "takeoff")

    def test_runway_crossing_requires_specific_explicit_clearance(self):
        route = TaxiRoute(
            purpose=RoutePurpose.OUTBOUND,
            legs=(
                leg("CAP ramp spot 4", "A1", Surface.APRON),
                leg("A1", "A2", Surface.RUNWAY_CROSSING, runway="09-27"),
                leg("A2", "A-RWY17"),
            ),
        )
        self.taxi.load_route(route)
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        self.taxi.complete_leg()
        self.assertEqual(self.taxi.directive().action, "hold")
        self.assertIn("09-27", self.taxi.directive().reason)

        with self.assertRaisesRegex(ValueError, "current crossing"):
            self.taxi.authorize_runway_crossing("17", ClearanceSource.ATC)

        self.taxi.authorize_runway_crossing("09-27", ClearanceSource.ATC)
        self.assertEqual(self.taxi.directive().action, "cross_runway")

    def test_crossing_clearance_is_single_use(self):
        route = TaxiRoute(
            purpose=RoutePurpose.OUTBOUND,
            legs=(
                leg("CAP ramp spot 4", "B", Surface.RUNWAY_CROSSING, runway="09-27"),
                leg("B", "C", Surface.RUNWAY_CROSSING, runway="04-22"),
                leg("C", "C-RWY17"),
            ),
        )
        self.taxi.load_route(route)
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        self.taxi.authorize_runway_crossing("09-27", ClearanceSource.ATC)
        self.taxi.complete_leg()

        self.assertEqual(self.taxi.directive().action, "hold")
        self.assertIn("04-22", self.taxi.directive().reason)

    def test_towered_crossing_rejects_non_atc_authorization(self):
        route = TaxiRoute(
            RoutePurpose.OUTBOUND,
            (leg("CAP ramp spot 4", "A", Surface.RUNWAY_CROSSING, "09-27"),),
        )
        self.taxi.load_route(route)
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        with self.assertRaisesRegex(PermissionError, "ATC"):
            self.taxi.authorize_runway_crossing(
                "09-27", ClearanceSource.CREW_TRAFFIC_CHECK
            )

    def test_untowered_crossing_requires_recorded_crew_traffic_check(self):
        taxi = TaxiCoordinator(start_point="north ramp", towered=False)
        route = TaxiRoute(
            RoutePurpose.OUTBOUND,
            (leg("north ramp", "A", Surface.RUNWAY_CROSSING, "09-27"),),
        )
        taxi.load_route(route)
        taxi.authorize_taxi(ClearanceSource.CREW_TRAFFIC_CHECK)
        self.assertEqual(taxi.directive().action, "hold")
        taxi.authorize_runway_crossing("09-27", ClearanceSource.CREW_TRAFFIC_CHECK)
        self.assertEqual(taxi.directive().action, "cross_runway")

    def test_return_route_must_end_at_recorded_start_point(self):
        self.clear_and_depart()
        self.taxi.mark_landed_and_runway_clear("B1")
        wrong = TaxiRoute(RoutePurpose.RETURN, (leg("B1", "other ramp"),))
        with self.assertRaisesRegex(ValueError, "recorded starting point"):
            self.taxi.load_route(wrong)

    def test_after_landing_return_taxi_requires_clearance_and_ends_at_start(self):
        self.clear_and_depart()
        self.taxi.mark_landed_and_runway_clear("B1")
        route = TaxiRoute(
            RoutePurpose.RETURN,
            (
                leg("B1", "A1"),
                leg("A1", "CAP ramp spot 4", Surface.APRON),
            ),
        )
        self.taxi.load_route(route)
        self.assertEqual(self.taxi.directive().action, "hold")
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        self.taxi.complete_leg()
        self.taxi.complete_leg()
        self.assertEqual(self.taxi.phase, TaxiPhase.RETURNED_TO_START)
        self.assertEqual(self.taxi.position, "CAP ramp spot 4")

    def test_ai_uncertainty_stops_and_requests_progressive_taxi(self):
        self.taxi.load_route(self.outbound)
        self.taxi.authorize_taxi(ClearanceSource.ATC)
        self.taxi.report_route_uncertain("taxiway sign does not match route")
        directive = self.taxi.directive()
        self.assertEqual(directive.action, "hold")
        self.assertTrue(directive.request_progressive_taxi)

    def test_route_must_be_contiguous(self):
        with self.assertRaisesRegex(ValueError, "contiguous"):
            TaxiRoute(
                RoutePurpose.OUTBOUND,
                (leg("A", "B"), leg("C", "D")),
            )


if __name__ == "__main__":
    unittest.main()
