"""Isolated airborne training deck: python -m services.ai_pilot.maneuver_server."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import threading

from .maneuvers import Limits, ManeuverGate, XPlaneAutopilotBackend, parse_maneuver
from .xplane_udp import XPlaneUDPClient
from .control_ownership import ControllerLock, require_legacy_route_qualification


class Handler(BaseHTTPRequestHandler):
    def reply(self, data, status=200):
        raw = json.dumps(data, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/api/status':
            return self.reply(self.server.gate.status())
        if self.path != '/':
            return self.reply({'error': 'Not found'}, 404)
        raw = Path(__file__).with_name('static').joinpath('maneuvers.html').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        try:
            # Loopback-only service; reject cross-origin browser writes and form submissions.
            if self.headers.get('Content-Type') != 'application/json':
                raise ValueError('Expected application/json')
            if self.headers.get('Origin') not in (None, f'http://{self.headers.get("Host")}'):
                raise ValueError('Cross-origin request refused')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError('Invalid body length')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Expected JSON object')
            gate = self.server.gate
            if self.path == '/api/acquire':
                result = gate.acquire()
            elif self.path == '/api/takeover':
                result = gate.takeover()
            elif self.path == '/api/maneuver':
                if set(body) - {'lease', 'sequence', 'text', 'maneuver'} or ('text' in body) == ('maneuver' in body):
                    raise ValueError('Supply exactly one text or maneuver request')
                fields = parse_maneuver(body['text']) if 'text' in body else body['maneuver']
                result = gate.submit(body.get('lease'), body.get('sequence'), fields)
            else:
                return self.reply({'error': 'Not found'}, 404)
            self.reply(result)
        except (ValueError, TypeError) as error:
            self.reply({'error': str(error)}, 400)


def main():
    parser = argparse.ArgumentParser(description='CAP 487 airborne maneuver deck')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--xp-host', default='127.0.0.1')
    parser.add_argument('--xp-port', type=int, default=49000)
    parser.add_argument('--port', type=int, default=8089)
    parser.add_argument('--min-altitude', type=float, default=3000)
    parser.add_argument('--max-altitude', type=float, default=6000)
    args = parser.parse_args()
    if args.live:
        require_legacy_route_qualification()
    logging.basicConfig(level=logging.INFO)
    # Prevent duplicate instances of this controller. Legacy clients must remain stopped.
    with ControllerLock():
        limits = Limits(min_altitude_ft=args.min_altitude, max_altitude_ft=args.max_altitude)
        client = XPlaneUDPClient(host=args.xp_host, port=args.xp_port, mock=not args.live)
        backend = XPlaneAutopilotBackend(client)
        gate = ManeuverGate(backend, limits)
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
        server.gate = gate
        stop = threading.Event()

        def monitor():
            while not stop.wait(.1):
                try:
                    if not args.live:
                        # Static observations, intentionally no fake maneuver completion.
                        for key, value in dict(heading_mag=274, altitude_indicated_ft=4500,
                                               agl_ft=2000 / 3.28084, kias=110,
                                               roll_deg=0, vvi_fpm=0).items():
                            client.set_mock_dref(backend.DATAREFS[key], value)
                        client.set_mock_dref('sim/cockpit/autopilot/autopilot_state', 0)
                    gate.tick()
                except Exception:
                    logging.exception('Maneuver monitor failed')
                    with gate.lock:
                        gate.lease = None
                        gate.active = None
                    client.set_paused(True)
                    return

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        logging.info('Airborne deck http://127.0.0.1:%s (%s)', args.port,
                     'LIVE: position aircraft manually first' if args.live else 'MOCK: static telemetry')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            thread.join()
            if gate.lease:
                backend.pause()
            server.server_close()
            client.stop()


if __name__ == '__main__':
    main()
