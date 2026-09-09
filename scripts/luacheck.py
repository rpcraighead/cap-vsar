import ctypes, sys
L = ctypes.CDLL("/usr/lib/x86_64-linux-gnu/liblua5.4.so.0")
L.luaL_newstate.restype = ctypes.c_void_p
L.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
L.luaL_loadstring.restype = ctypes.c_int
L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
L.lua_tolstring.restype = ctypes.c_char_p

rc_all = 0
for path in sys.argv[1:]:
    st = L.luaL_newstate()
    src = open(path, 'rb').read()
    r = L.luaL_loadstring(st, src)
    if r == 0:
        print(f"OK    {path}")
    else:
        msg = L.lua_tolstring(st, -1, None)
        print(f"FAIL  {path}\n      {msg.decode(errors='replace')}")
        rc_all = 1
sys.exit(rc_all)
