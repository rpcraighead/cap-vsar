-- Technisonic TDFM-136B — CAP VHF-FM mission radio, Mission Observer station
-- CAP V-SAR training simulator, Implementation Plan v0.8 §6.7
--
-- This is the observer's radio, not the pilot's. Plan §6.7.3 selects Option B as
-- the primary design: the MO panel represents the aircraft's VHF-FM mission
-- radio and its audio routes to the Mumble mission net, not to PilotEdge. That
-- means this instrument deliberately does NOT drive sim/cockpit2/radios/* or
-- the ATC transmit datarefs — it publishes Air Manager variables that the local
-- Mumble agent consumes (plan §6.3.2).
--
-- Behaviour follows Technisonic Operating Instructions 08RE399A:
--   §1.1.1  front panel controls
--   §1.1.2  the two-line channel parameter display
--   §1.2.1  MN/GD selects the active channel for transmit and edit
--   §1.2.2  selecting a Main channel memory
--   §1.3.1  five command levels; L2/L3 time out after 5 s back to L1
--   §3.1    Level 1 command set
--
-- Scope note, from the CAP FM Radio Mission Observer Guide: programming the
-- radio is a wing communications function, not an observer task. Level 1
-- commands the observer actually uses are implemented; the restricted
-- maintenance levels (L4/L5) are deliberately absent.

-- Air Manager executes lib/*.lua before logic.lua. Libraries publish their
-- module tables globally because require() is unavailable in the AM 4.2 sandbox.
local disp  = tdfm_display
local panel = tdfm_panel

-- Chassis geometry, the artwork that goes with it and the keypad table all live
-- in lib/tdfm_panel.lua, measured off Figure 1-1. Nothing here repeats them.

-- ------------------------------------------------------------------- state ----

-- A CAP channel card. Real frequencies come from the wing communications plan,
-- which is access-restricted through eServices and deliberately not reproduced
-- here — these are placeholders inside the 136-174 MHz band the radio covers.
-- The instructor loads the exercise's channel card by editing this table.
-- Authentic CAP fleet plan (CAPR 100-1 / CAP V-SAR).
-- Channels 1-20 represent standard tactical, command, and interop assignments;
-- channels 21-200 provide standard user-programmable memory positions.
local memories = {
    { memory = 1,  name = "TAC 1",    freq_hz = 148150000, mode = "n", squelch_mode = "t", tone = 110.9, nac = 0 },
    { memory = 2,  name = "TAC 2",    freq_hz = 148125000, mode = "n", squelch_mode = "t", tone = 110.9, nac = 0 },
    { memory = 3,  name = "CC 1",     freq_hz = 150225000, mode = "D", squelch_mode = "g", tone = 0.0,   nac = 0x293 },
    { memory = 4,  name = "CC 2",     freq_hz = 149275000, mode = "D", squelch_mode = "g", tone = 0.0,   nac = 0x293 },
    { memory = 5,  name = "AIR 1",    freq_hz = 150537500, mode = "n", squelch_mode = "t", tone = 110.9, nac = 0 },
    { memory = 6,  name = "AIR 2",    freq_hz = 149537500, mode = "n", squelch_mode = "t", tone = 110.9, nac = 0 },
    { memory = 7,  name = "SAR 1",    freq_hz = 149925000, mode = "n", squelch_mode = "t", tone = 110.9, nac = 0 },
    { memory = 8,  name = "GUARD",    freq_hz = 148150000, mode = "n", squelch_mode = "t", tone = 110.9, nac = 0 },
    { memory = 9,  name = "GROUND 1", freq_hz = 148150000, mode = "n", squelch_mode = "x", tone = 0.0,   nac = 0 },
    { memory = 10, name = "GROUND 2", freq_hz = 148125000, mode = "n", squelch_mode = "x", tone = 0.0,   nac = 0 },
    { memory = 11, name = "BASE DIS", freq_hz = 150225000, mode = "D", squelch_mode = "g", tone = 0.0,   nac = 0x293 },
    { memory = 12, name = "LOGISTCS", freq_hz = 149275000, mode = "n", squelch_mode = "t", tone = 110.9, nac = 0 },
    { memory = 13, name = "AIR EVAC", freq_hz = 150537500, mode = "n", squelch_mode = "t", tone = 110.9, nac = 0 },
    { memory = 14, name = "SAR 2",    freq_hz = 149900000, mode = "n", squelch_mode = "t", tone = 110.9, nac = 0 },
    { memory = 15, name = "VFIRE 21", freq_hz = 154280000, mode = "n", squelch_mode = "t", tone = 156.7, nac = 0 },
    { memory = 16, name = "VTAC 11",  freq_hz = 151137500, mode = "n", squelch_mode = "t", tone = 156.7, nac = 0 },
    { memory = 17, name = "CALCORD",  freq_hz = 156075000, mode = "n", squelch_mode = "t", tone = 156.7, nac = 0 },
    { memory = 18, name = "NATL GRD", freq_hz = 149250000, mode = "D", squelch_mode = "g", tone = 0.0,   nac = 0x293 },
    { memory = 19, name = "CMD 1",    freq_hz = 148150000, mode = "n", squelch_mode = "t", tone = 110.9, nac = 0 },
    { memory = 20, name = "CMD 2",    freq_hz = 148225000, mode = "n", squelch_mode = "t", tone = 110.9, nac = 0 },
}

for i = 21, 200 do
    table.insert(memories, {
        memory = i,
        name = string.format("CHAN %03d", i),
        freq_hz = 148150000,
        mode = "n",
        squelch_mode = "x",
        tone = 0.0,
        nac = 0,
    })
end

local guards = {
    { guard = 1, name = "GUARD 1", freq_hz = 148150000, mode = "n", squelch_mode = "t", tone = 110.9, nac = 0 },
    { guard = 2, name = "GUARD 2", freq_hz = 148125000, mode = "n", squelch_mode = "t", tone = 110.9, nac = 0 },
}

local st = {
    power        = false,
    main_index   = 1,
    guard_index  = 1,       -- G1/G2 switch
    mn_gd        = "MN",    -- MN/GD switch: which channel is active
    power_hi     = false,   -- HI/LO switch: 10 W or 1 W
    main_volume  = 60,
    guard_volume = 40,
    squelch_defeat = false, -- Guard encoder press
    brightness   = 80,

    -- §1.3.1: command level, 1..3 for the operator. L2/L3 time out after 5 s.
    level        = 1,
    level_timer  = nil,

    -- Interactive command in progress, e.g. CHAN awaiting three digits.
    entry        = nil,     -- { kind = "CHAN", digits = "" }

    keypad_locked = false,
    scanning      = false,
    scan_timer    = nil,
    scan_hold_timer = nil,
    talk_around   = false,  -- L1 '*'
    home_memory   = 1,      -- L1 '#' toggles between home and current
    transmitting  = false,

    -- Receiver activity, driven by the mission net rather than the sim.
    main_rx      = false,
    guard_rx     = false,

    -- Set by the MO audio panel (GMA 1347). The radio is only usable if the
    -- observer has actually selected it there — which is the single most
    -- common real-world failure the CAP guide describes.
    audio_selected = false,
    mic_selected   = false,
    ptt_pressed    = false,
    tot_timer      = nil,
    tot_expired    = false,
}

local canvas_id, draw_display, led_main, led_guard, update_rx_lamps, stop_scan, handle_main_rx_change, start_scan_timer

local function active_main()  return memories[st.main_index] end
local function active_guard() return guards[st.guard_index] end

local function redraw()
    if canvas_id then canvas_draw(canvas_id, draw_display) end
end

-- ------------------------------------------------------- mission-net wiring --

-- Plan §6.3.2: "Air Manager radio panel writes the selected frequency to a
-- shared variable; a small local agent moves the Mumble client accordingly."
-- These are the variables that agent subscribes to.
local var_freq          = si_variable_create("cap_fm_frequency_hz", "INT", 0)
local var_channel       = si_variable_create("cap_fm_channel", "INT", 0)
local var_name          = si_variable_create("cap_fm_channel_name", "STRING", "")
local var_ptt           = si_variable_create("cap_fm_transmitting", "BOOL", false)
local var_power         = si_variable_create("cap_fm_power_on", "BOOL", false)
local var_hi            = si_variable_create("cap_fm_high_power", "BOOL", false)
local var_talk_ar       = si_variable_create("cap_fm_talk_around", "BOOL", false)
local var_in_ptt        = si_variable_create("cap_fm_ptt", "BOOL", false)
local var_main_rx       = si_variable_create("cap_fm_main_rx", "BOOL", false)
local var_guard_rx      = si_variable_create("cap_fm_guard_rx", "BOOL", false)
local var_tone          = si_variable_create("cap_fm_ctcss_tone", "FLOAT", 0.0)
local var_nac           = si_variable_create("cap_fm_p25_nac", "INT", 0)
local var_guard_freq    = si_variable_create("cap_fm_guard_frequency_hz", "INT", 0)
local var_guard_channel = si_variable_create("cap_fm_guard_channel", "INT", 0)
local var_guard_name    = si_variable_create("cap_fm_guard_channel_name", "STRING", "")
local var_guard_tone    = si_variable_create("cap_fm_guard_ctcss_tone", "FLOAT", 0.0)
local var_guard_nac     = si_variable_create("cap_fm_guard_p25_nac", "INT", 0)
local var_guard_vol     = si_variable_create("cap_fm_guard_volume", "FLOAT", 0.4)
local var_main_vol      = si_variable_create("cap_fm_main_volume", "FLOAT", 0.6)

--- Publish the current selection to the Mumble agent.
local function publish()
    si_variable_write(var_power, st.power)
    if not st.power then
        si_variable_write(var_ptt, false)
        return
    end
    local ch = (st.mn_gd == "MN") and active_main() or active_guard()
    si_variable_write(var_freq, ch.freq_hz)
    si_variable_write(var_channel, (st.mn_gd == "MN") and ch.memory or (100 + ch.guard))
    si_variable_write(var_name, ch.name)
    si_variable_write(var_hi, st.power_hi)
    si_variable_write(var_talk_ar, st.talk_around)
    si_variable_write(var_tone, ch.tone or 0.0)
    si_variable_write(var_nac, ch.nac or 0)
    si_variable_write(var_ptt, st.transmitting)

    -- Guard receiver is independent and operates simultaneously
    local g = active_guard()
    si_variable_write(var_guard_freq, g.freq_hz)
    si_variable_write(var_guard_channel, 100 + g.guard)
    si_variable_write(var_guard_name, g.name)
    si_variable_write(var_guard_tone, g.tone or 0.0)
    si_variable_write(var_guard_nac, g.nac or 0)
    si_variable_write(var_guard_vol, st.guard_volume / 100)
    si_variable_write(var_main_vol, st.main_volume / 100)
end

-- ------------------------------------------------------------ command levels --

--- §1.3.1: levels 2 and 3 drop back to level 1 after five seconds of inactivity.
local function arm_level_timeout()
    if st.level_timer then timer_stop(st.level_timer); st.level_timer = nil end
    if st.level > 1 then
        st.level_timer = timer_start(5000, 0, function()
            st.level = 1
            st.entry = nil
            st.level_timer = nil
            redraw()
        end)
    end
end

local function set_level(level)
    st.level = math.max(1, math.min(3, level))
    arm_level_timeout()
    redraw()
end

-- ---------------------------------------------------------------- commands ----

--- L1-1 CHAN: select the Main memory by direct three-digit entry (§3.1.1).
local function begin_channel_entry()
    if st.mn_gd ~= "MN" then return end     -- scope: Main only
    st.entry = { kind = "CHAN", digits = "" }
    redraw()
end

local function commit_channel_entry()
    local n = tonumber(st.entry.digits)
    st.entry = nil
    if n then
        for i, m in ipairs(memories) do
            if m.memory == n then
                st.main_index = i
                publish()
                break
            end
        end
    end
    redraw()
end

--- L1-4 / L1-6: scroll the Main memory down / up (§3.1).
local function scroll_memory(delta)
    if st.mn_gd ~= "MN" then return end
    st.main_index = ((st.main_index - 1 + delta) % #memories) + 1
    publish()
    redraw()
end

stop_scan = function()
    st.scanning = false
    if st.scan_timer then
        timer_stop(st.scan_timer)
        st.scan_timer = nil
    end
    if st.scan_hold_timer then
        timer_stop(st.scan_hold_timer)
        st.scan_hold_timer = nil
    end
    redraw()
end

local function scan_step()
    if not st.scanning or not st.power or st.main_rx or st.transmitting then
        return
    end
    local next_idx = (st.main_index % 20) + 1
    st.main_index = next_idx
    publish()
    redraw()
end

start_scan_timer = function()
    if st.scan_timer then timer_stop(st.scan_timer) end
    st.scan_timer = timer_start(250, 250, scan_step)
end

handle_main_rx_change = function(active)
    if not st.scanning then return end
    if active then
        if st.scan_timer then
            timer_stop(st.scan_timer)
            st.scan_timer = nil
        end
        if st.scan_hold_timer then
            timer_stop(st.scan_hold_timer)
            st.scan_hold_timer = nil
        end
    else
        if not st.scan_hold_timer and not st.scan_timer then
            st.scan_hold_timer = timer_start(2000, 0, function()
                st.scan_hold_timer = nil
                if st.scanning and not st.main_rx and not st.transmitting then
                    scan_step()
                    start_scan_timer()
                end
            end)
        end
    end
end

--- L1-5 SCAN: start or stop scanning (§3.1.5). The guide tells the observer to
--- use it only if the briefing calls for it, and it locks out most of the keypad.
local function toggle_scan()
    if not st.power or st.mn_gd ~= "MN" then return end
    if st.scanning then
        stop_scan()
    else
        st.scanning = true
        if not st.main_rx and not st.transmitting then
            start_scan_timer()
        end
        redraw()
    end
end

--- L1-# : toggle between the home memory and the current one (§3.1).
local function toggle_home()
    local current = active_main().memory
    if current == st.home_memory then return end
    for i, m in ipairs(memories) do
        if m.memory == st.home_memory then
            st.home_memory = current
            st.main_index = i
            publish()
            break
        end
    end
    redraw()
end

--- L1-* : talk around (§3.1). Transmits on the receive frequency, bypassing the
--- repeater — which is exactly the thing an observer reaches for when the
--- briefed repeater does not answer.
local function toggle_talk_around()
    st.talk_around = not st.talk_around
    publish()
    redraw()
end

--- L2-3: lock / unlock the keypad. §1.1 of the CAP guide: "If the keypad has
--- been locked, press and hold ESC for two seconds to unlock."
local function toggle_keypad_lock()
    st.keypad_locked = not st.keypad_locked
    st.level = 1
    redraw()
end

-- Level 1 key map (§3.1 / Table 3-1). Keys not listed are edit or configuration
-- commands the observer is told not to touch, so they are intentionally inert.
local LEVEL1 = {
    ["1"] = begin_channel_entry,
    ["2"] = function() st.brightness = math.min(100, st.brightness + 10); redraw() end,
    ["4"] = function() scroll_memory(-1) end,
    ["5"] = toggle_scan,
    ["6"] = function() scroll_memory(1) end,
    ["8"] = function() st.brightness = math.max(10, st.brightness - 10); redraw() end,
    ["#"] = toggle_home,
    ["*"] = toggle_talk_around,
}

local LEVEL2 = {
    ["3"] = toggle_keypad_lock,
}

--- Route a keypress through the command-level machine.
local function press_key(key)
    if not st.power then return end

    -- An interactive entry swallows digits until it is accepted or abandoned.
    if st.entry then
        if key == "#" then
            commit_channel_entry()
        elseif key == "*" then
            st.entry = nil
            redraw()
        elseif key:match("%d") then
            st.entry.digits = (st.entry.digits .. key):sub(-3)
            if #st.entry.digits == 3 then
                commit_channel_entry()
            else
                redraw()
            end
        end
        return
    end

    if st.keypad_locked then
        -- Only the ESC hold path unlocks; handled by the button's release timer.
        return
    end

    if key == "0" then
        set_level(st.level + 1)                 -- step up through levels
        return
    end
    if key == "*" and st.level > 1 then
        set_level(st.level - 1)                 -- step down
        return
    end

    local map = (st.level == 1) and LEVEL1 or (st.level == 2) and LEVEL2 or nil
    local fn = map and map[key]
    if fn then
        fn()
        -- §1.3.1: after a L2/L3 command the timer resets rather than dropping
        -- straight back to level 1.
        arm_level_timeout()
    end
end

-- ------------------------------------------------------------- display draw --

draw_display = function()
    local ctx = lcd.context(panel.DISP_SCALE, 0, 0)

    -- Column 4 of the Main row shows scan state; on the Guard row it shows the
    -- command level, or the lock icon when the keypad is locked (§1.1.2(5)(6)).
    local main_extra  = st.scanning and "S" or " "
    local guard_extra = st.keypad_locked and "*"
                        or (st.level > 1 and tostring(st.level) or " ")

    local main = active_main()
    local guard = active_guard()

    local main_line = disp.compose({
        memory = main.memory, name = main.name, freq_hz = main.freq_hz,
        mode = main.mode, squelch_mode = main.squelch_mode,
        transmitting = st.transmitting and st.mn_gd == "MN",
    }, true, main_extra)

    local guard_line = disp.compose({
        guard = guard.guard, name = guard.name, freq_hz = guard.freq_hz,
        mode = guard.mode, squelch_mode = guard.squelch_mode,
        transmitting = st.transmitting and st.mn_gd == "GD",
    }, false, guard_extra)

    -- A channel entry in progress replaces the memory number with the digits
    -- being typed, cursor style (§3.1.1).
    if st.entry and st.entry.kind == "CHAN" then
        local shown = (st.entry.digits .. "___"):sub(1, 3)
        main_line = shown .. main_line:sub(4)
    end

    if st.tot_expired then
        if st.mn_gd == "MN" then
            main_line = string.format("%03d %-20s", main.memory or 0, "*** TIME OUT ***"):sub(1, 24)
        else
            guard_line = string.format("GD%d %-20s", guard.guard or 1, "*** TIME OUT ***"):sub(1, 24)
        end
    end

    disp.draw(ctx, { main_line, guard_line }, st.power)
end

-- ------------------------------------------------------------- faceplate -----

-- §1.1.1 front panel: two rotary encoders, three toggles, a 12-key keypad, two
-- squelch LEDs and the data port. The housing, screws, display recess and every
-- silk-screened legend are in resources/faceplate.png; each keypad cap carries
-- its own printed legend because the cap moves when pressed. Regenerate the lot
-- with `python3 scripts/make_panel_artwork.py`, which reads the geometry out of
-- lib/tdfm_panel.lua so the art and these hit regions cannot drift apart.

-- Add order is layer order: faceplate, then the display, then the LEDs, then
-- every control on top.
panel.add_faceplate()

canvas_id = canvas_add(panel.DISP_X, panel.DISP_Y, panel.DISP_W, panel.DISP_H,
                       draw_display)

-- §1.1.1(1): squelch LEDs, top = Main, bottom = Guard. Figure 1-1 puts them
-- inside the display bezel, one at the start of each line. The lit image sits
-- over the dark one and is shown while that channel is receiving.
local led_lit = {}
for i, p in ipairs(panel.LEDS) do
    local d = panel.LED_R * 2
    local lx, ly = p[1] - panel.LED_R, p[2] - panel.LED_R
    img_add("led_off.png", lx, ly, d, d)
    led_lit[i] = img_add("led_on.png", lx, ly, d, d)
    visible(led_lit[i], false)
end
led_main, led_guard = led_lit[1], led_lit[2]

local function power_on()
    if st.power then return end
    st.power = true
    update_rx_lamps()
    publish()
    redraw()
end

local function power_off()
    if not st.power then return end
    st.power = false
    st.level = 1
    st.entry = nil
    stop_scan()
    st.tot_expired = false
    if st.tot_timer then
        timer_stop(st.tot_timer)
        st.tot_timer = nil
    end
    update_rx_lamps()
    publish()
    redraw()
end

local MIN_BUS_VOLTS = 10.0
local avionics_switch_on = false
local bus_volts = 0.0
local bus_powered = false
-- Mission-kit gating, independent of the airframe bus — see
-- docs/DATAREF_CONTRACT.md Part 6. Both default true so a panel without the
-- master switch / CB panel instruments behaves exactly as before.
local mission_master_on = true
local mission_cb_in = true

local function update_bus_power()
    local powered = avionics_switch_on and (bus_volts >= MIN_BUS_VOLTS)
        and mission_master_on and mission_cb_in
    if powered == bus_powered then return end
    bus_powered = powered
    if bus_powered then
        power_on()
    else
        power_off()
    end
end

-- ---------------------------------------------------------------- controls ---

-- §1.1.1(3): Main encoder — volume, press for ON, press and hold for OFF.
--
-- dial_add has one callback (the turn). The push is a transparent button over
-- the knob centre, added after the dial so it is on top: knob_push() in
-- lib/knob_push.lua, as the stock G1000 does it.
local main_hold_timer
dial_add("knob.png", panel.MAIN_ENC.x, panel.MAIN_ENC.y,
         panel.MAIN_ENC.w, panel.MAIN_ENC.h, 20,
    function(direction)
        if not st.power then return end
        st.main_volume = math.max(0, math.min(100, st.main_volume + direction * 2))
        si_variable_write(var_main_vol, st.main_volume / 100)
        redraw()
    end)
knob_push(panel.MAIN_ENC,
    function()  -- pressed
        if not bus_powered then return end
        if not st.power then
            power_on()
        else
            -- Hold to switch off.
            if main_hold_timer then timer_stop(main_hold_timer) end
            main_hold_timer = timer_start(1500, 0, function()
                main_hold_timer = nil
                power_off()
            end)
        end
    end,
    function()  -- released
        if main_hold_timer then timer_stop(main_hold_timer); main_hold_timer = nil end
    end)

-- §1.1.1(4): Guard encoder — volume, press for squelch defeat.
dial_add("knob.png", panel.GUARD_ENC.x, panel.GUARD_ENC.y,
         panel.GUARD_ENC.w, panel.GUARD_ENC.h, 20,
    function(direction)
        if not st.power then return end
        st.guard_volume = math.max(0, math.min(100, st.guard_volume + direction * 2))
        si_variable_write(var_guard_vol, st.guard_volume / 100)
        redraw()
    end)
knob_push(panel.GUARD_ENC,
    function()
        if not st.power then return end
        st.squelch_defeat = true
        redraw()
    end,
    function()
        st.squelch_defeat = false
        redraw()
    end)

-- §1.1.1(6): MN/GD toggle — selects the active channel for transmit and edit.
local function requested_switch_position(position, direction)
    return math.max(0, math.min(1, position + direction))
end

local mn_gd_switch
mn_gd_switch = switch_add("toggle_up.png", "toggle_down.png",
           panel.TOGGLE.mn_gd.x, panel.TOGGLE.mn_gd.y,
           panel.TOGGLE.mn_gd.w, panel.TOGGLE.mn_gd.h,
    function(position, direction)
        local new_position = requested_switch_position(position, direction)
        switch_set_position(mn_gd_switch, new_position)
        st.mn_gd = (new_position == 0) and "MN" or "GD"
        if st.mn_gd == "GD" and st.scanning then
            stop_scan()
        end
        publish()
        redraw()
    end)

-- §1.1.1(7): Guard 1 / Guard 2 toggle.
local guard_switch
guard_switch = switch_add("toggle_up.png", "toggle_down.png",
           panel.TOGGLE.g1_g2.x, panel.TOGGLE.g1_g2.y,
           panel.TOGGLE.g1_g2.w, panel.TOGGLE.g1_g2.h,
    function(position, direction)
        local new_position = requested_switch_position(position, direction)
        switch_set_position(guard_switch, new_position)
        st.guard_index = new_position + 1
        publish()
        redraw()
    end)

-- §1.1.1(8): transmit power, high (10 W) or low (1 W).
local power_switch
power_switch = switch_add("toggle_up.png", "toggle_down.png",
           panel.TOGGLE.hi_lo.x, panel.TOGGLE.hi_lo.y,
           panel.TOGGLE.hi_lo.w, panel.TOGGLE.hi_lo.h,
    function(position, direction)
        local new_position = requested_switch_position(position, direction)
        switch_set_position(power_switch, new_position)
        st.power_hi = (new_position == 0)
        publish()
        redraw()
    end)
switch_set_position(power_switch, 1) -- Start in LO, matching st.power_hi=false.

-- §1.1.1(9): the twelve-key keypad.
local esc_hold_timer
for i, k in ipairs(panel.KEYPAD) do
    local x, y, w, h = panel.key_rect(i)
    local key = k.id
    button_add(panel.key_image(k, false), panel.key_image(k, true), x, y, w, h,
        function()
            if key == "*" then
                -- Hold ESC for two seconds to unlock the keypad.
                esc_hold_timer = timer_start(2000, 0, function()
                    if st.keypad_locked then
                        st.keypad_locked = false
                        redraw()
                    end
                    esc_hold_timer = nil
                end)
            end
            press_key(key)
        end,
        function()
            if esc_hold_timer then timer_stop(esc_hold_timer); esc_hold_timer = nil end
        end)
end

-- ------------------------------------------------------------------ wiring ---

-- Receive activity comes from the mission net agent, which knows who is talking
-- on the channel this radio is sitting on. Until that agent exists these stay
-- false and the LEDs remain dark.
--- §1.1.1(1): "LED channel squelch indicators - light on signal received
--- (top=Main, bottom=Guard)." They are on the radio, not on the audio panel, so
--- they report what the receiver is doing regardless of how the audio is routed.
---
--- That distinction is the whole diagnostic: a lit squelch LED with silence in
--- the headset says the radio is hearing the call and the audio panel is not
--- passing it, which is the CAP guide's "nearly every 'the radio is broken'
--- report in flight is an audio panel selection". Blanking the LEDs when COM3
--- audio is deselected, as an earlier build did, hides exactly the evidence the
--- trainee is supposed to find.
update_rx_lamps = function()
    if led_main and led_guard then
        visible(led_main,  st.power and st.main_rx)
        visible(led_guard, st.power and st.guard_rx)
    end
end

si_variable_subscribe("cap_fm_main_rx", "BOOL", function(v)
    st.main_rx = v and true or false
    update_rx_lamps()
    if handle_main_rx_change then
        handle_main_rx_change(st.main_rx)
    end
end)

si_variable_subscribe("cap_fm_guard_rx", "BOOL", function(v)
    -- §1.2.1: Guard is monitored continuously so base can reach the aircraft
    -- regardless of what Main is working.
    st.guard_rx = v and true or false
    update_rx_lamps()
end)

-- The observer's PTT. Plan §6.3: the mission net has its own push-to-talk key,
-- separate from the ATC network's.
--
-- Transmitting takes three things at once: the radio powered, COM3 MIC selected
-- on the audio panel, and the PTT pressed. Getting two of the three is the
-- classic "they can hear me but I can't reach them" trap, so the interlock is
-- modelled rather than assumed.
local function update_transmit()
    local tx = st.power and st.mic_selected and st.ptt_pressed and not st.tot_expired
    if tx ~= st.transmitting then
        st.transmitting = tx
        if tx then
            if st.scanning and st.scan_timer then
                timer_stop(st.scan_timer)
                st.scan_timer = nil
            end
            if st.tot_timer then timer_stop(st.tot_timer) end
            st.tot_timer = timer_start(60000, 0, function()
                st.tot_timer = nil
                st.tot_expired = true
                st.transmitting = false
                publish()
                redraw()
            end)
        else
            if st.tot_timer then
                timer_stop(st.tot_timer)
                st.tot_timer = nil
            end
            if st.scanning and not st.main_rx and not st.scan_timer and not st.scan_hold_timer then
                if start_scan_timer then start_scan_timer() end
            end
        end
        publish()
        redraw()
    end
end

-- PTT arrives on the cap_fm_ptt si_variable only (the mission-net PTT device or
-- the console). X-Plane has no copilot PTT dataref and no copilot PTT command:
-- DataRefs.txt has nothing containing "ptt" and Commands.txt only the pilot's
-- sim/operation/contact_atc_ptt, which is the ATC network key and must not key
-- the mission radio. The COM3 MIC interlock below still applies.
local manual_ptt = false

local function sync_ptt_state()
    local pressed = manual_ptt
    if pressed ~= st.ptt_pressed then
        st.ptt_pressed = pressed
        if not pressed then
            local was_expired = st.tot_expired
            st.tot_expired = false
            if st.tot_timer then
                timer_stop(st.tot_timer)
                st.tot_timer = nil
            end
            if was_expired then
                redraw()
            end
        end
        update_transmit()
    end
end

si_variable_subscribe("cap_fm_ptt", "BOOL", function(v)
    manual_ptt = v and true or false
    sync_ptt_state()
end)

-- COM3 audio / COM3 MIC selection from the GMA 1347 audio panel.
si_variable_subscribe("cap_fm_audio_selected", "BOOL", function(v)
    -- With COM3 audio deselected the observer hears nothing — but the radio is
    -- still receiving and its squelch LEDs still light. See update_rx_lamps().
    st.audio_selected = v and true or false
    redraw()
end)

si_variable_subscribe("cap_fm_mic_selected", "BOOL", function(v)
    st.mic_selected = v and true or false
    update_transmit()
    redraw()
end)

publish()
redraw()

xpl_dataref_subscribe("sim/cockpit2/switches/avionics_power_on", "INT", function(on)
    avionics_switch_on = (on or 0) ~= 0
    update_bus_power()
end)

xpl_dataref_subscribe("sim/cockpit2/electrical/bus_volts", "FLOAT[6]", function(val)
    bus_volts = type(val) == "table" and (val[1] or 0.0) or (type(val) == "number" and val or 0.0)
    update_bus_power()
end)

si_variable_subscribe("cap_mission_master_on", "BOOL", function(v)
    mission_master_on = v and true or false
    update_bus_power()
end)

si_variable_subscribe("cap_mission_cb_fm_in", "BOOL", function(v)
    mission_cb_in = v and true or false
    update_bus_power()
end)
