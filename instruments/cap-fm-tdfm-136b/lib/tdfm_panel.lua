-- tdfm_panel.lua — the TDFM-136B chassis: geometry, artwork wiring, controls.
--
-- Layout follows Technisonic Operating Instructions 08RE399A Figure 1-1 (PDF
-- page 11 of docs/TDFM136B_operating.pdf, rendered to
-- docs/figures/tdfm_p11_front_panel-11.png). The plate measured off that figure
-- is 1044 x 545 px, an aspect of 1.916, which is what the face below uses.
--
--   [Technisonic]                                       TDFM-136B  (P25)
--   ┌──────────────────────────────────────────────────┐
--   │ o 001 Control   w136.0000Rx                      │
--   │ o GD1 Forestry  n156.5000Rt                      │   1 2 3 #
--   └──────────────────────────────────────────────────┘   4 5 6 0
--      (MAIN)  (GUARD)  (PGM)                              7 8 9 *
--       MN|GD   G1|G2    HI|LO
--
-- ARTWORK
-- The housing, screws, display recess and every silk-screened legend are baked
-- into resources/faceplate.png; the encoders, toggles, LEDs and the twelve
-- keypad keys are separate images layered on top. Each key carries its own
-- legend because the key cap moves when pressed. Regenerate with:
--
--     python3 scripts/make_panel_artwork.py
--
-- That script PARSES THE GEOMETRY BLOCK BELOW rather than repeating it, so the
-- artwork cannot drift out of alignment with the control hit regions.

tdfm_panel = {}
local M = tdfm_panel

-- ===================== GEOMETRY (parsed by make_panel_artwork.py) =====================
-- Instrument units. Percentages in the comments are of the plate width or
-- height as measured on Figure 1-1.

M.FACE_W = 800
M.FACE_H = 420                  -- 800 / 1.916, the figure's aspect

-- Two lines of 24 characters. Integer scale keeps the LED cells even.
M.DISP_SCALE = 6
M.DISP_X = 128                  -- text origin; 24 chars span 128..698
M.DISP_Y = 65
M.DISP_W = 570                  -- (24 * lcd.CHAR_STEP - 1) * DISP_SCALE
M.DISP_H = 84                   -- two lines at a 9-dot pitch

-- The window is the black recess the LED matrix sits in. It runs wider than the
-- text on the left so the two squelch LEDs sit inside the bezel, one per line,
-- exactly as Figure 1-1 shows.
M.WINDOW = { x = 72, y = 36, w = 648, h = 126 }

M.LED_R = 10
M.LEDS = { { 100, 80 }, { 100, 134 } }      -- Main on line 1, Guard on line 2

-- Rotary encoders and the keyloader data port, in a row under the display.
M.MAIN_ENC  = { x = 80,  y = 202, w = 76, h = 76 }
M.GUARD_ENC = { x = 188, y = 202, w = 76, h = 76 }
M.PGM       = { x = 303, y = 211, w = 58, h = 58 }

-- Three toggles beneath the encoders. Figure 1-1 labels them above and below
-- the lever — MN over GD, G1 over G2, HI over LO — not with a combined caption.
M.TOGGLE = {
    mn_gd = { x = 105, y = 339, w = 26, h = 54, up = "MN", down = "GD" },
    g1_g2 = { x = 213, y = 339, w = 26, h = 54, up = "G1", down = "G2" },
    hi_lo = { x = 319, y = 339, w = 26, h = 54, up = "HI", down = "LO" },
}

-- Twelve keys, four columns by three rows.
M.KEY_W, M.KEY_H = 72, 58
M.KEY_X0, M.KEY_Y0 = 400, 202   -- top-left key origin
M.KEY_PITCH_X, M.KEY_PITCH_Y = 80, 67
M.KEY_COLS = 4

-- Four slotted corner screws and two small cross screws at mid-height.
M.SCREWS   = { { 30, 80 }, { 770, 80 }, { 30, 336 }, { 770, 336 } }
M.SCREW_R  = 17
M.SCREWS_SMALL = { { 30, 214 }, { 770, 214 } }
M.SCREW_SMALL_R = 9
M.CORNER = 10                   -- plate corner radius
-- =================== END GEOMETRY (parsed by make_panel_artwork.py) ===================

-- §1.1.1(9) / Figure 1-1: the digit is the primary legend and the Level-1
-- function sits under it. Keys 2, 4, 6 and 8 show their digit inside a cursor
-- arrow instead of carrying a word.
M.KEYPAD = {
    { id = "1", digit = "1", fn = "CHAN"  },
    { id = "2", digit = "2", arrow = "up"    },
    { id = "3", digit = "3", fn = "MODE"  },
    { id = "#", digit = "#", fn = "ENTER" },
    { id = "4", digit = "4", arrow = "left"  },
    { id = "5", digit = "5", fn = "SCAN"  },
    { id = "6", digit = "6", arrow = "right" },
    { id = "0", digit = "0", fn = "PROG"  },
    { id = "7", digit = "7", fn = "FREQ"  },
    { id = "8", digit = "8", arrow = "down"  },
    { id = "9", digit = "9", fn = "SQL"   },
    { id = "*", digit = "*", fn = "ESC"   },
}

--- Hit region of keypad key i, 1-based, reading left to right and top to bottom.
function M.key_rect(i)
    local col = (i - 1) % M.KEY_COLS
    local row = math.floor((i - 1) / M.KEY_COLS)
    return M.KEY_X0 + col * M.KEY_PITCH_X,
           M.KEY_Y0 + row * M.KEY_PITCH_Y,
           M.KEY_W, M.KEY_H
end

--- Resource name for a key. Each cap carries its own printed legend.
function M.key_image(entry, pressed)
    local safe = entry.id
    if safe == "#" then safe = "hash" elseif safe == "*" then safe = "star" end
    return "key_" .. safe .. (pressed and "_pressed" or "") .. ".png"
end

--- Lay the static housing in.
function M.add_faceplate()
    img_add("faceplate.png", 0, 0, M.FACE_W, M.FACE_H)
end

return M
