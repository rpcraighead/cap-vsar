"""Minimal stand-in for XPPython3's xp module, enough to drive the DF engine
offline. Datarefs are held in a dict keyed by name so a test can read and write
them exactly as Air Manager would."""
Type_Unknown, Type_Int, Type_Float, Type_Double = 0, 1, 2, 4
Type_FloatArray, Type_IntArray, Type_Data = 8, 16, 32
ProbeY, ProbeHitTerrain = 0, 0
FlightLoop_Phase_AfterFlightModel = 1

REFS = {}          # name -> dict of callbacks
SIM = {"lat": 0.0, "lon": 0.0, "elev_m": 0.0, "psi": 0.0,
       "phi": 0.0, "theta": 0.0}
TERRAIN_FT = 0.0   # flat ground unless a test raises it
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
    return {"sim/flightmodel/position/psi": SIM["psi"],
            "sim/flightmodel/position/phi": SIM["phi"],
            "sim/flightmodel/position/theta": SIM["theta"]}[ref.name]


def registerDataAccessor(name, dataType=Type_Unknown, writable=-1, **kw):
    REFS[name] = kw
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


def worldToLocal(lat, lon, alt):
    return 0.0, 0.0, 0.0


def localToWorld(x, y, z):
    return 0.0, 0.0, TERRAIN_FT / 3.28084


def probeTerrainXYZ(probe, x, y, z):
    return _Info()


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
