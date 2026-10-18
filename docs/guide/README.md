# CAP V-SAR User Guide & Training Package (`docs/guide/`)

This directory contains the plain-language Civil Air Patrol Emergency Services user guide, role quick-start checklist, glossary, screenshot library, change log, and build tooling for the **CAP V-SAR Simulator & Exercise System**, walking through **Scenario C-1 (`C-1 Palomar ILS - 121.5 ELT at ESCON`)** under exercise title **`CAWG Pauma Valley Mountain SAREX`**.

---

## Files in `docs/guide/`

| File | Format / Description | Size | Pages |
| :--- | :--- | :---: | :---: |
| `CAP_VSAR_Simulator_Exercise_Guide.md` | Master Markdown user guide covering all roles, the ESCON ELT scenario, all 7 operational phases (including Sign in with Google, per-seat email assignment, `mailto:` invitations, and offline badge-code fallback), the "Under development" status table, and Appendix A (including plain-language Google sign-in server setup). | 79.8 KB | — |
| `CAP_VSAR_Simulator_Exercise_Guide.html` | Self-contained single-file HTML guide with base64-embedded screenshots, sticky Table of Contents, role quick-start cards, and `@media print` stylesheet. Can be opened from any file share or emailed as a single file. | 14.8 MB | — |
| `CAP_VSAR_Simulator_Exercise_Guide.docx` | Microsoft Word / Google Docs `.docx` document with embedded high-resolution figures, formatted tables, and numbered procedures. | 11.0 MB | — |
| `CAP_VSAR_Simulator_Exercise_Guide.pdf` | Print-ready PDF manual rendered from the HTML guide with embedded screenshots, TOC, role cards, and figure captions. | 11.6 MB | 41 pages |
| `Quick_Start_by_Role.md` | Markdown source for the one-page printable role checklist sheet (`IC/AOBD/SET`, `MRO 1/2`, `MP/MO/MS`, `UDF 1/2`) covering both Google sign-in and offline badge codes. | 5.7 KB | — |
| `Quick_Start_by_Role.html` | Printable HTML version of the one-page role checklist sheet. | 9.9 KB | — |
| `Quick_Start_by_Role.pdf` | Printable 1-page PDF checklist sheet formatted for US Letter (`8.5" × 11"`). | 163.9 KB | 1 page |
| `Glossary.md` | Plain-language glossary of Civil Air Patrol Emergency Services abbreviations (`CAPR 100-1`, `CAPR 100-3`, `CAPP 100-3`, `CAPF 110`, `ICS 204`, `ICUT`, `MART Vol. II`, `SQTR`, `SET`) and simulator terms (including **Seat**, **Sign-In with Google**, and **Badge Code**). | 11.0 KB | — |
| `CHANGES_T26.md` | Fact-check corrections made in Task T26 (labels, badge prefixes, routing, sample addresses, duplicate screenshots). | 5.1 KB | — |
| `CHANGES_T22.md` | Section-by-section summary of changes made in Task T22 for Google sign-in, per-seat email assignment, no-seat handling, and offline badge fallback. | 8.6 KB | — |
| `build_guide_outputs.py` | Build and verification script that checks plain-language rules (zero forbidden software jargon in main text) and generates the `.html`, `.docx`, and `.pdf` deliverables. | 37.1 KB | — |

---

## Screenshots in `docs/guide/images/`

All 20 figures referenced in `CAP_VSAR_Simulator_Exercise_Guide.md` are stored in `docs/guide/images/`:

1. `01-setup-step1-exercise-details.png` — Exercise Director Setup (`/setup` Step 1: Exercise Details & Identity)
2. `02-setup-step2-fleet-and-seat-emails.png` — Exercise Director Setup (`/setup` Step 2: Fleet, Aircrew, Ground Staff & Per-Seat Google Emails)
3. `03-setup-step3-readiness-review.png` — Exercise Director Setup (`/setup` Step 3: Pre-Save Validation Checks & Planned Seat Manifest; screenshot predates the current button wording)
4. `04-setup-step4-invite-participants-by-email.png` — Exercise Director Setup (`/setup` Step 4: Invite Participants by Email Link & Collapsed Offline Badge Cards)
5. `05-setup-printable-badges.png` — Printable 2-Up Participant Access Badges for Offline / Field Use
6. `06-setup-step5-attendance-google-and-badge.png` — Exercise Director Setup (`/setup` Step 5: Attendance Tracking with Google and Badge Sign-Ins)
7. `07-login-google-signin-and-badge-fallback.png` — Participant Sign-In Page (`/login` with **Sign in with Google** and Offline Badge Fallback)
8. `07c-login-no-seat-assigned.png` — Friendly "There is no seat for you in this exercise" Screen
9. `07b-login-offline-badge-only.png` — Participant Sign-In Page (`/login` in Offline / Field Badge-Only Mode)
10. `08-boarding-pass-desktop.png` — Participant Boarding Pass (`/join/{code}` on Desktop)
11. `09-boarding-pass-mobile.png` — Participant Boarding Pass (`/join/{code}` on Mobile)
12. `10-portal-landing.png` — Participant Home Portal (`/`)
13. `11-ready-room-station-check.png` — Exercise Ready Room (`/ready`)
14. `18-flight-planner-escon-sar.png` — Pre-Flight SAR Pattern Planner (`/planner/` Centered on `ESCON`)
15. `13-mission-base-df-plotting.png` — Mission Base Tactical Map (`/base` with `ESCON` Tracks & LOPs)
16. `14-mission-base-radio.png` — Mission Base Radio Console (`/radio` with PTT & `CAPF 110` Log)
17. `16-panel-becker-sar-df-517.png` — Air Manager `Becker SAR-DF 517` Control Head (`CAP 423`)
18. `17-panel-rhotheta-rt-600.png` — Air Manager `RHOTHETA RT-600` Control Head (`CAP 415`)
19. `12-instructor-exercise-console.png` — Exercise Console (`/instructor` with Scenario C-1 & Signal Faults)
20. `15-debrief-console.png` — After-Action Debrief Console (`/debrief` with Revealed ELT & Scores)

---

## How to Regenerate the Deliverables

### Rebuild `.html`, `.docx`, and `.pdf` from the Markdown Sources

Run `build_guide_outputs.py` with `nice -n 10` using the `/home/ron/.venvs/onb` virtual environment:

```bash
nice -n 10 /home/ron/.venvs/onb/bin/python /home/ron/Projects/cap-vsar-c182-ai-pilot/docs/guide/build_guide_outputs.py
```

This script:
1. Verifies that `CAP_VSAR_Simulator_Exercise_Guide.md` (main text before Appendix A), `Quick_Start_by_Role.md`, and `Glossary.md` contain zero forbidden software jargon terms (`websocket`, `api`, `bridge`, `plugin`, `dataref`, `json`, `token`, `backend`, `router`, `oidc`, `jwt`, `pkce`, `endpoint`).
2. Generates `CAP_VSAR_Simulator_Exercise_Guide.html` (with base64-embedded images) and `Quick_Start_by_Role.html`.
3. Generates `CAP_VSAR_Simulator_Exercise_Guide.docx` via `python-docx`.
4. Renders `CAP_VSAR_Simulator_Exercise_Guide.pdf` and `Quick_Start_by_Role.pdf` via headless Google Chrome (`--print-to-pdf`).
