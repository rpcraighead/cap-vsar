# G1000 NXi upgrade research and proposed plan

Research date: 2026-09-11. Status: proposal; no simulator or runtime changes made.

Decision update, 2026-09-11: the user selected the independent XPPython3
extension route with SAR as a core capability. Implementation now lives in
the sibling `g1000-sar` repository, a separate local Git project. The initial
extension is implemented, packaged and installed. Live acceptance on X-Plane
12.4.3 with XPPython3 4.7.1 covers in-panel and popup rendering, native
softkey/FPL handoff, mission editing, crew marks, native waypoint exchange,
hot reload, avionics and display failures, reversion, dual-GPS failure, pause,
and invalid-schema recovery. From the CAP-VSAR repository root, see
`../g1000-sar/docs/VERIFICATION.md` for the current evidence and remaining
matrix. The original
options research below is retained for reference.

Recommendation: evaluate an existing NXi implementation on the CAP C182T before committing to a full avionics rewrite. Cockpit Vector is the first evaluation candidate because it documents Linux support and aircraft customization. Keep a targeted extension of Laminar's G1000 as the fallback. An NXi appearance alone is insufficient: acceptance must compare button sequences, navigation behavior, aircraft indications, and autopilot annunciations with the intended aircraft.

**Observed project baseline**

- The local X-Plane log identifies 12.4.3-r2, build 124311, running Vulkan. Installed XPPython3 is v4.7.1 for Python 3.12; its `XPLMDisplay.pyi` exposes avionics callbacks and the G1000 PFD/MFD devices. This establishes installed API definitions, not a successful runtime prototype.
- `scripts/build_c182t_package.py` builds a C182T NAV III from Laminar's C172 G1000. The README identifies it as CAP 487. Its constant-speed propeller configuration selects manifold-pressure/RPM engine indications. This does not establish that every engine limit, electrical system, or avionics option matches a real C182T.
- `panels/cap-c182t-mo-station/info.xml` uses a G1000 MFD in the Air Manager observer station. `instruments/g1000-mfd-watchdog/logic.lua` consumes `xpl/G1000_MFD` video. Replacement-display compatibility with this capture path is untested.
- The watchdog currently watches simulator dataref heartbeats; those do not independently prove that new video frames arrive. Include a frozen-video/live-telemetry case in display testing.
- `services/flightplanner/app.py` already generates X-Plane `.fms` routes, including SAR waypoints. `services/ai_pilot/README.md` documents GFC 700 integration and a serialized control lease. An external avionics plugin will not automatically honor that lease.
- No applicable AGENTS.md was found in the project or checked ancestor locations. The working tree contains substantial existing changes; this proposal is a separate new file.

**What an NXi target means**

Garmin's Cessna piston upgrade page covers select 172/182/206 installations. It identifies faster displays, visual approaches, a vertical situation display, and SurfaceWatch, with equipment-dependent additions such as ADS-B weather/traffic and Flight Stream connectivity. These are candidate comparison items, not proof that the target aircraft has them. [Garmin Cessna NXi upgrade](https://www.garmin.com/en-XD/aviation/g1000-nxi-flight-deck-upgrade-for-select-cessna-piston-singles/).

The missing reference is the intended aircraft's tail/model/year, installed NXi software version, enabled options, and matching pilot guide/AFMS. Use the existing CAP C182T as a provisional target. Do not assume that NXi retrofits, factory installations, and different software revisions share identical pages or behavior. Garmin's Cessna NAV III NXi guide is a starting reference to match to the aircraft, not a verified match yet: [Garmin guide, 190-02177-02 Rev. A](https://static.garmin.com/pumac/190-02177-02_a.pdf).

Laminar added synthetic vision and dedicated avionics-monitor output in X-Plane 12.3.0. Our installation is newer. Verify these existing facilities before budgeting replacements; their presence does not turn the stock suite into a complete NXi implementation. [X-Plane 12.3.0 release notes](https://www.x-plane.com/kb/x-plane-12-3-0-release-notes/).

**Available routes**

| Route | Evidence and constraints | Proposed role |
| --- | --- | --- |
| Cockpit Vector NXi | Documents Linux plugin/standalone displays, cockpit replacement, configurable EIS/CAS/checklists, and stock-command interception. Explicitly an active prerelease. | First feasibility trial; C182T and Air Manager compatibility remain unproven. [Documentation](https://cockpitvector.com/docs/g1000-nxi.html) |
| RealSimGear NXi software | Lists $1,495 USD, C172 support, VNAV, VSD, synthetic vision, holds, and aircraft-specific engine/checklist pages. Custom CAP C182T and Linux support are not established by the page reviewed; availability text is ambiguous. | Commercial comparison if platform and aircraft support can be confirmed. [Product](https://realsimgear.com/products/realsimgear-nxi-software-1) |
| COWS NXi | Official site advertises an X-Plane 12 NXi suite with contact-for-pricing. Detailed product page could not be retrieved. | Secondary candidate; availability, Linux, integration, and licensing need confirmation. [COWS](https://www.cows.studio/) |
| SIMiONIC | Offers an iPad NXi app; published X-Plane bridge downloads list Windows/macOS. This does not establish Linux or NXi-specific bridge compatibility. | Consider only if an iPad display architecture is desired. [Downloads](https://www.simionic.net/wordpress/downloads/) |
| Extend Laminar G1000 | SDK permits drawing over/replacing built-in screens and receiving input. It does not automatically supply Garmin NXi navigation logic. | Good for bounded pages and indications; a full replacement is a much larger project. [Avionics SDK](https://developer.x-plane.com/sdk/XPLMDisplay/) |

Cockpit Vector advertises FMS synchronization, procedure selection, VNAV, and external displays. It states freeware is for noncommercial use, with separate commercial licensing. Treat these as vendor claims to verify. Its release catalog did not expose a build identifier in the retrieved text; pin and record the actual evaluated version before testing. [Product](https://cockpitvector.com/products/g1000-nxi.html), [release archive](https://cockpitvector.com/products/g1000-nxi-releases.html).

**Implementation sequence and decision gates**

1. **Define the aircraft and measure the baseline — estimated 1–2 working days once references are available.** Create a feature matrix with reference page/sequence, installed option, stock behavior, candidate behavior, and pass/fail evidence. Prioritize engine/lean/fuel pages, PFD/MFD softkeys, Direct-To/FPL/PROC, VNAV/VSD, and failures. Check native synthetic vision and monitor output. Exit: a ranked, aircraft-specific gap list with unknowns explicitly marked.

2. **Run an isolated NXi compatibility trial — estimated 2–3 days after obtaining a usable build.** Use a disposable aircraft copy and recoverable plugin configuration. Start with AI Pilot inactive. Exercise cold start, PFD/MFD rendering, knobs, long-CLR, reversion, brightness/power, in-cockpit views, pop-outs, and the observer display. Test existing SAR `.fms` import and active-leg agreement. Record release/hash, startup errors, frame time, and rollback steps. Exit: select the replacement only if essential controls, route state, and observer output work. Otherwise use the extension fallback; do not run competing screen/command owners together.

3. **Build the C182T aircraft profile and first useful increment — estimated 3–7 days if the candidate passes.** Derive engine units/limits, fuel quantities/flow, electrical indications, alerts, and any installed electronic checklists from the target references. Compare known injected simulator values with displayed values. Store source profiles under a proposed `avionics/c182t-nxi/` directory and have the aircraft builder install them reproducibly. First release: correct aircraft indications, usable menus, and a synchronized observer display. Visual approaches, terrain alerts, and complex guidance are separate acceptance items.

4. **Validate navigation and control integration — estimated 1–2 weeks for a bounded supported feature set.** Test Direct-To, route edits, approach load versus activation, selected transitions, constraints, holds, missed approach, and CDI-source changes against the chosen reference. Record both annunciations and actual simulator behavior. Start with native/replacement avionics as sole navigation authority. Before enabling AI Pilot, establish whether its commands reach the active avionics/autopilot and implement an explicit ownership/handoff adapter if needed. Initially prevent overlapping AI maneuver control and unvalidated VNAV/approach coupling. Exit: no divergent routes, duplicated commands, or competing autopilot writes in the accepted scenarios.

5. **Package and run regression sorties — estimated 2–3 days.** Preserve the stock aircraft option, make installation/removal reversible, and document supported versions and remaining gaps. Run a representative SAR sortie plus a navigation/approach exercise, power-cycle and aircraft-reload cases, and an observer-display disconnect/reconnect test. Test video freeze separately from loss of telemetry. Verify that missing terrain/weather/navdata is represented correctly. Exit: repeatable results, usable rollback, and no unexplained avionics/control failures.

These are engineering estimates, not delivery commitments. A successful existing-product integration is plausibly a few weeks. Recreating an NXi FMS, flight director, terrain system, and full page suite is a multi-month effort requiring a separate estimate.

**Extension fallback architecture**

Use a separate proposed `xplane/PI_capvsar_avionics.py` plugin and testable page/state modules, rather than drawing avionics in `services/ai_pilot/web_server.py`. XPPython3 supports before/after screen callbacks, suppression of native drawing, and mouse/keyboard handling. Scope registrations to the intended aircraft; release callbacks on disable/unload. [XPPython3 avionics API](https://xppython3.readthedocs.io/en/latest/development/modules/display_avionics.html).

Begin with one reversible MFD page and prove its input ownership and display capture before expanding. Pass native commands through outside custom pages. Reuse simulator aircraft state and native navigation where adequate; label the deliverable an enhanced G1000 until its NXi behavior is demonstrated. A checklist or EIS page is bounded work. VSD requires terrain/path sampling; a coupled visual approach requires procedure geometry, mode transitions, and autopilot validation. Treat SAR mission overlays as project features unless the target Garmin installation explicitly supports the same functions.

**Acceptance evidence to retain**

- Reference-matched screenshots and recorded button sequences for accepted pages.
- Displayed value versus simulator value checks, including units and alert thresholds.
- Navigation traces showing active leg, selected altitude, CDI source, and armed/active flight modes.
- Pilot and observer agreement during route edits, failures, and reconnects.
- Measured frame-time impact against an agreed budget on the same scenario.
- Regression results for existing SAR exports and AI Pilot handoff, plus a successful rollback.

Research was read-only apart from this plan. No product was downloaded, installed, purchased, or runtime-tested, and no vendor was contacted.
