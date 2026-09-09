"""Tests for Technisonic TDFM-136B airborne transceiver simulation."""
import unittest
from tests.am import AirManager


class TestTDFM136B(unittest.TestCase):
    def test_tot_timer_unkeys_at_60s(self):
        """PTT held continuously unkeys after 60s, displays TOT warning, and locks out until released."""
        with AirManager() as am:
            am.load_instrument("cap-fm-tdfm-136b")

            # Turn on radio power via Main encoder press (x=80, y=202)
            am.press_dial_matching(x=80, y=202)
            self.assertTrue(am.read_si_variable("cap_fm_power_on"))

            # MO selects COM3 MIC on GMA 1347
            am.write_si_variable("cap_fm_mic_selected", True)

            # Observer presses PTT
            am.write_si_variable("cap_fm_ptt", True)
            self.assertTrue(am.read_si_variable("cap_fm_transmitting"))

            # After 30 seconds, still transmitting
            am.step_time(30000)
            self.assertTrue(am.read_si_variable("cap_fm_transmitting"))

            # At 60 seconds, TOT must force unkey
            am.step_time(30000)
            self.assertFalse(am.read_si_variable("cap_fm_transmitting"),
                             "TDFM-136B must unkey transmitter when 60s TOT timer expires")

            # Must display TOT warning on the active row
            drawn = am.eval("return _AM.drawn_commands")
            drawn_text = "".join(cmd[1] for cmd in drawn if cmd[0] == "txt")
            self.assertTrue("TIME OUT" in drawn_text or "TIMEOUT" in drawn_text or "TOT" in drawn_text,
                            f"Display must show TIME OUT or TOT warning, got: {drawn_text}")

            # While PTT is still held, cannot re-transmit
            am.step_time(5000)
            self.assertFalse(am.read_si_variable("cap_fm_transmitting"))

            # Releasing PTT clears TOT lockout
            am.write_si_variable("cap_fm_ptt", False)
            am.step_time(500)

            # Re-keying PTT transmits again
            am.write_si_variable("cap_fm_ptt", True)
            self.assertTrue(am.read_si_variable("cap_fm_transmitting"))

    def test_copilot_ptt_xplane_dataref(self):
        """X-Plane copilot PTT dataref keys TDFM transmission when powered and COM3 MIC selected."""
        with AirManager() as am:
            am.load_instrument("cap-fm-tdfm-136b")
            am.press_dial_matching(x=80, y=202)  # Power ON
            am.write_si_variable("cap_fm_mic_selected", True)

            self.assertFalse(am.read_si_variable("cap_fm_transmitting"))

            # Press copilot PTT via X-Plane dataref
            am.write_dataref("sim/cockpit2/radios/actuators/audio_panel_copilot_ptt", "INT", 1)
            self.assertTrue(am.read_si_variable("cap_fm_transmitting"))

            # Release copilot PTT
            am.write_dataref("sim/cockpit2/radios/actuators/audio_panel_copilot_ptt", "INT", 0)
            self.assertFalse(am.read_si_variable("cap_fm_transmitting"))

    def test_squelch_leds_rx(self):
        """cap_fm_main_rx and cap_fm_guard_rx drive squelch indicator LEDs, gated by radio power."""
        with AirManager() as am:
            am.load_instrument("cap-fm-tdfm-136b")

            # Find the two led_on image IDs
            led_on_ids = am.eval("""
                local ids = {}
                for id, img in pairs(_AM.images) do
                    if img.file == "led_on.png" then table.insert(ids, id) end
                end
                table.sort(ids)
                return ids
            """)
            self.assertEqual(len(led_on_ids), 2, "Expected 2 'led_on.png' elements for Main and Guard")
            main_led_id, guard_led_id = led_on_ids[0], led_on_ids[1]

            # Initially off when unpowered
            self.assertFalse(am.is_visible(main_led_id))
            self.assertFalse(am.is_visible(guard_led_id))

            # Trigger RX while radio is still off -> LEDs must remain unlit
            am.write_si_variable("cap_fm_main_rx", True)
            self.assertFalse(am.is_visible(main_led_id))

            # Turn power ON
            am.press_dial_matching(x=80, y=202)
            self.assertTrue(am.read_si_variable("cap_fm_power_on"))
            # Now Main LED must illuminate
            self.assertTrue(am.is_visible(main_led_id))
            self.assertFalse(am.is_visible(guard_led_id))

            # Trigger Guard RX -> both illuminate
            am.write_si_variable("cap_fm_guard_rx", True)
            self.assertTrue(am.is_visible(main_led_id))
            self.assertTrue(am.is_visible(guard_led_id))

            # Clear Main RX -> only Guard remains lit
            am.write_si_variable("cap_fm_main_rx", False)
            self.assertFalse(am.is_visible(main_led_id))
            self.assertTrue(am.is_visible(guard_led_id))

    def test_channel_plan_and_direct_3digit_entry(self):
        """Authentic CAP fleet plan is loaded and 3-digit direct entry (e.g. 015 -> VFIRE 21) works."""
        with AirManager() as am:
            am.load_instrument("cap-fm-tdfm-136b")
            am.press_dial_matching(x=80, y=202)  # Power ON

            # Default channel is 1 (TAC 1, 148.1500 MHz, CTCSS 110.9 Hz)
            self.assertEqual(am.read_si_variable("cap_fm_channel"), 1)
            self.assertEqual(am.read_si_variable("cap_fm_channel_name"), "TAC 1")
            self.assertEqual(am.read_si_variable("cap_fm_frequency_hz"), 148150000)
            self.assertAlmostEqual(am.read_si_variable("cap_fm_ctcss_tone"), 110.9, places=1)

            # Direct 3-digit entry: press '1' (CHAN), then '0', '1', '5' -> selects VFIRE 21
            am.click_button_matching("key_1.")
            am.click_button_matching("key_0.")
            am.click_button_matching("key_1.")
            am.click_button_matching("key_5.")

            # Must switch to channel 15: VFIRE 21, 154.2800 MHz, CTCSS 156.7 Hz
            self.assertEqual(am.read_si_variable("cap_fm_channel"), 15)
            self.assertEqual(am.read_si_variable("cap_fm_channel_name"), "VFIRE 21")
            self.assertEqual(am.read_si_variable("cap_fm_frequency_hz"), 154280000)
            self.assertAlmostEqual(am.read_si_variable("cap_fm_ctcss_tone"), 156.7, places=1)

            # Direct entry for a digital P25 channel: '0', '0', '3' -> CC 1 (150.2250 MHz, NAC $293)
            am.click_button_matching("key_1.")
            am.click_button_matching("key_0.")
            am.click_button_matching("key_0.")
            am.click_button_matching("key_3.")

            self.assertEqual(am.read_si_variable("cap_fm_channel"), 3)
            self.assertEqual(am.read_si_variable("cap_fm_channel_name"), "CC 1")
            self.assertEqual(am.read_si_variable("cap_fm_frequency_hz"), 150225000)
            self.assertEqual(am.read_si_variable("cap_fm_p25_nac"), 0x293)

            # Direct entry for high memory channel (e.g. 200)
            am.click_button_matching("key_1.")
            am.click_button_matching("key_2.")
            am.click_button_matching("key_0.")
            am.click_button_matching("key_0.")

            self.assertEqual(am.read_si_variable("cap_fm_channel"), 200)
            self.assertEqual(am.read_si_variable("cap_fm_channel_name"), "CHAN 200")

    def test_guard_receiver_independence(self):
        """Guard receiver operates independently with its own frequency, channel, and volume."""
        with AirManager() as am:
            am.load_instrument("cap-fm-tdfm-136b")
            am.press_dial_matching(x=80, y=202)  # Power ON

            # Main receiver is on TAC 1 (148.150 MHz)
            self.assertEqual(am.read_si_variable("cap_fm_channel"), 1)
            self.assertEqual(am.read_si_variable("cap_fm_frequency_hz"), 148150000)

            # Guard receiver is independently tuned to GUARD 1 (148.150 MHz, tone 110.9)
            self.assertEqual(am.read_si_variable("cap_fm_guard_channel"), 101)
            self.assertEqual(am.read_si_variable("cap_fm_guard_channel_name"), "GUARD 1")
            self.assertEqual(am.read_si_variable("cap_fm_guard_frequency_hz"), 148150000)
            self.assertAlmostEqual(am.read_si_variable("cap_fm_guard_ctcss_tone"), 110.9, places=1)

            # Volume dials publish normalized volume
            self.assertAlmostEqual(am.read_si_variable("cap_fm_main_volume"), 0.6, places=2)
            self.assertAlmostEqual(am.read_si_variable("cap_fm_guard_volume"), 0.4, places=2)

            # Rotate Guard encoder (x=188, y=202)
            am.turn_dial_matching(1, x=188, y=202)
            self.assertGreater(am.read_si_variable("cap_fm_guard_volume"), 0.4)

            # Rotate Main encoder (x=80, y=202)
            am.turn_dial_matching(1, x=80, y=202)
            self.assertGreater(am.read_si_variable("cap_fm_main_volume"), 0.6)

            # Toggle G1/G2 switch (x=213, y=339) to switch to GUARD 2 (148.125 MHz)
            am.click_switch_matching(x=213, y=339)
            self.assertEqual(am.read_si_variable("cap_fm_guard_channel"), 102)
            self.assertEqual(am.read_si_variable("cap_fm_guard_channel_name"), "GUARD 2")
            self.assertEqual(am.read_si_variable("cap_fm_guard_frequency_hz"), 148125000)

            # Main receiver remains on channel 1
            self.assertEqual(am.read_si_variable("cap_fm_channel"), 1)
            self.assertEqual(am.read_si_variable("cap_fm_frequency_hz"), 148150000)

    def test_scan_mode_channel_cycling_and_carrier_halt(self):
        """Scan mode cycles memories, halts on carrier, and resumes after 2s hold delay."""
        with AirManager() as am:
            am.load_instrument("cap-fm-tdfm-136b")
            am.press_dial_matching(x=80, y=202)  # Power ON

            self.assertEqual(am.read_si_variable("cap_fm_channel"), 1)

            # Press '5' (SCAN) to begin scanning
            am.click_button_matching("key_5.")

            # Scan should advance through channels every 250 ms
            am.step_time(250)
            self.assertEqual(am.read_si_variable("cap_fm_channel"), 2)

            am.step_time(250)
            self.assertEqual(am.read_si_variable("cap_fm_channel"), 3)

            # Carrier activity arrives on channel 3
            am.write_si_variable("cap_fm_main_rx", True)

            # Advance 1000 ms -> scan must remain paused on channel 3
            am.step_time(1000)
            self.assertEqual(am.read_si_variable("cap_fm_channel"), 3)

            # Carrier drops
            am.write_si_variable("cap_fm_main_rx", False)

            # Still within 2000 ms hold interval -> must remain on channel 3
            am.step_time(1500)
            self.assertEqual(am.read_si_variable("cap_fm_channel"), 3)

            # After hold timer expires (> 2000 ms), scan resumes advancing
            am.step_time(600)
            self.assertEqual(am.read_si_variable("cap_fm_channel"), 4)

            # Press '5' again to disengage scan
            am.click_button_matching("key_5.")
            am.step_time(500)
            self.assertEqual(am.read_si_variable("cap_fm_channel"), 4)


if __name__ == "__main__":
    unittest.main()
