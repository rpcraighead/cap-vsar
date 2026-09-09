# CAP V-SAR Radio Ecosystem: Real-World Operations & Fidelity Audit

**Date:** September 8, 2026  
**Repository:** `/home/ron/Projects/cap-vsar`  
**Purpose:** Hand-off technical audit evaluating the fidelity of CAP V-SAR radio configurations, instruments, audio routing, and backend systems against real-world Civil Air Patrol (CAP) operational doctrine, training syllabi, and hardware manuals.

---

## 1. Regulatory, Training & Equipment References

This audit evaluates the codebase against official publications and technical manuals:
* **CAPR 100-1:** *Radio Communications Policy* (Chapter 5: Communications Plans, Frequency Allocations, Station Records)
* **CAPR 100-3:** *Radiotelephone Procedures* (Operating Rules, Prowords, Call Signs, Phonetics, Radio Checks)
* **CAP Pamphlet 100-3:** *Radio Communications Guide* & **CAP Form 110:** *Communications Log*
* **CAP ICUT:** *Introductory Communications User Training* (Base Station Operations, Mobile Radios, Practical Skills Evaluation)
* **CAP MART Vol. II:** *Mission Observer / SAR-DR Mission Pilot Reference Text* (Ch. 2: Aircraft Communications, Ch. 4: Airborne TDFM-136 Transceiver)
* **CAP Mission Observer Task Guides:** Graded performance measures for TDFM-136, audio panel operations, and tactical reporting
* **Technisonic TDFM-136B Operating Instructions:** TiL Document 08RE399A (Keypad commands, memory banks, Guard receiver, Time-Out Timer)
* **Garmin GMA 1347 Audio Panel Pilot's Guide:** Document 190-00378-01 Rev. A (Cessna Nav III C182T / G1000)
* **Motorola APX 4500 / APX 6500 User Guides:** O2 and O5 Control Heads (P25 operation, zones, talk permit tones)
* **EFJohnson 5300 Series Mobile Operations Manual:** Base/mobile operations and fleet channel steering
* **Icom IC-A120 VHF Air Band Transceiver Instruction Manual:** Dual-watch, priority watch, memory presets
* **Becker SAR-DF 517 & RHOTHETA RT-600 Handbooks:** Pseudo-Doppler 3 kHz tone modulation, 406 MHz COSPAS-SARSAT bursts, tone suppression

---

## 2. Executive Summary

CAP V-SAR simulates radio propagation, cockpit direction finding, and tactical VHF communications for Civil Air Patrol search-and-rescue aircrews and ground teams. 

### What the Simulation Gets Right
1. **GMA 1347 Audio vs. Mic Interlock:** Faithful modeling of the primary trap for Mission Observers (`mo-audio-panel-gma1347/logic.lua`): selecting COM3 Audio allows listening to the FM net, but transmitting requires pressing COM3 MIC.
2. **Direction Finding Receiver Physics:** Solid pseudo-Doppler 3 kHz AM modulation tone and 406.025 MHz digital burst audio gating (`cap_df_audio.lua`), plus coverage distinctions between Becker 517 (4 channels) and RT-600 (19 channels).
3. **Mumble Audio Worklet & Server-Side Transmit Gate:** Low-latency 48 kHz mono streaming with an independent fail-closed 60-second PTT server lease (`radio.py:TransmitGate`).

### Critical Real-World Gaps & Deficits
1. **Ground Console Omits CAP Form 110 Log (Bug Tracker F-9):** The modern voice console (`/radio`) has no communications logbook. MROs cannot log Zulu time, channel, call signs, or traffic. (The log existed only in the deprecated `/radio-legacy` text console).
2. **No VHF-AM Airband Radio for Mission Base (No Dual-Watch):** Real-world MROs must monitor both the VHF-FM tactical net (148.150 MHz) and the VHF-AM airband SAR frequency (123.100 MHz / 122.900 MHz). The modern web radio only connects to a single Mumble net at a time.
3. **Airborne TDFM-136B Logic Disconnects:**
   * Unwired RX squelch indicators and PTT variables (Bug Tracker I-9b).
   * Missing 60-second transmitter Time-Out Timer (TOT) stuck-mic guard in the aircraft radio.
   * No actual dual-receiver audio mixing for Guard.
   * Hardcoded 6-channel generic memory table lacking authentic CAP channel plans, CTCSS PL tones, and P25 NACs.
4. **Superficial Intercom (ICS) Isolation:** GMA 1347 `ALL`, `PILOT`, `COPILOT`, and `CREW` isolation keys change faceplate lamps, but do not route or isolate audio streams between PilotEdge (ATC) and Mumble (Crew).

---

## 3. Detailed Component Audit & Gap Analysis

### 3.1 Airborne Tactical Transceiver: Technisonic TDFM-136B
**Files:**
* `instruments/cap-fm-tdfm-136b/logic.lua`
* `instruments/cap-fm-tdfm-136b/lib/tdfm_display.lua`
* `instruments/cap-fm-tdfm-136b/lib/tdfm_panel.lua`

#### Analysis of Current Code
* Implements physical layout: 2-line dot-matrix display, MN/GD toggle, G1/G2 switch, HI/LO power switch, dual rotary encoders (Main and Guard volume), squelch defeat, and 12-key keypad.
* Implements Level 1 command hierarchy: Direct CHAN selection (`L1-1`), memory scroll up/down (`L1-4`/`L1-6`), scan indicator toggle (`L1-5`), Home memory toggle (`L1-#`), and Talk-Around (`L1-*`).
* Auto-times out Level 2/3 back to Level 1 after 5 seconds (`arm_level_timeout`).
* Interlocks transmit state with GMA 1347 `cap_fm_mic_selected` and `cap_fm_ptt`.

#### Real-World & CAP Doctrine Gaps
* **Channel Plan & Nomenclature (`logic.lua:38–51`):**  
  * *Code:* Contains only 6 hardcoded memories (`CMD 1`, `CMD 2`, `AIR-GND`, `REPTR 1`, `SIMPLEX`, `TAC 1`) and 2 Guard channels (`GUARD 1` at 148.000 MHz, `GUARD 2` at 149.500 MHz).
  * *Real World (CAPR 100-1 §5 & MART Vol. II Ch. 4):* The TDFM-136B has 230 memory positions (1–200 user, 201–230 guard/scan). Standard CAP fleet codeplugs program Wing command channels, tactical channels (`TAC 1`, `TAC 2`, `AIR 1`, `AIR 2`, `SAR 1`), and federal interop channels (`VFIRE 21`, `VTAC 11`). Because only 6 channels exist in the code, entering a briefed 2-digit or 3-digit channel (e.g., `CHAN 012`) fails.
  * *Guard Frequency:* Real CAP Guard is standardized nationally (e.g., 148.1500 MHz analog with Tone 8 / 110.9 Hz or P25 NAC $293). Guard 1 is set to 148.000 MHz in code.
* **CTCSS PL Tones and P25 Digital NACs:**  
  * *Code:* Squelch mode is stored as single-letter metadata (`"t"`, `"x"`, `"g"`), but no subaudible CTCSS tones (e.g., Tone 1 = 100.0 Hz, Tone 8 = 110.9 Hz) or P25 Network Access Codes (standard `$293`) are modeled or verified.
  * *Real World (CAP MO Guide §5):* A frequent airborne failure mode is transmitting on a repeater channel without the correct access tone or transmitting on simplex when the repeater was needed. Trainees cannot experience or diagnose tone mismatches.
* **Missing Transmitter Time-Out Timer (Stuck Mic Guard):**  
  * *Code:* The Lua logic allows indefinite transmission as long as `cap_fm_ptt` is held.
  * *Real World (TDFM-136B Manual §1.1 & CAP MO Guide §5):* The TDFM-136 has a hardware TOT configured for 30, 60, or 90 seconds (CAP standard is 60 seconds). If keyed continuously, the radio automatically unkeys, flashes `TX` or sounds a warning tone, and locks out until released. Recognizing TOT cutoff and identifying a stuck mic is a core ICUT practical exam requirement.
* **Dead Squelch / RX Annunciators (Bug Tracker I-9b, `logic.lua:480–490`):**  
  * *Code:* `logic.lua` subscribes to `cap_fm_main_rx` and `cap_fm_guard_rx` to illuminate the green squelch LEDs (`led_main`, `led_guard`).
  * *Gap:* Neither the X-Plane propagation plugin (`PI_capvsar_df.py`) nor the Mumble server bridges publish these variables. The RX lamps remain permanently unlit during simulations.
* **Independent Guard Dual-Watch Receiver:**  
  * *Code:* Guard volume knob and G1/G2 switch exist, but only one active channel frequency (`var_freq`) is published to Mumble.
  * *Real World:* The TDFM-136 contains two physical receiver modules. The Guard receiver operates continuously in the background. Guard traffic must break through or mix with Main audio, allowing base to reach aircraft in an emergency regardless of what Main is working.
* **Scan Engine Simulation:**  
  * *Code:* `toggle_scan()` simply displays an `"S"` flag on the LCD; it does not cycle channels or monitor activity.
  * *Real World:* Scan cycles the programmed scan list and halts on active carrier with an automatic resume timer.

---

### 3.2 Cockpit Audio Management: Garmin GMA 1347 Audio Panel
**Files:**
* `instruments/mo-audio-panel-gma1347/logic.lua`
* `instruments/mo-audio-panel-gma1347/lib/gma_panel.lua`

#### Current Implementation
* Dedicated Mission Observer audio panel (copilot station) in the G1000 cockpit.
* Transceiver keys: COM1, COM2, and COM3 (dedicated CAP VHF-FM mission radio), with exclusive microphone selection.
* Concentric rotary knobs for Volume and Squelch (inner ring: pilot, outer ring: copilot/crew), with `MAN SQ` mode toggle.
* Implements Table 6A.3.2 ICS isolation state machine (`ALL`, `PILOT`, `COPILOT`, `CREW`).
* Models Split COM operation (copilot locked to COM2, losing COM3 tactical radio).
* 2-second power-up lamp test synchronized with avionics bus (`avionics_power_on`).

#### Real-World & CAP Doctrine Gaps
* **Intercom (ICS) Audio Isolation is Superficial (`logic.lua:80, 158–161`):**  
  * *Code:* Toggling `PILOT` or `COPLT` cycles `st.ics` and writes `var_ics = "ALL" / "PILOT" / "COPILOT" / "CREW"`.
  * *Gap:* Neither Mumble nor X-Plane audio consumes `cap_ics_isolation`. In practice, all crew members connect to a single Mumble channel (`CAP-1 Intercom`) or speak over Discord/external audio. Changing ICS isolation on the GMA 1347 changes the lamp display, but does not isolate passenger chatter from the pilot or mute cockpit noise during high-workload operations.
* **Split COM Voice Decoupling (`logic.lua:100–106, 177–185`):**  
  * *Code:* Engaging `SPLIT` forces copilot mic to COM2 and de-asserts `cap_fm_audio_selected` and `cap_fm_mic_selected`.
  * *Gap:* While this correctly drops the Air Manager Si variables, the external Mumble client on the MO station does not automatically mute or disconnect from the mission net unless an external bridge script is running.
* **Clearance Recorder (PLAY) Inactive (`logic.lua:188–197`):**  
  * *Code:* The `PLAY` button momentarily flashes its annunciator for 1200 ms.
  * *Real World (GMA 1347 Pilot’s Guide §6A.2):* The GMA 1347 digital clearance recorder continuously records the last 2.5 minutes of incoming COM audio. Pressing `PLAY` replays recorded radio traffic in reverse chronological chunks—vital for SAR crews who miss a grid coordinate or ATC clearance.
* **Fail-Safe Mode Hardware Bypass:**  
  * *Code:* Dropping avionics power turns off the panel and zeroes all audio variables.
  * *Real World:* True fail-safe connects the pilot’s headset and PTT directly to COM1 analog circuitry to ensure ATC survival, while completely isolating the copilot/MO.

---

### 3.3 Ground Mission Base Radios (MRO Station)
**Files:**
* Modern voice console: `services/exercise/app/static/mission-radio.html`, `mission-radio.js`, `services/exercise/app/radio.py`
* Legacy text console: `services/exercise/app/static/radio.html`, `radio.js`

#### Current Implementation
* Dual-chassis SVG artwork for **Motorola APX 4500 (O2 head)** and **EFJohnson 5300**.
* Web AudioWorklet streaming 48 kHz mono 16-bit PCM directly to Mumble (`radio-worklet.js` & `radio.py`).
* Server-side fail-closed PTT gate (`TransmitGate`) with a 60-second limit and a 1.5-second lease.
* Interactive rotary volume and net selection hit regions.

#### Real-World & CAP Doctrine Gaps
* **Complete Absence of CAP Form 110 Communications Log (Bug Tracker F-9):**  
  * *Real World (CAPR 100-1 §5-3, CAP Pamphlet 100-3, ICUT):* The primary duty of a CAP Mission Radio Operator (MRO) is maintaining the **CAP Form 110 Radio Communications Log**. The MRO must log:
    1. Zulu Time
    2. Frequency / Channel
    3. Station From (Call sign)
    4. Station To
    5. Traffic / Remarks (Ops Normal, coordinates, bearings, departures, arrivals)
  * *Gap:* The new voice console (`/radio`) completely lacks a Form 110 logging table. The log existed in the deprecated `/radio-legacy` console (`radio.html:343-368`), but was omitted when the Mumble Web Audio bridge was built. MROs operating the live voice net currently have no integrated logging tool.
* **Missing VHF-AM Airband SAR Radio (No Dual-Watch Capability):**  
  * *Real World (CAPR 100-1 & MART Vol. II):* Ground mission bases in Civil Air Patrol must communicate with search aircraft via two distinct systems:
    1. **VHF-FM Tactical Net** (148.150 MHz / CAP channels) for mission coordination and ground teams.
    2. **VHF-AM Aeronautical SAR Frequencies** (123.100 MHz primary SAR, 122.900 MHz secondary SAR, 121.500 MHz emergency Guard) via dedicated base transceivers like the **Icom IC-A120**.
  * *Gap:* `/radio` connects to only **one Mumble channel at a time**. The MRO cannot monitor both the tactical FM net and the aeronautical SAR net simultaneously. While `/radio-legacy` featured a dual-station rack (APX 6500 + Icom IC-A120), `/radio` eliminated the aeronautical transceiver.
* **Superficial Control Head Buttons:**  
  * *Code:* In `mission-radio.js`, buttons for `SCAN`, `SQL`, `MON`, and `EMER` on the APX 4500 and EFJohnson 5300 are inert visual SVG references.
  * *Real World:* MROs frequently use `MON` (Monitor / Squelch Open) to hear marginal signals from low-altitude aircraft in mountainous terrain, and `SCAN` to watch secondary nets.
* **Arbitrary Net Names vs. Authentic Fleet Codeplugs:**  
  * *Code:* Channels are defined as `PRIMARY`, `ALTERNATE`, `MISSION BASE`, `BRIEFING` (`radio.py:29-34`).
  * *Real World:* Real MRO radios display Zone and Channel tags adhering to the CAP fleet plan (e.g., `Z1 CH01 TAC 1`, `Z1 CH04 CC 1`, `Z2 CH01 GROUND 1`, `Z3 CH01 VFIRE21`).
* **Lack of Audio SFX / Sidetone Cues:**  
  * *Gap:* Unlike `radio.js` (which synthesized P25 talk-permit chirps, squelch tails, and AM clicks), `mission-radio.js` has no acoustic feedback. In real P25 radios, the 3-tone permit chirp (`941/1336/1209 Hz`) confirms channel grant before the operator speaks.
* **Network Blip Disconnect (Bug Tracker F-4):**  
  * *Code:* `mission-radio.js:185` triggers `disconnect()` on any WebSocket blip with no auto-reconnect logic. If a base tablet roams Wi-Fi, the MRO is silently dropped from the mission net.

---

### 3.4 Direction Finding Receivers: Becker SAR-DF 517 & RHOTHETA RT-600
**Files:**
* `instruments/df-becker-sar-df-517/`
* `instruments/df-rhotheta-rt-600/`
* `xplane/PI_capvsar_df.py`
* `instruments/*/lib/cap_df_audio.lua`

#### Current Implementation
* Dual DF head simulation covering 121.500 MHz, 243.000 MHz, and COSPAS-SARSAT 406 MHz channels.
* Accurate modeling of the Becker 517's 4-channel 406 coverage vs. RT-600's full 19-channel COSPAS-SARSAT coverage.
* Audio state machine (`cap_df_audio.lua`) playing 3 kHz pseudo-Doppler AM tone (`elt_analog_df.wav`), tone-suppressed clean sweep (`elt_analog_clean.wav`), and 406 digital burst (`elt_406_burst.wav`).
* Squelch gating and relative bearing calculations with spread indication.

#### Real-World & CAP Doctrine Gaps
* **Audio Fidelity & Signal-to-Noise Ratio (SNR):**  
  * *Code:* `cap_df_audio.lua` loops static pre-recorded WAV files at fixed fidelity, scaled only by the front-panel volume knob (`volume`).
  * *Real World:* Real DF receiver audio is characterized by varying signal-to-noise ratio. At maximum range or near terrain blockage, the ELT sweep is heavily buried in white noise and receiver hiss. In the simulator, the audio is either 100% pristine or completely muted by `rx_open`.
* **Tone Suppression Bleed Across Bands (Bug Tracker I-3):**  
  * *Code:* In `cap_df_audio.lua:41-44`, engaging `STORE` (tone suppression) on the Becker suppresses Doppler tone regardless of whether the head is on 121.5 MHz or 406 MHz.
* **121.5 MHz Beacons Producing 406 Decodes (Bug Tracker P-6):**  
  * *Code:* `PI_capvsar_df.py` can generate COSPAS-SARSAT 15-hex frames even when tracking legacy 121.5 MHz analog transmitters. Analog ELTs have no digital data stream.
* **Terrain Masking Attenuation Floor (Bug Tracker P-8):**  
  * *Code:* In `PI_capvsar_df.py`, terrain masking applies only -12 dB of attenuation.
  * *Real World:* Mountainous terrain (granite ridges) completely blocks VHF line-of-sight propagation (attenuation > 40–60 dB), rendering the signal fully inaudible.

---

### 3.5 Voice Topology & Inter-Process Signal Plumbing
**Files:**
* `docs/DATAREF_CONTRACT.md`
* `docs/BUG_TRACKER.md`
* `services/exercise/app/radio.py`
* `docs/MUMBLE_CHANNELS.md`

#### Real-World & Architectural Gaps
* **Unpublished `cap_fm_*` Variables in Contract (Bug Tracker I-9b):**  
  * *Code:* Variables `cap_fm_ptt`, `cap_fm_main_rx`, and `cap_fm_guard_rx` are subscribed to by the TDFM-136B and GMA 1347, but are omitted from `docs/DATAREF_CONTRACT.md` and have no backend producer.
* **Missing Air Manager <-> Mumble Bridge Service:**  
  * *Architecture:* Implementation Plan §6.3.2 assumed a local agent would bridge Air Manager Si variables (`cap_fm_frequency_hz`, `cap_fm_transmitting`) to the local Mumble client on the cockpit PC. This bridge daemon is not present in the repository, leaving the airborne station’s radio tuning decoupled from Mumble channel switching.
* **Concurrent Session Bottleneck (Bug Tracker X-9):**  
  * *Code:* `radio.py:297` enforces `CAPVSAR_RADIO_MAX_SESSIONS` (default 16). In a full SAREX with 3 multi-place aircraft crews (9 members) plus ground staff (Incident Commander, Air Operations Branch Director, 2 Mission Radio Operators, Planning), 16 sessions can be exhausted by page reloads.

---

## 4. Direct Matrix: Codebase vs. Official CAP Operations

| Operational Element | Official CAP Standard / Regulation | Current Codebase Implementation | Status & Fidelity Gap |
| :--- | :--- | :--- | :--- |
| **Tactical Radio Hardware** | Technisonic TDFM-136 / TDFM-136B (MART Vol. II Ch. 4) | Air Manager TDFM-136B instrument (`cap-fm-tdfm-136b`) | **High Visual / Moderate Logic**. Missing 230-ch memory table, Guard audio mixing, and TOT. |
| **Transmitter Time-Out Timer** | 60s standard TOT cutoff to prevent stuck mics (ICUT & MO Guide) | Lua script allows infinite transmission; Web radio has 60s server lease | **Partial**. Modeled on ground web radio; completely missing from airborne cockpit radio. |
| **Cockpit Audio Management** | GMA 1347 COM3 Audio vs. COM3 MIC interlock (G1000 Guide) | GMA 1347 instrument (`mo-audio-panel-gma1347`) | **Accurate**. Faithfully reproduces the #1 MO error trap (listening without mic selected). |
| **Cockpit ICS Isolation** | ALL / PILOT / COPILOT / CREW voice isolation (G1000 Table 6A.3.2) | GMA 1347 lamp state machine; writes `cap_ics_isolation` | **Visual Only**. No backend audio stream routing or muting honors the ICS state. |
| **Split COM Operation** | Pilot on COM1 (ATC), Copilot on COM2 (GMA 1347 Guide) | Toggles `st.split`; isolates MO from COM3 tactical | **Partial**. Sets Air Manager booleans, but does not decouple local Mumble client. |
| **Ground Base Radio Hardware** | Motorola APX / EFJohnson 5300 & Icom IC-A120 (ICUT Review) | Web console with APX 4500 & EFJ 5300 SVG skins (`/radio`) | **Moderate**. High visual fidelity; controls (SCAN, SQL, MON) are inert; no IC-A120 airband radio. |
| **Radio Communications Log** | **CAP Form 110** mandatory continuous log (CAPR 100-1 & CAPF 110) | Present in deprecated `/radio-legacy`; absent from `/radio` | **Critical Deficit**. Ground MRO has no operational logbook on the active voice console. |
| **Dual-Watch Monitoring** | MRO monitors VHF-FM (Tactical) and VHF-AM (SAR 123.100) (ICUT) | Web console restricted to 1 Mumble channel at a time | **Functional Gap**. Ground base cannot cross-monitor airband and tactical FM nets simultaneously. |
| **Tactical Net Nomenclature** | Standard Wing/National channels: TAC 1, CC 1, AIR 1 (CAPR 100-1) | Generic labels: `PRIMARY`, `ALTERNATE`, `BASE` | **Low Realism**. Misses opportunity to train authentic channel identification. |
| **Proword & Call Sign Rules** | CAPR 100-3 (ROGER, OVER, OUT, OPS NORMAL, no 10-codes) | Preamble documented in `MUMBLE_CHANNELS.md` | **Documentation Only**. No in-app prompts, logging aids, or protocol guidance for trainees. |
| **Direction Finding Audio** | Pseudo-Doppler 3 kHz tone, 406 burst, SNR noise (Becker Manual) | AudioWorklet / WAV loops (`cap_df_audio.lua`) | **Good**. Correct audio gating, but lacks RF distance-based noise degradation. |

---

## 5. Prioritized Remediation Roadmap for Engineering

### Phase 1: Immediate High-Priority Tasks (Critical for SAREX Training Integrity)
1. **Integrate CAP Form 110 Logging into Modern Voice Console (`mission-radio.html`) [Bug F-9]:**
   * Port the table structure, quick-report buttons ("Ops Normal", "Radio Check", "Bearing Report"), and CSV export mechanism from `services/exercise/app/static/radio.html` (`lines 343–368`) into `mission-radio.html`.
   * Bind entry logging with auto-populated UTC timestamp and active channel name.
2. **Implement Airborne TDFM-136B 60-Second Time-Out Timer (TOT):**
   * In `instruments/cap-fm-tdfm-136b/logic.lua`, introduce a transmission timer that automatically unkeys `var_ptt` after 60 seconds of continuous keying, renders a flashing `TOT` / `TX` warning on the LCD, and requires releasing the PTT key to reset.
3. **Plumb Air Manager `cap_fm_*` Variables [Bug I-9b]:**
   * Connect `cap_fm_main_rx` and `cap_fm_guard_rx` to Mumble channel voice-activity callbacks so the squelch LEDs (`led_main`, `led_guard`) illuminate realistically when traffic is received.
   * Provide a clear hardware/joystick binding for observer PTT feeding `cap_fm_ptt`.
4. **Implement Automatic Reconnection for Web Radio (`mission-radio.js`) [Bug F-4]:**
   * Replace the hard disconnect on `close` with an exponential backoff auto-reconnect routine so base operators on tablets do not get dropped during network roaming.

### Phase 2: Medium-Priority Tasks (Realism & Operational Accuracy)
1. **Introduce Dual-Watch VHF-AM Airband Transceiver at Mission Base:**
   * Add a secondary listening receiver for the Icom IC-A120 on the MRO console, allowing simultaneous monitoring of CAP VHF-FM tactical traffic and aeronautical SAR air-to-ground frequencies (123.100 MHz / 122.900 MHz).
2. **Expand TDFM-136B Memory Banks to Standard CAP Fleet Channels:**
   * Expand the `memories` table in `logic.lua` to 20+ channels using authentic CAP nomenclature (`CC 1`, `CC 2`, `TAC 1`, `TAC 2`, `AIR 1`, `AIR 2`, `SAR 1`, `VFIRE 21`, `VTAC 11`), supporting valid 3-digit direct entry (e.g., `CHAN 001` through `CHAN 020`).
3. **Add P25 Chirp & Squelch Tail Sidetone Feedback:**
   * Port `playP25Chirp()`, `playP25Tail()`, and `playAmSquelchBurst()` from `radio.js` into `mission-radio.js` to provide operators with tactile acoustic confirmation of channel access.
4. **Correct DF Head Tone Bleed and Decode Anomalies [Bugs I-3, P-6, P-8]:**
   * Scope tone suppression in `cap_df_audio.lua` strictly to AM frequencies.
   * Prevent 121.5 MHz beacons from falsely generating COSPAS-SARSAT digital frames in `PI_capvsar_df.py`.
   * Increase terrain masking attenuation from -12 dB to complete RF blockage (> 40 dB).

### Phase 3: Long-Term Enhancements (Advanced Simulation Architecture)
1. **Dynamic Signal-to-Noise Ratio (SNR) Audio Mixing:**
   * Synthesize real-time background noise in `cap_df_audio.lua` and `radio-worklet.js`, degrading audio intelligibility based on distance, aircraft AGL altitude, and antenna shielding.
2. **ICS Audio Intercom Sub-Routing:**
   * Plumb `cap_ics_isolation` to Mumble whisper lists or subchannels to provide genuine audio isolation between pilot and scanner stations during high-workload phases.
3. **Functional Control Head Softkeys:**
   * Make `MON` (squelch open) and `SCAN` functional on the APX 4500 and EFJohnson 5300 SVG control heads.

