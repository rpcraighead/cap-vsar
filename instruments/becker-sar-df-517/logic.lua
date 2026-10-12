-- Becker SAR-DF 517 — 4-band precision direction finder
-- CAP V-SAR training simulator, Implementation Plan v0.8 §6.2.1
--
-- Display-and-control layer only. Propagation, averaging, terrain masking and
-- the 406 MHz burst cadence live in the X-Plane engine plugin (§5.2) and reach
-- us through cap/df/* — see docs/DATAREF_CONTRACT.md.
--
-- Behaviour follows the Becker "Installation and Operation" manual DV 77513.04:
--   §3.2.1  power-on mode selection (Emergency / Training)
--   §3.2.2  DIM via REP held while turning PAGE
--   §3.3.1  bearing-mode controls
--   §3.3.2  pages 1-3 bearing displays
--   §3.3.3  406 scanning mode
--   §3.3.4  COSPAS/SARSAT decode (page 4)
--   §3.3.5  edit menu (page 5)
--   §3.4    training frequencies (page 6)
--   §3.5    error messages
--
-- NOTE: the operating-mode choice is available *only* at power-up. That trap is
-- deliberate and is one of the things worth drilling on the ground (plan §6.2.1).

-- Air Manager executes lib/*.lua before logic.lua. The libraries publish
-- cap_df, cap_df_audio, lcd and dcu in this instrument's global namespace.
local df = cap_df
local df_audio = cap_df_audio

-- ------------------------------------------------------------------ geometry --

-- The chassis is shared with the RT-600 — see lib/dcu.lua. Square panel-mount
-- unit with clipped corners, four corner knobs, three buttons across the top,
-- ON/OFF at the bottom. Verified against Fig 3-3 on PDF page 29 of the manual.
local LCD_SCALE    = dcu.LCD_SCALE
local LCD_X, LCD_Y = dcu.LCD_X, dcu.LCD_Y

-- ------------------------------------------------------------------- state ----

local MODE_EMERGENCY, MODE_TRAINING = 0, 1

-- §1.3.1: four fixed emergency channels, four freely adjustable training
-- channels. Frequencies in Hz.
-- "box" is the two-line band caption in the page-1 frame, which Fig 3-3 shows
-- reading "SEA-BAND / CHNL.(16)" on the marine channel. Nine characters is what
-- the frame holds at this font.
-- "fm" marks the band whose 3 kHz Doppler tone the receiver filters out anyway,
-- so STORE's tone suppression has nothing to do there (§3.3.1(5)).
local EMERGENCY_FREQS = {
    { hz = 121500000, label = "121.500", band = "VHF",  box = { "AERO-BAND", "EMERGENCY" } },
    { hz = 156800000, label = "156.800", band = "CH16", fm = true,
      box = { "SEA-BAND",  "CHNL.(16)" } },
    { hz = 243000000, label = "243.000", band = "UHF",  box = { "UHF-BAND",  "MILITARY"  } },
    { hz = 406025000, label = "406.025", band = "C/S",  box = { "COSPAS",    "SARSAT"    } },
    -- §3.3.3: scan surveils the 406 burst and, in the 5-45 s gap between
    -- bursts, the two continuous emergency frequencies — 121.500 and 243.000.
    -- It sits in the frequency knob's rotation rather than on a control of its
    -- own. The caption names only the first pair; the frame has no room for all
    -- three and the FREQ field already reads SCAN.
    { hz = 406025000, label = "SCAN", band = "SCAN", scan = true,
      box = { "SCAN MODE", "406/121.5" } },
}

-- Defaults sit inside the training ranges given in §1.3.1. Page 6 edits these.
local training_freqs = {
    { hz = 121600000, label = "121.600", band = "VHF",  min = 118000000, max = 122975000,
      box = { "AERO-BAND", "TRAINING" } },
    { hz = 156900000, label = "156.900", band = "CH16", min = 156000000, max = 157975000,
      fm = true, box = { "SEA-BAND",  "TRAINING" } },
    { hz = 243100000, label = "243.100", band = "UHF",  min = 240000000, max = 245975000,
      box = { "UHF-BAND",  "TRAINING" } },
    { hz = 406037000, label = "406.037", band = "C/S",  min = 400000000, max = 409975000,
      box = { "COSPAS",    "TRAINING" } },
    { hz = 406037000, label = "SCAN",    band = "SCAN", scan = true,
      box = { "SCAN MODE", "TRAINING" } },
}

-- §1.3.1 "Receiving channels: 8 (four of them are free adjustable)". The fifth
-- row of training_freqs is the SCAN knob position, not a frequency: it carries
-- no min/max, so page 6 must not offer it for editing. Deriving the count keeps
-- the two facts from drifting apart.
local TRAINING_EDITABLE = 0
for _, f in ipairs(training_freqs) do
    if f.min then TRAINING_EDITABLE = TRAINING_EDITABLE + 1 end
end

local st = {
    power        = false,
    booting      = false,     -- startup screen, mode still selectable
    mode         = MODE_EMERGENCY,
    page         = 1,         -- 1..6
    freq_index   = 1,         -- 1..4 within the active mode
    volume       = 60,        -- %
    brightness   = 80,        -- %

    -- §3.3.1(3): "For each frequency exists a squelch level, which has to be
    -- adjusted separately."
    squelch      = { 25, 25, 25, 25, 25 },

    -- Page 5 edit menu
    timehold     = 10,        -- s, normal value per §3.3.5(5)
    offset       = 0,         -- deg, normal value 000
    mounting     = 0,         -- 0 = TOP, 1 = BOTTOM
    edit_field   = 1,

    -- Page 6 training-frequency editor
    freq_edit_field = 1,      -- which training channel / MHz vs kHz

    -- REP held: DIM mode (§3.2.2)
    rep_held     = false,
    -- Repeat display of last valid bearing (§3.3.1(6))
    repeat_show  = false,
    repeat_bearing = nil,
    repeat_signal  = nil,

    -- STORE in bearing mode suppresses the 3 kHz tone on AM signals (§3.3.1(5))
    tone_suppressed = false,

    -- Stored COSPAS/SARSAT message (page 4 STORE / REP)
    stored_msg   = nil,
    shown_msg    = nil,
}

local canvas_id, draw_lcd
local boot_timer

local function active_freqs()
    return st.mode == MODE_TRAINING and training_freqs or EMERGENCY_FREQS
end

local function current_freq()
    return active_freqs()[st.freq_index]
end

--- §3.3.3: scan is a position on the frequency knob, not a separate mode flag.
local function scanning()
    return current_freq().scan == true
end

--- The two continuous frequencies scan sweeps between 406 bursts. §1.3.1:
--- "When receiving Cospas/Sarsat signals additionally the emergency frequencies
--- 121.500 MHz and 243.000 MHz can be surveilled." In Training mode the head is
--- on the freely adjusted training channels instead, so the pair the engine
--- sweeps has to follow the active mode rather than being assumed.
local function scan_alternates()
    local list = active_freqs()
    local vhf, uhf
    for _, f in ipairs(list) do
        if f.band == "VHF" then vhf = f.hz end
        if f.band == "UHF" then uhf = f.hz end
    end
    return vhf, uhf
end

-- Air Manager's own log once recorded this call throwing "You cannot call
-- canvas_draw within a draw callback", paired with a cascading "attempt to call
-- a number value" from the 250 ms tick below. This used to be wrapped in a
-- pcall; I-2 removed it because a swallowed error hid the real fault. The call
-- is direct now, so a recurrence of that log line is a fault to chase, not a
-- race to paper over. Air Manager's exact reentrancy rule is not documented and
-- could not be re-verified against the live application.
local function redraw()
    if canvas_id then canvas_draw(canvas_id, draw_lcd) end
end

-- Audio follows instantaneous squelch state, never a TIMEHOLD bearing. The
-- receiver stays muted during its ten-second power-up screen.
local function sync_audio()
    df_audio.update(st.power and not st.booting, df.state.rx_open,
                    df.state.band_mhz, st.volume / 100, st.tone_suppressed,
                    (df.state.signal or 0) / 100)
end

-- Push the whole control state at the engine. Cheap, and keeps the engine from
-- having to remember which of several writes arrived first.
local function push_state()
    df.set_power(st.power)
    if not st.power then return end
    df.set_mode(st.mode)
    df.set_head_type(0)                     -- 0 = Becker 517
    df.set_frequency_hz(current_freq().hz)
    df.set_squelch(st.squelch[st.freq_index])
    df.set_span_hz(0)                       -- single-channel receiver
    df.set_scan(scanning())
    df.set_scan_alternates(scan_alternates())
    df.set_timehold(st.timehold)
    df.set_offset(st.offset)
    df.set_mounting(st.mounting)
end

-- --------------------------------------------------------------- LCD pages ----

local ERROR_TEXT = {
    [12] = "E12:VOLT.D", [11] = "E11: NO AU", [10] = "E10:BAD AU",
    [9]  = "E9: BAD RU", [8]  = "E8:VOLT.AU", [7]  = "E7:BAD DCU",
    [6]  = "E6: NO DCU", [5]  = "E5:OSCILAT", [4]  = "E4:F/+OFS+",
    [3]  = "E3:F/-OFS-", [2]  = "E2:CS/SYNC", [1]  = "E1: CS/BCH",
    [0]  = "E0: NO REC",
}

-- Text rendering uses the shared fixed-cell font in lib/lcd.lua.
local function text(ctx, px, py, str, colour, mult)
    return lcd.text(ctx, px, py, str, colour, mult)
end

local function text_right(ctx, px, py, str, colour, mult)
    return lcd.text_right(ctx, px, py, str, colour, mult)
end

--- Why there is no usable bearing. The engine reports both conditions and they
--- are exactly what makes a bearing untrustworthy, so the operator sees the
--- reason in place of the value rather than wondering why the needle died.
local function no_fix_reason()
    -- §3.3.1(5): STORE switches off the 3 kHz tone superimposed on an AM
    -- signal, "enables better hearing of a signal, meanwhile bearing isn't
    -- possible anymore". So suppressing the tone really does stop the bearing.
    if st.tone_suppressed then return "3K-" end
    if df.state.in_cone then return "CONE" end
    if df.state.blocked then return "MASK" end
    return nil
end

local REASON_LONG = {
    CONE = "CONE OF CONF", MASK = "TERRAIN MASK", ["3K-"] = "TONE OFF-NO BRG",
}

--- Is a live bearing available? REPEAT still recalls the last stored value —
--- that is a read-back of something already measured, not a live bearing.
local function bearing_live()
    return df.state.valid and not st.tone_suppressed
end

--- Bottom row shared by the bearing pages. Fig 3-3 shows volume bottom-left and
--- frequency bottom-right, each with its value in an inverted field.
local function draw_common(ctx)
    local back = lcd.background_colour(st.brightness)

    local vol = (st.volume <= 0) and "OFF" or string.format("%d", st.volume)
    local x = dcu.inverted(ctx, 1, 57, vol, back)
    text(ctx, x + 1, 58, "VOL")

    local f = current_freq()
    local fw = lcd.text_width(f.label) + 3
    text(ctx, 127 - fw - 17, 58, "FREQ")
    dcu.inverted(ctx, 127 - fw, 57, f.label, back)

    -- Mode and tone flags sit between the two inverted fields. The cone and
    -- terrain conditions are NOT shown here: they belong where the bearing
    -- would have been, and this row runs into the band frame.
    if st.mode == MODE_TRAINING then text(ctx, 34, 58, "TRN") end
    if st.tone_suppressed then text(ctx, 50, 58, "3K-") end
end

--- Signal-level bar with the squelch marker, used on pages 1-3.
-- §3.3.2(3)(4): level 0-100% with a freely adjustable squelch threshold beside
-- it. The drawing itself lives in lib/dcu.lua because both heads use it.
local function draw_signal_bar(ctx, px, py, h)
    dcu.draw_bar(ctx, px, py, h, df.state.signal,
                 st.squelch[st.freq_index] / 100)
end

--- Page 1 — 360 degree bearing display (§3.3.2, Fig 3-4; photo on PDF page 29).
-- Layout follows the real screen: level bar hard left with its 100 label, the
-- dotted compass rose centred with the bearing bracketed in the middle, and a
-- right-hand status column carrying page, offset, mounting and the LS timer.
local function draw_page_1(ctx)
    local bearing = st.repeat_show and st.repeat_bearing or df.state.bearing
    local showing = st.repeat_show or bearing_live()

    -- Level bar hard left with its 100 label, exactly as Fig 3-3 has it.
    lcd.text(ctx, 10, 4, "100")
    draw_signal_bar(ctx, 4, 11, 44)

    dcu.draw_rose(ctx, 51, 30, 27,
                  showing and bearing or nil,
                  df.has_spread() and df.state.spread or nil,
                  { ticks = true, no_fix = no_fix_reason() })

    -- Right-hand status column. It starts at 94 rather than the manual's 97
    -- because our fixed character cells are wider than the reference and an
    -- eight-character row would otherwise lose its last glyph off the edge.
    lcd.text(ctx, 94, 4, "PAGE")
    dcu.inverted(ctx, 118, 4, tostring(st.page), lcd.background_colour(st.brightness))
    dcu.page_dots(ctx, 94, 13, 6, st.page)
    lcd.text(ctx, 94, 17, string.format("OFS:%s%03d", st.offset >= 0 and "+" or "-",
                                        math.abs(st.offset)))
    lcd.text(ctx, 94, 26, "MOUNT:")
    dcu.mount_glyph(ctx, 119, 26, st.mounting == 1)
    lcd.text(ctx, 94, 35, "LS:" .. df.format_timer(df.state.last_signal))

    -- Band / channel frame, "SEA-BAND / CHNL.(16)" on the marine channel.
    local f = current_freq()
    ctx:frame(88, 42, 40, 14)
    if f.box then
        lcd.text(ctx, 90, 44, f.box[1])
        if f.box[2] then lcd.text(ctx, 90, 50, f.box[2]) end
    else
        lcd.text(ctx, 90, 44, f.band)
    end

    draw_common(ctx)
end

--- Page 2 — expanded +/-45 degree bearing display (§3.3.2, Fig 3-5).
local function draw_page_2(ctx)
    local left, right, base = 8, 88, 44
    local span = 45

    ctx:hline(left, base, right - left)
    for tick = -45, 45, 15 do
        local x = left + (tick + span) / (span * 2) * (right - left)
        ctx:vline(math.floor(x), base - 2, 3)
    end
    -- Centre index: the nose
    ctx:triangle(left + (right - left) / 2, base + 6,
                 left + (right - left) / 2 - 3, base + 10,
                 left + (right - left) / 2 + 3, base + 10)

    local bearing = st.repeat_show and st.repeat_bearing or df.state.bearing
    local showing = st.repeat_show or bearing_live()

    if showing and bearing then
        local off = df.relative_offset(bearing)
        local clamped = math.max(-span, math.min(span, off))
        local x = left + (clamped + span) / (span * 2) * (right - left)
        ctx:vline(math.floor(x), base - 22, 22)
        ctx:triangle(x, base - 24, x - 3, base - 29, x + 3, base - 29)

        text(ctx, 1, 6, string.format("%03d", math.floor(bearing + 0.5)))
        -- Off the edge of the expanded scale: say so rather than pegging silently.
        if math.abs(off) > span then
            text(ctx, 30, 6, off > 0 and ">>" or "<<")
        end
    else
        text(ctx, 1, 6, no_fix_reason() or "---")
    end

    draw_signal_bar(ctx, 92, 12, 40)
    draw_common(ctx)
end

--- Page 3 — bearing as text (§3.3.2, Fig 3-6).
local function draw_page_3(ctx)
    local bearing = st.repeat_show and st.repeat_bearing or df.state.bearing
    local signal  = st.repeat_show and st.repeat_signal or df.state.signal
    local showing = st.repeat_show or bearing_live()

    text(ctx, 4, 10, "BEARING")
    if showing and bearing then
        -- Large readout: the display font at triple size.
        text(ctx, 4, 20, string.format("%03d", math.floor(bearing + 0.5)), nil, 3)
        text(ctx, 44, 30, "DEG")
        if df.has_spread() then
            text(ctx, 4, 40, string.format("SPRD %02d", math.floor(df.state.spread + 0.5)))
        else
            text(ctx, 4, 40, string.format("RNG %4.1f", df.state.distance_nm))
        end
    else
        local why = no_fix_reason()
        text(ctx, 4, 22, why and REASON_LONG[why] or "NO SIGNAL")
    end

    text(ctx, 4, 48, string.format("LVL %3d%%", math.floor(signal + 0.5)))
    draw_signal_bar(ctx, 92, 12, 40)
    draw_common(ctx)
end

--- Page 4 — COSPAS/SARSAT binary analysis (§3.3.4, Fig 3-8).
-- Selecting this page forces the active frequency to 406 (or its training
-- equivalent), which the engine sees through the frequency write below.
local function draw_page_4(ctx)
    local s = df.state
    local msg = st.shown_msg

    text(ctx, 1, 1, "C/S ANALYSE")
    text_right(ctx, 127, 1, "4")

    local sync, proto, hex15, country, has_pos, lat, lon, age
    if msg then
        sync     = msg.sync
        proto    = msg.protocol
        hex15    = msg.hex15
        country  = msg.country
        has_pos  = msg.has_pos
        lat      = msg.lat
        lon      = msg.lon
        age      = 0
    else
        sync     = s.cs_sync
        proto    = s.cs_protocol
        hex15    = s.cs_hex15
        country  = s.cs_country
        has_pos  = s.cs_has_pos
        lat      = s.cs_lat
        lon      = s.cs_lon
        age      = s.cs_msg_age
    end

    if sync == 1 then
        text(ctx, 1, 10, "SYNC OK")
    elseif sync == 2 then
        text(ctx, 1, 10, "SLFTEST")
    else
        text(ctx, 1, 10, "NO SYNC")
        text(ctx, 1, 20, "WAITING FOR")
        text(ctx, 1, 28, "BURST " .. df.format_timer(s.burst_age))
        text(ctx, 1, 44, string.format("%d%%", math.floor(st.volume)))
        text_right(ctx, 127, 58, current_freq().label)
        return
    end

    local PROTO = { [1] = "USER", [2] = "STANDARD", [3] = "NATIONAL" }
    local base = (proto or 0) % 4
    local name = PROTO[base] or "UNKNOWN"
    if proto and proto > 3 then name = name .. " TEST" end
    text(ctx, 46, 10, name)

    text(ctx, 1, 19, "ID " .. (hex15 or ""))
    text(ctx, 1, 28, string.format("CTRY %03d", country or 0))

    if has_pos and lat and lon then
        text(ctx, 1, 37, string.format("%s%06.3f", lat >= 0 and "N" or "S", math.abs(lat)))
        text(ctx, 1, 46, string.format("%s%07.3f", lon >= 0 and "E" or "W", math.abs(lon)))
    else
        text(ctx, 1, 37, "NO POSITION")
    end

    if st.stored_msg then text_right(ctx, 127, 46, "STORED") end
    text(ctx, 1, 57, "T " .. df.format_timer(age))
    text_right(ctx, 127, 57, current_freq().label)
end

--- Page 5 — edit menu (§3.3.5, Fig 3-9).
local EDIT_FIELDS = { "TIMEHOLD", "OFFSET", "MOUNTING" }

local function draw_page_5(ctx)
    text(ctx, 1, 1, "EDIT MENU")
    text_right(ctx, 127, 1, "5")

    local rows = {
        { "TIMEHOLD", string.format("%3d SEC", st.timehold) },
        { "OFFSET",   string.format("%03d DEG", st.offset) },
        { "MOUNTING", st.mounting == 0 and "TOP" or "BOTTOM" },
    }
    for i, row in ipairs(rows) do
        local y = 14 + (i - 1) * 11
        if st.edit_field == i then text(ctx, 1, y, ">") end
        text(ctx, 7, y, row[1])
        text_right(ctx, 127, y, row[2])
    end

    text(ctx, 1, 51, "SEL:+/-  SET:STORE")
end

--- Page 6 — adjustable training frequencies (§3.4, Fig 3-10).
local function draw_page_6(ctx)
    text(ctx, 1, 1, "TRAINING FREQ")
    text_right(ctx, 127, 1, "6")

    -- Four rows, not five: SCAN is a knob position, not a training frequency.
    -- Listing it here also ran the last row into the status line below.
    for i = 1, TRAINING_EDITABLE do
        local f = training_freqs[i]
        local y = 12 + (i - 1) * 10
        if st.freq_edit_field == i then text(ctx, 1, y, ">") end
        text(ctx, 7, y, f.band)
        text_right(ctx, 127, y, f.label)
    end

    if st.mode ~= MODE_TRAINING then
        text(ctx, 1, 55, "EMERG MODE - VIEW ONLY")
    else
        text(ctx, 1, 55, "SET:STORE")
    end
end

--- Startup screen with the mode still selectable (§3.2.1, Fig 3-1).
local function draw_boot(ctx)
    text(ctx, 20, 4, "SAR-DF 517")
    text(ctx, 12, 16, "SELECT MODE")

    local emergency_selected = (st.mode == MODE_EMERGENCY)
    -- Selected option is shown inverted, matching the real menu highlight.
    local function option(y, label, selected)
        if selected then
            ctx:rect(10, y - 2, 108, 9)
            text(ctx, 14, y, label, lcd.background_colour(st.brightness))
        else
            text(ctx, 14, y, label)
        end
    end
    option(28, "EMERGENCY", emergency_selected)
    option(40, "TRAINING", not emergency_selected)

    text(ctx, 6, 54, "PAGE KNOB SELECTS")
end

local PAGE_DRAW = {
    draw_page_1, draw_page_2, draw_page_3,
    draw_page_4, draw_page_5, draw_page_6,
}

-- ------------------------------------------------------------ canvas draw ----

draw_lcd = function()
    local ctx = lcd.context(LCD_SCALE, 0, 0)

    -- Backlit background
    _rect(0, 0, lcd.WIDTH * LCD_SCALE, lcd.HEIGHT * LCD_SCALE)
    _fill(lcd.background_colour(st.power and st.brightness or 0))

    if not st.power then return end

    -- §3.5: an internal error flashes and takes priority over normal content.
    -- The engine publishes -1 for "no error", not 0, because E0 (NO RECEIVER)
    -- is itself a real Becker code and would otherwise be unreachable.
    local err = df.state.error_code
    if err and err >= 0 and ERROR_TEXT[err] then
        text(ctx, 20, 26, ERROR_TEXT[err])
        return
    end

    if st.booting then
        draw_boot(ctx)
        return
    end

    if st.rep_held then
        -- DIM mode: PAGE knob sets brightness while REP is held (§3.2.2(1)).
        text(ctx, 30, 22, "DIM")
        text(ctx, 30, 34, string.format("%3d%%", math.floor(st.brightness)))
        return
    end

    PAGE_DRAW[st.page](ctx)
end

-- ------------------------------------------------------------- faceplate -----

-- The housing and every silk-screened legend live in resources/faceplate.png.
-- The Becker bezel carries "Clr / Store / Rep", the Rhotheta-SAR-DF 517-BECKER
-- identification block and DIM under Rep — and, unlike the RT-600, no F1/F2
-- alternates and no RT-600 name. Regenerate it with
-- `python3 scripts/make_df_artwork.py`, which reads the geometry out of
-- lib/dcu.lua so the art and these hit regions cannot drift apart.

-- ------------------------------------------------------------ layer order ----

-- Add order is layer order in Air Manager: first added is furthest back. The
-- faceplate is the backplate, the LCD canvas sits in its window, and the
-- control hotspots added at the end stay above both.
dcu.add_faceplate()
canvas_id = canvas_add(LCD_X, LCD_Y, dcu.LCD_W, dcu.LCD_H, draw_lcd)

-- ------------------------------------------------------------- behaviour -----

local function set_page(page)
    st.page = math.max(1, math.min(6, page))
    -- §3.3.4: selecting page 4 activates the 406 frequency automatically.
    if st.page == 4 then
        for i, f in ipairs(active_freqs()) do
            if f.band == "C/S" and not f.scan then st.freq_index = i end
        end
        df_audio.stop()
        df.set_frequency_hz(current_freq().hz)
        df.set_squelch(st.squelch[st.freq_index])
        df.set_scan(false)
    end
    redraw()
end

--- Everything on the screen that is a transient of the last session. The real
--- head powers up clean: STORE's tone suppression, the REP bearing and the C/S
--- frame on show do not survive a power cycle. Settings (volume, squelch,
--- TIMEHOLD, offset, mounting) and the stored frame are kept.
local function reset_volatile()
    st.tone_suppressed = false
    st.repeat_show     = false
    st.repeat_bearing  = nil
    st.repeat_signal   = nil
    st.rep_held        = false
    st.shown_msg       = nil
end

local function power_on()
    st.power   = true
    st.booting = true
    reset_volatile()
    push_state()
    sync_audio()
    redraw()

    -- The mode window closes when the startup screen ends and cannot be
    -- reopened without a power cycle.
    if boot_timer then timer_stop(boot_timer) end
    boot_timer = timer_start(10000, 0, function()
        st.booting = false
        st.page = 1
        push_state()
        sync_audio()
        redraw()
    end)
end

local function power_off()
    if boot_timer then timer_stop(boot_timer); boot_timer = nil end
    st.power   = false
    st.booting = false
    reset_volatile()
    df.set_power(false)
    df_audio.stop()
    redraw()
end

-- Set by the cap_power watcher at the bottom of this file.
local bus_powered = false

-- ---------------------------------------------------------------- controls ---

dcu.add_controls({
    power = function()
        if not bus_powered then return end
        if st.power then power_off() else power_on() end
    end,

    -- §3.2.2(2) PAGE, and §3.2.1 operating-mode selection during the power-on
    -- window, and §3.2.2(1) brightness while REP is held.
    page = function(direction)
        if not st.power then return end

        if st.booting then
            st.mode = (direction > 0) and MODE_TRAINING or MODE_EMERGENCY
            st.freq_index = 1
            push_state()
            redraw()
            return
        end

        if st.rep_held then
            st.brightness = math.max(0, math.min(100, st.brightness + direction * 5))
            redraw()
            return
        end

        set_page(st.page + direction)
    end,

    -- §3.3.1(1) FREQUENCY, doubling as the field selector on pages 5 and 6.
    freq = function(direction)
        if not st.power or st.booting then return end

        if st.page == 5 then
            st.edit_field = ((st.edit_field - 1 + direction) % #EDIT_FIELDS) + 1
            redraw()
            return
        end
        if st.page == 6 then
            st.freq_edit_field =
                ((st.freq_edit_field - 1 + direction) % TRAINING_EDITABLE) + 1
            redraw()
            return
        end

        local list = active_freqs()
        st.freq_index = ((st.freq_index - 1 + direction) % #list) + 1
        st.repeat_show = false
        st.tone_suppressed = false
        df_audio.stop()
        df.set_frequency_hz(current_freq().hz)
        df.set_squelch(st.squelch[st.freq_index])
        df.set_scan(scanning())
        df.set_scan_alternates(scan_alternates())
        redraw()
    end,

    -- §3.3.1(2) VOLUME, doubling as the value rotary while editing.
    vol = function(direction)
        if not st.power then return end

        if not st.booting and (st.page == 5 or st.page == 6) then
            if st.page == 5 then
                local f = EDIT_FIELDS[st.edit_field]
                if f == "TIMEHOLD" then
                    st.timehold = math.max(1, math.min(99, st.timehold + direction))
                elseif f == "OFFSET" then
                    st.offset = (st.offset + direction) % 360
                else
                    st.mounting = 1 - st.mounting
                end
            elseif st.mode == MODE_TRAINING then
                local f = training_freqs[st.freq_edit_field]
                local hz = f.hz + direction * 25000
                -- The min guard is belt and braces: freq_edit_field cannot
                -- reach the SCAN row, and if it ever did this would refuse
                -- rather than compare a number with nil.
                if f.min and hz >= f.min and hz <= f.max then
                    f.hz = hz
                    f.label = string.format("%.3f", hz / 1e6)
                end
            end
            redraw()
            return
        end

        st.volume = math.max(0, math.min(100, st.volume + direction * 2))
        sync_audio()
        redraw()
    end,

    -- §3.3.1(3) squelch, a separate level stored per frequency.
    sql = function(direction)
        if not st.power or st.booting then return end
        local i = st.freq_index
        st.squelch[i] = math.max(0, math.min(100, st.squelch[i] + direction * 2))
        df.set_squelch(st.squelch[i])
        redraw()
    end,

    -- §3.3.1(4) CLR — erases the averaging store, or the displayed C/S message.
    clr_press = function()
        if not st.power or st.booting then return end
        if st.page == 4 then
            st.shown_msg = nil
        else
            df.clear_average()
            st.repeat_show = false
        end
        redraw()
    end,

    -- §3.3.1(5) STORE — commits edits, stores a C/S message, or suppresses the
    -- 3 kHz tone superimposed on AM signals in bearing mode.
    store_press = function()
        if not st.power or st.booting then return end

        if st.page == 4 then
            local s = df.state
            if s.cs_sync ~= 0 then
                st.stored_msg = {
                    sync = s.cs_sync, protocol = s.cs_protocol, hex15 = s.cs_hex15,
                    country = s.cs_country, has_pos = s.cs_has_pos,
                    lat = s.cs_lat, lon = s.cs_lon,
                }
            end
        elseif st.page == 5 or st.page == 6 then
            push_state()
        elseif current_freq().fm then
            -- §3.3.1(5): on the maritime FM band an internal filter already
            -- fades the 3 kHz tone out, so the key has nothing to switch off.
            st.tone_suppressed = false
        else
            st.tone_suppressed = not st.tone_suppressed
        end
        sync_audio()
        redraw()
    end,

    -- §3.3.1(6) REP — last valid bearing; held, it is the DIM modifier.
    rep_press = function()
        if not st.power or st.booting then return end
        st.rep_held = true
        if st.page == 4 then
            st.shown_msg = st.stored_msg
        elseif df.state.valid then
            st.repeat_bearing = df.state.bearing
            st.repeat_signal  = df.state.signal
            st.repeat_show    = true
        end
        redraw()
    end,

    rep_release = function()
        st.rep_held = false
        st.repeat_show = false
        redraw()
    end,
})

-- ------------------------------------------------------------------ wiring ---

df.subscribe()
df.on_change(function()
    sync_audio()
    if st.power then redraw() end
end)

-- Keep the LS / burst timers ticking even when the engine is quiet.
-- The engine publishes no Last Signal or burst timer, so cap_df derives them
-- from valid-state transitions and needs a regular tick.
timer_start(0, 250, function()
    df.tick(0.25)
end)

df.set_power(false)
df_audio.stop()

-- Bus power: avionics master, bus voltage, mission master and this breaker
-- (lib/cap_power.lua; docs/DATAREF_CONTRACT.md Part 6).
cap_power.watch("cap_mission_cb_df_in", function(powered)
    bus_powered = powered
    if powered then
        power_on()
    else
        power_off()
    end
end)
