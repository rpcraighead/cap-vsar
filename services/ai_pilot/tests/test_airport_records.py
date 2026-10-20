"""Synthetic, offline tests for the airport-record builder and runway conversion."""

import csv
import json
import math
from pathlib import Path

import pytest

from services.ai_pilot.airports.builder import AirportRecordBuilder
from xplane.capvsar_landing import RUNWAYS, RunwayGeometry, tch_aim_point_m


PINNED = {
    "KMYF": ("28R", (32.8128249, -117.1311307), (32.8181752, -117.1447205), 424., 366., 46.02),
    "KSAN": ("27", (32.73136873, -117.18062185), (32.73659395, -117.20217254), 17., 552., 61.02),
    "KSEE": ("27R", (32.8263994, -116.9642836), (32.8294697, -116.9812827), 388., 215., 29.87),
    "KCRQ": ("24", (33.1295232, -117.2722025), (33.1269806, -117.2879522), 331., 0., 45.72),
}


def _apt_row(width, end1, lat1, lon1, disp1, end2, lat2, lon2, disp2):
    return (f"100 {width} 1 0 0.00 0 2 0 {end1} {lat1} {lon1} {disp1} 0 1 0 0 0 "
            f"{end2} {lat2} {lon2} {disp2} 0 1 0 0 0")


def _make_fixture(tmp_path):
    apt_rows = ["I", "1200 Version - synthetic test fixture"]
    for icao, (end, threshold, far_end, elevation, displacement, width) in PINNED.items():
        pair = {"KMYF": ("10L", "28R"), "KSAN": ("09", "27"),
                "KSEE": ("09L", "27R"), "KCRQ": ("06", "24")}[icao]
        apt_rows.extend([f"1 {elevation} 0 0 {icao} Synthetic {icao}",
                         _apt_row(width, pair[0], far_end[0], far_end[1], 0,
                                  pair[1], threshold[0], threshold[1], displacement)])
        apt_rows.append("21 33.1285171 -117.2755312 2 258.8 3.20")
        apt_rows.append("1051 118600 CTAF")
        apt_rows.extend(["1000 Calm flow", f"1101 {end} right"])
    apt = tmp_path / "apt.dat"
    apt.write_text("\n".join(apt_rows) + "\n", encoding="utf-8")

    cifp = tmp_path / "CIFP"
    cifp.mkdir()
    for icao, (end, threshold, _far, elevation, displacement, _width) in PINNED.items():
        feet = round(displacement / 0.3048)
        # ARINC coordinate text uses DDMMSS.hh / DDDMMSS.hh.
        lat = "N" + _dms(threshold[0], 2)
        lon = "W" + _dms(abs(threshold[1]), 3)
        (cifp / f"{icao}.dat").write_text(
            f"RWY:RW{end} ,     ,      ,{int(elevation):05d}, ,    , ,   ;{lat},{lon},{feet:04d};\n",
            encoding="utf-8")

    nasr = tmp_path / "nasr"
    nasr.mkdir()
    _write_csv(nasr / "APT_BASE.csv", ["ARPT_ID", "ICAO_ID", "ARPT_NAME", "ELEV", "TPA"], [
        {"ARPT_ID": icao[1:], "ICAO_ID": icao, "ARPT_NAME": f"FAA {icao}", "ELEV": elev, "TPA": ""}
        for icao, (_end, _threshold, _far, elev, _disp, _width) in PINNED.items()
    ])
    _write_csv(nasr / "APT_RWY.csv", ["ARPT_ID", "RWY_ID", "RWY_WIDTH"], [
        {"ARPT_ID": icao[1:], "RWY_ID": pair[0] + "/" + pair[1],
         "RWY_WIDTH": round(width / .3048)}
        for icao, (_end, _threshold, _far, _elev, _disp, width) in PINNED.items()
        for pair in (({"KMYF": ("10L", "28R"), "KSAN": ("09", "27"),
                       "KSEE": ("09L", "27R"), "KCRQ": ("06", "24")}[icao],))
    ])
    # Row fields not relevant to these geometry checks are omitted safely by
    # DictReader; this also exercises robust handling of sparse offline extracts.
    _write_csv(nasr / "APT_RWY_END.csv", ["ARPT_ID", "RWY_ID", "RWY_END_ID", "LAT_DECIMAL",
                                          "LONG_DECIMAL", "RWY_END_ELEV", "THR_CROSSING_HGT",
                                          "VISUAL_GLIDE_PATH_ANGLE", "DISPLACED_THR_LEN",
                                          "RIGHT_HAND_TRAFFIC_PAT_FLAG"], [
        {"ARPT_ID": icao[1:], "RWY_ID": "x", "RWY_END_ID": end,
         "LAT_DECIMAL": threshold[0], "LONG_DECIMAL": threshold[1],
         "RWY_END_ELEV": elev, "THR_CROSSING_HGT": tch,
         "VISUAL_GLIDE_PATH_ANGLE": angle,
         "DISPLACED_THR_LEN": round(displacement / .3048),
         "RIGHT_HAND_TRAFFIC_PAT_FLAG": "Y"}
        for icao, (end, threshold, _far, elev, displacement, _width), tch, angle in zip(
            PINNED, PINNED.values(), (41, 66, 45, 54), (3, 3.5, 4.5, 3.2))
    ])
    return apt, cifp, nasr


def _dms(value, degree_digits):
    degrees = int(value)
    minutes_total = (value - degrees) * 60
    minutes = int(minutes_total)
    seconds_hundredths = round((minutes_total - minutes) * 60 * 100)
    if seconds_hundredths >= 6000:
        minutes += 1
        seconds_hundredths = 0
    return f"{degrees:0{degree_digits}d}{minutes:02d}{seconds_hundredths:04d}"


def _write_csv(path, headers, rows):
    with path.open("w", newline="", encoding="latin1") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _find_end(record, runway_end):
    return next(item for item in record["runway_ends"] if item["runway_end"] == runway_end)


def test_builder_geometry_reproduces_all_four_pinned_table_entries(tmp_path):
    apt, cifp, nasr = _make_fixture(tmp_path)
    builder = AirportRecordBuilder(apt_paths=[apt], cifp_dir=cifp, nasr_dir=nasr,
                                   earth_nav_path=tmp_path / "earth_nav.dat",
                                   chart_supplement=tmp_path / "missing-chart.txt")
    for icao, (end, threshold, far_end, elevation, displacement, width) in PINNED.items():
        record = builder.build(icao).to_dict()
        runway_record = _find_end(record, end)
        geometry = RunwayGeometry.from_record(runway_record)
        pinned = RUNWAYS[f"{icao} {end}"]
        assert _distance(geometry.threshold, pinned.threshold) < 1.0
        assert _distance(geometry.far_end, pinned.far_end) < 1.0
        assert geometry.airport_elev_ft == pinned.airport_elev_ft == elevation
        legacy_displacement = 305.0 if icao == "KCRQ" else displacement
        assert geometry.displaced_threshold_m == pinned.displaced_threshold_m == legacy_displacement
        assert geometry.physical_displaced_threshold_m == displacement
        assert geometry.width_m == pinned.width_m == width
        assert geometry.aimpoint_m == pinned.aimpoint_m
        assert geometry.legacy_aim_point is True
        assert runway_record["fields"]["threshold"]["provenance"]["source"] == str(apt)
        assert runway_record["fields"]["blast_pad_m"]["value"] == 0
        assert runway_record["fields"]["blast_pad_m"]["provenance"]["source"] == str(apt)
        assert runway_record["fields"]["markings_code"]["value"] == "1"
        assert runway_record["fields"]["approach_lights_code"]["value"] == "0"
        assert runway_record["fields"]["tdz_lights_code"]["value"] == "0"
        assert runway_record["fields"]["reil_code"]["value"] == "0"
        assert "source_values" in runway_record and "disagreements" in runway_record
        # TCH aim is computed for comparison, but conversion defaults to legacy.
        assert runway_record["fields"]["aim_point_proposed_tch_m"]["value"] is not None
        assert geometry.aimpoint_m != runway_record["fields"]["aim_point_proposed_tch_m"]["value"]
        comparison = next(item for item in record["validation_report"]["aim_point_comparison"]
                          if item["runway_end"] == end)
        assert comparison["default_mode"] == "legacy"
        assert comparison["legacy_aim_point_m"]["value"] == geometry.aimpoint_m
        assert comparison["proposed_tch_aim_point_m"]["value"] == \
            runway_record["fields"]["aim_point_proposed_tch_m"]["value"]


def _distance(a, b):
    north = (a[0] - b[0]) * 111132.92
    east = (a[1] - b[1]) * 111412.84 * math.cos(math.radians(a[0]))
    return math.hypot(north, east)


def test_tch_rule_is_explicit_and_validated(tmp_path):
    apt, cifp, nasr = _make_fixture(tmp_path)
    builder = AirportRecordBuilder(apt_paths=[apt], cifp_dir=cifp, nasr_dir=nasr,
                                   earth_nav_path=tmp_path / "none",
                                   chart_supplement=tmp_path / "none.txt")
    entry = _find_end(builder.build("KCRQ").to_dict(), "24")
    legacy = RunwayGeometry.from_record(entry)
    proposed = RunwayGeometry.from_record(entry, aim_point_mode="tch")
    assert legacy.aimpoint_m == 312.62
    assert proposed.aimpoint_m == pytest.approx(tch_aim_point_m(0., 54., 3.2))
    with pytest.raises(ValueError, match="aim_point_mode"):
        RunwayGeometry.from_record(entry, aim_point_mode="automatic")
    with pytest.raises(ValueError, match="glide angle"):
        tch_aim_point_m(0, 54, 0)


def test_apt_streaming_keeps_flow_frequencies_and_overlay_conflicts(tmp_path):
    base = tmp_path / "base.dat"
    overlay = tmp_path / "overlay.dat"
    base.write_text("\n".join([
        "I", "1200 test", "1 20 0 0 KAAA Base", _apt_row(30, "09", 1, 2, 0, "27", 1.1, 2.1, 0),
        "1051 118600 CTAF", "1000 Calm", "1101 27 left", "1 50 0 0 KBBB Ignore",
        _apt_row(50, "01", 3, 4, 0, "19", 3.1, 4.1, 0), "",
    ]), encoding="utf-8")
    overlay.write_text("\n".join([
        "I", "1200 overlay", "1 21 0 0 KAAA Overlay",
        _apt_row(31, "09", 1, 2, 0, "27", 1.1, 2.1, 0),
        "1051 119000 CTAF", "1000 Overlay flow", "1101 27 right", "",
    ]), encoding="utf-8")
    record = AirportRecordBuilder(apt_paths=[base, overlay], cifp_dir=tmp_path,
                                  earth_nav_path=tmp_path / "none", nasr_dir=tmp_path / "none",
                                  chart_supplement=tmp_path / "none").build("KAAA").to_dict()
    end = _find_end(record, "27")
    assert end["fields"]["airport_elevation_ft"]["value"] == 21
    assert end["fields"]["width_m"]["value"] == 31
    assert len(record["fields"]["frequencies"]["value"]) == 2
    assert len(record["fields"]["traffic_flows"]["value"]) == 2
    assert "width_m" in end["disagreements"]
    assert record["validation_report"]["apt_sources_in_precedence_order"] == [str(base), str(overlay)]


def test_cifp_and_chart_text_are_sourced_and_chart_values_low_confidence(tmp_path):
    apt = tmp_path / "apt.dat"
    apt.write_text("\n".join(["I", "1200 fixture", "1 100 0 0 KAAA Test",
        _apt_row(30, "09", 32.0, -117.0, 0, "27", 32.01, -117.01, 0), ""]), encoding="utf-8")
    cifp = tmp_path / "CIFP"
    cifp.mkdir()
    (cifp / "KAAA.dat").write_text(
        "RWY:RW27 ,     ,      ,00102, ,    , ,   ;N32003600,W117003600,0000;\n",
        encoding="utf-8")
    chart = tmp_path / "chart.txt"
    chart.write_text("TEST (AAA)(KAAA)\n 100 B TPA—See Remarks\n"
        " RWY 09–27: H3000X100 (ASPH)\n"
        "   RWY 27: PAPI(P4L)—GA 3.2º TCH 54´. Thld dsplcd 297´. Rgt tfc.\n"
        " AIRPORT REMARKS: TPA—1503(1172) small acft.\n\nNEXT (BBB)(KBBB)\n",
        encoding="utf-8")
    result = AirportRecordBuilder(apt_paths=[apt], cifp_dir=cifp,
        earth_nav_path=tmp_path / "none", nasr_dir=tmp_path / "none",
        chart_supplement=chart).build("KAAA").to_dict()
    end = _find_end(result, "27")
    assert end["fields"]["threshold_elevation_ft"]["value"] == 102
    assert end["fields"]["tch_ft"]["value"] == 54
    assert end["fields"]["vgsi_glide_angle_deg"]["value"] == pytest.approx(3.2)
    assert end["fields"]["chart_right_hand_traffic"]["value"] is True
    assert end["fields"]["chart_right_hand_traffic"]["provenance"]["confidence"] == "low"
    assert result["fields"]["remarks"]["value"]
    json.dumps(result)


def test_apt_missing_right_pattern_is_distinguished_from_other_flow_assignment(tmp_path):
    apt, cifp, nasr = _make_fixture(tmp_path)
    # Keep only the KMYF airport's 05-left flow. NASR fixture independently says
    # 28R is right traffic, so the report must not mistake omission for agreement.
    original = apt.read_text(encoding="utf-8").splitlines()
    filtered = []
    in_kmyf = False
    for line in original:
        if line.startswith("1 "):
            in_kmyf = " KMYF " in line
        filtered.append(line)
        if in_kmyf and line.startswith("1101 "):
            filtered[-1] = "1101 05 left"
    apt.write_text("\n".join(filtered) + "\n", encoding="utf-8")
    result = AirportRecordBuilder(apt_paths=[apt], cifp_dir=cifp, nasr_dir=nasr,
                                  earth_nav_path=tmp_path / "none",
                                  chart_supplement=tmp_path / "none").build("KMYF").to_dict()
    end = _find_end(result, "28R")
    assert end["fields"]["apt_traffic_pattern_for_end"]["value"] is None
    assert end["fields"]["nasr_right_hand_traffic"]["value"] is True
    assert "apt_traffic_pattern_for_end" in end["missing"]


def test_earth_nav_gs_combined_field_is_decoded_and_retained(tmp_path):
    apt = tmp_path / "apt.dat"
    apt.write_text("\n".join(["I", "1200 fixture", "1 100 0 0 KAAA Test",
        _apt_row(30, "09", 32.0, -117.0, 0, "27", 32.01, -117.01, 0), ""]), encoding="utf-8")
    nav = tmp_path / "earth_nav.dat"
    nav.write_text("6 32.0100 -117.0100 100 10870 18 320259.087 IAAA KAAA K2 27 GS\n",
                   encoding="utf-8")
    result = AirportRecordBuilder(apt_paths=[apt], cifp_dir=tmp_path,
        earth_nav_path=nav, nasr_dir=tmp_path / "none",
        chart_supplement=tmp_path / "none.txt").build("KAAA").to_dict()
    end = _find_end(result, "27")
    gs_field = end["fields"]["gs_angle_deg"]
    assert gs_field["value"] == pytest.approx(3.2)
    assert gs_field["provenance"]["source"] == str(nav)
    assert "320259.087" in gs_field["provenance"]["detail"]
    assert "decoded true course 259." in gs_field["provenance"]["detail"]
    assert "gs_angle_deg" not in end["missing"]


def test_builder_accepts_non_us_icao_airport_code(tmp_path):
    apt = tmp_path / "apt.dat"
    apt.write_text("\n".join([
        "I", "1200 fixture", "1 55 0 0 EGAA Belfast International",
        _apt_row(45, "07", 54.65, -6.22, 0, "25", 54.65, -6.18, 0), "",
    ]), encoding="utf-8")
    record = AirportRecordBuilder(
        apt_paths=[apt], cifp_dir=tmp_path,
        earth_nav_path=tmp_path / "none", nasr_dir=tmp_path / "none",
        chart_supplement=tmp_path / "none.txt").build("EGAA").to_dict()
    assert record["icao"] == "EGAA"
    assert _find_end(record, "07")["fields"]["threshold"]["value"] == [54.65, -6.22]

