-- dcu.lua — the Display Control Unit chassis shared by both DF heads.
--
-- The Becker SAR-DF 517 and the RHOTHETA RT-600 are the *same physical control
-- head*. The bezel in both manuals carries both names — "SAR-DF 517" over
-- "RT-600.DCU" on the RHOTHETA unit, "Rhotheta / SAR-DF 517 / BECKER" on the
-- Becker one. Layout verified against:
--   517 manual   Fig 3-3 (PDF page 29) — Operating Elements in Bearing Mode
--   RT-600 manual Fig 2  (PDF page 8)  — RT-600.DCU Front Panel Layout
--   CAP RT-600 training deck, PDF page 8 — photographs of the unit in a panel
--
-- It is a square panel-mount instrument with clipped corners, not a wide
-- radio-stack strip:
--
--        (SQL)   [Clr] [Store] [Rep]   (Page)
--               ┌───────────────────┐
--               │   128 x 64 LCD    │
--               └───────────────────┘
--        (VOL)        [ON/OFF]        (FREQ)
--
-- Four large scalloped knobs at the corners, three small domed push-buttons
-- across the top centre, one ON/OFF push-button at the bottom centre, and the
-- display in the middle.
--
-- ARTWORK
-- The housing, screws, LCD recess and every silk-screened legend are baked into
-- resources/faceplate.png; the knobs and the two button states are separate
-- images layered on top. Physical legends therefore render as smooth printed
-- lettering; lcd.lua draws smooth text in the original logical display cells.
-- Regenerate every resource with:
--
--     python3 scripts/make_df_artwork.py
--
-- That script PARSES THE GEOMETRY BLOCK BELOW rather than repeating it, so the
-- artwork cannot drift out of alignment with the control hit regions. If you
-- move a control here, re-run the script; if the numbers stop being parseable
-- the script fails loudly instead of guessing.

dcu = {}
local M = dcu

-- ===================== GEOMETRY (parsed by make_df_artwork.py) =====================
-- Values are instrument units on a square face. Percentages in the comments are
-- of the face width, measured off 517 manual Fig 3-3.

M.FACE = 520                    -- square faceplate

M.LCD_SCALE = 3                 -- canvas units per LCD dot; integer keeps dots even
M.LCD_W = 384                   -- lcd.WIDTH  * LCD_SCALE
M.LCD_H = 192                   -- lcd.HEIGHT * LCD_SCALE
M.LCD_X = 68                    -- 13.1% .. 86.9%, manual measures 13.3% .. 86.7%
M.LCD_Y = 164

-- The lit glass is a little taller than the 2:1 dot area, as on the real module,
-- and sits inside a raised recess.
M.GLASS  = { x = 62,  y = 158, w = 396, h = 204 }
M.RECESS = { x = 50,  y = 146, w = 420, h = 228 }

-- Corner knobs, centres at 12.5% / 87.5%, diameter 19.2%.
M.KNOB = {
    sql  = { x = 15,  y = 15,  w = 100, h = 100 },
    page = { x = 405, y = 15,  w = 100, h = 100 },
    vol  = { x = 15,  y = 405, w = 100, h = 100 },
    freq = { x = 405, y = 405, w = 100, h = 100 },
}

-- Three domed push-buttons across the top centre, 86 units apart.
M.BTN = {
    clr   = { x = 148, y = 18, w = 52, h = 52 },
    store = { x = 234, y = 18, w = 52, h = 52 },
    rep   = { x = 320, y = 18, w = 52, h = 52 },
}

M.POWER = { x = 238, y = 456, w = 44, h = 44 }

M.SCREWS   = { { 24, 112 }, { 496, 112 }, { 24, 408 }, { 496, 408 } }
M.SCREW_R  = 11
M.INSET_R  = 250                -- the circular face inset the knobs sit on
M.CHAMFER  = 52                 -- clipped corner, 10% of the face
-- =================== END GEOMETRY (parsed by make_df_artwork.py) ===================

--- Lay the static housing in. Everything printed on the real bezel is in this
--- image; nothing here moves, so it is an image rather than a canvas.
function M.add_faceplate()
    img_add("faceplate.png", 0, 0, M.FACE, M.FACE)
end

--- Wire the four corner knobs and four buttons.
-- Callbacks are supplied by the faceplate; any may be nil. Added after the
-- faceplate image and the LCD canvas so the hit regions sit on top of both.
function M.add_controls(cb)
    local function dial(spec, fn)
        if fn then
            dial_add("knob.png", spec.x, spec.y, spec.w, spec.h, 20, fn)
        end
    end
    local function button(spec, up, down, press, release)
        if press then
            button_add(up, down, spec.x, spec.y, spec.w, spec.h, press, release)
        end
    end

    -- The ON/OFF button is a different moulding from the three domed keys and
    -- has its own artwork.
    button(M.POWER, "power.png", "power_pressed.png", cb.power)

    dial(M.KNOB.sql,  cb.sql)
    dial(M.KNOB.page, cb.page)
    dial(M.KNOB.vol,  cb.vol)
    dial(M.KNOB.freq, cb.freq)

    button(M.BTN.clr,   "button.png", "button_pressed.png", cb.clr_press,   cb.clr_release)
    button(M.BTN.store, "button.png", "button_pressed.png", cb.store_press, cb.store_release)
    button(M.BTN.rep,   "button.png", "button_pressed.png", cb.rep_press,   cb.rep_release)
end

-- ------------------------------------------------------------ display parts --

--- Rim marker. Solid for the averaged bearing the head is reporting, hollow for
--- an extreme of the un-averaged stream. Plotted dot by dot rather than stroked
--- as a circle so the shape is identical at any canvas scale and reads as a
--- deliberate 5x5 matrix symbol, which is what the panel actually shows.
local MARKER_RING = {
    { -1, -2 }, { 0, -2 }, { 1, -2 }, { 2, -1 }, { 2, 0 }, { 2, 1 },
    { 1, 2 }, { 0, 2 }, { -1, 2 }, { -2, 1 }, { -2, 0 }, { -2, -1 },
}

function M.marker(ctx, cx, cy, filled)
    for _, d in ipairs(MARKER_RING) do
        ctx:rect(cx + d[1], cy + d[2], 1, 1)
    end
    if filled then ctx:rect(cx - 1, cy - 1, 3, 3) end
end

--- Compass rose, drawn the way Fig 3-3 shows it.
--
-- An outer ring of dots carries the markers, a ring of graduations sits inside
-- it, "0" is at the top and "180" at the bottom, and the bearing is bracketed in
-- the middle at double height.
--
-- §3.3 is specific about what the markers mean: "the unaveraged maximal bearing
-- values (spread) are indicated and, if interpretable, the averaged bearing
-- value". So the solid marker is the averaged bearing and the two hollow ones
-- are the extremes of the un-averaged stream — exactly what cap/df/spread
-- measures. The operator reads the gap between the hollow markers to decide
-- whether to trust the solid one.
--
-- @param bearing  degrees relative, or nil for no fix
-- @param spread   degrees, or nil when the engine supplies no quality figure
-- @param opts     { brackets = bool, ticks = bool, big = bool }
function M.draw_rose(ctx, cx, cy, r, bearing, spread, opts)
    opts = opts or {}
    local brackets = opts.brackets ~= false
    local big      = opts.big ~= false
    local m        = big and 2 or 1

    -- Outer ring of dots: the real display draws it as dots, not a line.
    for deg = 0, 359, 6 do
        local x, y = lcd.polar(cx, cy, r, deg)
        ctx:rect(math.floor(x), math.floor(y), 1, 1)
    end

    -- Graduation ring, on the 517's large page-1 rose only. It is kept outside
    -- the bearing block: on the real screen the number is the thing you read and
    -- the graduations must not run through it.
    if opts.ticks and r >= 24 then
        for deg = 0, 359, 15 do
            local long = (deg % 45 == 0)
            local x1, y1 = lcd.polar(cx, cy, r - (long and 6 or 5), deg)
            local x2, y2 = lcd.polar(cx, cy, r - 3, deg)
            ctx:q_line(x1, y1, x2, y2)
        end
        ctx:stroke(nil, 1)
    end

    -- Cardinal ticks, standing slightly proud of the outer ring.
    for deg = 0, 359, 90 do
        local x1, y1 = lcd.polar(cx, cy, r - 2, deg)
        local x2, y2 = lcd.polar(cx, cy, r + 1, deg)
        ctx:q_line(x1, y1, x2, y2)
    end
    ctx:stroke(nil, 1)

    lcd.text(ctx, cx - 1, cy - r + 12, "0")
    lcd.text(ctx, cx - 5, cy + r - 13, "180")

    -- No usable bearing. opts.no_fix lets the caller say *why* — CONE or MASK —
    -- in the place the operator is already looking, instead of a bare "---".
    if not bearing then
        local why = opts.no_fix or "---"
        lcd.text(ctx, cx - lcd.text_width(why) * m / 2, cy - 2 * m, why, nil, m)
        return
    end

    -- Un-averaged extremes, as hollow markers on the rim.
    if spread and spread > 1 then
        for _, side in ipairs({ -1, 1 }) do
            local x, y = lcd.polar(cx, cy, r, bearing + side * spread / 2)
            M.marker(ctx, math.floor(x + 0.5), math.floor(y + 0.5), false)
        end
    end

    local s = string.format("%03d", math.floor(bearing + 0.5))
    if brackets then s = "<" .. s .. ">" end

    -- Pointer from the edge of the bearing block out to the rim. Fig 3-3 never
    -- runs the line across the digits, and neither do we: the start point is
    -- where the ray leaves the text box.
    local rad = math.rad(bearing)
    local ux, uy = math.sin(rad), -math.cos(rad)
    local hw = lcd.text_width(s) * m / 2 + 2
    local hh = lcd.CHAR_H * m / 2 + 2
    local t0 = r - 4
    if math.abs(ux) > 1e-6 then t0 = math.min(t0, hw / math.abs(ux)) end
    if math.abs(uy) > 1e-6 then t0 = math.min(t0, hh / math.abs(uy)) end
    ctx:line(cx + ux * t0, cy + uy * t0, cx + ux * (r - 3), cy + uy * (r - 3))

    local mx, my = lcd.polar(cx, cy, r, bearing)
    M.marker(ctx, math.floor(mx + 0.5), math.floor(my + 0.5), true)

    lcd.text(ctx, cx - lcd.text_width(s) * m / 2, cy - 2 * m, s, nil, m)
end

--- Vertical signal bar with its graduation ticks and the squelch marker.
-- §3.3.2(3)(4): receive level 0-100% with a freely adjustable squelch threshold
-- shown beside it. Fig 3-3 draws the threshold as a stub line with a solid block
-- on the end, pointing in at the bar.
-- @param sq  squelch position 0..1, or nil when auto-squelch is running
function M.draw_bar(ctx, x, y, h, level_pct, sq)
    ctx:frame(x, y, 5, h)
    local filled = math.floor(math.max(0, math.min(100, level_pct)) / 100 * (h - 2) + 0.5)
    if filled > 0 then ctx:rect(x + 1, y + h - 1 - filled, 3, filled) end

    -- Graduations every 10% down the right-hand side.
    for i = 0, 10 do
        local ty = y + h - 1 - math.floor(i / 10 * (h - 2) + 0.5)
        ctx:rect(x + 5, ty, (i % 5 == 0) and 3 or 2, 1)
    end

    if sq then
        local sy = y + h - 1 - math.floor(math.max(0, math.min(1, sq)) * (h - 2) + 0.5)
        ctx:rect(x + 5, sy, 5, 1)
        ctx:rect(x + 9, sy - 1, 3, 3)
    else
        lcd.text(ctx, x + 9, y + h - 6, "A")     -- auto squelch
    end
end

--- The mounting-orientation glyph the 517 prints after "MOUNT:" — an upright
--- tee for a TOP-mounted antenna and an inverted one for BOTTOM. Fig 3-3 shows
--- a symbol here rather than a word, and the distinction matters: the wrong
--- setting mirror-inverts every bearing the head reports.
function M.mount_glyph(ctx, x, y, bottom)
    if bottom then
        ctx:rect(x, y, 5, 1)            -- bar on top, stem down
        ctx:rect(x + 2, y + 1, 1, 4)
    else
        ctx:rect(x + 2, y, 1, 4)        -- stem up, bar on the bottom
        ctx:rect(x, y + 4, 5, 1)
    end
end

--- The row of page marks under the PAGE field on Fig 3-3: one mark per page,
--- the active one solid. Cheap, and it tells the operator where they are in the
--- six-page rotation without counting.
function M.page_dots(ctx, x, y, count, active)
    for i = 1, count do
        local dx = x + (i - 1) * 4
        if i == active then
            ctx:rect(dx, y - 1, 3, 3)
        else
            ctx:rect(dx + 1, y, 1, 1)
        end
    end
end

--- Inverted field — bright background, dark text — used for every highlighted
--- value and menu entry on both heads.
function M.inverted(ctx, x, y, str, back)
    local w = lcd.text_width(str) + 3
    ctx:rect(x, y - 1, w, lcd.CHAR_H + 3)
    lcd.text(ctx, x + 1, y + 1, str, back)
    return x + w
end

return M
