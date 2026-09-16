#!/usr/bin/env python3
"""A closed X-Plane UDP client must cancel its subscriptions, not just hang up.

X-Plane streams RREF to a port until it is told to stop, not until the client
dies. If a client only closes its socket and something rebinds that port before
X-Plane hits it and gets an ICMP unreachable - one script exiting and the next
starting, which is how these tools are used - the old stream keeps arriving and
is decoded against the NEW client's id numbering. Both start at zero, so values
land under the wrong names in silence.

Demonstrated live against X-Plane 12.4.3 on a never-before-used port, closing
both ways with no rebind gap: the old close delivered latitude in 3 of 16
samples that had asked for elevation; the fixed close delivered 16 of 16 real
elevation. For scripts/capture_flight_test.py that difference is airspeed
recorded as bank angle at 20 Hz.
"""

from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


xu = _load("capvsar_xplane_udp_subs", "services/ai_pilot/xplane_udp.py")

A = "sim/flightmodel/position/latitude"
B = "sim/flightmodel/position/elevation"
C = "sim/flightmodel/position/indicated_airspeed"


class FakeSocket:
    def __init__(self):
        self.sent = []
        self.closed = False

    def sendto(self, data, addr):
        self.sent.append(data)

    def close(self):
        self.closed = True

    def settimeout(self, *a):
        pass

    def setsockopt(self, *a):
        pass


def rrefs(sock):
    """(freq, id, dataref) for every RREF packet sent."""
    out = []
    for pkt in sock.sent:
        if not pkt.startswith(b"RREF\x00"):
            continue
        freq, ref_id = struct.unpack("<ii", pkt[5:13])
        name = pkt[13:].rstrip(b"\x00").decode("utf-8", "replace")
        out.append((freq, ref_id, name))
    return out


def client_with_fake_socket():
    c = xu.XPlaneUDPClient(host="127.0.0.1", port=49000, receive_port=49999)
    c._sock = FakeSocket()
    return c, c._sock


class TestUnsubscribeOnClose:
    def test_every_subscription_is_cancelled_on_stop(self):
        c, sock = client_with_fake_socket()
        for d in (A, B, C):
            c.subscribe_dref(d, 5)
        c.stop()
        cancels = {name for freq, _, name in rrefs(sock) if freq == 0}
        assert cancels == {A, B, C}

    def test_a_cancel_reuses_the_id_the_subscription_was_made_with(self):
        # A cancel carrying the wrong id cancels nothing; X-Plane matches on it.
        c, sock = client_with_fake_socket()
        c.subscribe_dref(A, 5)
        c.subscribe_dref(B, 5)
        subs = {name: rid for freq, rid, name in rrefs(sock) if freq > 0}
        c.stop()
        cancels = {name: rid for freq, rid, name in rrefs(sock) if freq == 0}
        assert cancels[A] == subs[A] and cancels[B] == subs[B]

    def test_cancels_are_sent_before_the_socket_closes(self):
        # Cancelling after close sends nothing at all.
        c, sock = client_with_fake_socket()
        c.subscribe_dref(A, 5)

        closed_at = {}
        real_close = sock.close

        def close_recording():
            closed_at["n"] = len(sock.sent)
            real_close()

        sock.close = close_recording
        c.stop()
        assert closed_at["n"] >= 2, "the cancel must already have been sent"

    def test_stop_forgets_the_subscriptions_it_cancelled(self):
        c, _ = client_with_fake_socket()
        c.subscribe_dref(A, 5)
        c.stop()
        assert c._dref_to_id == {} and c._id_to_dref == {}

    def test_stop_is_safe_with_no_subscriptions(self):
        c, sock = client_with_fake_socket()
        c.stop()
        assert [r for r in rrefs(sock) if r[0] == 0] == []

    def test_stop_twice_does_not_raise(self):
        c, _ = client_with_fake_socket()
        c.subscribe_dref(A, 5)
        c.stop()
        c.stop()

    def test_unsubscribe_all_is_callable_without_stopping(self):
        c, sock = client_with_fake_socket()
        c.subscribe_dref(A, 5)
        c.unsubscribe_all()
        assert any(freq == 0 and name == A for freq, _, name in rrefs(sock))
        assert c._dref_to_id == {}

    def test_the_context_manager_exit_cancels_too(self):
        c = xu.XPlaneUDPClient(host="127.0.0.1", port=49000, receive_port=49999)
        c._sock = FakeSocket()
        sock = c._sock
        with c:
            c.subscribe_dref(A, 5)
        assert any(freq == 0 and name == A for freq, _, name in rrefs(sock))

    def test_a_mock_client_stops_cleanly(self):
        c = xu.XPlaneUDPClient(mock=True)
        c.subscribe_dref(A, 5)
        c.stop()
