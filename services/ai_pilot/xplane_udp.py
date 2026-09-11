"""
X-Plane 12 UDP Client
---------------------
High-performance asynchronous UDP protocol client for X-Plane 12.
Supports dataref reading/writing, commands, subscriptions, aircraft positioning,
and offline mock mode.
"""

from __future__ import annotations

import logging
import socket
import struct
import threading
import time
from typing import Callable, Dict, Optional, Tuple

logger = logging.getLogger("ai_pilot.xplane_udp")


class XPlaneUDPClient:
    """Client for X-Plane 12 native UDP communications (Port 49000)."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 49000,
        receive_port: int = 49005,
        timeout: float = 1.0,
        mock: bool = False,
    ):
        self.host = host
        self.port = port
        self.receive_port = receive_port
        self.timeout = timeout
        self.mock = mock

        self._sock: Optional[socket.socket] = None
        self._running = False
        self._listener_thread: Optional[threading.Thread] = None

        # Dataref subscription bookkeeping
        self._next_sub_id = 1
        self._dref_to_id: Dict[str, int] = {}
        self._id_to_dref: Dict[int, str] = {}
        self._cache: Dict[str, float] = {}
        self._callbacks: Dict[str, list[Callable[[str, float], None]]] = {}
        self._lock = threading.Lock()

        if not self.mock:
            self._init_socket()
            self.start()

    def _init_socket(self) -> None:
        """Create and bind UDP socket for X-Plane communications."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.settimeout(self.timeout)
        try:
            self._sock.bind(("0.0.0.0", self.receive_port))
            logger.info("Bound UDP receive socket to port %d", self.receive_port)
        except OSError as e:
            logger.warning("Could not bind port %d (%s), using dynamic port", self.receive_port, e)
            self._sock.bind(("0.0.0.0", 0))
            self.receive_port = self._sock.getsockname()[1]
            logger.info("Bound UDP receive socket to dynamic port %d", self.receive_port)

    def start(self) -> None:
        """Start receiver thread."""
        if self.mock or self._running:
            return
        self._running = True
        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True, name="XP-UDP-Listener")
        self._listener_thread.start()
        logger.info("X-Plane UDP receiver thread started")

    def stop(self) -> None:
        """Stop receiver thread and close socket."""
        self._running = False
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=1.0)
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        logger.info("X-Plane UDP client closed")

    def __enter__(self) -> XPlaneUDPClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    # --------------------------------------------------------------------------
    # Low-level packet builders & parsers
    # --------------------------------------------------------------------------

    @staticmethod
    def pack_dref(dataref: str, value: float) -> bytes:
        """Pack DREF message: b'DREF\x00' + float32 + 500-byte null-padded path (509 bytes total)."""
        dref_bytes = dataref.encode("utf-8")
        if len(dref_bytes) > 500:
            raise ValueError(f"Dataref name too long (> 500 bytes): {dataref}")
        return b"DREF\x00" + struct.pack("<f", float(value)) + dref_bytes.ljust(500, b"\x00")

    @staticmethod
    def pack_cmnd(command: str) -> bytes:
        """Pack CMND message: b'CMND\x00' + command string + null byte."""
        return b"CMND\x00" + command.encode("utf-8") + b"\x00"

    @staticmethod
    def pack_rref(dataref: str, freq_hz: int, dref_id: int) -> bytes:
        """Pack RREF subscription request: b'RREF\x00' + freq_hz (i4) + id (i4) + 400-byte path."""
        dref_bytes = dataref.encode("utf-8")
        if len(dref_bytes) > 400:
            raise ValueError(f"Dataref name too long for RREF (> 400 bytes): {dataref}")
        return b"RREF\x00" + struct.pack("<ii", int(freq_hz), int(dref_id)) + dref_bytes.ljust(400, b"\x00")

    @staticmethod
    def pack_vehs(
        plane_idx: int,
        lat_deg: float,
        lon_deg: float,
        ele_m: float,
        psi_true: float,
        pitch_deg: float = 0.0,
        roll_deg: float = 0.0,
    ) -> bytes:
        """Pack VEHS (relocate aircraft without resetting flight dynamics):
        b'VEHS\x00' + int(plane_idx) + double(lat) + double(lon) + double(ele) +
        float(psi) + float(pitch) + float(roll).
        """
        return b"VEHS\x00" + struct.pack(
            "<idddfff",
            int(plane_idx),
            float(lat_deg),
            float(lon_deg),
            float(ele_m),
            float(psi_true),
            float(pitch_deg),
            float(roll_deg),
        )

    # --------------------------------------------------------------------------
    # Send methods
    # --------------------------------------------------------------------------

    def send_dref(self, dataref: str, value: float) -> None:
        """Send dataref value update to X-Plane."""
        with self._lock:
            self._cache[dataref] = float(value)
        if self.mock or not self._sock:
            return
        packet = self.pack_dref(dataref, value)
        try:
            self._sock.sendto(packet, (self.host, self.port))
        except OSError as e:
            logger.error("Failed to send DREF %s=%f: %s", dataref, value, e)

    def send_command(self, command: str) -> None:
        """Send command trigger to X-Plane."""
        if self.mock or not self._sock:
            return
        packet = self.pack_cmnd(command)
        try:
            self._sock.sendto(packet, (self.host, self.port))
        except OSError as e:
            logger.error("Failed to send CMND %s: %s", command, e)

    def subscribe_dref(
        self,
        dataref: str,
        freq_hz: int = 10,
        callback: Optional[Callable[[str, float], None]] = None,
    ) -> int:
        """Subscribe to a dataref at specified frequency in Hz."""
        with self._lock:
            if dataref in self._dref_to_id:
                sub_id = self._dref_to_id[dataref]
            else:
                sub_id = self._next_sub_id
                self._next_sub_id += 1
                self._dref_to_id[dataref] = sub_id
                self._id_to_dref[sub_id] = dataref

            if callback:
                self._callbacks.setdefault(dataref, []).append(callback)

        if not self.mock and self._sock:
            packet = self.pack_rref(dataref, freq_hz, sub_id)
            try:
                self._sock.sendto(packet, (self.host, self.port))
            except OSError as e:
                logger.error("Failed to subscribe to %s: %s", dataref, e)

        return sub_id

    def unsubscribe_dref(self, dataref: str) -> None:
        """Cancel subscription to a dataref (freq_hz = 0)."""
        with self._lock:
            sub_id = self._dref_to_id.get(dataref)
            if sub_id is None:
                return

        if not self.mock and self._sock:
            packet = self.pack_rref(dataref, 0, sub_id)
            try:
                self._sock.sendto(packet, (self.host, self.port))
            except OSError:
                pass

    def set_position(
        self,
        lat_deg: float,
        lon_deg: float,
        ele_m: float,
        heading_true: float,
        pitch_deg: float = 0.0,
        roll_deg: float = 0.0,
        plane_idx: int = 0,
    ) -> None:
        """Relocate aircraft to specified coordinates and heading."""
        if self.mock:
            with self._lock:
                self._cache["sim/flightmodel/position/latitude"] = lat_deg
                self._cache["sim/flightmodel/position/longitude"] = lon_deg
                self._cache["sim/flightmodel/position/elevation"] = ele_m
                self._cache["sim/flightmodel/position/psi"] = heading_true
                self._cache["sim/flightmodel/position/theta"] = pitch_deg
                self._cache["sim/flightmodel/position/phi"] = roll_deg
            return

        packet = self.pack_vehs(
            plane_idx=plane_idx,
            lat_deg=lat_deg,
            lon_deg=lon_deg,
            ele_m=ele_m,
            psi_true=heading_true,
            pitch_deg=pitch_deg,
            roll_deg=roll_deg,
        )
        if self._sock:
            try:
                self._sock.sendto(packet, (self.host, self.port))
            except OSError as e:
                logger.error("Failed to set position via VEHS: %s", e)

        # Also write explicit position datarefs as a fallback
        self.send_dref("sim/flightmodel/position/latitude", lat_deg)
        self.send_dref("sim/flightmodel/position/longitude", lon_deg)
        self.send_dref("sim/flightmodel/position/elevation", ele_m)
        self.send_dref("sim/flightmodel/position/psi", heading_true)
        self.send_dref("sim/flightmodel/position/theta", pitch_deg)
        self.send_dref("sim/flightmodel/position/phi", roll_deg)

    def set_paused(self, paused: bool) -> None:
        """Pause or unpause simulator."""
        self.send_dref("sim/time/paused", 1.0 if paused else 0.0)

    # --------------------------------------------------------------------------
    # Telemetry Cache Access
    # --------------------------------------------------------------------------

    def get_dref(self, dataref: str, default: float = 0.0) -> float:
        """Get the latest cached value for a dataref."""
        with self._lock:
            return self._cache.get(dataref, default)

    def get_all_cached(self) -> Dict[str, float]:
        """Return a copy of all cached datarefs."""
        with self._lock:
            return dict(self._cache)

    def set_mock_dref(self, dataref: str, value: float) -> None:
        """Directly inject a dataref value (primarily for testing and mock runs)."""
        with self._lock:
            self._cache[dataref] = float(value)
            cbs = list(self._callbacks.get(dataref, []))
        for cb in cbs:
            try:
                cb(dataref, float(value))
            except Exception as e:
                logger.error("Callback error on %s: %s", dataref, e)

    # --------------------------------------------------------------------------
    # Receiver Loop & Packet Parser
    # --------------------------------------------------------------------------

    def _listen_loop(self) -> None:
        """Background thread receiving UDP packets from X-Plane."""
        while self._running and self._sock:
            try:
                data, _addr = self._sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            if not data or len(data) < 5:
                continue

            header = data[:5]
            if header == b"RREF\x00":
                self._parse_rref(data[5:])
            elif header == b"DATA\x00" or header == b"DATA@":
                self._parse_data(data[5:])

    def _parse_rref(self, payload: bytes) -> None:
        """Parse RREF payload containing pairs of (int dref_id, float value)."""
        num_items = len(payload) // 8
        updates: list[Tuple[str, float, list[Callable[[str, float], None]]]] = []

        with self._lock:
            for i in range(num_items):
                chunk = payload[i * 8 : (i + 1) * 8]
                if len(chunk) < 8:
                    continue
                dref_id, val = struct.unpack("<if", chunk)
                dref_name = self._id_to_dref.get(dref_id)
                if dref_name:
                    self._cache[dref_name] = val
                    cbs = self._callbacks.get(dref_name)
                    if cbs:
                        updates.append((dref_name, val, list(cbs)))

        for dref_name, val, cbs in updates:
            for cb in cbs:
                try:
                    cb(dref_name, val)
                except Exception as e:
                    logger.error("Callback error on %s: %s", dref_name, e)

    def _parse_data(self, payload: bytes) -> None:
        """Parse standard X-Plane DATA output packet."""
        # 36 bytes per data block: 4 bytes int index + 8 * 4 bytes float values
        num_blocks = len(payload) // 36
        for i in range(num_blocks):
            chunk = payload[i * 36 : (i + 1) * 36]
            if len(chunk) < 36:
                continue
            idx = struct.unpack("<i", chunk[:4])[0]
            values = struct.unpack("<8f", chunk[4:])
            # Index 3: speeds (kias = values[0], ktas = values[2], groundspeed = values[3])
            if idx == 3:
                with self._lock:
                    self._cache["sim/flightmodel/position/indicated_airspeed"] = values[0]
                    self._cache["sim/flightmodel/position/true_airspeed"] = values[2]
                    self._cache["sim/flightmodel/position/groundspeed"] = values[3]
            # Index 20: position (lat = values[0], lon = values[1], alt_ft = values[2])
            elif idx == 20:
                with self._lock:
                    self._cache["sim/flightmodel/position/latitude"] = values[0]
                    self._cache["sim/flightmodel/position/longitude"] = values[1]
                    self._cache["sim/flightmodel/position/elevation"] = values[2] * 0.3048
