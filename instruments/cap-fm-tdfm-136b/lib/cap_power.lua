-- cap_power.lua — the bus-power gate every mission instrument shares.
--
-- An instrument is powered when ALL of these hold:
--   * the airframe avionics master is on   (sim/cockpit2/switches/avionics_power_on)
--   * the bus is above 10 V                (sim/cockpit2/electrical/bus_volts[0])
--   * the mission master switch is ON      (cap_mission_master_on, si_variable)
--   * this system's mission breaker is IN  (cap_mission_cb_*_in, si_variable)
--
-- The two mission conditions default true, so a panel without the master switch
-- or the CB panel instrument behaves exactly as before, and they can only cut
-- power: nothing here can power a system the aircraft bus itself has not.
-- docs/DATAREF_CONTRACT.md Part 6.
--
-- Air Manager executes lib/*.lua before logic.lua and has no require(), so the
-- module is a global table like the other libs.

cap_power = {}
local M = cap_power

M.MIN_BUS_VOLTS = 10.0

--- Watch the four conditions and call on_change(powered) when the AND of them
--- flips. Never called with the value the gate already holds.
-- @param breaker_var  name of this system's breaker si_variable
-- @param on_change    function(powered: boolean)
-- @return a table with powered(): the current state of the gate
function M.watch(breaker_var, on_change)
    local avionics_on, bus_volts = false, 0.0
    local master_on, breaker_in = true, true
    local powered = false

    local function update()
        local now = avionics_on and (bus_volts >= M.MIN_BUS_VOLTS)
            and master_on and breaker_in
        if now == powered then return end
        powered = now
        on_change(now)
    end

    xpl_dataref_subscribe("sim/cockpit2/switches/avionics_power_on", "INT", function(on)
        avionics_on = (on or 0) ~= 0
        update()
    end)

    xpl_dataref_subscribe("sim/cockpit2/electrical/bus_volts", "FLOAT[6]", function(val)
        bus_volts = type(val) == "table" and (val[1] or 0.0)
            or (type(val) == "number" and val or 0.0)
        update()
    end)

    si_variable_subscribe("cap_mission_master_on", "BOOL", function(v)
        master_on = v and true or false
        update()
    end)

    si_variable_subscribe(breaker_var, "BOOL", function(v)
        breaker_in = v and true or false
        update()
    end)

    return { powered = function() return powered end }
end
