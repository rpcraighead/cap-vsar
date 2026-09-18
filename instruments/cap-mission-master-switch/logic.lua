-- CAP Mission Equipment Master Switch — Mission Observer station
-- CAP V-SAR training simulator
--
-- The SAR mission kit (Becker/RT-600 DF head, TDFM-136B FM radio, GMA 1347
-- audio panel/MFD feed) is supplemental equipment fed off the airframe bus,
-- not part of the C182T's own BAT/ALT/AVIONICS electrical system. Real
-- mission-kit installations put a single guarded switch on the mission
-- equipment feed so the crew can kill all of it at once — for a precautionary
-- shutdown, or simply to stop it drawing the bus during engine start — without
-- touching the aircraft's own masters.
--
-- Published contract: docs/DATAREF_CONTRACT.md Part 6.
--
--   cap_mission_master_on (BOOL, si_variable) — true when the guarded switch
--   is ON. Every mission instrument ANDs this into its own power logic
--   alongside the airframe avionics-master/bus-voltage check it already had,
--   so this switch can cut mission power but can never substitute for a dead
--   aircraft bus.
--
-- The physical guard must be lifted before the switch can be worked, exactly
-- like the guarded switches CAP mission aircraft actually use to prevent an
-- inadvertent mid-search shutdown.

local CANVAS_W, CANVAS_H = 300, 150

local st = {
    guard_open = false,
    master_on = true,   -- starts closed/on so existing panels behave as before
}

local var_master = si_variable_create("cap_mission_master_on", "BOOL", st.master_on)

local function publish()
    si_variable_write(var_master, st.master_on)
end

-- Layout: guard cage sits above the rocker switch when closed, hinges up and
-- out of the way when open.
local SWITCH_X, SWITCH_Y, SWITCH_W, SWITCH_H = 110, 74, 80, 56
local GUARD_CLOSED_Y, GUARD_CLOSED_H = 68, 68   -- covers the switch
local GUARD_OPEN_Y, GUARD_OPEN_H = 40, 22       -- hinged up, clear of the switch

local canvas_id

local function draw()
    _rect(0, 0, CANVAS_W, CANVAS_H); _fill("#1c1f26")
    _rect(2, 2, CANVAS_W - 4, CANVAS_H - 4); _stroke("#3a3f4a", 2)

    _txt("MISSION EQUIP", "font:inconsolata_bold.ttf; size:16; color:#c7d0dc; halign:center;",
         CANVAS_W / 2, 16)
    _txt("MASTER", "font:inconsolata_bold.ttf; size:13; color:#8b93a1; halign:center;",
         CANVAS_W / 2, 34)

    -- Rocker switch body.
    _rect(SWITCH_X, SWITCH_Y, SWITCH_W, SWITCH_H); _fill("#2a2e37")
    _rect(SWITCH_X, SWITCH_Y, SWITCH_W, SWITCH_H); _stroke("#4a5060", 2)

    local lever_h = SWITCH_H / 2
    local lever_y = st.master_on and SWITCH_Y or (SWITCH_Y + lever_h)
    _rect(SWITCH_X + 4, lever_y, SWITCH_W - 8, lever_h - 4)
    _fill(st.master_on and "#2f9e44" or "#8a1f1f")

    _txt(st.master_on and "ON" or "OFF",
         "font:inconsolata_bold.ttf; size:14; color:#f2f4f7; halign:center;",
         CANVAS_W / 2, SWITCH_Y + SWITCH_H + 16)

    -- Guard cage, drawn either caging the switch (closed) or hinged clear (open).
    local guard_y, guard_h = st.guard_open and GUARD_OPEN_Y or GUARD_CLOSED_Y,
                              st.guard_open and GUARD_OPEN_H or GUARD_CLOSED_H
    _rect(SWITCH_X - 8, guard_y, SWITCH_W + 16, guard_h)
    _stroke(st.guard_open and "#c98a1f" or "#b3261e", 3)

    _txt(st.guard_open and "GUARD OPEN" or "LIFT GUARD",
         "font:inconsolata_bold.ttf; size:11; color:" .. (st.guard_open and "#c98a1f" or "#b3261e") .. "; halign:center;",
         CANVAS_W / 2, st.guard_open and (GUARD_OPEN_Y - 12) or (GUARD_CLOSED_Y + GUARD_CLOSED_H + 30))
end

local function redraw()
    if canvas_id then canvas_draw(canvas_id, draw) end
end

canvas_id = canvas_add(0, 0, CANVAS_W, CANVAS_H, draw)

-- Guard hit region: the cage's closed footprint, big enough to grab whether
-- the guard is currently open or shut.
button_add(nil, nil, SWITCH_X - 8, GUARD_OPEN_Y, SWITCH_W + 16, GUARD_CLOSED_H - GUARD_OPEN_Y + 10,
    function()
        st.guard_open = not st.guard_open
        redraw()
    end)

-- Switch hit region: only answers with the guard lifted, matching the real
-- hardware.
button_add(nil, nil, SWITCH_X, SWITCH_Y, SWITCH_W, SWITCH_H,
    function()
        if not st.guard_open then return end
        st.master_on = not st.master_on
        publish()
        redraw()
    end)
