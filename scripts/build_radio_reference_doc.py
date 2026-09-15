#!/usr/bin/env python3
"""Build the comprehensive Word (.docx) and Markdown (.md) reference document
for all CAP V-SAR radio models, features, technical specifications, and
operational use cases.
"""

from __future__ import annotations

import os
from pathlib import Path
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"

# D-5: this document used to embed page extracts from the Becker, RHOTHETA,
# Technisonic and Garmin manuals. Those are third-party copyrighted pages and
# this document is meant to be handed to squadron members, so the figures now
# come from our own redrawn faceplates under instruments/*/resources/ - the
# same artwork the simulated instruments render, produced by
# scripts/make_df_artwork.py and scripts/make_panel_artwork.py. Do not point
# these back at docs/figures/*_pNN_*.png.
OUT_DOCX = DOCS_DIR / "CAP_V-SAR_Radio_Features_and_Use_Cases.docx"
OUT_MD = DOCS_DIR / "RADIO_FEATURES_AND_USE_CASES.md"

# Color Palette (Civil Air Patrol & Modern Technical Standard)
COLOR_NAVY = RGBColor(11, 37, 69)      # Primary #0B2545
COLOR_STEEL = RGBColor(19, 64, 116)    # Secondary #134074
COLOR_GOLD = RGBColor(197, 155, 39)    # Accent Gold #C59B27
COLOR_TEXT = RGBColor(29, 42, 68)      # Body Text #1D2A44
COLOR_MUTED = RGBColor(100, 116, 139)  # Slate Muted #64748B
COLOR_WHITE = RGBColor(255, 255, 255)
HEX_NAVY = "0B2545"
HEX_LIGHT_BG = "F4F6F9"
HEX_ALT_ROW = "F8F9FA"
HEX_BORDER = "CBD5E1"
HEX_GOLD = "C59B27"


def set_cell_background(cell, hex_color: str):
    """Set background color of a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)


def set_cell_margins(cell, top=120, bottom=120, left=160, right=160):
    """Set inner padding for table cell in dxa (1 pt = 20 dxa)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)


def add_callout(doc: Document, title: str, text: str, alert_type="info"):
    """Insert a styled callout box with a colored left accent border."""
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.columns[0].width = Inches(6.5)

    cell = table.cell(0, 0)
    border_hex = HEX_GOLD if alert_type in ("warning", "trap") else HEX_NAVY
    set_cell_background(cell, HEX_LIGHT_BG)
    set_cell_margins(cell, top=140, bottom=140, left=200, right=180)

    # Set left border thick, clear others
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:top w:val="none"/>'
        f'<w:left w:val="single" w:sz="36" w:space="0" w:color="{border_hex}"/>'
        f'<w:bottom w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(tcBorders)

    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.15

    r_title = p.add_run(f"[{title.upper()}]\n")
    r_title.bold = True
    r_title.font.size = Pt(10)
    r_title.font.color.rgb = COLOR_GOLD if alert_type in ("warning", "trap") else COLOR_NAVY

    r_text = p.add_run(text)
    r_text.font.size = Pt(10)
    r_text.font.color.rgb = COLOR_TEXT

    # Spacer after callout
    p_space = doc.add_paragraph()
    p_space.paragraph_format.space_before = Pt(0)
    p_space.paragraph_format.space_after = Pt(4)


def add_styled_table(doc: Document, headers: list[str], rows: list[list[str]], col_widths: list[float] | None = None):
    """Add a professionally styled data table."""
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    # Header Row
    hdr_cells = table.rows[0].cells
    for i, title in enumerate(headers):
        cell = hdr_cells[i]
        set_cell_background(cell, HEX_NAVY)
        set_cell_margins(cell, top=140, bottom=140, left=140, right=140)
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(title)
        run.bold = True
        run.font.size = Pt(9.5)
        run.font.color.rgb = COLOR_WHITE

    # Data Rows
    for r_idx, row_data in enumerate(rows):
        row_cells = table.rows[r_idx + 1].cells
        bg_hex = HEX_ALT_ROW if (r_idx % 2 == 1) else "FFFFFF"
        for c_idx, val in enumerate(row_data):
            cell = row_cells[c_idx]
            set_cell_background(cell, bg_hex)
            set_cell_margins(cell, top=100, bottom=100, left=140, right=140)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.15
            run = p.add_run(str(val))
            run.font.size = Pt(9)
            run.font.color.rgb = COLOR_TEXT

    # Apply Borders
    tblPr = table._tbl.tblPr
    tblBorders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="6" w:space="0" w:color="{HEX_BORDER}"/>'
        f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="{HEX_BORDER}"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{HEX_BORDER}"/>'
        f'<w:insideV w:val="none"/>'
        f'<w:left w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(tblBorders)

    # Column Widths
    if col_widths:
        for row in table.rows:
            for idx, w in enumerate(col_widths):
                row.cells[idx].width = Inches(w)

    p_space = doc.add_paragraph()
    p_space.paragraph_format.space_before = Pt(0)
    p_space.paragraph_format.space_after = Pt(6)


def add_image_with_caption(doc: Document, image_path: Path, caption: str, width_inches=5.8):
    """Embed an image with a centered caption."""
    if not image_path.exists():
        return
    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_img.paragraph_format.space_before = Pt(6)
    p_img.paragraph_format.space_after = Pt(2)
    run_img = p_img.add_run()
    run_img.add_picture(str(image_path), width=Inches(width_inches))

    p_cap = doc.add_paragraph()
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_cap.paragraph_format.space_before = Pt(2)
    p_cap.paragraph_format.space_after = Pt(8)
    run_cap = p_cap.add_run(caption)
    run_cap.italic = True
    run_cap.font.size = Pt(8.5)
    run_cap.font.color.rgb = COLOR_MUTED


def build_documents():
    print("[*] Generating Word (.docx) document...")
    doc = Document()

    # Configure Margins (1 inch all around)
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        section.different_first_page_header_footer = True

        # Header (Pages 2+)
        hdr = section.header
        p_hdr = hdr.paragraphs[0]
        p_hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r_hdr = p_hdr.add_run("CIVIL AIR PATROL V-SAR • RADIO SYSTEMS REFERENCE")
        r_hdr.font.size = Pt(8)
        r_hdr.font.color.rgb = COLOR_MUTED

        # Footer (Pages 2+)
        ftr = section.footer
        p_ftr = ftr.paragraphs[0]
        p_ftr.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_ftr = p_ftr.add_run("CAP V-SAR Research & Simulation Project • Operational Reference Manual")
        r_ftr.font.size = Pt(8)
        r_ftr.font.color.rgb = COLOR_MUTED

    # Document Styles
    styles = doc.styles
    normal_style = styles["Normal"]
    normal_style.font.name = "Calibri"
    normal_style.font.size = Pt(10.5)
    normal_style.font.color.rgb = COLOR_TEXT
    normal_style.paragraph_format.line_spacing = 1.15
    normal_style.paragraph_format.space_after = Pt(6)

    # -------------------------------------------------------------
    # TITLE & METADATA BLOCK
    # -------------------------------------------------------------
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(12)
    p_title.paragraph_format.space_after = Pt(2)
    r_title = p_title.add_run("Civil Air Patrol V-SAR\nAirborne & Ground Radio Systems")
    r_title.bold = True
    r_title.font.size = Pt(24)
    r_title.font.color.rgb = COLOR_NAVY

    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_before = Pt(2)
    p_sub.paragraph_format.space_after = Pt(12)
    r_sub = p_sub.add_run("Technical Feature Specifications, Cockpit Avionics & Operational Use Cases")
    r_sub.font.size = Pt(13)
    r_sub.font.color.rgb = COLOR_STEEL

    # Metadata Strip
    p_meta = doc.add_paragraph()
    p_meta.paragraph_format.space_after = Pt(14)
    r_meta = p_meta.add_run(
        "Authority: CAPR 100-1, CAPR 100-3, MART Vol. II, ICUT Syllabus | Version: 2.4 | Status: Operational"
    )
    r_meta.italic = True
    r_meta.font.size = Pt(9)
    r_meta.font.color.rgb = COLOR_MUTED

    add_image_with_caption(
        doc,
        DOCS_DIR / "figures/manual/fig_c182t_aircraft.png",
        "Figure 1: Civil Air Patrol Cessna 182T NAV III Airborne Direction Finding & Tactical Communications Platform.",
        width_inches=5.8,
    )

    # -------------------------------------------------------------
    # SECTION 1: EXECUTIVE OVERVIEW & DOCTRINAL FOUNDATION
    # -------------------------------------------------------------
    h1 = doc.add_heading("1. Executive Overview & Regulatory Doctrine", level=1)
    h1.style.font.color.rgb = COLOR_NAVY

    doc.add_paragraph(
        "The Civil Air Patrol Virtual Search and Rescue (CAP V-SAR) simulation platform provides a "
        "high-fidelity training environment for search-and-rescue aircrews, flight line personnel, and ground "
        "incident command teams. Realistic communications fidelity is central to the training value of the platform: "
        "direction-finding physics, radio propagation degradation, audio panel interlocks, and authentic fleet "
        "codeplugs prepare crews for actual emergency services sorties."
    )

    doc.add_paragraph(
        "All simulated radio equipment, audio routing mechanisms, and user controls are engineered to reflect the "
        "strict operational, technical, and radiotelephone doctrine defined by official Civil Air Patrol publications "
        "and equipment manufacturer operating handbooks:"
    )

    doc.add_paragraph(
        "• CAPR 100-1 (Radio Communications Policy): Governs national and wing frequency allocations, standard fleet "
        "codeplugs, communications plans, and formal station recordkeeping requirements.\n"
        "• CAPR 100-3 (Radiotelephone Procedures): Regulates formal communications discipline, prohibited practices "
        "(including 10-codes), mandatory prowords (ROGER, OVER, OUT, WAIT, SAY AGAIN), and aircraft phonetics.\n"
        "• CAP Pamphlet 100-3 & CAP Form 110: Standard radio communications guide and the mandatory continuous "
        "radio log maintained by Mission Radio Operators (MRO) during operational exercises.\n"
        "• CAP Introductory Communications User Training (ICUT): Outlines foundational user competency across base, "
        "mobile, and airborne stations, including stuck-mic recognition and transmitter time-out limits.\n"
        "• CAP Mission Aircrew Reference Text (MART) Vol. II: Specific technical and procedural guide for Mission "
        "Observers (MO) and SAR Mission Pilots (MP) operating airborne direction finders and VHF-FM tactical transceivers.\n"
        "• Manufacturer Technical Manuals: Technisonic TDFM-136B (TiL 08RE399A), Garmin GMA 1347 Pilot's Guide "
        "(190-00378-01), Becker SAR-DF 517 DCU Manual, RHOTHETA RT-600 Manual, and Motorola APX 4500 User Guide."
    )

    add_callout(
        doc,
        "Doctrinal Requirement: Radiotelephone Discipline",
        "Under CAPR 100-3 §1-3, Civil Air Patrol stations operate in compliance with federal standards (NTIA/FAA). "
        "Amateur jargon and '10-codes' are strictly prohibited on all CAP nets. Standard military/civilian prowords, "
        "ITU phonetics, 24-hour UTC (Zulu) time, and clear-text tactical brevity codes are mandatory.",
        alert_type="info",
    )

    # -------------------------------------------------------------
    # SECTION 2: AIRBORNE RADIO SYSTEMS & HARDWARE SPECIFICATIONS
    # -------------------------------------------------------------
    h1 = doc.add_heading("2. Airborne Radio Systems & Cockpit Specifications", level=1)
    h1.style.font.color.rgb = COLOR_NAVY

    doc.add_paragraph(
        "The simulated Cessna 182T NAV III (Garmin G1000) cockpit features a fully integrated Mission Observer "
        "avionics console. The observer station accommodates tactical mission communications, inter-crew intercom "
        "isolation, and electronic search direction finding."
    )

    # 2.1 TDFM-136B
    h2 = doc.add_heading("2.1 Technisonic TDFM-136B VHF-FM Tactical Airborne Transceiver", level=2)
    h2.style.font.color.rgb = COLOR_STEEL

    doc.add_paragraph(
        "The Technisonic TDFM-136B is the standard airborne VHF-FM tactical radio deployed across the Civil Air Patrol "
        "Cessna fleet. In CAP V-SAR, the instrument is modeled down to the hardware control panel, internal dual-receiver "
        "pathways, authentic fleet memory plan, and physical transmitter protection timers."
    )

    add_image_with_caption(
        doc,
        ROOT / "instruments/cap-fm-tdfm-136b/resources/faceplate.png",
        "Figure 2: CAP V-SAR rendering of the Technisonic TDFM-136B control head as simulated.",
        width_inches=5.8,
    )

    # TDFM Specs Table
    tdfm_specs = [
        ["Frequency Range", "136.0000 MHz to 174.0000 MHz continuous coverage"],
        ["Channel Spacing", "25.0 kHz (Wideband) and 12.5 kHz (Narrowband)"],
        ["Operating Modes", "Analog FM and APCO Project 25 (P25) Phase 1 Digital Conventional"],
        ["Receiver Architecture", "Dual Independent Receivers: Main Agile Transceiver + Dedicated Guard Receiver"],
        ["Memory Capacity", "200 Programmed User Memories + 30 Dedicated Scan/Guard Channels"],
        ["RF Output Power", "Selectable: HIGH Power (10.0 Watts) or LOW Power (1.0 Watt) via front panel switch"],
        ["CTCSS / NAC Capability", "Full Continuous Tone-Coded Squelch (PL Tones) & P25 Network Access Codes ($293 standard)"],
        ["Transmitter Protection", "Hardware 60-Second Time-Out Timer (TOT) stuck-mic unkey with lockout warning"],
        ["Scanning Engine", "Operational timer-driven state machine: 250 ms dwell, carrier halt, 2000 ms hang time, PTT pause"],
        ["Audio Interface", "Dual rotary concentric volume potentiometers for independent Main and Guard audio mixing"],
    ]
    add_styled_table(doc, ["System Parameter", "Simulated Engineering Specification"], tdfm_specs, [2.2, 4.3])

    doc.add_paragraph(
        "Key TDFM-136B Functional Capabilities in CAP V-SAR:\n"
        "1. Independent Guard Receiver Architecture: In strict accordance with hardware manuals, the TDFM-136B houses "
        "two distinct physical receivers. The Guard receiver continuously monitors GD1 (168.650 MHz AIRGUARD) or GD2 "
        "(121.500 MHz VHF Emergency) in the background. Guard audio mixes continuously with Main audio, allowing mission "
        "base or emergency stations to break into the observer's headset regardless of what channel the Main receiver is working.\n"
        "2. Authentic 200-Channel CAP Fleet Plan: The radio comes pre-loaded with official CAP fleet nomenclature, "
        "frequencies, CTCSS tones, and P25 NACs. Channels include TAC 1 (148.150 MHz), TAC 2 (149.275 MHz), CC 1 (150.225 MHz), "
        "CC 2 (150.525 MHz), AIR 1 (150.550 MHz), AIR 2 (149.525 MHz), SAR 1 (148.475 MHz), and inter-agency channels "
        "(VFIRE 21, VTAC 11, CALCORD). Trainees can dial channels via 3-digit direct numeric entry (e.g. 012 for SAR 1).\n"
        "3. Transmitter Time-Out Timer (TOT): Continuous keying of the transmitter beyond 60 seconds triggers automatic "
        "carrier cutoff, illuminates '*** TIME OUT ***' across the LCD, and locks out the transmitter until the PTT is released.\n"
        "4. Operational Scan Engine: Engaging scan (L1-5) cycles programmed fleet memories on a 250 ms dwell. Squelch opening "
        "(cap_fm_main_rx) instantly freezes the scan; carrier drop initiates a 2000 ms hold timer before scan resumption."
    )

    add_callout(
        doc,
        "Operational Notice: Airborne Repeater Tone Requirement",
        "When operating on tactical repeaters (e.g., CAP Rptr 1 or regional mountain repeaters), transmitting without the "
        "correct CTCSS subaudible access tone (e.g., Tone 8 / 110.9 Hz) will fail to open the repeater receiver. In CAP V-SAR, "
        "the published cap_fm_ctcss_tone variable is verified by backend repeater logic.",
        alert_type="info",
    )

    # 2.2 GMA 1347
    h2 = doc.add_heading("2.2 Garmin GMA 1347 Airborne Audio Panel & Intercom System (ICS)", level=2)
    h2.style.font.color.rgb = COLOR_STEEL

    doc.add_paragraph(
        "The Garmin GMA 1347 handles all cockpit audio routing, microphone switching, and crew intercom isolation for the "
        "Garmin G1000 integrated avionics suite. The simulated Mission Observer station operates a dedicated copilot/observer "
        "audio panel."
    )

    add_image_with_caption(
        doc,
        ROOT / "instruments/mo-audio-panel-gma1347/resources/faceplate.png",
        "Figure 3: CAP V-SAR rendering of the GMA 1347 audio panel as simulated.",
        width_inches=1.8,
    )

    # GMA 1347 Specs Table
    gma_specs = [
        ["Transceiver Inputs", "COM1 (VHF-AM ATC), COM2 (VHF-AM Auxiliary/Air-to-Air), COM3 (CAP Tactical VHF-FM TDFM-136B)"],
        ["Microphone Selection", "Exclusive interlock: Only one COM transmitter can be keyed at a time"],
        ["Audio vs. MIC Interlock", "Independent audio monitoring vs. transmission keying (primary operational error trap)"],
        ["ICS Isolation Modes", "ALL (unrestricted), PILOT (isolated on COM1), COPILOT (isolated), CREW (cockpit isolated from cabin)"],
        ["Split COM Capability", "Pilot locked to COM1; Copilot/MO locked to COM2; Mission Observer isolated from tactical net"],
        ["Digital Clearance Recorder", "16-block circular buffer capturing 2.5 minutes of incoming COM audio with reverse playback"],
        ["Squelch & Volume Modes", "Concentric dual rotary knobs with push-button Manual Squelch (MAN SQ) override"],
        ["Fail-Safe Mode", "Automatic passive analog hard-wire connection linking Pilot headset and PTT directly to COM1 on bus power loss"],
    ]
    add_styled_table(doc, ["Audio Panel Feature", "Operational Implementation"], gma_specs, [2.2, 4.3])

    doc.add_paragraph(
        "Critical GMA 1347 Training Features in CAP V-SAR:\n"
        "• Audio vs. MIC Selection Interlock: Trainees frequently press 'COM3' (audio monitor) and assume they can transmit. "
        "The GMA 1347 enforces authentic hardware behavior: listening requires the COM3 audio key, while transmitting "
        "strictly requires selecting the 'COM3 MIC' key. Transmitting without COM3 MIC produces no RF carrier.\n"
        "• Intercom System (ICS) Isolation: Governed by G1000 Table 6A.3.2. Selecting 'PILOT' isolates the pilot to focus on "
        "air traffic control, while the Mission Observer and scanner continue tactical discussion. Selecting 'CREW' allows the "
        "front-seat aircrew to coordinate search tactics while isolating passengers in the rear cabin.\n"
        "• Split COM Operation: During critical flight regimes (such as entering congested tower airspace while maintaining "
        "a search grid), activating Split COM allows the pilot to work ATC on COM1 while the copilot works air-to-air on COM2. "
        "The tactical mission radio (COM3) is automatically de-asserted from the observer's audio path to prevent distraction.\n"
        "• Digital Clearance Recorder (PLAY): The GMA 1347 continuously digitizes and buffers the last 2.5 minutes of incoming "
        "radio traffic across COM1, COM2, and COM3 into a 16-block memory buffer. Pressing PLAY replays the latest block; "
        "successive presses step backward through historical radio calls. Pressing any other key instantly cancels playback."
    )

    add_callout(
        doc,
        "Classic Mission Observer Pitfall: The COM3 MIC Trap",
        "The single most frequent mistake made by trainee Mission Observers is listening to tactical traffic on COM3 Audio "
        "and attempting to transmit without selecting COM3 MIC. The GMA 1347's amber annunciators clearly distinguish "
        "between audio reception (COM3) and active microphone authorization (COM3 MIC).",
        alert_type="trap",
    )

    # 2.3 Becker SAR-DF 517
    h2 = doc.add_heading("2.3 Becker SAR-DF 517 Airborne Direction Finder", level=2)
    h2.style.font.color.rgb = COLOR_STEEL

    doc.add_paragraph(
        "The Becker SAR-DF 517 is a precision multi-band pseudo-Doppler airborne direction finding system. It computes "
        "real-time relative bearings to analog and digital emergency distress transmitters."
    )

    add_image_with_caption(
        doc,
        ROOT / "instruments/becker-sar-df-517/resources/faceplate.png",
        "Figure 4: CAP V-SAR rendering of the Becker SAR-DF 517 display control unit as simulated.",
        width_inches=5.8,
    )

    # Becker Specs Table
    b517_specs = [
        ["Frequency Coverage", "VHF: 121.500 MHz | UHF: 243.000 MHz | 406 MHz: 4-channel adjustable training suite"],
        ["406 MHz Channels", "Emergency: 406.025 MHz | Training: 406.022 MHz, 406.025 MHz, 406.028 MHz, 406.037 MHz"],
        ["Acoustic Profile", "3 kHz pseudo-Doppler AM tone modulation; tone-suppressed clean analog sweep via STORE key"],
        ["SNR Degradation", "Dynamic receiver discriminator noise mixing inversely against RF signal strength (cap/df/signal)"],
        ["Display Unit", "128x64 LCD dot-matrix with 360° circular bearing needle, numeric bearing, spread, and signal bar"],
        ["Digital Frame Decode", "Decodes 406 MHz COSPAS-SARSAT frames: 15-hex ID, country code, protocol, and coordinates"],
        ["Bearing Averaging", "Multi-sample circular averaging filter producing realistic aircraft course-change drag error"],
        ["Installation Calibration", "Selectable TOP vs. BOTTOM antenna mounting and configurable angular offset correction"],
    ]
    add_styled_table(doc, ["System Feature", "Becker SAR-DF 517 Specification"], b517_specs, [2.2, 4.3])

    doc.add_paragraph(
        "Key Operational Characteristics of the Becker 517:\n"
        "• Pseudo-Doppler AM Modulation: The DF antenna array switches four quarter-wave monopoles at a 3 kHz rotation "
        "rate, phase-modulating the received carrier. In CAP V-SAR, this distinctive 3 kHz warble is synthesized in real time. "
        "Engaging the STORE key activates tone suppression, delivering a clean audio sweep for aural null homing.\n"
        "• Dynamic Signal-to-Noise Ratio (SNR) Hiss: Unlike legacy simulators where audio was either perfect or absent, "
        "CAP V-SAR blends band-limited discriminator hiss (elt_noise.wav) inversely against signal strength. At maximum "
        "distance or behind mountain ridges, the ELT sweep is heavily masked by receiver static.\n"
        "• 406 MHz Channel Limitation: The Becker 517 covers four discrete 406 MHz channels in Training mode (406.022 to "
        "406.037 MHz). It cannot tune channels above 406.037 MHz, representing a major doctrinal training point for aircrews."
    )

    # 2.4 RHOTHETA RT-600
    h2 = doc.add_heading("2.4 RHOTHETA RT-600 Advanced Airborne SAR Direction Finder", level=2)
    h2.style.font.color.rgb = COLOR_STEEL

    doc.add_paragraph(
        "The RHOTHETA RT-600 is the modern advanced direction finding system utilized on newer Civil Air Patrol aircraft. "
        "It provides full-spectrum COSPAS-SARSAT digital tracking and dual-frequency scanning."
    )

    add_image_with_caption(
        doc,
        ROOT / "instruments/rhotheta-rt-600/resources/faceplate.png",
        "Figure 5: CAP V-SAR rendering of the RHOTHETA RT-600 DCU 600 as simulated.",
        width_inches=5.8,
    )

    # RT-600 Specs Table
    rt600_specs = [
        ["Frequency Coverage", "VHF Airband (118–137 MHz), Maritime VHF (156–162 MHz), UHF (243 MHz), 406 MHz COSPAS-SARSAT"],
        ["COSPAS-SARSAT Grid", "Full 19-Channel Grid: 406.022 MHz to 406.076 MHz across 7 CPSAR groups (A through S)"],
        ["Dual-Watch Scanning", "Simultaneously sweeps 406 MHz burst channels while scanning 121.500 MHz and 123.100 MHz"],
        ["Timehold Persistence", "Holds bearing during 50-second 406 burst gap while allowing background receiver scanning"],
        ["Airframe Shadowing", "Attitude-dependent wing null attenuation modeling fuselage and wing shielding (up to 24 dB loss)"],
        ["Digital Protocol Support", "Standard ELT, PLB, EPIRB, Maritime DSC Channel 70 (156.525 MHz), and Test Protocols"],
    ]
    add_styled_table(doc, ["System Feature", "RHOTHETA RT-600 Specification"], rt600_specs, [2.2, 4.3])

    doc.add_paragraph(
        "Key Differences Between Becker 517 and RHOTHETA RT-600:\n"
        "1. 406 MHz Frequency Coverage: The RT-600 spans the entire 19-channel COSPAS-SARSAT international allocation "
        "(406.022 to 406.076 MHz in 3 kHz steps). An exercise with an ELT on 406.040 MHz will be completely silent to a "
        "Becker 517, but readily tracked by an RT-600—teaching crews the importance of knowing their aircraft equipment.\n"
        "2. Multi-Channel CPSAR Sweeping: The RT-600 scans pre-programmed channel pairs or whole CPSAR groups, ensuring that "
        "distress bursts on unknown channels are intercepted during search sweeps.\n"
        "3. Airframe Shadowing & Wing Null Dynamics: High-wing Cessna aircraft exhibit significant RF shielding when the wing "
        "dips between the belly antenna and the beacon. CAP V-SAR models this with 24 dB of peak attenuation, enabling crews "
        "to execute authentic wing-dip ambiguity verification procedures."
    )

    # -------------------------------------------------------------
    # SECTION 3: GROUND STATION RADIO SYSTEMS & MRO SPECIFICATIONS
    # -------------------------------------------------------------
    h1 = doc.add_heading("3. Ground Mission Base Radio Systems & MRO Console", level=1)
    h1.style.font.color.rgb = COLOR_NAVY

    doc.add_paragraph(
        "Ground operations at Mission Base, forward operating bases, and mobile incident command posts are operated by "
        "qualified Mission Radio Operators (MRO). CAP V-SAR models the full ground communications stack, including tactical "
        "transceivers, airband base stations, and doctrinal logging systems."
    )

    # 3.1 Motorola APX & EFJohnson
    h2 = doc.add_heading("3.1 Motorola APX 4500 / APX 6500 & EFJohnson 5300 Tactical Base Radios", level=2)
    h2.style.font.color.rgb = COLOR_STEEL

    doc.add_paragraph(
        "The primary tactical radio at a CAP Mission Base is a high-power VHF-FM mobile or base station, typically a "
        "Motorola APX series (O2 or O5 control head) or EFJohnson 5300 transceiver."
    )

    add_image_with_caption(
        doc,
        DOCS_DIR / "figures/manual/fig_radio_apx.png",
        "Figure 6: Motorola APX Tactical VHF-FM Ground Control Head with CAP Zone/Channel Plan.",
        width_inches=5.2,
    )

    ground_tactical_specs = [
        ["Operating Frequencies", "VHF High-Band: 136.0000 MHz to 174.0000 MHz conventional analog FM & P25 digital"],
        ["Channel Organization", "Multi-Zone Fleet Architecture: Zone 1 (Command/Tactical), Zone 2 (Ground), Zone 3 (Interop)"],
        ["Acoustic Feedback", "Authentic 3-tone P25 talk-permit chirp (941/1336/1209 Hz), channel busy tone, squelch tail"],
        ["Transmit Server Lease", "Server-enforced 60-second transmit timeout gate (TransmitGate) preventing stuck microphones"],
        ["Display & Ergonomics", "High-contrast dot-matrix display, zone/channel name annunciator, signal RSSI meter"],
        ["Monitor Mode (MON)", "Instant squelch override allowing reception of marginal signals from low-altitude aircraft"],
    ]
    add_styled_table(doc, ["Feature", "Ground Tactical Radio Implementation"], ground_tactical_specs, [2.2, 4.3])

    # 3.2 Icom IC-A120
    h2 = doc.add_heading("3.2 Icom IC-A120 VHF Aeronautical Base Station Transceiver", level=2)
    h2.style.font.color.rgb = COLOR_STEEL

    doc.add_paragraph(
        "Under CAP regulations and ICUT doctrine, a Mission Base cannot rely solely on tactical VHF-FM. Base stations must "
        "maintain dedicated VHF-AM aeronautical airband capability to coordinate directly with aircraft on aviation frequencies."
    )

    add_image_with_caption(
        doc,
        DOCS_DIR / "figures/manual/fig_radio_icom.png",
        "Figure 7: Icom IC-A120 Ground Airband VHF-AM Base Station Transceiver.",
        width_inches=5.2,
    )

    icom_specs = [
        ["Frequency Range", "118.000 MHz to 136.992 MHz (VHF-AM aviation airband, 8.33 kHz and 25 kHz channel spacing)"],
        ["Dual-Watch Monitoring", "Simultaneous monitoring of Primary SAR (123.100 MHz) with priority watch on 121.500 MHz"],
        ["Noise Limiter (ANL)", "Automatic Noise Limiter suppressing pulse-type engine and electrical interference"],
        ["Side-Tone Verification", "Internal side-tone allowing operator to monitor outgoing transmission quality on headset"],
        ["Primary CAP Frequencies", "123.100 MHz (National SAR Air-to-Ground), 122.900 MHz (SAR Secondary), 121.500 MHz (Guard)"],
    ]
    add_styled_table(doc, ["System Feature", "Icom IC-A120 Operational Specification"], icom_specs, [2.2, 4.3])

    add_image_with_caption(
        doc,
        DOCS_DIR / "figures/manual/fig_radio_dual.png",
        "Figure 8: Dual-Station Mission Base Console: Motorola APX Tactical VHF-FM & Icom IC-A120 Aeronautical SAR.",
        width_inches=5.5,
    )

    # 3.3 CAP Form 110 Logger
    h2 = doc.add_heading("3.3 CAP Form 110 Radio Communications Log System", level=2)
    h2.style.font.color.rgb = COLOR_STEEL

    doc.add_paragraph(
        "CAPR 100-1 §5-3 mandates that every operational radio station maintain a continuous communications log. "
        "The CAP V-SAR ground console integrates a real-time digital CAP Form 110 logging system."
    )

    add_callout(
        doc,
        "Doctrinal Mandate: The CAP Form 110 Communications Log",
        "The Mission Radio Operator's primary legal and operational duty is maintaining an unbroken record of all radio traffic. "
        "In the event of an aircraft accident, overdue sortie, or lost crew, the Form 110 provides the official evidentiary "
        "record of last-known position, fuel status, and emergency distress messages.",
        alert_type="warning",
    )

    doc.add_paragraph(
        "Core Capabilities of the CAP V-SAR Form 110 Logger:\n"
        "• Automatic Zulu Timestamping: Every log entry captures UTC timestamping synchronized with the exercise clock.\n"
        "• Fast Tactical Shortcut Buttons: One-click logging for standard operational transmissions: 'Ops Normal', "
        "'Radio Check', 'Bearing Report', 'Departing Airport', 'In-Grid', 'Out-of-Grid', and 'Overhead Beacon'.\n"
        "• Aircraft Track Synchronization: Captures reported bearing, coordinates, and altitude directly into the session database.\n"
        "• Persistent Storage & CSV Export: Entries survive console restarts and can be exported as standard CSV records for "
        "the Communications Unit Leader (COML) and Planning Section Chief."
    )

    # -------------------------------------------------------------
    # SECTION 4: OPERATIONAL USE CASES & PROCEDURES
    # -------------------------------------------------------------
    h1 = doc.add_heading("4. Operational Use Cases & Doctrinal Procedures", level=1)
    h1.style.font.color.rgb = COLOR_NAVY

    doc.add_paragraph(
        "The following operational use cases demonstrate how the simulated radio ecosystem is utilized during Civil Air Patrol "
        "search and rescue exercises (SAREX) and disaster relief missions."
    )

    # Use Case 1
    h2 = doc.add_heading("4.1 Use Case 1: Electronic Search & Rescue (ELT / EPIRB Localization)", level=2)
    h2.style.font.color.rgb = COLOR_STEEL

    doc.add_paragraph(
        "Context: An overdue general aviation aircraft has crashed in mountainous terrain. The Air Force Rescue Coordination "
        "Center (AFRCC) alerts Civil Air Patrol to localize the emergency beacon."
    )

    add_callout(
        doc,
        "Operational Procedure: Dual-Antenna DF Search (MART Vol. II Ch. 5)",
        "Step 1: En Route Monitoring. While transiting to the search area at altitude, tune the Becker 517 / RT-600 to "
        "121.500 MHz and 406.025 MHz. Verify audio squelch opens.\n"
        "Step 2: Digital Decode Acquisition. Upon receiving a 406 MHz burst, record the 15-hex beacon ID and country code. "
        "Verify position coordinates if GPS-encoded.\n"
        "Step 3: Signal-to-Noise Ratio (SNR) Assessment. Note the receiver hiss. As the aircraft approaches the beacon, "
        "the 3 kHz pseudo-Doppler sweep clarifies and static subsides.\n"
        "Step 4: Wing-Dip Ambiguity Resolution. If the bearing needle fluctuates due to reflections, bank the aircraft 20° "
        "to drop the wing toward the beacon. The belly antenna is shielded by the wing (wing null loss up to 24 dB), "
        "confirming that the beacon lies on the side of the lowered wing.\n"
        "Step 5: Aural Null / Tone Suppression. Inside 1 NM, the bearing needle will oscillate rapidly. Engage the STORE key "
        "to suppress the 3 kHz Doppler tone, using clean analog receiver volume to execute an aural null overhead confirmation.",
        alert_type="info",
    )

    # Use Case 2
    h2 = doc.add_heading("4.2 Use Case 2: Tactical Air-to-Ground Coordination (Observer to Base)", level=2)
    h2.style.font.color.rgb = COLOR_STEEL

    doc.add_paragraph(
        "Context: The airborne crew coordinates search progress with Mission Base on the tactical VHF-FM mission net."
    )

    doc.add_paragraph(
        "Step-by-Step Procedure:\n"
        "1. Audio Panel Setup: The Mission Observer selects 'COM3' Audio on the GMA 1347 to monitor the net. To talk, the "
        "observer presses 'COM3 MIC', verifying that the amber MIC annunciator illuminates.\n"
        "2. TDFM Channel Selection: Dial channel '001' (TAC 1, 148.150 MHz). Confirm that the LCD renders 'MN  TAC 1'.\n"
        "3. Radio Check: Key the observer PTT. Transmission audio is gated by the 60-second hardware TOT. Base responds: "
        "'CAP-STONE 423, MISSION BASE, READ YOU LOUD AND CLEAR'.\n"
        "4. Routine Ops Normal Check: Every 30 minutes, the crew transmits: 'MISSION BASE, CAP-STONE 423, OPS NORMAL, "
        "GRID 142A, 4500 FEET, REMAINING FUEL 3.5 HOURS'. The MRO clicks 'Ops Normal' on the CAP Form 110 console.\n"
        "5. Guard Receiver Monitoring: While working TAC 1 on Main, the TDFM's secondary Guard receiver continuously listens "
        "on AIRGUARD (168.650 MHz). When Mission Base issues an urgent weather alert on Guard, it mixes into the crew's headset "
        "without requiring the crew to leave TAC 1."
    )

    # Use Case 3
    h2 = doc.add_heading("4.3 Use Case 3: Cockpit Intercom Management & Crew Resource Management", level=2)
    h2.style.font.color.rgb = COLOR_STEEL

    doc.add_paragraph(
        "Context: The search aircraft enters busy class D airspace near the search grid. The pilot must coordinate with "
        "Air Traffic Control while the Mission Observer continues working the tactical search net."
    )

    doc.add_paragraph(
        "Cockpit Execution via GMA 1347:\n"
        "• Pilot Isolation (ICS PILOT): Pressing PILOT isolates the pilot on COM1 (Tower). Intercom chatter from the Mission "
        "Observer and scanner is muted in the pilot's headset, ensuring zero distraction during ATC clearances.\n"
        "• Split COM Activation: Engaging Split COM locks the pilot to COM1 and copilot to COM2, automatically de-asserting "
        "COM3 to prevent tactical radio chatter from bleeding into air-to-air traffic.\n"
        "• Clearance Recorder Recovery: If the pilot misses an ATC altimeter setting or the observer misses a grid reference "
        "read by base, pressing the 'PLAY' key replays the recorded transmission cleanly without requiring a 'SAY AGAIN'."
    )

    # Use Case 4
    h2 = doc.add_heading("4.4 Use Case 4: Mission Radio Operator (MRO) Base Operations & Dual-Watch", level=2)
    h2.style.font.color.rgb = COLOR_STEEL

    doc.add_paragraph(
        "Context: Mission Base manages communications for three airborne search sorties and two ground search teams (UDF)."
    )

    doc.add_paragraph(
        "Ground Station Management:\n"
        "• Dual-Watch Monitoring: The MRO monitors tactical traffic on the Motorola APX 4500 (TAC 1 / 148.150 MHz) while "
        "keeping the Icom IC-A120 unmuted on 123.100 MHz (Aeronautical SAR Air-to-Ground). When an aircraft departs tower airspace, "
        "it reports in on 123.100 MHz; once established in the grid, it shifts to tactical VHF-FM.\n"
        "• Continuous Form 110 Logging: All position reports, fuel checks, and beacon bearings are logged into the digital "
        "Form 110 console. If an aircraft goes quiet, the MRO uses the Form 110 time log to initiate overdue aircraft protocols.\n"
        "• Talk-Around Simplex Operation: When coordinating with mobile vans in the immediate parking area, the MRO selects "
        "Talk-Around to bypass the regional mountain repeater, preventing net saturation."
    )

    # Use Case 5
    h2 = doc.add_heading("4.5 Use Case 5: Disaster Relief & Multi-Agency Interoperability", level=2)
    h2.style.font.color.rgb = COLOR_STEEL

    doc.add_paragraph(
        "Context: Civil Air Patrol aircraft provide airborne damage assessment and emergency communications relay following "
        "a major wildland fire or earthquake."
    )

    doc.add_paragraph(
        "Interoperability Procedures:\n"
        "• Mutual Aid Frequency Steering: The Mission Observer dials pre-programmed national interop channels on the TDFM-136B: "
        "Channel 016 (VFIRE 21 / 154.2800 MHz) to communicate with CAL FIRE / USFS ground commanders, or Channel 017 "
        "(VTAC 11 / 151.1375 MHz) for local search and rescue teams.\n"
        "• P25 Digital Common Access: When interoperating with federal and military agencies (e.g. FEMA, National Guard), "
        "the radio operates in P25 digital mode utilizing the standardized Network Access Code ($293).\n"
        "• Plain Language Requirement: Prowords and plain English descriptions replace all agency-specific jargon."
    )

    # Use Case 6
    h2 = doc.add_heading("4.6 Use Case 6: Communications Contingencies & Fail-Safe Operations", level=2)
    h2.style.font.color.rgb = COLOR_STEEL

    doc.add_paragraph(
        "Context: Equipment failures, stuck microphones, and terrain masking challenge aircrew survival and mission completion."
    )

    doc.add_paragraph(
        "Simulated Contingency Handling in CAP V-SAR:\n"
        "1. Stuck Microphone Mitigation: If an airborne PTT switch sticks closed, the TDFM-136B hardware Time-Out Timer unkeys "
        "the transmitter after 60 seconds, displaying '*** TIME OUT ***' and freeing the tactical net for emergency traffic.\n"
        "2. Complete Avionics Power Loss: If the aircraft electrical bus fails, the GMA 1347 drops into fail-safe mode. "
        "Internal analog relays mechanically bypass all digital circuitry, directly connecting the pilot's headset to COM1.\n"
        "3. Terrain Masking & Radio Horizon Recovery: When an aircraft descends into a mountain canyon, signals attenuate by "
        ">40 dB. Trainees learn the radio horizon formula: Distance = 1.23 * (sqrt(h_ac) + sqrt(h_base)). Crews climb to "
        "regain line-of-sight propagation with the base repeater."
    )

    # -------------------------------------------------------------
    # SECTION 5: CONSOLIDATED RADIO MODEL & FEATURE MATRIX
    # -------------------------------------------------------------
    h1 = doc.add_heading("5. Consolidated Radio Model & Feature Matrix", level=1)
    h1.style.font.color.rgb = COLOR_NAVY

    doc.add_paragraph(
        "The following master reference matrix cross-references every simulated radio model across operational station, "
        "frequency bands, audio characteristics, safety guards, and regulatory references."
    )

    matrix_headers = ["Radio Model", "Station", "Frequency Range", "Modulation & Standards", "Key Simulated Features", "Regulatory Reference"]
    matrix_rows = [
        [
            "Technisonic TDFM-136B",
            "Airborne Cockpit (MO Station)",
            "136.0000 – 174.0000 MHz",
            "Analog FM (25/12.5 kHz) & P25 Digital Conventional",
            "Dual independent receivers (Main + Guard dual-watch), 200 CAP memories, 60s TOT, 250ms scan engine, CTCSS/NAC",
            "MART Vol. II Ch. 4, TiL 08RE399A, CAPR 100-1 §5",
        ],
        [
            "Garmin GMA 1347",
            "Airborne Cockpit (G1000 Nav III)",
            "Audio Management (COM1/2/3, NAV, ICS)",
            "Digital Audio Matrix & Hardwire Analog Fail-Safe",
            "COM3 Audio vs. MIC interlock, Table 6A.3.2 ICS isolation (ALL/PILOT/COPLT/CREW), Split COM, 2.5-min Clearance Recorder",
            "Garmin Guide 190-00378-01, G1000 Nav III Pilot Guide",
        ],
        [
            "Becker SAR-DF 517",
            "Airborne DF (Cockpit DCU 517)",
            "121.500, 243.000 MHz, 4-ch 406 MHz suite",
            "Pseudo-Doppler 3 kHz AM & 406 COSPAS-SARSAT",
            "Dynamic SNR hiss mixing, STORE tone suppression, 128x64 LCD, 15-hex decode, course-change drag error, TOP/BOTTOM mount",
            "Becker SAR-DF 517 Manual, MART Vol. II Ch. 5",
        ],
        [
            "RHOTHETA RT-600",
            "Airborne DF (Cockpit DCU 600)",
            "118–137 MHz, 156–162 MHz, 243 MHz, 19-ch 406",
            "Multi-band Doppler & 406 COSPAS-SARSAT",
            "Full 19-ch 406 grid (A–S), dual-channel scan, 24 dB wing null airframe shadowing, 50s burst timehold, DSC Ch 70",
            "RHOTHETA RT-600 Manual, CAP Basic DF Training Guide",
        ],
        [
            "Motorola APX 4500 / 6500",
            "Ground Station (Mission Base)",
            "136.0000 – 174.0000 MHz",
            "Analog FM & APCO P25 Phase 1/2 Digital",
            "Authentic CAP fleet codeplug, 3-tone P25 talk permit chirp, 60s server TransmitGate, RSSI signal meter, MON mode",
            "CAPR 100-1 §5-2, Motorola APX 4500 User Guide",
        ],
        [
            "EFJohnson 5300 Series",
            "Ground Station (Command Mobile)",
            "136.0000 – 174.0000 MHz",
            "Analog FM & P25 Conventional",
            "Multi-zone channel selection, hardware squelch override, priority scan, mobile van command post dispatch",
            "EFJohnson 5300 Series Manual, ICUT Syllabus",
        ],
        [
            "Icom IC-A120",
            "Ground Station (Airband Base)",
            "118.000 – 136.992 MHz",
            "VHF-AM Aviation (8.33 / 25 kHz spacing)",
            "Dual-watch (123.100 MHz SAR + 121.500 MHz Guard), Automatic Noise Limiter (ANL), headset sidetone feedback",
            "Icom IC-A120 Manual, CAPR 100-1 §5-4, ICUT Ch. 4",
        ],
        [
            "CAP Form 110 System",
            "Ground Station (MRO Console)",
            "Software Application (Web Audio)",
            "REST / WebSocket Real-Time Telemetry",
            "Zulu timestamping, tactical quick-report buttons, aircraft track synchronization, CSV export, duplicate suppression",
            "CAPR 100-1 §5-3, CAP Pamphlet 100-3, CAP Form 110",
        ],
    ]
    add_styled_table(doc, matrix_headers, matrix_rows, [1.3, 1.0, 1.1, 1.1, 1.3, 0.7])

    # Save Word Document
    print(f"[*] Saving Word Document to: {OUT_DOCX}")
    doc.save(str(OUT_DOCX))
    print(f"[+] Word Document created successfully ({OUT_DOCX.stat().st_size:,} bytes).")

    # -------------------------------------------------------------
    # BUILD MARKDOWN COMPANION (docs/RADIO_FEATURES_AND_USE_CASES.md)
    # -------------------------------------------------------------
    print("[*] Generating Markdown companion...")
    md_content = """# Civil Air Patrol V-SAR: Airborne & Ground Radio Systems Reference
## Comprehensive Technical Specifications, Feature Matrix & Operational Use Cases

**Document Authority:** CAPR 100-1, CAPR 100-3, MART Vol. II, ICUT Syllabus  
**Date:** September 8, 2026  
**Status:** Operational Simulation Reference Manual  
**Repository:** `/home/ron/Projects/cap-vsar`  
**Word Document (.docx):** [`docs/CAP_V-SAR_Radio_Features_and_Use_Cases.docx`](CAP_V-SAR_Radio_Features_and_Use_Cases.docx)

---

## 1. Executive Overview & Regulatory Doctrine

The Civil Air Patrol Virtual Search and Rescue (CAP V-SAR) platform delivers an end-to-end tactical simulation environment for search-and-rescue aircrews, mission observers, and ground communications personnel. Realistic communications fidelity is central to the training value: direction-finding physics, radio propagation degradation, audio panel interlocks, and authentic fleet codeplugs prepare personnel for real emergency services operations.

All simulated radio equipment, audio routing mechanisms, and user controls are engineered to reflect the strict operational, technical, and radiotelephone doctrine defined by official Civil Air Patrol publications:

* **CAPR 100-1 (Radio Communications Policy):** Governs national and wing frequency allocations, standard fleet codeplugs, communications plans, and formal station recordkeeping.
* **CAPR 100-3 (Radiotelephone Procedures):** Regulates formal communications discipline, prohibited practices (including 10-codes), mandatory prowords (`ROGER`, `OVER`, `OUT`, `WAIT`, `SAY AGAIN`), and aircraft phonetics.
* **CAP Pamphlet 100-3 & CAP Form 110:** Standard radio communications guide and the mandatory continuous radio log maintained by Mission Radio Operators (MRO).
* **CAP Introductory Communications User Training (ICUT):** Foundational user competency across base, mobile, and airborne stations, including stuck-mic recognition and transmitter time-out limits.
* **CAP Mission Aircrew Reference Text (MART) Vol. II:** Specific technical and procedural guide for Mission Observers (MO) and SAR Mission Pilots (MP) operating airborne direction finders and VHF-FM tactical transceivers.
* **Manufacturer Operating Handbooks:** Technisonic TDFM-136B (TiL 08RE399A), Garmin GMA 1347 Pilot's Guide (190-00378-01), Becker SAR-DF 517 DCU Manual, RHOTHETA RT-600 Manual, and Motorola APX 4500 User Guide.

---

## 2. Airborne Radio Systems & Cockpit Specifications

The simulated Cessna 182T NAV III (Garmin G1000) cockpit features a fully integrated Mission Observer avionics console. The observer station accommodates tactical mission communications, inter-crew intercom isolation, and electronic search direction finding.

### 2.1 Technisonic TDFM-136B VHF-FM Tactical Transceiver
* **Role:** Primary Airborne Tactical Mission Radio (C182T Observer Station).
* **Frequency Range:** 136.0000 MHz to 174.0000 MHz continuous coverage (25 kHz wideband and 12.5 kHz narrowband channel spacing).
* **Modulation:** Analog FM and APCO Project 25 (P25) Phase 1 Digital Conventional.
* **Dual Independent Receivers:** Houses two physical receiver modules. The Guard receiver continuously monitors GD1 (168.650 MHz AIRGUARD) or GD2 (121.500 MHz Guard) in the background. Guard audio mixes continuously with Main audio, allowing mission base to break into the observer's headset regardless of Main channel selection.
* **Memory Capacity:** 200 programmed user memories + 30 dedicated scan/guard channels. Pre-loaded with official CAP fleet nomenclature (`TAC 1`, `TAC 2`, `CC 1`, `CC 2`, `AIR 1`, `AIR 2`, `SAR 1`, `VFIRE 21`, `VTAC 11`, `CALCORD`). Direct 3-digit numeric keypad entry (e.g. `CHAN 012`).
* **Transmitter Time-Out Timer (TOT):** Hardware 60-second timer forces carrier unkey, displays `*** TIME OUT ***` on LCD, and locks out the transmitter until PTT release.
* **Operational Scan Engine:** 250 ms dwell timer cycles programmed channels (1..20); halts instantly upon carrier detection (`cap_fm_main_rx`); holds for 2000 ms hang time on carrier loss before resuming; pauses during PTT.
* **Squelch & Power:** Selectable HIGH (10W) / LOW (1W) RF power switch, squelch defeat, dual-concentric volume knobs, and dual squelch LED annunciators (`MN` and `GD`).

### 2.2 Garmin GMA 1347 Airborne Audio Panel & Intercom (ICS)
* **Role:** G1000 Audio Management & Cockpit Intercom System (Copilot / MO Station).
* **Transceiver Inputs:** COM1 (VHF-AM ATC), COM2 (VHF-AM Auxiliary/Air-to-Air), COM3 (CAP Tactical VHF-FM via TDFM-136B).
* **Audio vs. MIC Interlock:** Independent audio monitoring vs. active microphone authorization. Trainees can monitor COM3 audio freely, but transmitting requires selecting the COM3 MIC key (the #1 MO trainee error trap).
* **Intercom (ICS) Isolation Modes (Table 6A.3.2):**
  * `ALL`: Full inter-crew communications between pilot, copilot/observer, and cabin passengers.
  * `PILOT`: Pilot isolated on COM1 (ATC); copilot and cabin passengers share intercom.
  * `COPILOT`: Copilot/MO isolated; pilot and cabin communicate.
  * `CREW`: Pilot and copilot communicate together; cabin passengers isolated.
* **Split COM Operation:** Pilot operates COM1; copilot operates COM2; Mission Observer de-asserted from tactical net to prevent distractions during high-workload terminal operations.
* **Digital Clearance Recorder (PLAY):** 16-block circular memory buffer capturing 2.5 minutes of incoming COM1, COM2, and COM3 audio. Pressing `PLAY` replays the latest block; successive presses step backward through historical radio calls. Any non-PLAY key aborts.
* **Fail-Safe Mode:** Automatic hard-wire analog relay linking pilot headset and PTT directly to COM1 upon avionics bus power loss.

### 2.3 Becker SAR-DF 517 Airborne Direction Finder
* **Role:** Precision VHF/UHF/406 MHz Airborne Direction Finding System (DCU 517).
* **Frequencies:** VHF 121.500 MHz, UHF 243.000 MHz, and 4-channel 406 MHz suite (Emergency: 406.025 MHz; Training: 406.022, 406.025, 406.028, 406.037 MHz).
* **Acoustic Profile:** 3 kHz pseudo-Doppler AM tone modulation (`elt_analog_df.wav`), tone-suppressed clean audio sweep (`elt_analog_clean.wav`) via `STORE` key, and 406 digital burst (`elt_406_burst.wav`).
* **Dynamic SNR Hiss Degradation:** Synthesized band-limited discriminator noise (`elt_noise.wav`) dynamically mixed inversely against RF signal strength (`cap/df/signal`). Distant or terrain-masked beacons are audibly noisy.
* **Display & Calculations:** 128x64 LCD dot-matrix with 360° circular needle, relative bearing, signal strength bar, and spread quality indicator. Decodes 15-hex COSPAS-SARSAT frames. Multi-sample circular averaging filter modeling authentic aircraft course-change drag error.
* **Calibration:** Top vs. Bottom antenna mounting toggle (preventing mirror bearing inversion) and angular offset adjustment.

### 2.4 RHOTHETA RT-600 Advanced SAR Direction Finder
* **Role:** Multi-Band Precision Airborne Direction Finder (DCU 600).
* **Frequency Coverage:** VHF Airband (118–137 MHz), Maritime VHF (156–162 MHz), Military (243 MHz), and the complete 19-channel COSPAS-SARSAT grid (406.022 to 406.076 MHz across 7 CPSAR groups A through S).
* **Dual-Watch Scanning:** Simultaneously sweeps 406 MHz burst channels while alternating between 121.500 MHz and secondary search frequencies.
* **Airframe Shadowing:** Attitude-dependent wing null attenuation modeling fuselage and wing shielding (up to 24 dB loss), enabling authentic wing-dip ambiguity resolution.

---

## 3. Ground Station Radio Systems & MRO Console

### 3.1 Motorola APX 4500 / APX 6500 & EFJohnson 5300 Tactical Base Radios
* **Role:** Primary Ground Mission Base and Mobile Command Post Tactical Transceiver.
* **Frequencies & Channels:** VHF High-Band (136–174 MHz) conventional analog and P25 digital. Multi-zone fleet codeplug (`Zone 1: Command/Tactical`, `Zone 2: Ground`, `Zone 3: Interop`).
* **Acoustic Cues:** Authentic 3-tone P25 talk-permit chirp (`941/1336/1209 Hz`), channel busy alert, and squelch tail.
* **Server-Side Transmit Gate:** Enforces a 60-second fail-closed lease (`TransmitGate`) to maintain net hygiene.
* **Monitor Mode (MON):** Instant squelch override allowing reception of marginal signals from low-altitude aircraft in mountainous terrain.

### 3.2 Icom IC-A120 VHF Aeronautical Base Station Transceiver
* **Role:** Dedicated Ground Airband SAR Base Station.
* **Frequencies:** 118.000 – 136.992 MHz (VHF-AM aviation airband, 8.33 / 25 kHz spacing).
* **Dual-Watch Capability:** Simultaneous monitoring of Primary Air-to-Ground SAR (123.100 MHz) with priority watch on Emergency Guard (121.500 MHz) or Airport UNICOM.
* **Noise Limiter (ANL) & Side-Tone:** Suppresses engine pulse noise and provides audio side-tone feedback.

### 3.3 CAP Form 110 Radio Communications Log System
* **Doctrinal Requirement:** Mandatory under CAPR 100-1 §5-3. Provides legal and operational records of all station traffic.
* **Core Capabilities:** Real-time Zulu timestamping, tactical shortcut buttons (`Ops Normal`, `Radio Check`, `Bearing Report`, `Departing`, `In-Grid`, `Out-of-Grid`, `Overhead`), coordinate and altitude logging, and CSV export for Incident Command.

---

## 4. Operational Use Cases & Doctrinal Procedures

### 4.1 Use Case 1: Electronic Search & Rescue (ELT / EPIRB Localization)
1. **En Route Monitoring:** Tune Becker 517 / RT-600 to 121.500 MHz and 406.025 MHz. Confirm squelch opens.
2. **Digital Decode:** Upon receiving a 406 MHz burst, record the 15-hex beacon ID and country code. Verify GPS position coordinates if present.
3. **SNR Hiss Evaluation:** Note receiver static. As the aircraft approaches the beacon, the 3 kHz pseudo-Doppler sweep clarifies and static subsides.
4. **Wing-Dip Ambiguity Resolution:** If bearing is ambiguous, bank the aircraft 20° toward the suspected direction. The high wing causes airframe shielding (up to 24 dB loss), confirming the beacon's lateral position.
5. **Aural Null / Tone Suppression:** Inside 1 NM, bearing needle oscillations increase. Engage the `STORE` key to suppress the 3 kHz tone, using clean analog receiver volume to confirm overhead beacon passage.

### 4.2 Use Case 2: Tactical Air-to-Ground Coordination (Observer to Base)
1. **Audio Panel Setup:** Observer selects `COM3` Audio to monitor, and `COM3 MIC` to transmit.
2. **Channel Selection:** Select Channel `001` (TAC 1 / 148.150 MHz) on the TDFM-136B.
3. **Radio Check:** Key observer PTT. Transmission audio is verified with base.
4. **30-Minute Ops Normal:** Crew reports: *"MISSION BASE, CAP-STONE 423, OPS NORMAL, GRID 142A, 4500 FEET, REMAINING FUEL 3.5 HOURS"*. MRO clicks `Ops Normal` on the Form 110 console.
5. **Guard Dual-Watch:** TDFM Guard receiver monitors AIRGUARD (168.650 MHz) continuously. Base emergency calls mix directly into crew audio without leaving TAC 1.

### 4.3 Use Case 3: Cockpit Intercom Management & CRM
1. **Pilot Isolation (`PILOT`):** When entering terminal airspace, pilot selects `PILOT` isolation, muting observer tactical chatter to focus on ATC.
2. **Split COM:** Pilot works ATC on COM1; copilot works air-to-air on COM2; tactical COM3 is isolated to prevent cockpit saturation.
3. **Clearance Recorder Playback:** If an ATC clearance or base grid coordinate is missed, pressing `PLAY` on the GMA 1347 replays the transmission without re-keying the net.

### 4.4 Use Case 4: Mission Radio Operator (MRO) Base Operations
1. **Dual-Watch:** MRO cross-monitors tactical VHF-FM on the APX 4500 while monitoring aeronautical SAR (123.100 MHz) on the IC-A120.
2. **Continuous Form 110 Logging:** All sorties, fuel states, and bearing reports are logged with Zulu timestamps.
3. **Talk-Around Mode:** Local simplex communication with flight line vehicles bypasses mountain repeaters.

### 4.5 Use Case 5: Disaster Relief & Multi-Agency Interoperability
1. **Mutual Aid Channels:** Dial national interop channels on the TDFM-136B: Channel `016` (VFIRE 21 / 154.2800 MHz) for CAL FIRE/USFS, or Channel `017` (VTAC 11 / 151.1375 MHz) for local SAR teams.
2. **P25 Digital Common Access:** Interoperate with FEMA and National Guard using standard P25 digital mode and NAC `$293`.
3. **Plain Language:** Radiotelephone prowords and clear text replace all 10-codes.

### 4.6 Use Case 6: Communications Contingencies & Fail-Safe Operations
1. **Stuck Mic Mitigation:** Airborne TDFM-136B 60s TOT automatically cuts off transmission, displaying `*** TIME OUT ***` and freeing the net.
2. **Avionics Power Loss:** GMA 1347 hardwire analog relays link pilot headset directly to COM1.
3. **Terrain Masking Recovery:** When canyon walls attenuate signals (>40 dB), crews climb to clear the radio horizon: $\\text{Distance (NM)} = 1.23 \\sqrt{h_{\\text{ac}}} + 1.23 \\sqrt{h_{\\text{base}}}$.

---

## 5. Consolidated Radio Model & Feature Matrix

| Radio Model | Station | Frequency Range | Modulation & Standards | Key Simulated Features | Regulatory Reference |
|---|---|---|---|---|---|
| **Technisonic TDFM-136B** | Airborne Cockpit (MO Station) | 136.0000 – 174.0000 MHz | Analog FM & P25 Digital | Dual independent receivers (Main + Guard dual-watch), 200 CAP memories, 60s TOT, 250ms scan engine, CTCSS/NAC | MART Vol. II Ch. 4, TiL 08RE399A, CAPR 100-1 §5 |
| **Garmin GMA 1347** | Airborne Cockpit (G1000 Nav III) | Audio Management (COM1/2/3, NAV, ICS) | Digital Audio Matrix & Hardwire Fail-Safe | COM3 Audio vs. MIC interlock, Table 6A.3.2 ICS isolation (ALL/PILOT/COPLT/CREW), Split COM, 2.5-min Clearance Recorder | Garmin Guide 190-00378-01, G1000 Nav III Pilot Guide |
| **Becker SAR-DF 517** | Airborne DF (Cockpit DCU 517) | 121.500, 243.000 MHz, 4-ch 406 MHz suite | Pseudo-Doppler 3 kHz AM & 406 COSPAS-SARSAT | Dynamic SNR hiss mixing, STORE tone suppression, 128x64 LCD, 15-hex decode, course-change drag error, TOP/BOTTOM mount | Becker SAR-DF 517 Manual, MART Vol. II Ch. 5 |
| **RHOTHETA RT-600** | Airborne DF (Cockpit DCU 600) | 118–137 MHz, 156–162 MHz, 243 MHz, 19-ch 406 | Multi-band Doppler & 406 COSPAS-SARSAT | Full 19-ch 406 grid (A–S), dual-channel scan, 24 dB wing null airframe shadowing, 50s burst timehold, DSC Ch 70 | RHOTHETA RT-600 Manual, CAP Basic DF Training Guide |
| **Motorola APX 4500 / 6500** | Ground Station (Mission Base) | 136.0000 – 174.0000 MHz | Analog FM & APCO P25 Phase 1/2 Digital | Authentic CAP fleet codeplug, 3-tone P25 talk permit chirp, 60s server TransmitGate, RSSI signal meter, MON mode | CAPR 100-1 §5-2, Motorola APX 4500 User Guide |
| **EFJohnson 5300 Series** | Ground Station (Command Mobile) | 136.0000 – 174.0000 MHz | Analog FM & P25 Conventional | Multi-zone channel selection, hardware squelch override, priority scan, mobile van command post dispatch | EFJohnson 5300 Series Manual, ICUT Syllabus |
| **Icom IC-A120** | Ground Station (Airband Base) | 118.000 – 136.992 MHz | VHF-AM Aviation (8.33 / 25 kHz spacing) | Dual-watch (123.100 MHz SAR + 121.500 MHz Guard), Automatic Noise Limiter (ANL), headset sidetone feedback | Icom IC-A120 Manual, CAPR 100-1 §5-4, ICUT Ch. 4 |
| **CAP Form 110 System** | Ground Station (MRO Console) | Software Application (Web Audio) | REST / WebSocket Real-Time Telemetry | Zulu timestamping, tactical quick-report buttons, aircraft track synchronization, CSV export, duplicate suppression | CAPR 100-1 §5-3, CAP Pamphlet 100-3, CAP Form 110 |
"""

    OUT_MD.write_text(md_content, encoding="utf-8")
    print(f"[+] Markdown companion created successfully ({OUT_MD.stat().st_size:,} bytes).")


if __name__ == "__main__":
    build_documents()

