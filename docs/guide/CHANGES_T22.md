# Changes in Task T22 — Google Sign-In, Per-Seat Email Assignment & Offline Badge Fallback

This document lists every section updated across `docs/guide/` for Task T22.

---

## 1. `CAP_VSAR_Simulator_Exercise_Guide.md` (and rebuilt `.html`, `.docx`, `.pdf`)

- **Role Quick-Start Cards Banner (HTML/PDF header):**
  - Updated all four role cards (`IC / AOBD / SET`, `MRO 1 & MRO 2`, `MP / MO / MS`, and `UDF 1 & UDF 2`) to show signing in with Google at `/login` as the primary path and the 8-character/full badge code or QR card as the offline/field fallback.
- **Table of Contents:**
  - Updated Section 4 title to `Phase 1: Exercise Director Setup, Seat Emails, and Invitations (/setup)`.
  - Updated Section 5 title to `Phase 2: Participant Sign-In (Google & Offline Badge), Boarding Pass, and Ready Room (/login, /join, /ready)`.
- **Section 2.2 (`Exercise Force Package and Fictional Sample Data`):**
  - Added sample assigned Google email addresses (`director.ic@cap.gov`, `mro1@cap.gov`, `pilot.423+sar@cap.gov`, `observer.423@cap.gov`, `pilot.419@cap.gov`, `udf1@cap.gov`) alongside badge-only seats (`SCN-423`, `OBS-415`, `UDF 2`) to illustrate mixed Google and badge-only seat provisioning.
- **Section 3 (`Positions, Roles, and Who Does What`):**
  - Updated the introduction, `3.1 Incident Commander (IC) / Exercise Director`, and `3.2 Ground Search / Urban Direction Finding Team` to describe per-seat Google email assignment in `/setup`, `Email this invite` (`mailto:`) / link sharing, and offline badge fallback at field sites without internet.
- **Section 4 (`Phase 1: Exercise Director Setup, Seat Emails, and Invitations (/setup)`):**
  - **Step 1 (`/setup` — Step 1):** Noted the Exercise Director's signed-in identity chip (`· Google` and email address when signed in via Google).
  - **Step 2 (`/setup` — Step 2):** Replaced the outdated screenshot with `images/02-setup-step2-fleet-and-seat-emails.png` (`Figure 2`). Documented how the director enters optional Google email addresses for each aircrew seat (`Mission Pilot`, `Mission Observer`, `Mission Scanner`), ground staff row (`MRO 1`, `MRO 2`, `UDF 1`, `UDF 2`), and the Exercise Director seat (`director.ic@cap.gov`), including the one-seat-per-email uniqueness rule, automatic trim/lowercase normalization (preserving dots and `+tags`), and leaving seats blank for badge-only use.
  - **Step 3 (`/setup` — Step 3):** Documented that clicking **Generate Roster & Invite Codes** saves all seat email assignments, rotates backup badge codes, signs out previous participant sessions, and keeps the Exercise Director signed in automatically.
  - **Step 4 (`/setup` — Step 4):** Replaced the outdated screenshot with `images/04-setup-step4-invite-participants-by-email.png` (`Figure 4`) while retaining `images/05-setup-printable-badges.png` (`Figure 5`). Documented the primary **Invite Participants** list (`Copy sign-in link`, `Email this invite` `mailto:` draft naming the exercise, seat, and site address with no server email sent, and `Copy badge link`) and the collapsible **Offline Fallback: Badge Cards** section for printing backup QR/badge sheets.
  - **Step 5 (`/setup` — Step 5):** Replaced the outdated screenshot with `images/06-setup-step5-attendance-google-and-badge.png` (`Figure 6`). Documented the **Assigned Email** column (visible only to the Exercise Director/Instructor) and the **Last Sign-In** column (`Signed in with Google` + UTC timestamp, `Signed in with badge` + UTC timestamp, or `Not signed in yet`).
- **Section 5 (`Phase 2: Participant Sign-In (Google & Offline Badge), Boarding Pass, and Ready Room (/login, /join, /ready)`):**
  - **Section 5.1 (`Signing In with Google at /login (Primary Path)`):** Replaced the outdated `/login` screenshot with `images/07-login-google-signin-and-badge-fallback.png` (`Figure 7`). Documented clicking **Sign in with Google**, automatic routing to the screen for each role (`/base`, `/radio`, `/`), the `· Google` identity chip in the top bar, and clicking the identity chip (or **Sign out**) to end the simulator session and switch seats.
  - **Section 5.2 (`What to Do If You See "There Is No Seat for You" or Sign In with the Wrong Account`):** Added new section and screenshot `images/07c-login-no-seat-assigned.png` (`Figure 8`). Explained what to do when a volunteer signs in with the wrong Google account (e.g., personal Gmail instead of CAP email) or when their email has not yet been assigned in `/setup`, as well as plain-language recovery steps for cancelled sign-ins, expired/cross-browser links, offline outages, and rate limits.
  - **Section 5.3 (`Signing In with a Badge Code or QR Card — Offline and Field Fallback (/login and /join/{code})`):** Added `images/07b-login-offline-badge-only.png` (`Figure 9`) alongside the desktop and mobile boarding pass views (`Figures 10 & 11`) and Participant Home Portal (`Figure 12`), explaining offline/field use when internet access to Google is unavailable at the ESCON site.
  - **Section 5.4 (`Completing Pre-Flight Checks in the Ready Room (/ready)`):** Updated `Figure 13` text to note that `joined` turns green whether the volunteer signed in with Google or a badge code.
- **Sections 6–10 (`Figures 14–20`):**
  - Renumbered figures sequentially from `Figure 14` through `Figure 20`.
- **Section 11 (`Capabilities Currently Under Development`):**
  - Updated `/setup` rows to reflect that per-seat Google sign-in and `mailto:` invite links are active, while automated server-sent email/SMS dispatch (`No server email sent · Use mailto or Copy Link`) and single-seat session revocation without re-saving Setup (`Not yet tracked`) remain listed with their current workarounds.
- **Section 12 (`Appendix A: Technical Staff Setup and System Administration`):**
  - Updated `A.1` and `A.2` to mention seat email storage and Google/badge sign-in.
  - Added **Section A.4 (`Setting Up Sign-In with Google (Plain-Language Guide for Server Operators)`)**, summarizing `/tmp/cap-vsar-oidc/OPERATOR.md` in plain language (creating the Google Web Application OAuth Client ID and Secret, setting the Authorized Redirect URI `https://<your-console-host>/auth/oidc/callback`, pasting the `CAPVSAR_OIDC_*` variables into `.env`, restarting and testing, offline behavior, and pointing to `/tmp/cap-vsar-oidc/OPERATOR.md` for technical details).

---

## 2. `Quick_Start_by_Role.md` (and rebuilt `.html`, `.pdf`)

- **Section 1 (`Incident Commander (IC) / Exercise Director / SET`):** Updated Step 1 and Step 2 to cover signing in with Google, entering each volunteer's Google email address per seat in `/setup` Step 2, sending invites via **Copy sign-in link** or **Email this invite** in Step 4, expanding **Offline Fallback: Badge Cards** for no-internet field use, and checking **Signed in with Google** / **Signed in with badge** in Step 5.
- **Section 3 (`Mission Radio Operator (MRO 1 / MRO 2) & MSA`):** Updated Step 1 to cover clicking **Sign in with Google** at `/login` (or using the offline badge code / QR card) and how to recover if *"There is no seat for you in this exercise"* appears.
- **Section 4 (`Aircrew: Mission Pilot, Mission Observer, Mission Scanner`):** Updated Step 1 to cover signing in with Google at `/login` (or using the offline badge code / QR card).
- **Section 5 (`Ground Search / UDF Team (UDF 1 / UDF 2)`):** Updated Step 1 to cover signing in with Google at `/login` (or using the offline badge code at an off-grid ESCON field site).

---

## 3. `Glossary.md`

- **Badge Code (`B`):** Updated definition to explain its role as the offline/field fallback in `/setup` Step 4 (**Offline Fallback: Badge Cards**) and `/cards` when internet access is unavailable or a seat has no email assigned.
- **Seat (`S`):** Added definition explaining individual crew and staff positions in the exercise roster and the one-email-per-seat assignment rule in `/setup` Step 2.
- **Sign-In with Google (`S`):** Added definition explaining Google sign-in at `/login` and automatic routing to the assigned station.

---

## 4. `build_guide_outputs.py` & `README.md`

- **`build_guide_outputs.py`:**
  - Added `"oidc"`, `"jwt"`, `"pkce"`, and `"endpoint"` to `FORBIDDEN_JARGON` so the build script enforces zero technical authentication jargon in the main body text, Quick Start, and Glossary.
  - Updated `role_cards_html` in `build_main_html()` for Google sign-in and per-seat email assignment.
  - Enhanced Markdown list parsing (`* ` and `- ` unordered lists, nested sub-bullets, and wrapped list continuation lines) in `markdown_to_html_blocks()` and `build_main_docx()` so all bulleted lists render cleanly in HTML, PDF, and DOCX.
- **`README.md`:**
  - Updated the file table, page counts, and 20-screenshot inventory in `docs/guide/images/`.
