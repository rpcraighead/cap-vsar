from flask import Flask, render_template, request, jsonify, send_from_directory, abort, Response
from collections import deque
from datetime import datetime, timedelta, timezone
import fcntl
import json
import hashlib
import math
import re
import os
import csv
import sqlite3
import requests
from io import StringIO
import threading
import time
from urllib.parse import urlsplit
from werkzeug.exceptions import HTTPException
from werkzeug.http import dump_cookie
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    from pygeomag import GeoMag
    _geomag = GeoMag()
except Exception:
    _geomag = None  # headings fall back to true (mag_var = 0)

app = Flask(__name__)
# O-8: the planner is reachable only through the compose-network Caddy proxy.
# Trust exactly that one hop so Flask sees the external HTTPS origin and the
# /planner prefix which Caddy stripped before forwarding the request.
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# L-12: the database lives in a DIRECTORY, not as a bind-mounted file.
#
# Compose used to mount ./services/flightplanner/data/aviation_data.db onto
# /app/aviation_data.db - a single file. SQLite writes its rollback journal and
# WAL beside the database, and those siblings are NOT part of the mount, so
# they landed in the container's own writable layer. A crash mid-write then
# left the journal on a layer that is discarded when the container is replaced,
# and the database with no way to roll back. O-3 papered over the symptom by
# pre-creating the file.
#
# DATA_DIR is overridable so a test or a local run can point somewhere else;
# the default keeps a plain `python app.py` checkout working exactly as before.
DATA_DIR = os.environ.get('CAPVSAR_PLANNER_DATA', os.path.join(BASE_DIR, 'data'))
_legacy_db = os.path.join(BASE_DIR, 'aviation_data.db')
DATABASE_PATH = os.environ.get('DATABASE_PATH') or os.path.join(
    DATA_DIR, 'aviation_data.db')
if not os.path.exists(DATABASE_PATH) and os.path.exists(_legacy_db):
    # A checkout that still has the old file in place keeps using it rather
    # than silently starting with an empty database.
    DATABASE_PATH = _legacy_db
try:
    os.makedirs(os.path.dirname(DATABASE_PATH) or '.', exist_ok=True)
except OSError:
    pass
DATABASE_UPDATE_LOCK_PATH = '/tmp/capvsar-flightplanner-aviation.update.lock'
DATABASE_UPDATE_STATUS_PATH = '/tmp/capvsar-flightplanner-aviation.update.json'
DOCS_DIR = os.path.join(BASE_DIR, 'docs')

# Documentation available from the UI: url slug -> (filename, title)
DOCS = {
    'guide':      ('USER_GUIDE.md', 'User Guide'),
    'user_guide': ('USER_GUIDE.md', 'User Guide'),
    'quickstart': ('QUICKSTART.md', 'Quick Start'),
}
CHARTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'charts')

# CAP V-SAR exercise console. Server-configured only - see the security note on
# sar_export_vsar() below for why this is never taken from the request body.
VSAR_CONSOLE_URL = os.environ.get('VSAR_CONSOLE_URL', 'http://192.0.2.151:8700').rstrip('/')
AVIATION_WEATHER_BASE = 'https://aviationweather.gov/api/data'

# Winds/temps aloft: Open-Meteo pressure-level data (GFS), no API key required.
# Pressure levels bracket the standard FB altitudes (~2.5k–14k ft).
OPEN_METEO_URL = 'https://api.open-meteo.com/v1/forecast'
WINDS_LEVELS_HPA = [925, 900, 850, 800, 700, 600]
WINDS_TARGET_ALT = [3000, 6000, 9000, 12000]
_winds_cache = {}  # (round(lat,1), round(lon,1), 'YYYYMMDDHH') -> winds dict
# L-10: this grew without limit. The key carries an hour stamp, so every hour
# minted a fresh generation and the old one was never dropped - a long-running
# base station accumulated every point anyone had ever planned through.
_WINDS_CACHE_MAX = 512


def _winds_cache_put(key, value):
    """Insert, evicting oldest-first once the cache is full."""
    if len(_winds_cache) >= _WINDS_CACHE_MAX:
        for stale in list(_winds_cache)[:len(_winds_cache) - _WINDS_CACHE_MAX + 1]:
            _winds_cache.pop(stale, None)
    _winds_cache[key] = value

MAX_PARALLEL_DIMENSION_NM = 50.0
MAX_PARALLEL_LEGS = 200
# L2-2: the most waypoints one exported flight plan may carry. 99 is the G1000
# flight-plan limit and sits just under the figure usually quoted for X-Plane's
# FMS importer (100). The real X-Plane 12 limit has NOT been verified against
# the simulator, so this is the conservative of the two. It is a ceiling on the
# waypoints in the list (the pattern); the .fms file adds the departure and
# destination airport records on top of them.
MAX_FMS_WAYPOINTS = 99
# Most points one terrain-profile or export request may carry.
MAX_REQUEST_POINTS = 500

# Where "no route typed" and the console push fall back to, and the sample
# datum the SAR dialog is pre-filled with. These used to be literals scattered
# through app.py, the template and app.js (review L2 improvement: hard-coded
# defaults). Set CAPVSAR_DEFAULT_AIRPORT / CAPVSAR_DEFAULT_DATUM for another
# base. The default datum is a pre-fill only: the server never plans on it
# (L2-1).
def _env_setting(name, fallback, upper=False):
    value = (os.environ.get(name) or fallback).strip()
    return value.upper() if upper else value


DEFAULT_AIRPORT = _env_setting('CAPVSAR_DEFAULT_AIRPORT', 'KSEE', upper=True)
DEFAULT_DATUM = _env_setting('CAPVSAR_DEFAULT_DATUM', '@33.1700,-117.0792')
VSAR_EXPORT_RATE_LIMIT = 5
VSAR_EXPORT_RATE_WINDOW_S = 60.0
_vsar_export_attempts = {}
_vsar_export_rate_lock = threading.Lock()

# Online-only base layers (Satellite, Street), offered by /api/tile-sources
# unless CAPVSAR_TILES_OFFLINE is set. Not cached by the planner.
ONLINE_LAYER_SOURCES = {
    'sat': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    'osm': 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
}

# FAA official tile sources via ArcGIS
TILE_SOURCES = {
    'vfr': 'https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services/VFR_Sectional/MapServer/tile/{z}/{y}/{x}',
    'ifr_low': 'https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services/IFR_AreaLow/MapServer/tile/{z}/{y}/{x}',
    'ifr_high': 'https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services/IFR_High/MapServer/tile/{z}/{y}/{x}',
}

# Chart regions - Southwest US coverage
CHART_REGIONS = {
    'socal': {'name': 'Southern California', 'bounds': [[32.0, -121.0], [35.5, -114.0]]},
    'phoenix': {'name': 'Phoenix/Arizona', 'bounds': [[31.0, -115.0], [35.5, -109.0]]},
    'norcal': {'name': 'Northern California', 'bounds': [[36.0, -124.0], [40.0, -119.0]]},
}

OURAIRPORTS_URLS = {
    'airports': 'https://davidmegginson.github.io/ourairports-data/airports.csv',
    'runways': 'https://davidmegginson.github.io/ourairports-data/runways.csv',
    'navaids': 'https://davidmegginson.github.io/ourairports-data/navaids.csv'
}

# Cessna 182T NAV III GFC 700, 182TIMBUS-01, revision 1 (20 Dec 2007).
# https://www.aeroelectric.com/Reference_Docs/Cessna/cessna-poh/C182T_2007_NavIII-G1000%2BGFC700_POH-PIM_fromCessna.pdf
# The user selected the POH SAMPLE aircraft as the simulation planning baseline.
# Its empty weight/moment are not a measurement of CAP 487 - they are a shared,
# sourced baseline, which only works if BOTH sides use the same one.
#
# L-7a, 2026-09-15: they did not. The builder specified 1,970 lb while this used
# 1,924 lb, so planner and simulator disagreed by 46 lb on every takeoff weight,
# CG and performance number for the same loading - and the crew reads both. The
# builder now carries 1,924 lb and an empty CG derived from the 70.9 moment
# rather than inherited from the stock C172S. tests/test_loading_baseline.py
# fails if the two drift apart again; change them together or not at all.
AIRCRAFT_DATABASE = {
    'CAP 487': {
        'name': 'CAP 487 - Cessna 182T NAV III (POH sample baseline)',
        # Figure 6-3, sample aircraft: pounds and thousand lb-in.
        'empty_weight': 1924, 'empty_weight_moment': 70.9,
        # Section 2-8 weight/CG limits; Section 1-5 engine specification.
        'max_takeoff_weight': 3100, 'max_landing_weight': 2950,
        'max_ramp_weight': 3110, 'engine_hp': 230,
        'cg_fwd_points': ((2250, 33.0), (2700, 35.5), (3100, 40.9)),
        'cg_aft_limit': 46.0,
        # Figures 6-3 and 6-5: average occupant and baggage A positions.
        # This form supports baggage A only (120 lb), not the B/C compartments.
        'arms': {'front_seats': 37.0, 'rear_seats': 74.0, 'baggage1': 97.0},
        'baggage1_max': 120, 'fuel_arm': 46.5,
        # Section 1-6 and Fig 6-3: 87 usable of 92 total US gal, 6 lb/gal.
        'usable_fuel': 87, 'total_fuel': 92, 'fuel_weight_per_gallon': 6.0,
        # Fig 5-8 sheet 1: engine start, taxi AND takeoff allowance, US gal.
        'taxi_fuel': 1.7,
        # Fig 5-9 sheets 1..9: standard-temperature column, 3100 lb,
        # recommended lean mixture, cowl flaps closed. Altitude -> RPM ->
        # manifold pressure in inHg -> (% MCP, KTAS, US gal/hour).
        # Above-80% rows exist only to interpolate; get_cruise rejects >80%.
        'cruise_performance': {0: {2000: {20: (49.0, 108.0, 9.2),
            21: (53.0, 112.0, 9.7),
            22: (56.0, 117.0, 10.2),
            23: (60.0, 120.0, 10.7),
            24: (64.0, 124.0, 11.3),
            25: (67.0, 127.0, 11.8),
            26: (71.0, 130.0, 12.4),
            27: (75.0, 133.0, 13.0)},
     2100: {20: (51.0, 111.0, 9.6),
            21: (55.0, 116.0, 10.1),
            22: (59.0, 120.0, 10.6),
            23: (63.0, 123.0, 11.2),
            24: (67.0, 127.0, 11.8),
            25: (71.0, 130.0, 12.4),
            26: (75.0, 133.0, 13.0),
            27: (79.0, 135.0, 13.7)},
     2200: {20: (54.0, 114.0, 9.9),
            21: (58.0, 119.0, 10.5),
            22: (62.0, 122.0, 11.1),
            23: (66.0, 126.0, 11.7),
            24: (71.0, 130.0, 12.3),
            25: (75.0, 133.0, 12.9),
            26: (79.0, 135.0, 13.6),
            27: (83.0, 137.0, 14.4)},
     2300: {20: (56.0, 116.0, 10.2),
            21: (60.0, 120.0, 10.8),
            22: (65.0, 124.0, 11.4),
            23: (69.0, 128.0, 12.0),
            24: (73.0, 132.0, 12.7),
            25: (78.0, 135.0, 13.4),
            26: (82.0, 137.0, 14.2)},
     2400: {20: (58.0, 118.0, 10.4),
            21: (62.0, 122.0, 11.1),
            22: (67.0, 127.0, 11.7),
            23: (71.0, 130.0, 12.4),
            24: (76.0, 133.0, 13.2),
            25: (81.0, 136.0, 14.0)}},
 2000: {2000: {20: (51.0, 112.0, 9.4),
               21: (54.0, 116.0, 10.0),
               22: (58.0, 120.0, 10.5),
               23: (62.0, 124.0, 11.0),
               24: (66.0, 127.0, 11.5),
               25: (69.0, 131.0, 12.1),
               26: (73.0, 134.0, 12.7)},
        2100: {20: (53.0, 115.0, 9.8),
               21: (57.0, 119.0, 10.4),
               22: (61.0, 123.0, 10.9),
               23: (65.0, 127.0, 11.5),
               24: (69.0, 131.0, 12.1),
               25: (73.0, 134.0, 12.7),
               26: (77.0, 137.0, 13.4)},
        2200: {20: (56.0, 118.0, 10.2),
               21: (60.0, 122.0, 10.8),
               22: (64.0, 126.0, 11.4),
               23: (69.0, 130.0, 12.0),
               24: (73.0, 134.0, 12.6),
               25: (77.0, 137.0, 13.3),
               26: (81.0, 139.0, 14.1)},
        2300: {20: (58.0, 120.0, 10.5),
               21: (62.0, 124.0, 11.1),
               22: (67.0, 128.0, 11.7),
               23: (71.0, 133.0, 12.4),
               24: (76.0, 136.0, 13.1),
               25: (80.0, 139.0, 13.9)},
        2400: {20: (60.0, 122.0, 10.7),
               21: (65.0, 126.0, 11.4),
               22: (69.0, 131.0, 12.1),
               23: (74.0, 134.0, 12.8),
               24: (79.0, 138.0, 13.6),
               25: (83.0, 140.0, 14.4)}},
 4000: {2000: {20: (52.0, 115.0, 9.7),
               21: (56.0, 120.0, 10.2),
               22: (60.0, 124.0, 10.7),
               23: (64.0, 128.0, 11.3),
               24: (68.0, 131.0, 11.8),
               25: (71.0, 135.0, 12.4)},
        2100: {20: (55.0, 119.0, 10.1),
               21: (59.0, 123.0, 10.6),
               22: (63.0, 127.0, 11.2),
               23: (67.0, 131.0, 11.8),
               24: (71.0, 135.0, 12.4),
               25: (75.0, 138.0, 13.0)},
        2200: {20: (58.0, 122.0, 10.4),
               21: (62.0, 126.0, 11.0),
               22: (66.0, 130.0, 11.7),
               23: (71.0, 134.0, 12.3),
               24: (75.0, 138.0, 13.0),
               25: (79.0, 141.0, 13.7)},
        2300: {20: (60.0, 124.0, 10.7),
               21: (65.0, 128.0, 11.4),
               22: (69.0, 133.0, 12.1),
               23: (74.0, 137.0, 12.8),
               24: (78.0, 140.0, 13.5),
               25: (83.0, 143.0, 14.3)},
        2400: {20: (62.0, 126.0, 11.1),
               21: (67.0, 131.0, 11.7),
               22: (72.0, 135.0, 12.5),
               23: (76.0, 139.0, 13.2),
               24: (81.0, 142.0, 14.0)}},
 6000: {2000: {19: (50.0, 114.0, 9.4),
               20: (54.0, 119.0, 9.9),
               21: (58.0, 123.0, 10.4),
               22: (62.0, 128.0, 11.0),
               23: (66.0, 132.0, 11.5)},
        2100: {19: (53.0, 118.0, 9.8),
               20: (57.0, 122.0, 10.3),
               21: (61.0, 127.0, 10.9),
               22: (65.0, 131.0, 11.5),
               23: (69.0, 135.0, 12.1)},
        2200: {19: (56.0, 121.0, 10.1),
               20: (60.0, 126.0, 10.7),
               21: (64.0, 130.0, 11.3),
               22: (69.0, 134.0, 12.0),
               23: (73.0, 138.0, 12.6)},
        2300: {19: (58.0, 123.0, 10.4),
               20: (62.0, 128.0, 11.0),
               21: (67.0, 133.0, 11.7),
               22: (71.0, 137.0, 12.4),
               23: (76.0, 141.0, 13.1)},
        2400: {19: (60.0, 126.0, 10.7),
               20: (65.0, 130.0, 11.4),
               21: (69.0, 135.0, 12.1),
               22: (74.0, 139.0, 12.8),
               23: (79.0, 143.0, 13.6)}},
 8000: {2000: {19: (52.0, 118.0, 9.6), 20: (56.0, 123.0, 10.1), 21: (60.0, 127.0, 10.7)},
        2100: {18: (50.0, 116.0, 9.4),
               19: (55.0, 121.0, 10.0),
               20: (59.0, 126.0, 10.6),
               21: (63.0, 131.0, 11.2)},
        2200: {18: (53.0, 119.0, 9.8),
               19: (57.0, 125.0, 10.4),
               20: (62.0, 130.0, 11.0),
               21: (66.0, 134.0, 11.6)},
        2300: {18: (55.0, 122.0, 10.1),
               19: (60.0, 127.0, 10.7),
               20: (64.0, 132.0, 11.3),
               21: (69.0, 137.0, 12.0)},
        2400: {18: (57.0, 124.0, 10.3),
               19: (62.0, 130.0, 11.0),
               20: (67.0, 135.0, 11.7),
               21: (72.0, 139.0, 12.5)}},
 10000: {2000: {18: (50.0, 116.0, 9.3), 19: (54.0, 122.0, 9.8), 20: (58.0, 127.0, 10.4)},
         2100: {18: (52.0, 120.0, 9.7), 19: (56.0, 125.0, 10.2), 20: (61.0, 130.0, 10.8)},
         2200: {18: (55.0, 123.0, 10.0), 19: (59.0, 129.0, 10.6), 20: (64.0, 134.0, 11.3)},
         2300: {18: (57.0, 126.0, 10.3),
                19: (62.0, 132.0, 11.0),
                20: (66.0, 137.0, 11.7),
                21: (71.0, 141.0, 12.4)},
         2400: {18: (59.0, 129.0, 10.6), 19: (64.0, 134.0, 11.3), 20: (69.0, 139.0, 12.1)}}},
        # Fig 5-8 sheet 1: maximum-rate climb, standard temperature, zero wind;
        # altitude -> (minutes from sea level, US gal, NM).
        'climb_performance': {
            0: (0, 0.0, 0), 2000: (2, 0.8, 3), 4000: (5, 1.5, 7),
            6000: (8, 2.3, 11), 8000: (11, 3.2, 16), 10000: (15, 4.2, 21),
            12000: (20, 5.2, 29), 14000: (26, 6.5, 38),
        },
        # Fig 5-6 sheet 1: 3100 lb, flaps 20, paved/level/dry runway;
        # altitude -> Celsius -> (ground roll ft, distance over 50 ft).
        'takeoff_distance': {0: {0: (715, 1365), 10: (765, 1460), 20: (825, 1570), 30: (885, 1680), 40: (945, 1800)},
 2000: {0: (850, 1635), 10: (915, 1760), 20: (980, 1890), 30: (1055, 2035), 40: (1130, 2190)},
 4000: {0: (1015, 1990), 10: (1090, 2150), 20: (1175, 2325), 30: (1260, 2515), 40: (1355, 2720)},
 6000: {0: (1220, 2470), 10: (1315, 2690), 20: (1415, 2930), 30: (1520, 3200), 40: (1635, 3510)}},
        # Fig 5-12: 2950 lb, flaps full, idle, max braking, paved/level/dry.
        # Same column units as takeoff; subset at 2000 ft altitude increments.
        'landing_distance': {0: {0: (560, 1300), 10: (580, 1335), 20: (600, 1365), 30: (620, 1400), 40: (640, 1435)},
 2000: {0: (600, 1370), 10: (625, 1405), 20: (645, 1440), 30: (670, 1480), 40: (690, 1515)},
 4000: {0: (650, 1450), 10: (670, 1485), 20: (695, 1525), 30: (720, 1565), 40: (740, 1600)},
 6000: {0: (700, 1530), 10: (725, 1575), 20: (750, 1615), 30: (775, 1660), 40: (800, 1700)}},
    }
}

DEFAULT_AIRCRAFT = 'CAP 487'

os.makedirs(CHARTS_DIR, exist_ok=True)

def get_utc_now():
    return datetime.now(timezone.utc)

def init_database():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS airports (icao TEXT PRIMARY KEY, name TEXT, city TEXT, state TEXT, latitude REAL, longitude REAL, elevation INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS runways (id INTEGER PRIMARY KEY, airport_icao TEXT, runway_id TEXT, length INTEGER, surface TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS navaids (id TEXT PRIMARY KEY, name TEXT, type TEXT, latitude REAL, longitude REAL)')
    # L-10: this data is OurAirports, not the FAA NASR cycle a pilot expects,
    # and nothing recorded which source or how old it was. Crews were reading
    # airport data of unknown vintage off a planner that looked authoritative.
    c.execute('CREATE TABLE IF NOT EXISTS data_source '
              '(key TEXT PRIMARY KEY, source TEXT, fetched_at TEXT, rows INTEGER)')
    conn.commit()
    conn.close()

init_database()

def log_msg(m): print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}")

# Startup/Chart download status
startup_status = {
    'ready': False,
    'in_progress': False,
    'phase': 'initializing',
    'message': 'Starting up...',
    'progress': 0,
    'vfr_tiles': 0,
    'ifr_tiles': 0
}

# Database update status
update_status = {'in_progress': False, 'message': '', 'progress': 0}


def _publish_update_status(**changes):
    update_status.update(changes)
    temporary = f'{DATABASE_UPDATE_STATUS_PATH}.{os.getpid()}.tmp'
    try:
        with open(temporary, 'w', encoding='utf-8') as status_file:
            json.dump(update_status, status_file)
        os.replace(temporary, DATABASE_UPDATE_STATUS_PATH)
    except OSError as e:
        log_msg(f'Could not publish aviation database status: {e}')


def _read_update_status():
    try:
        with open(DATABASE_UPDATE_STATUS_PATH, encoding='utf-8') as status_file:
            shared = json.load(status_file)
        if not isinstance(shared, dict):
            raise ValueError('status is not an object')
        return shared
    except (OSError, ValueError, TypeError):
        return dict(update_status)

def lat_lon_to_tile(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y

def get_tiles_for_region(bounds, zoom_levels):
    """Get all tile coordinates for a region"""
    tiles = []
    for z in zoom_levels:
        min_x, max_y = lat_lon_to_tile(bounds[0][0], bounds[0][1], z)
        max_x, min_y = lat_lon_to_tile(bounds[1][0], bounds[1][1], z)
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                tiles.append((z, x, y))
    return tiles

def download_tiles(chart_type, tile_url_template, regions, zoom_levels, phase_name):
    """Download tiles for specified regions"""
    global startup_status
    
    # Collect all tiles needed
    all_tiles = []
    for region_key, region in regions.items():
        tiles = get_tiles_for_region(region['bounds'], zoom_levels)
        for t in tiles:
            all_tiles.append((region_key, t[0], t[1], t[2]))
    
    total = len(all_tiles)
    downloaded = 0
    skipped = 0
    errors = 0
    
    chart_dir = os.path.join(CHARTS_DIR, chart_type)
    os.makedirs(chart_dir, exist_ok=True)
    
    for region_key, z, x, y in all_tiles:
        tile_path = os.path.join(chart_dir, str(z), str(x))
        os.makedirs(tile_path, exist_ok=True)
        tile_file = os.path.join(tile_path, f'{y}.png')
        
        if os.path.exists(tile_file) and os.path.getsize(tile_file) > 100:
            skipped += 1
        else:
            try:
                url = tile_url_template.format(z=z, x=x, y=y)
                response = requests.get(url, timeout=15, headers={
                    'User-Agent': 'Mozilla/5.0 CAP 487-FlightPlanner/1.0',
                    'Referer': 'https://www.faa.gov/'
                })
                if response.status_code == 200 and len(response.content) > 100:
                    with open(tile_file, 'wb') as f:
                        f.write(response.content)
                else:
                    errors += 1
            except Exception as e:
                errors += 1
                if errors <= 5:
                    log_msg(f"Tile error {z}/{x}/{y}: {e}")
        
        downloaded += 1
        progress = int((downloaded / total) * 100)
        startup_status['progress'] = progress
        startup_status['message'] = f'{phase_name}: {downloaded}/{total} tiles ({skipped} cached, {errors} errors)'
        
        if chart_type == 'vfr':
            startup_status['vfr_tiles'] = downloaded - errors
        else:
            startup_status['ifr_tiles'] = downloaded - errors
    
    return downloaded - errors

def count_existing_tiles():
    """Count tiles already downloaded"""
    vfr_count = 0
    ifr_count = 0
    
    vfr_dir = os.path.join(CHARTS_DIR, 'vfr')
    ifr_dir = os.path.join(CHARTS_DIR, 'ifr')
    
    if os.path.exists(vfr_dir):
        for root, dirs, files in os.walk(vfr_dir):
            vfr_count += len([f for f in files if f.endswith('.png')])
    
    if os.path.exists(ifr_dir):
        for root, dirs, files in os.walk(ifr_dir):
            ifr_count += len([f for f in files if f.endswith('.png')])
    
    return vfr_count, ifr_count

def startup_chart_download():
    """Download all charts on startup"""
    global startup_status
    
    startup_status['in_progress'] = True
    startup_status['ready'] = False
    
    # Check if charts already exist
    vfr_existing, ifr_existing = count_existing_tiles()
    min_tiles_needed = 500  # Rough estimate of minimum tiles for coverage
    
    if vfr_existing > min_tiles_needed and ifr_existing > min_tiles_needed:
        log_msg(f"Charts already cached: {vfr_existing} VFR, {ifr_existing} IFR tiles")
        startup_status['vfr_tiles'] = vfr_existing
        startup_status['ifr_tiles'] = ifr_existing
        startup_status['ready'] = True
        startup_status['in_progress'] = False
        startup_status['message'] = 'Charts loaded from cache'
        startup_status['progress'] = 100
        return
    
    try:
        # Download VFR Sectionals - zoom 6-12 for full detail
        startup_status['phase'] = 'vfr'
        startup_status['message'] = 'Downloading VFR Sectional charts...'
        log_msg("Downloading VFR Sectional charts (zoom 6-12)...")
        download_tiles('vfr', TILE_SOURCES['vfr'], CHART_REGIONS, range(6, 13), 'VFR Sectionals')
        
        # Download IFR Low - zoom 5-11 for full detail
        startup_status['phase'] = 'ifr'
        startup_status['message'] = 'Downloading IFR Low Enroute charts...'
        log_msg("Downloading IFR Low Enroute charts (zoom 5-11)...")
        download_tiles('ifr', TILE_SOURCES['ifr_low'], CHART_REGIONS, range(5, 12), 'IFR Low Enroute')
        
        startup_status['ready'] = True
        startup_status['message'] = 'All charts downloaded!'
        startup_status['progress'] = 100
        log_msg("Chart download complete!")
        
    except Exception as e:
        log_msg(f"Chart download error: {e}")
        startup_status['message'] = f'Error: {str(e)} - continuing with online tiles'
        startup_status['ready'] = True  # Allow app to work with online fallback
    finally:
        startup_status['in_progress'] = False

def _acquire_database_update_lock():
    try:
        lock_file = open(DATABASE_UPDATE_LOCK_PATH, 'a+')
    except OSError as e:
        log_msg(f'Could not open aviation database update lock: {e}')
        return None
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None
    return lock_file


def _release_database_update_lock(lock_file):
    fcntl.flock(lock_file, fcntl.LOCK_UN)
    lock_file.close()


def database_update_running():
    """Return whether another thread or worker holds the population lock."""
    lock_file = _acquire_database_update_lock()
    if lock_file is None:
        return True
    _release_database_update_lock(lock_file)
    return False


def download_database(lock_file=None):
    if lock_file is None:
        lock_file = _acquire_database_update_lock()
        if lock_file is None:
            log_msg('Aviation database update already running in another worker')
            return False
    _publish_update_status(in_progress=True, progress=5,
                           message='Downloading airports...')
    conn = None
    succeeded = False
    try:
        r = requests.get(OURAIRPORTS_URLS['airports'], timeout=300)
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM airports')
        c.execute('DELETE FROM runways')
        c.execute('DELETE FROM navaids')
        
        _publish_update_status(progress=20)
        cnt = 0
        for row in csv.DictReader(StringIO(r.content.decode('utf-8'))):
            icao = row.get('ident', '').upper()
            if row.get('iso_country') in ['US'] and len(icao) >= 3:
                try:
                    c.execute('INSERT OR REPLACE INTO airports VALUES (?,?,?,?,?,?,?)',
                        (icao, row.get('name',''), row.get('municipality',''),
                         row.get('iso_region','')[-2:] if row.get('iso_region') else '',
                         float(row.get('latitude_deg',0) or 0),
                         float(row.get('longitude_deg',0) or 0),
                         int(float(row.get('elevation_ft',0) or 0))))
                    cnt += 1
                except Exception as e:
                    log_msg(f"Skipping airport row {icao or '<unknown>'}: {e}")
        conn.commit()
        
        _publish_update_status(message='Downloading runways...', progress=40)
        r = requests.get(OURAIRPORTS_URLS['runways'], timeout=300)
        
        c.execute('SELECT icao FROM airports')
        apts = set(x[0] for x in c.fetchall())
        rcnt = 0
        for row in csv.DictReader(StringIO(r.content.decode('utf-8'))):
            apt = row.get('airport_ident','').upper()
            if apt in apts and row.get('le_ident'):
                try:
                    c.execute('INSERT INTO runways (airport_icao, runway_id, length, surface) VALUES (?,?,?,?)',
                        (apt, row.get('le_ident',''), int(float(row.get('length_ft',0) or 0)), row.get('surface','')))
                    rcnt += 1
                except Exception as e:
                    log_msg(f"Skipping runway row for {apt or '<unknown>'}: {e}")
        conn.commit()
        
        _publish_update_status(message='Downloading navaids...', progress=70)
        r = requests.get(OURAIRPORTS_URLS['navaids'], timeout=300)
        
        ncnt = 0
        for row in csv.DictReader(StringIO(r.content.decode('utf-8'))):
            nid = row.get('ident','').upper()
            if row.get('iso_country') in ['US'] and nid:
                try:
                    c.execute('INSERT OR REPLACE INTO navaids VALUES (?,?,?,?,?)',
                        (nid, row.get('name',''), row.get('type',''),
                         float(row.get('latitude_deg',0) or 0),
                         float(row.get('longitude_deg',0) or 0)))
                    ncnt += 1
                except Exception as e:
                    log_msg(f"Skipping navaid row {nid or '<unknown>'}: {e}")
        conn.commit()
        
        # Stamp what this data actually is, so the UI can stop implying a
        # currency the source does not have.
        for key, rows in (('airports', cnt), ('runways', rcnt), ('navaids', ncnt)):
            c.execute('INSERT OR REPLACE INTO data_source VALUES (?,?,?,?)',
                      (key, OURAIRPORTS_URLS[key], get_utc_now().isoformat(timespec='seconds'), rows))
        conn.commit()

        _publish_update_status(
            message=f'Done! {cnt} airports, {rcnt} runways, {ncnt} navaids',
            progress=100)
        succeeded = True
    except Exception as e:
        _publish_update_status(message=f'Error: {e}')
        log_msg(f'Aviation database update failed: {e}')
    finally:
        if conn is not None:
            conn.close()
        _publish_update_status(in_progress=False)
        _release_database_update_lock(lock_file)
    return succeeded


def start_database_update():
    """Start one population thread across all gunicorn workers."""
    lock_file = _acquire_database_update_lock()
    if lock_file is None:
        return False
    try:
        threading.Thread(target=download_database, args=(lock_file,), daemon=True).start()
    except Exception:
        _release_database_update_lock(lock_file)
        raise
    return True

def auto_update_if_empty():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM airports')
    count = c.fetchone()[0]
    conn.close()
    if count == 0:
        if start_database_update():
            log_msg("Database empty — auto-starting aviation data download...")
        else:
            log_msg("Database empty — another worker is populating it")
    else:
        log_msg(f"Database ready: {count} airports")

auto_update_if_empty()

# Weather simulation
def simulate_metar(station):
    now = get_utc_now()
    h = sum(ord(c) for c in station) + now.hour
    wd, ws = (h*37)%36*10, 5+(h%15)
    t, d = 15+(h%20)-10, 10+(h%15)-10
    alt = 29.80 + (h%40)/100
    vis = 10 if (h%10)>2 else (h%10)+3
    fltcat = 'VFR' if vis >= 5 else ('MVFR' if vis >= 3 else 'IFR')
    return {
        'icaoId': station,
        'rawOb': f"{station} {now.strftime('%d%H%M')}Z {wd:03d}{ws:02d}KT {vis}SM FEW050 {t:02d}/{d:02d} A{int(alt*100)}",
        'fltcat': fltcat, 'simulated': True
    }

def simulate_taf(station):
    now = get_utc_now()
    h = sum(ord(c) for c in station)
    return {
        'icaoId': station,
        'rawTAF': f"TAF {station} {now.strftime('%d%H%M')}Z {now.strftime('%d%H')}/{(now+timedelta(hours=24)).strftime('%d%H')} {(h*41)%36*10:03d}{8+(h%12):02d}KT P6SM FEW050",
        'simulated': True
    }

def simulate_winds(lat, lon):
    h = int((lat*100 + lon*100) % 1000)
    return {
        'station': 'ESTIMATED', 'simulated': True,
        'levels': {
            3000: {'direction': (h*7)%360, 'speed': 10+(h%10), 'temp': 10},
            6000: {'direction': (h*11)%360, 'speed': 15+(h%15), 'temp': 3},
            9000: {'direction': (h*13)%360, 'speed': 20+(h%20), 'temp': -4},
            12000: {'direction': (h*17)%360, 'speed': 25+(h%25), 'temp': -11},
        }
    }

def _interp_wind(samples, alt):
    """Linear interpolation of (u, v, temp) by altitude; clamped at the ends.
    samples: sorted list of (alt_ft, u, v, temp)."""
    if alt <= samples[0][0]:
        return samples[0][1:]
    if alt >= samples[-1][0]:
        return samples[-1][1:]
    for i in range(len(samples) - 1):
        a0, a1 = samples[i][0], samples[i + 1][0]
        if a0 <= alt <= a1:
            f = (alt - a0) / (a1 - a0) if a1 != a0 else 0
            return tuple(samples[i][j] + f * (samples[i + 1][j] - samples[i][j])
                         for j in (1, 2, 3))
    return samples[-1][1:]

def fetch_winds_aloft(lat, lon):
    """Real winds/temps aloft at a point from Open-Meteo (GFS), interpolated to
    the standard FB altitudes. Falls back to simulate_winds() on any failure so
    a route still calculates offline."""
    now = get_utc_now()
    key = (round(lat, 1), round(lon, 1), now.strftime('%Y%m%d%H'))
    if key in _winds_cache:
        return _winds_cache[key]
    try:
        fields = []
        for hpa in WINDS_LEVELS_HPA:
            fields += [f'windspeed_{hpa}hPa', f'winddirection_{hpa}hPa',
                       f'temperature_{hpa}hPa', f'geopotential_height_{hpa}hPa']
        r = requests.get(OPEN_METEO_URL, params={
            'latitude': lat, 'longitude': lon, 'hourly': ','.join(fields),
            'wind_speed_unit': 'kn', 'forecast_days': 1, 'timezone': 'UTC',
        }, timeout=6, headers={'User-Agent': 'CAP 487-Planner/1.0'})
        h = r.json()['hourly']
        times = h['time']
        target = now.strftime('%Y-%m-%dT%H:00')
        idx = times.index(target) if target in times else 0

        # Build (alt_ft, u, v, temp) samples from each pressure level.
        samples = []
        for hpa in WINDS_LEVELS_HPA:
            spd = h[f'windspeed_{hpa}hPa'][idx]
            drc = h[f'winddirection_{hpa}hPa'][idx]
            tmp = h[f'temperature_{hpa}hPa'][idx]
            gh  = h[f'geopotential_height_{hpa}hPa'][idx]
            if None in (spd, drc, tmp, gh):
                continue
            rad = math.radians(drc)                 # direction wind blows FROM
            samples.append((gh * 3.28084, -spd * math.sin(rad), -spd * math.cos(rad), tmp))
        if len(samples) < 2:
            raise ValueError('insufficient pressure levels')
        samples.sort()

        levels = {}
        for alt in WINDS_TARGET_ALT:
            u, v, tmp = _interp_wind(samples, alt)
            levels[alt] = {
                'direction': round((math.degrees(math.atan2(-u, -v)) + 360) % 360),
                'speed': round(math.hypot(u, v)),
                'temp': round(tmp),
            }
        result = {'station': 'GFS (Open-Meteo)', 'simulated': False, 'levels': levels}
        _winds_cache_put(key, result)
        return result
    except Exception as e:
        log_msg(f'Winds aloft fetch failed ({e}); using estimate')
        return simulate_winds(lat, lon)

def fetch_metar(station):
    try:
        r = requests.get(f"{AVIATION_WEATHER_BASE}/metar?ids={station}&format=json", timeout=8,
                        headers={'User-Agent': 'CAP 487-Planner/1.0'})
        if r.status_code == 200 and r.text.strip().startswith('['):
            data = r.json()
            if data: 
                data[0]['simulated'] = False
                return data[0]
    except: pass
    return simulate_metar(station)

def fetch_taf(station):
    try:
        r = requests.get(f"{AVIATION_WEATHER_BASE}/taf?ids={station}&format=json", timeout=8,
                        headers={'User-Agent': 'CAP 487-Planner/1.0'})
        if r.status_code == 200 and r.text.strip().startswith('['):
            data = r.json()
            if data:
                data[0]['simulated'] = False
                return data[0]
    except: pass
    return simulate_taf(station)

# Navigation
def gc_dist(lat1, lon1, lat2, lon2):
    R = 3440.065
    la1, la2 = math.radians(lat1), math.radians(lat2)
    dla, dlo = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dla/2)**2 + math.cos(la1)*math.cos(la2)*math.sin(dlo/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def bearing(lat1, lon1, lat2, lon2):
    la1, la2 = math.radians(lat1), math.radians(lat2)
    dlo = math.radians(lon2-lon1)
    x = math.sin(dlo)*math.cos(la2)
    y = math.cos(la1)*math.sin(la2) - math.sin(la1)*math.cos(la2)*math.cos(dlo)
    return (math.degrees(math.atan2(x,y))+360)%360

def destination_point(lat, lon, dist_nm, brg_deg):
    """Calculate destination lat/lon given start point, distance in NM, and bearing in degrees."""
    R = 3440.065
    d_div_r = dist_nm / R
    brg_rad = math.radians(brg_deg)
    lat1_rad = math.radians(lat)
    lon1_rad = math.radians(lon)
    
    lat2_rad = math.asin(math.sin(lat1_rad) * math.cos(d_div_r) +
                         math.cos(lat1_rad) * math.sin(d_div_r) * math.cos(brg_rad))
    lon2_rad = lon1_rad + math.atan2(math.sin(brg_rad) * math.sin(d_div_r) * math.cos(lat1_rad),
                                     math.cos(d_div_r) - math.sin(lat1_rad) * math.sin(lat2_rad))
    return round(math.degrees(lat2_rad), 6), round((math.degrees(lon2_rad) + 540) % 360 - 180, 6)

def _magnetic_headings(points):
    for index, point in enumerate(points):
        previous = points[max(0, index - 1)]
        variation = mag_var((previous['lat'] + point['lat']) / 2,
                            (previous['lon'] + point['lon']) / 2)
        point['heading_mag'] = round((point['heading_true'] - variation) % 360, 1)
    return points


def generate_expanding_square(datum_lat, datum_lon, spacing_nm=1.0, num_legs=8, initial_heading=0.0, turn_dir='right'):
    """Generate Civil Air Patrol Expanding Square (SS) search pattern waypoints."""
    points = [{'identifier': 'DATUM', 'lat': round(datum_lat, 6), 'lon': round(datum_lon, 6), 'leg_dist_nm': 0.0, 'heading_true': initial_heading}]
    cur_lat, cur_lon = datum_lat, datum_lon
    cur_hdg = initial_heading
    turn_angle = 90.0 if turn_dir.lower() == 'right' else -90.0
    
    for i in range(1, num_legs + 1):
        leg_len = ((i + 1) // 2) * spacing_nm
        next_lat, next_lon = destination_point(cur_lat, cur_lon, leg_len, cur_hdg)
        var = mag_var((cur_lat + next_lat)/2, (cur_lon + next_lon)/2)
        points.append({
            'identifier': f'SS{i:02d}',
            'lat': next_lat,
            'lon': next_lon,
            'leg_dist_nm': round(leg_len, 2),
            'heading_true': round(cur_hdg % 360, 1),
            'heading_mag': round((cur_hdg - var) % 360, 1)
        })
        cur_lat, cur_lon = next_lat, next_lon
        cur_hdg = (cur_hdg + turn_angle) % 360
        
    return _magnetic_headings(points)

def generate_creeping_line(start_lat, start_lon, end_lat, end_lon, sweep_width_nm=3.0, spacing_nm=1.0, max_legs=12):
    """Generate Civil Air Patrol Creeping Line (CS) search pattern waypoints."""
    adv_brg = bearing(start_lat, start_lon, end_lat, end_lon)
    tot_dist = gc_dist(start_lat, start_lon, end_lat, end_lon)
    num_sweeps = min(max_legs, max(1, math.ceil(tot_dist / spacing_nm)))
    
    left_brg = (adv_brg - 90) % 360
    right_brg = (adv_brg + 90) % 360
    half_w = sweep_width_nm / 2.0
    
    points = []
    cur_axis_lat, cur_axis_lon = destination_point(start_lat, start_lon, min(spacing_nm, tot_dist) / 2, adv_brg)
    
    # CS01 is where the pattern starts (left end of the first sweep). Nothing is
    # flown to reach it, so like PS01 it carries no leg length, and the heading
    # it shows is that of the first real leg, CS01 -> CS02 (L2-8). It used to
    # carry a fictitious half-width leg and a heading to the left that nobody
    # flies.
    p1_lat, p1_lon = destination_point(cur_axis_lat, cur_axis_lon, half_w, left_brg)
    points.append({'identifier': 'CS01', 'lat': p1_lat, 'lon': p1_lon, 'leg_dist_nm': 0.0, 'heading_true': round(right_brg, 1)})
    
    # Leg 2: Sweep right
    p2_lat, p2_lon = destination_point(cur_axis_lat, cur_axis_lon, half_w, right_brg)
    points.append({'identifier': 'CS02', 'lat': p2_lat, 'lon': p2_lon, 'leg_dist_nm': round(sweep_width_nm, 2), 'heading_true': round(right_brg, 1)})
    
    current_side = 'right'
    wpt_idx = 3
    for i in range(1, num_sweeps):
        cur_axis_lat, cur_axis_lon = destination_point(cur_axis_lat, cur_axis_lon, spacing_nm, adv_brg)
        if current_side == 'right':
            # Advance along right side
            adv_lat, adv_lon = destination_point(cur_axis_lat, cur_axis_lon, half_w, right_brg)
            points.append({'identifier': f'CS{wpt_idx:02d}', 'lat': adv_lat, 'lon': adv_lon, 'leg_dist_nm': round(spacing_nm, 2), 'heading_true': round(adv_brg, 1)})
            wpt_idx += 1
            # Cross to left side
            cross_lat, cross_lon = destination_point(cur_axis_lat, cur_axis_lon, half_w, left_brg)
            points.append({'identifier': f'CS{wpt_idx:02d}', 'lat': cross_lat, 'lon': cross_lon, 'leg_dist_nm': round(sweep_width_nm, 2), 'heading_true': round(left_brg, 1)})
            wpt_idx += 1
            current_side = 'left'
        else:
            # Advance along left side
            adv_lat, adv_lon = destination_point(cur_axis_lat, cur_axis_lon, half_w, left_brg)
            points.append({'identifier': f'CS{wpt_idx:02d}', 'lat': adv_lat, 'lon': adv_lon, 'leg_dist_nm': round(spacing_nm, 2), 'heading_true': round(adv_brg, 1)})
            wpt_idx += 1
            # Cross to right side
            cross_lat, cross_lon = destination_point(cur_axis_lat, cur_axis_lon, half_w, right_brg)
            points.append({'identifier': f'CS{wpt_idx:02d}', 'lat': cross_lat, 'lon': cross_lon, 'leg_dist_nm': round(sweep_width_nm, 2), 'heading_true': round(right_brg, 1)})
            wpt_idx += 1
            current_side = 'right'
            
    return _magnetic_headings(points)

def generate_parallel_track(corner_lat, corner_lon, length_nm=5.0, width_nm=4.0, axis_heading=0.0, spacing_nm=1.0):
    """Generate Civil Air Patrol Parallel Track (PS) search pattern waypoints."""
    cross_heading = (axis_heading + 90) % 360
    opp_heading = (axis_heading + 180) % 360
    num_sweeps = max(1, math.ceil(width_nm / spacing_nm))
    
    points = []
    cur_lat, cur_lon = destination_point(corner_lat, corner_lon, min(spacing_nm, width_nm) / 2, cross_heading)
    points.append({'identifier': 'PS01', 'lat': cur_lat, 'lon': cur_lon, 'leg_dist_nm': 0.0, 'heading_true': axis_heading})
    
    wpt_idx = 2
    for i in range(num_sweeps):
        # Fly length of box
        curr_sweep_hdg = axis_heading if i % 2 == 0 else opp_heading
        next_lat, next_lon = destination_point(cur_lat, cur_lon, length_nm, curr_sweep_hdg)
        points.append({'identifier': f'PS{wpt_idx:02d}', 'lat': next_lat, 'lon': next_lon, 'leg_dist_nm': round(length_nm, 2), 'heading_true': curr_sweep_hdg})
        wpt_idx += 1
        cur_lat, cur_lon = next_lat, next_lon
        
        if i < num_sweeps - 1:
            # Step laterally across track
            next_lat, next_lon = destination_point(cur_lat, cur_lon, spacing_nm, cross_heading)
            points.append({'identifier': f'PS{wpt_idx:02d}', 'lat': next_lat, 'lon': next_lon, 'leg_dist_nm': round(spacing_nm, 2), 'heading_true': cross_heading})
            wpt_idx += 1
            cur_lat, cur_lon = next_lat, next_lon
            
    return _magnetic_headings(points)

def fms_waypoint_limit_message(count):
    return (f'This flight plan has {count} waypoints; the limit is {MAX_FMS_WAYPOINTS} '
            f'(the G1000 flight-plan size, just under X-Plane\'s FMS limit). '
            f'Split the pattern into two files: fewer legs, wider spacing, '
            f'or a smaller area per file.')


def generate_xplane_fms_content(departure, destination, waypoints, cruise_alt=6500):
    """Generate X-Plane 11/12 standard .fms text file."""
    departure, destination = departure.strip().upper(), destination.strip().upper()
    if len(waypoints) > MAX_FMS_WAYPOINTS:
        raise ValueError(fms_waypoint_limit_message(len(waypoints)))
    airports = []
    for role, ident in (('ADEP', departure), ('ADES', destination)):
        airport = get_airport(ident)
        if not airport:
            raise ValueError(f'Cannot resolve {role} airport: {ident or "(empty)"}; update the aviation database or correct the identifier')
        airports.append(airport)
    lines = [
        "I",
        "1100 Version",
        f"CYCLE {get_utc_now().strftime('%y%m')}",
        f"ADEP {departure.upper()}",
        f"ADES {destination.upper()}",
        f"NUMENR {len(waypoints) + 2}"
    ]
    
    dep_apt, dest_apt = airports
    dep_lat, dep_lon = dep_apt['latitude'], dep_apt['longitude']
    dep_elev = dep_apt.get('elevation', 0)
    lines.append(f"1 {departure.upper()} ADEP {float(dep_elev):.1f} {dep_lat:.6f} {dep_lon:.6f}")
    
    for wpt in waypoints:
        lat = wpt.get('lat', 0.0)
        lon = wpt.get('lon', 0.0)
        # Laminar's v11 FMS specification (also used by X-Plane 12):
        # https://developer.x-plane.com/article/flightplan-files-v11-fms-file-format/
        # Type 28 uses lat/lon in columns 5/6; column 2 is the identifier.
        # Use a conservative ASCII token subset; never change the coordinates
        # to obtain a name. Preserve coordinate names for unlabelled points.
        ident = fms_identifier(wpt.get('identifier'))
        ident = ident or f"{lat:+.3f}_{lon:+.3f}"
        lines.append(f"28 {ident} DRCT {float(cruise_alt):.6f} {lat:.6f} {lon:.6f}")
        
    dest_lat, dest_lon = dest_apt['latitude'], dest_apt['longitude']
    dest_elev = dest_apt.get('elevation', 0)
    lines.append(f"1 {destination.upper()} ADES {float(dest_elev):.1f} {dest_lat:.6f} {dest_lon:.6f}")
    
    return "\n".join(lines) + "\n"


def mag_var(lat, lon):
    """Magnetic declination in degrees (east positive) from the WMM."""
    if _geomag is None:
        return 0.0
    try:
        t = get_utc_now()
        year = t.year + (t.timetuple().tm_yday - 1) / 365.25
        return _geomag.calculate(glat=lat, glon=lon, alt=0, time=year).d
    except Exception:
        return 0.0

def wind_corr(tc, tas, wd, ws):
    if tas <= 0:
        raise ValueError('True airspeed must be positive')
    if ws == 0: return 0, tas
    swc = (ws/tas)*math.sin(math.radians(wd-tc))
    if abs(swc) >= 1:
        raise ValueError('Crosswind is at or above true airspeed; course cannot be maintained')
    wca = math.degrees(math.asin(swc))
    # Winds-aloft direction is FROM: a headwind (wd == tc) must reduce GS
    gs = tas*math.cos(math.asin(swc)) - ws*math.cos(math.radians(wd-tc))
    if gs <= 0:
        raise ValueError('Headwind produces non-positive ground speed; leg cannot be flown')
    return round(wca,1), gs

def get_airport(icao):
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('SELECT icao,name,city,state,latitude,longitude,elevation FROM airports WHERE icao=?', (icao,))
    r = c.fetchone()
    conn.close()
    if r: return {'icao':r[0],'name':r[1],'city':r[2],'state':r[3],'latitude':r[4],'longitude':r[5],'elevation':r[6]}
    return None

def get_runways(icao):
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('SELECT runway_id,length,surface FROM runways WHERE airport_icao=? ORDER BY length DESC', (icao,))
    rws = [{'runway_id':r[0],'length':r[1],'surface':r[2]} for r in c.fetchall()]
    conn.close()
    return rws

def get_navaid(nid):
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('SELECT id,name,type,latitude,longitude FROM navaids WHERE id=?', (nid,))
    r = c.fetchone()
    conn.close()
    if r: return {'id':r[0],'name':r[1],'type':r[2],'latitude':r[3],'longitude':r[4]}
    return None

def fms_identifier(text):
    """The token an .fms record carries for a label (see generate_xplane_fms_content)."""
    return re.sub(r'[^A-Z0-9_]', '_', str(text or '').upper()).strip('_')


def split_route_label(token):
    """'DATUM=@33.1,-117.0' -> ('DATUM', '@33.1,-117.0'); 'KSEE' -> (None, 'KSEE').

    L2-7: lets "Apply to Route" hand the planner a coordinate point together
    with the name the pattern gave it. Only coordinate points can be named,
    and the name is reduced to the same characters the .fms export keeps, so
    the nav log and the flight-plan file agree.
    """
    if '=' in token:
        name, _, ident = token.partition('=')
        label = fms_identifier(name)[:12]
        if label and ident.startswith('@'):
            return label, ident
    return None, token


def get_coords(ident):
    # User-dropped waypoint: "@lat,lon" (from the map rubber-band "user waypoint" option)
    if ident.startswith('@'):
        try:
            lat_s, lon_s = ident[1:].split(',')
            lat, lon = float(lat_s), float(lon_s)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return (lat, lon, 'user', {'identifier': 'USR', 'user': True,
                                           'latitude': lat, 'longitude': lon})
        except Exception:
            return None
        return None
    a = get_airport(ident)
    if a: return (a['latitude'], a['longitude'], 'airport', a)
    n = get_navaid(ident)
    if n: return (n['latitude'], n['longitude'], 'navaid', n)
    return None

def _bracket(values, requested):
    values = sorted(values)
    if not values[0] <= requested <= values[-1]:
        raise ValueError(f'Input {requested:g} outside performance table {values[0]:g}..{values[-1]:g}')
    return (max(value for value in values if value <= requested),
            min(value for value in values if value >= requested))


def _lerp_tuple(low, high, fraction):
    return tuple(a + (b - a) * fraction for a, b in zip(low, high))


def get_cruise(alt, rpm, manifold_pressure=20.0):
    """Interpolate the POH standard-temperature altitude/RPM/MP grid."""
    cd = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]['cruise_performance']
    low, high = _bracket(cd, alt)
    rows = []
    for altitude in (low, high):
        rlow, rhigh = _bracket(cd[altitude], rpm)
        rpm_rows = []
        for setting in (rlow, rhigh):
            table = cd[altitude][setting]
            mlow, mhigh = _bracket(table, manifold_pressure)
            fraction = (manifold_pressure - mlow) / (mhigh - mlow) if mhigh != mlow else 0
            rpm_rows.append(_lerp_tuple(table[mlow], table[mhigh], fraction))
        fraction = (rpm - rlow) / (rhigh - rlow) if rhigh != rlow else 0
        rows.append(_lerp_tuple(*rpm_rows, fraction))
    fraction = (alt - low) / (high - low) if high != low else 0
    pwr, tas, gph = _lerp_tuple(*rows, fraction)
    if pwr > 80:
        raise ValueError('Cruise setting exceeds the POH maximum of 80% power')
    return {'power_percent': pwr, 'true_airspeed': tas, 'fuel_flow_gph': gph,
            'manifold_pressure_inhg': manifold_pressure,
            'conditions': 'POH standard temperature, recommended lean mixture, 3100 lb'}

def get_climb(fr, to):
    ac = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]
    cd = ac['climb_performance']
    alts = sorted(cd.keys())

    def at(altitude):
        # L2-11: interpolate between table rows (as get_cruise does) instead of
        # snapping to the nearest 2000 ft; outside the table, hold the end row.
        altitude = max(alts[0], min(alts[-1], altitude))
        low, high = _bracket(alts, altitude)
        fraction = (altitude - low) / (high - low) if high != low else 0
        return _lerp_tuple(cd[low], cd[high], fraction)

    fd, td = at(fr), at(to)
    return {'time_minutes': round(max(0, td[0]-fd[0]), 1),
            'fuel_gallons': round(max(0, td[1]-fd[1]), 2),
            'distance_nm': round(max(0, td[2]-fd[2]), 1)}

def calc_takeoff(wt, alt, temp, hw=0):
    ac = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]
    tbl = ac['takeoff_distance']
    if not 0 < wt <= ac['max_takeoff_weight']:
        raise ValueError('Takeoff weight must be positive and no more than 3100 lb')
    _bracket(tbl, alt)
    for row in tbl.values():
        _bracket(row, temp)
    alts = sorted(tbl.keys())
    a = min([x for x in alts if x >= alt], default=alts[-1])
    temps = sorted(tbl[a].keys())
    t = min([x for x in temps if x >= temp], default=temps[-1])
    gr, tot = tbl[a][t]
    # C182T POH, Figs 5-6 / 5-12 wind-correction notes (source above).
    # Up to 10 kt tailwind: increase distance 10% per 2 kt.
    if hw < -10:
        raise ValueError('Tailwind exceeds the 10 kt performance-table limit')
    wf = 1.0 - hw / 2 * 0.10 if hw < 0 else 1.0 - hw / 9 * 0.10
    if wf <= 0:
        raise ValueError('Headwind exceeds the supported runway correction')
    return {'ground_roll': int(gr*wf), 'total_over_50ft': int(tot*wf)}

def calc_landing(alt, temp, hw=0):
    ac = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]
    tbl = ac['landing_distance']
    _bracket(tbl, alt)
    for row in tbl.values():
        _bracket(row, temp)
    alts = sorted(tbl.keys())
    a = min([x for x in alts if x >= alt], default=alts[-1])
    temps = sorted(tbl[a].keys())
    t = min([x for x in temps if x >= temp], default=temps[-1])
    gr, tot = tbl[a][t]
    # C182T POH, Figs 5-6 / 5-12 wind-correction notes (source above).
    # Up to 10 kt tailwind: increase distance 10% per 2 kt.
    if hw < -10:
        raise ValueError('Tailwind exceeds the 10 kt performance-table limit')
    wf = 1.0 - hw / 2 * 0.10 if hw < 0 else 1.0 - hw / 9 * 0.10
    if wf <= 0:
        raise ValueError('Headwind exceeds the supported runway correction')
    return {'ground_roll': int(gr*wf), 'total_over_50ft': int(tot*wf)}


def _console_headers():
    """Forward only the caller's console identity; never borrow service tokens."""
    headers = {}
    for name in ('X-CAPVSAR-Token', 'Authorization'):
        value = request.headers.get(name, '').strip()
        if value:
            headers[name] = value
    session = request.cookies.get('capvsar_session')
    if session:
        headers['Cookie'] = dump_cookie('capvsar_session', session, path=None)
    return headers


def _request_security_error(require_json=False):
    if require_json and not request.is_json:
        return jsonify({'success': False,
                        'error': 'This endpoint requires a JSON request body'}), 415
    # Origin is a CSRF check, never proof of identity. Cookie authentication
    # requires it; explicit credentials also cannot override a hostile Origin.
    origin = request.headers.get('Origin')
    expected = urlsplit(request.host_url)
    supplied = urlsplit(origin or '')
    same_origin = (supplied.scheme, supplied.netloc) == (expected.scheme, expected.netloc)
    if (origin and not same_origin) or (request.cookies.get('capvsar_session') and not same_origin):
        return jsonify({'success': False,
                        'error': 'A same-origin request is required'}), 403
    headers = _console_headers()
    if not headers:
        return jsonify({'success': False, 'error': 'Console authentication required'}), 401
    try:
        reply = requests.get(f'{VSAR_CONSOLE_URL}/api/auth/me', headers=headers,
                             timeout=5, allow_redirects=False)
        if reply.status_code in (401, 403):
            return jsonify({'success': False, 'error': 'Console authentication rejected'}), reply.status_code
        if reply.status_code != 200:
            raise ValueError('Unexpected authentication response')
        identity = reply.json()
        if not isinstance(identity, dict):
            raise ValueError('Invalid authentication response')
    except (requests.RequestException, ValueError):
        return jsonify({'success': False, 'error': 'Console authentication unavailable'}), 503
    if identity.get('authenticated') is not True:
        return jsonify({'success': False, 'error': 'Console authentication required'}), 401
    if identity.get('role') != 'instructor':
        return jsonify({'success': False, 'error': 'Instructor access required'}), 403
    return None


def _limited_text(data, field, default, maximum):
    return _text(data, field, default, maximum)

class RequestError(ValueError):
    """A request the caller got wrong. Always a 400 with this exact message."""


def _body():
    """The JSON object a POST sent. Anything else is the caller's mistake."""
    data = request.get_json(silent=True, force=True)
    if data is None:
        if request.get_data():
            raise RequestError('The request body is not valid JSON')
        return {}
    if not isinstance(data, dict):
        raise RequestError('The request body must be a JSON object')
    return data


def _num(data, key, default, lo, hi, integer=False, clamp=False):
    """L2-3: one place that turns a request field into a number.

    Rejects what is not a finite number (text that does not parse, null,
    true/false, lists), names the field in the message, and either refuses
    values outside lo..hi or, with clamp=True, pulls them back inside (for
    fields the UI has always clamped rather than refused). A missing field
    yields the default untouched.
    """
    if key not in data:
        return default
    raw = data[key]
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise RequestError(f'{key} must be a number')
    try:
        value = float(raw)
    except ValueError:
        raise RequestError(f'{key} must be a number') from None
    if not math.isfinite(value):
        raise RequestError(f'{key} must be a finite number')
    if integer:
        if value != int(value) and not clamp:
            raise RequestError(f'{key} must be a whole number')
        value = int(value)
    if clamp:
        value = max(lo, min(hi, value))
    elif not lo <= value <= hi:
        raise RequestError(f'{key} must be between {lo:g} and {hi:g}')
    return value


def _text(data, key, default, maximum=200):
    """A string field (stripped, length-limited). Not text is a 400."""
    value = data.get(key, default)
    if not isinstance(value, str):
        raise RequestError(f'{key} must be text')
    value = value.strip()
    if len(value) > maximum:
        raise RequestError(f'{key} must be at most {maximum} characters')
    return value


def _text_list(data, key, maximum=MAX_REQUEST_POINTS):
    """A list of strings (blank entries dropped)."""
    value = data.get(key, [])
    if not isinstance(value, list) or len(value) > maximum:
        raise RequestError(f'{key} must be a list of at most {maximum} entries')
    out = []
    for item in value:
        if not isinstance(item, str):
            raise RequestError(f'{key} entries must be text')
        if item.strip():
            out.append(item.strip())
    return out


def _points(data, key, minimum=0, maximum=MAX_REQUEST_POINTS):
    """A list of {lat, lon[, identifier]} objects with checked coordinates."""
    value = data.get(key, [])
    if not isinstance(value, list):
        raise RequestError(f'{key} must be a list of points')
    if len(value) > maximum:
        raise RequestError(f'{key} must contain at most {maximum} points')
    if len(value) < minimum:
        raise RequestError(f'{key} needs at least {minimum} points')
    out = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise RequestError(f'{key}[{index}] must be an object with lat and lon')
        if 'lat' not in item or 'lon' not in item:
            raise RequestError(f'{key}[{index}] needs lat and lon')
        point = dict(item)
        point['lat'] = _num(item, 'lat', None, -90, 90)
        point['lon'] = _num(item, 'lon', None, -180, 180)
        ident = item.get('identifier')
        if ident is not None and not isinstance(ident, str):
            raise RequestError(f'{key}[{index}].identifier must be text')
        point['identifier'] = (ident or '')[:64]
        out.append(point)
    return out


def _is_api_request():
    return request.path.startswith('/api/') or request.path.startswith('/planner/api/')


@app.errorhandler(Exception)
def _json_errors(exc):
    """L2-3: the API never answers with Werkzeug's HTML error page.

    HTTP errors keep their own status (404, 405, 413, 415 ...). Our own
    RequestError is a 400 carrying its message. Anything else is a bug: log it
    here and tell the caller only that the request failed, never the Python
    text ("Unknown format code 'f' for object of type 'str'") behind it.
    Pages (everything outside /api/) keep the standard HTML errors.
    """
    if isinstance(exc, HTTPException):
        if not _is_api_request():
            return exc
        response = exc.get_response(request.environ)
        response.set_data(json.dumps({'success': False,
                                      'error': exc.description or exc.name}))
        response.mimetype = 'application/json'
        return response
    if isinstance(exc, RequestError):
        return jsonify({'success': False, 'error': str(exc)}), 400
    app.logger.exception('Unhandled error on %s %s', request.method, request.path)
    if not _is_api_request():
        from werkzeug.exceptions import InternalServerError
        return InternalServerError()
    return jsonify({'success': False,
                    'error': 'The planner could not process that request'}), 500


def _allow_vsar_export(client):
    now = time.monotonic()
    with _vsar_export_rate_lock:
        attempts = _vsar_export_attempts.setdefault(client, deque())
        while attempts and now - attempts[0] >= VSAR_EXPORT_RATE_WINDOW_S:
            attempts.popleft()
        if len(attempts) >= VSAR_EXPORT_RATE_LIMIT:
            return False
        attempts.append(now)
        return True


# Flask Routes
@app.route('/api/health')
def health():
    """Liveness that actually proves the planner can serve a flight plan.

    L-10: the compose healthcheck hit `/`, which renders a template and says
    nothing about the aviation database. A planner whose database had vanished
    reported healthy and then failed on the first airport lookup - during an
    exercise, that is the worst possible moment to discover it.

    A missing or unreadable database is a hard failure (503). An empty one is
    not: a fresh container legitimately starts before the first download, so
    `populated` is reported separately rather than held against liveness.
    """
    body = {'status': 'ok', 'database': DATABASE_PATH}
    try:
        conn = sqlite3.connect(f'file:{DATABASE_PATH}?mode=ro', uri=True, timeout=2)
        try:
            body['airports'] = conn.execute('SELECT COUNT(*) FROM airports').fetchone()[0]
            body['populated'] = body['airports'] > 0
            body['data_source'] = [
                {'key': k, 'source': src, 'fetched_at': at, 'rows': rows}
                for k, src, at, rows in conn.execute(
                    'SELECT key, source, fetched_at, rows FROM data_source ORDER BY key')
            ]
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'database': DATABASE_PATH,
                        'error': str(e)}), 503
    return jsonify(body)


@app.route('/')
def index():
    return render_template('index.html', default_airport=DEFAULT_AIRPORT,
                           default_datum=DEFAULT_DATUM)

def _resolve_doc(slug):
    """Map a URL slug (or raw '.md' filename) to a docs entry."""
    key = slug.lower().removesuffix('.md')
    return DOCS.get(key)

@app.route('/guide')
@app.route('/guide/<slug>')
def guide(slug='guide'):
    """Render a documentation markdown file as a styled HTML page."""
    entry = _resolve_doc(slug)
    if not entry:
        abort(404)
    filename, title = entry
    path = os.path.join(DOCS_DIR, filename)
    if not os.path.exists(path):
        abort(404)
    with open(path, encoding='utf-8') as f:
        text = f.read()
    try:
        import markdown
        body = markdown.markdown(text, extensions=['tables', 'fenced_code', 'toc', 'sane_lists'])
    except Exception:
        # Fallback: show the raw markdown if the library is unavailable
        from markupsafe import escape
        body = f'<pre>{escape(text)}</pre>'
    return render_template('guide.html', title=title, body=body, download=filename)

@app.route('/docs/<path:filename>')
def docs_download(filename):
    """Download the raw markdown source of a doc."""
    if not any(filename == fn for fn, _ in DOCS.values()):
        abort(404)
    return send_from_directory(DOCS_DIR, filename, as_attachment=True,
                               mimetype='text/markdown')

@app.route('/api/startup-status')
def get_startup_status():
    return jsonify(startup_status)

@app.route('/api/tile-sources')
def get_tile_sources():
    """Local tile URLs, always.

    These used to be the ArcGIS templates, so the browser went straight out to
    the internet and the whole server-side cache was bypassed (L-8). Serving
    /tiles/ means the map works at a base with no route out, for any area that
    has been cached.
    """
    prefix = request.script_root.rstrip('/')
    offline = tiles_offline()
    return jsonify({
        'vfr': f'{prefix}/tiles/vfr/{{z}}/{{x}}/{{y}}.png',
        'ifr_low': f'{prefix}/tiles/ifr_low/{{z}}/{{x}}/{{y}}.png',
        'ifr_high': f'{prefix}/tiles/ifr_high/{{z}}/{{x}}/{{y}}.png',
        # L2-10: the online-only Satellite and Street layers. They go straight
        # from the browser to the provider (not through the cache), so they are
        # only offered when this station is allowed to use the internet, and
        # only ever from here - never as literals in the JavaScript.
        'online_layers': {} if offline else dict(ONLINE_LAYER_SOURCES),
        'offline': offline,
    })

# ---------------------------------------------------------------- tiles (L-8)
#
# The mission base has no internet. Tiles used to be requested straight from
# ArcGIS by the browser, so the map was blank there - and the server-side cache
# that existed to prevent exactly that only ran under __main__, never under
# gunicorn, so the charts volume stayed empty and /tiles/ answered 204 forever.
# Nothing asked it for a tile anyway: /api/tile-sources handed the frontend the
# ArcGIS URLs directly.
#
# Now every tile goes through here. Cache first; on a miss, fetch upstream once
# and keep it, so an online planning session populates the cache for the
# offline exercise without anyone running a separate step.
#
# The cache directory names are not the same as the layer keys - 'ifr_low' is
# stored under 'ifr' because that is what download_tiles() was called with -
# so this map is the single place that knows both, and it is also the
# whitelist. chart_type arrives from the URL, and it is about to be used to
# build a path that gets WRITTEN to, so it never reaches the filesystem
# unvalidated.
TILE_CACHE = {
    'vfr':      {'dir': 'vfr',      'upstream': TILE_SOURCES['vfr']},
    'ifr_low':  {'dir': 'ifr',      'upstream': TILE_SOURCES['ifr_low']},
    'ifr_high': {'dir': 'ifr_high', 'upstream': TILE_SOURCES['ifr_high']},
}

# A base with no route out must not pay a network timeout per tile: Leaflet asks
# for dozens at once and every one of them would hold a worker. After a failure
# we stop trying for a while and serve straight from the cache.
TILE_FETCH_TIMEOUT_S = 4
TILE_UPSTREAM_COOLDOWN_S = 60
_tile_upstream = {'blocked_until': 0.0}
_tile_fetch_lock = threading.Lock()


def tiles_offline():
    """True when this station must never reach for the network."""
    return os.environ.get('CAPVSAR_TILES_OFFLINE', '').strip().lower() in (
        '1', 'true', 'yes', 'on')


def _fetch_tile_upstream(spec, z, x, y, dest_path):
    """Fetch one tile and cache it. Returns the bytes, or None."""
    if tiles_offline():
        return None
    now = time.time()
    if now < _tile_upstream['blocked_until']:
        return None
    try:
        url = spec['upstream'].format(z=z, x=x, y=y)
        r = requests.get(url, timeout=TILE_FETCH_TIMEOUT_S, headers={
            'User-Agent': 'Mozilla/5.0 CAP-VSAR-FlightPlanner/1.0',
            'Referer': 'https://www.faa.gov/',
        })
    except Exception:
        with _tile_fetch_lock:
            _tile_upstream['blocked_until'] = time.time() + TILE_UPSTREAM_COOLDOWN_S
        return None
    if r.status_code != 200 or len(r.content) <= 100:
        return None
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        # Write beside the target and rename, so a killed worker cannot leave a
        # half-written PNG in the cache to be served forever after.
        tmp = dest_path + '.part'
        with open(tmp, 'wb') as f:
            f.write(r.content)
        os.replace(tmp, dest_path)
    except OSError:
        pass                      # a read-only volume is not a reason to fail
    return r.content


@app.route('/tiles/<chart_type>/<int:z>/<int:x>/<int:y>.png')
def serve_tile(chart_type, z, x, y):
    # L-10: chart_type reaches the filesystem only as a TILE_CACHE key, and
    # z/x/y are <int:> converters, so traversal was never reachable here. The
    # explicit membership test states that invariant rather than leaving it to
    # be re-derived by the next reader of this function.
    if chart_type not in TILE_CACHE:
        return '', 404
    spec = TILE_CACHE[chart_type]
    tile_dir = os.path.join(CHARTS_DIR, spec['dir'], str(z), str(x))
    tile_file = f'{y}.png'
    full_path = os.path.join(tile_dir, tile_file)
    if os.path.exists(full_path) and os.path.getsize(full_path) > 100:
        return send_from_directory(tile_dir, tile_file, mimetype='image/png')

    body = _fetch_tile_upstream(spec, z, x, y, full_path)
    if body is None:
        # No tile and no way to get one. 204 leaves Leaflet's blank tile in
        # place, which is what an uncached corner of the map looked like
        # before; it is not an error.
        return '', 204
    return Response(body, mimetype='image/png')

@app.route('/api/update-database', methods=['POST'])
def trigger_update():
    security_error = _request_security_error(require_json=True)
    if security_error:
        return security_error
    started = start_database_update()
    return jsonify({'success': started})

@app.route('/api/update-status')
def get_status():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM airports')
    cnt = c.fetchone()[0]
    conn.close()
    status = _read_update_status()
    locked = database_update_running()
    if locked and not status.get('in_progress'):
        status.update(in_progress=True,
                      message='Aviation database update starting')
    elif not locked and status.get('in_progress'):
        status.update(in_progress=False,
                      message='Aviation database update was interrupted')
    return jsonify({'in_progress': status['in_progress'], 'message': status['message'],
                   'progress': status['progress'], 'airports': cnt})

@app.route('/api/nearest-airport')
def nearest_airport():
    try:
        lat = float(request.args.get('lat', 0))
        lon = float(request.args.get('lon', 0))
        radius_nm = float(request.args.get('radius_nm', 20))
    except (ValueError, TypeError):
        return jsonify({'found': False, 'error': 'Invalid coordinates'})

    cos_lat = math.cos(math.radians(lat))
    lat_delta = radius_nm / 60.0
    lon_delta = radius_nm / max(0.001, 60.0 * cos_lat)

    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    results = []

    # ORDER BY approximate squared distance so LIMIT keeps the closest rows
    # (PK order could drop the true nearest fix in dense areas like SoCal)
    cos2 = cos_lat * cos_lat
    c.execute('''SELECT icao, name, city, latitude, longitude, elevation
                 FROM airports
                 WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?
                 ORDER BY (latitude-?)*(latitude-?) + (longitude-?)*(longitude-?)*?
                 LIMIT 300''',
              (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta,
               lat, lat, lon, lon, cos2))
    for row in c.fetchall():
        d = gc_dist(lat, lon, row[3], row[4])
        if d <= radius_nm:
            results.append({'ident': row[0], 'name': row[1], 'city': row[2],
                            'lat': row[3], 'lon': row[4], 'type': 'airport', 'distance_nm': round(d, 1)})

    c.execute('''SELECT id, name, type, latitude, longitude
                 FROM navaids
                 WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?
                 ORDER BY (latitude-?)*(latitude-?) + (longitude-?)*(longitude-?)*?
                 LIMIT 150''',
              (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta,
               lat, lat, lon, lon, cos2))
    for row in c.fetchall():
        d = gc_dist(lat, lon, row[3], row[4])
        if d <= radius_nm:
            results.append({'ident': row[0], 'name': row[1], 'type': row[2],
                            'lat': row[3], 'lon': row[4], 'distance_nm': round(d, 1)})

    conn.close()

    if not results:
        return jsonify({'found': False})

    results.sort(key=lambda x: x['distance_nm'])
    return jsonify({'found': True, 'nearest': results[:20]})

@app.route('/api/airport-info/<icao>')
def airport_info(icao):
    a = get_airport(icao.upper())
    if not a: return jsonify({'success': False})
    return jsonify({'success': True, 'airport': a, 'runways': get_runways(icao.upper())})

@app.route('/api/calculate-route', methods=['POST'])
def calc_route():
    d = _body()
    dep = _text(d, 'departure', '', 64).upper()
    dest = _text(d, 'destination', '', 64).upper()
    wpts = [w.upper() for w in _text_list(d, 'waypoints')]
    alt = _num(d, 'cruise_altitude', 6500, 0, 60000, integer=True)
    rpm = _num(d, 'rpm', 2400, 0, 10000, integer=True)
    reserve_minutes = _num(d, 'reserve_minutes', 45, 15, 120, integer=True, clamp=True)
    manifold_pressure = _num(d, 'manifold_pressure', 20, 0, 100)

    ac = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]
    pts = [dep] + wpts + [dest]

    coords = []
    user_n = 0
    for p in pts:
        label, ident = split_route_label(p)
        c = get_coords(ident)
        if not c: return jsonify({'success': False, 'error': f'Not found: {p}'})
        # L2-7: a named point ("DATUM=@33.1,-117.0") keeps its name, so the
        # nav log shows the same labels the .fms export carries.
        if not label:
            if c[2] == 'user':
                user_n += 1
                label = f'USR{user_n}'
            else:
                label = ident
        coords.append({'identifier': label, 'lat': c[0], 'lon': c[1], 'type': c[2], 'data': c[3]})

    try:
        cruise = get_cruise(alt, rpm, manifold_pressure)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    mid = coords[len(coords)//2]
    winds = fetch_winds_aloft(mid['lat'], mid['lon'])
    
    wdir, wspd = 0, 0
    if winds and 'levels' in winds:
        lvls = sorted(winds['levels'].keys())
        nrst = min(lvls, key=lambda x: abs(x-alt))
        wdir = winds['levels'][nrst]['direction']
        wspd = winds['levels'][nrst]['speed']
    # L2-5: simulate_winds() invents 15-30 kt from a hash of the position. It
    # is fine for a briefing placeholder but headings, groundspeeds, times and
    # fuel for every leg would carry a fictitious wind with nothing on the nav
    # log saying so. Without real winds the route is planned in still air and
    # says that it was.
    winds_available = bool(winds) and 'levels' in winds and not winds.get('simulated', False)
    if not winds_available:
        wdir, wspd = 0, 0
    
    segs = []
    tot_dist, tot_time, tot_fuel = 0, 0, 0
    
    for i in range(len(coords)-1):
        fr, to = coords[i], coords[i+1]
        dist = gc_dist(fr['lat'], fr['lon'], to['lat'], to['lon'])
        tc = bearing(fr['lat'], fr['lon'], to['lat'], to['lon'])
        try:
            wca, gs = wind_corr(tc, cruise['true_airspeed'], wdir, wspd)
        except ValueError as exc:
            return jsonify({'success': False, 'error': f"{fr['identifier']} to {to['identifier']}: {exc}"}), 400
        # MH = TH - variation (east positive: "east is least")
        var = mag_var((fr['lat'] + to['lat']) / 2, (fr['lon'] + to['lon']) / 2)
        mh = (tc + wca - var) % 360
        lt = (dist/gs)*60 if gs > 0 else 0
        lf = (lt/60) * cruise['fuel_flow_gph']

        segs.append({'from': fr['identifier'], 'to': to['identifier'],
            'distance_nm': round(dist,1), 'true_course': round(tc,0),
            'wind_correction': round(wca,0), 'magnetic_heading': round(mh,0),
            'mag_var': round(var,1),
            'ground_speed': round(gs,0), 'time_minutes': round(lt,0), 'fuel_gallons': round(lf,1)})
        tot_dist += dist; tot_time += lt; tot_fuel += lf
    
    dep_elev = (coords[0]['data'] or {}).get('elevation') or 0
    climb = get_climb(dep_elev, alt)
    taxi = ac['taxi_fuel']
    reserve = (reserve_minutes / 60.0) * cruise['fuel_flow_gph']
    
    return jsonify({
        'success': True, 'route_points': coords, 'segments': segs,
        'winds_aloft': {'altitude': alt, 'direction': wdir, 'speed': wspd,
                        'source': (winds.get('station', 'estimated')
                                   if winds_available else 'none - planned in still air'),
                        'simulated': winds.get('simulated', True),
                        'available': winds_available},
        'aircraft': ac['name'],
        'cruise': dict(cruise, altitude=alt, rpm=rpm),
        'full_fuel_endurance_hours': round(max(0, (ac['usable_fuel'] - taxi - climb['fuel_gallons'] - reserve) / cruise['fuel_flow_gph']) + climb['time_minutes'] / 60, 2),
        'climb': climb,
        'totals': {
            'distance_nm': round(tot_dist,1),
            'time_minutes': round(tot_time + climb['time_minutes'],0),
            'taxi_fuel': taxi, 'climb_fuel': climb['fuel_gallons'],
            'cruise_fuel': round(tot_fuel,1), 'reserve_fuel': round(reserve,1),
            'total_fuel': round(taxi + climb['fuel_gallons'] + tot_fuel + reserve, 1)
        }
    })

@app.route('/api/weather-briefing', methods=['POST'])
def weather_briefing():
    d = _body()
    dep = _text(d, 'departure', '', 64).upper()
    dest = _text(d, 'destination', '', 64).upper()
    wpts = [w.upper() for w in _text_list(d, 'waypoints')]
    try:
        apts = [a for a in [dep] + wpts + [dest] if a]
        
        briefing = {
            'generated_at': get_utc_now().strftime('%Y-%m-%d %H:%M UTC'),
            'route': ' -> '.join(apts),
            'metars': [], 'tafs': [], 'winds_aloft': None,
            'pireps': [], 'airmets_sigmets': [], 'notams': [], 'tfrs': []
        }
        
        for a in apts:
            briefing['metars'].append(fetch_metar(a))
            briefing['tafs'].append(fetch_taf(a))
            briefing['notams'].append({'airport': a, 'text': f'Check notams.faa.gov for {a}', 'simulated': True})
        
        dc, nc = get_coords(dep), get_coords(dest)
        if dc and nc:
            mlat, mlon = (dc[0]+nc[0])/2, (dc[1]+nc[1])/2
            briefing['winds_aloft'] = fetch_winds_aloft(mlat, mlon)
        
        briefing['tfrs'] = [{'notam_id': 'INFO', 'type': 'INFO', 'description': 'Check tfr.faa.gov'}]
        
        return jsonify({'success': True, 'briefing': briefing})
    except Exception:
        # L2-3: the cause goes to the log, not to the caller.
        app.logger.exception('weather briefing failed')
        return jsonify({'success': False,
                        'error': 'The weather briefing could not be built'}), 502

@app.route('/api/performance/takeoff', methods=['POST'])
def perf_to():
    try:
        d = _body()
        return jsonify(calc_takeoff(_num(d, 'weight', 3100, 0, 10000, integer=True),
                                    _num(d, 'pressure_altitude', 0, -2000, 60000, integer=True),
                                    _num(d, 'temperature', 15, -100, 100, integer=True),
                                    _num(d, 'headwind', 0, -200, 200, integer=True)))
    except (ValueError, TypeError) as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

@app.route('/api/performance/landing', methods=['POST'])
def perf_land():
    try:
        d = _body()
        return jsonify(calc_landing(_num(d, 'pressure_altitude', 0, -2000, 60000, integer=True),
                                    _num(d, 'temperature', 15, -100, 100, integer=True),
                                    _num(d, 'headwind', 0, -200, 200, integer=True)))
    except (ValueError, TypeError) as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

@app.route('/api/weight-balance', methods=['POST'])
def wb():
    d = _body()
    ac = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]
    arms = ac['arms']
    ew = _num(d, 'empty_weight', ac['empty_weight'], 0, 10000)
    em = _num(d, 'empty_moment', ac['empty_weight_moment'], 0, 100000)
    p = _num(d, 'pilot_weight', 0, 0, 2000)
    f = _num(d, 'front_passenger_weight', 0, 0, 2000)
    r = _num(d, 'rear_passenger_weight', 0, 0, 2000)
    b = _num(d, 'baggage_weight', 0, 0, 2000)
    fu = _num(d, 'fuel_gallons', 0, 0, 1000)

    warnings = []
    if fu > ac['usable_fuel']:
        warnings.append(f"Fuel exceeds usable capacity ({ac['usable_fuel']} gal)")
    if b > ac['baggage1_max']:
        warnings.append(f"Baggage exceeds {ac['baggage1_max']} lb limit")

    fw = fu * ac['fuel_weight_per_gallon']
    tw = ew + p + f + r + b + fw
    tm = (em*1000 + (p + f)*arms['front_seats'] + r*arms['rear_seats']
          + b*arms['baggage1'] + fw*ac['fuel_arm'])
    cg = tm/tw if tw > 0 else 0

    # Forward CG limit varies with weight (linear between POH envelope points)
    envelope = ac['cg_fwd_points']
    fwd_limit = envelope[0][1] if tw <= envelope[0][0] else envelope[-1][1]
    for (w1, f1), (w2, f2) in zip(envelope, envelope[1:]):
        if w1 <= tw <= w2:
            fwd_limit = f1 + (tw - w1) / (w2 - w1) * (f2 - f1)
            break

    within_weight = tw <= ac['max_takeoff_weight']
    within_cg = fwd_limit <= cg <= ac['cg_aft_limit']

    return jsonify({
        'aircraft': ac['name'], 'baseline': 'POH sample: 1924 lb, moment/1000 70.9',
        'max_landing_weight': ac['max_landing_weight'],
        'fuel_burn_before_landing_gallons': math.ceil(max(0, tw - ac['max_landing_weight']) / ac['fuel_weight_per_gallon'] * 10) / 10,
        'total_weight': round(tw,1), 'max_weight': ac['max_takeoff_weight'],
        'weight_margin': round(ac['max_takeoff_weight']-tw,1),
        'cg': round(cg,2), 'cg_forward_limit': round(fwd_limit,2), 'cg_aft_limit': ac['cg_aft_limit'],
        'within_weight_limits': within_weight,
        'within_cg_limits': within_cg,
        'within_all_limits': within_weight and within_cg and not warnings,
        'warnings': warnings,
        'moment_1000': round(tm/1000,1)
    })

# d-TPP airport diagram cache
dtpp_cache = {'cycle': None, 'diagrams': {}, 'loading': False}

# L2-9: FAA d-TPP cycles are 28-day, AIRAC-style: 13 a year, each named YYNN
# where NN counts the cycles that take effect in that year, starting at 01.
# 2601 took effect on 2026-01-22 and every other cycle is a multiple of 28 days
# from it. (The old code used the calendar month, so for most of the year it
# asked the FAA for a cycle that does not exist.)
DTPP_ANCHOR = datetime(2026, 1, 22, tzinfo=timezone.utc).date()
DTPP_CYCLE_DAYS = 28


def dtpp_cycle_for(day):
    """The d-TPP cycle id (YYNN) in effect on `day` (a date, taken as UTC)."""
    steps = (day - DTPP_ANCHOR).days // DTPP_CYCLE_DAYS
    effective = DTPP_ANCHOR + timedelta(days=DTPP_CYCLE_DAYS * steps)
    # First cycle that takes effect on or after 1 January of that year.
    jan1 = effective.replace(month=1, day=1)
    first = effective - timedelta(
        days=DTPP_CYCLE_DAYS * ((effective - jan1).days // DTPP_CYCLE_DAYS))
    number = (effective - first).days // DTPP_CYCLE_DAYS + 1
    return f'{effective.year % 100:02d}{number:02d}'


def get_dtpp_cycle():
    """The current FAA d-TPP cycle string (YYNN), by UTC date."""
    return dtpp_cycle_for(get_utc_now().date())

def load_dtpp_diagrams():
    """Download and parse the FAA d-TPP metafile to build airport diagram index."""
    import xml.etree.ElementTree as ET

    if dtpp_cache['loading']:
        return
    dtpp_cache['loading'] = True

    cycle = get_dtpp_cycle()
    log_msg(f"Downloading FAA d-TPP metafile for cycle {cycle}...")

    try:
        url = f'https://aeronav.faa.gov/d-tpp/{cycle}/xml_data/d-tpp_Metafile.xml'
        r = requests.get(url, timeout=60, headers={'User-Agent': 'CAP 487-Planner/1.0'})
        if r.status_code != 200:
            log_msg(f"d-TPP metafile not found for cycle {cycle}")
            dtpp_cache['loading'] = False
            return

        root = ET.fromstring(r.content)
        diagrams = {}

        for apt in root.iter('airport_name'):
            apt_ident = apt.get('apt_ident', '')
            icao_ident = apt.get('icao_ident', '')
            for rec in apt.iter('record'):
                cn = rec.find('chart_name')
                pdf = rec.find('pdf_name')
                if cn is not None and pdf is not None and 'AIRPORT DIAGRAM' in (cn.text or ''):
                    pdf_url = f'https://aeronav.faa.gov/d-tpp/{cycle}/{pdf.text}'
                    if icao_ident:
                        diagrams[icao_ident] = pdf_url
                    if apt_ident:
                        diagrams[apt_ident] = pdf_url

        dtpp_cache['cycle'] = cycle
        dtpp_cache['diagrams'] = diagrams
        log_msg(f"Loaded {len(diagrams)} airport diagrams from d-TPP cycle {cycle}")
    except Exception as e:
        log_msg(f"Error loading d-TPP: {e}")
    finally:
        dtpp_cache['loading'] = False

@app.route('/api/airport-detail/<icao>')
def airport_detail(icao):
    """Get detailed airport info including diagram URL."""
    icao = icao.upper()
    a = get_airport(icao)
    if not a:
        return jsonify({'success': False, 'error': f'Airport {icao} not found'})

    runways = get_runways(icao)
    faa_id = icao[1:] if icao.startswith('K') and len(icao) == 4 else icao

    # Load d-TPP diagram index if not cached
    if not dtpp_cache['diagrams'] and not dtpp_cache['loading']:
        load_dtpp_diagrams()

    # Look up diagram URL
    diagram_url = dtpp_cache['diagrams'].get(icao) or dtpp_cache['diagrams'].get(faa_id)

    # Fetch METAR for current conditions
    metar = fetch_metar(icao)

    return jsonify({
        'success': True,
        'airport': a,
        'runways': runways,
        'diagram_url': diagram_url,
        'metar': metar,
        'faa_id': faa_id
    })

@app.route('/api/terrain-profile', methods=['POST'])
def terrain_profile():
    """Sample terrain elevation along a route using USGS Elevation Point Query Service."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    d = _body()
    route_points = _points(d, 'route_points')
    cruise_altitude = _num(d, 'cruise_altitude', 6000, -2000, 60000, integer=True)

    if len(route_points) < 2:
        return jsonify({'success': False, 'error': 'Need at least 2 route points'}), 400

    # Generate sample points along the route
    samples = []
    cumulative_dist = 0.0
    MAX_SAMPLES = 80  # Cap to keep response time reasonable

    # First pass: calculate total distance
    total_route_dist = 0.0
    for i in range(len(route_points) - 1):
        p1, p2 = route_points[i], route_points[i + 1]
        total_route_dist += gc_dist(p1['lat'], p1['lon'], p2['lat'], p2['lon'])

    # Sample interval based on total distance
    sample_interval = max(1.0, total_route_dist / MAX_SAMPLES)

    for i in range(len(route_points) - 1):
        p1 = route_points[i]
        p2 = route_points[i + 1]
        lat1, lon1 = p1['lat'], p1['lon']
        lat2, lon2 = p2['lat'], p2['lon']
        seg_dist = gc_dist(lat1, lon1, lat2, lon2)

        n_samples = max(2, int(seg_dist / sample_interval))
        for j in range(n_samples):
            frac = j / max(1, n_samples - 1)
            lat = lat1 + (lat2 - lat1) * frac
            lon = lon1 + (lon2 - lon1) * frac
            dist = cumulative_dist + seg_dist * frac

            sample = {'lat': round(lat, 5), 'lon': round(lon, 5), 'dist_nm': round(dist, 1)}
            if j == 0:
                sample['waypoint'] = p1.get('identifier', '')
            samples.append(sample)

        cumulative_dist += seg_dist

    # Add final point
    last = route_points[-1]
    samples.append({
        'lat': round(last['lat'], 5),
        'lon': round(last['lon'], 5),
        'dist_nm': round(cumulative_dist, 1),
        'waypoint': last.get('identifier', '')
    })

    # Deduplicate very close points
    filtered = [samples[0]]
    for s in samples[1:]:
        if abs(s['dist_nm'] - filtered[-1]['dist_nm']) > 0.3 or s.get('waypoint'):
            filtered.append(s)
    if filtered[-1]['dist_nm'] != samples[-1]['dist_nm']:
        filtered.append(samples[-1])
    samples = filtered

    # Query USGS elevation API in parallel
    USGS_URL = 'https://epqs.nationalmap.gov/v1/json'

    def fetch_elevation(idx, sample):
        try:
            r = requests.get(USGS_URL, params={
                'x': sample['lon'], 'y': sample['lat'],
                'units': 'Feet', 'wkid': 4326, 'includeDate': False
            }, timeout=8)
            if r.status_code == 200:
                elev = float(r.json().get('value', 0))
                return idx, max(0, elev) if elev > -1000 else 0
        except Exception:
            pass
        # L2-4: "could not look it up" is not "sea level". Offline, every
        # route used to report 0 ft terrain and a green ADEQUATE clearance.
        return idx, None

    # Fetch all elevations with 10 parallel workers
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(fetch_elevation, i, s) for i, s in enumerate(samples)]
        results = {}
        for f in as_completed(futures):
            idx, elev = f.result()
            results[idx] = elev

    max_elevation = 0
    unknown_samples = 0
    for i, sample in enumerate(samples):
        elev = results.get(i)
        sample['elevation_known'] = elev is not None
        if elev is None:
            unknown_samples += 1
        # Unknown samples keep a numeric 0 so the profile can still be drawn
        # and the climb computed, but never count towards terrain or clearance.
        sample['elevation_ft'] = round(elev) if elev is not None else 0
        if elev is not None:
            max_elevation = max(max_elevation, sample['elevation_ft'])

    # Compute flight path with climb and descent profiles
    ac = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]
    dep_elev = samples[0]['elevation_ft']
    dest_elev = samples[-1]['elevation_ft']
    rpm = int(d.get('rpm', 2400))
    try:
        cruise = get_cruise(cruise_altitude, rpm, float(d.get('manifold_pressure', 20)))
    except (TypeError, ValueError) as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    gs = cruise['true_airspeed']  # approximate GS (no wind for profile)

    # Climb: interpolate distance to reach cruise altitude from departure elevation
    climb_perf = ac['climb_performance']
    climb_alts = sorted(climb_perf.keys())

    def interp_climb_dist(target_alt):
        """Get distance (NM) to climb from sea level to target_alt."""
        if target_alt <= 0:
            return 0
        for j in range(len(climb_alts) - 1):
            a1, a2 = climb_alts[j], climb_alts[j + 1]
            if a1 <= target_alt <= a2:
                frac = (target_alt - a1) / (a2 - a1)
                d1, d2 = climb_perf[a1][2], climb_perf[a2][2]
                return d1 + (d2 - d1) * frac
        return climb_perf[climb_alts[-1]][2]

    # Distance to climb from dep_elev to cruise_altitude
    climb_dist = interp_climb_dist(cruise_altitude) - interp_climb_dist(dep_elev)
    climb_dist = max(0, climb_dist)

    # Descent: 500 fpm at cruise ground speed
    descent_alt = cruise_altitude - dest_elev
    if descent_alt > 0 and gs > 0:
        descent_time_min = descent_alt / 500.0  # minutes at 500 fpm
        descent_dist = (descent_time_min / 60.0) * gs  # NM
    else:
        descent_dist = 0

    # Top of descent point — ensure it doesn't overlap with climb
    tod_dist = max(climb_dist, cumulative_dist - descent_dist)

    # If climb + descent exceed total distance, adjust both proportionally
    if climb_dist + descent_dist > cumulative_dist:
        ratio = cumulative_dist / (climb_dist + descent_dist)
        climb_dist = climb_dist * ratio
        descent_dist = descent_dist * ratio
        tod_dist = climb_dist  # No cruise segment — go directly from climb to descent

    # Assign flight_path_alt to each sample point
    min_clearance = float('inf')
    for sample in samples:
        dist = sample['dist_nm']
        if dist <= climb_dist and climb_dist > 0:
            # Climbing phase: linear from dep_elev to cruise_altitude
            frac = dist / climb_dist
            sample['flight_alt'] = round(dep_elev + (cruise_altitude - dep_elev) * frac)
        elif dist >= tod_dist and descent_dist > 0:
            # Descending phase: linear from cruise_altitude to dest_elev
            frac = (dist - tod_dist) / descent_dist if descent_dist > 0 else 1
            frac = min(1.0, frac)
            sample['flight_alt'] = round(cruise_altitude - (cruise_altitude - dest_elev) * frac)
        else:
            # Cruise phase
            sample['flight_alt'] = cruise_altitude

        clearance = sample['flight_alt'] - sample['elevation_ft']
        # Skip departure/destination points for min clearance (on the ground)
        if dist > 0.5 and dist < cumulative_dist - 0.5 and sample['elevation_known']:
            min_clearance = min(min_clearance, clearance)

    terrain_known = unknown_samples == 0
    if min_clearance == float('inf'):
        min_clearance = (cruise_altitude - max_elevation
                         if unknown_samples < len(samples) else None)

    return jsonify({
        'success': True,
        'profile': samples,
        'cruise_altitude': cruise_altitude,
        'terrain_known': terrain_known,
        'terrain_unknown_samples': unknown_samples,
        'max_terrain': round(max_elevation) if unknown_samples < len(samples) else None,
        'min_clearance': round(min_clearance) if min_clearance is not None else None,
        # None means "cannot say": a failed lookup must not read as adequate.
        'vfr_clearance_ok': (None if min_clearance is None
                             else (False if min_clearance < 1000
                                   else (True if terrain_known else None))),
        'ifr_mea_margin': (None if min_clearance is None
                           else (False if min_clearance < 2000
                                 else (True if terrain_known else None))),
        'total_distance': round(cumulative_dist, 1),
        'climb_distance': round(climb_dist, 1),
        'descent_distance': round(descent_dist, 1),
        'top_of_descent': round(tod_dist, 1),
        'departure_elevation': dep_elev,
        'destination_elevation': dest_elev
    })

# =============================================================================
# Civil Air Patrol Search and Rescue (SAR) & V-SAR Integration API
# =============================================================================

def pattern_search_centre(wpts, datum):
    """Where the search area is centred, for the alert circle and the beacon.

    The expanding square is built around its datum. A parallel track's first
    waypoint is a lane start half a spacing inside one edge of the box and a
    creeping line's is the end of its first sweep, so neither is the centre
    (L2-6). The middle of the bounding box is, to well inside the accuracy a
    briefing needs for areas of tens of miles.
    """
    if not wpts:
        return {'lat': datum[0], 'lon': datum[1]}
    if wpts[0].get('identifier') == 'DATUM':
        return {'lat': wpts[0]['lat'], 'lon': wpts[0]['lon']}
    lats = [p['lat'] for p in wpts]
    lons = [p['lon'] for p in wpts]
    return {'lat': round((min(lats) + max(lats)) / 2, 6),
            'lon': round((min(lons) + max(lons)) / 2, 6)}


@app.route('/api/sar/generate-pattern', methods=['POST'])
def sar_generate():
    data = _body()
    ptype = _text(data, 'pattern_type', 'expanding_square', 40)

    # Resolve datum
    # L2-1: an unresolvable datum used to fall through to a hard-coded point
    # near KSEE and return success, so a mistyped identifier planned (and
    # exported, and pushed to the console) a search 10 NM from where the
    # crew meant. Say so instead.
    raw_datum = data.get('datum', '')
    if not isinstance(raw_datum, str):
        return jsonify({'success': False, 'error': 'datum must be an identifier or @lat,lon'}), 400
    datum_input = raw_datum.strip()
    datum_coords = None
    if datum_input:
        c = get_coords(datum_input)
        if not c:
            return jsonify({'success': False, 'error':
                f'Datum "{datum_input}" was not found. Check the identifier, '
                f'use @lat,lon, or wait for the aviation database to finish loading.'}), 400
        datum_coords = (c[0], c[1])
    elif 'datum_lat' in data and 'datum_lon' in data:
        try:
            datum_coords = (_num(data, 'datum_lat', None, -90, 90),
                            _num(data, 'datum_lon', None, -180, 180))
        except RequestError as exc:
            return jsonify({'success': False, 'error':
                f'datum_lat and datum_lon must be numbers in range ({exc})'}), 400
    else:
        return jsonify({'success': False, 'error':
            'A datum is required: an airport, navaid, @lat,lon, or datum_lat and datum_lon.'}), 400
            
    # The UI's <input min/max> only constrains the form; this is a public POST
    # endpoint anyone can call directly, so the same bounds are enforced here.
    # spacing_nm floors above zero (both creeping_line and parallel_track
    # divide by it - 0 was an unhandled ZeroDivisionError) and num_legs caps
    # to keep one request from generating an unbounded waypoint list.
    spacing = _num(data, 'spacing_nm', 1.0, 0.1, 20.0, clamp=True)
    legs = _num(data, 'num_legs', 8, 1, 40, integer=True, clamp=True)
    init_hdg = _num(data, 'initial_heading', 0.0, -36000, 36000) % 360.0
    coverage_truncated = False
    turn_dir = _text(data, 'turn_direction', 'right', 10).lower()
    if turn_dir not in ('left', 'right'):
        raise RequestError('turn_direction must be "left" or "right"')

    try:
        if ptype == 'expanding_square':
            wpts = generate_expanding_square(datum_coords[0], datum_coords[1], spacing, legs, init_hdg, turn_dir)
        elif ptype == 'creeping_line':
            end_lat = _num(data, 'end_lat', datum_coords[0] + 0.15, -90, 90)
            end_lon = _num(data, 'end_lon', datum_coords[1] + 0.15, -180, 180)
            sweep_w = _num(data, 'sweep_width_nm', 3.0, 0.1, 50.0, clamp=True)
            coverage_truncated = math.ceil(gc_dist(*datum_coords, end_lat, end_lon) / spacing) > legs
            wpts = generate_creeping_line(datum_coords[0], datum_coords[1], end_lat, end_lon, sweep_w, spacing, legs)
        elif ptype == 'parallel_track':
            box_len = max(0.1, _num(data, 'length_nm', 5.0, 0, 1e6))
            if box_len > MAX_PARALLEL_DIMENSION_NM:
                return jsonify({'success': False, 'error':
                    f'length_nm must be at most {MAX_PARALLEL_DIMENSION_NM:g}'}), 400
            box_w = max(0.1, _num(data, 'width_nm', 4.0, 0, 1e6))
            if box_w > MAX_PARALLEL_DIMENSION_NM:
                return jsonify({'success': False, 'error':
                    f'width_nm must be at most {MAX_PARALLEL_DIMENSION_NM:g}'}), 400
            sweeps = max(1, math.ceil(box_w / spacing))
            leg_count = 2 * sweeps - 1
            if leg_count > MAX_PARALLEL_LEGS:
                return jsonify({'success': False, 'error':
                    f'width_nm with spacing_nm would generate {sweeps} sweeps '
                    f'({leg_count} legs); maximum is {MAX_PARALLEL_LEGS} legs'}), 400
            axis_hdg = _num(data, 'axis_heading', 0.0, -36000, 36000) % 360.0
            wpts = generate_parallel_track(datum_coords[0], datum_coords[1], box_len, box_w, axis_hdg, spacing)
        else:
            return jsonify({'success': False, 'error': f'Unknown pattern: {ptype}'}), 400
    except (TypeError, ValueError) as exc:
        if isinstance(exc, RequestError):
            raise
        app.logger.exception('pattern generation failed')
        return jsonify({'success': False, 'error': 'One or more pattern parameters were not valid'}), 400

    tot_dist = 0.0
    for i in range(len(wpts) - 1):
        tot_dist += gc_dist(wpts[i]['lat'], wpts[i]['lon'], wpts[i+1]['lat'], wpts[i+1]['lon'])
        
    cruise = get_cruise(6500, 2400)
    tas = cruise['true_airspeed']
    est_time_min = (tot_dist / tas) * 60.0 if tas > 0 else 0
    est_fuel_gal = (est_time_min / 60.0) * cruise['fuel_flow_gph']
    
    route_fragment = " ".join(f"@{p['lat']:.5f},{p['lon']:.5f}" for p in wpts)
    
    # L2-2: say now, at preview time, that this pattern cannot be exported as
    # one flight plan, rather than at the export button.
    fms_over = len(wpts) > MAX_FMS_WAYPOINTS
    warnings = [fms_waypoint_limit_message(len(wpts))] if fms_over else []

    return jsonify({
        'success': True,
        'pattern_type': ptype,
        'coverage_truncated': coverage_truncated,
        'fms_waypoint_count': len(wpts),
        'fms_waypoint_limit': MAX_FMS_WAYPOINTS,
        'exceeds_fms_limit': fms_over,
        'warnings': warnings,
        'datum': {'lat': datum_coords[0], 'lon': datum_coords[1]},
        'search_centre': pattern_search_centre(wpts, datum_coords),
        'waypoints': wpts,
        'total_distance_nm': round(tot_dist, 1),
        'estimated_time_minutes': round(est_time_min, 0),
        'estimated_fuel_gallons': round(est_fuel_gal, 1),
        'route_fragment': route_fragment
    })

@app.route('/api/sar/export-fms', methods=['POST'])
def sar_export_fms():
    data = _body()
    dep = _text(data, 'departure', DEFAULT_AIRPORT, 8)
    dest = _text(data, 'destination', DEFAULT_AIRPORT, 8)
    wpts = _points(data, 'waypoints')
    alt = _num(data, 'altitude', 6500, -2000, 60000, integer=True)
    try:
        fms_text = generate_xplane_fms_content(dep, dest, wpts, alt)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    return jsonify({
        'success': True,
        'filename': f"{fms_identifier(dep)}_{fms_identifier(dest)}_SAR.fms",
        'content': fms_text
    })

def point_elevation_ft(lat, lon, timeout=6):
    """Ground elevation at one point, or None (L-9).

    The V-SAR push sent beacon_elev_ft: 0.0 - sea level. The DF propagation
    model uses that elevation for BOTH ends of the radio horizon and as one end
    of the terrain line-of-sight ray, so a beacon planted at sea level in
    mountainous country modelled nothing real: the horizon was computed from a
    height the beacon does not have, and the ray ran to the wrong place.
    """
    try:
        r = requests.get('https://epqs.nationalmap.gov/v1/json', params={
            'x': lon, 'y': lat, 'units': 'Feet', 'wkid': 4326,
            'includeDate': False}, timeout=timeout)
        if r.status_code != 200:
            return None
        value = float(r.json().get('value'))
    except (requests.RequestException, TypeError, ValueError, KeyError):
        return None
    # The service answers -1000000 for "no data", and a negative elevation is
    # not something a CAP search area has.
    return max(0.0, value) if value > -1000 else None


# How far to move the beacon off the planned search datum, and the environment
# variable that changes it. The datum is where the planner *thinks* the beacon
# is; putting the real one exactly there means the crew flies to the middle of
# their own search area and finds it immediately, which trains nothing. A real
# distress beacon is wherever it is.
BEACON_OFFSET_NM = float(os.environ.get('CAPVSAR_BEACON_OFFSET_NM', '2.5'))


def offset_beacon(lat, lon, seed_text):
    """Move the beacon off the datum by BEACON_OFFSET_NM on a stable bearing.

    Deterministic per plan, so re-pushing the same sortie does not teleport the
    beacon, and so an instructor can reproduce a scenario. Zero disables it.
    """
    if BEACON_OFFSET_NM <= 0:
        return lat, lon
    bearing = (int(hashlib.sha256(seed_text.encode()).hexdigest()[:8], 16) % 360)
    d = BEACON_OFFSET_NM / 60.0                       # NM -> degrees of latitude
    rad = math.radians(bearing)
    new_lat = lat + d * math.cos(rad)
    cos_lat = math.cos(math.radians(lat)) or 1e-6
    new_lon = lon + (d * math.sin(rad)) / cos_lat
    return round(new_lat, 6), round(new_lon, 6)


@app.route('/api/sar/export-vsar', methods=['POST'])
def sar_export_vsar():
    # SECURITY: the console URL is never taken from the request body. This is
    # an authenticated endpoint that writes into the CAP V-SAR
    # exercise console's state (creates a scenario, broadcasts a message);
    # accepting a caller-supplied target here was an open SSRF - any client
    # could redirect the server-side POST at an arbitrary URL. VSAR_CONSOLE_URL
    # is fixed at process start from an environment variable an operator sets,
    # not from anything a request can influence.
    security_error = _request_security_error(require_json=True)
    if security_error:
        return security_error
    if not _allow_vsar_export(request.remote_addr or 'unknown'):
        return jsonify({'success': False,
                        'error': 'V-SAR export rate limit exceeded; try again shortly'}), 429

    vsar_url = VSAR_CONSOLE_URL
    data = _body()
    try:
        pattern_type = _limited_text(data, 'pattern_type', 'Search Pattern', 40)
        callsign = _limited_text(data, 'callsign', 'CAP 487', 24)
        dep = _limited_text(data, 'departure', DEFAULT_AIRPORT, 8)
        dest = _limited_text(data, 'destination', DEFAULT_AIRPORT, 8)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    waypoints = data.get('waypoints', [])

    if not isinstance(waypoints, list) or not waypoints:
        return jsonify({'success': False, 'error': 'No waypoints to export'}), 400
    if len(waypoints) > 500:
        return jsonify({'success': False,
                        'error': 'waypoints must contain at most 500 points'}), 400

    try:
        datum = waypoints[0]
        float(datum['lat']); float(datum['lon'])
        centre = data.get('search_centre')
        if isinstance(centre, dict):
            datum_lat, datum_lon = float(centre['lat']), float(centre['lon'])
        else:
            c = pattern_search_centre(
                [{'identifier': w.get('identifier'), 'lat': float(w['lat']),
                  'lon': float(w['lon'])} for w in waypoints], (0.0, 0.0))
            datum_lat, datum_lon = c['lat'], c['lon']
        if not (-90 <= datum_lat <= 90 and -180 <= datum_lon <= 180):
            raise ValueError('search centre out of range')
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return jsonify({'success': False, 'error':
            'waypoints must have numeric lat/lon (and search_centre, if sent, too)'}), 400

    # L-9: the beacon does not sit on the planned datum, and it is not at sea
    # level. Both of those handed the exercise away - the first tells the crew
    # where to look, the second makes the propagation model meaningless.
    beacon_lat, beacon_lon = offset_beacon(
        datum_lat, datum_lon, f"{callsign}|{pattern_type}|{datum_lat}|{datum_lon}")
    beacon_elev = point_elevation_ft(beacon_lat, beacon_lon)
    elevation_known = beacon_elev is not None

    scenario_payload = {
        'name': f"CAP Sortie - {pattern_type.replace('_', ' ').title()} ({dep}->{dest})",
        'notes': f"Generated by CAP 487 Flight Planner for {callsign}. Total waypoints: {len(waypoints)}. Planned at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%MZ')}."
                 + ("" if elevation_known else
                    " Beacon elevation could not be resolved (USGS unreachable); the instructor should set it before flying."),
        'beacon_lat': beacon_lat,
        'beacon_lon': beacon_lon,
        'beacon_elev_ft': beacon_elev if elevation_known else 0.0,
        'band': '121.5',
        'power': 1.0,
        'alert_kind': 'Planned CAP Search Sortie',
        # The ALERT is the centre of the planned search area - what the crew is
        # briefed on and what it is drawn around (L2-6: not waypoints[0], which
        # is a box edge for a parallel track). Only the beacon moves.
        'alert_text': f"{callsign} search area: {len(waypoints)} waypoints. Centre: {datum_lat:.4f}, {datum_lon:.4f}.",
        'alert_lat': datum_lat,
        'alert_lon': datum_lon,
        'alert_radius_nm': 5.0
    }

    message_payload = {
        'sender': 'FLIGHT PLANNER',
        'recipient': 'ALL',
        'body': f"Filed {pattern_type} flight plan for {callsign}: {len(waypoints)} search waypoints around ({datum_lat:.4f}, {datum_lon:.4f})."
    }
    
    try:
        r_scen = requests.post(f"{vsar_url}/api/scenarios", json=scenario_payload,
                               timeout=5, headers=_console_headers(), allow_redirects=False)
        if r_scen.status_code in (401, 403):
            return jsonify({
                'success': False,
                'error': 'V-SAR console denied scenario creation for this caller'
            }), r_scen.status_code
        scen_ok = r_scen.status_code in (200, 201)
        r_msg = requests.post(f"{vsar_url}/api/messages", json=message_payload,
                              timeout=5, headers=_console_headers(), allow_redirects=False)
        if r_msg.status_code in (401, 403):
            return jsonify({
                'success': scen_ok,
                'scenario_created': scen_ok,
                'message_sent': False,
                'error': 'V-SAR console denied message broadcast for this caller'
            }), r_msg.status_code
        msg_ok = r_msg.status_code in (200, 201)

        # L-9: the console accepts /api/messages whether or not a sortie is
        # running - with one it persists the message into the record, without
        # one it only broadcasts to whoever is watching. The old code inferred
        # "ready in console" from a 400 the console stopped returning long ago,
        # so that branch was dead and every push claimed it had been
        # "broadcast to active sortie". Ask the console what is actually
        # running rather than guessing from a status code.
        sortie_running = None
        try:
            r_state = requests.get(f"{vsar_url}/api/state", timeout=4,
                                   headers=_console_headers(), allow_redirects=False)
            if r_state.status_code == 200:
                sortie = (r_state.json() or {}).get('sortie') or {}
                sortie_running = bool(sortie) and not sortie.get('stopped')
        except (requests.RequestException, ValueError):
            sortie_running = None       # unknown, and reported as unknown

        persisted = bool(msg_ok and sortie_running)
        if not scen_ok:
            status_desc = f"Failed to create scenario in V-SAR Console (HTTP {r_scen.status_code})"
        elif not msg_ok:
            status_desc = (f"Scenario created; the console rejected the broadcast "
                           f"(HTTP {r_msg.status_code})")
        elif sortie_running is True:
            status_desc = ("Scenario created and broadcast; a sortie is running, "
                           "so the message is in its record")
        elif sortie_running is False:
            status_desc = ("Scenario created and broadcast. No sortie is running, "
                           "so the message is NOT part of any exercise record - "
                           "start the sortie in the console")
        else:
            status_desc = ("Scenario created and broadcast; could not confirm "
                           "whether a sortie is running")

        return jsonify({
            'success': scen_ok,
            'vsar_url': vsar_url,
            'scenario_created': scen_ok,
            # Kept for older callers, but it only ever meant "the console
            # accepted it". broadcast/persisted are the honest pair.
            'message_sent': msg_ok,
            'message_broadcast': msg_ok,
            'message_persisted': persisted,
            'sortie_running': sortie_running,
            'beacon_offset_nm': BEACON_OFFSET_NM,
            'beacon_elevation_resolved': elevation_known,
            'message': status_desc
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f"Failed to connect to V-SAR console at {vsar_url}: {str(e)}"
        }), 502

def start_chart_precache():
    """Kick off the chart pre-cache, once per container (L-8).

    This only ever ran under `__main__`, so in Docker - the only way it
    actually runs - it never ran at all. The charts volume stayed empty, every
    /tiles/ request answered 204, and USER_GUIDE.md's promise that cached tiles
    are used first was simply untrue.

    gunicorn forks several workers and each imports this module, so the work is
    claimed with an exclusive lock file: whoever creates it downloads, the rest
    carry on serving. The lock lives in the charts volume and is removed when
    the download finishes.
    """
    if os.environ.get('CAPVSAR_PRECACHE_CHARTS', '1').strip().lower() in (
            '0', 'false', 'no', 'off'):
        log_msg('Chart pre-cache disabled by CAPVSAR_PRECACHE_CHARTS')
        return False
    if tiles_offline():
        log_msg('CAPVSAR_TILES_OFFLINE set - serving only what is already cached')
        return False
    try:
        os.makedirs(CHARTS_DIR, exist_ok=True)
        lock_path = os.path.join(CHARTS_DIR, '.precache.pid')
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False              # another worker already claimed it
    except OSError as e:
        log_msg(f'Chart pre-cache could not claim the lock: {e}')
        return False
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)

    def run():
        try:
            startup_chart_download()
        finally:
            try:
                os.unlink(lock_path)
            except OSError:
                pass

    threading.Thread(target=run, daemon=True).start()
    return True


# Under gunicorn there is no __main__, so this is where it has to happen.
# Importing this module must not start a download during tests, which import it
# directly - CAPVSAR_PRECACHE_CHARTS=0 is how the suites opt out.
start_chart_precache()


if __name__ == '__main__':
    print("=" * 60)
    print("CAP 487 Flight Planner - CAP San Diego Sr. Sq. 57")
    print("=" * 60)
    print(f"Charts directory: {os.path.abspath(CHARTS_DIR)}")
    
    # Already started at import time by start_chart_precache(); the lock file
    # makes this second call a no-op.
    start_chart_precache()
    
    print("Starting server at http://localhost:5000")
    print("Charts will download automatically on first run...")
    print("=" * 60)
    
    app.run(debug=False, host='0.0.0.0', port=5000)
