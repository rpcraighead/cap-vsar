"""
Everything the console reads from its environment, in one place (C15-1).

main.py held the database path, the log configuration, the retention window,
the seed scenario and the effect defaults interleaved with the request
handlers, so "what does this service actually take from its environment" could
only be answered by reading a thousand lines. Import from here.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

DB = os.environ.get("CAPVSAR_DB", "/data/exercise.db")
STATIC = Path(__file__).parent / "static"

LOG_LEVEL = os.environ.get("CAPVSAR_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
log = logging.getLogger("capvsar.console")

# How much position history to keep. A three-hour sortie at 2 s per aircraft is
# ~5,400 rows per aircraft, which is fine; what is not fine is every sortie
# since the console was built sitting in the same table and /track reading all
# of it. Retention is by sortie, not by row age: a debrief of last week's
# exercise must still replay in full.
POSITION_RETENTION_SORTIES = int(os.environ.get("CAPVSAR_KEEP_SORTIES", "20"))
TRACK_PAGE_DEFAULT = 5000
TRACK_PAGE_MAX = 50000

ALERT_COLUMNS = [
    ("alert_kind", "TEXT"), ("alert_text", "TEXT"),
    ("alert_lat", "REAL"), ("alert_lon", "REAL"), ("alert_radius_nm", "REAL"),
]



DEFAULT_EFFECTS = {
    "radio_horizon": True, "burst_cadence": True,
    "cone_of_confusion": True, "multipath": False,
    "multipath_offset_deg": 40.0,
    "airframe_shadowing": False,
    "df_antenna_profile": "c182_belly",
    "wing_null_max_loss_db": 24.0,
    # T33: tactical-net audio degrades with reach to the fixed radio sites
    # (static and dropouts, app/radio_link.py). radio_conditions 0..1 scales
    # the signal margin for weather or atmospherics; 1.0 is a clear day.
    "radio_reach": True,
    "radio_conditions": 1.0,
}

SEED = {
    "name": "C-1  Palomar ILS - 121.5 ELT at ESCON",
    "notes": ("121.5 ELT on the ground at the ESCON intermediate fix on the KCRQ "
              "ILS, where the plate calls for 3,300 ft. No satellite alert. SoCal "
              "Approach protects the approach altitude and issues blocks above and "
              "below. Drawn from an actual unit sortie."),
    "beacon_lat": 33.1700, "beacon_lon": -117.0792, "beacon_elev_ft": 700.0,
    "band": "121.5", "power": 1.0,
    "effects": {**DEFAULT_EFFECTS, "burst_cadence": False, "multipath": True},
    # The alert is what mission base is given. It is NOT the beacon position -
    # 121.5 has not been satellite-monitored since 2009, so this one arrives as
    # reports with no position at all.
    "alert_kind": "121.5 pilot report - no position",
    "alert_text": ("Multiple reports of a 121.5 MHz ELT signal in the McClellan-Palomar "
                   "(KCRQ) approach area. No satellite alert and no Doppler position. "
                   "Search area is the approach corridor. Expect SoCal Approach to "
                   "protect the ILS altitude - request blocks above and below."),
    "alert_lat": 33.1283, "alert_lon": -117.2800, "alert_radius_nm": 12.0,
}

# Fixed radio sites for this exercise (T31; model and reach rules in
# app/radio_sites.py, design in docs/RADIO_SITES.md). Positions are data so
# another exercise can put the base and the repeater elsewhere (Palomar, say)
# without a code change: set CAPVSAR_RADIO_SITES to a JSON file of the same
# shape. Antenna heights are placeholders until the user confirms them.
RADIO_SITES = [
    # Gillespie Field airport reference point and field elevation: OurAirports
    # airports.csv (2026-10-12) as loaded into the flight planner's
    # services/flightplanner/data/aviation_data.db, row KSEE
    # (32.826198577881, -116.97200012207, 388 ft). The repository's own KSEE
    # 27R threshold survey (services/ai_pilot/flight_controller.py) gives the
    # same 388 ft field elevation.
    {"id": "BASE-KSEE", "role": "base_antenna", "name": "Mission Base, Gillespie Field (KSEE)",
     "lat": 32.826199, "lon": -116.972000, "ground_elev_ft": 388.0, "antenna_agl_ft": 30.0},
    # Julian VORTAC: X-Plane 12 "Resources/default data/earth_nav.dat",
    # line 22664: "3  33.140458333 -116.585936111  5560  11400 ... JLI ENRT K2
    # JULIAN VORTAC" (row type 3 = VOR, elevation 5,560 ft MSL, 114.00 MHz).
    {"id": "RPT-JLI", "role": "repeater", "name": "Julian (JLI VORTAC)",
     "lat": 33.140458, "lon": -116.585936, "ground_elev_ft": 5560.0, "antenna_agl_ft": 40.0},
]
# National CAP pair: the repeater transmits 148.125 and listens on 143.550
# ("primary"); "secondary" is 148.150 / 143.700 (docs/CA_WING_REPEATERS.md).
REPEATER_PAIR = "primary"


