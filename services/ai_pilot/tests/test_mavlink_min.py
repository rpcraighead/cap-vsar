"""Golden-byte tests for the stdlib MAVLink codec.

The frames below were produced once with pymavlink 2.4.49 (ardupilotmega
dialect, MAVLink 2, source system 255 / component 190, sequence from 0) and
pinned here, so the hand-written encoder is checked against the real dialect
without the service depending on it. Regenerate with:

    from pymavlink.dialects.v20 import ardupilotmega as m
    mav = m.MAVLink(io.BytesIO(), srcSystem=255, srcComponent=190)
    m.MAVLink_heartbeat_message(6, 8, 0, 0, 4, 3).pack(mav).hex()
    ... (one .pack() per frame, mav.seq incremented between them)
"""

from __future__ import annotations

import struct
import unittest

from services.ai_pilot import mavlink_min as mav

# label -> (msgid, hex). Sequence numbers 0..10 in this order.
GOLDEN = [
    ("heartbeat", mav.MSG_HEARTBEAT,
     "fd09000000ffbe0000000000000006080004033d48"),
    ("set_mode_guided", mav.MSG_COMMAND_LONG,
     "fd20000001ffbe4c00000000803f000070410000000000000000000000000000000000000000b00001013354"),
    ("set_message_interval_rc", mav.MSG_COMMAND_LONG,
     "fd20000002ffbe4c000000008242005043480000000000000000000000000000000000000000ff0101017aae"),
    ("guided_heading", mav.MSG_COMMAND_INT,
     "fd20000003ffbe4b00000000803f00c089430000404000000000000000000000000000000000faa70101b7db"),
    ("guided_altitude", mav.MSG_COMMAND_INT,
     "fd20000004ffbe4b00000000000000000000000020400000000000000000000000003373ab44f9a7010120f4"),
    ("command_ack", mav.MSG_COMMAND_ACK,
     "fd0a000005ffbe4d0000faa7000000000000ffbe3b98"),
    ("command_ack_trimmed", mav.MSG_COMMAND_ACK,
     "fd01000006ffbe4d0000b0b936"),
    ("rc_channels", mav.MSG_RC_CHANNELS,
     "fd2a000007ffbe41000040e20100dc05dc05dc05dc05e8030000000000000000000000000000000000000000000000000000085a9ee6"),
    ("vfr_hud", mav.MSG_VFR_HUD,
     "fd13000008ffbe4a000066666242000068423373ab44cdcc4c3e13013ef94f"),
    ("global_position_int", mav.MSG_GLOBAL_POSITION_INT,
     "fd1c000009ffbe21000040e2010040249c1340fe70bad0ed140040420f000100020003009e6bdff7"),
    ("heartbeat_plane_guided", mav.MSG_HEARTBEAT,
     "fd0900000affbe0000000f000000010301040392e6"),
]


class GoldenTests(unittest.TestCase):
    def test_every_golden_frame_decodes_and_reencodes_identically(self):
        parser = mav.Parser()
        for label, msgid, hex_frame in GOLDEN:
            raw = bytes.fromhex(hex_frame)
            with self.subTest(label):
                messages = parser.feed(raw)
                self.assertEqual(len(messages), 1)
                message = messages[0]
                self.assertEqual(message.msgid, msgid)
                self.assertEqual((message.sysid, message.compid), (255, 190))
                again = mav.encode(message.msgid, message.fields, message.seq, message.sysid, message.compid)
                self.assertEqual(again, raw)
        self.assertEqual((parser.dropped, parser.rejected), (0, 0))

    def test_builders_match_golden_bytes(self):
        cases = {
            "heartbeat": mav.heartbeat(),
            "set_mode_guided": mav.set_mode(mav.PLANE_MODE_GUIDED),
            "set_message_interval_rc": mav.set_message_interval(mav.MSG_RC_CHANNELS, 5.0),
            "guided_heading": mav.guided_change_heading(mav.HEADING_TYPE_HEADING, 275.5, 3.0),
            "guided_altitude": mav.guided_change_altitude(1371.6, mav.MAV_FRAME_GLOBAL, 2.5),
        }
        for label, msgid, hex_frame in GOLDEN:
            if label not in cases:
                continue
            with self.subTest(label):
                built_id, fields = cases[label]
                self.assertEqual(built_id, msgid)
                seq = bytes.fromhex(hex_frame)[4]
                self.assertEqual(mav.encode(built_id, fields, seq).hex(), hex_frame)

    def test_decoded_fields_are_what_was_packed(self):
        parser = mav.Parser()
        by_label = {label: parser.feed(bytes.fromhex(h))[0] for label, _id, h in GOLDEN}
        hdg = by_label["guided_heading"].fields
        self.assertEqual(hdg["command"], mav.MAV_CMD_GUIDED_CHANGE_HEADING)
        self.assertAlmostEqual(hdg["param2"], 275.5, places=4)
        alt = by_label["guided_altitude"].fields
        self.assertAlmostEqual(alt["z"], 1371.6, places=3)
        self.assertEqual(alt["frame"], mav.MAV_FRAME_GLOBAL)
        rc = by_label["rc_channels"].fields
        self.assertEqual([rc["chan%d_raw" % i] for i in range(1, 6)], [1500] * 4 + [1000])
        self.assertEqual(rc["chancount"], 8)
        gpi = by_label["global_position_int"].fields
        self.assertEqual(gpi["alt"], 1371600)
        self.assertEqual(gpi["lon"], -1167000000)
        beat = by_label["heartbeat_plane_guided"].fields
        self.assertEqual(beat["custom_mode"], mav.PLANE_MODE_GUIDED)
        self.assertEqual(beat["base_mode"], mav.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED)

    def test_v2_trailing_zero_padding(self):
        # An ACK for DO_SET_MODE (176 = 0xB0 0x00) with result ACCEPTED (0) is
        # trimmed to ONE payload byte on the wire; everything after it,
        # including the extension fields, must read back as zero.
        raw = bytes.fromhex(dict((l, h) for l, _i, h in GOLDEN)["command_ack_trimmed"])
        self.assertEqual(raw[1], 1)
        message = mav.Parser().feed(raw)[0]
        self.assertEqual(message.fields["command"], mav.MAV_CMD_DO_SET_MODE)
        self.assertEqual(message.fields["result"], mav.MAV_RESULT_ACCEPTED)
        self.assertEqual(message.fields["target_system"], 0)


class RobustnessTests(unittest.TestCase):
    def frame(self, seq=0):
        return mav.encode(*mav.heartbeat(), seq=seq)

    def test_crc_extra_mismatch_rejected(self):
        raw = bytearray(self.frame())
        raw[-1] ^= 0x01
        parser = mav.Parser()
        self.assertEqual(parser.feed(bytes(raw)), [])
        self.assertEqual(parser.rejected, 1)

    def test_v1_frame_decodes(self):
        payload = struct.pack("<IBBBBB", mav.PLANE_MODE_GUIDED, 1, 3, 1, 4, 3)
        header = bytes((mav.MAGIC_V1, len(payload), 7, 1, 1, mav.MSG_HEARTBEAT))
        crc = mav.crc16_mcrf4xx(header[1:] + payload)
        crc = mav.crc16_mcrf4xx(bytes((50,)), crc)
        raw = header + payload + struct.pack("<H", crc)
        message = mav.Parser().feed(raw)[0]
        self.assertEqual((message.sysid, message.compid, message.seq), (1, 1, 7))
        self.assertEqual(message.fields["custom_mode"], mav.PLANE_MODE_GUIDED)

    def signed_frame(self, seq=0):
        """A correctly checksummed MAVLink 2 frame carrying a signature."""
        payload = struct.pack("<IBBBBB", 0, 6, 8, 0, 4, 3)
        header = bytes((mav.MAGIC_V2, len(payload), mav.INCOMPAT_FLAG_SIGNED, 0, seq, 255, 190, 0, 0, 0))
        crc = mav.crc16_mcrf4xx(header[1:] + payload)
        crc = mav.crc16_mcrf4xx(bytes((50,)), crc)
        return header + payload + struct.pack("<H", crc) + bytes(13)

    def test_signed_frame_rejected_whole(self):
        parser = mav.Parser()
        messages = parser.feed(self.signed_frame(seq=9) + self.frame(seq=1))
        self.assertEqual([m.seq for m in messages], [1], "the signed frame is skipped as a unit")
        self.assertEqual((parser.rejected, parser.dropped), (1, 0))

    def test_signed_flag_with_bad_crc_does_not_swallow_the_next_frame(self):
        # A stray byte pattern with the signed bit set claims 13 extra bytes;
        # its checksum fails, so the parser drops one byte and resyncs
        # instead of skipping the real frame behind it.
        bogus = bytearray(self.signed_frame(seq=9))
        bogus[-14] ^= 0xFF          # corrupt the checksum, keep the signature bytes
        parser = mav.Parser()
        messages = parser.feed(bytes(bogus[:20]) + self.frame(seq=1))
        self.assertEqual([m.seq for m in messages], [1])
        self.assertGreater(parser.dropped, 0)

    def test_unknown_message_id_is_skipped(self):
        payload = b"\x01\x02\x03"
        header = bytes((mav.MAGIC_V2, len(payload), 0, 0, 0, 1, 1, 0xFF, 0x00, 0x00))  # msgid 255
        raw = header + payload + b"\x00\x00" + self.frame(seq=2)
        messages = mav.Parser().feed(raw)
        self.assertEqual([m.seq for m in messages], [2])

    def test_resync_after_garbage(self):
        # A stray 0xFD that parses as a 5-byte HEARTBEAT with a bad checksum:
        # one byte is dropped, the scan resumes, and the real frame decodes.
        bogus = bytes((mav.MAGIC_V2, 5, 0, 0, 9, 1, 1, 0, 0, 0)) + b"12345" + b"\x00\x00"
        parser = mav.Parser()
        messages = parser.feed(b"\x00\x11" + bogus + self.frame(seq=3))
        self.assertEqual([m.seq for m in messages], [3])
        self.assertGreater(parser.dropped, 0)
        self.assertGreaterEqual(parser.rejected, 1)

    def test_bogus_length_waits_for_more_bytes_then_resyncs(self):
        # A stray 0xFD claiming 200 payload bytes stalls the parser until that
        # many bytes have arrived - the same behaviour as any streaming
        # MAVLink parser - and then resyncs onto the next real frame.
        parser = mav.Parser()
        self.assertEqual(parser.feed(b"\xfd\xc8" + self.frame(seq=1)), [])
        messages = parser.feed(bytes(220) + self.frame(seq=2))
        self.assertIn(2, [m.seq for m in messages])

    def test_stream_split_across_reads(self):
        parser = mav.Parser()
        stream = self.frame(seq=4) + self.frame(seq=5) + self.frame(seq=6)
        seen = []
        for i in range(0, len(stream), 5):
            seen += parser.feed(stream[i:i + 5])
        self.assertEqual([m.seq for m in seen], [4, 5, 6])

    def test_encode_requires_every_field(self):
        with self.assertRaisesRegex(ValueError, "missing fields"):
            mav.encode(mav.MSG_HEARTBEAT, {"custom_mode": 0}, seq=0)


class MockLinkTests(unittest.TestCase):
    def test_mock_link_auto_acks_and_reports_mode(self):
        link = mav.MockLink(clock=lambda: 10.0)
        self.assertIsNone(link.custom_mode())
        event = link.arm_ack(mav.MAV_CMD_DO_SET_MODE)
        link.send(*mav.set_mode(mav.PLANE_MODE_GUIDED))
        self.assertTrue(event.is_set())
        self.assertEqual(link.wait_ack(mav.MAV_CMD_DO_SET_MODE, 0.1), mav.MAV_RESULT_ACCEPTED)
        self.assertEqual(link.custom_mode(), mav.PLANE_MODE_GUIDED)
        self.assertEqual(link.heartbeat_age(), 0.0)

    def test_mock_heartbeat_reports_armed_by_default(self):
        link = mav.MockLink(clock=lambda: 10.0)
        link.inject_heartbeat(mav.PLANE_MODE_MANUAL)
        fields, _age = link.latest(mav.MSG_HEARTBEAT)
        self.assertTrue(fields["base_mode"] & mav.MAV_MODE_FLAG_SAFETY_ARMED)

    def test_other_systems_on_the_link_are_ignored(self):
        link = mav.MockLink(clock=lambda: 10.0)
        link.inject_heartbeat(mav.PLANE_MODE_GUIDED)
        link.inject(mav.MSG_HEARTBEAT, {"custom_mode": mav.PLANE_MODE_MANUAL, "type": 6, "autopilot": 8,
                                        "base_mode": 1, "system_status": 4, "mavlink_version": 3}, sysid=255)
        self.assertEqual(link.custom_mode(), mav.PLANE_MODE_GUIDED, "a GCS heartbeat must not read as the aircraft's mode")

    def test_link_requests_heartbeat_faster_than_default(self):
        self.assertIn((mav.MSG_HEARTBEAT, 5.0), mav.MavlinkLink.STREAMS)

    def test_mock_link_can_withhold_and_override_acks(self):
        link = mav.MockLink(clock=lambda: 10.0, auto_ack=None)
        link.arm_ack(mav.MAV_CMD_GUIDED_CHANGE_HEADING)
        link.send(*mav.guided_change_heading(mav.HEADING_TYPE_HEADING, 90.0, 3.0))
        self.assertIsNone(link.wait_ack(mav.MAV_CMD_GUIDED_CHANGE_HEADING, 0.05))
        link.ack_overrides[mav.MAV_CMD_GUIDED_CHANGE_ALTITUDE] = mav.MAV_RESULT_DENIED
        link.arm_ack(mav.MAV_CMD_GUIDED_CHANGE_ALTITUDE)
        link.send(*mav.guided_change_altitude(1000.0, mav.MAV_FRAME_GLOBAL, 2.5))
        self.assertEqual(link.wait_ack(mav.MAV_CMD_GUIDED_CHANGE_ALTITUDE, 0.05), mav.MAV_RESULT_DENIED)


if __name__ == "__main__":
    unittest.main()
