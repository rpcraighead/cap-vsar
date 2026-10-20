"""
The reach model on the live voice path (T33): a listener's relayed frames
pick up static and dropouts according to the link to the speaker, a `link`
message tells the face what it is hearing through, and the scenario's
`radio_reach` effect turns the whole thing off. Uses test_radio's fixtures.
"""
import importlib
import math
import sys
from array import array
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "services" / "exercise"))

from test_radio import sockets, join, hello          # noqa: E402,F401  (pytest fixtures)
from app import radio                                 # noqa: E402

# `hub` is bound per test, not at import: radio.py reaches the hub lazily
# (`from .hub import hub` inside reach_conditions and station_endpoint), so it
# always sees whatever `app.hub` is in sys.modules *now*. test_backup_exercise_db
# and test_console pop every app.* module to get a console on their own database
# and do not put the old ones back, so a hub imported here at collection time is
# a different object from the one the radio code consults once those files have
# run, and the positions and effects this file sets on it are never seen.
hub = None


def current_hub():
    return importlib.import_module("app.hub").hub

FAR_AND_LOW = {"callsign": "CAP 487", "lat": 30.0, "lon": -116.97, "alt_ft": 50.0}      # 170 NM south, on the deck
IN_THE_BLOCK = {"callsign": "CAP 487", "lat": 33.17, "lon": -117.08, "alt_ft": 4500.0}  # ESCON at 4,500 ft


def tone(n=960, amp=8000):
    return array("h", (int(amp * math.sin(2 * math.pi * 440 * i / 48000)) for i in range(n))).tobytes()


@pytest.fixture
def scenario(monkeypatch):
    global hub
    hub = current_hub()
    monkeypatch.setattr(hub, "scenario", {"effects": {"radio_reach": True, "radio_conditions": 1.0}})
    monkeypatch.setattr(hub, "aircraft", {})
    yield hub


def frames_after(face, radio_obj, aircraft, count=150, chunk=16):
    """Deliver `count` frames in chunks the face's 32-item queue can hold,
    draining after each; return (input frame, received frames, messages)."""
    import json
    hub.aircraft[aircraft["callsign"]] = dict(aircraft)
    radio_obj.links.clear()
    radio_obj.links_at.clear()
    pcm = tone()
    received, messages = [], []
    sent = 0
    while sent < count:
        batch = min(chunk, count - sent)
        for _ in range(batch):
            radio_obj.deliver_audio(9, radio_obj.channel_id, radio_obj.epoch, aircraft["callsign"], pcm)
        sent += batch
        got = 0
        while got < batch:
            item = face.receive()
            if "bytes" in item:
                received.append(item["bytes"][8:])
                got += 1
            elif "text" in item:
                messages.append(json.loads(item["text"]))
            else:
                raise AssertionError("face closed: %r" % (item,))
    return pcm, received, messages


def test_a_far_low_aircraft_is_heard_at_base_with_static_and_dropouts(sockets, scenario):
    client, _clients = sockets
    with join(client) as face:
        hello(face, "MISSION BASE")
        live = next(iter(radio.SESSIONS))
        live.face_session[next(iter(live.faces))] = ({"role": "base", "callsign": "MISSION BASE"}, True)
        pcm, received, messages = frames_after(face, live, FAR_AND_LOW)
        link = next(m for m in messages if m["type"] == "link")
        assert link["speaker"] == "CAP 487"
        assert link["path"] == "none" and link["quality"] == "unusable"
        assert link["heard"] == "out of range of base and repeater"
        assert len(received) == 150
        assert all(len(f) == 1920 for f in received)
        assert any(f == bytes(1920) for f in received), "no dropout in 3 s of an unusable link"
        assert any(f not in (pcm, bytes(1920)) for f in received), "no static on the frames that got through"
        assert not any(f == pcm for f in received), "an unusable link passed a clean frame"


def test_an_aircraft_in_the_search_block_is_heard_clear(sockets, scenario):
    client, _clients = sockets
    with join(client) as face:
        hello(face, "MISSION BASE")
        live = next(iter(radio.SESSIONS))
        live.face_session[next(iter(live.faces))] = ({"role": "base", "callsign": "MISSION BASE"}, True)
        pcm, received, messages = frames_after(face, live, IN_THE_BLOCK, count=20)
        link = next(m for m in messages if m["type"] == "link")
        assert link["path"] == "direct" and link["quality"] == "clear" and link["margin"] == 1.0
        assert all(f == pcm for f in received)
        # the link is announced once, not per frame
        assert sum(1 for m in messages if m["type"] == "link") == 1


def test_the_effect_switch_and_a_missing_scenario_pass_audio_through(sockets, scenario, monkeypatch):
    client, _clients = sockets
    with join(client) as face:
        hello(face, "MISSION BASE")
        live = next(iter(radio.SESSIONS))
        live.face_session[next(iter(live.faces))] = ({"role": "base", "callsign": "MISSION BASE"}, True)
        hub.scenario["effects"]["radio_reach"] = False
        pcm, received, messages = frames_after(face, live, FAR_AND_LOW, count=20)
        assert all(f == pcm for f in received)
        assert not any(m["type"] == "link" for m in messages)
        monkeypatch.setattr(hub, "scenario", None)
        pcm, received, messages = frames_after(face, live, FAR_AND_LOW, count=20)
        assert all(f == pcm for f in received)


def test_conditions_degrade_an_otherwise_clear_link(sockets, scenario):
    client, _clients = sockets
    with join(client) as face:
        hello(face, "MISSION BASE")
        live = next(iter(radio.SESSIONS))
        live.face_session[next(iter(live.faces))] = ({"role": "base", "callsign": "MISSION BASE"}, True)
        hub.scenario["effects"]["radio_conditions"] = 0.5
        pcm, received, messages = frames_after(face, live, IN_THE_BLOCK, count=20)
        link = next(m for m in messages if m["type"] == "link")
        assert link["path"] == "direct" and link["quality"] == "weak" and link["margin"] == 0.5
        assert all(f != pcm for f in received), "static expected at half conditions"


def test_unknown_positions_and_ground_teams_are_nominal(sockets, scenario):
    client, _clients = sockets
    with join(client) as face:
        hello(face, "UDF 1")
        live = next(iter(radio.SESSIONS))
        live.face_session[next(iter(live.faces))] = ({"role": "ground_team", "callsign": "UDF 1"}, True)
        pcm, received, messages = frames_after(face, live, FAR_AND_LOW, count=10)
        link = next(m for m in messages if m["type"] == "link")
        assert link["path"] == "nominal"
        assert all(f == pcm for f in received)


def test_station_endpoint_uses_telemetry_then_role(scenario):
    hub.aircraft["CAP 487"] = dict(IN_THE_BLOCK)
    self_ac = radio.station_endpoint("cap-487", "aircrew")
    assert self_ac["kind"] == "aircraft" and self_ac["alt_ft"] == 4500.0
    assert radio.station_endpoint("MRO 1", "base")["kind"] == "base"
    assert radio.station_endpoint("INSTRUCTOR", "instructor")["kind"] == "base"
    assert radio.station_endpoint("UDF 2", "ground_team")["kind"] == "ground"
    assert radio.station_endpoint("CAP 415", "aircrew") == {"kind": "aircraft"}
    assert radio.station_endpoint("Stranger", None)["kind"] == "unknown"
    assert radio.reach_conditions() == 1.0
    hub.scenario["effects"]["radio_conditions"] = "bad"
    assert radio.reach_conditions() == 1.0
    hub.scenario["effects"]["radio_conditions"] = 3.0
    assert radio.reach_conditions() == 1.0
    hub.scenario["effects"]["radio_reach"] = False
    assert radio.reach_conditions() is None


def test_effects_accept_the_new_switches_and_defaults_carry_them():
    from app.models import EffectsIn
    from app.settings import DEFAULT_EFFECTS
    assert DEFAULT_EFFECTS["radio_reach"] is True and DEFAULT_EFFECTS["radio_conditions"] == 1.0
    EffectsIn(radio_reach=False, radio_conditions=0.25)
    with pytest.raises(ValueError):
        EffectsIn(radio_conditions=1.5)
