"""
CAP V-SAR - DF propagation engine.

Phase 1 of the implementation plan. This runs inside X-Plane because two things
it must do are only possible here: probing real terrain for line-of-sight, and
reading aircraft state at frame rate.

It publishes what the direction finder would show as custom datarefs, which any
external program can read - Air Manager subscribes to these exactly as it would
to a stock dataref:

    cap/df/valid          int    1 when a usable bearing exists
    cap/df/bearing_rel    float  degrees relative to the nose - drives the needle
    cap/df/bearing_true   float  degrees true
    cap/df/signal         float  0..1 signal strength - drives the bar
    cap/df/distance_nm    float  slant range, for the instructor
    cap/df/in_cone        int    1 inside the cone of confusion
    cap/df/blocked        int    1 when terrain is masking the signal
    cap/df/band           float  121.5 / 243 / 406

Beacon truth and effect switches arrive from the exercise console over HTTP on
a background thread, so no network call ever runs in the flight loop. The same
thread reports position back, which makes this the sim bridge as well - one
component rather than the two the plan sketched.

    cap/scenario/active       int
    cap/scenario/beacon_lat   double   (writable, for offline testing)
    cap/scenario/beacon_lon   double
    cap/scenario/beacon_elev  float    feet MSL
"""
import json
import math
import threading
import time
import urllib.request

import xp

CONSOLE = "http://192.0.2.151:8700"
CALLSIGN = "CAP-1"
POLL_S = 3.0            # scenario refresh
REPORT_S = 2.0          # position report
LOOP_S = 0.25           # DF recompute
R_NM = 3440.065
M_PER_NM = 1852.0
FT_PER_M = 3.28084
LOS_SAMPLES = 24        # terrain probes along the path


def bearing_true(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2 - lon1)
    la1, la2 = math.radians(lat1), math.radians(lat2)
    y = math.sin(dlon) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def distance_nm(lat1, lon1, lat2, lon2):
    la1, la2 = math.radians(lat1), math.radians(lat2)
    dla, dlo = la2 - la1, math.radians(lon2 - lon1)
    a = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * R_NM * math.asin(min(1.0, math.sqrt(a)))


def interp(lat1, lon1, lat2, lon2, f):
    """Good enough over search-area distances, and far cheaper than a slerp."""
    return lat1 + (lat2 - lat1) * f, lon1 + (lon2 - lon1) * f


class PythonInterface:
    def __init__(self):
        self.probe = None
        self.loop = None
        self.accessors = []
        self.stop = threading.Event()

        # published DF state
        self.valid = 0
        self.bearing_rel = 0.0
        self.bearing_true = 0.0
        self.signal = 0.0
        self.distance = 0.0
        self.in_cone = 0
        self.blocked = 0

        # scenario, replaced wholesale by the network thread
        self.scn = {"active": 0, "lat": 0.0, "lon": 0.0, "elev_ft": 0.0,
                    "band": 121.5, "power": 1.0, "effects": {}}
        self.started = time.time()
        self.pos = (0.0, 0.0, 0.0, 0.0)   # lat, lon, alt_ft, hdg_true

    # ------------------------------------------------------------- lifecycle
    def XPluginStart(self):
        self.dr_lat = xp.findDataRef("sim/flightmodel/position/latitude")
        self.dr_lon = xp.findDataRef("sim/flightmodel/position/longitude")
        self.dr_elev = xp.findDataRef("sim/flightmodel/position/elevation")
        self.dr_psi = xp.findDataRef("sim/flightmodel/position/psi")

        def f(name, get):
            self.accessors.append(
                xp.registerDataAccessor(name, xp.Type_Float, 0, readFloat=lambda r, g=get: g()))

        def i(name, get):
            self.accessors.append(
                xp.registerDataAccessor(name, xp.Type_Int, 0, readInt=lambda r, g=get: g()))

        i("cap/df/valid", lambda: self.valid)
        f("cap/df/bearing_rel", lambda: self.bearing_rel)
        f("cap/df/bearing_true", lambda: self.bearing_true)
        f("cap/df/signal", lambda: self.signal)
        f("cap/df/distance_nm", lambda: self.distance)
        i("cap/df/in_cone", lambda: self.in_cone)
        i("cap/df/blocked", lambda: self.blocked)
        f("cap/df/band", lambda: float(self.scn.get("band", 121.5)))
        i("cap/scenario/active", lambda: int(self.scn.get("active", 0)))

        # writable, so a scenario can be set by hand with no console reachable
        self.accessors.append(xp.registerDataAccessor(
            "cap/scenario/beacon_lat", xp.Type_Double, 1,
            readDouble=lambda r: float(self.scn["lat"]),
            writeDouble=lambda r, v: self.scn.__setitem__("lat", v)))
        self.accessors.append(xp.registerDataAccessor(
            "cap/scenario/beacon_lon", xp.Type_Double, 1,
            readDouble=lambda r: float(self.scn["lon"]),
            writeDouble=lambda r, v: self.scn.__setitem__("lon", v)))
        self.accessors.append(xp.registerDataAccessor(
            "cap/scenario/beacon_elev", xp.Type_Float, 1,
            readFloat=lambda r: float(self.scn["elev_ft"]),
            writeFloat=lambda r, v: self.scn.__setitem__("elev_ft", v)))

        self.probe = xp.createProbe(xp.ProbeY)
        xp.log("CAP V-SAR: DF engine started, %d datarefs published" % len(self.accessors))
        return "CAP V-SAR DF", "org.cap.vsar.df", "Direction finder propagation engine"

    def XPluginEnable(self):
        self.loop = xp.createFlightLoop(self.flight_loop, xp.FlightLoop_Phase_AfterFlightModel)
        xp.scheduleFlightLoop(self.loop, LOOP_S)
        self.net = threading.Thread(target=self.net_worker, daemon=True)
        self.net.start()
        return 1

    def XPluginDisable(self):
        self.stop.set()
        if self.loop:
            xp.destroyFlightLoop(self.loop)
            self.loop = None

    def XPluginStop(self):
        for a in self.accessors:
            xp.unregisterDataAccessor(a)
        self.accessors = []
        if self.probe:
            xp.destroyProbe(self.probe)
            self.probe = None

    def XPluginReceiveMessage(self, inFrom, inMsg, inParam):
        pass

    # -------------------------------------------------------------- terrain
    def terrain_ft(self, lat, lon):
        """Terrain elevation in feet MSL, or None if outside loaded scenery."""
        x, y, z = xp.worldToLocal(lat, lon, 0.0)
        info = xp.probeTerrainXYZ(self.probe, x, y, z)
        if info.result != xp.ProbeHitTerrain:
            return None
        _, _, alt_m = xp.localToWorld(info.locationX, info.locationY, info.locationZ)
        return alt_m * FT_PER_M

    def line_of_sight_blocked(self, ac_lat, ac_lon, ac_ft, b_lat, b_lon, b_ft):
        """
        Sample terrain along the path and compare it to the straight ray.

        This is the reason the engine lives in the simulator: no server-side
        model can see the ridge between the aircraft and the beacon.
        """
        for k in range(1, LOS_SAMPLES):
            fr = k / float(LOS_SAMPLES)
            lat, lon = interp(ac_lat, ac_lon, b_lat, b_lon, fr)
            ground = self.terrain_ft(lat, lon)
            if ground is None:
                continue                      # unloaded scenery: assume clear
            ray = b_ft + (ac_ft - b_ft) * fr  # linear, adequate at these ranges
            if ground > ray + 50.0:           # 50 ft margin for probe noise
                return True
        return False

    # ------------------------------------------------------------ main loop
    def flight_loop(self, sinceLast, elapsed, counter, refCon):
        try:
            self.compute()
        except Exception as e:
            xp.log("CAP V-SAR: compute failed: %s" % e)
        return LOOP_S

    def compute(self):
        lat = xp.getDatad(self.dr_lat)
        lon = xp.getDatad(self.dr_lon)
        alt_ft = xp.getDatad(self.dr_elev) * FT_PER_M
        hdg = xp.getDataf(self.dr_psi)
        self.pos = (lat, lon, alt_ft, hdg)

        s = self.scn
        if not s.get("active"):
            self.valid, self.signal, self.blocked, self.in_cone = 0, 0.0, 0, 0
            return

        b_lat, b_lon, b_ft = s["lat"], s["lon"], s["elev_ft"]
        eff = s.get("effects", {})

        d = distance_nm(lat, lon, b_lat, b_lon)
        self.distance = d
        brg = bearing_true(lat, lon, b_lat, b_lon)

        # radio horizon: 1.23 * sqrt(height above the beacon)
        if eff.get("radio_horizon", True):
            horizon = 1.23 * math.sqrt(max(alt_ft - b_ft, 0.0))
            if d > horizon:
                self.valid, self.signal, self.blocked = 0, 0.0, 0
                return

        # terrain masking - the effect only the simulator can produce
        blocked = False
        if eff.get("terrain_masking", True) and d > 0.3:
            blocked = self.line_of_sight_blocked(lat, lon, alt_ft, b_lat, b_lon, b_ft)
        self.blocked = 1 if blocked else 0

        signal = min(1.0, float(s.get("power", 1.0)) * 25.0 / max(d * d, 0.25))
        if blocked:
            signal *= 0.06                    # heavy attenuation, not silence
        self.signal = signal

        if signal < 0.08:
            self.valid = 0
            return

        # cone of confusion
        agl = max(alt_ft - b_ft, 1.0)
        cone_nm = (agl / 6076.0) * math.tan(math.radians(30.0))
        if eff.get("cone_of_confusion", True) and d < cone_nm:
            self.in_cone, self.valid = 1, 0
            return
        self.in_cone = 0

        # 406 transmits a burst about every 50 s; hold the needle between them
        if float(s.get("band", 121.5)) > 400 and eff.get("burst_cadence", True):
            if (time.time() - self.started) % 50.0 > 1.5:
                self.valid = 1                # hold last bearing
                return

        if eff.get("multipath", False):
            if int((time.time() - self.started) / 12.0) % 3 == 0:
                brg = (brg + float(eff.get("multipath_offset_deg", 40.0))) % 360.0

        self.bearing_true = brg
        self.bearing_rel = (brg - hdg) % 360.0
        self.valid = 1

    # ------------------------------------------------------- network thread
    def net_worker(self):
        last_report = 0.0
        while not self.stop.is_set():
            try:
                with urllib.request.urlopen(CONSOLE + "/api/state", timeout=4) as r:
                    st = json.load(r)
                sc = st.get("scenario") or {}
                so = st.get("sortie") or {}
                running = bool(so and not so.get("stopped"))
                # beacon truth is withheld until reveal, so fall back to whatever
                # was written into the writable datarefs
                if running and sc.get("beacon_lat") is not None:
                    self.scn.update({"active": 1, "lat": sc["beacon_lat"],
                                     "lon": sc["beacon_lon"],
                                     "elev_ft": sc.get("beacon_elev_ft", 0.0),
                                     "band": float(sc.get("band", 121.5)),
                                     "power": sc.get("power", 1.0),
                                     "effects": sc.get("effects", {})})
                elif running:
                    self.scn["active"] = 1
                    self.scn["effects"] = sc.get("effects", self.scn["effects"])
                else:
                    self.scn["active"] = 0
            except Exception:
                pass                          # console offline is not an error

            now = time.time()
            if now - last_report >= REPORT_S:
                last_report = now
                try:
                    lat, lon, alt_ft, hdg = self.pos
                    body = json.dumps({"callsign": CALLSIGN, "lat": lat, "lon": lon,
                                       "alt_ft": alt_ft, "hdg_true": hdg}).encode()
                    req = urllib.request.Request(
                        CONSOLE + "/api/positions", data=body,
                        headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=4).read()
                except Exception:
                    pass
            self.stop.wait(POLL_S)
