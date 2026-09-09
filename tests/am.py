"""Air Manager 4.2 Lua execution harness for off-simulator testing.

Modeled on tests/xp.py for the X-Plane plugin. Loads real instrument lib/*.lua
and logic.lua files against ctypes Lua 5.4 with complete stubs for the Air Manager
4.2 API (si_variable_*, xpl_*, timer_*, button_add, dial_add, switch_add, canvas_draw,
img_add, txt_add, sound_*).
"""
import ctypes
import ctypes.util
import glob
from pathlib import Path
import random

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

PREAMBLE = b"""
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
    next_node_id = 1,
    drawn_commands = {},
    in_draw = false
}

function si_variable_create(name, kind, def)
    local v = _AM.variables[name]
    if not v then
        v = { id = name, name = name, kind = kind, value = def, subscribers = {} }
        _AM.variables[name] = v
    end
    return name
end

function si_variable_subscribe(name, kind, cb)
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

function si_variable_write(id_or_name, val)
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

function si_variable_read(id_or_name)
    local v = _AM.variables[id_or_name]
    return v and v.value or nil
end

function xpl_dataref_subscribe(name, kind, ...)
    local args = {...}
    local cb
    for i = 1, #args do
        if type(args[i]) == "function" then
            cb = args[i]
            break
        end
    end
    local d = _AM.datarefs[name]
    if not d then
        local def = (kind == "INT" and 0) or (kind == "FLOAT" and 0.0) or (kind:match("BYTE") and "") or 0
        d = { name = name, kind = kind, value = def, subscribers = {} }
        _AM.datarefs[name] = d
    end
    if cb then
        table.insert(d.subscribers, cb)
        cb(d.value)
    end
end

function xpl_dataref_write(name, kind, val)
    local d = _AM.datarefs[name]
    if not d then
        d = { name = name, kind = kind, value = val, subscribers = {} }
        _AM.datarefs[name] = d
    else
        d.value = val
    end
    for _, cb in ipairs(d.subscribers) do
        cb(val)
    end
end

function xpl_command(name, phase)
    table.insert(_AM.commands, { name = name, phase = phase })
end

function timer_start(delay, interval, cb)
    local id = _AM.next_timer_id
    _AM.next_timer_id = id + 1
    _AM.timers[id] = { id = id, delay = delay, interval = interval, cb = cb, active = true }
    return id
end

function timer_stop(id)
    if id and _AM.timers[id] then
        _AM.timers[id].active = false
    end
end

function timer_running(id)
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
                    table.insert(to_run, t.cb)
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
    for _, cb in ipairs(to_run) do
        cb()
    end
end

function button_add(up_img, down_img, x, y, w, h, press_cb, release_cb)
    local id = _AM.next_node_id
    _AM.next_node_id = id + 1
    _AM.buttons[id] = {
        id = id, up_img = up_img, down_img = down_img,
        x = x, y = y, w = w, h = h,
        press_cb = press_cb, release_cb = release_cb
    }
    return id
end

function dial_add(img, x, y, w, h, step, turn_cb, press_cb, release_cb)
    local id = _AM.next_node_id
    _AM.next_node_id = id + 1
    _AM.dials[id] = {
        id = id, img = img, x = x, y = y, w = w, h = h, step = step,
        turn_cb = turn_cb, press_cb = press_cb, release_cb = release_cb
    }
    return id
end

function switch_add(up_img, down_img, x, y, w, h, cb)
    local id = _AM.next_node_id
    _AM.next_node_id = id + 1
    _AM.switches[id] = {
        id = id, up_img = up_img, down_img = down_img,
        x = x, y = y, w = w, h = h,
        cb = cb, position = 0
    }
    return id
end

function switch_set_position(id, pos)
    if id and _AM.switches[id] then
        _AM.switches[id].position = pos
    end
end

function switch_get_position(id)
    if id and _AM.switches[id] then
        return _AM.switches[id].position
    end
    return 0
end

function img_add(file, x, y, w, h)
    local id = _AM.next_node_id
    _AM.next_node_id = id + 1
    _AM.images[id] = {
        id = id, file = file, x = x, y = y, w = w, h = h,
        visible = true, opacity = 1.0, rotate = 0
    }
    return id
end

function visible(id, is_vis)
    if not id then return end
    if _AM.images[id] then _AM.images[id].visible = (is_vis and true or false) end
    if _AM.texts[id] then _AM.texts[id].visible = (is_vis and true or false) end
    if _AM.canvases[id] then _AM.canvases[id].visible = (is_vis and true or false) end
end

function opacity(id, val)
    if id and _AM.images[id] then _AM.images[id].opacity = val end
end

function rotate(id, deg)
    if id and _AM.images[id] then _AM.images[id].rotate = deg end
end

function move(id, x, y, w, h)
    local item = _AM.images[id] or _AM.texts[id] or _AM.buttons[id] or _AM.dials[id]
    if item then
        if x then item.x = x end
        if y then item.y = y end
        if w then item.w = w end
        if h then item.h = h end
    end
end

function txt_add(text, style, x, y, w, h)
    local id = _AM.next_node_id
    _AM.next_node_id = id + 1
    _AM.texts[id] = {
        id = id, text = text, style = style,
        x = x, y = y, w = w, h = h, visible = true
    }
    return id
end

function txt_set(id, text)
    if id and _AM.texts[id] then
        _AM.texts[id].text = text
    end
end

function txt_style(id, style)
    if id and _AM.texts[id] then
        _AM.texts[id].style = style
    end
end

function canvas_add(x, y, w, h, cb)
    local id = _AM.next_node_id
    _AM.next_node_id = id + 1
    _AM.canvases[id] = {
        id = id, x = x, y = y, w = w, h = h, cb = cb, visible = true
    }
    if cb then
        canvas_draw(id, cb)
    end
    return id
end

function canvas_draw(id, cb)
    if cb == nil then
        error("attempt to call a nil value (canvas_draw requires callback)")
    end
    if _AM.in_draw then
        error("You cannot call canvas_draw within a draw callback.")
    end
    _AM.in_draw = true
    local ok, err = pcall(cb)
    _AM.in_draw = false
    if not ok then error(err) end
end

function _rect(x, y, w, h) table.insert(_AM.drawn_commands, {"rect", x, y, w, h}) end
function _circle(cx, cy, r) table.insert(_AM.drawn_commands, {"circle", cx, cy, r}) end
function _triangle(x1, y1, x2, y2, x3, y3) table.insert(_AM.drawn_commands, {"triangle", x1, y1, x2, y2, x3, y3}) end
function _move_to(x, y) table.insert(_AM.drawn_commands, {"move_to", x, y}) end
function _line_to(x, y) table.insert(_AM.drawn_commands, {"line_to", x, y}) end
function _stroke(color, width) table.insert(_AM.drawn_commands, {"stroke", color, width}) end
function _fill(color) table.insert(_AM.drawn_commands, {"fill", color}) end
function _txt(text, style, x, y) table.insert(_AM.drawn_commands, {"txt", text, style, x, y}) end

function sound_add(file, vol)
    local id = _AM.next_node_id
    _AM.next_node_id = id + 1
    _AM.sounds[id] = { id = id, file = file, volume = vol or 1.0, state = "stopped" }
    return id
end

function sound_volume(id, vol) if id and _AM.sounds[id] then _AM.sounds[id].volume = vol end end
function sound_play(id) if id and _AM.sounds[id] then _AM.sounds[id].state = "playing" end end
function sound_loop(id) if id and _AM.sounds[id] then _AM.sounds[id].state = "looping" end end
function sound_stop(id) if id and _AM.sounds[id] then _AM.sounds[id].state = "stopped" end end
"""


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


class AirManager:
    """Simulated Air Manager 4.2 runtime executing instrument Lua code."""

    def __init__(self):
        self.L = _LUA.luaL_newstate()
        if not self.L:
            raise RuntimeError("Failed to allocate Lua state")
        _LUA.luaL_openlibs(self.L)
        self._exec_string(PREAMBLE, "<am_preamble>")
        self.instrument_name = None

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
        """Load an instrument's lib/*.lua files and then logic.lua."""
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

    def write_si_variable(self, name, value):
        """Write a value to a Sim Innovations variable and trigger subscribers."""
        if isinstance(value, bool):
            val_str = "true" if value else "false"
        elif isinstance(value, (int, float)):
            val_str = str(value)
        elif isinstance(value, str):
            val_str = f'"{value}"'
        else:
            val_str = "nil"
        self.eval(f"si_variable_write('{name}', {val_str})")

    def read_si_variable(self, name):
        """Read the current value of a Sim Innovations variable."""
        return self.eval(f"return si_variable_read('{name}')")

    def write_dataref(self, name, kind, value):
        """Write a value to an X-Plane dataref and trigger subscribers."""
        if isinstance(value, bool):
            val_str = "true" if value else "false"
        elif isinstance(value, (int, float)):
            val_str = str(value)
        elif isinstance(value, str):
            val_str = f'"{value}"'
        else:
            val_str = "nil"
        self.eval(f"xpl_dataref_write('{name}', '{kind}', {val_str})")

    def read_dataref(self, name):
        """Read current dataref value."""
        return self.eval(f"return _AM.datarefs['{name}'] and _AM.datarefs['{name}'].value or nil")

    def get_commands(self):
        """Return list of invoked X-Plane commands."""
        return self.eval("return _AM.commands")

    def step_time(self, ms):
        """Advance simulated Air Manager clock by ms and invoke expired timers."""
        self.eval(f"_AM_step_time({int(ms)})")

    def click_button(self, btn_id):
        """Trigger button press then release."""
        self.press_button(btn_id)
        self.release_button(btn_id)

    def press_button(self, btn_id):
        self.eval(f"if _AM.buttons[{btn_id}] and _AM.buttons[{btn_id}].press_cb then _AM.buttons[{btn_id}].press_cb() end")

    def release_button(self, btn_id):
        self.eval(f"if _AM.buttons[{btn_id}] and _AM.buttons[{btn_id}].release_cb then _AM.buttons[{btn_id}].release_cb() end")

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

    def turn_dial(self, dial_id, direction):
        self.eval(f"if _AM.dials[{dial_id}] and _AM.dials[{dial_id}].turn_cb then _AM.dials[{dial_id}].turn_cb({direction}) end")

    def turn_dial_matching(self, direction, pattern=None, x=None, y=None):
        d_id = self.find_dial_matching(pattern, x, y)
        self.turn_dial(d_id, direction)
        return d_id

    def press_dial(self, dial_id):
        self.eval(f"if _AM.dials[{dial_id}] and _AM.dials[{dial_id}].press_cb then _AM.dials[{dial_id}].press_cb() end")

    def release_dial(self, dial_id):
        self.eval(f"if _AM.dials[{dial_id}] and _AM.dials[{dial_id}].release_cb then _AM.dials[{dial_id}].release_cb() end")

    def click_dial(self, dial_id):
        self.press_dial(dial_id)
        self.release_dial(dial_id)

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

    def press_dial_matching(self, pattern=None, x=None, y=None):
        d_id = self.find_dial_matching(pattern, x, y)
        self.press_dial(d_id)
        return d_id

    def release_dial_matching(self, pattern=None, x=None, y=None):
        d_id = self.find_dial_matching(pattern, x, y)
        self.release_dial(d_id)
        return d_id

    def click_dial_matching(self, pattern=None, x=None, y=None):
        d_id = self.find_dial_matching(pattern, x, y)
        self.click_dial(d_id)
        return d_id

    def turn_dial_matching(self, direction, pattern=None, x=None, y=None):
        d_id = self.find_dial_matching(pattern, x, y)
        self.turn_dial(d_id, direction)
        return d_id

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

    def is_visible(self, node_id):
        return self.eval(f"""
            local n = _AM.images[{node_id}] or _AM.texts[{node_id}] or _AM.canvases[{node_id}]
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

    def close(self):
        if self.L:
            _LUA.lua_close(self.L)
            self.L = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
