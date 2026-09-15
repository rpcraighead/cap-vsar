"""L-10: dependency pins, container identity, health truthfulness, cache bounds."""
from pathlib import Path
import os
import re
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
PLANNER = HERE.parent
ROOT = PLANNER.parents[1]
sys.path.insert(0, str(PLANNER))
os.environ.setdefault("CAPVSAR_PRECACHE_CHARTS", "0")

import app as flight_app  # noqa: E402


# -- dependency pins --------------------------------------------------------

def _requirements():
    text = (PLANNER / "requirements.txt").read_text()
    return dict(
        line.split("==", 1) for line in text.splitlines()
        if line.strip() and not line.startswith("#") and "==" in line
    )


def test_every_runtime_dependency_is_pinned():
    """An unpinned dep means the image rebuilds to whatever shipped that day."""
    text = (PLANNER / "requirements.txt").read_text()
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            assert "==" in line, f"unpinned requirement: {line}"


def test_requests_is_past_both_known_cves():
    """2.31.0 carried CVE-2024-35195 and CVE-2024-47081; 2.32.4 fixes both."""
    major, minor, patch = (int(p) for p in _requirements()["requests"].split("."))
    assert (major, minor, patch) >= (2, 32, 4), "requests predates the CVE fixes"


def test_gunicorn_is_pinned_here_not_installed_loose_in_the_dockerfile():
    """It used to be `pip install -r requirements.txt gunicorn` - unversioned."""
    assert "gunicorn" in _requirements()
    dockerfile = (PLANNER / "Dockerfile").read_text()
    assert not re.search(r"pip install[^\n]*\bgunicorn\b", dockerfile)


def test_werkzeug_stays_compatible_with_the_pinned_flask():
    """Flask 3.0.x does not support Werkzeug 3.1 - bump them together."""
    req = _requirements()
    if req["Flask"].startswith("3.0."):
        assert req["Werkzeug"].startswith("3.0."), "Flask 3.0 needs Werkzeug 3.0.x"


# -- container identity -----------------------------------------------------

def test_container_does_not_run_as_root():
    dockerfile = (PLANNER / "Dockerfile").read_text()
    assert re.search(r"^USER\s+planner\s*$", dockerfile, re.M), "no USER directive"
    # The UID must be settable, because /app/data is a bind mount whose owner
    # is decided by the host, not the image.
    assert "ARG APP_UID" in dockerfile


def test_compose_healthcheck_verifies_the_database_not_the_index_page():
    compose = (ROOT / "docker-compose.yml").read_text()
    planner = compose.split("flightplanner:", 1)[1].split("\n  board:", 1)[0]
    assert "/api/health" in planner
    assert "urlopen('http://127.0.0.1:8080/')" not in planner


# -- health endpoint --------------------------------------------------------

def _client():
    return flight_app.app.test_client()


def test_health_fails_closed_when_the_database_is_missing(tmp_path, monkeypatch):
    """The whole point: a planner with no database must not report healthy."""
    monkeypatch.setattr(flight_app, "DATABASE_PATH", str(tmp_path / "gone.db"))
    response = _client().get("/api/health")
    assert response.status_code == 503
    assert response.get_json()["status"] == "unhealthy"


def test_health_reports_ok_and_the_data_cycle_when_the_database_is_present(tmp_path, monkeypatch):
    db = tmp_path / "aviation.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE airports (icao TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE data_source (key TEXT PRIMARY KEY, source TEXT, fetched_at TEXT, rows INTEGER)")
    conn.execute("INSERT INTO airports VALUES ('KSEE')")
    conn.execute("INSERT INTO data_source VALUES ('airports','https://example.invalid/a.csv','2026-09-15T00:00:00+00:00',1)")
    conn.commit(); conn.close()

    monkeypatch.setattr(flight_app, "DATABASE_PATH", str(db))
    body = _client().get("/api/health").get_json()
    assert body["status"] == "ok"
    assert body["populated"] is True
    assert body["data_source"][0]["source"].endswith("a.csv")
    assert body["data_source"][0]["fetched_at"] == "2026-09-15T00:00:00+00:00"


def test_an_empty_database_is_healthy_but_reports_unpopulated(tmp_path, monkeypatch):
    """A fresh container starts before the first download; that is not a fault."""
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE airports (icao TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE data_source (key TEXT PRIMARY KEY, source TEXT, fetched_at TEXT, rows INTEGER)")
    conn.commit(); conn.close()

    monkeypatch.setattr(flight_app, "DATABASE_PATH", str(db))
    response = _client().get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["populated"] is False


def test_health_does_not_write_to_the_database(tmp_path, monkeypatch):
    """It opens read-only, so a health probe can never create or migrate a DB."""
    db = tmp_path / "ro.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE airports (icao TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE data_source (key TEXT, source TEXT, fetched_at TEXT, rows INTEGER)")
    conn.commit(); conn.close()
    before = db.stat().st_mtime_ns

    monkeypatch.setattr(flight_app, "DATABASE_PATH", str(db))
    _client().get("/api/health")
    assert db.stat().st_mtime_ns == before


# -- bounded caches ---------------------------------------------------------

def test_winds_cache_stops_growing():
    """The key carries an hour stamp, so every hour minted a new generation."""
    flight_app._winds_cache.clear()
    try:
        for i in range(flight_app._WINDS_CACHE_MAX * 2):
            flight_app._winds_cache_put((i, i, f"{i:010d}"), {"levels": []})
        assert len(flight_app._winds_cache) <= flight_app._WINDS_CACHE_MAX
    finally:
        flight_app._winds_cache.clear()


def test_winds_cache_keeps_the_most_recent_entry():
    flight_app._winds_cache.clear()
    try:
        for i in range(flight_app._WINDS_CACHE_MAX * 2):
            flight_app._winds_cache_put((i, i, f"{i:010d}"), {"seq": i})
        newest = (flight_app._WINDS_CACHE_MAX * 2 - 1,) * 2 + (f"{flight_app._WINDS_CACHE_MAX * 2 - 1:010d}",)
        assert flight_app._winds_cache[newest]["seq"] == flight_app._WINDS_CACHE_MAX * 2 - 1
    finally:
        flight_app._winds_cache.clear()


# -- tile route -------------------------------------------------------------

def test_unknown_chart_type_is_refused_without_touching_the_filesystem():
    for hostile in ("../../etc", "..", "vfr/../../etc", "VFR"):
        assert _client().get(f"/tiles/{hostile}/1/2/3.png").status_code in (404, 308)
