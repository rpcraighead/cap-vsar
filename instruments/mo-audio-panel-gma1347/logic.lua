-- Garmin GMA 1347 — Mission Observer audio panel
-- CAP V-SAR training simulator, Implementation Plan v0.8 §6.7
--
-- This is the MO's audio panel, so it drives the *copilot* side of X-Plane's
-- audio system, not the pilot's. The observer sits right seat; the pilot's
-- panel is a separate thing and this instrument must not fight it.
--
-- Layout and behaviour follow the Garmin G1000 Audio Panel Pilot's Guide
-- 190-00378-01 Rev. A (the C182T copy hosted by CAP TX-435, in docs/):
--   Fig 6A.2.1   front panel controls          (PDF page 5)
--   §ON/OFF, POWER-UP SETTINGS AND FAIL-SAFE   self-test, restore, fail-safe
--   §TRANSCEIVER KEYS                          MIC keys are exclusive
--   §SPLIT COM                                 COM 1/2, and its cost to the MO
--   §MARKER BEACON RECEIVER                    MKR/MUTE three-state behaviour
--   §INTERCOM SYSTEM (ICS) ISOLATION           Table 6A.3.2 state machine
--
-- Why this instrument matters for the exercise, from the CAP FM Radio Mission
-- Observer Guide: "Nearly every 'the radio is broken' report in flight is an
-- audio panel selection", and "Hearing the ground team perfectly and getting no
-- reply is almost always a mic-selection problem, not a radio problem." The
-- panel makes the audio/mic distinction visible, which is the whole point.

-- Air Manager executes lib/*.lua before logic.lua; require() is unavailable in
-- the AM 4.2 sandbox, so this table is published by lib/gma_panel.lua.
local panel = gma_panel

-- Chassis geometry, the key table and the artwork that goes with them live in
-- lib/gma_panel.lua, measured off Figure 6A.2.1. §6A.2 gives the panel as
-- 1.3 x 7.70 inches, so it is a tall narrow strip; the annunciator triangles
-- are white when lit, and the volume/squelch control is a concentric pair.

local st = {
    powered = false,        -- follows the avionics master
    self_test = false,      -- ~2 s lamp test on power-up

    mic = "com1",           -- exclusive: com1 / com2 / com3

    audio = {
        com1 = true,  com2 = false, com3 = false, tel = false,
        nav1 = false, nav2 = false, dme = false,  adf = false,
        aux  = false, spkr = false,
    },

    split   = false,        -- COM 1/2
    pa      = false,
    hi_sens = false,
    man_sq  = false,

    -- MKR/MUTE is three-state (§MARKER BEACON RECEIVER): off, on, or on but
    -- momentarily muted while a tone is being received.
    mkr        = false,
    mkr_muted  = false,

    -- ICS isolation: ALL / PILOT / COPILOT / CREW (Table 6A.3.2)
    ics = "ALL",

    -- §6A.2: the small knob is the pilot channel and the large knob the
    -- copilot/passenger channels, so they carry their own levels.
    volume  = { pilot = 0.7, crew = 0.7 },
    squelch = { pilot = 0.5, crew = 0.5 },
    vol_mode = "VOL",       -- whether the rings adjust volume or squelch

    play_flash = false,

    -- §Clearance Recorder: digital recording of up to 2.5 min of incoming audio
    recorder = {
        blocks = {},      -- list of { com = "com1"|"com2"|"com3", duration_ms = ..., text = ... }
        max_blocks = 16,
        max_time_ms = 150000, -- 2.5 minutes
        current_idx = 0,
        active_rx = {
            com1 = false,
            com2 = false,
            com3 = false,
        },
    },
    playback_active = false,
}

local test_timer, play_timer

-- Defined once the annunciator images exist, down in the wiring section.
local refresh = function() end

-- ---------------------------------------------------------- mission-net link --

-- COM3 is the CAP VHF-FM mission radio. X-Plane has no third COM, so COM3
-- audio and mic selection go to the same Air Manager variables the TDFM-136B
-- instrument and the local Mumble agent use (plan §6.3.2). This is the
-- audio-panel half of the split the CAP guide describes: selecting COM3 audio
-- lets you *listen*, selecting COM3 MIC is what lets you *talk*.
local var_fm_audio        = si_variable_create("cap_fm_audio_selected", "BOOL", false)
local var_fm_mic          = si_variable_create("cap_fm_mic_selected",   "BOOL", false)
local var_ics             = si_variable_create("cap_ics_isolation",     "STRING", "ALL")
local var_ics_pilot_iso   = si_variable_create("cap_ics_pilot_isolated",   "BOOL", false)
local var_ics_copilot_iso = si_variable_create("cap_ics_copilot_isolated", "BOOL", false)
local var_ics_crew_iso    = si_variable_create("cap_ics_crew_isolated",    "BOOL", false)
local var_split_com       = si_variable_create("cap_split_com_active",     "BOOL", false)
local var_rec_playing     = si_variable_create("cap_recorder_playing",     "BOOL", false)
local var_rec_block       = si_variable_create("cap_recorder_block",       "INT", 0)
local var_rec_count       = si_variable_create("cap_recorder_count",       "INT", 0)
local var_rec_text        = si_variable_create("cap_recorder_text",        "STRING", "")

local function publish_ics()
    si_variable_write(var_ics, st.ics)
    si_variable_write(var_ics_pilot_iso,   st.ics == "PILOT")
    si_variable_write(var_ics_copilot_iso, st.ics == "PILOT" or st.ics == "COPILOT")
    si_variable_write(var_ics_crew_iso,    st.ics == "CREW")
end

-- ------------------------------------------------------------ X-Plane wiring --

-- Everything here targets the copilot side. Verified present in
-- X-Plane 12/Resources/plugins/DataRefs.txt and Commands.txt.
local DR = {
    com1 = "sim/cockpit2/radios/actuators/audio_selection_com1_copilot",
    com2 = "sim/cockpit2/radios/actuators/audio_selection_com2_copilot",
    nav1 = "sim/cockpit2/radios/actuators/audio_selection_nav1_copilot",
    nav2 = "sim/cockpit2/radios/actuators/audio_selection_nav2_copilot",
    adf  = "sim/cockpit2/radios/actuators/audio_selection_adf1_copilot",
    dme  = "sim/cockpit2/radios/actuators/audio_selection_dme1_copilot",
}

local CMD_MIC = {
    com1 = "sim/audio_panel_copilot/transmit_audio_com1",
    com2 = "sim/audio_panel_copilot/transmit_audio_com2",
}

--- Under split COM the copilot is restricted to COM2 (§SPLIT COM: "the copilot
--- is only able to monitor/hear COM2"). That costs the MO the FM mission net,
--- which is exactly the trade the crew has to understand before using it.
local function effective_audio(id)
    if st.split then return id == "com2" end
    return st.audio[id] == true
end

local function push_audio()
    if not st.powered then return end
    for id, dataref in pairs(DR) do
        xpl_dataref_write(dataref, "INT", effective_audio(id) and 1 or 0)
    end

    -- The active COM audio is always heard whether or not its audio key is lit,
    -- so COM3 MIC brings the FM net with it (CAP guide §2, G1000 aircraft).
    local fm_audio = effective_audio("com3") or (st.mic == "com3")
    si_variable_write(var_fm_audio, st.split and false or fm_audio)
    si_variable_write(var_fm_mic,   st.split and false or (st.mic == "com3"))
    si_variable_write(var_split_com, st.split)
end

local function push_mic()
    if not st.powered then return end
    if st.mic == "com1" or st.mic == "com2" then
        xpl_command(CMD_MIC[st.mic])
    end
    -- COM3 has no X-Plane transceiver; the mission-net variables carry it.
    push_audio()
end

-- ------------------------------------------------------------------ actions --

--- MIC keys are exclusive and, uniquely, pressing an already-selected MIC key
--- does not deselect it (§Deselecting Keys).
local function select_mic(which)
    if st.split then
        -- In split COM the copilot's microphone is fixed to COM2.
        return
    end
    st.mic = which
    -- §TRANSCEIVERS: "COM audio can be selected by either pressing the desired
    -- COM key or by pressing the corresponding COM MIC key. If selected in this
    -- manner, the audio source remains selected independently of the active
    -- microphone source selection." So the matching audio key latches on, and
    -- stays on after the microphone moves elsewhere.
    st.audio[which] = true
    push_mic()
end

local function toggle_audio(id)
    st.audio[id] = not st.audio[id]
    push_audio()
end

--- Table 6A.3.2 ICS isolation transitions, verbatim.
local ICS_PILOT = { PILOT = "ALL",  COPILOT = "CREW", CREW = "COPILOT", ALL = "PILOT"   }
local ICS_COPLT = { PILOT = "CREW", COPILOT = "ALL",  CREW = "PILOT",   ALL = "COPILOT" }

local function press_ics(key)
    st.ics = (key == "pilot") and ICS_PILOT[st.ics] or ICS_COPLT[st.ics]
    publish_ics()
end

--- MKR/MUTE, §MARKER BEACON RECEIVER: selected -> (tone received) press mutes
--- without changing the annunciator -> pressing again while muted deactivates.
local function press_mkr()
    if not st.mkr then
        st.mkr, st.mkr_muted = true, false
    elseif not st.mkr_muted then
        st.mkr_muted = true          -- annunciator stays lit
    else
        st.mkr, st.mkr_muted = false, false
    end
    xpl_command(st.mkr and "sim/audio_panel_copilot/monitor_audio_mkr_on"
                       or  "sim/audio_panel_copilot/monitor_audio_mkr_off")
end

local function press_split()
    st.split = not st.split
    if st.split then
        -- §SPLIT COM: COM1 goes to the pilot, COM2 to the copilot.
        st.mic = "com2"
        xpl_command(CMD_MIC.com2)
    end
    push_audio()
end

local function record_transmission(com_id, duration_ms, text)
    if not st.powered then return end
    local dur = math.max(500, math.min(30000, duration_ms or 1500))
    table.insert(st.recorder.blocks, {
        com = com_id,
        duration_ms = dur,
        text = text or string.format("%s transmission (%d ms)", string.upper(tostring(com_id)), dur),
    })
    while #st.recorder.blocks > st.recorder.max_blocks do
        table.remove(st.recorder.blocks, 1)
    end
    local total_dur = 0
    for _, b in ipairs(st.recorder.blocks) do total_dur = total_dur + b.duration_ms end
    while #st.recorder.blocks > 1 and total_dur > st.recorder.max_time_ms do
        total_dur = total_dur - st.recorder.blocks[1].duration_ms
        table.remove(st.recorder.blocks, 1)
    end
    si_variable_write(var_rec_count, #st.recorder.blocks)
end

local function stop_playback()
    if play_timer then
        timer_stop(play_timer)
        play_timer = nil
    end
    st.play_flash = false
    st.playback_active = false
    st.recorder.current_idx = 0
    si_variable_write(var_rec_playing, false)
    si_variable_write(var_rec_block, 0)
    refresh()
end

--- PLAY is the digital clearance recorder playback (§Clearance Recorder).
local function press_play()
    if not st.powered or st.self_test then return end
    local count = #st.recorder.blocks
    if count == 0 then
        -- Empty buffer: 400 ms flash
        st.play_flash = true
        refresh()
        if play_timer then timer_stop(play_timer) end
        play_timer = timer_start(400, 0, function()
            st.play_flash = false
            play_timer = nil
            refresh()
        end)
        return
    end

    if st.playback_active then
        -- Step back to previous recorded block (reverse chronological)
        if st.recorder.current_idx > 1 then
            st.recorder.current_idx = st.recorder.current_idx - 1
        else
            st.recorder.current_idx = count
        end
    else
        st.recorder.current_idx = count
        st.playback_active = true
    end

    local block = st.recorder.blocks[st.recorder.current_idx]
    local dur = (block and block.duration_ms) or 1500
    st.play_flash = true
    si_variable_write(var_rec_playing, true)
    si_variable_write(var_rec_block, st.recorder.current_idx)
    si_variable_write(var_rec_text, (block and block.text) or ("COM" .. tostring(block and block.com or 1)))
    refresh()

    if play_timer then timer_stop(play_timer) end
    play_timer = timer_start(dur, 0, function()
        stop_playback()
    end)
end

-- Dispatch table for every key press.
local ACTION = {
    com1_mic = function() select_mic("com1") end,
    com2_mic = function() select_mic("com2") end,
    com3_mic = function() select_mic("com3") end,
    com1     = function() toggle_audio("com1") end,
    com2     = function() toggle_audio("com2") end,
    com3     = function() toggle_audio("com3") end,
    tel      = function() toggle_audio("tel")  end,
    spkr     = function() toggle_audio("spkr") end,
    nav1     = function() toggle_audio("nav1") end,
    nav2     = function() toggle_audio("nav2") end,
    dme      = function() toggle_audio("dme")  end,
    adf      = function() toggle_audio("adf")  end,
    aux      = function() toggle_audio("aux")  end,
    split    = press_split,
    mkr      = press_mkr,
    play     = press_play,
    pa       = function() st.pa = not st.pa end,
    hi_sens  = function() st.hi_sens = not st.hi_sens end,
    man_sq   = function()
        st.man_sq = not st.man_sq
        -- §VOLUME/SQUELCH CONTROL: with auto-squelch active there is no squelch
        -- to set, so the selection returns to volume.
        if not st.man_sq then st.vol_mode = "VOL" end
    end,
    pilot    = function() press_ics("pilot") end,
    coplt    = function() press_ics("coplt") end,
}

--- Is a key's annunciator lit right now?
local function annunciated(id)
    if st.self_test then return true end        -- power-up lamp test
    if not st.powered then return false end

    -- §SPLIT COM: "During split COM operation, the COM1, COM1 MIC, COM2 and
    -- COM2 MIC keys are annunciated and thus active." All four, not just the
    -- copilot's pair. The annunciators report the panel's state; this seat's
    -- restriction to COM2 audio lives in effective_audio(), not here.
    if st.split and (id == "com1" or id == "com1_mic"
                     or id == "com2" or id == "com2_mic") then
        return true
    end

    if id == "com1_mic" then return st.mic == "com1" end
    if id == "com2_mic" then return st.mic == "com2" end
    if id == "com3_mic" then return st.mic == "com3" and not st.split end
    if id == "split"    then return st.split end
    if id == "mkr"      then return st.mkr end   -- stays lit even while muted
    if id == "pa"       then return st.pa end
    if id == "hi_sens"  then return st.hi_sens end
    if id == "man_sq"   then return st.man_sq end
    if id == "play"     then return st.play_flash end
    if id == "pilot"    then return st.ics == "PILOT" or st.ics == "CREW" end
    if id == "coplt"    then return st.ics == "COPILOT" or st.ics == "CREW" end

    return st.audio[id] == true
end

-- ------------------------------------------------------------------ drawing --
--
-- There is nothing to draw. The housing, the two group outlines and every
-- silk-screened legend are baked into resources/faceplate.png; each key is its
-- own image pair because the cap carries its legend and moves when pressed; and
-- each annunciator is a lit/unlit image pair switched with visible(). That is
-- how the real panel works — it has no display, only lamps — so the instrument
-- has no canvas at all.
--
-- The first draft drew an invented status line across the top carrying the ICS
-- mode and a split-COM warning. It is gone: Table 6A.3.2's states are already
-- readable from the PILOT and COPLT annunciators (neither lit = ALL, PILOT lit
-- = PILOT, COPLT lit = COPILOT, both lit = CREW) and split COM is readable from
-- the COM 1/2 annunciator. Teaching the crew to read the lamps is the point.

-- ------------------------------------------------------------------- wiring --

-- Add order is layer order: faceplate, then the annunciators, then the keys.
panel.add_faceplate()

-- §VOLUME/SQUELCH CONTROL: the selected function is illuminated beside the
-- concentric knob. The faceplate carries the dim legends; these white overlays
-- provide the live VOL/SQ indication that the static artwork cannot express.
local mode_style = "font:roboto_bold.ttf; size:18; color:#ffffff; halign:center; valign:center;"
local mode_vol = txt_add("VOL", mode_style,
                         panel.MODE_VOL.x, panel.MODE_VOL.y,
                         panel.MODE_VOL.w, panel.MODE_VOL.h)
local mode_sq = txt_add("SQ", mode_style,
                        panel.MODE_SQ.x, panel.MODE_SQ.y,
                        panel.MODE_SQ.w, panel.MODE_SQ.h)

local ann_lit = {}
for _, k in ipairs(panel.KEYS) do
    local ax, ay, aw, ah = panel.ann_rect(k)
    img_add("ann_off.png", ax, ay, aw, ah)
    ann_lit[k.id] = img_add("ann_on.png", ax, ay, aw, ah)
end

--- Show the lamps the current state calls for. This is what refresh() means on
--- a panel with no display.
function refresh()
    for _, k in ipairs(panel.KEYS) do
        visible(ann_lit[k.id], annunciated(k.id))
    end
    visible(mode_vol, st.powered and (st.self_test or st.vol_mode == "VOL"))
    visible(mode_sq, st.powered and
                     (st.self_test or (st.man_sq and st.vol_mode == "SQ")))
end

for _, k in ipairs(panel.KEYS) do
    local x, y, w, h = panel.key_rect(k)
    local action = ACTION[k.id]
    button_add(panel.key_image(k, false), panel.key_image(k, true), x, y, w, h,
        function()
            if not st.powered or st.self_test then return end
            if k.id ~= "play" and st.playback_active then
                stop_playback()
            end
            if action then action() end
            refresh()
        end)
end

-- §6A.2: "The small knob adjusts the volume/squelch level associated with the
-- pilot channel, while the large knob adjusts the volume/squelch level
-- associated with the copilot/passenger channels." So this is a concentric
-- pair, not one dial. The MO sits right seat, so the outer ring is the one that
-- moves what the observer hears; the inner is modelled for completeness and
-- because reaching for the wrong ring is a real cockpit error.
--
-- Pressing the knob swaps between volume and squelch, which is the closest a
-- mouse gets to pull-for-squelch.
local function adjust(direction, pilot_side)
    if not st.powered then return end
    local who = pilot_side and "pilot" or "crew"
    local store = (st.vol_mode == "VOL") and st.volume or st.squelch
    store[who] = math.max(0, math.min(1, store[who] + direction * 0.02))
    -- Only the copilot/passenger ring drives this station's audio; the pilot
    -- ring is modelled so that reaching for the wrong one has the real effect,
    -- which is that nothing the observer hears changes.
    if st.vol_mode == "VOL" and not pilot_side then
        xpl_dataref_write("sim/operation/sound/radio_copilot_audio_panel_volume_ratio",
                          "FLOAT", st.volume.crew)
    end
end

--- §VOLUME/SQUELCH CONTROL: "When the GMA 1347 MAN SQ key is selected, pressing
--- the VOL/SQ knob toggles between volume and squelch ... NOTE: When the MAN SQ
--- key is deselected (i.e., auto-squelch is active), pressing the VOL/SQ knob
--- has no effect on the VOL/SQ selection state."
local function swap_mode()
    if not st.powered or not st.man_sq then return end
    st.vol_mode = (st.vol_mode == "VOL") and "SQ" or "VOL"
    refresh()
end

dial_add("knob_outer.png", panel.KNOB_OUTER.x, panel.KNOB_OUTER.y,
         panel.KNOB_OUTER.w, panel.KNOB_OUTER.h, 20,
         function(direction) adjust(direction, false) end)

-- Added after the outer ring so the inner knob takes the turns inside it.
dial_add("knob_inner.png", panel.KNOB_INNER.x, panel.KNOB_INNER.y,
         panel.KNOB_INNER.w, panel.KNOB_INNER.h, 20,
         function(direction) adjust(direction, true) end)

-- The two rings share a centre, and the VOL/SQ push is the centre of the pair.
-- dial_add has no press callback, so the push is a transparent button over that
-- centre, added last so it is on top (lib/knob_push.lua, as the stock G1000).
knob_push(panel.KNOB_INNER, swap_mode)

-- DISPLAY BACKUP: reversionary mode. The CAP guide is blunt about this one --
-- "the red button on the audio panel is display reversion, not a radio control.
-- Leave it alone unless the pilot calls for it" -- so it is present and it
-- works, but it does nothing to the radios.
button_add("backup.png", "backup_pressed.png",
           panel.BACKUP.x, panel.BACKUP.y, panel.BACKUP.w, panel.BACKUP.h,
    function()
    if not st.powered then return end
    xpl_command("sim/GPS/G1000_display_reversion")
end)

-- ----------------------------------------------------------------- power-up --

--- §Power-up Settings: a ~2 s lamp test, then the previous selections are
--- restored. Air Manager's persistence gives us the "restored" half for free.
local function run_self_test()
    st.self_test = true
    refresh()
    if test_timer then timer_stop(test_timer) end
    test_timer = timer_start(2000, 0, function()
        st.self_test = false
        test_timer = nil
        push_mic()
        push_audio()
        refresh()
    end)
end

local MIN_BUS_VOLTS = 10.0
local avionics_switch_on = false
local bus_volts = 0.0
-- Mission-kit gating, independent of the airframe bus — see
-- docs/DATAREF_CONTRACT.md Part 6. Both default true so a panel without the
-- master switch / CB panel instruments behaves exactly as before.
local mission_master_on = true
local mission_cb_in = true

local function update_power()
    local powered = avionics_switch_on and (bus_volts >= MIN_BUS_VOLTS)
        and mission_master_on and mission_cb_in
    if powered == st.powered then return end
    st.powered = powered
    if powered then
        run_self_test()
    else
        st.self_test = false
        stop_playback()
        -- A dark recorder hears nothing. Forget which radios were mid-transmission
        -- so the fall of a stale "receiving" flag after power returns cannot
        -- record a block that was never heard.
        for com in pairs(st.recorder.active_rx) do
            st.recorder.active_rx[com] = false
        end
        si_variable_write(var_fm_audio, false)
        si_variable_write(var_fm_mic, false)
        refresh()
    end
end

-- The GMA 1347 is powered by the avionics master (§ON/OFF Operation) and bus voltage.
xpl_dataref_subscribe("sim/cockpit2/switches/avionics_power_on", "INT", function(on)
    avionics_switch_on = (on or 0) ~= 0
    update_power()
end)

xpl_dataref_subscribe("sim/cockpit2/electrical/bus_volts", "FLOAT[6]", function(val)
    bus_volts = type(val) == "table" and (val[1] or 0.0) or (type(val) == "number" and val or 0.0)
    update_power()
end)

si_variable_subscribe("cap_mission_master_on", "BOOL", function(v)
    mission_master_on = v and true or false
    update_power()
end)

si_variable_subscribe("cap_mission_cb_audio_in", "BOOL", function(v)
    mission_cb_in = v and true or false
    update_power()
end)

-- Ingest audio events to feed the clearance recorder buffer. sim/atc/com1_rx and
-- com2_rx are X-Plane's "is this radio receiving an ATC / ATIS / plugin
-- transmission" flags (DataRefs.txt, read-only). The names this used to
-- subscribe, sim/cockpit2/radios/indicators/com{1,2}_receiving, do not exist.
xpl_dataref_subscribe("sim/atc/com1_rx", "INT", function(v)
    if not st.powered then return end
    local rx = (v == 1)
    if rx and not st.recorder.active_rx.com1 then
        st.recorder.active_rx.com1 = true
    elseif not rx and st.recorder.active_rx.com1 then
        st.recorder.active_rx.com1 = false
        record_transmission("com1", 2000, "COM1 ATC clearance")
    end
end)

xpl_dataref_subscribe("sim/atc/com2_rx", "INT", function(v)
    if not st.powered then return end
    local rx = (v == 1)
    if rx and not st.recorder.active_rx.com2 then
        st.recorder.active_rx.com2 = true
    elseif not rx and st.recorder.active_rx.com2 then
        st.recorder.active_rx.com2 = false
        record_transmission("com2", 2000, "COM2 radio traffic")
    end
end)

-- The TDFM leaves its channel and frequency at their last values when it powers
-- off (docs/DATAREF_CONTRACT.md Part 5), so the only signal that the FM radio is
-- dark is cap_fm_power_on. A radio that is off hears nothing, and a recorder
-- that logs its carrier would play back a call nobody received. Defaults true so
-- a panel without a TDFM instrument behaves as before.
local fm_radio_on = true
si_variable_subscribe("cap_fm_power_on", "BOOL", function(v)
    fm_radio_on = v and true or false
    if not fm_radio_on then
        st.recorder.active_rx.com3 = false
    end
end)

si_variable_subscribe("cap_fm_main_rx", "BOOL", function(v)
    if not st.powered or not fm_radio_on then return end
    local rx = v and true or false
    if rx and not st.recorder.active_rx.com3 then
        st.recorder.active_rx.com3 = true
    elseif not rx and st.recorder.active_rx.com3 then
        st.recorder.active_rx.com3 = false
        record_transmission("com3", 2500, "CAP VHF-FM mission net")
    end
end)

si_variable_subscribe("cap_record_transmission", "STRING", function(v)
    if v and #v > 0 then
        record_transmission("com3", 2000, v)
    end
end)

-- Tell X-Plane this station listens through the copilot audio panel rather than
-- the pilot's. Without it the MO hears the pilot's selections, not their own.
xpl_command("sim/audio_panel/use_copilot_audio")

publish_ics()
push_audio()
refresh()
