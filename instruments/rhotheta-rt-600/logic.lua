-- RHOTHETA RT-600 — wideband airborne radio direction finder
-- CAP V-SAR training simulator, Implementation Plan v0.8 §6.2.2
--
-- The RT-600 is the CAP fleet replacement for the Becker SAR-DF 517. It shares
-- the same 128x64 LCD and the same propagation engine (cap/df/*), so this
-- faceplate is a sibling of the 517 rather than a rewrite — the difference the
-- exercise is meant to teach is 406 MHz channel coverage, and that is decided
-- engine-side from cap/df/head_type (see docs/DATAREF_CONTRACT.md).
--
-- Behaviour follows the RHOTHETA "User Manual: Installation and Operation"
-- for the RT-600 / SAR-DF 517:
--   §2.1    front panel, Page knob and ON/OFF are the only page-independent controls
--   §2.1.1  three push-buttons with dual function (short press F1/F2/DIM,
--           long press CLR/STORE/REP)
--   §2.1.2  five-second power-on screen
--   §2.1.3  two main pages, DF and FRQ
--   §2.1.4  dimming, 5-100% in 5% steps, stored per day/night
--   §2.3.1  DF-mode operating elements
--   §2.3.2  standard DF display
--   §2.3.3  COSPAS-SARSAT options and Auto Squelch
--   §2.3.4  COSPAS-SARSAT decode window
--
-- The most important behavioural difference from the 517: the RT-600's three
-- buttons do one thing on a short press and another when held, and the softkey
-- legends along the bottom of the LCD say which. Everything is context sensitive.

-- Air Manager executes lib/*.lua before logic.lua. The libraries publish
-- cap_df, cap_df_audio, lcd and dcu in this instrument's global namespace.
local df = cap_df
local df_audio = cap_df_audio

-- Same physical control head as the 517 — see lib/dcu.lua. Verified against
-- Fig 2 on PDF page 8 of the RT-600 manual and the CAP training deck's
-- photographs of the unit installed in an aircraft (deck PDF page 8).
local LCD_SCALE    = dcu.LCD_SCALE
local LCD_X, LCD_Y = dcu.LCD_X, dcu.LCD_Y

-- Long-press threshold. The manual gives "> 2 sec" for CLR/STORE and "ca. 3
-- seconds" for REP; a single 2 s threshold is close enough to teach the habit
-- of holding the key rather than tapping it.
local LONG_PRESS_MS = 2000

-- ------------------------------------------------------------------- state ----

-- §2.2.3: the 406 MHz band is the reason the RT-600 exists in this project, and
-- the way it covers that band is the whole point. It does NOT tune individual
-- channels. It selects one of seven CPSAR groups, each covering two or three of
-- the 3 kHz channels *simultaneously*:
--
--   CPSAR1 "022-028"   406.022 … 028 MHz   channels A, B, C
--   CPSAR2 "031-037"   406.031 … 037 MHz   channels D, E, F
--   CPSAR3 "040-043"   406.040 … 043 MHz   channels G, H
--   CPSAR4 "046-052"   406.046 … 052 MHz   channels I, J, K
--   CPSAR5 "055-061"   406.055 … 061 MHz   channels L, M, N
--   CPSAR6 "064-070"   406.064 … 070 MHz   channels O, P, Q
--   CPSAR7 "073-076"   406.073 … 076 MHz   channels R, S
--
-- That is nineteen channels, A through S, on an inclusive 406.022–406.076 grid
-- — not the eighteen an earlier draft counted by stopping at 406.073. The
-- Becker's technical data lists a single COSPAS/SARSAT channel, 406.025, so one
-- RT-600 group selection already covers ground the Becker cannot reach at all.
-- The engine decides receivability from the centre and span below.
local CS_GROUPS = {
    { lo = 406022000, hi = 406028000, label = "022-028", chans = "A-C" },
    { lo = 406031000, hi = 406037000, label = "031-037", chans = "D-F" },
    { lo = 406040000, hi = 406043000, label = "040-043", chans = "G-H" },
    { lo = 406046000, hi = 406052000, label = "046-052", chans = "I-K" },
    { lo = 406055000, hi = 406061000, label = "055-061", chans = "L-N" },
    { lo = 406064000, hi = 406070000, label = "064-070", chans = "O-Q" },
    { lo = 406073000, hi = 406076000, label = "073-076", chans = "R-S" },
}

local function cs_channels()
    local list = {}
    for _, g in ipairs(CS_GROUPS) do
        list[#list + 1] = {
            hz    = math.floor((g.lo + g.hi) / 2),      -- receiver centre
            span  = math.floor((g.hi - g.lo) / 2),      -- half-width covered
            label = g.label,
            chans = g.chans,
            band  = "C/S",
        }
    end
    return list
end

local FREQS = {}
do
    -- International emergency and application frequencies first, then the full
    -- COSPAS-SARSAT channel set.
    local base = {
        { hz = 121500000, label = "121.500", band = "VHF"  },
        { hz = 243000000, label = "243.000", band = "UHF"  },
        { hz = 156800000, label = "156.800", band = "CH16" },
    }
    for _, f in ipairs(base) do FREQS[#FREQS + 1] = f end
    for _, f in ipairs(cs_channels()) do FREQS[#FREQS + 1] = f end
end

local PAGE_DF, PAGE_FRQ = 1, 2

local st = {
    power       = false,
    booting     = false,
    page        = PAGE_DF,
    freq_index  = 1,
    volume      = 60,        -- §2.3.1(2): 0..99
    brightness  = 80,        -- §2.1.4: 5..100 in 5% steps
    dim_mode    = false,

    -- §2.3.2(4): squelch is 0..60% and is stored per band, not per frequency.
    squelch     = { VHF = 25, UHF = 25, CH16 = 25, ["C/S"] = 0 },

    -- §2.3.3(1): 0% or 60% forces Auto Squelch during COSPAS-SARSAT operation.
    decode_open = false,
    scan        = false,

    repeat_show    = false,
    repeat_bearing = nil,
    repeat_signal  = nil,

    -- §2.3.5: switching to 121.500 from a COSPAS-SARSAT channel is a temporary
    -- excursion; the unit offers a direct route back to the channel it left.
    cs_return_index = nil,

    -- Set while a button is down so release can tell short from long.
    press_at    = {},
    long_fired  = {},
}

local canvas_id, draw_lcd
local boot_timer, dim_timer

local function current_freq() return FREQS[st.freq_index] end

-- Same fix as the Becker's redraw() and for the same reason: this instrument
-- shares the cap_df.lua 250 ms tick timer, which is the one caller of redraw()
-- that isn't a button or dataref callback and so is the one that can race the
-- engine's own repaint. See the Becker's logic.lua for the log evidence and
-- the caveat that this is a best-effort fix, not verified live.
local function redraw()
    if canvas_id then canvas_draw(canvas_id, draw_lcd) end
end

-- Audio follows instantaneous squelch state, never a bearing retained by
-- TIMEHOLD. The receiver stays muted during its five-second power-up screen.
local function sync_audio()
    df_audio.update(st.power and not st.booting, df.state.rx_open,
                    df.state.band_mhz, st.volume / 99, false,
                    (df.state.signal or 0) / 100)
end

--- §2.3.3(1): on a COSPAS-SARSAT channel, a squelch of 0 or 60 means the unit
--- sets the threshold automatically just above the noise floor.
local function auto_squelch_active()
    local f = current_freq()
    if f.band ~= "C/S" then return false end
    local sq = st.squelch[f.band]
    return sq <= 0 or sq >= 60
end

local function push_state()
    df.set_power(st.power)
    if not st.power then return end
    df.set_head_type(1)                       -- 1 = RHOTHETA RT-600
    df.set_mode(0)                            -- RT-600 has no separate training mode
    df.set_frequency_hz(current_freq().hz)
    -- A CPSAR group covers several channels at once; everything else is a
    -- single frequency.
    df.set_span_hz(current_freq().span or 0)
    -- Auto squelch is expressed to the engine as a negative threshold, which is
    -- the one value a real level can never take.
    df.set_squelch(auto_squelch_active() and -1 or st.squelch[current_freq().band])
    df.set_scan(st.scan)
end

-- --------------------------------------------------------------- LCD pages ----

local text, text_right = lcd.text, lcd.text_right

--- Softkey legend strip along the bottom of the display. §2.1(3): "If a field
--- with dark background and bright text is shown below a button, the function
--- described in this field may be selected through the operational element."
local function draw_softkeys(ctx, f1, f2)
    local back = lcd.background_colour(st.brightness)
    -- The menu strip runs along the TOP of the display, directly under the
    -- three push-buttons it labels (§2.1(3)).
    for _, slot in ipairs({ { 2, f1 }, { 34, f2 } }) do
        local x, label = slot[1], slot[2]
        if label and label ~= "" then
            dcu.inverted(ctx, x, 1, label, back)
        end
    end
end

--- §2.3.2 DF mode. Layout follows the photographed screen: softkey fields and
--- page tabs across the top, signal percentage and bar down the left, the
--- dotted rose centred with the bearing bracketed, and a right-hand column
--- carrying the Last Signal timer, band name and channel range.
local function draw_page_df(ctx)
    local s = df.state
    local back = lcd.background_colour(st.brightness)
    local f = current_freq()

    -- Signal percentage above the bar, as on the real screen.
    text(ctx, 2, 11, string.format("%d%%", math.floor(s.signal + 0.5)))
    dcu.draw_bar(ctx, 3, 19, 30, s.signal,
                 (not auto_squelch_active()) and (st.squelch[f.band] / 60) or nil)

    local bearing = st.repeat_show and st.repeat_bearing or s.bearing
    local showing = st.repeat_show or s.valid
    local why = s.in_cone and "CONE" or (s.blocked and "MASK" or nil)
    dcu.draw_rose(ctx, 53, 31, 22,
                  showing and bearing or nil,
                  df.has_spread() and s.spread or nil,
                  { no_fix = why })

    -- Right-hand column
    text(ctx, 84, 11, df.format_timer(s.last_signal) .. " LS")
    if f.band == "C/S" then
        text(ctx, 84, 22, "SARSAT")
        text(ctx, 84, 31, f.label)          -- the selected group, e.g. 031-037
        text(ctx, 84, 40, "CH " .. (f.chans or ""))
    else
        text(ctx, 84, 22, f.band)
    end

    -- Bottom row: volume left, frequency right, both in inverted fields.
    local vol = (st.volume <= 0) and "OFF" or string.format("%d", st.volume)
    local x = dcu.inverted(ctx, 1, 49, vol, back)
    text(ctx, x + 1, 50, "VOL")

    local fw = lcd.text_width(f.label) + 3
    text(ctx, 127 - fw - 15, 50, "FRQ")
    dcu.inverted(ctx, 127 - fw, 49, f.label, back)

    -- Softkeys are context sensitive (§2.3.3(2)(3), §2.3.5).
    if f.band == "C/S" then
        draw_softkeys(ctx, "121.5", "DECODE")
    elseif st.cs_return_index then
        draw_softkeys(ctx, "406", "")
    else
        draw_softkeys(ctx, st.scan and "STOP" or "SCAN", "")
    end
end

--- §2.1.3 / frequency selection page.
local function draw_page_frq(ctx)
    text(ctx, 2, 1, "FREQ SELECT")

    -- Window of channels around the selection.
    local per_page = 5
    local first = math.max(1, math.min(#FREQS - per_page + 1, st.freq_index - 2))
    local back = lcd.background_colour(st.brightness)

    for row = 0, per_page - 1 do
        local idx = first + row
        local f = FREQS[idx]
        if f then
            local y = 11 + row * 8
            if idx == st.freq_index then
                ctx:rect(1, y - 1, 126, 7)
                text(ctx, 3, y, f.band, back)
                text_right(ctx, 124, y, f.label, back)
            else
                text(ctx, 3, y, f.band)
                text_right(ctx, 124, y, f.label)
            end
        end
    end

    text(ctx, 2, 48, string.format("%d/%d", st.freq_index, #FREQS))
    draw_softkeys(ctx, "SELECT", "")
end

--- §2.3.4 COSPAS-SARSAT decode window.
local function draw_decode(ctx)
    local s = df.state
    text(ctx, 2, 1, "C/S DECODE")

    if s.cs_sync == 0 then
        text(ctx, 2, 14, "NO VALID FRAME")
        text(ctx, 2, 24, "BURST " .. df.format_timer(s.burst_age))
        draw_softkeys(ctx, "BACK", "")
        return
    end

    text(ctx, 2, 11, s.cs_sync == 2 and "SELFTEST" or "SYNC OK")

    local PROTO = { [1] = "USER", [2] = "STANDARD", [3] = "NATIONAL" }
    local base = s.cs_protocol % 4
    local name = PROTO[base] or "UNKNOWN"
    if s.cs_protocol > 3 then name = name .. " TEST" end
    text(ctx, 52, 11, name)

    text(ctx, 2, 20, "ID " .. s.cs_hex15)
    text(ctx, 2, 29, string.format("CTRY %03d", s.cs_country))

    if s.cs_has_pos then
        text(ctx, 2, 38, string.format("%s%06.3f %s%07.3f",
            s.cs_lat >= 0 and "N" or "S", math.abs(s.cs_lat),
            s.cs_lon >= 0 and "E" or "W", math.abs(s.cs_lon)))
    else
        text(ctx, 2, 38, "NO POSITION")
    end

    text(ctx, 2, 47, "AGE " .. df.format_timer(s.cs_msg_age))
    draw_softkeys(ctx, "BACK", "")
end

--- §2.1.2 power-on screen, displayed for five seconds.
local function draw_boot(ctx)
    text(ctx, 34, 8, "RT-600")
    text(ctx, 22, 20, "STANDARD (A)")
    text(ctx, 14, 32, "WWW.RHOTHETA.COM")
    text(ctx, 10, 44, "AU 1.40  DCU 1.40")
end

-- ------------------------------------------------------------ canvas draw ----

draw_lcd = function()
    local ctx = lcd.context(LCD_SCALE, 0, 0)

    _rect(0, 0, lcd.WIDTH * LCD_SCALE, lcd.HEIGHT * LCD_SCALE)
    _fill(lcd.background_colour(st.power and st.brightness or 0))

    if not st.power then return end

    if st.booting then draw_boot(ctx); return end

    if st.dim_mode then
        -- §2.1.4(2): brightness replaces the Page field in the top right.
        text(ctx, 40, 22, "DIM")
        text(ctx, 34, 34, string.format("%3d%%", math.floor(st.brightness)))
        return
    end

    -- §2.1(3): the page menu sits top right with the active page highlighted.
    local back = lcd.background_colour(st.brightness)
    local function page_tab(x, label, active)
        if active then
            dcu.inverted(ctx, x, 1, label, back)
        else
            text(ctx, x + 1, 2, label)
        end
    end

    if st.decode_open then
        draw_decode(ctx)
    else
        page_tab(96, "DF",  st.page == PAGE_DF)
        page_tab(112, "FRQ", st.page == PAGE_FRQ)
        if st.page == PAGE_DF then draw_page_df(ctx) else draw_page_frq(ctx) end
    end
end

-- ------------------------------------------------------------- faceplate -----

-- The housing and every silk-screened legend live in resources/faceplate.png.
-- §2.1.1: each button does one thing on a short press and another when held, and
-- the bezel is silk-screened with both — so unlike the Becker this faceplate
-- carries boxed F1 and F2 alternates under Clr and Store, and the RHOTHETA /
-- SAR-DF 517 / RT-600.DCU identification the real bezel has. Regenerate it with
-- `python3 scripts/make_df_artwork.py`, which reads the geometry out of
-- lib/dcu.lua so the art and the hit regions cannot drift apart.

-- Add order is layer order: faceplate, then the LCD in its window, then the
-- control hotspots on top of both.
dcu.add_faceplate()
canvas_id = canvas_add(LCD_X, LCD_Y, dcu.LCD_W, dcu.LCD_H, draw_lcd)

-- ------------------------------------------------------------- behaviour -----

--- Transients of the last session. The real head powers up clean, so a REP
--- bearing or an open decode window does not survive a power cycle.
local function reset_volatile()
    st.repeat_show, st.decode_open = false, false
    st.repeat_bearing, st.repeat_signal = nil, nil
end

local function power_on()
    st.power, st.booting = true, true
    reset_volatile()
    push_state(); sync_audio(); redraw()

    if boot_timer then timer_stop(boot_timer) end
    boot_timer = timer_start(5000, 0, function()   -- §2.1.2: five seconds
        st.booting = false
        sync_audio()
        redraw()
    end)
end

local function power_off()
    if boot_timer then timer_stop(boot_timer); boot_timer = nil end
    if dim_timer then timer_stop(dim_timer); dim_timer = nil end
    for k, t in pairs(st.press_at) do
        timer_stop(t)
        st.press_at[k] = nil
    end
    for k in pairs(st.long_fired) do
        st.long_fired[k] = false
    end
    st.power, st.booting, st.dim_mode = false, false, false
    reset_volatile()
    df.set_power(false)
    df_audio.stop()
    redraw()
end

-- Set by the cap_power watcher at the bottom of this file.
local bus_powered = false

--- §2.1.4: DIM mode falls back to the prior page after ~3 s of inactivity.
local function enter_dim_mode()
    st.dim_mode = true
    if dim_timer then timer_stop(dim_timer) end
    dim_timer = timer_start(3000, 0, function()
        st.dim_mode = false
        redraw()
    end)
    redraw()
end

--- Short press of F1 (§2.3.3(2), §2.3.1(4)).
local function f1_short()
    if st.decode_open then
        st.decode_open = false
    elseif st.page == PAGE_FRQ then
        st.page = PAGE_DF                       -- SELECT confirms the channel
        df_audio.stop()
        push_state()
    elseif current_freq().band == "C/S" then
        -- §2.3.3(2): direct switch-over to 121.500 while working a beacon.
        st.cs_return_index = st.freq_index
        for i, f in ipairs(FREQS) do
            if f.hz == 121500000 then st.freq_index = i end
        end
        df_audio.stop()
        push_state()
    elseif st.cs_return_index then
        -- §2.3.5: direct return to the COSPAS-SARSAT channel we left.
        st.freq_index = st.cs_return_index
        st.cs_return_index = nil
        df_audio.stop()
        push_state()
    else
        st.scan = not st.scan
        df.set_scan(st.scan)
    end
    redraw()
end

--- Short press of F2 (§2.3.3(3)).
local function f2_short()
    if st.page == PAGE_DF and current_freq().band == "C/S" then
        st.decode_open = not st.decode_open
        redraw()
    end
end

--- Long press of F1 = CLR (§2.3.1(4)).
local function f1_long()
    df.clear_average()
    st.repeat_show = false
    redraw()
end

--- Long press of F2 = STORE. §2.3.1(5): "Without function except if a special
--- function is high-lighted in the menu line" — on the standard version there
--- is nothing to store outside the setup page, so this is deliberately inert.
local function f2_long() end

--- Long press of DIM = REP (§2.3.1(6)).
local function rep_long()
    if df.state.valid then
        st.repeat_bearing = df.state.bearing
        st.repeat_signal  = df.state.signal
        st.repeat_show    = true
        redraw()
    end
end

-- ---------------------------------------------------------------- controls ---

--- Build the press/release pair for one of the three dual-function buttons.
local function dual(ctrl_key, short_fn, long_fn, clears_repeat)
    return
        function()   -- press
            if not st.power or st.booting then return end
            st.long_fired[ctrl_key] = false
            st.press_at[ctrl_key] = timer_start(LONG_PRESS_MS, 0, function()
                st.long_fired[ctrl_key] = true
                st.press_at[ctrl_key] = nil
                long_fn()
            end)
        end,
        function()   -- release
            if st.press_at[ctrl_key] then
                timer_stop(st.press_at[ctrl_key])
                st.press_at[ctrl_key] = nil
            end
            if not st.power or st.booting then
                st.long_fired[ctrl_key] = false
                return
            end
            if not st.long_fired[ctrl_key] then short_fn() end
            st.long_fired[ctrl_key] = false
            -- REP holds the frozen value only while its own key is down.
            if clears_repeat and st.repeat_show then
                st.repeat_show = false
                redraw()
            end
        end
end

local clr_press,   clr_release   = dual("clr",   f1_short, f1_long)
local store_press, store_release = dual("store", f2_short, f2_long)
local rep_press,   rep_release   = dual("rep",
                                        function() enter_dim_mode() end,
                                        rep_long, true)

dcu.add_controls({
    power = function()
        if not bus_powered then return end
        if st.power then power_off() else power_on() end
    end,

    -- §2.3.1(2) VOLUME, 0..99
    vol = function(direction)
        if not st.power or st.booting then return end
        st.volume = math.max(0, math.min(99, st.volume + direction))
        sync_audio()
        redraw()
    end,

    -- §2.3.1(3) SQUELCH, 0..60, stored per band
    sql = function(direction)
        if not st.power or st.booting then return end
        local band = current_freq().band
        st.squelch[band] = math.max(0, math.min(60, st.squelch[band] + direction))
        df.set_squelch(auto_squelch_active() and -1 or st.squelch[band])
        redraw()
    end,

    -- §2.3.1(1) FREQUENCY opens the FRQ page and steps the selection there.
    freq = function(direction)
        if not st.power or st.booting or st.decode_open then return end
        if st.page ~= PAGE_FRQ then
            st.page = PAGE_FRQ
        else
            st.freq_index = math.max(1, math.min(#FREQS, st.freq_index + direction))
            st.cs_return_index = nil   -- manual tuning ends the 121.5 excursion
            df_audio.stop()
            push_state()               -- carries the new centre and span
        end
        redraw()
    end,

    -- §2.1(7) PAGE selects DF / FRQ and sets brightness while dimming.
    page = function(direction)
        if not st.power or st.booting then return end

        if st.dim_mode then
            st.brightness = math.max(5, math.min(100, st.brightness + direction * 5))
            enter_dim_mode()                         -- restart the 3 s fallback
            return
        end

        if st.decode_open then return end

        if st.page == PAGE_FRQ then
            st.freq_index = math.max(1, math.min(#FREQS, st.freq_index + direction))
            st.cs_return_index = nil
            df_audio.stop()
            push_state()
        else
            st.page = (direction > 0) and PAGE_FRQ or PAGE_DF
        end
        redraw()
    end,

    clr_press   = clr_press,   clr_release   = clr_release,
    store_press = store_press, store_release = store_release,
    rep_press   = rep_press,   rep_release   = rep_release,
})

-- ------------------------------------------------------------------ wiring ---

df.subscribe()
df.on_change(function()
    sync_audio()
    if st.power then redraw() end
end)

-- Keep the Last Signal and burst timers ticking between engine updates.
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
