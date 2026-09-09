-- gma_panel.lua — the GMA 1347 chassis: geometry, artwork wiring, key table.
--
-- Layout follows the Garmin G1000 Audio Panel Pilot's Guide 190-00378-01 Rev. A,
-- Figure 6A.2.1 (PDF page 5 of docs/GMA1347_C182T_CAP_audio_panel.pdf, rendered
-- to docs/figures/gma1347_panel-05.png). §6A.2 gives the dimensions outright:
--
--   "The GMA 1347 front panel measures 7.79 inches in depth, 1.3 inches in
--    width and 7.70 inches in height."
--
-- So the face is 1.3 : 7.70, an aspect of 1 : 5.923 — a tall narrow strip, not
-- the squat panel the first draft drew. The measured figure agrees at 1 : 5.87.
--
-- Two further details from the same page that the first draft had wrong:
--
--   * "The triangular key annunciator lights are WHITE when illuminated and
--     point to the corresponding keys." They are not green.
--   * "The dual knob located at the bottom of the unit controls volume as well
--     as squelch threshold levels. The small knob adjusts the volume/squelch
--     level associated with the pilot channel, while the large knob adjusts the
--     volume/squelch level associated with the copilot/passenger channels."
--     It is a concentric pair, not a single knob.
--
-- ARTWORK
-- The housing, group outlines and every silk-screened legend are baked into
-- resources/faceplate.png. Each key is its own image pair because the cap
-- carries its legend and moves when pressed, and the annunciator triangle above
-- each key is a separate lit/unlit image so it can be switched at run time.
-- Regenerate with:
--
--     python3 scripts/make_panel_artwork.py
--
-- That script PARSES THE GEOMETRY BLOCK BELOW rather than repeating it.

gma_panel = {}
local M = gma_panel

-- ===================== GEOMETRY (parsed by make_panel_artwork.py) =====================

M.FACE_W = 240
M.FACE_H = 1422                 -- 240 * 7.70 / 1.3, per §6A.2

M.KEY_W, M.KEY_H = 92, 54
M.COL_X = { 18, 130 }           -- left and right key columns
M.ROW_Y = {                     -- key centres, measured off Figure 6A.2.1
    92, 185, 277, 370, 462, 555, 647, 740, 832, 925, 1021,
}

-- Annunciator triangle above each key: white when lit, per §6A.2.
M.ANN_W, M.ANN_H = 16, 9
M.ANN_DY = 15                   -- centre-to-centre above the key top edge

-- The two outlines Figure 6A.2.1 prints on the plate.
M.GROUP_TX  = { x = 7, y = 47,  w = 226, h = 366 }   -- transmitters / transceivers
M.GROUP_ICS = { x = 7, y = 978, w = 226, h = 118 }   -- ICS isolation

-- Concentric volume / squelch knob. Outer is copilot & passenger, inner pilot.
M.KNOB_OUTER = { x = 77, y = 1173, w = 86, h = 86 }
M.KNOB_INNER = { x = 97, y = 1193, w = 46, h = 46 }
M.MODE_VOL   = { x = 10,  y = 1264, w = 68, h = 26 }
M.MODE_SQ    = { x = 162, y = 1264, w = 68, h = 26 }

M.BACKUP = { x = 87, y = 1304, w = 66, h = 66 }      -- red reversionary button

M.PHOTOCELL = { 176, 832 }      -- the small sensor where a right-column key would be
M.PHOTOCELL_R = 6
M.CORNER = 40                   -- the plate's generously rounded ends
-- =================== END GEOMETRY (parsed by make_panel_artwork.py) ===================

-- id, column (1 left / 2 right), row, legend lines.
-- Order matches Figure 6A.2.1 top to bottom. Row 9 has no right-hand key; the
-- photocell sits there instead.
M.KEYS = {
    { id = "com1_mic", col = 1, row = 1,  text = { "COM1", "MIC" } },
    { id = "com1",     col = 2, row = 1,  text = { "COM1" } },
    { id = "com2_mic", col = 1, row = 2,  text = { "COM2", "MIC" } },
    { id = "com2",     col = 2, row = 2,  text = { "COM2" } },
    { id = "com3_mic", col = 1, row = 3,  text = { "COM3", "MIC" } },
    { id = "com3",     col = 2, row = 3,  text = { "COM3" } },
    { id = "split",    col = 1, row = 4,  text = { "COM", "1/2" } },
    { id = "tel",      col = 2, row = 4,  text = { "TEL" } },
    { id = "pa",       col = 1, row = 5,  text = { "PA" } },
    { id = "spkr",     col = 2, row = 5,  text = { "SPKR" } },
    { id = "mkr",      col = 1, row = 6,  text = { "MKR", "MUTE" } },
    { id = "hi_sens",  col = 2, row = 6,  text = { "HI", "SENS" } },
    { id = "dme",      col = 1, row = 7,  text = { "DME" } },
    { id = "nav1",     col = 2, row = 7,  text = { "NAV1" } },
    { id = "adf",      col = 1, row = 8,  text = { "ADF" } },
    { id = "nav2",     col = 2, row = 8,  text = { "NAV2" } },
    { id = "aux",      col = 1, row = 9,  text = { "AUX" } },
    { id = "man_sq",   col = 1, row = 10, text = { "MAN", "SQ" } },
    { id = "play",     col = 2, row = 10, text = { "PLAY" } },
    { id = "pilot",    col = 1, row = 11, text = { "PILOT" } },
    { id = "coplt",    col = 2, row = 11, text = { "COPLT" } },
}

--- Hit region of one key.
function M.key_rect(k)
    return M.COL_X[k.col], M.ROW_Y[k.row] - M.KEY_H / 2, M.KEY_W, M.KEY_H
end

--- Hit region of the annunciator triangle above one key.
function M.ann_rect(k)
    local x, y = M.key_rect(k)
    return x + (M.KEY_W - M.ANN_W) / 2, y - M.ANN_DY, M.ANN_W, M.ANN_H
end

function M.key_image(k, pressed)
    return "key_" .. k.id .. (pressed and "_pressed" or "") .. ".png"
end

--- Lay the static housing in.
function M.add_faceplate()
    img_add("faceplate.png", 0, 0, M.FACE_W, M.FACE_H)
end

return M
