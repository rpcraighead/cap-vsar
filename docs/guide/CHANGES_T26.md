# Changes in Task T26 — Fact-check of the guide after T22/T24

Antigravity's T22 addendum had already been applied to the Markdown sources (ASCII-only emails, invite-message contents,
previous-session replacement, the friendly no-seat screen); the `.html/.docx/.pdf` outputs were stale and are rebuilt by
this task. Corrections made to the text, checked against `services/exercise/app` and `static/`:

## Factual errors fixed
- **Badge-code prefixes:** ground teams are `UDF-<n>-…` (`n` = position in the staff list: `UDF-3` / `UDF-4` in the sample
  roster), never `GT-1` / `GT-2` (guide §2.2, Quick Start §5, Glossary "Badge Code", role cards in the build script).
- **Where seats land after sign-in:** Mission Radio Operators open Mission Base (`/base`), not `/radio`; only ground teams
  land on `/radio` (guide §5.1; Glossary "Sign-In with Google" no longer lists `/instructor`, the director lands on `/`).
- **Setup Step 3 wording:** heading `Review Configuration Readiness & Save Roster`, check list `Pre-Save Validation Checks`,
  chip `Ready to Save`, button **Save Roster & Seat Invites** (was "Generate Roster & Invite Codes" / "Pre-Mint" /
  "Ready to Mint" throughout the guide, Quick Start and §11). Figure 3's screenshot predates this wording; its caption says so.
- **Printing badges:** there is no `/cards` page and no "Print Access Badges" button; the button is **Print Offline Badges**
  (Step 3) and the browser's print view of the Offline Fallback section (guide Step 4, Figure 5 caption, Quick Start,
  Glossary).
- **Role badge text** on invite rows and the attendance table is `BASE`, not `MISSION BASE`.
- **Copy badge link** sits on every invite row, not inside the offline drawer.
- **Section 2B** only (there is no "2C").
- **Debrief outcome thresholds:** `overhead the beacon` is under `0.5 NM` (not `0.25`), `localised` under `2 NM`; the
  "Table view" control does not exist (there is a Replay slider).
- **Cone of confusion:** the simulator models a `30°` cone above the beacon (about `0.35 NM` radius at `4,500 ft MSL`),
  not a fixed `0.25–0.5 NM` band (§8.2, §9).
- **Base Radio log panel:** quick-entry buttons are `Ops Normal` and `Radio Check`; the export is **Export CAPF-110**; the
  log is on `/radio` itself, with the old text console at `/radio-legacy` (§7.2). Unverified buttons (`Bearing Report`,
  `Departing`, `In-Grid`, `Out-of-Grid`, `Overhead`) and "CSV export" removed.
- **Ready Room check buttons** are `Headset tested on the radio page` and `I have read the briefing`.
- **Badge-code error wording** on `/login` ("That badge code was not recognized or was replaced…"), not "Access Badge Not Recognized".
- **"24-hour session"** is the default, not fixed (`CAPVSAR_SESSION_LIFETIME_S`).
- Removed the unverified "30 seconds of silence" claim, the "QR Unavailable" label, the "Check Name" chip, and the
  "8-character" badge wording (badge codes are full codes; the short alias is still under development).

## Sample data and privacy
- Prose and tables now use `@example.org` (reserved example domain) instead of `@cap.gov`, which is Civil Air Patrol's real
  domain. Figure captions keep the placeholder addresses visible in the screenshots and §2.2 says they are placeholders.
  **Worth a retake after the sim is free:** screenshots 02, 04, 06, 07c still show `@cap.gov` samples, and 03 shows the
  old Step 3 wording.
- `CAPVSAR_OIDC_HD` example is now a placeholder rather than a real wing domain.
- `CAPVSAR_ALLOWED_EMAIL_DOMAINS` does not exist in the code and was not mentioned anywhere in the guide; nothing to remove.

## Plain-language pass
- Removed `mailto:`, `@media print`, `callbacks`, and the internal ticket ids `F-8` / `F-10` from the body text.
  (`No server email sent · Use mailto or Copy Link` stays only as the literal on-screen label.)

## Images
- Deleted the four byte-identical duplicates (`02-…-fleet-and-staff`, `04-…-invite-badges`, `06-…-attendance-tracking`,
  `07-participant-login`); the 20 remaining files are each referenced exactly once by the guide. README updated.

## Verified and left as is
ESCON fix geometry (`33.1700° N, 117.0792° W`, `700 ft`, `3,300 ft` ILS crossing, `076.01° T` / `10.40 NM` from KCRQ),
the `12 NM` alert ring and alert text, ELT bands `121.5 / 243 / 406` MHz and the `406.022–406.076` MHz grid, multipath `40°`,
wing blanking `24 dB`, `406` burst every `50 s`, the `10°` good-cut band, Ramona ridge `3,977–4,526 ft` and the `6,000 ft`
guard floor with `700 fpm` climb (GFC 700 trial report), search speeds `90` KIAS (C172SP) / `100` KIAS (C182T), planner
waypoint names `DATUM`, `SS01…`, the 99/97-waypoint `.fms` limit, voice channel names, DF instrument descriptions, and
TDFM-136B / GMA 1347 details (RADIO_FEATURES_AND_USE_CASES.md).

## Not verifiable from the repository
AI Mission Pilot throttle ratios (`0.73–0.75`, `0.57–0.59`), climb caps (`340` / `595 fpm`), altitude hold `25–30 ft`,
cross-track `6–11 m` and bank `21–35°` come from flight-trial reports, not from code or profile files; the `11° East`
magnetic variation, SoCal Approach `127.30 MHz`, and the Icom IC-A120 `123.100 MHz` watch are aviation facts outside the
repository. Left unchanged.

## Rebuild and Figure 14 retake (after "sim finished")
- Figure 14 (`images/18-flight-planner-escon-sar.png`) retaken: the old capture (2026-10-11) showed the planner's
  "Simulation use only" dialog over a sample KSEE–KPSP flight with no search pattern. The new capture was made on a
  locally started planner (`python app.py`, `nice -n 10`, stopped afterwards) using the Scenario C-1 datum from the repo
  (`@33.1700,-117.0792`), the notice acknowledged with its button, the SAR generator run as a user would (Expanding
  Square, 1.0 NM, 8 legs, heading 0, right turns, Preview on Map, Apply to Route) over a `KCRQ KRNM` route. FAA VFR
  Sectional tiles only (public domain, attribution control visible); no email addresses on screen. Caption rewritten
  to match; §6.2 steps corrected (no "Search Altitude" field in the dialog; buttons are **Preview on Map**,
  **Apply to Route**, **Export X-Plane .FMS**, **Push to V-SAR Console**).
- `.html`, `.docx`, `.pdf` for the guide and the Quick Start rebuilt with `build_guide_outputs.py` (language check:
  zero forbidden terms); README sizes and page counts refreshed from the files.
- `.gitignore` at the repo root now ignores `docs/guide/*.html|docx|pdf` and `.~lock.*#`: the outputs are rebuilt on
  demand, not versioned. The LibreOffice lock file was left in place because Writer still had the `.docx` open.
