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


class TestReloadAndProducerPresentPath(unittest.TestCase):
    """I2-7: the producers publish once at load, and the consumers are tested
    with the producers actually loaded into the same Air Manager state."""

    def test_master_switch_reload_republishes_its_drawn_state(self):
        with AirManager() as am:
            # A previous session left the variable OFF; AM keeps variables
            # across an instrument reload, and the reloaded switch draws ON.
            am.write_si_variable("cap_mission_master_on", False)
            am.load_instrument("cap-mission-master-switch")
            self.assertTrue(am.read_si_variable("cap_mission_master_on"))

    def test_cb_panel_reload_republishes_its_drawn_state(self):
        with AirManager() as am:
            am.write_si_variable("cap_mission_cb_fm_in", False)
            am.write_si_variable("cap_mission_cb_df_in", False)
            am.load_instrument("cap-mission-cb-panel")
            for var in ("cap_mission_cb_df_in", "cap_mission_cb_fm_in", "cap_mission_cb_audio_in"):
                self.assertTrue(am.read_si_variable(var), var)

    def test_stale_off_does_not_keep_a_reloaded_consumer_dark(self):
        """A consumer that subscribed to the stale OFF would stay unpowered until
        someone worked the switch; the producer's load-time publish fixes that."""
        with AirManager() as am:
            am.write_si_variable("cap_mission_cb_fm_in", False)
            am.load_instrument("cap-fm-tdfm-136b")
            am.set_avionics_power(True, 28.0)
            self.assertFalse(am.read_si_variable("cap_fm_power_on"))
            am.load_instrument("cap-mission-cb-panel")
            self.assertTrue(am.read_si_variable("cap_fm_power_on"))

    def _all_loaded(self, consumer_first):
        am = AirManager()
        order = ["cap-fm-tdfm-136b", "cap-mission-master-switch", "cap-mission-cb-panel"]
        if not consumer_first:
            order = order[1:] + order[:1]
        for name in order:
            am.load_instrument(name)
        am.set_avionics_power(True, 28.0)
        return am

    def test_master_switch_cuts_and_restores_a_loaded_tdfm(self):
        for consumer_first in (True, False):
            with self.subTest(consumer_first=consumer_first):
                am = self._all_loaded(consumer_first)
                try:
                    self.assertTrue(am.read_si_variable("cap_fm_power_on"))
                    am.click_at(110 + 5, 40 + 5)                  # lift the guard
                    am.click_at(110 + 40, 74 + 28)                # switch OFF
                    self.assertFalse(am.read_si_variable("cap_mission_master_on"))
                    self.assertFalse(am.read_si_variable("cap_fm_power_on"))
                    am.click_at(110 + 40, 74 + 28)                # switch ON
                    self.assertTrue(am.read_si_variable("cap_fm_power_on"))
                finally:
                    am.close()

    def test_pulling_the_fm_breaker_cuts_a_loaded_tdfm_only(self):
        for consumer_first in (True, False):
            with self.subTest(consumer_first=consumer_first):
                am = self._all_loaded(consumer_first)
                try:
                    x, y = TestMissionCBPanel.BREAKER_BUTTONS["fm"]
                    am.click_at(x + 10, y + 10)
                    self.assertFalse(am.read_si_variable("cap_mission_cb_fm_in"))
                    self.assertFalse(am.read_si_variable("cap_fm_power_on"))
                    am.click_at(x + 10, y + 10)
                    self.assertTrue(am.read_si_variable("cap_fm_power_on"))
                finally:
                    am.close()


class TestCapPowerGate(unittest.TestCase):
    """lib/cap_power.lua: the one bus-power gate the four powered instruments share."""

    def _gate(self, am):
        from tests.am import ROOT
        am.eval((ROOT / "instruments/_shared/lib/cap_power.lua").read_text())
        am.eval("""
            calls = {}
            gate = cap_power.watch("cap_mission_cb_df_in", function(p) calls[#calls + 1] = p end)
        """)

    def test_and_of_four_conditions_reported_on_transitions_only(self):
        with AirManager() as am:
            self._gate(am)
            self.assertFalse(am.eval("return gate.powered()"))
            am.write_dataref("sim/cockpit2/switches/avionics_power_on", "INT", 1)
            am.write_dataref("sim/cockpit2/electrical/bus_volts", "FLOAT[6]", 9.9)
            self.assertEqual(am.eval("return #calls"), 0, "9.9 V is below the 10 V threshold")
            am.write_dataref("sim/cockpit2/electrical/bus_volts", "FLOAT[6]", 10.0)
            am.write_dataref("sim/cockpit2/electrical/bus_volts", "FLOAT[6]", 27.0)
            self.assertEqual(am.eval("return #calls"), 1)
            self.assertTrue(am.eval("return gate.powered()"))
            am.write_si_variable("cap_mission_master_on", True)
            self.assertEqual(am.eval("return #calls"), 1, "no change, no call")
            am.write_si_variable("cap_mission_cb_df_in", False)
            self.assertFalse(am.eval("return gate.powered()"))
            am.write_si_variable("cap_mission_cb_df_in", True)
            am.write_si_variable("cap_mission_master_on", False)
            self.assertFalse(am.eval("return gate.powered()"))
            self.assertEqual(am.eval("return #calls"), 4)

    def test_a_dead_bus_is_never_overridden_by_the_mission_conditions(self):
        with AirManager() as am:
            self._gate(am)
            am.write_si_variable("cap_mission_master_on", True)
            am.write_si_variable("cap_mission_cb_df_in", True)
            self.assertFalse(am.eval("return gate.powered()"))


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
