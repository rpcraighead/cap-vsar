"""Exercise real Lua text calls; check glyph fit using the shipped preview font.

These are off-simulator regressions, not an Air Manager/OpenGL screenshot test.
Run: python3 tests/test_lcd_text.py
"""
import ctypes
import ctypes.util
import json
from pathlib import Path
import re
import unittest

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / 'scripts/fonts/inconsolata_bold.ttf'
HEADS = ('becker-sar-df-517', 'rhotheta-rt-600', 'cap-fm-tdfm-136b')


def draw_calls(head, code):
    lua = ctypes.CDLL(ctypes.util.find_library('lua5.4'))
    state = ctypes.c_void_p
    lua.luaL_newstate.restype = state
    lua.luaL_openlibs.argtypes = [state]
    lua.luaL_loadstring.argtypes = [state, ctypes.c_char_p]
    lua.lua_pcallk.argtypes = [state, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              ctypes.c_ssize_t, ctypes.c_void_p]
    lua.lua_tolstring.argtypes = [state, ctypes.c_int, ctypes.c_void_p]
    lua.lua_tolstring.restype = ctypes.c_char_p
    lua.lua_close.argtypes = [state]
    lib = ROOT / 'instruments' / head / 'lib/lcd.lua'
    src = '''
local calls = {}
function _txt(ch, style, x, y)
    calls[#calls + 1] = string.format("%s\\t%s\\t%.6f\\t%.6f", ch, style, x, y)
end
''' + 'dofile(' + json.dumps(str(lib)) + ')\n' + code + '\nreturn table.concat(calls, "\\n")'
    st = lua.luaL_newstate()
    try:
        lua.luaL_openlibs(st)
        rc = lua.luaL_loadstring(st, src.encode())
        if not rc:
            rc = lua.lua_pcallk(st, 0, 1, 0, 0, None)
        result = lua.lua_tolstring(st, -1, None).decode()
        if rc:
            raise AssertionError(result)
        return [(c, style, float(x), float(y)) for c, style, x, y in
                (row.split('\t') for row in result.splitlines())]
    finally:
        lua.lua_close(st)


def ink_bounds(calls):
    # Render into a padded area so a clipped first/last glyph cannot hide.
    k, pad = 4, 100
    img = Image.new('L', (3000, 1000), 0)
    d = ImageDraw.Draw(img)
    for ch, style, x, y in calls:
        size = float(re.search(r'size:([\d.]+)', style)[1])
        f = ImageFont.truetype(str(FONT), round(size*k))
        d.text((x*k+pad, y*k+pad), ch, font=f, fill=255, anchor='ma')
    box = img.getbbox()
    return tuple((v-pad)/k for v in box) if box else None


class DisplayTextTests(unittest.TestCase):
    def test_padded_fields_preserve_case_and_columns(self):
        for head in HEADS:
            calls = draw_calls(head, 'lcd.text(lcd.context(6), 0, 0, "A w n D g")')
            self.assertEqual(''.join(c[0] for c in calls), 'AwnDg')
            # All four spaces occupy their columns even though they carry no ink.
            self.assertEqual([c[2]-calls[0][2] for c in calls], [0, 48, 96, 144, 192])

    def test_tdfm_last_column_and_descenders_fit_both_rows(self):
        code = '''
local ctx = lcd.context(6)
lcd.text(ctx, 0, 0, "MMMMMMMMMMMMMMMMMMMMMMMM")
lcd.text(ctx, 0, 9, "gggggggggggggggggggggggg")
'''
        calls = draw_calls(HEADS[2], code)
        self.assertEqual(len(calls), 48)
        x0, y0, x1, y1 = ink_bounds(calls)
        self.assertGreaterEqual(x0, 0)
        self.assertGreaterEqual(y0, 0)
        self.assertLessEqual(x1, 570)
        self.assertLessEqual(y1, 84)

    def test_df_right_alignment_and_scaled_readouts_fit(self):
        for head in HEADS[:2]:
            for m in (1, 2, 3):
                code = f'lcd.text_right(lcd.context(3), 127, 64-5*{m}, "121.500", nil, {m})'
                x0, y0, x1, y1 = ink_bounds(draw_calls(head, code))
                self.assertGreaterEqual(x0, 0)
                self.assertGreaterEqual(y0, 0)
                self.assertLessEqual(x1, 384)
                self.assertLessEqual(y1, 192)

    def test_inverse_text_keeps_colour_and_clearance(self):
        calls = draw_calls(HEADS[0], 'lcd.text(lcd.context(3), 1, 1, "SCAN", "#c6d96b")')
        self.assertTrue(all('color:#c6d96b;' in c[1] for c in calls))
        x0, y0, x1, y1 = ink_bounds(calls)
        # The DCU reverse-video cell is 18x7 logical units; text has a 1-unit inset.
        self.assertGreater(x0, 0)
        self.assertGreater(y0, 0)
        self.assertLess(x1, 18*3)
        self.assertLessEqual(y1, 7*3)

    def test_power_off_tdfm_emits_no_text(self):
        lib = ROOT / 'instruments/cap-fm-tdfm-136b/lib/tdfm_display.lua'
        code = 'dofile(' + json.dumps(str(lib)) + ')\n'
        code += 'tdfm_display.draw(lcd.context(6), {"MAIN", "GUARD"}, false)'
        self.assertEqual(draw_calls(HEADS[2], code), [])


if __name__ == '__main__':
    unittest.main()
