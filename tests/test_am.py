"""Unit tests for the Air Manager 4.2 Lua execution harness (tests/am.py).

Verifies that:
- All four instruments load, initialize, and run.
- Loading lib/*.lua in arbitrary shuffled orders does not fail.
- canvas_draw requires a callback, mirroring AM 4.2 behavior.
- Timers, Si variables, datarefs, buttons, switches, and dials function properly.
"""
import glob
import itertools
from pathlib import Path
import unittest

from tests.am import AirManager, ROOT

INSTRUMENTS = [
    "cap-fm-tdfm-136b",
    "mo-audio-panel-gma1347",
    "becker-sar-df-517",
    "rhotheta-rt-600",
]


class TestAirManagerHarness(unittest.TestCase):
    def test_all_instruments_load_and_run(self):
        """Every instrument in instruments/ loads without error in the harness."""
        for inst_name in INSTRUMENTS:
            with AirManager() as am:
                am.load_instrument(inst_name)
                self.assertEqual(am.instrument_name, inst_name)

    def test_shuffled_lib_load_order(self):
        """Lib files can be loaded in any order without load-time global collisions."""
        for inst_name in INSTRUMENTS:
            inst_dir = ROOT / "instruments" / inst_name
            libs = sorted(inst_dir.glob("lib/*.lua"))
            if len(libs) <= 1:
                continue
            # Test all permutations if <= 6, else sample permutations
            perms = list(itertools.permutations(libs))
            if len(perms) > 6:
                perms = perms[:6]
            for p in perms:
                with AirManager() as am:
                    am.load_instrument(inst_name, lib_order=p)

    def test_canvas_draw_requires_callback(self):
        """Calling canvas_draw without a callback throws an error, as in AM 4.2."""
        with AirManager() as am:
            with self.assertRaises(RuntimeError) as ctx:
                am.eval("canvas_draw(1)")
            self.assertIn("canvas_draw requires callback", str(ctx.exception))

    def test_timer_progression(self):
        """timer_start, timer_stop, and step_time fire single-shot and recurring timers."""
        with AirManager() as am:
            am.eval("""
                ticks = 0
                one_shot = 0
                timer_start(1000, 0, function() one_shot = one_shot + 1 end)
                timer_start(500, 500, function() ticks = ticks + 1 end)
            """)
            self.assertEqual(am.eval("return ticks"), 0)
            self.assertEqual(am.eval("return one_shot"), 0)

            am.step_time(500)
            self.assertEqual(am.eval("return ticks"), 1)
            self.assertEqual(am.eval("return one_shot"), 0)

            am.step_time(500)
            self.assertEqual(am.eval("return ticks"), 2)
            self.assertEqual(am.eval("return one_shot"), 1)

            am.step_time(1000)
            self.assertEqual(am.eval("return ticks"), 4)
            self.assertEqual(am.eval("return one_shot"), 1)  # one-shot does not re-fire

    def test_si_variable_pub_sub(self):
        """Si variables can be created, subscribed, written, and read."""
        with AirManager() as am:
            am.eval("""
                v_seen = nil
                si_variable_create('test_var', 'INT', 42)
                si_variable_subscribe('test_var', 'INT', function(v) v_seen = v end)
            """)
            self.assertEqual(am.eval("return v_seen"), 42)
            self.assertEqual(am.read_si_variable("test_var"), 42)

            am.write_si_variable("test_var", 99)
            self.assertEqual(am.eval("return v_seen"), 99)
            self.assertEqual(am.read_si_variable("test_var"), 99)

    def test_gma1347_power_and_mic_interlock(self):
        """GMA 1347 powers on, runs 2s self test, and sets COM3 mic/audio variables."""
        with AirManager() as am:
            am.load_instrument("mo-audio-panel-gma1347")
            # Initially unpowered
            self.assertFalse(am.read_si_variable("cap_fm_mic_selected"))
            self.assertFalse(am.read_si_variable("cap_fm_audio_selected"))

            # Turn on avionics master
            am.write_dataref("sim/cockpit2/switches/avionics_power_on", "INT", 1)
            # Advance past 2s self test
            am.step_time(2000)

            # Press COM3 MIC key
            am.click_button_matching("com3_mic")
            self.assertTrue(am.read_si_variable("cap_fm_mic_selected"))
            self.assertTrue(am.read_si_variable("cap_fm_audio_selected"))

            # Press COM1 MIC key (moves mic away from COM3, but COM3 audio remains)
            am.click_button_matching("com1_mic")
            self.assertFalse(am.read_si_variable("cap_fm_mic_selected"))
            self.assertTrue(am.read_si_variable("cap_fm_audio_selected"))

    def test_becker_tone_suppression_resets_on_freq_change(self):
        """Becker 517 STORE suppresses 3 kHz tone on 121.5, and frequency dial change clears suppression."""
        with AirManager() as am:
            am.load_instrument("becker-sar-df-517")
            # Power ON button: x=238, y=456
            am.click_button_matching(x=238, y=456)
            # Advance past 10s boot screen
            am.step_time(10000)

            # Clear drawn command history before testing
            am.eval("_AM.drawn_commands = {}")
            am.eval("if canvas_id then canvas_draw(canvas_id, draw_lcd) end")
            drawn = am.eval("return _AM.drawn_commands")
            drawn_text = "".join(cmd[1] for cmd in drawn if cmd[0] == "txt")
            self.assertNotIn("3K-", drawn_text)

            # Press STORE button: x=234, y=18 to suppress 3 kHz tone
            am.eval("_AM.drawn_commands = {}")
            am.click_button_matching(x=234, y=18)
            drawn = am.eval("return _AM.drawn_commands")
            drawn_text = "".join(cmd[1] for cmd in drawn if cmd[0] == "txt")
            self.assertIn("3K-", drawn_text, f"Display should show 3K- after STORE press, got: {drawn_text}")

            # Turn frequency dial: x=405, y=405 to change band/channel
            am.eval("_AM.drawn_commands = {}")
            am.turn_dial_matching(1, x=405, y=405)
            drawn = am.eval("return _AM.drawn_commands")
            drawn_text = "".join(cmd[1] for cmd in drawn if cmd[0] == "txt")
            self.assertNotIn("3K-", drawn_text, f"Display must not retain 3K- on frequency change, got: {drawn_text}")

    def test_gma1347_ics_isolation_and_split_com(self):
        """GMA 1347 implements Table 6A.3.2 ICS isolation states and Split COM drops MO from mission net."""
        with AirManager() as am:
            am.load_instrument("mo-audio-panel-gma1347")
            am.write_dataref("sim/cockpit2/switches/avionics_power_on", "INT", 1)
            am.step_time(2000)

            # Default mode is ALL
            self.assertEqual(am.read_si_variable("cap_ics_isolation"), "ALL")
            self.assertFalse(am.read_si_variable("cap_ics_pilot_isolated"))
            self.assertFalse(am.read_si_variable("cap_ics_copilot_isolated"))
            self.assertFalse(am.read_si_variable("cap_ics_crew_isolated"))
            self.assertFalse(am.read_si_variable("cap_split_com_active"))

            # Press PILOT key -> mode becomes PILOT
            am.click_button_matching("pilot")
            self.assertEqual(am.read_si_variable("cap_ics_isolation"), "PILOT")
            self.assertTrue(am.read_si_variable("cap_ics_pilot_isolated"))
            self.assertTrue(am.read_si_variable("cap_ics_copilot_isolated"))
            self.assertFalse(am.read_si_variable("cap_ics_crew_isolated"))

            # Press COPLT key -> mode becomes CREW (Table 6A.3.2: PILOT + COPLT = CREW)
            am.click_button_matching("coplt")
            self.assertEqual(am.read_si_variable("cap_ics_isolation"), "CREW")
            self.assertFalse(am.read_si_variable("cap_ics_pilot_isolated"))
            self.assertFalse(am.read_si_variable("cap_ics_copilot_isolated"))
            self.assertTrue(am.read_si_variable("cap_ics_crew_isolated"))

            # Press PILOT key -> mode returns to COPILOT
            am.click_button_matching("pilot")
            self.assertEqual(am.read_si_variable("cap_ics_isolation"), "COPILOT")
            self.assertFalse(am.read_si_variable("cap_ics_pilot_isolated"))
            self.assertTrue(am.read_si_variable("cap_ics_copilot_isolated"))
            self.assertFalse(am.read_si_variable("cap_ics_crew_isolated"))

            # Press COPLT key -> returns to ALL
            am.click_button_matching("coplt")
            self.assertEqual(am.read_si_variable("cap_ics_isolation"), "ALL")

            # Select COM3 MIC -> observer is on FM mission net
            am.click_button_matching("com3_mic")
            self.assertTrue(am.read_si_variable("cap_fm_mic_selected"))
            self.assertTrue(am.read_si_variable("cap_fm_audio_selected"))

            # Press SPLIT COM -> copilot is locked to COM2, MO dropped from FM mission net
            am.click_button_matching("split")
            self.assertTrue(am.read_si_variable("cap_split_com_active"))
            self.assertFalse(am.read_si_variable("cap_fm_mic_selected"))
            self.assertFalse(am.read_si_variable("cap_fm_audio_selected"))

            # Press SPLIT COM again to disable -> restored
            am.click_button_matching("split")
            self.assertFalse(am.read_si_variable("cap_split_com_active"))

    def test_gma1347_clearance_recorder(self):
        """Clearance recorder buffers incoming COM transmissions and replays in reverse order on PLAY."""
        with AirManager() as am:
            am.load_instrument("mo-audio-panel-gma1347")
            am.write_dataref("sim/cockpit2/switches/avionics_power_on", "INT", 1)
            am.step_time(2000)

            self.assertEqual(am.read_si_variable("cap_recorder_count"), 0)
            self.assertFalse(am.read_si_variable("cap_recorder_playing"))

            # COM1 receives a clearance transmission
            am.write_dataref("sim/cockpit2/radios/indicators/com1_receiving", "INT", 1)
            am.step_time(100)
            am.write_dataref("sim/cockpit2/radios/indicators/com1_receiving", "INT", 0)
            self.assertEqual(am.read_si_variable("cap_recorder_count"), 1)

            # COM3 receives a mission radio message
            am.write_si_variable("cap_fm_main_rx", True)
            am.step_time(100)
            am.write_si_variable("cap_fm_main_rx", False)
            self.assertEqual(am.read_si_variable("cap_recorder_count"), 2)

            # Press PLAY -> plays latest recorded block (block 2)
            am.click_button_matching("play")
            self.assertTrue(am.read_si_variable("cap_recorder_playing"))
            self.assertEqual(am.read_si_variable("cap_recorder_block"), 2)

            # Press PLAY again while playing -> steps back to block 1 (reverse chronological)
            am.click_button_matching("play")
            self.assertTrue(am.read_si_variable("cap_recorder_playing"))
            self.assertEqual(am.read_si_variable("cap_recorder_block"), 1)

            # Press MKR/MUTE -> immediately aborts playback
            am.click_button_matching("mkr")
            self.assertFalse(am.read_si_variable("cap_recorder_playing"))
            self.assertEqual(am.read_si_variable("cap_recorder_block"), 0)

    def test_df_audio_snr_degradation(self):
        """DF audio modulates receiver hiss inversely with RF signal strength."""
        with AirManager() as am:
            am.load_instrument("becker-sar-df-517")
            # Power ON and wait past boot screen
            am.click_button_matching(x=238, y=456)
            am.step_time(10000)

            # Squelch open, 100% signal -> clean beacon audio, noise inactive
            am.eval("""
                cap_df_audio.update(true, true, 121.5, 0.6, false, 1.0)
            """)
            sounds = [s for s in am.eval("return _AM.sounds") if isinstance(s, dict)]
            noise_sound = next(s for s in sounds if s.get("file") == "elt_noise.wav")
            analog_sound = next(s for s in sounds if s.get("file") == "elt_analog_df.wav")

            self.assertEqual(analog_sound["state"], "looping")
            self.assertAlmostEqual(noise_sound["volume"], 0.0, places=2)

            # Weak / masked signal: signal drops to 10%
            am.eval("""
                cap_df_audio.update(true, true, 121.5, 0.6, false, 0.1)
            """)
            sounds = [s for s in am.eval("return _AM.sounds") if isinstance(s, dict)]
            noise_sound = next(s for s in sounds if s.get("file") == "elt_noise.wav")
            analog_sound = next(s for s in sounds if s.get("file") == "elt_analog_df.wav")

            # Noise should now be looping with audible gain
            self.assertEqual(noise_sound["state"], "looping")
            self.assertGreater(noise_sound["volume"], 0.3)
            # Tone volume should be significantly attenuated
            self.assertLess(analog_sound["volume"], 0.3)

            # Close squelch -> both stop
            am.eval("""
                cap_df_audio.update(true, false, 121.5, 0.6, false, 0.1)
            """)
            sounds = [s for s in am.eval("return _AM.sounds") if isinstance(s, dict)]
            noise_sound = next(s for s in sounds if s.get("file") == "elt_noise.wav")
            analog_sound = next(s for s in sounds if s.get("file") == "elt_analog_df.wav")
            self.assertEqual(analog_sound["state"], "stopped")
            self.assertEqual(noise_sound["state"], "stopped")


if __name__ == "__main__":
    unittest.main()
