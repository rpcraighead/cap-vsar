"""O-8: planner routes and assets remain valid behind Caddy at /planner/."""
from pathlib import Path
import os
import re
import sys


HERE = Path(__file__).resolve().parent
PLANNER = HERE.parent
ROOT = PLANNER.parents[1]
sys.path.insert(0, str(PLANNER))
os.environ.setdefault("CAPVSAR_PRECACHE_CHARTS", "0")

import app as flight_app  # noqa: E402


def _prefixed_get(path):
    return flight_app.app.test_client().get(path, headers={
        "X-Forwarded-For": "10.0.0.10",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "ms01.local",
        "X-Forwarded-Prefix": "/planner",
    })


def test_index_generates_assets_and_links_under_planner_prefix():
    response = _prefixed_get("/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'data-planner-base="/planner"' in page
    assert 'href="/planner/static/' in page
    assert 'src="/planner/static/' in page
    assert 'href="/planner/guide"' in page


def test_tile_urls_stay_under_planner_prefix():
    response = _prefixed_get("/api/tile-sources")
    assert response.status_code == 200
    sources = response.get_json()
    for chart_type in ("vfr", "ifr_low", "ifr_high"):
        assert sources[chart_type].startswith(f"/planner/tiles/{chart_type}/")


def test_frontend_has_no_root_relative_fetch_bypassing_planner_mount():
    source = (PLANNER / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert re.search(r"fetch\(\s*[`'\"]\/", source) is None
    assert source.count("fetch(plannerUrl(") >= 16


def test_compose_does_not_publish_backend_ports():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"8700:8700"' not in compose
    assert '"8090:8080"' not in compose
    assert '"80:80"' in compose
    assert '"443:443"' in compose


def test_caddy_routes_both_apps_on_one_origin():
    caddy = (ROOT / "services" / "exercise" / "Caddyfile").read_text(encoding="utf-8")
    assert "handle_path /planner/*" in caddy
    assert "reverse_proxy flightplanner:8080" in caddy
    assert "header_up X-Forwarded-Prefix /planner" in caddy
    assert "reverse_proxy exercise:8700" in caddy
    assert "http://ms01" in caddy
    assert "handle /radio-ca.crt" in caddy
    assert "redir https://{host}{uri} 308" in caddy
