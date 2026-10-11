"""The Air Manager harness must refuse what Air Manager refuses (D3).

These test the harness itself: the signature table, the X-Plane name allowlist,
multi-dataref subscriptions, hit testing and the sound restart counter. They
use no instrument, so a failure here is a harness regression, not an
instrument one.
"""
import unittest

from tests import am_api
from tests.am import AirManager


def lua_error(am, code):
    """Run Lua that is expected to raise; return the message."""
    try:
        am.eval(code)
    except RuntimeError as exc:
        return str(exc)
    raise AssertionError(f"expected a Lua error from: {code}")


class SignatureTable(unittest.TestCase):
    def test_dial_add_has_one_callback(self):
        """dial_add(img, x, y, w, h, [step], turn_cb): press/release are not an AM feature."""
        with AirManager() as am:
            am.eval('dial_add("k.png", 0, 0, 10, 10, function(d) end)')
            am.eval('dial_add("k.png", 0, 0, 10, 10, 20, function(d) end)')
            msg = lua_error(am, 'dial_add("k.png", 0, 0, 10, 10, 20, function() end, function() end)')
            self.assertIn("dial_add", msg)
            self.assertIn("too many arguments", msg)
            msg = lua_error(am, 'dial_add("k.png", 0, 0, 10, 10, 20, function() end, function() end, function() end)')
            self.assertIn("too many arguments", msg)

    def test_button_add_signature(self):
        with AirManager() as am:
            am.eval("button_add(nil, nil, 0, 0, 5, 5, function() end)")
            am.eval('button_add("a.png", "b.png", 0, 0, 5, 5, function() end, function() end)')
            self.assertIn("bad argument #7", lua_error(am, "button_add(nil, nil, 0, 0, 5, 5, 'x')"))
            self.assertIn("not enough arguments", lua_error(am, "button_add(nil, nil, 0, 0, 5, 5)"))
            self.assertIn("too many arguments", lua_error(
                am, "button_add(nil, nil, 0, 0, 5, 5, function() end, function() end, 1)"))

    def test_wrong_type_is_an_error(self):
        with AirManager() as am:
            self.assertIn("bad argument #1", lua_error(am, "img_add(12, 0, 0, 1, 1)"))
            self.assertIn("bad argument #3", lua_error(am, 'txt_add("t", "s", "x", 0, 1, 1)'))

    def test_unlisted_function_is_undefined(self):
        with AirManager() as am:
            self.assertIn("nil value", lua_error(am, "group_add(1, 2)"))
            self.assertIn("nil value", lua_error(am, "xpl_command_subscribe('x', function() end)"))

    def test_sandbox_has_no_require(self):
        with AirManager() as am:
            self.assertIn("nil value", lua_error(am, 'require("cap_df")'))
            self.assertIn("nil value", lua_error(am, 'io.open("/etc/passwd")'))

    def test_every_listed_function_has_a_stub_and_vice_versa(self):
        with AirManager() as am:
            for name in am_api.SIGNATURES:
                self.assertEqual(am.eval(f"return type({name})"), "function", name)

    def test_css_rgba_is_not_an_air_manager_colour(self):
        """I2-8: _fill takes a name, #RGB, #RRGGBB or #RRGGBBAA."""
        with AirManager() as am:
            for ok in ('"red"', '"#fff"', '"#1c1f26"', '"#0A0A0ABF"'):
                am.eval(f"_fill({ok})")
            for bad in ('"rgba(10, 10, 10, 0.75)"', '"#12345"', "123", "nil"):
                self.assertIn("_fill", lua_error(am, f"_fill({bad})"))


class NameAllowlist(unittest.TestCase):
    def test_unknown_dataref_is_refused_on_subscribe_and_write(self):
        with AirManager() as am:
            for call in (
                'xpl_dataref_subscribe("sim/cockpit2/radios/indicators/com1_receiving", "INT", function(v) end)',
                'xpl_dataref_write("sim/does/not/exist", "INT", 1)',
            ):
                self.assertIn("allowlist", lua_error(am, call))

    def test_unknown_command_is_refused(self):
        with AirManager() as am:
            self.assertIn("allowlist", lua_error(am, 'xpl_command("sim/audio_panel_copilot/ptt")'))
            am.eval('xpl_command("sim/GPS/G1000_display_reversion")')
            self.assertEqual(am.command_names(), ["sim/GPS/G1000_display_reversion"])

    def test_type_must_match_x_plane(self):
        with AirManager() as am:
            msg = lua_error(am, 'xpl_dataref_subscribe("sim/atc/com1_rx", "FLOAT", function(v) end)')
            self.assertIn("is INT in X-Plane", msg)

    def test_read_only_dataref_cannot_be_written_by_an_instrument(self):
        with AirManager() as am:
            self.assertIn("read-only", lua_error(am, 'xpl_dataref_write("sim/atc/com1_rx", "INT", 1)'))
            # ...but the simulator can publish it.
            am.write_dataref("sim/atc/com1_rx", "INT", 1)
            self.assertEqual(am.read_dataref("sim/atc/com1_rx"), 1)

    def test_sim_side_write_is_validated_too(self):
        with AirManager() as am:
            with self.assertRaises(RuntimeError):
                am.write_dataref("sim/atc/com1_receiving", "INT", 1)
            with self.assertRaises(RuntimeError):
                am.write_dataref("sim/atc/com1_rx", "FLOAT", 1.0)

    def test_cap_df_names_come_from_the_plugin(self):
        names = am_api.scrape_df_names()
        self.assertEqual(names["cap/df/signal"], {"type": "FLOAT", "writable": False})
        self.assertEqual(names["cap/df/power"], {"type": "INT", "writable": True})
        self.assertEqual(names["cap/df/clear_average"], {"type": "INT", "writable": True})
        self.assertEqual(names["cap/df/cs_hex15"]["type"], "BYTE[15]")
        with AirManager() as am:
            am.eval('xpl_dataref_write("cap/df/squelch", "FLOAT", 25.0)')
            self.assertIn("read-only", lua_error(am, 'xpl_dataref_write("cap/df/signal", "FLOAT", 1.0)'))
            self.assertIn("allowlist", lua_error(am, 'xpl_dataref_write("cap/df/not_a_thing", "INT", 1)'))


class MultiDatarefSubscription(unittest.TestCase):
    def test_callback_gets_every_value_when_any_changes(self):
        with AirManager() as am:
            am.eval("""
                seen = {}
                xpl_dataref_subscribe(
                    "cap/df/valid", "INT",
                    "cap/df/bearing_rel", "FLOAT",
                    "cap/df/band", "FLOAT",
                    function(a, b, c) seen[#seen + 1] = { a, b, c } end)
            """)
            self.assertEqual(am.eval("return #seen"), 0, "no callback before a value arrives")
            am.write_dataref("cap/df/bearing_rel", "FLOAT", 47.0)
            self.assertEqual(am.eval("return seen[#seen][1]"), 0)
            self.assertEqual(am.eval("return seen[#seen][2]"), 47.0)
            am.write_dataref("cap/df/valid", "INT", 1)
            self.assertEqual(am.eval("return seen[#seen][1]"), 1)
            self.assertEqual(am.eval("return seen[#seen][2]"), 47.0, "earlier value is kept")
            self.assertEqual(am.eval("return #seen"), 2)

    def test_one_frame_calls_the_group_once(self):
        with AirManager() as am:
            am.eval("""
                calls = 0
                xpl_dataref_subscribe("cap/df/valid", "INT", "cap/df/band", "FLOAT",
                                      function() calls = calls + 1 end)
            """)
            am.write_datarefs([("cap/df/valid", "INT", 1), ("cap/df/band", "FLOAT", 406.0)])
            self.assertEqual(am.eval("return calls"), 1)

    def test_subscribe_needs_pairs_then_callback(self):
        with AirManager() as am:
            self.assertIn("callback", lua_error(am, 'xpl_dataref_subscribe("cap/df/valid", "INT")'))
            self.assertIn("pairs", lua_error(
                am, 'xpl_dataref_subscribe("cap/df/valid", "INT", "cap/df/band", function() end)'))

    def test_cap_df_gating_is_exercised_through_the_datarefs(self):
        """The 8-argument cap_df callback is driven end to end, I-1 redraw gating included."""
        with AirManager() as am:
            am.load_instrument("becker-sar-df-517")
            am.eval("redraws = 0; cap_df.on_change(function() redraws = redraws + 1 end)")
            am.publish_df(valid=1, bearing_rel=47.0, signal=0.8)
            first = am.eval("return redraws")
            self.assertGreater(first, 0)
            self.assertEqual(am.eval("return cap_df.state.bearing"), 47.0)
            self.assertAlmostEqual(am.eval("return cap_df.state.signal"), 80.0)
            # The identical frame again is not a change: no redraw.
            am.publish_df()
            self.assertEqual(am.eval("return redraws"), first)


class HitTesting(unittest.TestCase):
    def test_topmost_button_wins_and_dial_is_not_hidden_by_it(self):
        with AirManager() as am:
            am.eval("""
                turned = 0; pushed = 0
                d = dial_add("k.png", 0, 0, 100, 100, function(dir) turned = turned + dir end)
                b = button_add(nil, nil, 30, 30, 40, 40, function() pushed = pushed + 1 end)
            """)
            self.assertEqual(am.button_at(50, 50), am.eval("return b"))
            self.assertIsNone(am.button_at(5, 5))
            am.press_at(50, 50)
            self.assertEqual(am.eval("return pushed"), 1)
            am.turn_at(50, 50, 1)
            am.turn_at(5, 5, 1)
            self.assertEqual(am.eval("return turned"), 2)
            with self.assertRaises(ValueError):
                am.press_at(5, 5)

    def test_hidden_button_is_not_hit(self):
        with AirManager() as am:
            am.eval("b = button_add(nil, nil, 0, 0, 10, 10, function() end); visible(b, false)")
            self.assertIsNone(am.button_at(5, 5))


class SoundRestarts(unittest.TestCase):
    def test_looping_a_looping_sound_counts_as_a_restart(self):
        with AirManager() as am:
            am.eval('s = sound_add("n.wav", 0); sound_loop(s)')
            self.assertEqual(am.sounds()["n.wav"]["restarts"], 0)
            am.eval("sound_loop(s)")
            self.assertEqual(am.sounds()["n.wav"]["restarts"], 1)
            am.eval("sound_stop(s); sound_loop(s)")
            self.assertEqual(am.sounds()["n.wav"]["restarts"], 1)


class TimerSignature(unittest.TestCase):
    def test_nil_delay_and_two_argument_forms(self):
        """The stock G1000 uses timer_start(nil, 2500, cb) and timer_start(2000, cb)."""
        with AirManager() as am:
            am.eval("""
                n = 0
                timer_start(nil, 100, function() n = n + 1 end)
                timer_start(200, function() n = n + 10 end)
            """)
            am.step_time(200)
            self.assertEqual(am.eval("return n"), 13)   # 0, 100 and 200 ms, plus the one-shot


if __name__ == "__main__":
    unittest.main()
