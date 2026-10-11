"""G1000 MFD video-stream watchdog (O-7b, I2-8): one video node, banner and hotspot on top."""
import unittest

from tests.am import AirManager

HEARTBEAT = "sim/time/total_running_time_sec"
VERSION = "sim/version/xplane_internal_version"


def load(am):
    am.load_instrument("g1000-mfd-watchdog")
    am.write_dataref(VERSION, "INT", 120000)
    am.write_dataref(HEARTBEAT, "FLOAT", 100.0)


def go_stale(am):
    am.step_time(3500)
    assert am.read_si_variable("g1000_mfd_stream_stale")


def video_ids(am):
    streams = am.eval("return _AM.video_streams")
    return sorted(streams) if isinstance(streams, dict) else [i for i, s in enumerate(streams, 1) if s]


class OneVideoNodeBelowTheOverlays(unittest.TestCase):
    def test_exactly_one_video_stream_node_survives_many_rearms(self):
        with AirManager() as am:
            load(am)
            self.assertEqual(len(video_ids(am)), 1)
            go_stale(am)
            am.step_time(20000)                       # several automatic re-arms (5 s apart)
            self.assertGreaterEqual(am.read_si_variable("g1000_mfd_rearm_count"), 4)
            am.click_at(1000, 800)                    # manual re-arm via the hotspot
            self.assertEqual(len(video_ids(am)), 1,
                             "every video_stream_add stacks a new node over the banner")

    def test_banner_and_hotspot_are_added_after_the_video_node(self):
        with AirManager() as am:
            load(am)
            (video,) = video_ids(am)
            canvases = am.eval("return _AM.canvases")
            banner = max(c["id"] for c in canvases.values())
            hotspot = am.button_at(1000, 800)
            self.assertIsNotNone(hotspot)
            self.assertGreater(banner, video)
            self.assertGreater(hotspot, video)
            # The black plate is under the video.
            plate = min(c["id"] for c in canvases.values())
            self.assertLess(plate, video)

    def test_rearm_keeps_the_node_visible(self):
        with AirManager() as am:
            load(am)
            (video,) = video_ids(am)
            go_stale(am)
            am.step_time(6000)
            self.assertTrue(am.is_visible(video))


class StaleBannerAndRecovery(unittest.TestCase):
    def test_banner_scrim_uses_rrggbbaa_not_css_rgba(self):
        with AirManager() as am:
            load(am)
            go_stale(am)
            fills = [c[1] for c in am.eval("return _AM.drawn_commands") if c[0] == "fill"]
            self.assertIn("#0A0A0ABF", fills)
            self.assertFalse([f for f in fills if "rgba" in f])

    def test_hotspot_rearms_only_while_stale(self):
        with AirManager() as am:
            load(am)
            before = am.read_si_variable("g1000_mfd_rearm_count")
            am.click_at(1000, 800)
            self.assertEqual(am.read_si_variable("g1000_mfd_rearm_count"), before)
            go_stale(am)
            count = am.read_si_variable("g1000_mfd_rearm_count")
            am.click_at(1000, 800)
            self.assertFalse(am.read_si_variable("g1000_mfd_stream_stale"))
            self.assertEqual(am.read_si_variable("g1000_mfd_rearm_count"), count + 1)

    def test_frames_resuming_clears_the_banner(self):
        with AirManager() as am:
            load(am)
            go_stale(am)
            am.write_dataref(HEARTBEAT, "FLOAT", 110.0)
            self.assertFalse(am.read_si_variable("g1000_mfd_stream_stale"))


if __name__ == "__main__":
    unittest.main()
