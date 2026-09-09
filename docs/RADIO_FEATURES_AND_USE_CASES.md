# Civil Air Patrol V-SAR: Airborne & Ground Radio Systems Reference
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
3. **Terrain Masking Recovery:** When canyon walls attenuate signals (>40 dB), crews climb to clear the radio horizon: $\text{Distance (NM)} = 1.23 \sqrt{h_{\text{ac}}} + 1.23 \sqrt{h_{\text{base}}}$.

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
