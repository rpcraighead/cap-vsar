"""Air Manager 4.2 Lua execution harness for off-simulator testing.

Modeled on tests/xp.py for the X-Plane plugin. Loads real instrument lib/*.lua
and logic.lua files against ctypes Lua 5.4 with stubs for the Air Manager 4.2 API.

The harness is deliberately no more permissive than Air Manager
(docs/DECISIONS_2026-10-10.md D3):

* every stub is checked against the signature table in tests/am_api.py and
  raises a Lua error on an extra argument, a missing one or a wrong type;
  a function that is not in the table is undefined;
* xpl_dataref_subscribe / xpl_dataref_write / xpl_command accept only names in
  tests/fixtures/xplane_names.json (the sim/... names the instruments use,
  validated against X-Plane's DataRefs.txt by scripts/check_xplane_names.py)
  plus the cap/df/* names scraped from xplane/PI_capvsar_df.py;
* a multi-dataref subscription is one callback that receives every value;
* sounds count restarts.
"""
import ctypes
import ctypes.util
from pathlib import Path
import random

from tests import am_api

ROOT = Path(__file__).resolve().parents[1]

# Locate system Lua 5.4 shared library
_LUA_PATH = ctypes.util.find_library("lua5.4") or "/usr/lib/x86_64-linux-gnu/liblua5.4.so.0"
_LUA = ctypes.CDLL(_LUA_PATH)

_state_p = ctypes.c_void_p
_LUA.luaL_newstate.restype = _state_p
_LUA.luaL_openlibs.argtypes = [_state_p]
_LUA.luaL_loadstring.argtypes = [_state_p, ctypes.c_char_p]
_LUA.luaL_loadstring.restype = ctypes.c_int
_LUA.lua_pcallk.argtypes = [_state_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ssize_t, ctypes.c_void_p]
_LUA.lua_pcallk.restype = ctypes.c_int
_LUA.lua_tolstring.argtypes = [_state_p, ctypes.c_int, ctypes.c_void_p]
_LUA.lua_tolstring.restype = ctypes.c_char_p
_LUA.lua_tonumberx.argtypes = [_state_p, ctypes.c_int, ctypes.c_void_p]
_LUA.lua_tonumberx.restype = ctypes.c_double
_LUA.lua_toboolean.argtypes = [_state_p, ctypes.c_int]
_LUA.lua_toboolean.restype = ctypes.c_int
_LUA.lua_type.argtypes = [_state_p, ctypes.c_int]
_LUA.lua_type.restype = ctypes.c_int
_LUA.lua_gettop.argtypes = [_state_p]
_LUA.lua_gettop.restype = ctypes.c_int
_LUA.lua_settop.argtypes = [_state_p, ctypes.c_int]
_LUA.lua_next.argtypes = [_state_p, ctypes.c_int]
_LUA.lua_next.restype = ctypes.c_int
_LUA.lua_pushnil.argtypes = [_state_p]
_LUA.lua_close.argtypes = [_state_p]

_PREAMBLE_HEAD = """
_AM = {
    variables = {},
    datarefs = {},
    commands = {},
    timers = {},
    next_timer_id = 1,
    images = {},
    texts = {},
    buttons = {},
    dials = {},
    switches = {},
    canvases = {},
    sounds = {},
    video_streams = {},
    user_props = {},
    next_node_id = 1,
    drawn_commands = {},
    in_draw = false
}

-- Stubs are defined here, not as globals. The signature table (tests/am_api.py)
-- decides which of them the instrument may see and wraps each in an argument
-- check; a name that is not in the table is undefined, as in Air Manager.
local IMPL = {}

local function fail(fname, msg)
    error(fname .. ": " .. msg, 3)
end

-- ------------------------------------------------------------ X-Plane names --

local function valid_dataref_type(kind)
    if type(kind) ~= "string" then return false end
    if kind == "INT" or kind == "FLOAT" or kind == "DOUBLE" then return true end
    local base = kind:match("^(%u+)%[%d+%]$")
    return base == "INT" or base == "FLOAT" or base == "DOUBLE" or base == "BYTE"
end

local function check_dataref(fname, name, kind, need_writable)
    if not valid_dataref_type(kind) then
        fail(fname, "unknown dataref type '" .. tostring(kind) .. "'")
    end
    local meta = _AM_NAMES.datarefs[name]
    if not meta then
        fail(fname, "dataref '" .. tostring(name) .. "' is not in the X-Plane name allowlist "
             .. "(tests/fixtures/xplane_names.json); it does not exist in X-Plane")
    end
    if meta.type ~= kind then
        fail(fname, "dataref '" .. name .. "' is " .. meta.type .. " in X-Plane, not " .. kind)
    end
    if need_writable and not meta.writable then
        fail(fname, "dataref '" .. name .. "' is read-only in X-Plane")
    end
end

local function check_command(fname, name)
    if not _AM_NAMES.commands[name] then
        fail(fname, "command '" .. tostring(name) .. "' is not in the X-Plane name allowlist "
             .. "(tests/fixtures/xplane_names.json); it does not exist in X-Plane")
    end
end

-- ------------------------------------------------------------------ variables --

function IMPL.si_variable_create(name, kind, def)
    local v = _AM.variables[name]
    if not v then
        v = { id = name, name = name, kind = kind, value = def, subscribers = {} }
        _AM.variables[name] = v
    end
    return name
end

function IMPL.si_variable_subscribe(name, kind, cb)
    local v = _AM.variables[name]
    if not v then
        v = { id = name, name = name, kind = kind, value = nil, subscribers = {} }
        _AM.variables[name] = v
    end
    table.insert(v.subscribers, cb)
    if v.value ~= nil then
        cb(v.value)
    end
end

function IMPL.si_variable_write(id_or_name, val)
    local v = _AM.variables[id_or_name]
    if not v then
        v = { id = id_or_name, name = tostring(id_or_name), kind = "UNKNOWN", value = val, subscribers = {} }
        _AM.variables[id_or_name] = v
    else
        v.value = val
    end
    for _, cb in ipairs(v.subscribers) do
        cb(val)
    end
end

function IMPL.si_variable_read(id_or_name)
    local v = _AM.variables[id_or_name]
    if v == nil then return nil end
    return v.value
end

-- ------------------------------------------------------------------ datarefs --

local function dataref_default(kind)
    if kind:match("^BYTE") then return "" end
    if kind == "FLOAT" or kind == "DOUBLE" then return 0.0 end
    return 0
end

local function dataref_record(name, kind)
    local d = _AM.datarefs[name]
    if not d then
        d = { name = name, kind = kind, value = dataref_default(kind), subscribers = {} }
        _AM.datarefs[name] = d
    end
    return d
end

-- A multi-dataref subscription is one group: AM calls the callback with the
-- current value of EVERY name in it whenever any one of them changes.
local function notify_group(group)
    local values = {}
    for i, name in ipairs(group.names) do
        values[i] = _AM.datarefs[name].value
    end
    group.cb(table.unpack(values, 1, #group.names))
end

function IMPL.xpl_dataref_subscribe(...)
    local args = { ... }
    local n = select("#", ...)
    local group = { names = {}, kinds = {}, cb = args[n] }
    for i = 1, n - 1, 2 do
        check_dataref("xpl_dataref_subscribe", args[i], args[i + 1], false)
        group.names[#group.names + 1] = args[i]
        group.kinds[#group.kinds + 1] = args[i + 1]
    end
    for i, name in ipairs(group.names) do
        local d = dataref_record(name, group.kinds[i])
        table.insert(d.subscribers, group)
    end
    -- No callback until a value arrives: Air Manager calls back "when new data
    -- is available from X-Plane" (snippet xpl_dataref_subscribe).
end

-- Set values, then call each affected subscriber group once.
function _AM_write_datarefs(list)
    local order, seen = {}, {}
    for _, item in ipairs(list) do
        local d = dataref_record(item[1], item[2])
        d.value = item[3]
        for _, group in ipairs(d.subscribers) do
            if not seen[group] then
                seen[group] = true
                order[#order + 1] = group
            end
        end
    end
    for _, group in ipairs(order) do
        notify_group(group)
    end
end

-- The simulator side: any name X-Plane has, read-only or not.
function _AM_sim_write(list)
    for _, item in ipairs(list) do
        check_dataref("sim write", item[1], item[2], false)
    end
    _AM_write_datarefs(list)
end

function IMPL.xpl_dataref_write(name, kind, val)
    check_dataref("xpl_dataref_write", name, kind, true)
    _AM_write_datarefs({ { name, kind, val } })
end

function IMPL.xpl_command(name)
    check_command("xpl_command", name)
    table.insert(_AM.commands, { name = name })
end

-- -------------------------------------------------------------------- timers --

function IMPL.timer_start(delay, interval, cb)
    if type(interval) == "function" then
        cb, interval = interval, nil
    end
    local id = _AM.next_timer_id
    _AM.next_timer_id = id + 1
    _AM.timers[id] = { id = id, delay = delay or 0, interval = interval, cb = cb,
                       active = true, count = 0 }
    return id
end

function IMPL.timer_stop(id)
    if id and _AM.timers[id] then
        _AM.timers[id].active = false
    end
end

function IMPL.timer_running(id)
    return id and _AM.timers[id] and _AM.timers[id].active or false
end

function _AM_step_time(ms)
    local to_run = {}
    for id, t in pairs(_AM.timers) do
        if t.active then
            local rem = ms
            while t.active and rem > 0 do
                if t.delay <= rem then
                    rem = rem - t.delay
                    t.count = t.count + 1
                    table.insert(to_run, { t.cb, t.count })
                    if t.interval and t.interval > 0 then
                        t.delay = t.interval
                    else
                        t.active = false
                        break
                    end
                else
                    t.delay = t.delay - rem
                    rem = 0
                end
            end
        end
    end
    for _, run in ipairs(to_run) do
        run[1](run[2])
    end
end

-- ------------------------------------------------------------------ controls --

local function new_id()
    local id = _AM.next_node_id
    _AM.next_node_id = id + 1
    return id
end

function IMPL.button_add(up_img, down_img, x, y, w, h, press_cb, release_cb)
    local id = new_id()
    _AM.buttons[id] = {
        id = id, up_img = up_img, down_img = down_img,
        x = x, y = y, w = w, h = h,
        press_cb = press_cb, release_cb = release_cb, visible = true
    }
    return id
end

function IMPL.dial_add(img, x, y, w, h, step, turn_cb)
    if turn_cb == nil then step, turn_cb = nil, step end
    local id = new_id()
    _AM.dials[id] = {
        id = id, img = img, x = x, y = y, w = w, h = h, step = step,
        turn_cb = turn_cb, visible = true
    }
    return id
end

function IMPL.switch_add(...)
    local args = { ... }
    local n = select("#", ...)
    local cb = args[n]
    local x, y, w, h = args[n - 4], args[n - 3], args[n - 2], args[n - 1]
    local images = {}
    for i = 1, n - 5 do images[i] = args[i] end
    local id = new_id()
    _AM.switches[id] = {
        id = id, up_img = images[1], down_img = images[2], images = images,
        x = x, y = y, w = w, h = h,
        cb = cb, position = 0, visible = true
    }
    return id
end

function IMPL.switch_set_position(id, pos)
    if _AM.switches[id] then
        _AM.switches[id].position = pos
    end
end

function IMPL.switch_get_position(id)
    if _AM.switches[id] then
        return _AM.switches[id].position
    end
    return 0
end

-- Topmost visible control whose rectangle contains (x, y). Add order is layer
-- order in Air Manager, so the highest id wins.
function _AM_hit(kind, x, y)
    local best
    for id, c in pairs(_AM[kind]) do
        if c.visible ~= false and x >= c.x and x < c.x + c.w and y >= c.y and y < c.y + c.h then
            if not best or id > best then best = id end
        end
    end
    return best
end

-- ------------------------------------------------------------------ graphics --

function IMPL.img_add(file, x, y, w, h, style)
    local id = new_id()
    _AM.images[id] = {
        id = id, file = file, x = x, y = y, w = w, h = h, style = style,
        visible = true, opacity = 1.0, rotate = 0
    }
    return id
end

local function node(id)
    return _AM.images[id] or _AM.texts[id] or _AM.canvases[id] or _AM.video_streams[id]
        or _AM.buttons[id] or _AM.dials[id] or _AM.switches[id]
end

function IMPL.visible(id, is_vis)
    local n = node(id)
    if n then n.visible = is_vis end
end

function IMPL.video_stream_add(source, x, y, w, h, sx, sy, sw, sh)
    local id = new_id()
    _AM.video_streams[id] = {
        id = id, source = source, x = x, y = y, w = w, h = h, visible = true
    }
    return id
end

function IMPL.user_prop_add_enum(name, options, default, desc)
    _AM.user_props[name] = default
    return name
end
function IMPL.user_prop_add_integer(name, min, max, default, desc)
    _AM.user_props[name] = default
    return name
end
function IMPL.user_prop_add_boolean(name, default, desc)
    _AM.user_props[name] = default
    return name
end
function IMPL.user_prop_get(prop_or_name)
    if type(prop_or_name) == "string" and _AM.user_props[prop_or_name] ~= nil then
        return _AM.user_props[prop_or_name]
    end
    return prop_or_name
end

function IMPL.opacity(id, val)
    if _AM.images[id] then _AM.images[id].opacity = val end
end

function IMPL.rotate(id, deg)
    if _AM.images[id] then _AM.images[id].rotate = deg end
end

function IMPL.move(id, x, y, w, h)
    local item = node(id)
    if item then
        if x then item.x = x end
        if y then item.y = y end
        if w then item.w = w end
        if h then item.h = h end
    end
end

function IMPL.txt_add(text, style, x, y, w, h)
    local id = new_id()
    _AM.texts[id] = {
        id = id, text = text, style = style,
        x = x, y = y, w = w, h = h, visible = true
    }
    return id
end

function IMPL.txt_set(id, text)
    if _AM.texts[id] then
        _AM.texts[id].text = text
    end
end

function IMPL.txt_style(id, style)
    if _AM.texts[id] then
        _AM.texts[id].style = style
    end
end

function IMPL.canvas_draw(id, cb)
    if _AM.in_draw then
        error("You cannot call canvas_draw within a draw callback.")
    end
    _AM.in_draw = true
    local ok, err = pcall(cb)
    _AM.in_draw = false
    if not ok then error(err) end
end

function IMPL.canvas_add(x, y, w, h, cb)
    local id = new_id()
    _AM.canvases[id] = {
        id = id, x = x, y = y, w = w, h = h, cb = cb, visible = true
    }
    if cb then
        IMPL.canvas_draw(id, cb)
    end
    return id
end

local function cmd(...) table.insert(_AM.drawn_commands, { ... }) end
function IMPL._rect(x, y, w, h) cmd("rect", x, y, w, h) end
function IMPL._circle(cx, cy, r) cmd("circle", cx, cy, r) end
function IMPL._triangle(x1, y1, x2, y2, x3, y3) cmd("triangle", x1, y1, x2, y2, x3, y3) end
function IMPL._move_to(x, y) cmd("move_to", x, y) end
function IMPL._line_to(x, y) cmd("line_to", x, y) end
function IMPL._stroke(color, width) cmd("stroke", color, width) end
function IMPL._fill(color) cmd("fill", color) end
function IMPL._txt(text, style, x, y) cmd("txt", text, style, x, y) end

-- -------------------------------------------------------------------- sound --
-- A sound that is told to loop (or play) while it is already running is
-- restarted by Air Manager; count those so a test can assert there are none.

function IMPL.sound_add(file, vol)
    local id = new_id()
    _AM.sounds[id] = { id = id, file = file, volume = vol or 1.0, state = "stopped",
                       restarts = 0, starts = 0 }
    return id
end

function IMPL.sound_volume(id, vol)
    if _AM.sounds[id] then _AM.sounds[id].volume = vol end
end

local function start_sound(id, state)
    local s = _AM.sounds[id]
    if not s then return end
    if s.state ~= "stopped" then s.restarts = s.restarts + 1 end
    s.starts = s.starts + 1
    s.state = state
end

function IMPL.sound_play(id) start_sound(id, "playing") end
function IMPL.sound_loop(id) start_sound(id, "looping") end
function IMPL.sound_stop(id)
    if _AM.sounds[id] then _AM.sounds[id].state = "stopped" end
end

-- ------------------------------------------------------- signature enforcement --

local TYPE_LABEL = { s = "string", n = "number", f = "function", b = "boolean",
                     a = "any value", c = "colour string" }

local function is_colour(v)
    if type(v) ~= "string" then return false end
    if v:match("^%a+$") then return true end
    return v:match("^#%x%x%x$") ~= nil or v:match("^#%x%x%x%x%x%x$") ~= nil
        or v:match("^#%x%x%x%x%x%x%x%x$") ~= nil
end

local function type_ok(base, v)
    if base == "a" then return true end
    if base == "s" then return type(v) == "string" end
    if base == "n" then return type(v) == "number" end
    if base == "f" then return type(v) == "function" end
    if base == "b" then return type(v) == "boolean" end
    if base == "c" then return is_colour(v) end
    return false
end

local parsed = {}
local function parse(shape)
    local p = parsed[shape]
    if p then return p end
    p = { codes = {}, required = 0 }
    for code in shape:gmatch("%S+") do
        local base, opt = code:sub(1, 1), code:sub(2, 2) == "?"
        p.codes[#p.codes + 1] = { base = base, opt = opt }
        if not opt then p.required = #p.codes end
    end
    parsed[shape] = p
    return p
end

local function try_shape(shape, n, args)
    local p = parse(shape)
    if n > #p.codes then
        return "too many arguments (got " .. n .. ", at most " .. #p.codes .. ")"
    end
    if n < p.required then
        return "not enough arguments (got " .. n .. ", need " .. p.required .. ")"
    end
    for i = 1, n do
        local c, v = p.codes[i], args[i]
        if v == nil then
            if not (c.opt or c.base == "a") then
                return "bad argument #" .. i .. " (" .. TYPE_LABEL[c.base] .. " expected, got nil)"
            end
        elseif not type_ok(c.base, v) then
            return "bad argument #" .. i .. " (" .. TYPE_LABEL[c.base] .. " expected, got "
                .. type(v) .. (c.base == "c" and (" " .. tostring(v)) or "") .. ")"
        end
    end
    return nil
end

local VALIDATORS = {}
function VALIDATORS.dataref_pairs(n, args)
    -- (name, type)+ , callback
    if n < 3 or n % 2 == 0 then
        return "expects name, type pairs followed by a callback (got " .. n .. " arguments)"
    end
    for i = 1, n - 1, 2 do
        if type(args[i]) ~= "string" then
            return "bad argument #" .. i .. " (dataref name string expected, got " .. type(args[i]) .. ")"
        end
        if type(args[i + 1]) ~= "string" then
            return "bad argument #" .. (i + 1) .. " (dataref type string expected, got " .. type(args[i + 1]) .. ")"
        end
    end
    if type(args[n]) ~= "function" then
        return "bad argument #" .. n .. " (callback function expected, got " .. type(args[n]) .. ")"
    end
    return nil
end

for name, shapes in pairs(_SIG) do
    local impl = IMPL[name]
    assert(impl, "signature table lists " .. name .. " but the harness has no stub for it")
    local wrapped
    if type(shapes) == "string" then
        local validator = assert(VALIDATORS[shapes], "unknown validator " .. shapes)
        wrapped = function(...)
            local n = select("#", ...)
            local why = validator(n, { ... })
            if why then error(name .. ": " .. why, 2) end
            return impl(...)
        end
    else
        wrapped = function(...)
            local n = select("#", ...)
            local args = { ... }
            local reasons = {}
            for _, shape in ipairs(shapes) do
                local why = try_shape(shape, n, args)
                if not why then return impl(...) end
                reasons[#reasons + 1] = why
            end
            local msg = (#shapes == 1) and reasons[1]
                or ("no matching signature: " .. table.concat(reasons, " | "))
            error(name .. ": " .. msg, 2)
        end
    end
    _G[name] = wrapped
end
for name in pairs(IMPL) do
    assert(_SIG[name], "harness stub " .. name .. " is not in the signature table (tests/am_api.py)")
end

-- Air Manager's sandbox has no require() and no file access.
for _, name in ipairs(_SANDBOX_REMOVED) do _G[name] = nil end
"""


def _lua_literal(value):
    """Render a Python value as a Lua literal."""
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        out = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return '"' + out + '"'
    if isinstance(value, (list, tuple)):
        return "{" + ", ".join(_lua_literal(v) for v in value) + "}"
    raise TypeError(f"cannot render {value!r} as a Lua literal")


def _build_preamble():
    names = am_api.allowed_names()
    drefs = ",\n".join(
        f"    [{_lua_literal(n)}] = {{ type = {_lua_literal(m['type'])}, "
        f"writable = {_lua_literal(bool(m['writable']))} }}"
        for n, m in sorted(names["datarefs"].items()))
    cmds = ",\n".join(f"    [{_lua_literal(n)}] = true" for n in sorted(names["commands"]))
    removed = ", ".join(_lua_literal(n) for n in am_api.SANDBOX_REMOVED)
    return "\n".join([
        f"_SANDBOX_REMOVED = {{ {removed} }}",
        f"_AM_NAMES = {{ datarefs = {{\n{drefs}\n}}, commands = {{\n{cmds}\n}} }}",
        am_api.lua_signature_table(),
        _PREAMBLE_HEAD,
    ]).encode("utf-8")


PREAMBLE = _build_preamble()


def _lua_to_python(L, idx):
    """Recursively convert a Lua stack element to a Python value."""
    t = _LUA.lua_type(L, idx)
    if t == 0:  # LUA_TNIL
        return None
    if t == 1:  # LUA_TBOOLEAN
        return bool(_LUA.lua_toboolean(L, idx))
    if t == 3:  # LUA_TNUMBER
        n = _LUA.lua_tonumberx(L, idx, None)
        return int(n) if n.is_integer() else n
    if t == 4:  # LUA_TSTRING
        return _LUA.lua_tolstring(L, idx, None).decode("utf-8", "replace")
    if t == 5:  # LUA_TTABLE
        res = {}
        if idx < 0:
            idx = _LUA.lua_gettop(L) + idx + 1
        _LUA.lua_pushnil(L)
        is_array = True
        max_k = 0
        while _LUA.lua_next(L, idx) != 0:
            k = _lua_to_python(L, -2)
            v = _lua_to_python(L, -1)
            res[k] = v
            if not isinstance(k, int) or k < 1:
                is_array = False
            else:
                max_k = max(max_k, k)
            _LUA.lua_settop(L, -2)
        if is_array and max_k == len(res) and len(res) > 0:
            return [res[i] for i in range(1, max_k + 1)]
        return res
    return f"<lua:{t}>"


# What the engine publishes on a quiet frame. publish_df() starts from these so a
# test names only the datarefs it cares about; band is the 121.5 MHz default.
DF_DEFAULTS = {
    "cap/df/valid": 0, "cap/df/bearing_rel": 0.0, "cap/df/bearing_true": 0.0,
    "cap/df/signal": 0.0, "cap/df/distance_nm": 0.0, "cap/df/in_cone": 0,
    "cap/df/blocked": 0, "cap/df/band": 121.5,
    "cap/df/airframe_shadowed": 0, "cap/df/airframe_attenuation_db": 0.0,
    "cap/df/rx_open": 0,
    "cap/df/spread": 0.0, "cap/df/error_code": -1, "cap/df/cs_sync": 0,
    "cap/df/cs_protocol": 0, "cap/df/cs_country": 0, "cap/df/cs_has_position": 0,
    "cap/df/cs_lat": 0.0, "cap/df/cs_lon": 0.0, "cap/df/cs_msg_age_sec": 0.0,
    "cap/df/cs_hex15": "",
}


class AirManager:
    """Simulated Air Manager 4.2 runtime executing instrument Lua code."""

    def __init__(self):
        self.L = _LUA.luaL_newstate()
        if not self.L:
            raise RuntimeError("Failed to allocate Lua state")
        _LUA.luaL_openlibs(self.L)
        self._exec_string(PREAMBLE, "<am_preamble>")
        self.instrument_name = None
        self._df = dict(DF_DEFAULTS)
        self._names = am_api.allowed_names()["datarefs"]

    def _exec_string(self, code_bytes, chunk_name="<eval>"):
        rc = _LUA.luaL_loadstring(self.L, code_bytes)
        if rc != 0:
            err = _LUA.lua_tolstring(self.L, -1, None).decode("utf-8", "replace")
            _LUA.lua_settop(self.L, -2)
            raise AssertionError(f"Syntax error in {chunk_name}: {err}")
        rc = _LUA.lua_pcallk(self.L, 0, 1, 0, 0, None)
        if rc != 0:
            err = _LUA.lua_tolstring(self.L, -1, None).decode("utf-8", "replace")
            _LUA.lua_settop(self.L, -2)
            raise RuntimeError(f"Runtime error in {chunk_name}: {err}")
        res = _lua_to_python(self.L, -1)
        _LUA.lua_settop(self.L, -2)
        return res

    def eval(self, code_str):
        """Evaluate a Lua string and return its result converted to Python."""
        return self._exec_string(code_str.encode("utf-8"))

    def load_instrument(self, name, shuffle_libs=False, lib_order=None):
        """Load an instrument's lib/*.lua files and then logic.lua.

        Calling it again loads another instrument into the same Lua state, which
        is how a test puts a producer and its consumers on one si_variable bus.
        """
        self.instrument_name = name
        inst_dir = ROOT / "instruments" / name
        if not inst_dir.is_dir():
            raise FileNotFoundError(f"Instrument directory not found: {inst_dir}")

        lib_files = sorted(inst_dir.glob("lib/*.lua"))
        if lib_order is not None:
            lib_files = [Path(p) for p in lib_order]
        elif shuffle_libs:
            lib_files = list(lib_files)
            random.shuffle(lib_files)

        for lib_path in lib_files:
            code = lib_path.read_bytes()
            self._exec_string(code, str(lib_path))

        logic_path = inst_dir / "logic.lua"
        code = logic_path.read_bytes()
        self._exec_string(code, str(logic_path))

    # ------------------------------------------------------------ variables --

    def write_si_variable(self, name, value):
        """Write a value to a Sim Innovations variable and trigger subscribers."""
        self.eval(f"si_variable_write('{name}', {_lua_literal(value)})")

    def read_si_variable(self, name):
        """Read the current value of a Sim Innovations variable."""
        return self.eval(f"return si_variable_read('{name}')")

    # ------------------------------------------------------------- datarefs --

    def write_dataref(self, name, kind, value):
        """X-Plane (or the DF engine) publishes a value; subscribers are called.

        Refuses a name or type X-Plane does not have. Read-only datarefs are
        writable from here because this is the simulator's side of the wire.
        """
        self.write_datarefs([(name, kind, value)])

    def write_datarefs(self, items):
        """Publish several datarefs in one frame.

        All values are set first, then every subscription group that contains
        at least one of them is called once with all of its current values,
        which is what a multi-dataref xpl_dataref_subscribe sees in Air Manager.
        items: iterable of (name, kind, value).
        """
        lua = ", ".join(
            "{" + ", ".join((_lua_literal(n), _lua_literal(k), _lua_literal(v))) + "}"
            for n, k, v in items)
        self.eval(f"_AM_sim_write({{{lua}}})")

    def publish_df(self, **fields):
        """Publish the cap/df/* engine outputs, one frame, like the plugin does.

        Keyword names are the dataref names without the cap/df/ prefix. Values
        persist between calls, so a test states only what changes:
        ``am.publish_df(valid=1, bearing_rel=47.0, signal=0.8, rx_open=1)``.
        """
        for key, value in fields.items():
            full = "cap/df/" + key
            if full not in self._df:
                raise KeyError(f"{full} is not an engine output the harness publishes")
            self._df[full] = value
        self.write_datarefs((n, self._names[n]["type"], v) for n, v in self._df.items())

    def read_dataref(self, name):
        """Read current dataref value."""
        return self.eval(f"return _AM.datarefs['{name}'] and _AM.datarefs['{name}'].value or nil")

    def get_commands(self):
        """Return list of invoked X-Plane commands."""
        return self.eval("return _AM.commands")

    def command_names(self):
        cmds = self.get_commands() or []
        return [c["name"] for c in cmds]

    def step_time(self, ms):
        """Advance simulated Air Manager clock by ms and invoke expired timers."""
        self.eval(f"_AM_step_time({int(ms)})")

    # -------------------------------------------------------------- buttons --

    def click_button(self, btn_id):
        """Trigger button press then release."""
        self.press_button(btn_id)
        self.release_button(btn_id)

    def press_button(self, btn_id):
        self.eval(f"local b = _AM.buttons[{btn_id}]; if b and b.visible ~= false and b.press_cb then b.press_cb() end")

    def release_button(self, btn_id):
        self.eval(f"local b = _AM.buttons[{btn_id}]; if b and b.visible ~= false and b.release_cb then b.release_cb() end")

    def button_at(self, x, y):
        """Id of the topmost visible button covering (x, y), or None."""
        return self.eval(f"return _AM_hit('buttons', {x}, {y})")

    def _button_at_or_raise(self, x, y):
        btn = self.button_at(x, y)
        if btn is None:
            raise ValueError(f"no button covers ({x}, {y})")
        return btn

    def press_at(self, x, y):
        """Press the topmost button under (x, y), as a mouse click would."""
        btn = self._button_at_or_raise(x, y)
        self.press_button(btn)
        return btn

    def release_at(self, x, y):
        btn = self._button_at_or_raise(x, y)
        self.release_button(btn)
        return btn

    def click_at(self, x, y):
        btn = self._button_at_or_raise(x, y)
        self.click_button(btn)
        return btn

    def find_button_matching(self, pattern=None, x=None, y=None):
        btns = self.get_buttons()
        for b_id, b in (btns.items() if isinstance(btns, dict) else enumerate(btns, 1)):
            if not isinstance(b, dict):
                continue
            up = str(b.get("up_img", ""))
            down = str(b.get("down_img", ""))
            bx, by = b.get("x"), b.get("y")
            if pattern:
                if pattern in up or pattern in down:
                    if (x is None or bx == x) and (y is None or by == y):
                        return b.get("id", b_id)
            elif x is not None and bx == x and (y is None or by == y):
                return b.get("id", b_id)
        raise ValueError(f"No button matching pattern={pattern} x={x} y={y}")

    def click_button_matching(self, pattern=None, x=None, y=None):
        """Click the first button matching pattern or coordinates."""
        target_id = self.find_button_matching(pattern, x, y)
        self.click_button(target_id)
        return target_id

    # ---------------------------------------------------------------- dials --
    # A dial has one callback, called with +1 or -1. It has no press or release;
    # a knob push is a button placed over the knob (see knob_push in the shared
    # lib), so tests push it with press_at()/release_at().

    def turn_dial(self, dial_id, direction):
        self.eval(f"if _AM.dials[{dial_id}] and _AM.dials[{dial_id}].turn_cb then _AM.dials[{dial_id}].turn_cb({direction}) end")

    def dial_at(self, x, y):
        """Id of the topmost dial covering (x, y), or None.

        Buttons are ignored on purpose: the stock G1000 lays a small button
        over the centre of a dial and its turn events still reach the dial.
        """
        return self.eval(f"return _AM_hit('dials', {x}, {y})")

    def turn_at(self, x, y, direction):
        d_id = self.dial_at(x, y)
        if d_id is None:
            raise ValueError(f"no dial covers ({x}, {y})")
        self.turn_dial(d_id, direction)
        return d_id

    def find_dial_matching(self, pattern=None, x=None, y=None):
        dials = self.get_dials()
        for d_id, d in (dials.items() if isinstance(dials, dict) else enumerate(dials, 1)):
            if not isinstance(d, dict):
                continue
            img = str(d.get("img", ""))
            dx, dy = d.get("x"), d.get("y")
            if pattern and pattern in img:
                if (x is None or dx == x) and (y is None or dy == y):
                    return d.get("id", d_id)
            elif x is not None and dx == x and (y is None or dy == y):
                return d.get("id", d_id)
        raise ValueError(f"No dial matching pattern={pattern} x={x} y={y}")

    def turn_dial_matching(self, direction, pattern=None, x=None, y=None):
        d_id = self.find_dial_matching(pattern, x, y)
        self.turn_dial(d_id, direction)
        return d_id

    # ------------------------------------------------------------- switches --

    def find_switch_matching(self, pattern=None, x=None, y=None):
        switches = self.get_switches()
        for s_id, s in (switches.items() if isinstance(switches, dict) else enumerate(switches, 1)):
            if not isinstance(s, dict):
                continue
            up = str(s.get("up_img", ""))
            down = str(s.get("down_img", ""))
            sx, sy = s.get("x"), s.get("y")
            if pattern and (pattern in up or pattern in down):
                if (x is None or sx == x) and (y is None or sy == y):
                    return s.get("id", s_id)
            elif x is not None and sx == x and (y is None or sy == y):
                return s.get("id", s_id)
        raise ValueError(f"No switch matching pattern={pattern} x={x} y={y}")

    def click_switch_matching(self, pattern=None, x=None, y=None, direction=1):
        s_id = self.find_switch_matching(pattern, x, y)
        cur = self.get_switch_position(s_id)
        self.flip_switch(s_id, position=cur, direction=direction)
        return s_id

    def flip_switch(self, switch_id, position=None, direction=0):
        """Flip switch. If position is None, toggles current position."""
        if position is None:
            cur = self.get_switch_position(switch_id)
            position = 1 if cur == 0 else 0
        self.eval(f"""
            local sw = _AM.switches[{switch_id}]
            if sw and sw.cb then
                sw.cb({position}, {direction})
            end
        """)

    def get_switch_position(self, switch_id):
        return self.eval(f"return switch_get_position({switch_id})")

    # --------------------------------------------------------------- display --

    def is_visible(self, node_id):
        return self.eval(f"""
            local n = _AM.images[{node_id}] or _AM.texts[{node_id}] or _AM.canvases[{node_id}]
                      or _AM.video_streams[{node_id}] or _AM.buttons[{node_id}]
            return n and n.visible or false
        """)

    def get_text(self, txt_id):
        return self.eval(f"return _AM.texts[{txt_id}] and _AM.texts[{txt_id}].text or nil")

    def get_buttons(self):
        return self.eval("return _AM.buttons")

    def get_dials(self):
        return self.eval("return _AM.dials")

    def get_switches(self):
        return self.eval("return _AM.switches")

    def sounds(self):
        """Sound records keyed by file name: state, volume, restarts, starts."""
        raw = self.eval("return _AM.sounds") or {}
        items = raw.values() if isinstance(raw, dict) else raw
        return {s["file"]: s for s in items if isinstance(s, dict)}

    def set_avionics_power(self, on=True, volts=28.0):
        self.write_dataref("sim/cockpit2/switches/avionics_power_on", "INT", 1 if on else 0)
        self.write_dataref("sim/cockpit2/electrical/bus_volts", "FLOAT[6]", float(volts) if on else 0.0)

    def close(self):
        if self.L:
            _LUA.lua_close(self.L)
            self.L = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
