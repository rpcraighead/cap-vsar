"""Unit tests for X-Plane UDP packet protocol formatting and parsing."""

import struct
import unittest

from services.ai_pilot.xplane_udp import XPlaneUDPClient


class TestUDPProtocol(unittest.TestCase):
    def test_pack_dref(self):
        dref = "sim/cockpit2/controls/parking_brake_ratio"
        val = 1.0
        packet = XPlaneUDPClient.pack_dref(dref, val)

        self.assertEqual(packet[:5], b"DREF\x00")
        unpacked_val = struct.unpack("<f", packet[5:9])[0]
        self.assertAlmostEqual(unpacked_val, 1.0, places=4)

        # Path must be padded to 500 bytes (total 5 + 4 + 500 = 509 bytes)
        self.assertEqual(len(packet), 509)
        dref_path_bytes = packet[9:].rstrip(b"\x00")
        self.assertEqual(dref_path_bytes.decode("utf-8"), dref)

    def test_pack_cmnd(self):
        cmd = "sim/flight_controls/flaps_down"
        packet = XPlaneUDPClient.pack_cmnd(cmd)

        self.assertEqual(packet[:5], b"CMND\x00")
        self.assertEqual(packet[5:], cmd.encode("utf-8") + b"\x00")

    def test_pack_rref(self):
        dref = "sim/flightmodel/position/indicated_airspeed"
        freq = 10
        dref_id = 42
        packet = XPlaneUDPClient.pack_rref(dref, freq, dref_id)

        self.assertEqual(packet[:5], b"RREF\x00")
        unpacked_freq, unpacked_id = struct.unpack("<ii", packet[5:13])
        self.assertEqual(unpacked_freq, 10)
        self.assertEqual(unpacked_id, 42)
        # 5 + 8 + 400 = 413 bytes
        self.assertEqual(len(packet), 413)
        self.assertEqual(packet[13:].rstrip(b"\x00").decode("utf-8"), dref)

    def test_pack_vehs(self):
        packet = XPlaneUDPClient.pack_vehs(
            plane_idx=0,
            lat_deg=32.8264,
            lon_deg=-116.9643,
            ele_m=118.26,
            psi_true=282.0,
            pitch_deg=1.5,
            roll_deg=0.0,
        )
        self.assertEqual(packet[:5], b"VEHS\x00")
        p, lat, lon, ele, psi, pitch, roll = struct.unpack("<idddfff", packet[5:])
        self.assertEqual(p, 0)
        self.assertAlmostEqual(lat, 32.8264, places=4)
        self.assertAlmostEqual(lon, -116.9643, places=4)
        self.assertAlmostEqual(ele, 118.26, places=2)
        self.assertAlmostEqual(psi, 282.0, places=1)
        self.assertAlmostEqual(pitch, 1.5, places=1)
        self.assertAlmostEqual(roll, 0.0, places=1)

    def test_mock_cache_and_subscription(self):
        client = XPlaneUDPClient(mock=True)
        sub_id = client.subscribe_dref("sim/flightmodel/position/latitude", 10)
        self.assertGreater(sub_id, 0)

        client.set_mock_dref("sim/flightmodel/position/latitude", 32.8264)
        self.assertAlmostEqual(client.get_dref("sim/flightmodel/position/latitude"), 32.8264, places=4)

        # Test callback
        received = []

        def on_update(name, val):
            received.append((name, val))

        client.subscribe_dref("sim/flightmodel/position/latitude", callback=on_update)
        client.set_mock_dref("sim/flightmodel/position/latitude", 33.0380)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], "sim/flightmodel/position/latitude")
        self.assertAlmostEqual(received[0][1], 33.0380, places=4)

        client.stop()


if __name__ == "__main__":
    unittest.main()
