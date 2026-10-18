# CAP V-SAR Glossary of Terms

This glossary explains Civil Air Patrol Emergency Services abbreviations, aviation terms, and CAP V-SAR simulator terms in plain language.

---

## A

- **After-Action Debrief (`/debrief`):** The post-exercise review screen where the Incident Commander, Skills Evaluation Trainer (`SET`), and aircrews inspect recorded flight tracks, closest point of approach (`CPA`), bearing error in degrees, and the `CAPF 110` communications log.
- **AI Mission Pilot:** The automated left-seat pilot in CAP V-SAR that flies the simulated Cessna 182T Skylane (`CAP 487`) or Cessna 172SP, operates the Garmin GFC 700 autopilot, and executes search patterns while protecting terrain clearance over the Ramona ridge (`6,000 ft MSL` floor).
- **Air Operations Branch Director (AOBD):** The Mission Base officer who generates search patterns in the Flight Planner (`/planner/`), assigns altitude blocks (`ICS 204`), and monitors airborne tracks and plotted lines of position on `/base`.
- **Autopilot (Garmin GFC 700):** The flight control system integrated into the Garmin G1000 flight deck that holds heading (`HDG`), navigation course (`NAV`), pitch attitude (`PIT`), vertical speed (`VS`), flight level change (`FLC`), or altitude hold (`ALT`).

## B

- **Badge Code:** The participant sign-in code (such as `INSTR-1-...`, `MRO-1-...`, `OBS-423-...`, or `UDF-3-...`) printed on a participant's badge card from the **Offline Fallback: Badge Cards** section of `/setup` Step 4 (or **Print Offline Badges** in Step 3). When internet access is unavailable at a field site (such as an off-grid ESCON briefing) or a seat has no email address assigned, entering the badge code at `/login` or scanning its QR code (`/join/{code}`) signs the participant directly into their assigned station.
- **Becker SAR-DF 517:** The airborne direction-finding instrument used in CAP aircraft (`CAP 423`) to display the relative bearing (`0°` to `359°` relative to the aircraft nose) and signal strength of a 121.5 MHz or 243.0 MHz emergency beacon, including a `STORE` button that suppresses the 3 kHz audio tone for aural null homing.

## C

- **CAPF 110 (Communications Log):** The standard Civil Air Patrol form maintained by the Mission Radio Operator on `/radio` and `/base` to record every radio transmission with a UTC (Zulu) timestamp, calling station (`FROM`), called station (`TO`), and message summary.
- **CAPP 100-3 (Standard Radio Communications Guide):** The Civil Air Patrol guide covering tactical radio operations, standard prowords, and air-to-ground communications discipline.
- **CAPR 100-1 (Radio Communications Policy):** The Civil Air Patrol regulation governing radio communications policy, station identification, and communications logging.
- **CAPR 100-3 (Radiotelephone Procedures):** The Civil Air Patrol regulation governing voice radio operating procedures and standard radiotelephone phraseology.
- **Closest Point of Approach (CPA):** The shortest horizontal distance (in nautical miles) between an aircraft's recorded flight track and the true ELT position, scored on `/debrief`.
- **Cockpit Intercom:** The private audio channel inside a single aircraft (`CAP 423` or `CAP 415`) that connects the Mission Pilot, Mission Observer, and Mission Scanner without broadcasting over external radio nets.
- **Cone of Confusion:** The inverted cone directly above a ground transmitter where horizontal direction-finding signal components vanish and the bearing needle swings rapidly and reverses `180°` upon station passage.
- **Creeping Line Search (`CS`):** A parallel-track electronic or visual search pattern flown perpendicular to the major axis of a route or approach corridor (`ESCON` ILS Runway 24 localizer course).

## E

- **Electronic Search:** An aerial or ground search mission focused on locating an emergency radio beacon (121.5 MHz or 406 MHz ELT) using direction-finding equipment and signal-strength metering.
- **ELT (Emergency Locator Transmitter):** A battery-powered distress radio beacon carried aboard aircraft that activates upon impact (or manually during a training exercise) to transmit a warbling sweep tone on `121.5 MHz` (and digital bursts on `406.025 / 406.028 MHz`).
- **ESCON (`33.1700° N, 117.0792° W`):** The charted intermediate fix on the McClellan-Palomar (`KCRQ`) ILS or LOC Runway 24 instrument approach, located in the inland valley between Escondido and Valley Center (`065°` magnetic / `076.01°` true at `10.40 NM` DME from `I-CRQ`, terrain elevation approximately `700 ft MSL`). In Scenario C-1 (`C-1 Palomar ILS - 121.5 ELT at ESCON`), a practice 121.5 MHz ELT (`EX-ESCON-1215`) is placed near `ESCON`.
- **Expanding Square Search (`SS`):** A systematic search pattern centered on a known point or fix (`ESCON`) that spirals outward in 90-degree right-hand turns (`DATUM` through `SS08`), increasing leg length by one track spacing (`1.0 NM`) every two legs.

## G

- **Garmin G1000 (PFD / MFD):** The integrated glass flight deck in the Cessna 182T NAV III Skylane, consisting of the Primary Flight Display (`PFD`) on the left and the Multi-Function Display (`MFD`) moving map on the right.
- **Garmin GMA 1347:** The cockpit audio panel used by the Mission Pilot and Mission Observer to select transmit (`COM1`, `COM2`, `COM3`) and receive (`COM1`, `COM2`, `COM3`, `AUX`) audio sources.

## I

- **Icom IC-A120:** The simulated VHF-AM airband base radio on `/radio` used by `MRO 2` to monitor `123.100 MHz` SAR airband and `121.500 MHz` guard.
- **ICS 204 (Assignment List):** The Incident Command System form used to assign an aircrew (`CAP 423`), aircraft (`CAP 487`), search area (`ESCON`), altitude block (`4,500 ft MSL`), and radio frequencies for a specific sortie.
- **ICUT (Introductory Communications User Training):** The baseline Civil Air Patrol radio communications training qualification required before operating CAP radios.
- **Incident Commander (IC):** The officer responsible for overall mission command, safety, sortie tasking, and exercise control at `/setup`, `/instructor`, and `/base`.

## L

- **Line of Position (LOP):** A plotted true bearing line drawn on the Mission Base map (`/base`) from an aircraft's GPS coordinates along the reported true bearing toward the ELT. Where two or more LOPs cross indicates the estimated beacon location.

## M

- **MART Vol. II (Mission Aircrew Reference Text, Volume II):** The Civil Air Patrol Mission Observer and SAR/DR reference manual covering visual search, electronic search patterns, and direction-finding procedures.
- **Mission Base (`/base`):** The ground command post screen where the Incident Commander, Air Operations Branch Director, and Mission Radio Operator track aircraft, plot DF lines of position, and manage tasking.
- **Mission Observer (MO):** The right-seat aircrew member (`OBS-423`, `OBS-415`) responsible for navigation, radio communications (`TDFM-136B` and `GMA 1347`), direction finding (`Becker SAR-DF 517` or `RHOTHETA RT-600`), and reporting bearings and Ops Normal calls to Mission Base.
- **Mission Radio Operator (MRO):** The ground station operator (`MRO 1`, `MRO 2`) at `/radio` who operates the base radios, maintains the `CAPF 110` log, and tracks 30-minute Ops Normal check-ins.
- **Mission Scanner (MS):** The rear-seat aircrew member (`SCN-423`) responsible for visual scanning outside the aircraft, terrain/traffic lookout, and assisting the Mission Observer with chart orientation.
- **Motorola APX 4500 / EFJohnson 5300:** The simulated VHF-FM tactical radio control head on `/radio` used by `MRO 1` and `UDF` ground teams on the Primary and Alternate SAR nets.
- **MSL (Mean Sea Level):** Altitude measured in feet above average sea level, as read on the aircraft barometric altimeter.
- **Multipath Reflection:** Signal distortion caused when VHF radio waves bounce off steep terrain (such as the Ramona ridge east of `ESCON`), deflecting the DF bearing needle away from the true line of sight.

## O

- **Ops Normal Report:** A mandatory periodic safety report (every 30 minutes per the exercise communications plan) transmitted by each airborne sortie and ground team to Mission Base confirming normal operations.

## P

- **Parallel Track Search (`PS`):** A rectangular grid search pattern consisting of parallel legs spaced evenly across a search box, generated in `/planner/`.
- **Push-to-Talk (PTT):** The microphone key switch (`Space` bar or the on-screen **PUSH TO TALK (SPACE)** button on `/radio`) held down while speaking on the selected radio channel and released to listen.

## R

- **RHOTHETA RT-600:** The multi-band airborne direction-finding unit (`121.5 MHz` and `406.028 MHz` COSPAS-SARSAT hex ID decode) installed in `CAP 415`.

## S

- **SAREX (Search and Rescue Exercise):** A structured Civil Air Patrol training exercise simulating real-world emergency services missions so aircrews and ground staff can earn or maintain qualifications.
- **Seat:** An individual crew or staff position in an exercise roster—such as the Exercise Director (`INSTR-1`), Mission Radio Operator (`MRO 1`, `MRO 2`), Mission Pilot (`PLT-423`), Mission Observer (`OBS-423`), Mission Scanner (`SCN-423`), or Ground UDF Team (`UDF 1`, `UDF 2`). In `/setup` Step 2, the Exercise Director can assign one Google email address to each seat (or leave the email box blank for badge-only use). Each email address can be assigned to at most one seat per exercise.
- **SET (Skills Evaluation Trainer):** The Civil Air Patrol qualification authorizing an experienced member to evaluate trainees on Specialty Qualification Training Record (`SQTR`) tasks.
- **Sign-In with Google:** The primary way volunteers join an exercise at `/login`. When the Exercise Director assigns a member's Google email address to a seat in `/setup` Step 2, clicking **Sign in with Google** at `/login` verifies that email account and opens that member's assigned station (`/base`, `/radio`, or `/`) automatically without typing a badge code.
- **SoCal Approach (`127.30 MHz`):** The Southern California TRACON air traffic control facility responsible for the airspace around McClellan-Palomar (`KCRQ`), Ramona (`KRNM`), and the `ESCON` intermediate fix.
- **Sortie:** A single flight by one aircraft (`CAP 423` or `CAP 415`) or deployment of one ground team (`UDF 1` or `UDF 2`) to perform an assigned mission task.
- **SQTR (Specialty Qualification Training Record):** The official Civil Air Patrol checklist of training tasks required to qualify as a Mission Observer, Mission Scanner, Mission Pilot, UDF technician, or Mission Radio Operator.
- **Station:** Any participant seat or radio position in the simulator (`IC`, `MRO 1`, `MRO 2`, `CAP 423`, `CAP 415`, `UDF 1`, `UDF 2`, or the AI Mission Pilot).

## T

- **Technisonic TDFM-136B:** The airborne P25 VHF-FM tactical radio installed in CAP aircraft (`COM3` on the GMA 1347 audio panel) for communicating with Mission Base and UDF ground teams.

## U

- **Urban Direction Finding (UDF) Team (`UDF 1`, `UDF 2`):** A mobile ground team equipped with a vehicle VHF-FM radio (`/radio`) and handheld direction finder that drives to the airborne LOP intersection to locate and silence the ELT on foot.
