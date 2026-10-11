"""Tests for the mission-kit master switch, circuit breaker panel, and the
power-gating they add to the DF heads, TDFM-136B and GMA 1347.

See docs/DATAREF_CONTRACT.md Part 6. Uses the same Lua-in-Python harness as
tests/test_tdfm.py; no X-Plane or Air Manager required.
"""
import unittest

from tests.am import AirManager

# The TDFM main encoder's push is a button over the knob centre (knob_push):
# MAIN_ENC is x=80 y=202 w=76 h=76 in lib/tdfm_panel.lua.
TDFM_MAIN_ENC_CENTRE = (118, 240)


class TestMissionMasterSwitch(unittest.TestCase):
    def test_defaults_on(self):
        with AirManager() as am:
            am.load_instrument("cap-mission-master-switch")
            self.assertTrue(am.read_si_variable("cap_mission_master_on"))

    def test_switch_ignored_with_guard_closed(self):
        with AirManager() as am:
            am.load_instrument("cap-mission-master-switch")
            btn = am.find_button_matching(x=110, y=74)
            am.click_button(btn)
            self.assertTrue(am.read_si_variable("cap_mission_master_on"),
                             "switch must not respond while the guard is down")

    def test_lift_guard_then_switch_off_and_on(self):
        with AirManager() as am:
            am.load_instrument("cap-mission-master-switch")
            guard = am.find_button_matching(x=102, y=40)
            switch = am.find_button_matching(x=110, y=74)

            am.click_button(guard)   # lift guard
            am.click_button(switch)  # OFF
            self.assertFalse(am.read_si_variable("cap_mission_master_on"))

            am.click_button(switch)  # ON again, guard still open
            self.assertTrue(am.read_si_variable("cap_mission_master_on"))

    def test_closing_guard_locks_switch_again(self):
        with AirManager() as am:
            am.load_instrument("cap-mission-master-switch")
            guard = am.find_button_matching(x=102, y=40)
            switch = am.find_button_matching(x=110, y=74)

            am.click_button(guard)   # open
            am.click_button(guard)   # closed again
            am.click_button(switch)
            self.assertTrue(am.read_si_variable("cap_mission_master_on"),
                             "switch must not respond once the guard is closed again")


class TestMissionCBPanel(unittest.TestCase):
    BREAKER_BUTTONS = {"df": (54, 46), "fm": (228, 46), "audio": (401, 46)}
    VARS = {"df": "cap_mission_cb_df_in", "fm": "cap_mission_cb_fm_in",
            "audio": "cap_mission_cb_audio_in"}

    def test_defaults_all_in(self):
        with AirManager() as am:
            am.load_instrument("cap-mission-cb-panel")
            for var in self.VARS.values():
                self.assertTrue(am.read_si_variable(var))

    def test_pulling_one_breaker_does_not_affect_the_others(self):
        with AirManager() as am:
            am.load_instrument("cap-mission-cb-panel")
            x, y = self.BREAKER_BUTTONS["fm"]
            btn = am.find_button_matching(x=x, y=y)
            am.click_button(btn)

            self.assertFalse(am.read_si_variable("cap_mission_cb_fm_in"))
            self.assertTrue(am.read_si_variable("cap_mission_cb_df_in"))
            self.assertTrue(am.read_si_variable("cap_mission_cb_audio_in"))

            am.click_button(btn)  # push back in
            self.assertTrue(am.read_si_variable("cap_mission_cb_fm_in"))


class TestMissionGatingIntegration(unittest.TestCase):
    """The mission master switch / breakers must AND into each consumer's
    existing airframe-bus power gate without a producer instrument present."""

    def test_tdfm_powers_on_with_defaults_and_bus_up(self):
        with AirManager() as am:
            am.load_instrument("cap-fm-tdfm-136b")
            am.set_avionics_power(True, 28.0)
            am.press_at(*TDFM_MAIN_ENC_CENTRE)
            am.release_at(*TDFM_MAIN_ENC_CENTRE)
            self.assertTrue(am.read_si_variable("cap_fm_power_on"))

    def test_mission_master_off_cuts_tdfm_even_with_bus_up(self):
        with AirManager() as am:
            am.load_instrument("cap-fm-tdfm-136b")
            am.set_avionics_power(True, 28.0)
            am.press_at(*TDFM_MAIN_ENC_CENTRE)
            am.release_at(*TDFM_MAIN_ENC_CENTRE)
            self.assertTrue(am.read_si_variable("cap_fm_power_on"))

            am.write_si_variable("cap_mission_master_on", False)
            self.assertFalse(am.read_si_variable("cap_fm_power_on"),
                              "mission master OFF must cut TDFM power even with the aircraft bus up")

    def test_fm_breaker_pulled_cuts_tdfm(self):
        with AirManager() as am:
            am.load_instrument("cap-fm-tdfm-136b")
            am.set_avionics_power(True, 28.0)
            am.press_at(*TDFM_MAIN_ENC_CENTRE)
            am.release_at(*TDFM_MAIN_ENC_CENTRE)
            self.assertTrue(am.read_si_variable("cap_fm_power_on"))

            am.write_si_variable("cap_mission_cb_fm_in", False)
            self.assertFalse(am.read_si_variable("cap_fm_power_on"))

    def test_df_breaker_pulled_cuts_becker_but_not_bus_check(self):
        with AirManager() as am:
            am.load_instrument("becker-sar-df-517")
            am.set_avionics_power(True, 28.0)
            self.assertEqual(am.read_dataref("cap/df/power"), 1)

            am.write_si_variable("cap_mission_cb_df_in", False)
            self.assertEqual(am.read_dataref("cap/df/power"), 0)

            am.write_si_variable("cap_mission_cb_df_in", True)
            self.assertEqual(am.read_dataref("cap/df/power"), 1)

    def test_mission_gating_never_overrides_a_dead_bus(self):
        with AirManager() as am:
            am.load_instrument("becker-sar-df-517")
            am.set_avionics_power(False, 0.0)
            am.write_si_variable("cap_mission_master_on", True)
            am.write_si_variable("cap_mission_cb_df_in", True)
            self.assertEqual(am.read_dataref("cap/df/power"), 0,
                              "mission gating must never power a system the aircraft bus itself has not")

    def test_audio_panel_breaker_pull_forces_power_down(self):
        with AirManager() as am:
            am.load_instrument("mo-audio-panel-gma1347")
            am.set_avionics_power(True, 28.0)
            # Simulate a prior COM3 audio selection the crew had made.
            am.write_si_variable("cap_fm_audio_selected", True)

            am.write_si_variable("cap_mission_cb_audio_in", False)

            # Losing power clears the selection, same as any other power-down.
            self.assertFalse(am.read_si_variable("cap_fm_audio_selected"))


if __name__ == "__main__":
    unittest.main()
