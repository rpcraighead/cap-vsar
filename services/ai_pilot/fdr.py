"""
Flight Data Recorder (FDR) Tap
------------------------------
High-rate telemetry and avionics recording tap for X-Plane 12 and CAP V-SAR.
Captures synchronous frames across flight kinematics, Becker SAR-DF-517,
RHOTHETA RT-600, scenario ground truth, and CAP FM / GMA-1347 radios.
"""

from __future__ import annotations

import csv
import datetime
import json
import logging
import math
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .flight_controller import haversine_distance_nm
from .xplane_udp import XPlaneUDPClient

logger = logging.getLogger("ai_pilot.fdr")

DEFAULT_RECORDS_DIR = Path(__file__).resolve().parent.parent.parent / "logs" / "fdr"


RECORDED_DATAREFS = (
    "cap/df/active_freq_hz",
    "cap/df/airframe_attenuation_db",
    "cap/df/airframe_shadowed",
    "cap/df/band",
    "cap/df/bearing_rel",
    "cap/df/bearing_true",
    "cap/df/blocked",
    "cap/df/cs_country",
    "cap/df/cs_has_position",
    "cap/df/cs_lat",
    "cap/df/cs_lon",
    "cap/df/cs_msg_age_sec",
    "cap/df/cs_protocol",
    "cap/df/cs_sync",
    "cap/df/distance_nm",
    "cap/df/error_code",
    "cap/df/head_type",
    "cap/df/in_cone",
    "cap/df/mode",
    "cap/df/mounting",
    "cap/df/offset_deg",
    "cap/df/power",
    "cap/df/rx_open",
    "cap/df/rx_span_hz",
    "cap/df/scan_enable",
    "cap/df/signal",
    "cap/df/spread",
    "cap/df/squelch",
    "cap/df/timehold_sec",
    "cap/df/valid",
    "cap/scenario/active",
    "cap/scenario/beacon_elev",
    "cap/scenario/beacon_lat",
    "cap/scenario/beacon_lon",
    "cap_fm_audio_selected",
    "cap_fm_channel",
    "cap_fm_frequency_hz",
    "cap_fm_guard_frequency_hz",
    "cap_fm_high_power",
    "cap_fm_mic_selected",
    "cap_fm_power_on",
    "cap_fm_transmitting",
    "sim/cockpit2/radios/actuators/audio_com_listen",
    "sim/cockpit2/radios/actuators/audio_com_mic",
    "sim/cockpit2/radios/actuators/audio_panel_copilot_ptt",
    "sim/cockpit2/radios/actuators/com1_frequency_hz_833",
    "sim/cockpit2/radios/actuators/com2_frequency_hz_833",
    "sim/cockpit2/radios/actuators/transponder_code",
    "sim/flightmodel/position/elevation",
    "sim/flightmodel/position/groundspeed",
    "sim/flightmodel/position/indicated_airspeed",
    "sim/flightmodel/position/latitude",
    "sim/flightmodel/position/longitude",
    "sim/flightmodel/position/mag_psi",
    "sim/flightmodel/position/phi",
    "sim/flightmodel/position/psi",
    "sim/flightmodel/position/theta",
    "sim/flightmodel/position/vh_ind_fpm",
    "sim/flightmodel/position/y_agl",
    "sim/time/total_flight_time_sec",
)
"""Every dataref sample_current_frame reads.

AI-11: nothing used to subscribe these. In --live mode only legacy DATA
packets (indices 3 and 20, off by default in X-Plane) populated anything, so
speed and position arrived if the operator had hand-configured a Data Output
the README never mentioned, and heading, attitude, AGL, VVI, engine and every
cap/df/* dataref stayed at their defaults forever. The recorder subscribes
what it records, because it is the component that knows what that is.
"""


STALE_AFTER_S = 2.0
"""Seconds a dataref may go unheard before the recorder stops treating it as
measured. AI-11: past this the reading is NaN, which records "not known"
rather than a number nobody observed."""


@dataclass
class FDRFrame:
    """Synchronous frame capturing complete aircraft and avionics state."""

    # Timestamp & Indexing
    timestamp_utc: str
    sim_time_s: float
    frame_index: int

    # Flight Dynamics & Position
    lat: float
    lon: float
    alt_msl_ft: float
    alt_agl_ft: float
    roll_deg: float
    pitch_deg: float
    heading_mag: float
    heading_true: float
    kias: float
    groundspeed_kts: float
    vvi_fpm: float

    # Flight Controller State
    flight_phase: str

    # DF System Outputs (cap/df/*)
    df_valid: int
    df_bearing_rel: float
    df_bearing_true: float
    df_signal: float  # 0.0 .. 1.0 link budget
    df_distance_nm: float
    df_in_cone: int
    df_blocked: int
    df_airframe_shadowed: int
    df_airframe_attenuation_db: float
    df_rx_open: int
    df_band_mhz: float
    df_spread_deg: float
    df_error_code: int  # -1 = none, 0..12 = E0..E12

    # COSPAS-SARSAT Decodes
    cs_sync: int
    cs_protocol: int
    cs_hex15: str
    cs_country: int
    cs_has_position: int
    cs_lat: float
    cs_lon: float
    cs_msg_age_sec: float

    # DF Panel Configuration & Crew Settings
    df_power: int
    df_active_freq_hz: int
    df_head_type: int  # 0 = Becker SAR-DF-517, 1 = RHOTHETA RT-600
    df_squelch: float  # 0..100%, or -1 for Auto Squelch
    df_mode: int  # 0 = Emergency, 1 = Training
    df_scan_enable: int
    df_timehold_sec: float
    df_offset_deg: float
    df_mounting: int  # 0 = top, 1 = bottom
    df_rx_span_hz: int

    # Scenario Ground Truth (cap/scenario/*)
    scenario_active: int
    beacon_lat: float
    beacon_lon: float
    beacon_elev_ft: float

    # Standard Aviation Radios
    com1_freq_hz: int
    com2_freq_hz: int
    com_mic_channel: int
    com_listen_channel: int
    transponder_code: int

    # CAP FM Radio (TDFM-136B) & Audio Panel (GMA-1347)
    cap_fm_power: bool
    cap_fm_freq_hz: int
    cap_fm_channel: int
    cap_fm_channel_name: str
    cap_fm_transmitting: bool
    cap_fm_ptt: bool
    cap_fm_high_power: bool
    cap_fm_guard_freq_hz: int
    cap_ics_isolation: str
    cap_fm_audio_selected: bool
    cap_fm_mic_selected: bool

    # AI-11. 1 while the simulator is actually reporting telemetry, 0 when
    # nothing has ever arrived or the link has gone quiet. Without this a
    # recording of silence is indistinguishable from a recording of an
    # aeroplane parked at 0N 0E, and the debrief engine grades it as a flight.
    link_established: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FlightDataRecorder:
    """Manages continuous recording of FDRFrame streams to disk and memory."""

    def __init__(
        self,
        client: XPlaneUDPClient,
        output_dir: Optional[Path] = None,
        ring_buffer_size: int = 1000,
        rate_hz: float = 4.0,
    ) -> None:
        self.client = client
        self.output_dir = output_dir or DEFAULT_RECORDS_DIR
        self.ring_buffer_size = ring_buffer_size
        self.rate_hz = rate_hz
        # AI-11: how long a dataref may go unheard before it stops counting as
        # a measurement. Generous next to the 4 Hz default record rate.
        self.stale_after_s = STALE_AFTER_S

        # AI-11: subscribe what we record. Without this the cache is only ever
        # populated by whatever legacy Data Output the operator happened to
        # enable, and every other field is a default masquerading as data.
        self.subscribe_recorded_datarefs()

        self._lock = threading.Lock()
        self._recording = False
        self._thread: Optional[threading.Thread] = None
        self._current_file: Optional[Path] = None
        self._file_handle = None
        self._frame_count = 0
        self._session_start_time: Optional[float] = None
        self._ring_buffer: List[FDRFrame] = []
        self._stop_event = threading.Event()

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    @property
    def current_file(self) -> Optional[Path]:
        with self._lock:
            return self._current_file

    @property
    def frame_count(self) -> int:
        with self._lock:
            return self._frame_count

    def start_recording(self, session_name: Optional[str] = None) -> Path:
        """Start background FDR recording."""
        with self._lock:
            if self._recording:
                logger.warning("FDR is already recording to %s", self._current_file)
                return self._current_file  # type: ignore

            self.output_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
            name = f"fdr_{session_name}_{ts}.jsonl" if session_name else f"fdr_{ts}.jsonl"
            self._current_file = self.output_dir / name
            self._file_handle = open(self._current_file, "w", encoding="utf-8")

            self._recording = True
            self._frame_count = 0
            self._session_start_time = time.time()
            self._ring_buffer.clear()
            self._stop_event.clear()

            self._thread = threading.Thread(target=self._sampling_loop, daemon=True, name="FDR-Sampler")
            self._thread.start()

            logger.info("FDR recording started: %s (sampling rate: %.1f Hz)", self._current_file, self.rate_hz)
            return self._current_file

    def stop_recording(self) -> Optional[Path]:
        """Stop FDR recording and flush output file."""
        with self._lock:
            if not self._recording:
                return None
            self._recording = False
            self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        with self._lock:
            if self._file_handle:
                try:
                    self._file_handle.flush()
                    self._file_handle.close()
                except Exception as e:
                    logger.error("Error closing FDR file: %s", e)
                self._file_handle = None

            filepath = self._current_file
            logger.info("FDR recording stopped: %s (%d frames saved)", filepath, self._frame_count)
            return filepath

    def record_frame(self, frame: FDRFrame) -> None:
        """Record a single frame to file and in-memory ring buffer (thread-safe)."""
        with self._lock:
            self._frame_count += 1
            # Add to ring buffer
            self._ring_buffer.append(frame)
            if len(self._ring_buffer) > self.ring_buffer_size:
                self._ring_buffer.pop(0)

            # Write to disk if active
            if self._file_handle:
                line = json.dumps(frame.to_dict()) + "\n"
                self._file_handle.write(line)

    def subscribe_recorded_datarefs(self, freq_hz: int = 10) -> int:
        """Ask the simulator to stream every dataref this recorder writes.

        Returns the number subscribed. Safe to call again; subscribe_dref
        reuses the existing id for a dataref already registered.
        """
        count = 0
        for dataref in RECORDED_DATAREFS:
            try:
                self.client.subscribe_dref(dataref, freq_hz=freq_hz)
                count += 1
            except Exception as exc:                      # pragma: no cover
                logger.warning("Could not subscribe %s: %s", dataref, exc)
        logger.info("FDR subscribed %d datarefs at %d Hz", count, freq_hz)
        return count

    def _measured(self, dataref: str) -> float:
        """A float the simulator actually reported recently, else NaN.

        AI-11: the alternative is a 0.0 default, which writes a stationary
        aeroplane at 0N 0E and a powered DF into the record and lets the
        debrief engine grade a flight that never happened. NaN propagates
        honestly - it is not a position, not a speed, and not zero.
        """
        return self.client.get_dref(
            dataref, default=float("nan"), max_age_s=self.stale_after_s
        )

    def sample_current_frame(self, phase: str = "IN_FLIGHT") -> FDRFrame:
        """Sample a complete FDRFrame from the client cache."""
        c = self.client
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sim_time = self._measured("sim/time/total_flight_time_sec")

        # Kinematics
        lat = self._measured("sim/flightmodel/position/latitude")
        lon = self._measured("sim/flightmodel/position/longitude")
        ele_m = self._measured("sim/flightmodel/position/elevation")
        alt_msl_ft = ele_m * 3.28084
        alt_agl_ft = self._measured("sim/flightmodel/position/y_agl") * 3.28084
        roll = self._measured("sim/flightmodel/position/phi")
        pitch = self._measured("sim/flightmodel/position/theta")
        hdg_true = self._measured("sim/flightmodel/position/psi")
        hdg_mag = self._measured("sim/flightmodel/position/mag_psi")
        if hdg_mag != hdg_mag:
            hdg_mag = hdg_true
        kias = self._measured("sim/flightmodel/position/indicated_airspeed")
        gs = self._measured("sim/flightmodel/position/groundspeed") * 1.94384
        vvi = self._measured("sim/flightmodel/position/vh_ind_fpm")

        # DF State
        df_valid = int(c.get_dref("cap/df/valid", 0.0))
        df_bearing_rel = self._measured("cap/df/bearing_rel")
        df_bearing_true = self._measured("cap/df/bearing_true")
        df_signal = self._measured("cap/df/signal")
        df_distance_nm = self._measured("cap/df/distance_nm")
        df_in_cone = int(c.get_dref("cap/df/in_cone", 0.0))
        df_blocked = int(c.get_dref("cap/df/blocked", 0.0))
        df_shadowed = int(c.get_dref("cap/df/airframe_shadowed", 0.0))
        df_atten = c.get_dref("cap/df/airframe_attenuation_db", 0.0)
        df_rx_open = int(c.get_dref("cap/df/rx_open", 0.0))
        df_band = c.get_dref("cap/df/band", 121.5)
        df_spread = c.get_dref("cap/df/spread", 0.0)
        df_error = int(c.get_dref("cap/df/error_code", -1.0))

        # COSPAS-SARSAT
        cs_sync = int(c.get_dref("cap/df/cs_sync", 0.0))
        cs_proto = int(c.get_dref("cap/df/cs_protocol", 0.0))
        cs_hex15 = ""
        cs_country = int(c.get_dref("cap/df/cs_country", 0.0))
        cs_has_pos = int(c.get_dref("cap/df/cs_has_position", 0.0))
        cs_lat = c.get_dref("cap/df/cs_lat", 0.0)
        cs_lon = c.get_dref("cap/df/cs_lon", 0.0)
        cs_age = c.get_dref("cap/df/cs_msg_age_sec", 0.0)

        # Panel Inputs
        df_power = int(c.get_dref("cap/df/power", 1.0))
        df_freq = int(c.get_dref("cap/df/active_freq_hz", 121500000.0))
        df_head = int(c.get_dref("cap/df/head_type", 0.0))
        df_squelch = c.get_dref("cap/df/squelch", -1.0)
        df_mode = int(c.get_dref("cap/df/mode", 0.0))
        df_scan = int(c.get_dref("cap/df/scan_enable", 0.0))
        df_timehold = c.get_dref("cap/df/timehold_sec", 10.0)
        df_offset = c.get_dref("cap/df/offset_deg", 0.0)
        df_mount = int(c.get_dref("cap/df/mounting", 0.0))
        df_span = int(c.get_dref("cap/df/rx_span_hz", 0.0))

        # Scenario Truth
        scn_active = int(c.get_dref("cap/scenario/active", 0.0))
        bc_lat = c.get_dref("cap/scenario/beacon_lat", 0.0)
        bc_lon = c.get_dref("cap/scenario/beacon_lon", 0.0)
        bc_elev = c.get_dref("cap/scenario/beacon_elev", 0.0)

        # Standard Radios
        com1 = int(c.get_dref("sim/cockpit2/radios/actuators/com1_frequency_hz_833", 128250.0))
        com2 = int(c.get_dref("sim/cockpit2/radios/actuators/com2_frequency_hz_833", 122900.0))
        com_mic = int(c.get_dref("sim/cockpit2/radios/actuators/audio_com_mic", 1.0))
        com_listen = int(c.get_dref("sim/cockpit2/radios/actuators/audio_com_listen", 1.0))
        xpdr = int(c.get_dref("sim/cockpit2/radios/actuators/transponder_code", 1200.0))

        # CAP Radios
        fm_power = bool(c.get_dref("cap_fm_power_on", 1.0) > 0.5)
        fm_freq = int(c.get_dref("cap_fm_frequency_hz", 148150000.0))
        fm_chan = int(c.get_dref("cap_fm_channel", 1.0))
        fm_tx = bool(c.get_dref("cap_fm_transmitting", 0.0) > 0.5)
        fm_ptt = bool(c.get_dref("sim/cockpit2/radios/actuators/audio_panel_copilot_ptt", 0.0) > 0.5)
        fm_hi = bool(c.get_dref("cap_fm_high_power", 1.0) > 0.5)
        fm_gd = int(c.get_dref("cap_fm_guard_frequency_hz", 168650000.0))
        ics_iso = "ALL"
        fm_aud_sel = bool(c.get_dref("cap_fm_audio_selected", 1.0) > 0.5)
        fm_mic_sel = bool(c.get_dref("cap_fm_mic_selected", 1.0) > 0.5)

        return FDRFrame(
            timestamp_utc=now_utc,
            sim_time_s=sim_time,
            frame_index=self._frame_count,
            lat=lat,
            lon=lon,
            alt_msl_ft=alt_msl_ft,
            alt_agl_ft=alt_agl_ft,
            roll_deg=roll,
            pitch_deg=pitch,
            heading_mag=hdg_mag,
            heading_true=hdg_true,
            kias=kias,
            groundspeed_kts=gs,
            vvi_fpm=vvi,
            flight_phase=phase,
            link_established=int(self.client.link_established()),
            df_valid=df_valid,
            df_bearing_rel=df_bearing_rel,
            df_bearing_true=df_bearing_true,
            df_signal=df_signal,
            df_distance_nm=df_distance_nm,
            df_in_cone=df_in_cone,
            df_blocked=df_blocked,
            df_airframe_shadowed=df_shadowed,
            df_airframe_attenuation_db=df_atten,
            df_rx_open=df_rx_open,
            df_band_mhz=df_band,
            df_spread_deg=df_spread,
            df_error_code=df_error,
            cs_sync=cs_sync,
            cs_protocol=cs_proto,
            cs_hex15=cs_hex15,
            cs_country=cs_country,
            cs_has_position=cs_has_pos,
            cs_lat=cs_lat,
            cs_lon=cs_lon,
            cs_msg_age_sec=cs_age,
            df_power=df_power,
            df_active_freq_hz=df_freq,
            df_head_type=df_head,
            df_squelch=df_squelch,
            df_mode=df_mode,
            df_scan_enable=df_scan,
            df_timehold_sec=df_timehold,
            df_offset_deg=df_offset,
            df_mounting=df_mount,
            df_rx_span_hz=df_span,
            scenario_active=scn_active,
            beacon_lat=bc_lat,
            beacon_lon=bc_lon,
            beacon_elev_ft=bc_elev,
            com1_freq_hz=com1,
            com2_freq_hz=com2,
            com_mic_channel=com_mic,
            com_listen_channel=com_listen,
            transponder_code=xpdr,
            cap_fm_power=fm_power,
            cap_fm_freq_hz=fm_freq,
            cap_fm_channel=fm_chan,
            cap_fm_channel_name="TAC 1",
            cap_fm_transmitting=fm_tx,
            cap_fm_ptt=fm_ptt,
            cap_fm_high_power=fm_hi,
            cap_fm_guard_freq_hz=fm_gd,
            cap_ics_isolation=ics_iso,
            cap_fm_audio_selected=fm_aud_sel,
            cap_fm_mic_selected=fm_mic_sel,
        )

    def _sampling_loop(self) -> None:
        """Background sampling thread loop."""
        interval = 1.0 / self.rate_hz
        while not self._stop_event.is_set():
            t0 = time.time()
            try:
                frame = self.sample_current_frame()
                self.record_frame(frame)
            except Exception as e:
                logger.error("Error sampling FDR frame: %s", e)

            elapsed = time.time() - t0
            sleep_time = max(0.001, interval - elapsed)
            self._stop_event.wait(timeout=sleep_time)

    def get_ring_buffer(self) -> List[Dict[str, Any]]:
        """Return shallow copy of current in-memory ring buffer frames as dicts."""
        with self._lock:
            return [f.to_dict() for f in self._ring_buffer]

    def get_status(self) -> Dict[str, Any]:
        """Return recorder health and status."""
        with self._lock:
            dur = (time.time() - self._session_start_time) if (self._recording and self._session_start_time) else 0.0
            return {
                "is_recording": self._recording,
                "current_file": str(self._current_file) if self._current_file else None,
                "frame_count": self._frame_count,
                "duration_seconds": round(dur, 1),
                "sampling_rate_hz": self.rate_hz,
                "ring_buffer_size": len(self._ring_buffer),
                "output_dir": str(self.output_dir),
            }

    @staticmethod
    def export_csv(jsonl_path: Path, csv_path: Path) -> int:
        """Convert a JSONL FDR session file into a CSV spreadsheet."""
        if not jsonl_path.is_file():
            raise FileNotFoundError(f"JSONL file not found: {jsonl_path}")

        count = 0
        with open(jsonl_path, "r", encoding="utf-8") as f_in:
            first_line = f_in.readline()
            if not first_line:
                return 0
            first_obj = json.loads(first_line)
            fieldnames = list(first_obj.keys())

            with open(csv_path, "w", newline="", encoding="utf-8") as f_out:
                writer = csv.DictWriter(f_out, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(first_obj)
                count += 1

                for line in f_in:
                    if line.strip():
                        obj = json.loads(line)
                        writer.writerow(obj)
                        count += 1
        return count

