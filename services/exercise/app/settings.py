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


