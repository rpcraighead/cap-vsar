-- cap_df.lua — binding to the CAP V-SAR propagation engine.
--
-- The engine is PI_capvsar_df.py, an XPPython3 plugin living at
--   X-Plane 12/Resources/plugins/PythonPlugins/PI_capvsar_df.py
-- It owns propagation, terrain line-of-sight, the radio horizon, the cone of
-- confusion, the 406 burst cadence, bearing averaging and the COSPAS/SARSAT
-- decode, and it doubles as the sim bridge to the exercise console on ms01:8700.
--
-- IMPORTANT: this module is written against the datarefs that plugin *actually*
-- publishes today, not against an idealised set. See docs/DATAREF_CONTRACT.md.
--
-- Published by the engine (read-only):
--   cap/df/valid          INT    1 when a usable bearing exists
--   cap/df/bearing_rel    FLOAT  degrees relative to the nose
--   cap/df/bearing_true   FLOAT  degrees true
--   cap/df/signal         FLOAT  0..1  (note: NOT a percentage)
--   cap/df/distance_nm    FLOAT  slant range
--   cap/df/in_cone        INT    1 inside the cone of confusion
--   cap/df/blocked        INT    1 when terrain masks the signal
--   cap/df/airframe_shadowed INT  1 when the wing/fuselage attenuates reception
--   cap/df/airframe_attenuation_db FLOAT current installation loss
--   cap/df/rx_open        INT    instantaneous reception; unlike valid, not held
--   cap/df/band           FLOAT  what the head is on, in MHz
--   cap/df/spread         FLOAT  scatter of the un-averaged bearings, degrees
--   cap/df/error_code     INT    -1 none, else Becker E0..E12
--   cap/df/cs_*                  COSPAS/SARSAT decode — see subscribe_decode()
--
-- Written by the faceplate (see the write section at the bottom): power, tuned
-- frequency, head type, squelch, mode, scan, timehold, offset, mounting and the
-- CLR pulse. The engine reads all of these, so the frequency knob now really
-- does retune the receiver — which is what makes the 517-vs-RT-600 406 MHz
-- coverage difference demonstrable.

-- Air Manager executes every file in lib/ before logic.lua. Its Lua sandbox
-- does not provide require(), so expose this table to the main script.
cap_df = {}
local M = cap_df

-- The engine registers the panel-input datarefs listed in Part 3 of the
-- contract. Set this false again only if you are running against an older
-- PI_capvsar_df.py that does not have them, so Air Manager is not asked to write
-- datarefs that do not exist.
M.ENGINE_ACCEPTS_PANEL_INPUT = true

M.state = {
    bearing      = 0,       -- deg relative, 0 = nose  (cap/df/bearing_rel)
    bearing_true = 0,
    signal       = 0,       -- % 0..100, rescaled from the engine's 0..1
    valid        = false,
    distance_nm  = 0,
    in_cone      = false,   -- overhead the beacon; bearing is meaningless
    blocked      = false,   -- terrain masking
    airframe_shadowed = false,
    airframe_attenuation_db = 0,
    rx_open      = false,
    band_mhz     = 121.5,

    -- Derived here because the engine does not publish them. Honest
    -- approximations, not engine truth.
    last_signal  = 0,       -- s since valid last went true
    burst_age    = 0,       -- s since the last 406 acquisition

    -- Engine truth, published since the panel-input revision.
    spread       = 0,       -- deg of scatter before averaging
    error_code   = -1,      -- -1 = no error; 0..12 are E0..E12
    cs_sync      = 0,
    cs_protocol  = 0,
    cs_hex15     = "",
    cs_country   = 0,
    cs_has_pos   = false,
    cs_lat       = 0,
    cs_lon       = 0,
    cs_msg_age   = 0,
}

-- Set the first time the engine answers on one of the newer datarefs. Until
-- then the faceplates draw nothing rather than drawing a spread of zero, which
-- would read as a perfect bearing.
local engine_seen = false

--- True when the engine supplies a real bearing-quality figure. The faceplates
--- use this to decide whether to draw the spread wedge at all.
function M.has_spread() return engine_seen end

--- True when COSPAS/SARSAT decode is available. The 517's page 4 and the
--- RT-600's decode window show "no valid frame" while this is false.
function M.has_decode() return engine_seen end

local on_change_cb = nil
local last_valid_at = nil
local elapsed = 0

function M.on_change(callback) on_change_cb = callback end

local function changed()
    if on_change_cb then on_change_cb(M.state) end
end

-- ---------------------------------------------------------------- subscribe --

function M.subscribe()
    xpl_dataref_subscribe(
        "cap/df/valid",        "INT",
        "cap/df/bearing_rel",  "FLOAT",
        "cap/df/bearing_true", "FLOAT",
        "cap/df/signal",       "FLOAT",
        "cap/df/distance_nm",  "FLOAT",
        "cap/df/in_cone",      "INT",
        "cap/df/blocked",      "INT",
        "cap/df/band",         "FLOAT",
        function(valid, bearing_rel, bearing_true, signal,
                 distance_nm, in_cone, blocked, band)
            local s = M.state
            local was_valid = s.valid

            s.valid        = (valid or 0) ~= 0
            s.bearing      = bearing_rel or 0
            s.bearing_true = bearing_true or 0
            -- The engine works in 0..1; both DF heads display 0..100 %.
            s.signal       = math.max(0, math.min(1, signal or 0)) * 100
            s.distance_nm  = distance_nm or 0
            s.in_cone      = (in_cone or 0) ~= 0
            s.blocked      = (blocked or 0) ~= 0
            s.band_mhz     = band or 121.5

            if s.valid then
                last_valid_at = elapsed
                s.last_signal = 0
                if s.band_mhz > 400 and not was_valid then
                    -- Re-acquisition on 406 means a fresh burst arrived.
                    s.burst_age = 0
                end
            end
            changed()
        end)

    M.subscribe_decode()
    M.subscribe_reception()
end

--- Instantaneous reception and installation loss. These remain separate from
-- valid because TIMEHOLD can keep a bearing on screen after the audio nulls.
function M.subscribe_reception()
    xpl_dataref_subscribe(
        "cap/df/airframe_shadowed",       "INT",
        "cap/df/airframe_attenuation_db", "FLOAT",
        "cap/df/rx_open",                 "INT",
        function(shadowed, loss_db, rx_open)
            local s = M.state
            s.airframe_shadowed = (shadowed or 0) ~= 0
            s.airframe_attenuation_db = loss_db or 0
            s.rx_open = (rx_open or 0) ~= 0
            changed()
        end)
end

--- Bearing quality, error state and the COSPAS/SARSAT frame.
--
-- Kept as a second subscription rather than lengthening the first: these arrive
-- on a different cadence (the decode only changes when a burst lands) and the
-- callback would otherwise take eighteen arguments.
function M.subscribe_decode()
    xpl_dataref_subscribe(
        "cap/df/spread",          "FLOAT",
        "cap/df/error_code",      "INT",
        "cap/df/cs_sync",         "INT",
        "cap/df/cs_protocol",     "INT",
        "cap/df/cs_country",      "INT",
        "cap/df/cs_has_position", "INT",
        "cap/df/cs_lat",          "FLOAT",
        "cap/df/cs_lon",          "FLOAT",
        "cap/df/cs_msg_age_sec",  "FLOAT",
        function(spread, error_code, cs_sync, cs_protocol, cs_country,
                 cs_has_position, cs_lat, cs_lon, cs_msg_age)
            local s = M.state
            engine_seen = true

            s.spread      = spread or 0
            s.error_code  = error_code or -1
            s.cs_sync     = cs_sync or 0
            s.cs_protocol = cs_protocol or 0
            s.cs_country  = cs_country or 0
            s.cs_has_pos  = (cs_has_position or 0) ~= 0
            s.cs_lat      = cs_lat or 0
            s.cs_lon      = cs_lon or 0
            s.cs_msg_age  = cs_msg_age or 0
            changed()
        end)

    -- The 15-hex ident is a byte array, so it comes in on its own.
    xpl_dataref_subscribe("cap/df/cs_hex15", "BYTE[15]", function(hex15)
        M.state.cs_hex15 = M.bytes_to_string(hex15)
        changed()
    end)
end

--- Air Manager hands a BYTE[n] dataref back as a string on some builds and as a
--- table of byte values on others. Accept either, and trim the NULs the engine
--- pads a short ident with.
function M.bytes_to_string(value)
    if value == nil then return "" end
    if type(value) == "table" then
        local out = {}
        for _, byte in ipairs(value) do
            if byte == 0 then break end
            out[#out + 1] = string.char(byte)
        end
        value = table.concat(out)
    end
    return (tostring(value):gsub("%z.*$", ""))
end

--- Drive the derived timers. The faceplate calls this from its own timer so the
--- Last Signal and burst counters keep running between engine updates.
function M.tick(dt)
    elapsed = elapsed + dt
    local s = M.state
    if not s.valid and last_valid_at then
        s.last_signal = elapsed - last_valid_at
    end
    if s.band_mhz > 400 then
        s.burst_age = s.burst_age + dt
    end
end

-- -------------------------------------------------------------------- write --
--
-- What the panel tells the engine about itself. The engine registers every one
-- of these as a writable dataref; the gate below exists only so the faceplates
-- can still be run against an older engine build without filling the Air Manager
-- log with "no such dataref" errors.

local function write(dataref, kind, value)
    if not M.ENGINE_ACCEPTS_PANEL_INPUT then return end
    xpl_dataref_write(dataref, kind, value)
end

function M.set_power(on)            write("cap/df/power", "INT", on and 1 or 0) end
function M.set_frequency_hz(hz)     write("cap/df/active_freq_hz", "INT", math.floor(hz + 0.5)) end

--- Half-width the receiver covers either side of the tuned frequency, in Hz.
--- Zero for a single-channel receiver such as the Becker. The RT-600 uses it for
--- its COSPAS-SARSAT groups, each of which covers two or three 3 kHz channels at
--- once (RT-600 manual §2.2.3) — that breadth is the receiver difference the
--- exercise is built on, so the engine has to know about it.
function M.set_span_hz(hz)          write("cap/df/rx_span_hz", "INT", math.floor((hz or 0) + 0.5)) end

--- The two continuous frequencies the head sweeps between 406 bursts while
--- scanning (517 §3.3.3). They are the emergency pair in Emergency mode and the
--- corresponding training channels in Training mode, so the panel has to say
--- which rather than the engine assuming.
function M.set_scan_alternates(hz1, hz2)
    write("cap/df/scan_alt1_hz", "INT", math.floor((hz1 or 0) + 0.5))
    write("cap/df/scan_alt2_hz", "INT", math.floor((hz2 or 0) + 0.5))
end
function M.set_squelch(percent)     write("cap/df/squelch", "FLOAT", percent) end
function M.set_mode(mode)           write("cap/df/mode", "INT", mode) end
function M.set_scan(enabled)        write("cap/df/scan_enable", "INT", enabled and 1 or 0) end
function M.set_head_type(head)      write("cap/df/head_type", "INT", head) end
function M.set_timehold(seconds)    write("cap/df/timehold_sec", "FLOAT", seconds) end
function M.set_offset(degrees)      write("cap/df/offset_deg", "FLOAT", degrees) end
function M.set_mounting(mounting)   write("cap/df/mounting", "INT", mounting) end

--- CLR. The engine clears its averaging store and resets the dataref itself, so
--- the panel only ever writes the 1.
function M.clear_average()          write("cap/df/clear_average", "INT", 1) end

-- ------------------------------------------------------------------ helpers --

--- Format the "mm:ss" timer both heads use. Returns dashes before the first fix.
function M.format_timer(seconds)
    if seconds == nil or seconds < 0 then return "--:--" end
    local total = math.floor(seconds)
    if total > 5999 then return "99:59" end
    return string.format("%02d:%02d", math.floor(total / 60), total % 60)
end

function M.wrap_bearing(deg)
    deg = deg % 360
    if deg < 0 then deg = deg + 360 end
    return deg
end

--- Signed difference from the nose, -180..180. Used by the expanded page.
function M.relative_offset(deg)
    local d = M.wrap_bearing(deg)
    if d > 180 then d = d - 360 end
    return d
end

return M
