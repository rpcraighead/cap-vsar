-- CAP Mission Equipment Circuit Breaker Panel — Mission Observer station
-- CAP V-SAR training simulator
--
-- The SAR mission kit is fed through its own breakers on the observer side,
-- separate from the airframe's ESSENTIAL/AVIONICS BUS breakers under the
-- pilot's yoke (compare Cessna 182T POH "CIRCUIT BREAKERS AND FUSES" — pulling
-- one drops that system's load "for emergency electrical load management"
-- without touching anything else on the bus). This panel gives the mission
-- kit that same crew-operable interrupt, one breaker per system.
--
-- Published contract: docs/DATAREF_CONTRACT.md Part 6.
--
--   cap_mission_cb_df_in    (BOOL, si_variable) — DF head breaker, in = closed
--   cap_mission_cb_fm_in    (BOOL, si_variable) — TDFM-136B FM radio breaker
--   cap_mission_cb_audio_in (BOOL, si_variable) — GMA 1347 audio panel / MFD
--                                                  mission feed breaker
--
-- All three default to IN (closed), so a panel that never adds this
-- instrument sees no behaviour change. Each consuming instrument ANDs its
-- breaker alongside the airframe avionics-master/bus-voltage check and the
-- mission master switch (cap_mission_master_on) it already respects.
--
-- Pulling a breaker here is a crew action, not a simulated fault — it does
-- not model an overcurrent trip. It is the same "reduce electrical load"
-- switch-like use the POH itself warns shortens breaker life, offered here
-- deliberately as a training/load-shedding control.

local CANVAS_W, CANVAS_H = 520, 150

local BREAKERS = {
    { key = "df",    var_name = "cap_mission_cb_df_in",    label = "DF" },
    { key = "fm",    var_name = "cap_mission_cb_fm_in",    label = "FM RADIO" },
    { key = "audio", var_name = "cap_mission_cb_audio_in", label = "AUDIO/MFD" },
}

local COL_W = CANVAS_W / #BREAKERS
local BTN_W, BTN_H = 64, 60
local BTN_Y = 46

for i, b in ipairs(BREAKERS) do
    b.x = math.floor((i - 1) * COL_W + (COL_W - BTN_W) / 2)
    b.in_state = true
    b.var = si_variable_create(b.var_name, "BOOL", true)
end

local canvas_id

local function publish(b)
    si_variable_write(b.var, b.in_state)
end

-- Publish every breaker once at load, so a reload (Air Manager keeps the
-- variables) cannot leave the bus saying OUT for a breaker drawn IN, and a
-- consumer loaded earlier hears the producer arrive.
for _, b in ipairs(BREAKERS) do
    publish(b)
end

local function draw()
    _rect(0, 0, CANVAS_W, CANVAS_H); _fill("#1c1f26")
    _rect(2, 2, CANVAS_W - 4, CANVAS_H - 4); _stroke("#3a3f4a", 2)

    _txt("MISSION EQUIP — CIRCUIT BREAKERS",
         "font:inconsolata_bold.ttf; size:14; color:#c7d0dc; halign:center;",
         CANVAS_W / 2, 14)

    for _, b in ipairs(BREAKERS) do
        local cx = b.x + BTN_W / 2

        -- Red band behind the button, exposed when the breaker is pulled out.
        _rect(b.x, BTN_Y, BTN_W, BTN_H); _fill("#8a1f1f")

        -- The breaker button itself: flush (in) or popped forward, shorter,
        -- with the red band showing above it (out).
        local btn_y = b.in_state and BTN_Y or (BTN_Y + 16)
        local btn_h = b.in_state and BTN_H or (BTN_H - 16)
        _rect(b.x, btn_y, BTN_W, btn_h); _fill(b.in_state and "#3a3f4a" or "#2a2e37")
        _rect(b.x, btn_y, BTN_W, btn_h); _stroke("#565d6b", 2)

        _txt(b.label, "font:inconsolata_bold.ttf; size:10; color:#c7d0dc; halign:center;",
             cx, BTN_Y + BTN_H + 18)
        _txt(b.in_state and "IN" or "OUT",
             "font:inconsolata_bold.ttf; size:9; color:" .. (b.in_state and "#8fd19e" or "#e08a8a") .. "; halign:center;",
             cx, BTN_Y + BTN_H + 32)
    end
end

local function redraw()
    if canvas_id then canvas_draw(canvas_id, draw) end
end

canvas_id = canvas_add(0, 0, CANVAS_W, CANVAS_H, draw)

for _, b in ipairs(BREAKERS) do
    button_add(nil, nil, b.x, BTN_Y, BTN_W, BTN_H,
        function()
            b.in_state = not b.in_state
            publish(b)
            redraw()
        end)
end
