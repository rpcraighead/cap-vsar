-- Garmin G1000 MFD Video Stream Watchdog & Recovery Wrapper
-- CAP V-SAR training simulator (Tracker O-7b)
--
-- Problem: SimVideoStreamClient drops connection intermittently (~every few
-- minutes in X-Plane 12 with the Sim Innovations flightsim plugin). The stock
-- Air Manager G1000 instrument calls video_stream_add() only once at load time,
-- leaving the MFD tile frozen on its last received frame indefinitely after a
-- socket reconnect. Navigating an electronic search on a stale moving map is a
-- critical safety hazard.
--
-- Solution:
-- 1. Dual-keyed monitoring:
--    - Connection status: monitored via sim/version/xplane_internal_version.
--    - Frame arrival / heartbeat: monitored via sim/time/total_running_time_sec.
-- 2. Visual Stale Indication:
--    - If frame arrivals cease for longer than WATCHDOG_TIMEOUT_SEC, the tile
--      presents a high-visibility amber/black warning banner:
--      "[ MFD VIDEO STREAM INTERRUPTED - RE-ARMING ]"
--      so the crew immediately knows the screen is not live.
-- 3. Automatic Recovery:
--    - Upon detecting reconnection or frame resumption the stream is re-armed.
--      Air Manager has no call to remove a node, and every video_stream_add()
--      stacks a new 2048x1536 node ABOVE everything added before it, so the
--      instrument creates exactly ONE video node, below the banner and the
--      click hotspot, and re-arms it by toggling its visibility.
--    - An interactive click region permits manual re-arm on demand.
--
-- Layer order is add order: black plate, video stream, stale banner, hotspot.

local STREAM_WIDTH  = 2048
local STREAM_HEIGHT = 1536
local WATCHDOG_TIMEOUT_TICKS = 6  -- 6 x 500ms = 3.0s timeout

local prop_source = user_prop_add_enum("Stream source", "xpl/G1000_MFD,xpl/G1000_PFD_1,xpl/G1000_PFD_2", "xpl/G1000_MFD", "X-Plane offscreen video texture source")
local prop_rearm_interval = user_prop_add_integer("Auto re-arm interval (s)", 1, 30, 5, "Interval between re-arm attempts while stream is stale")

local var_stale          = si_variable_create("g1000_mfd_stream_stale", "BOOL", false)
local var_rearm_count    = si_variable_create("g1000_mfd_rearm_count", "INT", 0)
local var_last_heartbeat = si_variable_create("g1000_mfd_last_heartbeat", "FLOAT", 0.0)

local vst_id = nil
local is_stale = false
local current_tick = 0
local last_packet_tick = 0
local last_rearm_tick = 0
local rearm_counter = 0
local xpl_connected = false
local sim_running_time = 0.0

-- Background black plate
local cnv_bg = canvas_add(0, 0, STREAM_WIDTH, STREAM_HEIGHT)
canvas_draw(cnv_bg, function()
    _rect(0, 0, STREAM_WIDTH, STREAM_HEIGHT)
    _fill("#050505")
end)

--- Arm the video stream. The first call creates the one and only video node;
--- later calls re-arm it in place (hide, then show) so nothing is stacked over
--- the banner and the hotspot added below.
local function arm_video_stream()
    rearm_counter = rearm_counter + 1
    si_variable_write(var_rearm_count, rearm_counter)

    if vst_id == nil then
        local source = user_prop_get(prop_source) or "xpl/G1000_MFD"
        vst_id = video_stream_add(source, 0, 0, STREAM_WIDTH, STREAM_HEIGHT)
    else
        visible(vst_id, false)
        visible(vst_id, true)
    end
end

-- Initial stream arm on startup. Everything added after this sits above it.
arm_video_stream()

-- Stale warning overlay canvas, above the video.
local cnv_stale = canvas_add(0, 0, STREAM_WIDTH, STREAM_HEIGHT)

local function update_stale_banner()
    canvas_draw(cnv_stale, function()
        if not is_stale then return end

        -- Semi-transparent dark scrim over frozen frame: #RRGGBBAA, 0xBF = 75 %.
        -- (The CSS rgba(...) form is not an Air Manager colour.)
        _rect(0, 0, STREAM_WIDTH, STREAM_HEIGHT)
        _fill("#0A0A0ABF")

        -- Prominent warning box in centre
        local bw = 1400
        local bh = 320
        local bx = (STREAM_WIDTH - bw) / 2
        local by = (STREAM_HEIGHT - bh) / 2

        _rect(bx, by, bw, bh)
        _fill("#1a1200")
        _stroke("#ffaa00", 6)

        -- Striped header bar
        _rect(bx, by, bw, 60)
        _fill("#ffaa00")

        _txt("MFD VIDEO STREAM INTERRUPTED", "font:roboto_bold.ttf; size:36; color:#000000; halign:center; valign:center;", bx + bw / 2, by + 30)
        _txt("SimVideoStreamClient connection dropped or frames ceased.", "font:roboto_bold.ttf; size:30; color:#ffffff; halign:center; valign:center;", bx + bw / 2, by + 120)
        _txt(string.format("Auto re-arming video pipeline... (rearm attempts: %d)", rearm_counter), "font:roboto_bold.ttf; size:28; color:#ffcc44; halign:center; valign:center;", bx + bw / 2, by + 180)
        _txt("Click anywhere on this screen to force manual re-arm", "font:roboto_bold.ttf; size:24; color:#aaaaaa; halign:center; valign:center;", bx + bw / 2, by + 250)
    end)
    visible(cnv_stale, is_stale)
end

local function mark_stale()
    if is_stale then return end
    is_stale = true
    si_variable_write(var_stale, true)
    update_stale_banner()
end

local function mark_recovered()
    if not is_stale then return end
    is_stale = false
    si_variable_write(var_stale, false)
    update_stale_banner()
end

local function force_rearm()
    arm_video_stream()
    mark_recovered()
end

-- Interactive click hotspot allows operator to force re-arm manually. Added
-- after the video node, so it is on top of it.
button_add(nil, nil, 0, 0, STREAM_WIDTH, STREAM_HEIGHT, function()
    if is_stale then
        force_rearm()
    end
end)

-- Heartbeat monitoring from X-Plane
xpl_dataref_subscribe("sim/time/total_running_time_sec", "FLOAT", function(t)
    local cur_t = t or 0.0
    if cur_t > sim_running_time then
        sim_running_time = cur_t
        last_packet_tick = current_tick
        xpl_connected = true
        si_variable_write(var_last_heartbeat, cur_t)
        if is_stale then
            -- Connection resumed: re-arm stream and dismiss banner
            arm_video_stream()
            mark_recovered()
        end
    end
end)

xpl_dataref_subscribe("sim/version/xplane_internal_version", "INT", function(ver)
    if (ver or 0) > 0 then
        xpl_connected = true
        last_packet_tick = current_tick
    end
end)

-- Watchdog timer checks every 500 ms
timer_start(500, 500, function()
    current_tick = current_tick + 1
    local elapsed_ticks = current_tick - last_packet_tick

    if xpl_connected and elapsed_ticks >= WATCHDOG_TIMEOUT_TICKS then
        mark_stale()

        -- Periodically re-attempt arming stream while disconnected
        local rearm_interval_sec = user_prop_get(prop_rearm_interval) or 5
        local rearm_ticks = math.max(2, math.floor(rearm_interval_sec * 2))
        if current_tick - last_rearm_tick >= rearm_ticks then
            last_rearm_tick = current_tick
            arm_video_stream()
        end
    elseif xpl_connected and elapsed_ticks < WATCHDOG_TIMEOUT_TICKS then
        if is_stale then
            mark_recovered()
        end
    end
end)

update_stale_banner()
