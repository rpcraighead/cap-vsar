"""GMA 1347 behaviour that depends on the real X-Plane and Air Manager API (I2-1, I2-3, G)."""
import unittest

from tests.am import AirManager

# KNOB_INNER x=97 y=1193 w=46 h=46 in lib/gma_panel.lua; the rings are concentric,
# so this is the centre of both. The VOL/SQ push is a knob_push button there.
KNOB_CENTRE = (120, 1216)
KNOB_OUTER_RIM = (82, 1216)      # on the outer ring, outside the inner knob


def powered_gma(am):
    am.load_instrument("mo-audio-panel-gma1347")
    am.set_avionics_power(True, 28.0)
    am.step_time(2000)


class ClearanceRecorderDatarefs(unittest.TestCase):
    def test_recorder_uses_the_real_atc_rx_datarefs(self):
        """I2-1: sim/atc/com1_rx and com2_rx, not the nonexistent radios/indicators names."""
        with AirManager() as am:
            powered_gma(am)
            self.assertEqual(am.read_si_variable("cap_recorder_count"), 0)

            am.write_dataref("sim/atc/com1_rx", "INT", 1)
            am.write_dataref("sim/atc/com1_rx", "INT", 0)
            self.assertEqual(am.read_si_variable("cap_recorder_count"), 1)

            am.write_dataref("sim/atc/com2_rx", "INT", 1)
            am.write_dataref("sim/atc/com2_rx", "INT", 0)
            self.assertEqual(am.read_si_variable("cap_recorder_count"), 2)

    def test_unpowered_panel_records_nothing(self):
        with AirManager() as am:
            am.load_instrument("mo-audio-panel-gma1347")
            am.write_dataref("sim/atc/com1_rx", "INT", 1)
            am.write_dataref("sim/atc/com1_rx", "INT", 0)
            self.assertEqual(am.read_si_variable("cap_recorder_count"), 0)

    def test_power_loss_mid_transmission_does_not_record_a_phantom_block(self):
        """Improvement G: active_rx is cleared on power loss, so a stale 'receiving'
        flag cannot turn the next power-up's first idle into a recorded block."""
        with AirManager() as am:
            powered_gma(am)
            am.write_dataref("sim/atc/com1_rx", "INT", 1)       # transmission starts
            am.write_dataref("sim/cockpit2/electrical/bus_volts", "FLOAT[6]", 0.0)   # power lost
            am.write_dataref("sim/cockpit2/electrical/bus_volts", "FLOAT[6]", 28.0)  # and back
            am.step_time(2000)
            # The transmission ended while we were dark; the panel is back up and
            # sees com1_rx fall. Nothing was heard, so nothing is recorded.
            am.write_dataref("sim/atc/com1_rx", "INT", 0)
            self.assertEqual(am.read_si_variable("cap_recorder_count"), 0)


class FmRecorderGating(unittest.TestCase):
    """Part 5 of DATAREF_CONTRACT.md: cap_fm_* values are stale while cap_fm_power_on is false."""

    def test_dark_fm_radio_is_not_recorded(self):
        with AirManager() as am:
            am.load_instrument("mo-audio-panel-gma1347")
            am.load_instrument("cap-fm-tdfm-136b")
            am.set_avionics_power(True, 28.0)
            am.step_time(2000)
            self.assertTrue(am.read_si_variable("cap_fm_power_on"))

            am.write_si_variable("cap_fm_main_rx", True)
            am.write_si_variable("cap_fm_main_rx", False)
            self.assertEqual(am.read_si_variable("cap_recorder_count"), 1)

            # Hold the TDFM main encoder: radio off. Its channel/frequency stay
            # published at their last values; the carrier must not be recorded.
            am.press_at(118, 240)
            am.step_time(1500)
            am.release_at(118, 240)
            self.assertFalse(am.read_si_variable("cap_fm_power_on"))
            self.assertEqual(am.read_si_variable("cap_fm_frequency_hz"), 148150000)

            am.write_si_variable("cap_fm_main_rx", True)
            am.write_si_variable("cap_fm_main_rx", False)
            self.assertEqual(am.read_si_variable("cap_recorder_count"), 1)

    def test_radio_going_dark_mid_call_leaves_no_phantom_block(self):
        with AirManager() as am:
            am.load_instrument("mo-audio-panel-gma1347")
            am.load_instrument("cap-fm-tdfm-136b")
            am.set_avionics_power(True, 28.0)
            am.step_time(2000)
            am.write_si_variable("cap_fm_main_rx", True)
            am.write_si_variable("cap_mission_cb_fm_in", False)     # FM breaker pulled
            self.assertFalse(am.read_si_variable("cap_fm_power_on"))
            am.write_si_variable("cap_mission_cb_fm_in", True)      # pushed back in
            am.write_si_variable("cap_fm_main_rx", False)
            self.assertEqual(am.read_si_variable("cap_recorder_count"), 0)


class VolSqPush(unittest.TestCase):
    def _mode_nodes(self, am):
        texts = am.eval("return _AM.texts")
        items = texts.values() if isinstance(texts, dict) else texts
        by = {t["text"]: t["id"] for t in items if t.get("text") in ("VOL", "SQ")}
        return by["VOL"], by["SQ"]

    def test_knob_push_toggles_vol_and_sq_only_with_man_sq(self):
        """I2-3: the ring's push is a button over the knob centre, not a dial press callback."""
        with AirManager() as am:
            powered_gma(am)
            vol, sq = self._mode_nodes(am)
            self.assertTrue(am.is_visible(vol))
            self.assertFalse(am.is_visible(sq))

            # Auto squelch: the push has no effect (Pilot's Guide, VOLUME/SQUELCH CONTROL).
            am.click_at(*KNOB_CENTRE)
            self.assertTrue(am.is_visible(vol))
            self.assertFalse(am.is_visible(sq))

            am.click_button_matching("man_sq")
            am.click_at(*KNOB_CENTRE)
            self.assertFalse(am.is_visible(vol))
            self.assertTrue(am.is_visible(sq))
            am.click_at(*KNOB_CENTRE)
            self.assertTrue(am.is_visible(vol))

    def test_push_button_sits_above_both_rings_and_turns_still_reach_them(self):
        with AirManager() as am:
            powered_gma(am)
            btn = am.button_at(*KNOB_CENTRE)
            inner = am.dial_at(*KNOB_CENTRE)
            outer = am.dial_at(*KNOB_OUTER_RIM)
            self.assertIsNotNone(btn)
            self.assertGreater(btn, inner)
            self.assertGreater(inner, outer)
            # Turning the outer (copilot) ring writes the copilot volume dataref.
            am.turn_at(*KNOB_OUTER_RIM, 1)
            self.assertAlmostEqual(
                am.read_dataref("sim/operation/sound/radio_copilot_audio_panel_volume_ratio"), 0.72)


if __name__ == "__main__":
    unittest.main()
