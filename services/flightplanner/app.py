from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from collections import deque
from datetime import datetime, timedelta, timezone
import fcntl
import hmac
import json
import math
import os
import csv
import sqlite3
import requests
from io import StringIO
import threading
import time
from urllib.parse import urlsplit

try:
    from pygeomag import GeoMag
    _geomag = GeoMag()
except Exception:
    _geomag = None  # headings fall back to true (mag_var = 0)

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'aviation_data.db')
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

MAX_PARALLEL_DIMENSION_NM = 50.0
MAX_PARALLEL_LEGS = 200
VSAR_EXPORT_RATE_LIMIT = 5
VSAR_EXPORT_RATE_WINDOW_S = 60.0
_vsar_export_attempts = {}
_vsar_export_rate_lock = threading.Lock()

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

AIRCRAFT_DATABASE = {
    'N499CP': {
        'name': 'N499CP - Cessna 172S NAV III',
        'empty_weight': 1642, 'empty_weight_moment': 62.6,
        'max_takeoff_weight': 2550, 'usable_fuel': 53,
        'fuel_weight_per_gallon': 6.0,
        # POH Section 6: forward CG limit slopes aft with weight; aft limit constant
        'cg_fwd_points': ((1950, 35.0), (2550, 41.0)),
        'cg_aft_limit': 47.3,
        'arms': {'front_seats': 37.0, 'rear_seats': 73.0, 'baggage1': 95.0},
        'baggage1_max': 120,
        'fuel_arm': 48.0, 'taxi_fuel': 1.4,
        
        'cruise_performance': {
            4000: {2500: {0: (69, 115, 9.5)}, 2400: {0: (61, 109, 8.5)}},
            6000: {2600: {0: (73, 119, 9.9)}, 2500: {0: (65, 114, 9.0)}, 2400: {0: (57, 108, 8.2)}},
            8000: {2600: {0: (68, 119, 9.4)}, 2500: {0: (61, 112, 8.6)}, 2400: {0: (54, 106, 7.8)}},
            10000: {2600: {0: (64, 117, 9.0)}, 2500: {0: (57, 111, 8.2)}},
        },
        
        'climb_performance': {
            0: (0, 0.0, 0), 2000: (3, 0.8, 4), 4000: (6, 1.5, 8),
            6000: (10, 2.2, 13), 8000: (14, 3.0, 19), 10000: (20, 3.9, 27),
        },
        
        'takeoff_distance_2550': {
            0: {15: (940, 1630), 30: (1070, 1810)},
            2000: {15: (1150, 1960), 30: (1285, 2190)},
            4000: {15: (1390, 2390), 30: (1550, 2685)},
            6000: {15: (1680, 2950), 30: (1875, 3320)},
        },
        
        'landing_distance': {
            0: {15: (575, 1335), 30: (605, 1380)},
            2000: {15: (620, 1405), 30: (650, 1455)},
            4000: {15: (665, 1480), 30: (700, 1535)},
            6000: {15: (720, 1560), 30: (755, 1620)},
        },
    }
}

DEFAULT_AIRCRAFT = 'N499CP'

os.makedirs(CHARTS_DIR, exist_ok=True)

def get_utc_now():
    return datetime.now(timezone.utc)

def init_database():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS airports (icao TEXT PRIMARY KEY, name TEXT, city TEXT, state TEXT, latitude REAL, longitude REAL, elevation INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS runways (id INTEGER PRIMARY KEY, airport_icao TEXT, runway_id TEXT, length INTEGER, surface TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS navaids (id TEXT PRIMARY KEY, name TEXT, type TEXT, latitude REAL, longitude REAL)')
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
                    'User-Agent': 'Mozilla/5.0 N499CP-FlightPlanner/1.0',
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
        }, timeout=6, headers={'User-Agent': 'N499CP-Planner/1.0'})
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
        _winds_cache[key] = result
        return result
    except Exception as e:
        log_msg(f'Winds aloft fetch failed ({e}); using estimate')
        return simulate_winds(lat, lon)

def fetch_metar(station):
    try:
        r = requests.get(f"{AVIATION_WEATHER_BASE}/metar?ids={station}&format=json", timeout=8,
                        headers={'User-Agent': 'N499CP-Planner/1.0'})
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
                        headers={'User-Agent': 'N499CP-Planner/1.0'})
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
        
    return points

def generate_creeping_line(start_lat, start_lon, end_lat, end_lon, sweep_width_nm=3.0, spacing_nm=1.0, max_legs=12):
    """Generate Civil Air Patrol Creeping Line (CS) search pattern waypoints."""
    adv_brg = bearing(start_lat, start_lon, end_lat, end_lon)
    tot_dist = gc_dist(start_lat, start_lon, end_lat, end_lon)
    num_sweeps = min(max_legs, max(2, int(tot_dist / spacing_nm)))
    
    left_brg = (adv_brg - 90) % 360
    right_brg = (adv_brg + 90) % 360
    half_w = sweep_width_nm / 2.0
    
    points = []
    cur_axis_lat, cur_axis_lon = start_lat, start_lon
    
    # Leg 1: Offset left
    p1_lat, p1_lon = destination_point(cur_axis_lat, cur_axis_lon, half_w, left_brg)
    points.append({'identifier': 'CS01', 'lat': p1_lat, 'lon': p1_lon, 'leg_dist_nm': round(half_w, 2), 'heading_true': round(left_brg, 1)})
    
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
            
    return points

def generate_parallel_track(corner_lat, corner_lon, length_nm=5.0, width_nm=4.0, axis_heading=0.0, spacing_nm=1.0):
    """Generate Civil Air Patrol Parallel Track (PS) search pattern waypoints."""
    cross_heading = (axis_heading + 90) % 360
    opp_heading = (axis_heading + 180) % 360
    num_sweeps = max(2, int(width_nm / spacing_nm))
    
    points = []
    cur_lat, cur_lon = corner_lat, corner_lon
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
            
    return points

def generate_xplane_fms_content(departure, destination, waypoints, cruise_alt=6500):
    """Generate X-Plane 11/12 standard .fms text file."""
    lines = [
        "I",
        "1100 Version",
        f"CYCLE {get_utc_now().strftime('%y%m')}",
        f"ADEP {departure.upper()}",
        f"ADES {destination.upper()}",
        f"NUMENR {len(waypoints) + 2}"
    ]
    
    dep_apt = get_airport(departure.upper())
    dep_lat = dep_apt['latitude'] if dep_apt else (waypoints[0]['lat'] if waypoints else 0.0)
    dep_lon = dep_apt['longitude'] if dep_apt else (waypoints[0]['lon'] if waypoints else 0.0)
    dep_elev = dep_apt.get('elevation', 0) if dep_apt else 0
    lines.append(f"1 {departure.upper()} ADEP {float(dep_elev):.1f} {dep_lat:.6f} {dep_lon:.6f}")
    
    for wpt in waypoints:
        lat = wpt.get('lat', 0.0)
        lon = wpt.get('lon', 0.0)
        ident = f"{lat:+.3f}_{lon:+.3f}"
        lines.append(f"28 {ident} DRCT {float(cruise_alt):.6f} {lat:.6f} {lon:.6f}")
        
    dest_apt = get_airport(destination.upper())
    dest_lat = dest_apt['latitude'] if dest_apt else (waypoints[-1]['lat'] if waypoints else 0.0)
    dest_lon = dest_apt['longitude'] if dest_apt else (waypoints[-1]['lon'] if waypoints else 0.0)
    dest_elev = dest_apt.get('elevation', 0) if dest_apt else 0
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
    if ws == 0: return 0, tas
    swc = (ws/tas)*math.sin(math.radians(wd-tc))
    swc = max(-1, min(1, swc))
    wca = math.degrees(math.asin(swc))
    # Winds-aloft direction is FROM: a headwind (wd == tc) must reduce GS
    gs = tas*math.cos(math.asin(swc)) - ws*math.cos(math.radians(wd-tc))
    return round(wca,1), max(round(gs,1), 0)

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

def get_cruise(alt, rpm):
    ac = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]
    cd = ac['cruise_performance']
    alts = sorted(cd.keys())
    a = min(alts, key=lambda x: abs(x-alt))
    if a not in cd: return {'true_airspeed': 110, 'fuel_flow_gph': 8.5}
    rpms = sorted(cd[a].keys())
    r = min(rpms, key=lambda x: abs(x-rpm))
    if r not in cd[a]: return {'true_airspeed': 110, 'fuel_flow_gph': 8.5}
    pwr, tas, gph = cd[a][r][0]
    return {'power_percent': pwr, 'true_airspeed': tas, 'fuel_flow_gph': gph}

def get_climb(fr, to):
    ac = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]
    cd = ac['climb_performance']
    alts = sorted(cd.keys())
    f = min(alts, key=lambda x: abs(x-fr))
    t = min(alts, key=lambda x: abs(x-to))
    fd, td = cd[f], cd[t]
    return {'time_minutes': max(0,td[0]-fd[0]), 'fuel_gallons': max(0,td[1]-fd[1]), 'distance_nm': max(0,td[2]-fd[2])}

def calc_takeoff(wt, alt, temp, hw=0):
    ac = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]
    tbl = ac['takeoff_distance_2550']
    alts = sorted(tbl.keys())
    a = min([x for x in alts if x >= alt], default=alts[-1])
    temps = sorted(tbl[a].keys())
    t = min([x for x in temps if x >= temp], default=temps[-1])
    gr, tot = tbl[a][t]
    wf = 1.0 - (hw/9*0.10) if hw > 0 else 1.0
    return {'ground_roll': int(gr*wf), 'total_over_50ft': int(tot*wf)}

def calc_landing(alt, temp, hw=0):
    ac = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]
    tbl = ac['landing_distance']
    alts = sorted(tbl.keys())
    a = min([x for x in alts if x >= alt], default=alts[-1])
    temps = sorted(tbl[a].keys())
    t = min([x for x in temps if x >= temp], default=temps[-1])
    gr, tot = tbl[a][t]
    wf = 1.0 - (hw/9*0.10) if hw > 0 else 1.0
    return {'ground_roll': int(gr*wf), 'total_over_50ft': int(tot*wf)}


def _same_origin_or_instructor_token():
    supplied = (request.headers.get('X-CAPVSAR-Token') or '').strip()
    expected = os.environ.get('CAPVSAR_TOKEN_INSTRUCTOR', '').strip()
    if expected and supplied and hmac.compare_digest(supplied, expected):
        return True
    origin = request.headers.get('Origin')
    return bool(origin and urlsplit(origin).netloc == urlsplit(request.host_url).netloc)


def _request_security_error(require_json=False):
    if require_json and not request.is_json:
        return jsonify({'success': False,
                        'error': 'This endpoint requires a JSON request body'}), 415
    if not _same_origin_or_instructor_token():
        return jsonify({'success': False,
                        'error': 'A same-origin request or valid instructor token is required'}), 403
    return None


def _limited_text(data, field, default, maximum):
    value = data.get(field, default)
    if not isinstance(value, str):
        raise ValueError(f'{field} must be text')
    value = value.strip()
    if len(value) > maximum:
        raise ValueError(f'{field} must be at most {maximum} characters')
    return value


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


def _console_headers(role):
    token = os.environ.get(f'CAPVSAR_TOKEN_{role.upper()}', '').strip()
    if role == 'base' and not token:
        token = os.environ.get('CAPVSAR_TOKEN_INSTRUCTOR', '').strip()
    return {'X-CAPVSAR-Token': token} if token else {}

# Flask Routes
@app.route('/')
def index():
    return render_template('index.html')

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
    return jsonify({
        'vfr': TILE_SOURCES['vfr'],
        'ifr_low': TILE_SOURCES['ifr_low'],
        'ifr_high': TILE_SOURCES['ifr_high'],
    })

# Serve cached tiles
@app.route('/tiles/<chart_type>/<int:z>/<int:x>/<int:y>.png')
def serve_tile(chart_type, z, x, y):
    tile_dir = os.path.join(CHARTS_DIR, chart_type, str(z), str(x))
    tile_file = f'{y}.png'
    full_path = os.path.join(tile_dir, tile_file)
    if os.path.exists(full_path):
        return send_from_directory(tile_dir, tile_file, mimetype='image/png')
    return '', 204

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
    d = request.json
    dep, dest = d.get('departure','').upper(), d.get('destination','').upper()
    wpts = [w.upper() for w in d.get('waypoints', []) if w.strip()]
    alt, rpm = int(d.get('cruise_altitude', 6500)), int(d.get('rpm', 2400))
    reserve_minutes = max(15, min(120, int(d.get('reserve_minutes', 45))))
    
    ac = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]
    pts = [dep] + wpts + [dest]
    
    coords = []
    user_n = 0
    for p in pts:
        c = get_coords(p)
        if not c: return jsonify({'success': False, 'error': f'Not found: {p}'})
        if c[2] == 'user':
            user_n += 1
            label = f'USR{user_n}'
        else:
            label = p
        coords.append({'identifier': label, 'lat': c[0], 'lon': c[1], 'type': c[2], 'data': c[3]})
    
    cruise = get_cruise(alt, rpm)
    mid = coords[len(coords)//2]
    winds = fetch_winds_aloft(mid['lat'], mid['lon'])
    
    wdir, wspd = 0, 0
    if winds and 'levels' in winds:
        lvls = sorted(winds['levels'].keys())
        nrst = min(lvls, key=lambda x: abs(x-alt))
        wdir = winds['levels'][nrst]['direction']
        wspd = winds['levels'][nrst]['speed']
    
    segs = []
    tot_dist, tot_time, tot_fuel = 0, 0, 0
    
    for i in range(len(coords)-1):
        fr, to = coords[i], coords[i+1]
        dist = gc_dist(fr['lat'], fr['lon'], to['lat'], to['lon'])
        tc = bearing(fr['lat'], fr['lon'], to['lat'], to['lon'])
        wca, gs = wind_corr(tc, cruise['true_airspeed'], wdir, wspd)
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
    
    dep_elev = coords[0]['data'].get('elevation', 0) if coords[0]['data'] else 0
    climb = get_climb(dep_elev, alt)
    taxi = ac['taxi_fuel']
    reserve = (reserve_minutes / 60.0) * cruise['fuel_flow_gph']
    
    return jsonify({
        'success': True, 'route_points': coords, 'segments': segs,
        'winds_aloft': {'altitude': alt, 'direction': wdir, 'speed': wspd,
                        'source': winds.get('station', 'estimated'),
                        'simulated': winds.get('simulated', True)},
        'cruise': {'altitude': alt, 'rpm': rpm, 'true_airspeed': cruise['true_airspeed'], 'fuel_flow_gph': cruise['fuel_flow_gph']},
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
    try:
        d = request.json
        dep, dest = d.get('departure','').upper(), d.get('destination','').upper()
        wpts = [w.upper() for w in d.get('waypoints', []) if w.strip()]
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
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/performance/takeoff', methods=['POST'])
def perf_to():
    d = request.json
    return jsonify(calc_takeoff(int(d.get('weight',2550)), int(d.get('pressure_altitude',0)),
                                int(d.get('temperature',15)), int(d.get('headwind',0))))

@app.route('/api/performance/landing', methods=['POST'])
def perf_land():
    d = request.json
    return jsonify(calc_landing(int(d.get('pressure_altitude',0)), int(d.get('temperature',15)), int(d.get('headwind',0))))

@app.route('/api/weight-balance', methods=['POST'])
def wb():
    d = request.json
    ac = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]
    arms = ac['arms']
    ew = float(d.get('empty_weight', ac['empty_weight']))
    em = float(d.get('empty_moment', ac['empty_weight_moment']))
    p, f, r, b, fu = float(d.get('pilot_weight',0)), float(d.get('front_passenger_weight',0)), float(d.get('rear_passenger_weight',0)), float(d.get('baggage_weight',0)), float(d.get('fuel_gallons',0))

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
    (w1, f1), (w2, f2) = ac['cg_fwd_points']
    if tw <= w1:   fwd_limit = f1
    elif tw >= w2: fwd_limit = f2
    else:          fwd_limit = f1 + (tw - w1) / (w2 - w1) * (f2 - f1)

    within_weight = tw <= ac['max_takeoff_weight']
    within_cg = fwd_limit <= cg <= ac['cg_aft_limit']

    return jsonify({
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

def get_dtpp_cycle():
    """Compute current FAA d-TPP cycle string (YYMM format)."""
    from datetime import date
    today = date.today()
    # Try current and recent cycle codes
    # Cycles are YYMM where MM is the month-ish (not exact, but close enough)
    return f'{today.year % 100:02d}{today.month:02d}'

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
        r = requests.get(url, timeout=60, headers={'User-Agent': 'N499CP-Planner/1.0'})
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

    d = request.json
    route_points = d.get('route_points', [])
    cruise_altitude = int(d.get('cruise_altitude', 6000))

    if len(route_points) < 2:
        return jsonify({'success': False, 'error': 'Need at least 2 route points'})

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
        except:
            pass
        return idx, 0

    # Fetch all elevations with 10 parallel workers
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(fetch_elevation, i, s) for i, s in enumerate(samples)]
        results = {}
        for f in as_completed(futures):
            idx, elev = f.result()
            results[idx] = elev

    max_elevation = 0
    for i, sample in enumerate(samples):
        sample['elevation_ft'] = round(results.get(i, 0))
        max_elevation = max(max_elevation, sample['elevation_ft'])

    # Compute flight path with climb and descent profiles
    ac = AIRCRAFT_DATABASE[DEFAULT_AIRCRAFT]
    dep_elev = samples[0]['elevation_ft']
    dest_elev = samples[-1]['elevation_ft']
    rpm = int(d.get('rpm', 2400))
    cruise = get_cruise(cruise_altitude, rpm)
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
        if dist > 0.5 and dist < cumulative_dist - 0.5:
            min_clearance = min(min_clearance, clearance)

    if min_clearance == float('inf'):
        min_clearance = cruise_altitude - max_elevation

    return jsonify({
        'success': True,
        'profile': samples,
        'cruise_altitude': cruise_altitude,
        'max_terrain': round(max_elevation),
        'min_clearance': round(min_clearance),
        'vfr_clearance_ok': min_clearance >= 1000,
        'ifr_mea_margin': min_clearance >= 2000,
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

@app.route('/api/sar/generate-pattern', methods=['POST'])
def sar_generate():
    data = request.json or {}
    ptype = data.get('pattern_type', 'expanding_square')
    
    # Resolve datum
    datum_input = data.get('datum', '').strip()
    datum_coords = None
    if datum_input:
        c = get_coords(datum_input)
        if c:
            datum_coords = (c[0], c[1])
    if not datum_coords:
        try:
            datum_coords = (float(data.get('datum_lat', 33.17)), float(data.get('datum_lon', -117.0792)))
        except (ValueError, TypeError):
            datum_coords = (33.17, -117.0792)
            
    # The UI's <input min/max> only constrains the form; this is a public POST
    # endpoint anyone can call directly, so the same bounds are enforced here.
    # spacing_nm floors above zero (both creeping_line and parallel_track
    # divide by it - 0 was an unhandled ZeroDivisionError) and num_legs caps
    # to keep one request from generating an unbounded waypoint list.
    try:
        spacing = max(0.1, min(20.0, float(data.get('spacing_nm', 1.0))))
        legs = max(1, min(40, int(data.get('num_legs', 8))))
        init_hdg = float(data.get('initial_heading', 0.0)) % 360.0
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'spacing_nm, num_legs and initial_heading must be numbers'}), 400
    turn_dir = data.get('turn_direction', 'right')

    try:
        if ptype == 'expanding_square':
            wpts = generate_expanding_square(datum_coords[0], datum_coords[1], spacing, legs, init_hdg, turn_dir)
        elif ptype == 'creeping_line':
            end_lat = float(data.get('end_lat', datum_coords[0] + 0.15))
            end_lon = float(data.get('end_lon', datum_coords[1] + 0.15))
            sweep_w = max(0.1, min(50.0, float(data.get('sweep_width_nm', 3.0))))
            wpts = generate_creeping_line(datum_coords[0], datum_coords[1], end_lat, end_lon, sweep_w, spacing, legs)
        elif ptype == 'parallel_track':
            box_len = max(0.1, float(data.get('length_nm', 5.0)))
            if box_len > MAX_PARALLEL_DIMENSION_NM:
                return jsonify({'success': False, 'error':
                    f'length_nm must be at most {MAX_PARALLEL_DIMENSION_NM:g}'}), 400
            box_w = max(0.1, float(data.get('width_nm', 4.0)))
            if box_w > MAX_PARALLEL_DIMENSION_NM:
                return jsonify({'success': False, 'error':
                    f'width_nm must be at most {MAX_PARALLEL_DIMENSION_NM:g}'}), 400
            sweeps = max(2, int(box_w / spacing))
            leg_count = 2 * sweeps - 1
            if leg_count > MAX_PARALLEL_LEGS:
                return jsonify({'success': False, 'error':
                    f'width_nm with spacing_nm would generate {sweeps} sweeps '
                    f'({leg_count} legs); maximum is {MAX_PARALLEL_LEGS} legs'}), 400
            axis_hdg = float(data.get('axis_heading', 0.0)) % 360.0
            wpts = generate_parallel_track(datum_coords[0], datum_coords[1], box_len, box_w, axis_hdg, spacing)
        else:
            return jsonify({'success': False, 'error': f'Unknown pattern: {ptype}'}), 400
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'One or more pattern parameters were not valid numbers'}), 400

    tot_dist = 0.0
    for i in range(len(wpts) - 1):
        tot_dist += gc_dist(wpts[i]['lat'], wpts[i]['lon'], wpts[i+1]['lat'], wpts[i+1]['lon'])
        
    cruise = get_cruise(6500, 2400)
    tas = cruise['true_airspeed']
    est_time_min = (tot_dist / tas) * 60.0 if tas > 0 else 0
    est_fuel_gal = (est_time_min / 60.0) * cruise['fuel_flow_gph']
    
    route_fragment = " ".join(f"@{p['lat']:.5f},{p['lon']:.5f}" for p in wpts)
    
    return jsonify({
        'success': True,
        'pattern_type': ptype,
        'datum': {'lat': datum_coords[0], 'lon': datum_coords[1]},
        'waypoints': wpts,
        'total_distance_nm': round(tot_dist, 1),
        'estimated_time_minutes': round(est_time_min, 0),
        'estimated_fuel_gallons': round(est_fuel_gal, 1),
        'route_fragment': route_fragment
    })

@app.route('/api/sar/export-fms', methods=['POST'])
def sar_export_fms():
    data = request.json or {}
    dep = data.get('departure', 'KSEE')
    dest = data.get('destination', 'KSEE')
    wpts = data.get('waypoints', [])
    alt = int(data.get('altitude', 6500))
    fms_text = generate_xplane_fms_content(dep, dest, wpts, alt)
    
    return jsonify({
        'success': True,
        'filename': f"{dep}_{dest}_SAR.fms",
        'content': fms_text
    })

@app.route('/api/sar/export-vsar', methods=['POST'])
def sar_export_vsar():
    # SECURITY: the console URL is never taken from the request body. This is
    # an unauthenticated public endpoint that writes into the CAP V-SAR
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
    data = request.json or {}
    try:
        pattern_type = _limited_text(data, 'pattern_type', 'Search Pattern', 40)
        callsign = _limited_text(data, 'callsign', 'CAP499', 24)
        dep = _limited_text(data, 'departure', 'KSEE', 8)
        dest = _limited_text(data, 'destination', 'KSEE', 8)
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
        datum_lat = float(datum['lat'])
        datum_lon = float(datum['lon'])
    except (KeyError, TypeError, ValueError, IndexError):
        return jsonify({'success': False, 'error': 'waypoints[0] must have numeric lat/lon'}), 400

    scenario_payload = {
        'name': f"CAP Sortie - {pattern_type.replace('_', ' ').title()} ({dep}->{dest})",
        'notes': f"Generated by N499CP Flight Planner for {callsign}. Total waypoints: {len(waypoints)}. Planned at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%MZ')}.",
        'beacon_lat': datum_lat,
        'beacon_lon': datum_lon,
        'beacon_elev_ft': 0.0,
        'band': '121.5',
        'power': 1.0,
        'alert_kind': 'Planned CAP Search Sortie',
        'alert_text': f"{callsign} search corridor: {len(waypoints)} waypoints. Initial point: {datum_lat}, {datum_lon}.",
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
                               timeout=5, headers=_console_headers('instructor'))
        if r_scen.status_code == 403:
            return jsonify({
                'success': False,
                'error': ('V-SAR console refused the instructor token. Set the same '
                          'CAPVSAR_TOKEN_INSTRUCTOR value on the planner and console.')
            }), 502
        scen_ok = r_scen.status_code in (200, 201)
        r_msg = requests.post(f"{vsar_url}/api/messages", json=message_payload,
                              timeout=5, headers=_console_headers('base'))
        if r_msg.status_code == 403:
            return jsonify({
                'success': scen_ok,
                'scenario_created': scen_ok,
                'message_sent': False,
                'error': ('V-SAR console refused the base token. Set matching '
                          'CAPVSAR_TOKEN_BASE values, or provide the instructor token '
                          'to the planner as the base-role fallback.')
            }), 502
        msg_ok = r_msg.status_code in (200, 201)

        if scen_ok and msg_ok:
            status_desc = f"Pushed to V-SAR Console (scenario created & broadcast to active sortie)"
        elif scen_ok:
            if r_msg.status_code == 400 and 'no sortie running' in r_msg.text:
                status_desc = f"Pushed to V-SAR Console (scenario created; ready in console)"
            else:
                status_desc = f"Pushed to V-SAR Console (scenario created; message status {r_msg.status_code})"
        else:
            status_desc = f"Failed to create scenario in V-SAR Console (HTTP {r_scen.status_code})"

        return jsonify({
            'success': scen_ok,
            'vsar_url': vsar_url,
            'scenario_created': scen_ok,
            'message_sent': msg_ok,
            'message': status_desc
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f"Failed to connect to V-SAR console at {vsar_url}: {str(e)}"
        }), 502

if __name__ == '__main__':
    print("=" * 60)
    print("N499CP Flight Planner - CAP San Diego Sr. Sq. 57")
    print("=" * 60)
    print(f"Charts directory: {os.path.abspath(CHARTS_DIR)}")
    
    # Start chart download in background
    threading.Thread(target=startup_chart_download, daemon=True).start()
    
    print("Starting server at http://localhost:5000")
    print("Charts will download automatically on first run...")
    print("=" * 60)
    
    app.run(debug=False, host='0.0.0.0', port=5000)
