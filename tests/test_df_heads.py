"""Behaviour of the two DF heads (Becker 517, RT-600) driven through the cap/df/*
datarefs, the way the engine drives them in X-Plane.

Nothing here writes cap_df.state: the 8- and 9-argument subscription callbacks
and the I-1 redraw gating are part of what is under test (D3 item 3).
"""
import unittest

from tests.am import AirManager

BECKER = "becker-sar-df-517"
RT600 = "rhotheta-rt-600"


def booted(am, head=BECKER):
    am.load_instrument(head)
    am.set_avionics_power(True, 28.0)
    am.step_time(10000)          # past the 10 s (517) / 5 s (RT-600) start-up screen


def screen_text(am):
    """Everything the head draws, as one string, after a fresh repaint."""
    am.eval("_AM.drawn_commands = {}")
    am.eval("for _, c in pairs(_AM.canvases) do canvas_draw(c.id, c.cb) end")
    return "".join(cmd[1] for cmd in am.eval("return _AM.drawn_commands") if cmd[0] == "txt")


class DfAudioIsDrivenByDatarefs(unittest.TestCase):
    def test_squelch_and_signal_drive_the_sounds(self):
        with AirManager() as am:
            booted(am)
            am.publish_df(valid=1, rx_open=1, signal=1.0, bearing_rel=20.0)
            s = am.sounds()
            self.assertEqual(s["elt_analog_df.wav"]["state"], "looping")
            self.assertEqual(s["elt_noise.wav"]["state"], "stopped")

            am.publish_df(signal=0.1)
            s = am.sounds()
            self.assertEqual(s["elt_noise.wav"]["state"], "looping")
            self.assertGreater(s["elt_noise.wav"]["volume"], 0.3)

            am.publish_df(rx_open=0)
            s = am.sounds()
            self.assertEqual(s["elt_analog_df.wav"]["state"], "stopped")
            self.assertEqual(s["elt_noise.wav"]["state"], "stopped")


class WeakSignalDoesNotStutter(unittest.TestCase):
    """I2-4: cap_df_audio re-issued sound_loop(noise) on every update()."""

    def test_burst_of_engine_frames_never_restarts_the_hiss(self):
        for head in (BECKER, RT600):
            with self.subTest(head=head), AirManager() as am:
                booted(am, head)
                am.publish_df(valid=1, rx_open=1, signal=0.10, bearing_rel=10.0)
                self.assertEqual(am.sounds()["elt_noise.wav"]["state"], "looping")
                # A weak signal wobbling by a few percent: each frame is a change
                # big enough to pass the I-1 redraw gating, so audio is re-synced.
                for i in range(40):
                    am.publish_df(signal=0.08 + 0.01 * (i % 6), bearing_rel=10.0 + i)
                noise = am.sounds()["elt_noise.wav"]
                self.assertEqual(noise["state"], "looping")
                self.assertEqual(noise["restarts"], 0,
                                 "sound_loop on an already-looping sound restarts it in Air Manager")
                self.assertEqual(am.sounds()["elt_analog_df.wav"]["restarts"], 0)

    def test_direct_update_burst(self):
        with AirManager() as am:
            booted(am)
            am.publish_df(valid=1, rx_open=1, signal=0.1)
            for _ in range(25):
                am.eval("cap_df_audio.update(true, true, 121.5, 0.6, false, 0.1)")
            self.assertEqual(am.sounds()["elt_noise.wav"]["restarts"], 0)

    def test_hiss_still_starts_and_stops_with_the_signal(self):
        with AirManager() as am:
            booted(am)
            am.publish_df(valid=1, rx_open=1, signal=1.0)
            self.assertEqual(am.sounds()["elt_noise.wav"]["state"], "stopped")
            am.publish_df(signal=0.2)                       # weak: hiss comes in
            self.assertEqual(am.sounds()["elt_noise.wav"]["state"], "looping")
            am.publish_df(signal=1.0)                       # strong again: hiss out
            self.assertEqual(am.sounds()["elt_noise.wav"]["state"], "stopped")
            am.publish_df(signal=0.2)                       # and back: a start, not a restart
            noise = am.sounds()["elt_noise.wav"]
            self.assertEqual(noise["state"], "looping")
            self.assertEqual(noise["restarts"], 0)

    def test_noise_does_not_leak_when_the_tone_changes(self):
        """Changing the wanted tone stops everything, then starts it once."""
        with AirManager() as am:
            booted(am)
            am.publish_df(valid=1, rx_open=1, signal=0.2, band=121.5)
            am.publish_df(band=406.025, signal=0.2)
            s = am.sounds()
            self.assertEqual(s["elt_406_burst.wav"]["state"], "playing")
            self.assertEqual(s["elt_noise.wav"]["state"], "looping")
            self.assertEqual(s["elt_noise.wav"]["restarts"], 0)
            self.assertEqual(s["elt_analog_df.wav"]["state"], "stopped")


class TimersReadDashesBeforeAnySignal(unittest.TestCase):
    """I2-5: LS and BURST read 00:00 before a signal was ever received."""

    def test_becker_last_signal_dashes_then_counts(self):
        with AirManager() as am:
            booted(am)
            am.step_time(3000)
            self.assertIn("LS:--:--", screen_text(am))
            self.assertNotIn("LS:00:00", screen_text(am))

            am.publish_df(valid=1, bearing_rel=33.0, signal=0.6)
            self.assertIn("LS:00:00", screen_text(am))
            am.publish_df(valid=0)
            am.step_time(5000)
            self.assertIn("LS:00:05", screen_text(am))

    def test_rt600_last_signal_and_burst_dashes_before_first_signal(self):
        with AirManager() as am:
            booted(am, RT600)
            am.publish_df(band=406.025)          # tuned to 406, nothing heard yet
            am.step_time(4000)
            text = screen_text(am)
            self.assertIn("--:--LS", text)
            self.assertNotIn("00:00LS", text)

    def test_burst_age_starts_at_the_first_406_acquisition(self):
        with AirManager() as am:
            booted(am, RT600)
            am.publish_df(band=406.025)
            am.step_time(4000)
            self.assertIsNone(am.eval("return cap_df.state.burst_age"))
            am.publish_df(valid=1, bearing_rel=90.0, signal=0.7)
            self.assertEqual(am.eval("return cap_df.state.burst_age"), 0)
            am.step_time(3000)
            self.assertGreaterEqual(am.eval("return cap_df.state.burst_age"), 2.75)


class PowerCycleClearsVolatileUiState(unittest.TestCase):
    """I2-6: the real head powers up clean."""

    def test_becker_tone_suppression_does_not_survive_a_power_cycle(self):
        with AirManager() as am:
            booted(am)
            am.click_button_matching(x=234, y=18)               # STORE: suppress the 3 kHz tone
            self.assertIn("3K-", screen_text(am))

            am.set_avionics_power(False, 0.0)
            am.set_avionics_power(True, 28.0)
            am.step_time(10000)
            self.assertNotIn("3K-", screen_text(am))
            # ... and the audio path agrees: tone suppression is what STORE toggles.
            am.publish_df(valid=1, rx_open=1, signal=1.0, band=121.5)
            self.assertEqual(am.sounds()["elt_analog_df.wav"]["state"], "looping")

    def test_becker_shown_c_s_message_does_not_survive_a_power_cycle(self):
        with AirManager() as am:
            booted(am)
            for _ in range(3):
                am.turn_dial_matching(1, x=405, y=15)           # PAGE knob to page 4
            am.publish_df(cs_sync=1, cs_protocol=1, cs_country=366,
                          cs_has_position=0, cs_hex15="AD4800000000000")
            am.click_button_matching(x=234, y=18)               # STORE it
            am.click_button_matching(x=320, y=18)               # REP: show the stored frame
            self.assertIn("AD48", screen_text(am))

            am.set_avionics_power(False, 0.0)
            am.set_avionics_power(True, 28.0)
            am.step_time(10000)
            am.publish_df(cs_hex15="BB0000000000000")
            for _ in range(3):
                am.turn_dial_matching(1, x=405, y=15)
            text = screen_text(am)
            self.assertIn("BB00", text, "page 4 should show the live frame")
            self.assertNotIn("AD48", text, "the previously shown frame must not survive power-off")

    def test_becker_repeat_display_is_cleared_by_power_off(self):
        """Guard: REP held across a power cut must not leave the repeat bearing up."""
        with AirManager() as am:
            booted(am)
            am.publish_df(valid=1, bearing_rel=77.0, signal=0.8)
            am.press_button(am.find_button_matching(x=320, y=18))     # REP held: repeat shown
            am.set_avionics_power(False, 0.0)
            am.release_button(am.find_button_matching(x=320, y=18))   # released while dark
            am.set_avionics_power(True, 28.0)
            am.step_time(10000)
            am.publish_df(bearing_rel=120.0)
            self.assertIn("120", screen_text(am))


if __name__ == "__main__":
    unittest.main()
