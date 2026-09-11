#!/usr/bin/env python3
"""
The planner has to work at a mission base with no internet (L-8).

Before this, Leaflet and the fonts came from CDNs and every map tile was
requested straight from ArcGIS by the browser, so at a base with no route out
the map did not render at all. The server-side tile cache that existed to
prevent exactly that only ran under `__main__` - never under gunicorn, which is
the only way it actually runs - and nothing asked it for a tile anyway, because
/api/tile-sources handed the frontend the ArcGIS URLs directly.

These tests pin the three things that made it fail and would make it fail
again: no CDN in the markup, tiles addressed locally, and no outbound request
when the station is offline.

    pytest services/flightplanner/tests/test_offline_map.py
"""
import os
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
PLANNER = os.path.dirname(HERE)
sys.path.insert(0, PLANNER)

# Importing app.py starts the chart pre-cache; a test run must not download the
# south-west United States.
os.environ.setdefault('CAPVSAR_PRECACHE_CHARTS', '0')
import app as flight_app                                      # noqa: E402

STATIC = os.path.join(PLANNER, 'static')
TEMPLATES = os.path.join(PLANNER, 'templates')
CDN_MARKERS = ('unpkg.com', 'cdn.jsdelivr', 'cdnjs.cloudflare',
               'fonts.googleapis.com', 'fonts.gstatic.com',
               'tiles.arcgis.com', 'server.arcgisonline.com',
               'tile.openstreetmap.org')


def _client():
    flight_app.app.config['TESTING'] = True
    return flight_app.app.test_client()


class NoInternetInTheMarkup(unittest.TestCase):
    """Every asset the browser needs comes from this host."""

    def _rendered(self, name):
        with open(os.path.join(TEMPLATES, name), encoding='utf-8') as fh:
            html = fh.read()
        # Strip comments: the templates cite the CDN URLs they were vendored
        # from, which is documentation, not a load.
        while '<!--' in html and '-->' in html:
            a = html.index('<!--')
            html = html[:a] + html[html.index('-->', a) + 3:]
        return html

    def test_no_cdn_in_templates(self):
        for name in ('index.html', 'guide.html'):
            html = self._rendered(name)
            for marker in CDN_MARKERS:
                self.assertNotIn(marker, html,
                                 f'{name} still loads {marker}')

    def test_leaflet_is_vendored(self):
        for rel in ('vendor/leaflet/leaflet.js', 'vendor/leaflet/leaflet.css',
                    'vendor/leaflet/images/marker-icon.png'):
            self.assertTrue(os.path.exists(os.path.join(STATIC, rel)), rel)

    def test_fonts_are_vendored_and_self_referential(self):
        css_path = os.path.join(STATIC, 'vendor', 'fonts', 'fonts.css')
        self.assertTrue(os.path.exists(css_path))
        with open(css_path, encoding='utf-8') as fh:
            css = fh.read()
        self.assertNotIn('https://', css.split('*/', 1)[-1],
                         'fonts.css still points at a remote host')
        for family in ('Orbitron', 'IBM Plex Sans', 'JetBrains Mono'):
            self.assertIn(family, css)
        # Every file the CSS names must actually be on disk.
        import re
        for ref in re.findall(r"url\(([^)]+)\)", css):
            name = ref.rsplit('/', 1)[-1]
            self.assertTrue(
                os.path.exists(os.path.join(STATIC, 'vendor', 'fonts', name)),
                f'fonts.css references missing file {name}')


class TilesGoThroughTheCache(unittest.TestCase):
    def test_tile_sources_are_local(self):
        body = _client().get('/api/tile-sources').get_json()
        for key in ('vfr', 'ifr_low', 'ifr_high'):
            self.assertTrue(body[key].startswith('/tiles/'),
                            f'{key} is {body[key]!r}, not a local URL')
            for marker in CDN_MARKERS:
                self.assertNotIn(marker, body[key])

    def test_unknown_chart_type_is_rejected(self):
        # chart_type builds a path that is now written to as well as read, so
        # it never reaches the filesystem unvalidated.
        for bad in ('elevation', 'vfr2', 'VFR'):
            self.assertEqual(_client().get(f'/tiles/{bad}/8/1/1.png').status_code,
                             404, bad)

    def test_traversal_cannot_escape_the_cache(self):
        c = _client()
        for bad in ('/tiles/..%2f..%2fetc/8/1/1.png', '/tiles/../8/1/1.png'):
            self.assertIn(c.get(bad).status_code, (404, 308, 400))

    def test_cached_tile_is_served_without_touching_the_network(self):
        z, x, y = 9, 88, 204
        tile_dir = os.path.join(flight_app.CHARTS_DIR, 'vfr', str(z), str(x))
        os.makedirs(tile_dir, exist_ok=True)
        path = os.path.join(tile_dir, f'{y}.png')
        payload = b'\x89PNG\r\n\x1a\n' + b'cap-vsar-test' * 16
        with open(path, 'wb') as fh:
            fh.write(payload)
        try:
            with patch.object(flight_app.requests, 'get',
                              side_effect=AssertionError('went to the network')):
                r = _client().get(f'/tiles/vfr/{z}/{x}/{y}.png')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data, payload)
        finally:
            os.remove(path)

    def test_offline_station_never_reaches_for_the_network(self):
        with patch.dict(os.environ, {'CAPVSAR_TILES_OFFLINE': '1'}):
            with patch.object(flight_app.requests, 'get',
                              side_effect=AssertionError('went to the network')):
                r = _client().get('/tiles/vfr/9/1/1.png')
        # No tile, no network, no error: Leaflet leaves its blank tile up.
        self.assertEqual(r.status_code, 204)

    def test_a_miss_is_fetched_once_and_kept(self):
        z, x, y = 7, 21, 49
        path = os.path.join(flight_app.CHARTS_DIR, 'vfr', str(z), str(x), f'{y}.png')
        body = b'\x89PNG\r\n\x1a\n' + b'downloaded' * 20

        class Resp:
            status_code = 200
            content = body

        flight_app._tile_upstream['blocked_until'] = 0.0
        try:
            with patch.object(flight_app.requests, 'get', return_value=Resp()) as g:
                r = _client().get(f'/tiles/vfr/{z}/{x}/{y}.png')
                self.assertEqual(r.status_code, 200)
                self.assertEqual(g.call_count, 1)
                # ...and the next request is served from disk.
                r2 = _client().get(f'/tiles/vfr/{z}/{x}/{y}.png')
                self.assertEqual(g.call_count, 1, 'refetched a tile it had cached')
            self.assertEqual(r2.data, body)
            self.assertTrue(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_upstream_failure_backs_off_instead_of_stalling_every_tile(self):
        flight_app._tile_upstream['blocked_until'] = 0.0
        try:
            with patch.object(flight_app.requests, 'get',
                              side_effect=OSError('no route to host')) as g:
                first = _client().get('/tiles/vfr/6/3/5.png')
                for _ in range(5):
                    _client().get('/tiles/vfr/6/3/6.png')
            self.assertEqual(first.status_code, 204)
            self.assertEqual(g.call_count, 1,
                             'each tile paid its own network timeout')
        finally:
            flight_app._tile_upstream['blocked_until'] = 0.0


class PrecacheRunsUnderGunicorn(unittest.TestCase):
    def test_precache_is_not_gated_on_dunder_main(self):
        with open(os.path.join(PLANNER, 'app.py'), encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn('start_chart_precache()', src)
        # The import-time call must come before the __main__ block, or Docker
        # never runs it - which was the whole bug.
        self.assertLess(src.index('\nstart_chart_precache()'),
                        src.index("if __name__ == '__main__':"))

    def test_precache_can_be_switched_off(self):
        with patch.dict(os.environ, {'CAPVSAR_PRECACHE_CHARTS': '0'}):
            self.assertFalse(flight_app.start_chart_precache())
        with patch.dict(os.environ, {'CAPVSAR_PRECACHE_CHARTS': '1',
                                     'CAPVSAR_TILES_OFFLINE': '1'}):
            self.assertFalse(flight_app.start_chart_precache())

    def test_only_one_worker_claims_the_download(self):
        lock = os.path.join(flight_app.CHARTS_DIR, '.precache.pid')
        os.makedirs(flight_app.CHARTS_DIR, exist_ok=True)
        with open(lock, 'w') as fh:
            fh.write('999999')
        try:
            with patch.dict(os.environ, {'CAPVSAR_PRECACHE_CHARTS': '1'}):
                with patch.object(flight_app, 'startup_chart_download',
                                  side_effect=AssertionError('second worker downloaded')):
                    self.assertFalse(flight_app.start_chart_precache())
        finally:
            os.remove(lock)


if __name__ == '__main__':
    unittest.main(verbosity=2)
