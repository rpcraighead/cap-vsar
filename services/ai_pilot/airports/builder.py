"""Build sourced airport/runway-end records from local aviation data.

The apt.dat reader keeps only the requested airport in memory.  The optional
FAA and Chart Supplement readers are deliberately best-effort: free text is
retained verbatim and parsed values from that text are marked low confidence.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any, Iterable

from .schema import AirportRecord, RunwayEndRecord, SourcedValue

XP_ROOT = Path.home() / "X-Plane 12"
GLOBAL_APT = XP_ROOT / "Global Scenery/Global Airports/Earth nav data/apt.dat"
DEFAULT_CIFP = XP_ROOT / "Resources/default data/CIFP"
DEFAULT_EARTH_NAV = XP_ROOT / "Resources/default data/earth_nav.dat"
DEFAULT_NASR = Path.home() / "Projects/ksee-gillespie/data/faa/raw_APT_CSV_2026-10-01"
DEFAULT_CHART = Path.home() / "Downloads/chart-supplement-2026-09-03/CS_SW_20260903.txt"
KSAN_CUSTOM_APT = (XP_ROOT / "Custom Scenery" / "KSAN_San_Diego_Int'l v3.0"
                   / "Earth nav data/apt.dat")
KSEE_CUSTOM_APT = (XP_ROOT / "Custom Scenery" / "KSEE Gillespie Field"
                   / "Earth nav data/apt.dat")
FT_TO_M = 0.3048
_LEGACY_DISPLACEMENT_OVERRIDES = {"KCRQ 24": 305.0}

_RUNWAY_RE = re.compile(r"^(\d{1,2})([LCR]?)$", re.I)
_CHART_HEADER_RE = re.compile(r"\(([A-Z0-9]{3})\)\((K[A-Z0-9]{3})\)")


def normalize_runway(value: str) -> str:
    value = value.strip().upper().removeprefix("RW")
    match = _RUNWAY_RE.match(value)
    if not match:
        return value
    return f"{int(match.group(1)):02d}{match.group(2).upper()}"


def _float(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _source_value(value: Any, source: str | None, confidence: str = "high",
                  detail: str | None = None) -> SourcedValue:
    return SourcedValue(value, source, confidence, detail)


def _distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    north = (b[0] - a[0]) * 111132.92
    east = (b[1] - a[1]) * 111412.84 * math.cos(math.radians(a[0]))
    return math.hypot(north, east)


def _bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    north = (b[0] - a[0]) * 111132.92
    east = (b[1] - a[1]) * 111412.84 * math.cos(math.radians(a[0]))
    return math.degrees(math.atan2(east, north)) % 360.0


def _angle_difference(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _airport_id_match(row: dict[str, str], icao: str) -> bool:
    return row.get("ICAO_ID", "").strip().upper() == icao or \
        row.get("ARPT_ID", "").strip().upper() == icao[-3:]


def _apt_airport(path: Path, icao: str) -> dict[str, Any] | None:
    """Stream one apt.dat and retain only the requested airport block."""
    active: dict[str, Any] | None = None
    found: dict[str, Any] | None = None
    flow_title = ""
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, 1):
            parts = line.split()
            if not parts:
                continue
            code = parts[0]
            if code in {"1", "16", "17"}:
                if active is not None:
                    found = active
                active = None
                flow_title = ""
                if code == "1" and len(parts) >= 5 and parts[4].upper() == icao:
                    active = {"icao": icao, "name": " ".join(parts[5:]),
                              "elevation_ft": _float(parts[1]), "source": str(path),
                              "header_line": line_number, "runways": [], "vgsi": [],
                              "flows": [], "patterns": [], "frequencies": []}
                continue
            if active is None:
                continue
            if code == "100" and len(parts) >= 26:
                width = _float(parts[1])
                pair_id = f"{normalize_runway(parts[8])}-{normalize_runway(parts[17])}"
                ends = []
                for offset in (8, 17):
                    end = normalize_runway(parts[offset])
                    lat, lon, displaced = (_float(parts[offset + index])
                                           for index in (1, 2, 3))
                    if end and lat is not None and lon is not None:
                        ends.append({"runway_end": end, "runway_id": pair_id,
                                     "threshold": [lat, lon],
                                     "displaced_threshold_m": displaced or 0.0,
                                     "blast_pad_m": _float(parts[offset + 4]),
                                     "markings_code": parts[offset + 5],
                                     "approach_lights_code": parts[offset + 6],
                                     "tdz_lights_code": parts[offset + 7],
                                     "reil_code": parts[offset + 8],
                                     "width_m": width, "row": line_number,
                                     "apt_source": str(path)})
                if len(ends) == 2:
                    ends[0]["far_end"] = ends[1]["threshold"]
                    ends[1]["far_end"] = ends[0]["threshold"]
                    active["runways"].extend(ends)
            elif code == "21" and len(parts) >= 6:
                values = [_float(v) for v in parts[1:3]]
                orientation, angle = _float(parts[4]), _float(parts[5])
                if values[0] is not None and values[1] is not None and angle is not None:
                    active["vgsi"].append({"position": values, "type": parts[3],
                                            "orientation_deg": orientation,
                                            "angle_deg": angle, "row": line_number,
                                            "source": str(path)})
            elif code == "1000":
                flow_title = " ".join(parts[1:])
                active["flows"].append({"flow": flow_title, "rows": [],
                                        "source": str(path), "row": line_number})
            elif code in {"1001", "1002", "1003", "1101", "1110"}:
                row = {"type": code, "values": parts[1:], "source": str(path),
                       "row": line_number}
                if active["flows"]:
                    active["flows"][-1]["rows"].append(row)
                if code == "1101" and len(parts) >= 3:
                    active["patterns"].append({"runway": normalize_runway(parts[1]),
                                              "side": parts[2].lower(), "flow": flow_title,
                                              "source": str(path), "row": line_number})
            elif code in {"1050", "1051", "1052", "1053", "1054", "1055", "1056"}:
                if len(parts) >= 3:
                    active["frequencies"].append({"type": code, "frequency_khz": parts[1],
                                                  "label": " ".join(parts[2:]),
                                                  "source": str(path), "row": line_number})
    if active is not None:
        found = active
    return found


def _cifp_records(path: Path, icao: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return result
    for line_number, line in enumerate(path.open(encoding="utf-8", errors="replace"), 1):
        if not line.startswith("RWY:"):
            continue
        sections = line.rstrip("\n").split(";")
        header = sections[0].split(",")
        match = re.search(r"RW(\d{1,2}[LCR]?)", header[0].upper())
        if not match:
            continue
        runway_end = normalize_runway(match.group(1))
        elevation = _float(header[3]) if len(header) > 3 else None
        coord_parts = sections[1].split(",") if len(sections) > 1 else []
        lat = _arinc_coordinate(coord_parts[0]) if coord_parts else None
        lon = _arinc_coordinate(coord_parts[1]) if len(coord_parts) > 1 else None
        displaced_ft = _float(coord_parts[2]) if len(coord_parts) > 2 else None
        result[runway_end] = {"threshold": [lat, lon] if lat is not None and lon is not None else None,
                              "threshold_elevation_ft": elevation,
                              "displaced_threshold_ft": displaced_ft,
                              "source": str(path), "line": line_number}
    return result


def _arinc_coordinate(value: str) -> float | None:
    value = value.strip().upper()
    if len(value) < 8 or value[0] not in "NSEW":
        return None
    try:
        degrees_digits = 2 if value[0] in "NS" else 3
        degrees = int(value[1:1 + degrees_digits])
        minutes = int(value[1 + degrees_digits:3 + degrees_digits])
        seconds = int(value[3 + degrees_digits:]) / 100.0
        result = degrees + minutes / 60.0 + seconds / 3600.0
        return -result if value[0] in "SW" else result
    except ValueError:
        return None


def _earth_nav_gs(path: Path, icao: str) -> dict[str, list[dict[str, Any]]]:
    """Collect matching glide-slope rows and decode their combined field.

    X-Plane NAV1200 encodes glide angle * 100,000 plus the true course. The
    course is in [0, 360), so the angle's hundredths are the thousands prefix.
    Retain the raw value and decoded course alongside the angle for audit.
    """
    result: dict[str, list[dict[str, Any]]] = {}
    if not path.is_file():
        return result
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, 1):
            parts = line.split()
            if len(parts) >= 8 and parts[0] == "6" and parts[-1].upper() == "GS":
                airport = next((p.upper() for p in parts if p.upper() == icao), None)
                if not airport:
                    continue
                runway = (normalize_runway(parts[-2])
                          if re.fullmatch(r"\d{1,2}[LCR]?", parts[-2], re.I) else None)
                if not runway:
                    continue
                raw_angle_field = parts[6]
                raw_combined = _float(raw_angle_field)
                decoded_angle = None
                decoded_course = None
                if raw_combined is not None and raw_combined >= 0:
                    angle_hundredths = math.floor(raw_combined / 1000.0 + 1e-9)
                    decoded_course = round(raw_combined - angle_hundredths * 1000.0, 3)
                    candidate_angle = angle_hundredths / 100.0
                    if 0 < candidate_angle < 90 and 0 <= decoded_course < 360:
                        decoded_angle = candidate_angle
                    else:
                        decoded_course = None
                result.setdefault(runway, []).append({
                    "raw_course_angle_field": raw_angle_field,
                    "decoded_glide_angle_deg": decoded_angle,
                    "decoded_true_course_deg": decoded_course,
                    "ident": parts[7],
                    "source": str(path), "line": line_number,
                })
    return result


def _runway_pair_key(value: str) -> frozenset[str]:
    ends = re.split(r"[/\-]", value.strip().upper())
    return frozenset(normalize_runway(end) for end in ends if end)


def _read_nasr(directory: Path, icao: str) -> dict[str, Any]:
    data: dict[str, Any] = {"ends": {}, "widths": {}, "airport": {}, "remarks": []}
    base_path = directory / "APT_BASE.csv"
    if base_path.is_file():
        with base_path.open(newline="", encoding="latin1") as stream:
            for row in csv.DictReader(stream):
                if _airport_id_match(row, icao):
                    data["airport"] = {"elevation_ft": _float(row.get("ELEV")),
                                       "tpa": row.get("TPA") or None,
                                       "name": row.get("ARPT_NAME") or None,
                                       "source": str(base_path)}
                    break
    runway_path = directory / "APT_RWY.csv"
    if runway_path.is_file():
        with runway_path.open(newline="", encoding="latin1") as stream:
            for row in csv.DictReader(stream):
                if _airport_id_match(row, icao):
                    data["widths"][_runway_pair_key(row.get("RWY_ID", ""))] = {
                        "width_ft": _float(row.get("RWY_WIDTH")), "source": str(runway_path),
                        "runway_id": row.get("RWY_ID")}
    end_path = directory / "APT_RWY_END.csv"
    if end_path.is_file():
        with end_path.open(newline="", encoding="latin1") as stream:
            for row in csv.DictReader(stream):
                if not _airport_id_match(row, icao):
                    continue
                runway_end = normalize_runway(row.get("RWY_END_ID", ""))
                if not runway_end:
                    continue
                pair = _runway_pair_key(row.get("RWY_ID", ""))
                width = data["widths"].get(pair, {})
                data["ends"][runway_end] = {
                    "runway_id": row.get("RWY_ID"),
                    "threshold": [_float(row.get("LAT_DECIMAL")),
                                  _float(row.get("LONG_DECIMAL"))],
                    "threshold_elevation_ft": _float(row.get("RWY_END_ELEV")),
                    "tch_ft": _float(row.get("THR_CROSSING_HGT")),
                    "vgsi_glide_angle_deg": _float(row.get("VISUAL_GLIDE_PATH_ANGLE")),
                    "displaced_threshold_ft": _float(row.get("DISPLACED_THR_LEN")),
                    "right_hand_traffic": (row.get("RIGHT_HAND_TRAFFIC_PAT_FLAG") or "").upper(),
                    "vgsi_code": row.get("VGSI_CODE") or None,
                    "runway_gradient_pct": _float(row.get("RWY_GRAD")),
                    "runway_gradient_direction": row.get("RWY_GRAD_DIRECTION") or None,
                    "width_ft": width.get("width_ft"),
                    "source": str(end_path), "line_end": runway_end,
                }
    remarks_path = directory / "APT_RMK.csv"
    if remarks_path.is_file():
        with remarks_path.open(newline="", encoding="latin1") as stream:
            for row in csv.DictReader(stream):
                if _airport_id_match(row, icao) and row.get("REMARK"):
                    data["remarks"].append({"value": row["REMARK"].strip(),
                                            "source": str(remarks_path),
                                            "tab": row.get("TAB_NAME"),
                                            "element": row.get("ELEMENT")})
    return data


def _chart_block(path: Path, icao: str) -> dict[str, Any]:
    if not path.is_file():
        return {}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = None
    for index, line in enumerate(lines):
        if any(match.group(2) == icao for match in _CHART_HEADER_RE.finditer(line)):
            start = index
            break
    if start is None:
        return {}
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if any(_CHART_HEADER_RE.search(line) for line in lines[index:index + 1]):
            end = index
            break
    block_lines = lines[start:end]
    text = "\n".join(block_lines)
    result: dict[str, Any] = {"ends": {}, "remarks": [], "source": str(path)}
    if len(block_lines) > 1:
        elevation_match = re.match(r"\s*([\d,]+)\s+[A-Z]", block_lines[1])
        if elevation_match:
            result["elevation_ft"] = _float(elevation_match.group(1))
    # Runway-specific lines may wrap; collect each end's text until the next
    # runway end or airport section heading.
    runway_text = re.split(r"\bRUNWAY DECLARED DISTANCE INFORMATION\b", text,
                           maxsplit=1, flags=re.I)[0]
    pair_gradients: dict[str, dict[str, Any]] = {}
    pair_headers = list(re.finditer(
        r"\bRWY\s+(\d{1,2}[LCR]?)\s*[–—-]\s*(\d{1,2}[LCR]?)\s*:",
        runway_text, re.I))
    for pair_index, pair_match in enumerate(pair_headers):
        pair_limit = (pair_headers[pair_index + 1].start()
                      if pair_index + 1 < len(pair_headers) else len(runway_text))
        pair_segment = runway_text[pair_match.end():pair_limit]
        first_end = re.search(r"\bRWY\s+\d{1,2}[LCR]?\s*:", pair_segment, re.I)
        if first_end:
            pair_segment = pair_segment[:first_end.start()]
        gradient = re.search(r"([\d.]+)%\s+(up|down)(?:\s+([NSEW]+))?", pair_segment, re.I)
        if gradient:
            value = {"percent": _float(gradient.group(1)),
                     "direction": gradient.group(2).lower(),
                     "bearing": (gradient.group(3) or "").upper() or None}
            for runway_end in (normalize_runway(pair_match.group(1)),
                               normalize_runway(pair_match.group(2))):
                pair_gradients[runway_end] = value
                result["ends"].setdefault(runway_end, {
                    "vgsi_glide_angle_deg": None, "tch_ft": None,
                    "displaced_threshold_ft": None, "right_hand_traffic": None,
                    "runway_gradient": value, "source": str(path),
                    "confidence": "low", "quote": " ".join(pair_segment.split())[:360],
                })
    start_matches = list(re.finditer(r"\bRWY\s+(\d{1,2}[LCR]?)\s*:", runway_text, re.I))
    for index, match in enumerate(start_matches):
        runway_end = normalize_runway(match.group(1))
        next_end = (start_matches[index + 1].start()
                    if index + 1 < len(start_matches) else len(runway_text))
        next_pair = next((pair.start() for pair in pair_headers
                          if pair.start() > match.start()), len(runway_text))
        segment_end = min(next_end, next_pair)
        segment = runway_text[match.end():segment_end]
        segment = re.split(r"\n\s*(?:RUNWAY DECLARED|SERVICE:|NOISE:|AIRPORT REMARKS:|COMMUNICATIONS:)",
                           segment, maxsplit=1, flags=re.I)[0]
        angle = re.search(r"(?:PAPI|PVASI)\s*\([^)]*\)\s*[-–—]\s*GA\s*([\d.]+)\s*[º°]?\s*TCH\s*(\d+)\s*[´′']?",
                          segment, re.I)
        displaced = re.search(r"Thld\s+dsplcd\s+([\d,]+)\s*[´′']?", segment, re.I)
        traffic = re.search(r"\bRgt\s+tfc\b", segment, re.I)
        gradient = re.search(r"([\d.]+)%\s+(up|down)(?:\s+([NSEW]+))?", segment, re.I)
        gradient_value = ({"percent": _float(gradient.group(1)),
                           "direction": gradient.group(2).lower(),
                           "bearing": (gradient.group(3) or "").upper() or None}
                          if gradient else pair_gradients.get(runway_end))
        result["ends"][runway_end] = {
            "vgsi_glide_angle_deg": _float(angle.group(1)) if angle else None,
            "tch_ft": _float(angle.group(2)) if angle else None,
            "displaced_threshold_ft": _float(displaced.group(1)) if displaced else None,
            "right_hand_traffic": "Y" if traffic else None,
            "runway_gradient": gradient_value,
            "source": str(path), "confidence": "low", "quote": " ".join(segment.split())[:360],
        }
    # Keep untrusted prose as quoted evidence; typed extraction is deliberately
    # conservative and remains marked low-confidence.
    remarks = []
    for section in ("NOISE:", "AIRPORT REMARKS:"):
        match = re.search(r"(?m)^\s*" + re.escape(section) + r"\s*(.*?)(?=^\s*[A-Z][A-Z /-]+:|\Z)",
                          text, re.I | re.S)
        if match:
            remarks.append(" ".join(match.group(1).split()))
    result["remarks"] = remarks
    tpa_matches = re.findall(r"\bTPA\s*[—–-]\s*([^\n.]+)", text, re.I)
    useful_tpa = next((value.strip() for value in tpa_matches
                       if value.strip() and not value.strip().lower().startswith("see remarks")), None)
    result["tpa_text"] = useful_tpa or (tpa_matches[0].strip() if tpa_matches else None)
    gradients = re.findall(r"([\d.]+)%\s+(up|down)\s+([NSEW]+)", text, re.I)
    result["gradients"] = [f"{number}% {direction.lower()} {bearing.upper()}"
                           for number, direction, bearing in gradients]
    return result


def _value_for(record: dict[str, Any], field: str) -> Any:
    item = record.get("fields", {}).get(field)
    if isinstance(item, dict) and "value" in item:
        return item["value"]
    return item


def _numbers_differ(values: list[dict[str, Any]], field: str) -> bool:
    present = [item["value"] for item in values if item.get("value") is not None]
    if len(present) < 2:
        return False
    if field in {"threshold", "far_end"}:
        try:
            return any(_distance_m(tuple(a), tuple(b)) > 0.01
                       for i, a in enumerate(present) for b in present[i + 1:])
        except (TypeError, ValueError):
            return len({repr(v) for v in present}) > 1
    if all(isinstance(value, (float, int)) for value in present):
        tolerance = 1e-6
        return max(present) - min(present) > tolerance
    return len({repr(value) for value in present}) > 1


class AirportRecordBuilder:
    """Construct one airport's runway-end records using local files only."""

    def __init__(self, *, apt_paths: Iterable[str | Path] | None = None,
                 comparison_apt_paths: Iterable[str | Path] | None = None,
                 cifp_dir: str | Path | None = None,
                 earth_nav_path: str | Path | None = None,
                 nasr_dir: str | Path | None = None,
                 chart_supplement: str | Path | None = None):
        use_installed_defaults = apt_paths is None
        if apt_paths is None:
            paths = [GLOBAL_APT]
            # This locally installed custom airport is the source of the pinned
            # KSAN 27 coordinates. Paths are ordered from base to overlay.
            if KSAN_CUSTOM_APT.is_file():
                paths.append(KSAN_CUSTOM_APT)
            apt_paths = paths
        self.apt_paths = [Path(path) for path in apt_paths]
        if comparison_apt_paths is None:
            comparison_apt_paths = ([KSEE_CUSTOM_APT] if use_installed_defaults and
                                    KSEE_CUSTOM_APT.is_file() else [])
        self.comparison_apt_paths = [Path(path) for path in comparison_apt_paths]
        self.cifp_dir = Path(cifp_dir) if cifp_dir is not None else DEFAULT_CIFP
        self.earth_nav_path = Path(earth_nav_path) if earth_nav_path is not None else DEFAULT_EARTH_NAV
        self.nasr_dir = Path(nasr_dir) if nasr_dir is not None else DEFAULT_NASR
        self.chart_supplement = (Path(chart_supplement) if chart_supplement is not None
                                 else DEFAULT_CHART)

    def build(self, icao: str) -> AirportRecord:
        icao = icao.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{4}", icao):
            raise ValueError("ICAO must be a four-character airport code")
        apt_versions = [record for path in self.apt_paths
                        if path.is_file() and (record := _apt_airport(path, icao))]
        if not apt_versions:
            raise LookupError(f"{icao} was not found in the configured apt.dat files")
        comparison_versions = [record for path in self.comparison_apt_paths
                              if path.is_file() and (record := _apt_airport(path, icao))]
        all_apt_versions = apt_versions + comparison_versions
        effective = apt_versions[-1]
        cifp = _cifp_records(self.cifp_dir / f"{icao}.dat", icao)
        nav = _earth_nav_gs(self.earth_nav_path, icao)
        nasr = _read_nasr(self.nasr_dir, icao)
        chart = _chart_block(self.chart_supplement, icao)

        airport_fields: dict[str, SourcedValue] = {}
        airport_sources: dict[str, list[dict[str, Any]]] = {}
        airport_disagreements: dict[str, list[dict[str, Any]]] = {}
        airport_candidates: dict[str, list[SourcedValue]] = {
            "airport_name": [], "airport_elevation_ft": [], "tpa": [],
            "frequencies": [], "traffic_flows": [],
            "remarks": [],
        }
        for version in all_apt_versions:
            if version.get("name"):
                airport_candidates["airport_name"].append(_source_value(
                    version["name"], version["source"], detail="apt.dat airport header"))
            airport_candidates["airport_elevation_ft"].append(
                _source_value(version["elevation_ft"], version["source"],
                              detail=f"apt.dat header row {version['header_line']}"))
        if nasr.get("airport", {}).get("name"):
            airport_candidates["airport_name"].append(_source_value(
                nasr["airport"]["name"], nasr["airport"]["source"]))
        if nasr.get("airport", {}).get("elevation_ft") is not None:
            airport_candidates["airport_elevation_ft"].append(_source_value(
                nasr["airport"]["elevation_ft"], nasr["airport"]["source"]))
        if chart.get("elevation_ft") is not None:
            airport_candidates["airport_elevation_ft"].append(_source_value(
                chart["elevation_ft"], chart["source"], "low", "parsed Chart Supplement header"))
        if nasr.get("airport", {}).get("tpa"):
            airport_candidates["tpa"].append(_source_value(nasr["airport"]["tpa"],
                                                            nasr["airport"]["source"]))
        if chart.get("tpa_text"):
            airport_candidates["tpa"].append(_source_value(chart["tpa_text"], chart["source"],
                                                            "low", "free-text TPA field"))
        for version in all_apt_versions:
            if version["frequencies"]:
                airport_candidates["frequencies"].append(_source_value(
                    version["frequencies"], version["source"], detail="apt.dat frequency rows"))
            if version["flows"]:
                airport_candidates["traffic_flows"].append(_source_value(
                    version["flows"], version["source"], detail="apt.dat 1000/1101 flow rows"))
        for item in nasr.get("remarks", []):
            airport_candidates["remarks"].append(_source_value(
                item["value"], item["source"], "low", f"NASR APT_RMK {item.get('tab')}"))
            if re.search(r"\bTPA\b", item["value"], re.I):
                airport_candidates["tpa"].append(_source_value(
                    item["value"], item["source"], "low", "best-effort extraction from NASR APT_RMK"))
        for remark in chart.get("remarks", []):
            airport_candidates["remarks"].append(_source_value(
                remark, chart.get("source"), "low", "untrusted Chart Supplement prose"))

        for field_name, candidates in airport_candidates.items():
            preferred_source = effective["source"] if field_name in {
                "airport_name", "airport_elevation_ft"} else None
            chosen = next((candidate for candidate in candidates
                           if candidate.source == preferred_source and candidate.value is not None), None)
            chosen = chosen or next((candidate for candidate in candidates
                                     if candidate.value is not None), None)
            if field_name in {"frequencies", "traffic_flows", "remarks"} and candidates:
                chosen = _source_value([candidate.value for candidate in candidates],
                                       "combined local sources", "low" if field_name == "remarks" else "high")
            airport_fields[field_name] = chosen or _source_value(None, None)
            serialized = [candidate.to_dict() | {"source": candidate.source}
                          for candidate in candidates]
            airport_sources[field_name] = serialized
            if _numbers_differ([{"value": c.value} for c in candidates], field_name):
                airport_disagreements[field_name] = serialized

        name = effective.get("name") or nasr.get("airport", {}).get("name") or icao
        runway_ends: list[RunwayEndRecord] = []
        for apt_end in effective["runways"]:
            end_id = apt_end["runway_end"]
            runway_id = apt_end["runway_id"]
            selected_pair = next((runway for runway in effective["runways"]
                                  if runway["runway_id"] == runway_id and
                                  runway["runway_end"] != end_id), None)
            if selected_pair is None:
                continue
            apt_versions_for_end = [
                endpoint for version in all_apt_versions for endpoint in version["runways"]
                if endpoint["runway_end"] == end_id]
            cifp_end = cifp.get(end_id, {})
            nasr_end = nasr.get("ends", {}).get(end_id, {})
            chart_end = chart.get("ends", {}).get(end_id, {})
            candidates: dict[str, list[SourcedValue]] = {
                "threshold": [], "far_end": [], "airport_elevation_ft": [],
                "displaced_threshold_m": [], "width_m": [], "threshold_elevation_ft": [],
                "blast_pad_m": [], "markings_code": [], "approach_lights_code": [],
                "tdz_lights_code": [], "reil_code": [],
                "tch_ft": [], "vgsi_glide_angle_deg": [], "gs_angle_deg": [],
                "runway_gradient": [], "apt_traffic_pattern_for_end": [],
                "nasr_right_hand_traffic": [], "chart_right_hand_traffic": [],
            }
            for endpoint in apt_versions_for_end:
                candidates["threshold"].append(_source_value(endpoint["threshold"],
                    endpoint["apt_source"], detail=f"apt.dat row {endpoint['row']}"))
                candidates["far_end"].append(_source_value(endpoint["far_end"],
                    endpoint["apt_source"], detail=f"opposite end, row {endpoint['row']}"))
                candidates["displaced_threshold_m"].append(_source_value(
                    endpoint["displaced_threshold_m"], endpoint["apt_source"],
                    detail=f"apt.dat row {endpoint['row']} (metres)"))
                candidates["width_m"].append(_source_value(endpoint["width_m"],
                    endpoint["apt_source"], detail=f"apt.dat row {endpoint['row']} (metres)"))
                for field_name in ("blast_pad_m", "markings_code", "approach_lights_code",
                                   "tdz_lights_code", "reil_code"):
                    candidates[field_name].append(_source_value(
                        endpoint[field_name], endpoint["apt_source"],
                        detail=f"apt.dat row {endpoint['row']}"))
            for candidate in airport_candidates["airport_elevation_ft"]:
                candidates["airport_elevation_ft"].append(candidate)
            if cifp_end.get("threshold"):
                candidates["threshold"].append(_source_value(cifp_end["threshold"], cifp_end["source"],
                                                              detail=f"CIFP RWY row {cifp_end['line']}"))
            if cifp_end.get("threshold_elevation_ft") is not None:
                candidates["threshold_elevation_ft"].append(_source_value(
                    cifp_end["threshold_elevation_ft"], cifp_end["source"],
                    detail=f"CIFP RWY row {cifp_end['line']}"))
            if cifp_end.get("displaced_threshold_ft") is not None:
                candidates["displaced_threshold_m"].append(_source_value(
                    cifp_end["displaced_threshold_ft"] * FT_TO_M, cifp_end["source"],
                    detail=f"CIFP displaced length {cifp_end['displaced_threshold_ft']} ft"))
            if nasr_end:
                if nasr_end.get("threshold") and all(v is not None for v in nasr_end["threshold"]):
                    candidates["threshold"].append(_source_value(nasr_end["threshold"],
                                                                  nasr_end["source"], "medium"))
                for key, field_name in (("threshold_elevation_ft", "threshold_elevation_ft"),
                                        ("tch_ft", "tch_ft"),
                                        ("vgsi_glide_angle_deg", "vgsi_glide_angle_deg")):
                    if nasr_end.get(key) is not None:
                        candidates[field_name].append(_source_value(nasr_end[key], nasr_end["source"]))
                if nasr_end.get("displaced_threshold_ft") is not None:
                    candidates["displaced_threshold_m"].append(_source_value(
                        nasr_end["displaced_threshold_ft"] * FT_TO_M, nasr_end["source"],
                        detail=f"NASR displaced length {nasr_end['displaced_threshold_ft']} ft"))
                if nasr_end.get("width_ft") is not None:
                    candidates["width_m"].append(_source_value(nasr_end["width_ft"] * FT_TO_M,
                                                               nasr_end["source"], detail="NASR runway width"))
                if nasr_end.get("runway_gradient_pct") is not None:
                    candidates["runway_gradient"].append(_source_value(
                        {"percent": nasr_end["runway_gradient_pct"],
                         "direction": nasr_end.get("runway_gradient_direction")}, nasr_end["source"]))
                if nasr_end.get("right_hand_traffic") in {"Y", "N"}:
                    candidates["nasr_right_hand_traffic"].append(_source_value(
                        nasr_end["right_hand_traffic"] == "Y", nasr_end["source"]))
            if chart_end:
                for key, field_name in (("tch_ft", "tch_ft"),
                                        ("vgsi_glide_angle_deg", "vgsi_glide_angle_deg")):
                    if chart_end.get(key) is not None:
                        candidates[field_name].append(_source_value(chart_end[key], chart_end["source"],
                                                                   "low", chart_end.get("quote")))
                if chart_end.get("displaced_threshold_ft") is not None:
                    candidates["displaced_threshold_m"].append(_source_value(
                        chart_end["displaced_threshold_ft"] * FT_TO_M, chart_end["source"], "low",
                        chart_end.get("quote")))
                if chart_end.get("right_hand_traffic"):
                    candidates["chart_right_hand_traffic"].append(_source_value(True, chart_end["source"],
                                                                                 "low", chart_end.get("quote")))
                if chart_end.get("runway_gradient"):
                    candidates["runway_gradient"].append(_source_value(
                        chart_end["runway_gradient"], chart_end["source"], "low",
                        chart_end.get("quote")))
            for vgsi in _matched_vgsi(apt_end, selected_pair, effective["vgsi"]):
                candidates["vgsi_glide_angle_deg"].append(_source_value(
                    vgsi["angle_deg"], vgsi["source"], "medium",
                    f"apt.dat row {vgsi['row']}; orientation {vgsi['orientation_deg']}°"))
            for gs in nav.get(end_id, []):
                candidates["gs_angle_deg"].append(_source_value(
                    gs["decoded_glide_angle_deg"], gs["source"], "high",
                    f"earth_nav row {gs['line']}; raw combined field {gs['raw_course_angle_field']}; "
                    f"decoded true course {gs['decoded_true_course_deg']}°"))

            # apt.dat 1101 is a pattern direction assignment within a traffic flow.
            flow_matches = [flow for flow in effective["patterns"] if flow["runway"] == end_id]
            for flow in flow_matches:
                candidates["apt_traffic_pattern_for_end"].append(_source_value(
                    {"side": flow["side"], "flow": flow["flow"]}, flow["source"],
                    detail=f"apt.dat row {flow['row']}"))

            fields: dict[str, SourcedValue] = {}
            fields["runway_end"] = _source_value(
                end_id, apt_end["apt_source"], detail=f"apt.dat row {apt_end['row']} runway designator")
            fields["runway_name"] = _source_value(
                f"{icao} {end_id}", "derived from airport ICAO and runway-end designator")
            field_order = ("threshold", "far_end", "airport_elevation_ft", "displaced_threshold_m",
                           "width_m", "blast_pad_m", "markings_code", "approach_lights_code",
                           "tdz_lights_code", "reil_code", "threshold_elevation_ft", "tch_ft",
                           "vgsi_glide_angle_deg",
                           "gs_angle_deg", "runway_gradient", "apt_traffic_pattern_for_end",
                           "nasr_right_hand_traffic", "chart_right_hand_traffic")
            for field_name in field_order:
                options = candidates[field_name]
                if field_name in {"threshold", "far_end", "displaced_threshold_m", "width_m",
                                  "airport_elevation_ft", "blast_pad_m", "markings_code",
                                  "approach_lights_code", "tdz_lights_code", "reil_code"}:
                    selected = next((option for option in options
                                     if option.source == effective["source"] and option.value is not None), None)
                elif field_name == "threshold_elevation_ft":
                    selected = next((option for option in options if option.source == nasr_end.get("source")), None)
                    selected = selected or next((option for option in options if option.source == cifp_end.get("source")), None)
                elif field_name in {"tch_ft", "vgsi_glide_angle_deg"}:
                    selected = next((option for option in options if option.source == nasr_end.get("source")), None)
                    selected = selected or next((option for option in options if option.source == chart.get("source")), None)
                    selected = selected or next((option for option in options
                                                  if option.source in {v.get("source") for v in effective["vgsi"]}), None)
                elif field_name == "runway_gradient":
                    selected = next((option for option in options if option.source == chart.get("source")), None)
                    selected = selected or (options[0] if options else None)
                elif field_name == "apt_traffic_pattern_for_end":
                    selected = options[0] if options else None
                elif field_name == "nasr_right_hand_traffic":
                    selected = options[0] if options else None
                elif field_name == "chart_right_hand_traffic":
                    selected = options[0] if options else None
                elif field_name == "gs_angle_deg":
                    selected = next((option for option in options if option.value is not None), None)
                    if selected is None and options:
                        selected = options[0]
                else:
                    selected = options[0] if options else None
                fields[field_name] = selected or _source_value(None, None)

            # Combined traffic-pattern value preserves conditional rows rather
            # than collapsing an airport's flows to one runway-end side.
            pattern_items: list[dict[str, Any]] = []
            for option in candidates["apt_traffic_pattern_for_end"]:
                pattern_items.append({"value": option.value,
                                      "provenance": {"source": option.source,
                                                     "confidence": option.confidence,
                                                     "detail": option.detail}})
            for candidate in candidates["nasr_right_hand_traffic"] + candidates["chart_right_hand_traffic"]:
                pattern_items.append({"value": "right" if candidate.value else "left",
                                      "provenance": {"source": candidate.source,
                                                     "confidence": candidate.confidence,
                                                     "detail": candidate.detail}})
            fields["traffic_pattern"] = _source_value(
                pattern_items, "per-source traffic pattern entries" if pattern_items else None,
                "low" if any(item["provenance"]["confidence"] == "low" for item in pattern_items)
                else "high")
            fields["glide_angle_deg"] = fields["vgsi_glide_angle_deg"] if \
                fields["vgsi_glide_angle_deg"].value is not None else fields["gs_angle_deg"]

            displacement = fields["displaced_threshold_m"].value or 0.0
            legacy_displacement = _LEGACY_DISPLACEMENT_OVERRIDES.get(
                f"{icao} {end_id}", displacement)
            # The current RunwayGeometry constructor adds 25 ft to its input.
            # KCRQ's historic input is a 305 m stand-in, so the resulting
            # legacy aim point is 312.62 m, matching the in-tree table exactly.
            legacy_aimpoint = legacy_displacement + 25.0 * FT_TO_M
            fields["legacy_displaced_threshold_m"] = _source_value(
                legacy_displacement, "legacy landing-table compatibility rule", "medium",
                "KCRQ 24 stores its historic 305 m target in the legacy displacement slot")
            fields["legacy_aim_point_m"] = _source_value(
                legacy_aimpoint, "legacy landing-table compatibility rule", "medium",
                "Uses historic displacement input (KCRQ 24: 305 m) plus the constructor's 25 ft offset")
            fields["legacy_aim_point"] = _source_value(True,
                "legacy landing-table compatibility rule", "high")
            tch, angle = fields["tch_ft"].value, fields["glide_angle_deg"].value
            proposed = None
            if tch is not None and angle is not None and 0 < angle < 90:
                proposed = displacement + tch * FT_TO_M / math.tan(math.radians(angle))
            fields["aim_point_proposed_tch_m"] = _source_value(
                proposed, "derived from published TCH and VGSI/GS angle" if proposed is not None else None,
                "medium" if proposed is not None else "low",
                "reported only; no TCH rule is selected by default")

            # Source listings and disagreements are retained per field. Missing
            # sources stay visible even where another source supplies a value.
            source_values: dict[str, list[dict[str, Any]]] = {}
            disagreements: dict[str, list[dict[str, Any]]] = {}
            missing: list[str] = []
            for field_name, options in candidates.items():
                serialized = [option.to_dict() | {"source": option.source} for option in options]
                source_values[field_name] = serialized
                if _numbers_differ([{"value": option.value} for option in options], field_name):
                    disagreements[field_name] = serialized
                if not any(option.value is not None for option in options):
                    missing.append(field_name)
            traffic_sources: dict[str, list[dict[str, Any]]] = {}
            for item in pattern_items:
                source = item["provenance"]["source"] or "unknown"
                traffic_sources.setdefault(source, []).append(item)
            source_values["traffic_pattern"] = pattern_items
            side_sets = {source: {item["value"] if isinstance(item["value"], str)
                                  else item["value"].get("side")
                                  for item in items}
                         for source, items in traffic_sources.items()}
            if len(side_sets) > 1:
                sides = [side for side_set in side_sets.values() for side in side_set if side]
                if len(set(sides)) > 1:
                    disagreements["traffic_pattern"] = pattern_items
            if not pattern_items:
                missing.append("traffic_pattern")
            if fields["aim_point_proposed_tch_m"].value is None:
                missing.append("aim_point_proposed_tch_m")
            runway_ends.append(RunwayEndRecord(icao, end_id, f"{icao} {end_id}", fields,
                                               source_values, disagreements, missing))

        report = {
            "airport_fields": {
                "sources": airport_sources,
                "disagreements": airport_disagreements,
                "missing": [name for name, field_value in airport_fields.items()
                            if field_value.value is None],
            },
            "runway_end_count": len(runway_ends),
            "runway_ends": [{
                "runway_end": end.runway_end,
                "field_sources": {name: value.to_dict()["provenance"]
                                  for name, value in end.fields.items()},
                "source_values": end.source_values,
                "disagreements": end.disagreements,
                "missing": end.missing,
            } for end in runway_ends],
            "aim_point_comparison": [{
                "runway_end": end.runway_end,
                "default_mode": "legacy",
                "legacy_aim_point_m": end.fields["legacy_aim_point_m"].to_dict(),
                "proposed_tch_aim_point_m": end.fields["aim_point_proposed_tch_m"].to_dict(),
            } for end in runway_ends],
            "apt_sources_in_precedence_order": [version["source"] for version in apt_versions],
            "apt_sources_compared_without_precedence": [version["source"]
                                                         for version in comparison_versions],
            "notes": [
                "apt.dat sources are ordered base-to-overlay; the last airport block wins geometry.",
                "Comparison-only apt.dat sources are reported as alternatives and never override the configured base/overlay geometry.",
                "Chart Supplement free text is untrusted and any parsed values are low confidence.",
                "earth_nav GS angle uses the NAV1200 combined-angle/course encoding; raw value and decoded course are retained for audit.",
            ],
        }
        return AirportRecord(icao, name, airport_fields, runway_ends, report)


def _matched_vgsi(end: dict[str, Any], far_end: dict[str, Any], vgsi_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    threshold = tuple(end["threshold"])
    heading = _bearing_deg(threshold, tuple(far_end["threshold"]))
    scored = []
    for row in vgsi_rows:
        position = tuple(row["position"])
        distance = _distance_m(threshold, position)
        orientation_error = _angle_difference(row["orientation_deg"], heading)
        if distance <= 2500 and orientation_error <= 35:
            scored.append((distance + orientation_error * 20, row))
    if not scored:
        return []
    scored.sort(key=lambda item: item[0])
    best = scored[0][0]
    return [row for score, row in scored if score <= best + 25]


def build_airport_record(icao: str, **builder_options: Any) -> dict[str, Any]:
    """Convenience API returning a JSON-serializable record dictionary."""
    return AirportRecordBuilder(**builder_options).build(icao).to_dict()
