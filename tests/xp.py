"""Minimal stand-in for XPPython3's xp module, enough to drive the DF engine
offline. Datarefs are held in a dict keyed by name so a test can read and write
them exactly as Air Manager would."""
Type_Unknown, Type_Int, Type_Float, Type_Double = 0, 1, 2, 4
Type_FloatArray, Type_IntArray, Type_Data = 8, 16, 32
ProbeY, ProbeHitTerrain = 0, 0
FlightLoop_Phase_AfterFlightModel = 1

REFS = {}          # name -> dict of callbacks
SIM = {"lat": 0.0, "lon": 0.0, "elev_m": 0.0, "psi": 0.0,
       "phi": 0.0, "theta": 0.0,
       "paused": 0}      # sim/time/paused, which the engine freezes on (P2-6)
TERRAIN_FT = 0.0   # flat ground unless a test raises it
TERRAIN_FN = None  # optional callable (lat, lon) -> elevation in feet
LOG = []


class _Ref:
    def __init__(self, name):
        self.name = name


def log(msg):
    LOG.append(msg)


def findDataRef(name):
    return _Ref(name)


def getDatad(ref):
    return {"sim/flightmodel/position/latitude": SIM["lat"],
            "sim/flightmodel/position/longitude": SIM["lon"],
            "sim/flightmodel/position/elevation": SIM["elev_m"]}[ref.name]


def getDataf(ref):
    # true_psi is true heading; psi is the local OpenGL-frame heading. A test
    # that sets only "psi" gets the same value from both, so the distinction
    # only shows up where a test deliberately sets them apart (P-12).
    return {"sim/flightmodel/position/psi": SIM["psi"],
            "sim/flightmodel/position/true_psi": SIM.get("true_psi", SIM["psi"]),
            "sim/flightmodel/position/phi": SIM["phi"],
            "sim/flightmodel/position/theta": SIM["theta"]}[ref.name]


def getDatai(ref):
    return {"sim/time/paused": SIM["paused"]}[ref.name]


# Which read callback each declared type may carry, and the Python type X-Plane
# (via XPPython3) needs it to return. A float accessor that returns an int, or
# an int accessor that returns a float, is the kind of mistake that only shows
# up in the sim as a dead dataref, so the stub refuses it at the callback.
_READ_FOR_TYPE = {Type_Int: "readInt", Type_Float: "readFloat",
                  Type_Double: "readDouble", Type_Data: "readData"}
_PY_TYPE_FOR_READ = {"readInt": int, "readFloat": float,
                     "readDouble": float, "readData": int}   # readData -> count


def _checked(name, key, fn):
    want = _PY_TYPE_FOR_READ[key]

    def read(*args, **kw):
        value = fn(*args, **kw)
        if type(value) is not want:     # bool and numpy scalars are not int/float
            raise TypeError("%s: %s returned %s, the declared type needs %s"
                            % (name, key, type(value).__name__, want.__name__))
        return value
    return read


def registerDataAccessor(name, dataType=Type_Unknown, writable=-1, **kw):
    """Record the declared type, and hold the read callback to it."""
    if dataType in _READ_FOR_TYPE:
        wanted = _READ_FOR_TYPE[dataType]
        stray = [k for k in kw if k.startswith("read") and k != wanted]
        if stray or (wanted not in kw):
            raise TypeError("%s: declared type %d wants %s, got %s"
                            % (name, dataType, wanted, sorted(kw)))
    REFS[name] = {k: (_checked(name, k, v) if k in _PY_TYPE_FOR_READ else v)
                  for k, v in kw.items()}
    REFS[name]["dataType"] = dataType
    REFS[name]["writable"] = writable
    return _Ref(name)


def unregisterDataAccessor(ref):
    REFS.pop(ref.name, None)


def createProbe(t=ProbeY):
    return object()


def destroyProbe(p):
    pass


class _Info:
    result = ProbeHitTerrain
    locationX = locationY = locationZ = 0.0

    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.locationX = x
        self.locationY = y
        self.locationZ = z


def worldToLocal(lat, lon, alt):
    return float(lat), float(lon), float(alt)


def localToWorld(x, y, z):
    if TERRAIN_FN is not None:
        elev_ft = float(TERRAIN_FN(x, y))
    else:
        elev_ft = TERRAIN_FT
    return x, y, elev_ft / 3.28084


def probeTerrainXYZ(probe, x, y, z):
    return _Info(x, y, z)


def createFlightLoop(cb, phase):
    return object()


def scheduleFlightLoop(loop, s):
    pass


def destroyFlightLoop(loop):
    pass


# ---- helpers a test uses to act like Air Manager -------------------------
def read(name):
    cbs = REFS[name]
    for key in ("readInt", "readFloat", "readDouble"):
        if cbs.get(key):
            return cbs[key](None)
    if cbs.get("readData"):
        out = []
        cbs["readData"](None, out, 0, -1)
        return bytes(out).decode("ascii", "replace")
    raise KeyError(name)


def write(name, value):
    cbs = REFS[name]
    for key in ("writeInt", "writeFloat", "writeDouble"):
        if cbs.get(key):
            return cbs[key](None, value)
    raise KeyError("not writable: " + name)
