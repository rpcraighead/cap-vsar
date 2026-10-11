"""KSEE trial route is tied to real scenery geometry, not route labels alone."""
from dataclasses import replace
from pathlib import Path

import pytest

from services.ai_pilot.ksee_surface import (
    APT_SHA256, PARKING_NAME, TAXI_NODE_IDS, read_survey,
)


APT = Path("/home/ron/X-Plane 12/Global Scenery/Global Airports/Earth nav data/apt.dat")


@pytest.fixture(scope="module")
def survey():
    if not APT.is_file():
        pytest.skip("Pinned X-Plane scenery not installed")
    return read_survey(APT)


def test_parking_12_route_reaches_27r_hold_without_entering_any_runway(survey):
    route, points = survey.taxi_route()
    heading, length, entry_along = survey.runway_frame()
    assert route.start == PARKING_NAME and route.destination == "KSEE node 124"
    assert len(route.legs) == len(TAXI_NODE_IDS)
    assert set(points) == {PARKING_NAME} | {f"KSEE node {n}" for n in TAXI_NODE_IDS}
    assert 281 < heading < 283 and 1600 < length < 1650
    assert 30 < entry_along < 70


def test_survey_rejects_route_label_or_geometry_drift(survey):
    a, b = TAXI_NODE_IDS[0:2]
    false_label = replace(survey, edges={**survey.edges, frozenset((a,b)): "runway 09L/27R"})
    with pytest.raises(ValueError, match="edge missing or crosses"):
        false_label.validate()
    moved_nodes = {**survey.nodes, 125: survey.runway_ends["27R"]}
    false_geometry = replace(survey, nodes=moved_nodes)
    with pytest.raises(ValueError, match="intersects|holding node"):
        false_geometry.validate()
