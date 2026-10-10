"""Minimal MAVLink codec and TCP link for the ArduPlane backend. Stdlib only.

The small backend, mission-transaction, and diagnostic message subset is
encoded and decoded by hand. A full dialect library was rejected on purpose:
the service's core remains stdlib only. Golden bytes in the tests were
produced with pymavlink and pinned to check this hand encoding against the
MAVLink dialect.

Frames: MAVLink v2 is emitted; v1 and v2 are both decoded. Signed frames are
rejected (nothing here can verify a signature, so accepting one would be
accepting an unauthenticated write path), unknown ids are skipped, a CRC
failure drops one byte and resyncs.
"""

from __future__ import annotations

import logging
from collections import deque
import socket
import struct
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger("ai_pilot.mavlink_min")

MAGIC_V1 = 0xFE
MAGIC_V2 = 0xFD
INCOMPAT_FLAG_SIGNED = 0x01

# ------------------------------------------------------------------ enums ----

MAV_TYPE_GCS = 6
MAV_AUTOPILOT_INVALID = 8
MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1
MAV_MODE_FLAG_SAFETY_ARMED = 128
MAV_STATE_ACTIVE = 4

MAV_CMD_DO_SET_MODE = 176
MAV_CMD_DO_SET_MISSION_CURRENT = 224
MAV_CMD_DO_SET_HOME = 179
MAV_CMD_SET_MESSAGE_INTERVAL = 511
MAV_CMD_GUIDED_CHANGE_SPEED = 43000
MAV_CMD_GUIDED_CHANGE_ALTITUDE = 43001
MAV_CMD_GUIDED_CHANGE_HEADING = 43002
MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_NAV_LAND = 21
MAV_CMD_NAV_TAKEOFF = 22
MAV_CMD_DO_LAND_START = 189
MAV_CMD_DO_GO_AROUND = 191

MAV_RESULT_ACCEPTED = 0
MAV_RESULT_TEMPORARILY_REJECTED = 1
MAV_RESULT_DENIED = 2
MAV_RESULT_UNSUPPORTED = 3
MAV_RESULT_FAILED = 4
MAV_RESULT_IN_PROGRESS = 5

MAV_FRAME_GLOBAL = 0
MAV_FRAME_GLOBAL_RELATIVE_ALT = 3
MAV_FRAME_GLOBAL_INT = 5
MAV_FRAME_GLOBAL_RELATIVE_ALT_INT = 6
MAV_MISSION_ACCEPTED = 0
MAV_MISSION_TYPE_MISSION = 0

HEADING_TYPE_COG = 0
HEADING_TYPE_HEADING = 1
HEADING_TYPE_DEFAULT = 2

PLANE_MODE_MANUAL = 0
PLANE_MODE_FBWA = 5
PLANE_MODE_RTL = 11
PLANE_MODE_LOITER = 12
PLANE_MODE_GUIDED = 15
PLANE_MODE_AUTO = 10

MSG_HEARTBEAT = 0
MSG_PARAM_REQUEST_READ = 20
MSG_PARAM_VALUE = 22
MSG_ATTITUDE = 30
MSG_GLOBAL_POSITION_INT = 33
MSG_SERVO_OUTPUT_RAW = 36
MSG_MISSION_CURRENT = 42
MSG_MISSION_COUNT = 44
MSG_MISSION_ITEM_REACHED = 46
MSG_MISSION_ACK = 47
MSG_MISSION_REQUEST_INT = 51
MSG_MISSION_ITEM_INT = 73
MSG_RC_CHANNELS = 65
MSG_VFR_HUD = 74
MSG_COMMAND_INT = 75
MSG_COMMAND_LONG = 76
MSG_COMMAND_ACK = 77
MSG_AUTOPILOT_VERSION = 148

# ----------------------------------------------------------- definitions ----

# (name, struct format in WIRE order, crc_extra, field names in wire order).
# Wire order is the XML field list sorted by type size, descending, with
# extension fields appended unsorted - that is what the CRC and the trailing
# zero truncation are computed over, not the documentation order.
MSG_DEFS = {
    MSG_HEARTBEAT: (
        "HEARTBEAT", "<IBBBBB", 50,
        ("custom_mode", "type", "autopilot", "base_mode", "system_status", "mavlink_version"),
    ),
    MSG_PARAM_REQUEST_READ: (
        "PARAM_REQUEST_READ", "<hBB16s", 214,
        ("param_index", "target_system", "target_component", "param_id"),
    ),
    MSG_PARAM_VALUE: (
        "PARAM_VALUE", "<fHH16sB", 220,
        ("param_value", "param_count", "param_index", "param_id", "param_type"),
    ),
    MSG_ATTITUDE: (
        "ATTITUDE", "<Iffffff", 39,
        ("time_boot_ms", "roll", "pitch", "yaw", "rollspeed", "pitchspeed", "yawspeed"),
    ),
    MSG_GLOBAL_POSITION_INT: (
        "GLOBAL_POSITION_INT", "<IiiiihhhH", 104,
        ("time_boot_ms", "lat", "lon", "alt", "relative_alt", "vx", "vy", "vz", "hdg"),
    ),
    MSG_SERVO_OUTPUT_RAW: (
        "SERVO_OUTPUT_RAW", "<I8HB8H", 222,
        ("time_usec",) + tuple("servo%d_raw" % i for i in range(1, 9))
        + ("port",) + tuple("servo%d_raw" % i for i in range(9, 17)),
    ),
    MSG_MISSION_CURRENT: (
        "MISSION_CURRENT", "<HHBB", 28,
        ("seq", "total", "mission_state", "mission_mode"),
    ),
    MSG_MISSION_COUNT: (
        "MISSION_COUNT", "<HBBB", 221,
        ("count", "target_system", "target_component", "mission_type"),
    ),
    MSG_MISSION_ITEM_REACHED: (
        "MISSION_ITEM_REACHED", "<H", 11, ("seq",),
    ),
    MSG_MISSION_ACK: (
        "MISSION_ACK", "<BBBB", 153,
        ("target_system", "target_component", "type", "mission_type"),
    ),
    MSG_MISSION_REQUEST_INT: (
        "MISSION_REQUEST_INT", "<HBBB", 196,
        ("seq", "target_system", "target_component", "mission_type"),
    ),
    MSG_MISSION_ITEM_INT: (
        "MISSION_ITEM_INT", "<ffffiifHHBBBBBB", 38,
        ("param1", "param2", "param3", "param4", "x", "y", "z", "seq",
         "command", "target_system", "target_component", "frame", "current",
         "autocontinue", "mission_type"),
    ),
    MSG_RC_CHANNELS: (
        "RC_CHANNELS", "<I18HBB", 118,
        ("time_boot_ms",) + tuple("chan%d_raw" % i for i in range(1, 19)) + ("chancount", "rssi"),
    ),
    MSG_VFR_HUD: (
        "VFR_HUD", "<ffffhH", 20,
        ("airspeed", "groundspeed", "alt", "climb", "heading", "throttle"),
    ),
    MSG_COMMAND_INT: (
        "COMMAND_INT", "<ffffiifHBBBBB", 158,
        ("param1", "param2", "param3", "param4", "x", "y", "z", "command",
         "target_system", "target_component", "frame", "current", "autocontinue"),
    ),
    MSG_COMMAND_LONG: (
        "COMMAND_LONG", "<fffffffHBBB", 152,
        ("param1", "param2", "param3", "param4", "param5", "param6", "param7",
         "command", "target_system", "target_component", "confirmation"),
    ),
    MSG_COMMAND_ACK: (
        # progress / result_param2 / target_* are MAVLink 2 extensions.
        "COMMAND_ACK", "<HBBiBB", 143,
        ("command", "result", "progress", "result_param2", "target_system", "target_component"),
    ),
    MSG_AUTOPILOT_VERSION: (
        "AUTOPILOT_VERSION", "<QQIIIIHH8s8s8s18s", 178,
        ("capabilities", "uid", "flight_sw_version", "middleware_sw_version",
         "os_sw_version", "board_version", "vendor_id", "product_id",
         "flight_custom_version", "middleware_custom_version",
         "os_custom_version", "uid2"),
    ),
}

_HEADER_LEN = {MAGIC_V1: 6, MAGIC_V2: 10}
_SIGNATURE_LEN = 13


def crc16_mcrf4xx(data: bytes, crc: int = 0xFFFF) -> int:
    """X.25 / MCRF4XX CRC as MAVLink uses it, continuable."""
    for byte in data:
        tmp = (byte ^ crc) & 0xFF
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc


@dataclass(frozen=True)
class Message:
    msgid: int
    name: str
    fields: dict
    sysid: int
    compid: int
    seq: int


def pack_payload(msgid: int, fields: dict) -> bytes:
    name, fmt, _extra, names = MSG_DEFS[msgid]
    missing = [n for n in names if n not in fields]
    if missing:
        raise ValueError("%s missing fields %s" % (name, missing))
    return struct.pack(fmt, *(fields[n] for n in names))


def unpack_payload(msgid: int, payload: bytes) -> dict:
    _name, fmt, _extra, names = MSG_DEFS[msgid]
    size = struct.calcsize(fmt)
    # v2 trims trailing zero bytes; a v1 frame lacks the extension fields
    # entirely. Both cases are "zero from here on".
    payload = payload[:size].ljust(size, b"\x00")
    return dict(zip(names, struct.unpack(fmt, payload)))


def encode(msgid: int, fields: dict, seq: int, sysid: int = 255, compid: int = 190) -> bytes:
    """MAVLink 2 frame, unsigned, trailing zero payload bytes trimmed."""
    _name, _fmt, crc_extra, _names = MSG_DEFS[msgid]
    payload = pack_payload(msgid, fields).rstrip(b"\x00") or b"\x00"
    header = bytes((
        MAGIC_V2, len(payload), 0, 0, seq & 0xFF, sysid & 0xFF, compid & 0xFF,
        msgid & 0xFF, (msgid >> 8) & 0xFF, (msgid >> 16) & 0xFF,
    ))
    crc = crc16_mcrf4xx(header[1:] + payload)
    crc = crc16_mcrf4xx(bytes((crc_extra,)), crc)
    return header + payload + struct.pack("<H", crc)


class Parser:
    """Incremental frame parser over a byte stream."""

    MAX_BUFFER = 64 * 1024

    def __init__(self):
        self._buf = bytearray()
        self.dropped = 0        # bytes discarded while resyncing
        self.rejected = 0       # complete frames refused (signed, bad CRC)

    def feed(self, data: bytes) -> list:
        self._buf += data
        if len(self._buf) > self.MAX_BUFFER:
            del self._buf[:-self.MAX_BUFFER]
        out = []
        while True:
            message, consumed = self._next()
            if consumed == 0:
                break
            del self._buf[:consumed]
            if message is not None:
                out.append(message)
        return out

    def _next(self):
        buf = self._buf
        if not buf:
            return None, 0
        magic = buf[0]
        if magic not in _HEADER_LEN:
            self.dropped += 1
            return None, 1
        hdr = _HEADER_LEN[magic]
        if len(buf) < hdr:
            return None, 0
        length = buf[1]
        signed = magic == MAGIC_V2 and (buf[2] & INCOMPAT_FLAG_SIGNED)
        total = hdr + length + 2 + (_SIGNATURE_LEN if signed else 0)
        if len(buf) < total:
            return None, 0
        if magic == MAGIC_V2:
            seq, sysid, compid = buf[4], buf[5], buf[6]
            msgid = buf[7] | (buf[8] << 8) | (buf[9] << 16)
        else:
            seq, sysid, compid, msgid = buf[2], buf[3], buf[4], buf[5]
        definition = MSG_DEFS.get(msgid)
        if definition is None:
            # No crc_extra, so the frame cannot be verified; trust its length.
            return None, total
        # The checksum covers len..payload for signed frames too (the
        # signature follows it), so verify BEFORE honouring a signed frame's
        # claimed length: a stray byte pattern with the signed bit set must
        # not be allowed to swallow the real frames behind it.
        crc_extra = definition[2]
        payload = bytes(buf[hdr:hdr + length])
        crc = crc16_mcrf4xx(bytes(buf[1:hdr]) + payload)
        crc = crc16_mcrf4xx(bytes((crc_extra,)), crc)
        (wire_crc,) = struct.unpack_from("<H", buf, hdr + length)
        if crc != wire_crc:
            self.rejected += 1
            self.dropped += 1
            return None, 1
        if signed:
            # Genuine signed frame. Nothing here can verify the signature, so
            # do not trust it; skip it as a unit.
            self.rejected += 1
            return None, total
        return Message(msgid, definition[0], unpack_payload(msgid, payload), sysid, compid, seq), total


# --------------------------------------------------------------- builders ----

def heartbeat() -> tuple:
    return MSG_HEARTBEAT, {
        "custom_mode": 0, "type": MAV_TYPE_GCS, "autopilot": MAV_AUTOPILOT_INVALID,
        "base_mode": 0, "system_status": MAV_STATE_ACTIVE, "mavlink_version": 3,
    }


def command_long(command: int, target_system: int, target_component: int, *params) -> tuple:
    params = list(params) + [0.0] * (7 - len(params))
    return MSG_COMMAND_LONG, {
        "param1": params[0], "param2": params[1], "param3": params[2], "param4": params[3],
        "param5": params[4], "param6": params[5], "param7": params[6],
        "command": command, "target_system": target_system,
        "target_component": target_component, "confirmation": 0,
    }


def command_int(command: int, target_system: int, target_component: int, frame: int,
                param1=0.0, param2=0.0, param3=0.0, param4=0.0, x=0, y=0, z=0.0) -> tuple:
    return MSG_COMMAND_INT, {
        "param1": param1, "param2": param2, "param3": param3, "param4": param4,
        "x": int(x), "y": int(y), "z": float(z), "command": command,
        "target_system": target_system, "target_component": target_component,
        "frame": frame, "current": 0, "autocontinue": 0,
    }


def set_mode(mode: int, target_system: int = 1, target_component: int = 1) -> tuple:
    return command_long(MAV_CMD_DO_SET_MODE, target_system, target_component,
                        float(MAV_MODE_FLAG_CUSTOM_MODE_ENABLED), float(mode))


def set_home_here(target_system: int = 1, target_component: int = 1) -> tuple:
    """param1=1 means 'use the vehicle's current location', so no coordinates
    are sent and nothing can be mistyped into them."""
    return command_long(MAV_CMD_DO_SET_HOME, target_system, target_component, 1.0)


def set_message_interval(msgid: int, hz: float, target_system: int = 1, target_component: int = 1) -> tuple:
    interval_us = 1e6 / hz if hz > 0 else -1.0
    return command_long(MAV_CMD_SET_MESSAGE_INTERVAL, target_system, target_component,
                        float(msgid), float(interval_us))


def guided_change_heading(heading_type: int, heading_deg: float, rate_deg_s: float,
                          target_system: int = 1, target_component: int = 1) -> tuple:
    """COMMAND_INT only: ArduPlane's guided slew handler ignores COMMAND_LONG."""
    return command_int(MAV_CMD_GUIDED_CHANGE_HEADING, target_system, target_component,
                       MAV_FRAME_GLOBAL, param1=float(heading_type),
                       param2=float(heading_deg), param3=float(rate_deg_s))


def guided_change_altitude(alt_m: float, frame: int, rate_m_s: float,
                           target_system: int = 1, target_component: int = 1) -> tuple:
    return command_int(MAV_CMD_GUIDED_CHANGE_ALTITUDE, target_system, target_component,
                       frame, param3=float(rate_m_s), z=float(alt_m))


def param_request_read(name: str, target_system=1, target_component=1):
    raw = name.encode("ascii")
    if not 1 <= len(raw) <= 16:
        raise ValueError("MAVLink parameter name must be 1–16 ASCII bytes")
    return MSG_PARAM_REQUEST_READ, {"param_index": -1,
                                    "target_system": target_system,
                                    "target_component": target_component,
                                    "param_id": raw.ljust(16, b"\x00")}


# ------------------------------------------------------------------- link ----

class MavlinkLink:
    """TCP client to a SITL / autopilot MAVLink endpoint.

    The reader thread only stores the latest copy of each message and resolves
    command ACK waits. It never calls into the backend, so no backend lock is
    ever taken from this thread.
    """

    HEARTBEAT_HZ = 1.0
    # HEARTBEAT at 5 Hz so a mode change is confirmed within ~200 ms rather
    # than up to a second; the backend's GUIDED confirmation waits on it.
    STREAMS = ((MSG_HEARTBEAT, 5.0), (MSG_RC_CHANNELS, 5.0), (MSG_VFR_HUD, 5.0),
               (MSG_GLOBAL_POSITION_INT, 5.0), (MSG_ATTITUDE, 5.0),
               (MSG_SERVO_OUTPUT_RAW, 5.0))

    def __init__(self, host="127.0.0.1", port=5760, clock=time.monotonic,
                 sysid=255, compid=190, target_system=1, target_component=1,
                 connect=True, timeout=2.0):
        self.host, self.port, self.clock = host, port, clock
        self.sysid, self.compid = sysid, compid
        self.target_system, self.target_component = target_system, target_component
        self.timeout = timeout
        self._sock = None
        self._parser = Parser()
        self._latest = {}
        self._received = deque(maxlen=300)
        self._cursor = 0
        self._acks = {}
        self._ack_events = {}
        self._seq = 0
        self._lock = threading.Lock()
        self._receive_condition = threading.Condition(self._lock)
        self._send_lock = threading.Lock()
        self._running = False
        self._reader = None
        self._beater = None
        self.sent = 0
        if connect:
            self.connect()

    # -- lifecycle --

    def connect(self):
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._sock.settimeout(0.5)
        self._running = True
        self._reader = threading.Thread(target=self._read_loop, name="mavlink-reader", daemon=True)
        self._beater = threading.Thread(target=self._heartbeat_loop, name="mavlink-heartbeat", daemon=True)
        self._reader.start()
        self._beater.start()
        for msgid, hz in self.STREAMS:
            self.send(*set_message_interval(msgid, hz, self.target_system, self.target_component))

    def close(self):
        self._running = False
        sock, self._sock = self._sock, None
        if sock:
            try:
                sock.close()
            except OSError:
                pass
        for thread in (self._reader, self._beater):
            if thread and thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=1.0)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- sending --

    def send(self, msgid: int, fields: dict) -> None:
        # The whole frame goes out under the lock: a heartbeat and a command
        # from two threads must not interleave on a partial send.
        with self._send_lock:
            frame = encode(msgid, fields, self._seq, self.sysid, self.compid)
            self._seq = (self._seq + 1) & 0xFF
            self.sent += 1
            sock = self._sock
            if sock is None:
                raise OSError("MAVLink link is not connected")
            sock.sendall(frame)

    def arm_ack(self, command: int) -> threading.Event:
        """Call before sending a command so an early ACK cannot be missed."""
        with self._lock:
            self._acks.pop(command, None)
            event = threading.Event()
            self._ack_events[command] = event
            return event

    def wait_ack(self, command: int, timeout: float):
        """Result code of the ACK for `command`, or None on timeout."""
        with self._lock:
            event = self._ack_events.get(command)
        if event is None:
            event = self.arm_ack(command)
        if not event.wait(timeout):
            return None
        with self._lock:
            entry = self._acks.get(command)
        return entry[0] if entry else None

    # -- observing --

    def latest(self, msgid: int):
        """(fields, age_seconds) of the newest copy, or (None, inf)."""
        with self._lock:
            entry = self._latest.get(msgid)
        if entry is None:
            return None, float("inf")
        return entry[0], self.clock() - entry[1]

    def message_cursor(self) -> int:
        with self._lock:
            return self._cursor

    def wait_message(self, msgids, after_cursor: int, timeout: float):
        """Wait for a new validated frame, preserving duplicate mission requests."""
        wanted = set(msgids)
        deadline = time.monotonic() + timeout
        with self._receive_condition:
            while True:
                for cursor, message in self._received:
                    if cursor > after_cursor and message.msgid in wanted:
                        return cursor, message
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return after_cursor, None
                self._receive_condition.wait(remaining)

    def heartbeat_age(self) -> float:
        return self.latest(MSG_HEARTBEAT)[1]

    def custom_mode(self):
        fields, _age = self.latest(MSG_HEARTBEAT)
        return None if fields is None else fields["custom_mode"]

    def request_param(self, name: str, timeout=0.4, retries=2):
        """Return a fresh effective value; a defaults file is not a readback."""
        msgid, fields = param_request_read(name, self.target_system, self.target_component)
        for _ in range(retries + 1):
            cursor = self.message_cursor()
            self.send(msgid, fields)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                cursor, message = self.wait_message(
                    (MSG_PARAM_VALUE,), cursor, deadline - time.monotonic())
                if message is None:
                    break
                returned = message.fields["param_id"].split(b"\x00", 1)[0]
                if returned == name.encode("ascii"):
                    return float(message.fields["param_value"])
        raise TimeoutError("Effective parameter %s not returned" % name)

    # -- threads --

    def _deliver(self, message: Message) -> None:
        if message.sysid != self.target_system:
            return      # another GCS, or a companion, on the same link
        now = self.clock()
        with self._receive_condition:
            self._cursor += 1
            self._received.append((self._cursor, message))
            self._latest[message.msgid] = (message.fields, now)
            if message.msgid == MSG_COMMAND_ACK:
                command = message.fields["command"]
                self._acks[command] = (message.fields["result"], now)
                event = self._ack_events.get(command)
                if event:
                    event.set()
            self._receive_condition.notify_all()

    def _read_loop(self) -> None:
        while self._running:
            sock = self._sock
            if sock is None:
                break
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            for message in self._parser.feed(data):
                self._deliver(message)
        self._running = False

    def _heartbeat_loop(self) -> None:
        period = 1.0 / self.HEARTBEAT_HZ
        while self._running:
            try:
                self.send(*heartbeat())
            except OSError:
                break
            time.sleep(period)


class MockLink(MavlinkLink):
    """Offline stand-in: records sends, lets a test inject frames, auto-ACKs.

    The same surface as MavlinkLink so the backend and the fly script do not
    branch on it, mirroring XPlaneUDPClient(mock=True).
    """

    def __init__(self, clock=time.monotonic, auto_ack=MAV_RESULT_ACCEPTED, **kwargs):
        super().__init__(clock=clock, connect=False, **kwargs)
        self.sent_messages = []
        self.auto_ack = auto_ack        # result code, or None to never ACK
        self.ack_overrides = {}         # command -> result, wins over auto_ack
        self.honour_mode_changes = True # False: ACK a DO_SET_MODE but never report the new mode

    def connect(self):
        self._running = True

    def close(self):
        self._running = False

    def send(self, msgid: int, fields: dict) -> None:
        encode(msgid, fields, self._seq, self.sysid, self.compid)  # validate like the real thing
        self._seq = (self._seq + 1) & 0xFF
        self.sent += 1
        self.sent_messages.append((msgid, dict(fields)))
        if msgid in (MSG_COMMAND_LONG, MSG_COMMAND_INT):
            command = fields["command"]
            result = self.ack_overrides.get(command, self.auto_ack)
            if result is not None:
                self.inject_ack(command, result)
            if command == MAV_CMD_DO_SET_MODE and result == MAV_RESULT_ACCEPTED and self.honour_mode_changes:
                self.inject_heartbeat(int(fields["param2"]))

    def inject(self, msgid: int, fields: dict, sysid: int = 1, compid: int = 1) -> None:
        self._deliver(Message(msgid, MSG_DEFS[msgid][0], dict(fields), sysid, compid, 0))

    def inject_heartbeat(self, custom_mode: int,
                         base_mode: int = MAV_MODE_FLAG_CUSTOM_MODE_ENABLED | MAV_MODE_FLAG_SAFETY_ARMED) -> None:
        self.inject(MSG_HEARTBEAT, {
            "custom_mode": custom_mode, "type": 1, "autopilot": 3,
            "base_mode": base_mode, "system_status": MAV_STATE_ACTIVE, "mavlink_version": 3,
        })

    def inject_ack(self, command: int, result: int) -> None:
        self.inject(MSG_COMMAND_ACK, {
            "command": command, "result": result, "progress": 0,
            "result_param2": 0, "target_system": 255, "target_component": 190,
        })

    def sent_commands(self) -> list:
        return [fields["command"] for msgid, fields in self.sent_messages
                if msgid in (MSG_COMMAND_LONG, MSG_COMMAND_INT)]
