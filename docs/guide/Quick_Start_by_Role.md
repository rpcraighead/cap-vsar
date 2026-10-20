# CAP V-SAR Quick Start by Role (Printable One-Page Sheet)

**Exercise:** `CAWG Pauma Valley Mountain SAREX` | **Scenario:** `C-1 Palomar ILS - 121.5 ELT at ESCON` (`33.1700° N, 117.0792° W`, `700 ft MSL`)
**Safety Notice:** Begin exercise radio calls with **"EXERCISE TRAFFIC"** (`CAPR 100-1`, `CAPR 100-3`, `CAPP 100-3`). Supplemental training tool only.

---

## 1. Incident Commander (IC) / Exercise Director / SET (`INSTR-1`)

1. **Configure Exercise & Assign Seat Emails (`/setup`):** Sign in with your Exercise Director Google account (or initial director badge code), enter title `CAWG Pauma Valley Mountain SAREX` (Step 1), configure aircraft `CAP 423` (`CAP 487`, C182T G1000, Becker 517) and `CAP 415` (`N415CP`, RHOTHETA RT-600) plus `MRO 1/2`, `UDF 1/2`, and Director seats with each volunteer's Google email address in Step 2 (leave any seat email blank for badge-only use), click **Save Roster & Seat Invites** (Step 3), and send invites via **Copy sign-in link** or **Email this invite** in Step 4 (expand **Offline Fallback: Badge Cards** or click **Print Offline Badges** to print backup badge/QR cards for no-internet field use).
2. **Track Who Has Joined (Step 5 & `/ready`) & Launch Sortie (`/instructor`):** Verify each seat's sign-in status (**Signed in with Google** or **Signed in with badge**) in `/setup` Step 5 and confirm stations are ready in `/ready`. Open `/instructor`, select `C-1 Palomar ILS - 121.5 ELT at ESCON`, click **Start Exercise**, and manage signal propagation faults (Terrain Masking, Multipath, Cone of Confusion, Wing Blanking).
3. **Conduct Debrief (`/debrief`):** Click **Reveal ELT Position** after ground find (`EX-ESCON-1215`) and review closest point of approach (CPA), bearing error, and `CAPF 110` log discipline on `/debrief` for `SQTR` / `SET` feedback.

---

## 2. Air Operations Branch Director (AOBD) & Mission Safety Officer (`/planner/`, `/base`)

1. **Generate Search Pattern (`/planner/`):** Select **Expanding Square (`SS`)** centered on `ESCON` (`33.1700° N, 117.0792° W`), `1.0 NM` track spacing, `4,500 ft MSL` for `CAP 423` (`5,500 ft MSL` high cover for `CAP 415`), and export the `.fms` flight plan for the Garmin G1000.
2. **Brief Airspace & Terrain Safety:** Brief the `3,300 ft MSL` McClellan-Palomar (`KCRQ`) ILS Runway 24 approach altitude at `ESCON` and the `6,000 ft MSL` terrain clearance floor over the Ramona ridge (`3,977–4,526 ft MSL`) east of `117.05° W`.
3. **Track Sorties & Plot LOPs (`/base`):** Watch live aircraft tracks and plotted red dashed bearing lines of position (LOPs) on `/base`; vector `UDF 1` to the LOP intersection near Highway 76 / Valley Center Rd.

---

## 3. Mission Radio Operator (`MRO 1` / `MRO 2`) & MSA (`/radio`, `/base`)

1. **Sign In (`/login` → `/ready` → `/radio`):** Open `/login` and click **Sign in with Google** using the email assigned to `MRO 1` or `MRO 2` (or enter your offline badge code / scan your QR card if working without internet). If you see *"There is no seat for you in this exercise"*, switch to the Google account your director assigned or ask the director to add your email in `/setup`. On `/radio`, click **Join Voice Net** on the **Primary SAR Net** (`Motorola APX 4500` for `MRO 1`; `Icom IC-A120` airband watch for `MRO 2`).
2. **Operate PTT & Maintain `CAPF 110` Log:** Hold **PUSH TO TALK (SPACE)** to answer check-ins, departure calls, and bearing reports using standard prowords (`CAPR 100-3`). Record every transmission in the **CAP Form 110** log with station callsigns, UTC time, and message text.
3. **Track 30-Minute Ops Normal & Taskings:** Log 30-minute **Ops Normal** reports from `CAP 423`, `CAP 415`, and `UDF 1/2`, and post bearing cuts (`FROM`, `TRUE BEARING`, `QUALITY`) so they plot on the **Mission Base** (`/base`) map.

---

## 4. Aircrew: Mission Pilot (`MP`), Mission Observer (`MO`), Mission Scanner (`MS`) (`CAP 423` / `CAP 415`)

1. **Sign In & Pre-Flight (`/login` → `/ready`):** At `/login`, click **Sign in with Google** using the email assigned to your crew seat (`PLT-423`, `OBS-423`, `SCN-423`, `PLT-415`, `OBS-415`)—or use your offline badge code / QR card (`/join/{code}`)—to open your station (`/base` and `/ready`). Verify the **Mission Master Switch** is `ON`, check the **Garmin GMA 1347** audio panel (`COM1` SoCal Approach, `COM3` Technisonic TDFM-136B tactical FM, `AUX` DF audio), and load the `ESCON` `.fms` pattern on the G1000 MFD.
2. **Fly the Search Pattern & Coordinate with AI Mission Pilot:** Maintain `4,500 ft MSL` (`CAP 423`) at `100 KIAS` (or supervise the **AI Mission Pilot** / **Garmin GFC 700** autopilot in `NAV` or `HDG` + `ALT` mode, respecting the `6,000 ft MSL` Ramona ridge floor).
3. **Track the 121.5 MHz ELT & Report Bearings:** Monitor the **Becker SAR-DF 517** (`CAP 423`) or **RHOTHETA RT-600** (`CAP 415`) with wings level (`< 5°` bank). Use `STORE` (3 kHz tone suppression) for aural null confirmation, identify the `180°` needle reversal in the **cone of confusion** directly over `ESCON`, and report true bearings + 30-minute Ops Normal calls to `Mission Base`.

---

## 5. Ground Search / UDF Team (`UDF 1` / `UDF 2`) (`/radio`)

1. **Sign In & Monitor Net (`/login` → `/ready` → `/radio`):** Click **Sign in with Google** at `/login` with the email assigned to `UDF 1` or `UDF 2` (or use the offline badge code from your printed card at an off-grid ESCON field site), join the **Primary SAR Net** on `/radio`, and copy the airborne LOP intersection coordinates near `ESCON` (`33.1700° N, 117.0792° W`).
2. **Home In & Report Find:** Conduct ground DF homing along the Valley Center / Highway 76 corridor, locate the practice beacon, and transmit `"EXERCISE TRAFFIC — Mission Base, UDF 1, practice ELT located, ID EX-ESCON-1215"` for entry in the `CAPF 110` log.
