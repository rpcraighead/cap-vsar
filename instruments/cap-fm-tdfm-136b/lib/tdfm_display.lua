-- tdfm_display.lua — the TDFM-136B's two-line by 24-character LED display.
--
-- Per the Technisonic Operating Instructions (08RE399A) §1.1.1, the unit has a
-- "two line by 24 character LED display (top = Main, bottom = Guard)". The
-- character cells use the same smooth built-in font as the DF heads. No extra
-- instrument font resource is required.
--
-- Line layout (§1.1.2), 24 columns, 1-indexed:
--
--   cols 1-3   memory number (Main: 001-230; Guard: GD1 / GD2)
--   col  4     Main: scan indicator      Guard: command level / keypad lock
--   cols 5-12  eight-character memory description
--   col  13    operating mode: w (25 kHz), n (12.5 kHz), D (P25 digital)
--   cols 14-21 frequency in use
--   col  22    R or T
--   col  23    squelch mode: analog x/t/c, digital m/n/g
--   col  24    spare

tdfm_display = {}
local M = tdfm_display

M.COLS  = 24
M.LINES = 2

-- The real display is amber-red LED on black rather than an LCD panel.
M.COLOUR_ON  = "#ff9a2e"
M.COLOUR_DIM = "#3a2409"
M.COLOUR_OFF = "#0a0806"

--- Compose one 24-character line from a channel table.
-- @param ch     channel state
-- @param is_main true for the Main row, false for Guard
-- @param extra  character for column 4 (scan indicator or command level)
function M.compose(ch, is_main, extra)
    local number = is_main
        and string.format("%03d", ch.memory or 0)
        or  string.format("GD%d", ch.guard or 1)

    local name = (ch.name or ""):upper()
    name = (name .. string.rep(" ", 8)):sub(1, 8)

    -- §1.1.2(9): eight characters of frequency, e.g. "136.0000"
    local freq = string.format("%8.4f", (ch.freq_hz or 0) / 1e6)

    return string.format("%-3s%1s%-8s%1s%8s%1s%1s",
        number,
        extra or " ",
        name,
        ch.mode or "n",
        freq,
        ch.transmitting and "T" or "R",
        ch.squelch_mode or "x")
end

-- Keep this literal so the file is safe when Air Manager executes libraries in
-- random order. It is lcd.CHAR_H (5) plus four blank dot rows.
M.LINE_PITCH = 9                    -- logical units between row origins

--- Width and height of the character matrix, in LCD dots. lib/tdfm_panel.lua's
--- DISP_W / DISP_H are these times DISP_SCALE, and the artwork script checks it.
function M.extent()
    return M.COLS * lcd.CHAR_STEP - 1,
           (M.LINES - 1) * M.LINE_PITCH + lcd.CHAR_H
end

--- Draw both display lines. The canvas is exactly the character matrix, so the
--- origin is (0,0) and the unlit wash fills it.
-- @param ctx    lcd context
-- @param lines  array of two composed strings
-- @param on     whether the display is powered
function M.draw(ctx, lines, on)
    -- The faceplate supplies the black display well. Keeping that background
    -- out of this canvas is also required by Air Manager 4.2: each _fill()
    -- applies to every path queued in the callback, so a later amber glyph fill
    -- would recolour a background rectangle and turn the whole display amber.
    if not on then return end

    for i = 1, M.LINES do
        lcd.text(ctx, 0, (i - 1) * M.LINE_PITCH, lines[i] or "", M.COLOUR_ON)
    end
end

return M
