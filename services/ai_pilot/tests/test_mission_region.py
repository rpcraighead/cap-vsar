from services.ai_pilot.search_patterns import expanding_square
from xplane.capvsar_mission import in_airborne_region

ESCON = (33.1700, -117.0792)


def test_original_route_region_unchanged():
    assert in_airborne_region(32.78, -117.20)
    assert not in_airborne_region(32.60, -117.20)


def test_escon_search_square_is_inside_the_geofence():
    points = expanding_square(*ESCON, 0., 1., 8, "right")
    assert points and all(in_airborne_region(p.lat, p.lon) for p in points)


def test_far_north_still_outside():
    assert not in_airborne_region(33.40, -117.08)
