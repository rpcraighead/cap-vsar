/**
 * CAP V-SAR Exercise & Fleet Setup Controller
 * Manages 5-step onboarding workflow, fleet & per-seat Google email assignment,
 * inline client + server 422 validation, mailto/link invitations, collapsible
 * offline QR badge cards, and live attendance / Ready Room tracking.
 */
(function() {
    // F-6: setup is round-tripped through /api/setup, so these cards render
    // server-supplied strings. Escape before building HTML, including the
    // quote, because several values land inside attribute values.
    const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c =>
        ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

    let currentSetup = {
        name: "Civil Air Patrol SAREX Exercise",
        director_email: "",
        num_aircraft: 1,
        aircraft: [
            {
                id: "ac-1",
                callsign: "CAP 423",
                tail: "CAP 487",
                df_model: "Becker SAR-DF 517",
                crew: ["pilot", "observer", "scanner"],
                emails: {}
            }
        ],
        staff: [
            { role: "base", title: "Mission Radio Operator 1", callsign: "MRO 1" },
            { role: "base", title: "Mission Radio Operator 2", callsign: "MRO 2" },
            { role: "ground_team", title: "Ground Search Team 1", callsign: "UDF 1" }
        ],
        staffEmails: {
            "MRO 1": "",
            "MRO 2": "",
            "UDF 1": "",
            "UDF 2": ""
        }
    };

    let currentRoster = [];
    let latestReadyData = null;
    let oidcProviderInfo = { enabled: false, label: "Sign in with Google", login_url: "/auth/oidc/login", issuer_host: "" };
    let activeRoleFilter = "all";
    let activeSearchQuery = "";
    let activeStep = 1;

    // DOM Elements
    const exNameInput = document.getElementById("exName");
    const exNameCharCount = document.getElementById("exNameCharCount");
    const exNameValidation = document.getElementById("exNameValidation");
    const step1StatusChip = document.getElementById("step1StatusChip");
    const setupOidcStatus = document.getElementById("setupOidcStatus");
    const setupLastUpdated = document.getElementById("setupLastUpdated");
    const aircraftGrid = document.getElementById("aircraftGrid");
    const directorEmailInput = document.getElementById("directorEmailInput") || document.getElementById("directorEmail");
    const setupValidationBanner = document.getElementById("setupValidationBanner");
    const saveSetupBtn = document.getElementById("saveSetupBtn");
    const saveSetupBtnLabel = document.getElementById("saveSetupBtnLabel");
    const resetSetupBtn = document.getElementById("resetSetupBtn");
    const printBadgesBtn = document.getElementById("printBadgesBtn");
    const copyAllLinksBtn = document.getElementById("copyAllLinksBtn");
    const inviteList = document.getElementById("inviteList");
    const offlineBadgeFallback = document.getElementById("offlineBadgeFallback");
    const offlineBadgeCountChip = document.getElementById("offlineBadgeCountChip");
    const rosterGrid = document.getElementById("rosterGrid");
    const rosterCount = document.getElementById("rosterCount");
    const rosterSearchInput = document.getElementById("rosterSearchInput");
    const userBadge = document.getElementById("userBadge");
    const userBadgeText = document.getElementById("userBadgeText");
    const logoutBtn = document.getElementById("logoutBtn");
    const themeToggleBtn = document.getElementById("themeToggleBtn");
    const zuluClock = document.getElementById("zuluClock");
    const refreshAttendanceBtn = document.getElementById("refreshAttendanceBtn");
    const attendanceTableBody = document.getElementById("attendanceTableBody");
    const attendanceLastSync = document.getElementById("attendanceLastSync");
    const toastContainer = document.getElementById("onbToastContainer");

    async function init() {
        initTheme();
        startZuluClock();
        await loadProviders();
        await checkAuth();
        await loadSetup();
        await loadReadyStatus();
        bindEvents();
    }

    function initTheme() {
        try {
            const saved = localStorage.getItem("cap_vsar_theme");
            if (saved === "light" || saved === "dark") {
                document.documentElement.setAttribute("data-theme", saved);
                document.body.setAttribute("data-theme", saved);
            }
        } catch (e) {
            // Ignore storage errors in restricted contexts
        }
    }

    function toggleTheme() {
        const current = document.documentElement.getAttribute("data-theme");
        const prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
        const effective = current || (prefersLight ? "light" : "dark");
        const next = effective === "light" ? "dark" : "light";
        document.documentElement.setAttribute("data-theme", next);
        document.body.setAttribute("data-theme", next);
        try {
            localStorage.setItem("cap_vsar_theme", next);
        } catch (e) {
            // Ignore storage errors
        }
        showToast(`Switched to ${next} display theme`, "info");
    }

    function startZuluClock() {
        const tick = () => {
            const now = new Date();
            const iso = now.toISOString();
            if (zuluClock) {
                zuluClock.textContent = iso.slice(11, 19) + "Z";
            }
            const printTs = document.getElementById("printTimestamp");
            if (printTs) {
                printTs.textContent = "ISSUED " + iso.slice(0, 10) + " " + iso.slice(11, 16) + "Z";
            }
        };
        tick();
        setInterval(tick, 1000);
    }

    function showToast(message, tone) {
        if (!toastContainer) return;
        const toast = document.createElement("div");
        const toneClass = tone === "good" || tone === "warn" || tone === "danger" ? tone : "info";
        toast.className = `onb-toast ${toneClass}`;
        toast.textContent = message;
        toastContainer.appendChild(toast);
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 3200);
    }

    async function loadProviders() {
        try {
            const res = await fetch("/api/auth/providers", { cache: "no-store" });
            if (!res.ok) return;
            const data = await res.json();
            if (data && data.oidc) {
                oidcProviderInfo = data.oidc;
            }
            if (setupOidcStatus) {
                if (oidcProviderInfo.enabled) {
                    const hostInfo = oidcProviderInfo.issuer_host ? ` (${oidcProviderInfo.issuer_host})` : "";
                    setupOidcStatus.textContent = `Enabled${hostInfo}`;
                } else {
                    setupOidcStatus.textContent = "Offline / Badge mode (not configured)";
                }
            }
        } catch (e) {
            if (setupOidcStatus) {
                setupOidcStatus.textContent = "Offline / Badge mode";
            }
        }
    }

    async function checkAuth() {
        try {
            const res = await fetch("/api/auth/me");
            const data = await res.json();
            if (data.authenticated && data.role === "instructor") {
                const baseLabel = data.title || "Instructor";
                let badgeLabel = baseLabel;
                if (data.via === "oidc") {
                    badgeLabel = data.email ? `${baseLabel} · ${data.email} (Google)` : `${baseLabel} (Google)`;
                } else if (data.via === "badge") {
                    badgeLabel = `${baseLabel} (Badge)`;
                }
                if (userBadgeText) {
                    userBadgeText.textContent = badgeLabel;
                } else if (userBadge) {
                    userBadge.textContent = badgeLabel;
                }
            } else if (!data.authenticated) {
                const testRes = await fetch("/api/setup");
                if (testRes.status === 403 || testRes.status === 401) {
                    window.location.href = "/login?next=/setup";
                }
            }
        } catch (e) {
            console.error("Auth check failed", e);
        }
    }

    function normaliseEmailClient(raw) {
        if (raw == null) return "";
        return String(raw).trim().toLowerCase();
    }

    function isValidEmailFormat(norm) {
        if (!norm) return true;
        if (norm.length > 254 || /\s/.test(norm)) return false;
        const parts = norm.split("@");
        if (parts.length !== 2) return false;
        const local = parts[0];
        const domain = parts[1];
        if (!local || !domain) return false;
        if (!domain.includes(".") || domain.startsWith(".") || domain.endsWith(".")) return false;
        return true;
    }

    function applyServerSetupData(data) {
        if (!data) return;
        if (data.name && exNameInput) {
            exNameInput.value = data.name;
            currentSetup.name = data.name;
        }
        if (data.updated && setupLastUpdated) {
            setupLastUpdated.textContent = formatTimestamp(data.updated);
        }
        currentRoster = Array.isArray(data.roster) ? data.roster : [];

        const cfg = data.config || {};
        // Director email from config or INSTR-1 roster row
        const instrRow = currentRoster.find(r => r.role === "instructor" || String(r.code || "").startsWith("INSTR-1"));
        const dirEmail = cfg.director_email != null
            ? String(cfg.director_email)
            : (instrRow && instrRow.email ? String(instrRow.email) : "");
        currentSetup.director_email = dirEmail;
        if (directorEmailInput) {
            directorEmailInput.value = dirEmail;
        }

        if (Array.isArray(cfg.aircraft) && cfg.aircraft.length > 0) {
            currentSetup.aircraft = cfg.aircraft.map((ac, idx) => {
                const acEmails = Object.assign({}, ac.emails || {});
                const acId = ac.id || `ac-${idx + 1}`;
                // Also pull normalised emails from roster rows for this aircraft
                currentRoster.forEach(r => {
                    if (r.aircraft_id === acId && r.email) {
                        if (r.seat === "pilot") acEmails.pilot = r.email;
                        if (r.seat === "observer") acEmails.observer = r.email;
                        if (r.seat === "scanner") acEmails.scanner = r.email;
                    }
                });
                return {
                    id: acId,
                    callsign: ac.callsign || `CAP ${420 + idx + 1}`,
                    tail: ac.tail || "",
                    df_model: ac.df_model || "Becker SAR-DF 517",
                    crew: Array.isArray(ac.crew) ? ac.crew : ["pilot", "observer", "scanner"],
                    emails: acEmails
                };
            });
            currentSetup.num_aircraft = currentSetup.aircraft.length || data.num_aircraft || 1;
        }

        // Reset staff emails before populating from config & roster
        currentSetup.staffEmails = { "MRO 1": "", "MRO 2": "", "UDF 1": "", "UDF 2": "" };
        if (Array.isArray(cfg.staff)) {
            currentSetup.staff = cfg.staff;
            syncStaffCheckboxes(cfg.staff);
            cfg.staff.forEach(st => {
                const key = normaliseStaffCallsign(st.callsign);
                if (key && st.email) {
                    currentSetup.staffEmails[key] = String(st.email);
                }
            });
        }
        currentRoster.forEach(r => {
            if ((r.role === "base" || r.role === "ground_team") && r.email) {
                const key = normaliseStaffCallsign(r.callsign);
                if (key) {
                    currentSetup.staffEmails[key] = String(r.email);
                }
            }
        });
        syncStaffEmailInputs();
    }

    function normaliseStaffCallsign(cs) {
        const u = String(cs || "").toUpperCase().replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
        if (u === "MRO 1") return "MRO 1";
        if (u === "MRO 2") return "MRO 2";
        if (u === "UDF 1") return "UDF 1";
        if (u === "UDF 2") return "UDF 2";
        return "";
    }

    function syncStaffEmailInputs() {
        const pairs = [
            ["staffEmailMro1", "MRO 1"],
            ["staffEmailMro2", "MRO 2"],
            ["staffEmailUdf1", "UDF 1"],
            ["staffEmailUdf2", "UDF 2"]
        ];
        pairs.forEach(([inputId, key]) => {
            const el = document.getElementById(inputId);
            if (el) {
                el.value = currentSetup.staffEmails[key] || "";
            }
        });
    }

    async function loadSetup() {
        try {
            const res = await fetch("/api/setup");
            if (res.status === 403 || res.status === 401) {
                window.location.href = "/login?next=/setup";
                return;
            }
            const data = await res.json();
            applyServerSetupData(data);
            validateExerciseName();
            renderStepper();
            renderAircraftCards();
            updateStaffVisualState();
            validateEmailFields();
            renderReadinessReview();
            renderRoster(currentRoster);
            renderAttendanceTable();
            updateKpiStrip();
        } catch (e) {
            console.error("Failed to load setup", e);
            validateExerciseName();
            renderStepper();
            renderAircraftCards();
            updateStaffVisualState();
            validateEmailFields();
            renderReadinessReview();
        }
    }

    async function loadReadyStatus() {
        try {
            const res = await fetch("/api/ready");
            if (res.ok) {
                latestReadyData = await res.json();
                if (attendanceLastSync) {
                    const now = new Date().toISOString().slice(11, 19) + "Z";
                    attendanceLastSync.textContent = `Synced ${now}`;
                }
                renderAttendanceTable();
                updateKpiStrip();
            }
        } catch (e) {
            // /api/ready is optional enrichment for Step 5
        }
    }

    function syncStaffCheckboxes(staffList) {
        const callsigns = new Set(
            staffList.map(s => normaliseStaffCallsign(s.callsign)).filter(Boolean)
        );
        const mro2 = document.getElementById("staffMro2");
        const udf1 = document.getElementById("staffUdf1");
        const udf2 = document.getElementById("staffUdf2");
        if (mro2) mro2.checked = callsigns.has("MRO 2");
        if (udf1) udf1.checked = callsigns.has("UDF 1");
        if (udf2) udf2.checked = callsigns.has("UDF 2");
    }

    function bindEvents() {
        // 5-Step Workflow Stepper navigation
        document.querySelectorAll(".onb-step-item").forEach(btn => {
            btn.addEventListener("click", () => {
                const stepNum = parseInt(btn.dataset.stepTarget, 10);
                setActiveWorkflowStep(stepNum, true);
            });
        });

        // Exercise Name input & quick presets
        if (exNameInput) {
            exNameInput.addEventListener("input", () => {
                currentSetup.name = exNameInput.value;
                validateExerciseName();
                renderReadinessReview();
                updatePrintHeader();
            });
        }

        document.querySelectorAll("[data-ex-preset]").forEach(btn => {
            btn.addEventListener("click", () => {
                const preset = btn.getAttribute("data-ex-preset");
                if (preset && exNameInput) {
                    exNameInput.value = preset;
                    currentSetup.name = preset;
                    validateExerciseName();
                    renderReadinessReview();
                    updatePrintHeader();
                    showToast(`Applied exercise preset: ${preset}`, "info");
                }
            });
        });

        // Aircraft Count Stepper buttons
        document.querySelectorAll(".btn-stepper").forEach(btn => {
            btn.addEventListener("click", () => {
                const count = parseInt(btn.dataset.count, 10);
                setAircraftCount(count);
                setActiveWorkflowStep(2, false);
            });
        });

        // Ground staff checkboxes
        ["staffMro2", "staffUdf1", "staffUdf2"].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener("change", () => {
                    updateStaffVisualState();
                    validateEmailFields();
                    renderReadinessReview();
                    updateKpiStrip();
                });
            }
        });

        // Ground staff & Director email inputs
        const staffEmailBindings = [
            ["staffEmailMro1", "MRO 1"],
            ["staffEmailMro2", "MRO 2"],
            ["staffEmailUdf1", "UDF 1"],
            ["staffEmailUdf2", "UDF 2"]
        ];
        staffEmailBindings.forEach(([inputId, key]) => {
            const el = document.getElementById(inputId);
            if (el) {
                el.addEventListener("input", () => {
                    currentSetup.staffEmails[key] = el.value;
                    hideValidationBanner();
                    validateEmailFields();
                    renderReadinessReview();
                });
                el.addEventListener("blur", () => {
                    const norm = normaliseEmailClient(el.value);
                    if (el.value !== norm) el.value = norm;
                    currentSetup.staffEmails[key] = norm;
                    validateEmailFields();
                    renderReadinessReview();
                });
            }
        });

        if (directorEmailInput) {
            directorEmailInput.addEventListener("input", () => {
                currentSetup.director_email = directorEmailInput.value;
                hideValidationBanner();
                validateEmailFields();
                renderReadinessReview();
            });
            directorEmailInput.addEventListener("blur", () => {
                const norm = normaliseEmailClient(directorEmailInput.value);
                if (directorEmailInput.value !== norm) directorEmailInput.value = norm;
                currentSetup.director_email = norm;
                validateEmailFields();
                renderReadinessReview();
            });
        }

        // Save, Reset, Print, Copy All
        saveSetupBtn.addEventListener("click", saveSetup);
        resetSetupBtn.addEventListener("click", resetSetup);
        printBadgesBtn.addEventListener("click", () => {
            if (offlineBadgeFallback) {
                offlineBadgeFallback.open = true;
            }
            updatePrintHeader();
            window.print();
        });
        if (copyAllLinksBtn) {
            copyAllLinksBtn.addEventListener("click", copyAllInviteLinks);
        }

        // Roster role filter pills
        document.querySelectorAll("[data-role-filter]").forEach(btn => {
            btn.addEventListener("click", () => {
                activeRoleFilter = btn.getAttribute("data-role-filter") || "all";
                document.querySelectorAll("[data-role-filter]").forEach(b => {
                    b.classList.toggle("is-active", b === btn);
                });
                renderRoster(currentRoster);
            });
        });

        // Roster search filter
        if (rosterSearchInput) {
            rosterSearchInput.addEventListener("input", () => {
                activeSearchQuery = rosterSearchInput.value.trim().toLowerCase();
                renderRoster(currentRoster);
            });
        }

        // Refresh attendance status
        if (refreshAttendanceBtn) {
            refreshAttendanceBtn.addEventListener("click", async () => {
                await loadSetup();
                await loadReadyStatus();
                showToast("Refreshed participant sign-ins and Ready Room status", "good");
            });
        }

        if (themeToggleBtn) {
            themeToggleBtn.addEventListener("click", toggleTheme);
        }

        if (logoutBtn) {
            logoutBtn.addEventListener("click", async () => {
                try {
                    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
                } catch (e) {
                    // Leaving anyway
                }
                window.location.href = "/login";
            });
        }
    }

    function setActiveWorkflowStep(stepNum, scrollIntoView) {
        activeStep = stepNum;
        document.querySelectorAll(".onb-step-item").forEach(btn => {
            const n = parseInt(btn.dataset.stepTarget, 10);
            btn.classList.toggle("is-active", n === stepNum);
            btn.classList.toggle("is-complete", n < stepNum);
        });
        if (scrollIntoView) {
            const panel = document.querySelector(`[data-step-panel="${stepNum}"]`);
            if (panel) {
                panel.scrollIntoView({ behavior: "smooth", block: "start" });
            }
        }
    }

    function validateExerciseName() {
        if (!exNameInput) return true;
        const val = exNameInput.value.trim();
        const len = val.length;
        if (exNameCharCount) {
            exNameCharCount.textContent = `${len} / 100`;
        }
        const isValid = len >= 3 && len <= 100;
        exNameInput.classList.toggle("is-invalid", !isValid);
        if (exNameValidation) {
            exNameValidation.className = "onb-field-feedback " + (isValid ? "is-valid" : "is-error");
            exNameValidation.textContent = isValid
                ? "Displayed across all participant invitations, boarding passes, and printable QR cards."
                : "Exercise name should be between 3 and 100 characters.";
        }
        if (step1StatusChip) {
            step1StatusChip.className = "onb-status-chip " + (isValid ? "onb-chip-ok" : "onb-chip-warn");
            step1StatusChip.textContent = isValid ? "Configured" : "Name Required";
        }
        return isValid;
    }

    function updatePrintHeader() {
        const titleEl = document.getElementById("printExerciseTitle");
        if (titleEl && exNameInput) {
            titleEl.textContent = exNameInput.value.trim() || "Civil Air Patrol SAREX Exercise";
        }
        const summaryEl = document.getElementById("printSeatSummary");
        if (summaryEl) {
            summaryEl.textContent = `${currentRoster.length} SEATS PROVISIONED`;
        }
    }

    function renderStepper() {
        document.querySelectorAll(".btn-stepper").forEach(btn => {
            const count = parseInt(btn.dataset.count, 10);
            if (count === currentSetup.num_aircraft) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });
    }

    function setAircraftCount(count) {
        currentSetup.num_aircraft = count;
        while (currentSetup.aircraft.length < count) {
            const idx = currentSetup.aircraft.length + 1;
            currentSetup.aircraft.push({
                id: `ac-${idx}`,
                callsign: `CAP ${420 + idx}`,
                tail: `N${498 + idx}CP`,
                df_model: idx % 2 === 1 ? "Becker SAR-DF 517" : "RHOTHETA RT-600",
                crew: ["pilot", "observer", "scanner"],
                emails: {}
            });
        }
        if (currentSetup.aircraft.length > count) {
            currentSetup.aircraft = currentSetup.aircraft.slice(0, count);
        }
        renderStepper();
        renderAircraftCards();
        validateEmailFields();
        renderReadinessReview();
        updateKpiStrip();
    }

    function renderAircraftCards() {
        aircraftGrid.innerHTML = "";
        currentSetup.aircraft.forEach((ac, idx) => {
            const card = document.createElement("div");
            const slotNum = idx + 1;
            card.className = "ac-config-card";
            card.setAttribute("data-slot", String(slotNum));

            const dfModelStr = String(ac.df_model || "");
            const is517 = dfModelStr.includes("517");
            const is600 = dfModelStr.includes("600");
            const crewArr = Array.isArray(ac.crew) ? ac.crew : [];
            const hasPilot = crewArr.includes("pilot");
            const hasObs = crewArr.includes("observer");
            const hasScn = crewArr.includes("scanner");
            const emailsObj = ac.emails || {};

            const safeCallsign = esc(ac.callsign);
            const safeTail = esc(ac.tail);
            const safePilotEmail = esc(emailsObj.pilot || "");
            const safeObsEmail = esc(emailsObj.observer || "");
            const safeScnEmail = esc(emailsObj.scanner || "");

            card.innerHTML = `
                <div class="ac-card-header">
                    <b>
                        <span class="ac-slot-dot" aria-hidden="true"></span>
                        <span>Aircraft ${slotNum}</span>
                    </b>
                    <span class="tag mono" data-callsign-tag="${idx}">${safeCallsign}</span>
                </div>
                <div class="form-grid" style="margin-top:6px">
                    <div>
                        <label>Call Sign</label>
                        <input type="text" class="ac-callsign" data-index="${idx}" maxlength="32" value="${safeCallsign}" placeholder="e.g. CAP 423">
                        <div class="onb-field-feedback" data-callsign-err="${idx}"></div>
                    </div>
                    <div>
                        <label>Tail Number</label>
                        <input type="text" class="ac-tail" data-index="${idx}" maxlength="16" value="${safeTail}" placeholder="e.g. N499CP">
                        <div class="onb-field-feedback" data-tail-err="${idx}"></div>
                    </div>
                </div>
                <div style="margin-top:6px">
                    <label>Direction Finder (DF) Receiver Model</label>
                    <select class="ac-df" data-index="${idx}">
                        <option value="Becker SAR-DF 517" ${is517 ? "selected" : ""}>Becker SAR-DF 517 (Standard Left/Right Homing)</option>
                        <option value="RHOTHETA RT-600" ${is600 ? "selected" : ""}>RHOTHETA RT-600 (360° Bearing &amp; 19-Channel Grid)</option>
                    </select>
                </div>
                <div style="margin-top:10px">
                    <label>Aircrew Positions &amp; Assigned Google Emails <span class="onb-opt-note">(optional &mdash; blank for badge-only)</span></label>
                    <div class="onb-crew-email-rows">
                        <div class="onb-crew-email-row">
                            <label class="checkbox-inline onb-crew-chk-label">
                                <input type="checkbox" class="crew-pilot" data-index="${idx}" ${hasPilot ? "checked" : ""}>
                                <span>Mission Pilot</span>
                            </label>
                            <div class="onb-crew-email-field">
                                <input type="email" class="ac-crew-email" data-index="${idx}" data-seat="pilot" value="${safePilotEmail}" placeholder="Pilot Google email (optional)" maxlength="254" autocomplete="off" spellcheck="false" ${hasPilot ? "" : "disabled"}>
                                <div class="onb-field-feedback" data-email-err="ac-${idx}-pilot"></div>
                            </div>
                        </div>
                        <div class="onb-crew-email-row">
                            <label class="checkbox-inline onb-crew-chk-label">
                                <input type="checkbox" class="crew-obs" data-index="${idx}" ${hasObs ? "checked" : ""}>
                                <span>Mission Observer</span>
                            </label>
                            <div class="onb-crew-email-field">
                                <input type="email" class="ac-crew-email" data-index="${idx}" data-seat="observer" value="${safeObsEmail}" placeholder="Observer Google email (optional)" maxlength="254" autocomplete="off" spellcheck="false" ${hasObs ? "" : "disabled"}>
                                <div class="onb-field-feedback" data-email-err="ac-${idx}-observer"></div>
                            </div>
                        </div>
                        <div class="onb-crew-email-row">
                            <label class="checkbox-inline onb-crew-chk-label">
                                <input type="checkbox" class="crew-scn" data-index="${idx}" ${hasScn ? "checked" : ""}>
                                <span>Mission Scanner</span>
                            </label>
                            <div class="onb-crew-email-field">
                                <input type="email" class="ac-crew-email" data-index="${idx}" data-seat="scanner" value="${safeScnEmail}" placeholder="Scanner Google email (optional)" maxlength="254" autocomplete="off" spellcheck="false" ${hasScn ? "" : "disabled"}>
                                <div class="onb-field-feedback" data-email-err="ac-${idx}-scanner"></div>
                            </div>
                        </div>
                    </div>
                    <div class="onb-field-feedback" data-crew-err="${idx}"></div>
                </div>
            `;
            aircraftGrid.appendChild(card);
        });

        // Bind aircraft card inputs
        aircraftGrid.querySelectorAll(".ac-callsign").forEach(el => {
            el.addEventListener("input", e => {
                const i = parseInt(e.target.dataset.index, 10);
                currentSetup.aircraft[i].callsign = e.target.value;
                const tagEl = aircraftGrid.querySelector(`[data-callsign-tag="${i}"]`);
                if (tagEl) tagEl.textContent = e.target.value.trim() || `AC ${i + 1}`;
                validateAircraftFields();
                validateEmailFields();
                renderReadinessReview();
                updateKpiStrip();
            });
        });

        aircraftGrid.querySelectorAll(".ac-tail").forEach(el => {
            el.addEventListener("input", e => {
                const i = parseInt(e.target.dataset.index, 10);
                currentSetup.aircraft[i].tail = e.target.value;
                validateAircraftFields();
                renderReadinessReview();
            });
        });

        aircraftGrid.querySelectorAll(".ac-df").forEach(el => {
            el.addEventListener("change", e => {
                const i = parseInt(e.target.dataset.index, 10);
                currentSetup.aircraft[i].df_model = e.target.value;
                renderReadinessReview();
            });
        });

        aircraftGrid.querySelectorAll(".crew-pilot, .crew-obs, .crew-scn").forEach(el => {
            el.addEventListener("change", () => {
                aircraftGrid.querySelectorAll(".ac-config-card").forEach((c, idx) => {
                    const crew = [];
                    const pChk = c.querySelector(".crew-pilot");
                    const oChk = c.querySelector(".crew-obs");
                    const sChk = c.querySelector(".crew-scn");
                    if (pChk && pChk.checked) crew.push("pilot");
                    if (oChk && oChk.checked) crew.push("observer");
                    if (sChk && sChk.checked) crew.push("scanner");
                    currentSetup.aircraft[idx].crew = crew;

                    const pIn = c.querySelector('.ac-crew-email[data-seat="pilot"]');
                    const oIn = c.querySelector('.ac-crew-email[data-seat="observer"]');
                    const sIn = c.querySelector('.ac-crew-email[data-seat="scanner"]');
                    if (pIn) pIn.disabled = !(pChk && pChk.checked);
                    if (oIn) oIn.disabled = !(oChk && oChk.checked);
                    if (sIn) sIn.disabled = !(sChk && sChk.checked);
                });
                validateAircraftFields();
                validateEmailFields();
                renderReadinessReview();
                updateKpiStrip();
            });
        });

        aircraftGrid.querySelectorAll(".ac-crew-email").forEach(el => {
            el.addEventListener("input", e => {
                const i = parseInt(e.target.dataset.index, 10);
                const seat = e.target.dataset.seat;
                if (!currentSetup.aircraft[i].emails) {
                    currentSetup.aircraft[i].emails = {};
                }
                currentSetup.aircraft[i].emails[seat] = e.target.value;
                hideValidationBanner();
                validateEmailFields();
                renderReadinessReview();
            });
            el.addEventListener("blur", e => {
                const i = parseInt(e.target.dataset.index, 10);
                const seat = e.target.dataset.seat;
                const norm = normaliseEmailClient(e.target.value);
                if (e.target.value !== norm) e.target.value = norm;
                if (!currentSetup.aircraft[i].emails) {
                    currentSetup.aircraft[i].emails = {};
                }
                currentSetup.aircraft[i].emails[seat] = norm;
                validateEmailFields();
                renderReadinessReview();
            });
        });

        validateAircraftFields();
    }

    function validateAircraftFields() {
        const seenCallsigns = new Map();
        currentSetup.aircraft.forEach(ac => {
            const norm = String(ac.callsign || "").trim().toUpperCase();
            if (norm) {
                seenCallsigns.set(norm, (seenCallsigns.get(norm) || 0) + 1);
            }
        });

        let allValid = true;
        currentSetup.aircraft.forEach((ac, idx) => {
            const csVal = String(ac.callsign || "").trim();
            const tailVal = String(ac.tail || "").trim();
            const crewArr = Array.isArray(ac.crew) ? ac.crew : [];
            const isDupCs = csVal && (seenCallsigns.get(csVal.toUpperCase()) || 0) > 1;
            const csValid = csVal.length >= 2 && !isDupCs;
            const tailValid = tailVal.length >= 2;
            const crewValid = crewArr.length >= 1;

            if (!csValid || !tailValid || !crewValid) allValid = false;

            const csInput = aircraftGrid.querySelector(`.ac-callsign[data-index="${idx}"]`);
            const csErr = aircraftGrid.querySelector(`[data-callsign-err="${idx}"]`);
            if (csInput) csInput.classList.toggle("is-invalid", !csValid);
            if (csErr) {
                csErr.className = "onb-field-feedback " + (csValid ? "" : "is-error");
                csErr.textContent = !csVal
                    ? "Callsign required (e.g. CAP 423)"
                    : isDupCs
                        ? "Duplicate callsign across aircraft"
                        : "";
            }

            const tailInput = aircraftGrid.querySelector(`.ac-tail[data-index="${idx}"]`);
            const tailErr = aircraftGrid.querySelector(`[data-tail-err="${idx}"]`);
            if (tailInput) tailInput.classList.toggle("is-invalid", !tailValid);
            if (tailErr) {
                tailErr.className = "onb-field-feedback " + (tailValid ? "" : "is-error");
                tailErr.textContent = tailValid ? "" : "Tail number required (e.g. N499CP)";
            }

            const crewErr = aircraftGrid.querySelector(`[data-crew-err="${idx}"]`);
            if (crewErr) {
                crewErr.className = "onb-field-feedback " + (crewValid ? "" : "is-error");
                crewErr.textContent = crewValid ? "" : "Select at least 1 aircrew seat for this aircraft";
            }
        });
        return allValid;
    }

    function collectActiveEmailEntries() {
        const entries = [];
        // 1. Director
        if (directorEmailInput) {
            entries.push({
                errKey: "director_email",
                seatLabel: "INSTR-1",
                inputEl: directorEmailInput,
                raw: directorEmailInput.value,
                norm: normaliseEmailClient(directorEmailInput.value)
            });
        }
        // 2. Aircraft crew
        currentSetup.aircraft.forEach((ac, idx) => {
            const crewArr = Array.isArray(ac.crew) ? ac.crew : [];
            const cs = String(ac.callsign || `CAP ${420 + idx + 1}`).trim();
            const suffix = cs.includes(" ") ? cs.split(/\s+/).slice(-1)[0] : String(idx + 1);
            const prefixMap = { pilot: "PLT", observer: "OBS", scanner: "SCN" };
            ["pilot", "observer", "scanner"].forEach(seat => {
                const inputEl = aircraftGrid.querySelector(`.ac-crew-email[data-index="${idx}"][data-seat="${seat}"]`);
                const errKey = `ac-${idx}-${seat}`;
                if (!crewArr.includes(seat)) {
                    clearEmailFieldError(errKey, inputEl);
                    return;
                }
                const rawVal = inputEl ? inputEl.value : ((ac.emails && ac.emails[seat]) || "");
                entries.push({
                    errKey,
                    seatLabel: `${prefixMap[seat]}-${suffix}`,
                    inputEl,
                    raw: rawVal,
                    norm: normaliseEmailClient(rawVal)
                });
            });
        });
        // 3. Ground staff
        const staffDefs = [
            { chkId: "staffMro1", inputId: "staffEmailMro1", key: "MRO 1", alwaysOn: true },
            { chkId: "staffMro2", inputId: "staffEmailMro2", key: "MRO 2", alwaysOn: false },
            { chkId: "staffUdf1", inputId: "staffEmailUdf1", key: "UDF 1", alwaysOn: false },
            { chkId: "staffUdf2", inputId: "staffEmailUdf2", key: "UDF 2", alwaysOn: false }
        ];
        staffDefs.forEach(def => {
            const chk = document.getElementById(def.chkId);
            const inputEl = document.getElementById(def.inputId);
            const errKey = `staff-${def.key}`;
            const active = def.alwaysOn || (chk && chk.checked);
            if (!active) {
                clearEmailFieldError(errKey, inputEl);
                return;
            }
            const rawVal = inputEl ? inputEl.value : (currentSetup.staffEmails[def.key] || "");
            entries.push({
                errKey,
                seatLabel: def.key,
                inputEl,
                raw: rawVal,
                norm: normaliseEmailClient(rawVal)
            });
        });
        return entries;
    }

    function clearEmailFieldError(errKey, inputEl) {
        if (inputEl) inputEl.classList.remove("is-invalid");
        const errEl = document.querySelector(`[data-email-err="${errKey}"]`);
        if (errEl) {
            errEl.className = "onb-field-feedback";
            errEl.textContent = "";
        }
    }

    function setEmailFieldError(errKey, inputEl, message) {
        if (inputEl) inputEl.classList.add("is-invalid");
        const errEl = document.querySelector(`[data-email-err="${errKey}"]`);
        if (errEl) {
            errEl.className = "onb-field-feedback is-error";
            errEl.textContent = message;
        }
    }

    function validateEmailFields() {
        const entries = collectActiveEmailEntries();
        const byEmail = new Map();
        let allValid = true;

        entries.forEach(entry => {
            clearEmailFieldError(entry.errKey, entry.inputEl);
            if (!entry.norm) return;
            if (!isValidEmailFormat(entry.norm)) {
                allValid = false;
                setEmailFieldError(
                    entry.errKey,
                    entry.inputEl,
                    "Enter a valid email address (for example, member@cawg.cap.gov) — value is not a valid email address."
                );
                return;
            }
            if (!byEmail.has(entry.norm)) {
                byEmail.set(entry.norm, []);
            }
            byEmail.get(entry.norm).push(entry);
        });

        byEmail.forEach((group, email) => {
            if (group.length > 1) {
                allValid = false;
                const seatNames = group.map(g => g.seatLabel).join(", ");
                const msg = `email ${email} is assigned to more than one seat (${seatNames}); one seat per email`;
                group.forEach(g => {
                    setEmailFieldError(g.errKey, g.inputEl, msg);
                });
            }
        });

        return { allValid, assignedCount: Array.from(byEmail.values()).reduce((acc, g) => acc + g.length, 0) };
    }

    function showValidationBanner(message) {
        if (!setupValidationBanner) return;
        setupValidationBanner.textContent = message;
        setupValidationBanner.style.display = "block";
    }

    function hideValidationBanner() {
        if (!setupValidationBanner) return;
        setupValidationBanner.textContent = "";
        setupValidationBanner.style.display = "none";
    }

    function applyServer422Errors(errData, sentStaff) {
        if (!errData) return "Validation error while saving setup.";
        const detail = errData.detail;
        if (typeof detail === "string") {
            // Duplicate email or general ValueError from save_exercise_setup
            const entries = collectActiveEmailEntries();
            entries.forEach(entry => {
                if (entry.norm && detail.toLowerCase().includes(entry.norm)) {
                    setEmailFieldError(entry.errKey, entry.inputEl, detail);
                }
            });
            showValidationBanner(detail);
            return detail;
        }
        if (Array.isArray(detail)) {
            const messages = [];
            detail.forEach(item => {
                const loc = Array.isArray(item.loc) ? item.loc : [];
                const msg = String(item.msg || "Invalid field value").replace(/^Value error,\s*/i, "");
                messages.push(msg);

                // Map pydantic loc to our inline field feedback element
                if (loc[1] === "director_email") {
                    setEmailFieldError("director_email", directorEmailInput, msg);
                } else if (loc[1] === "aircraft" && typeof loc[2] === "number") {
                    const acIdx = loc[2];
                    if (loc[3] === "emails" && typeof loc[4] === "string") {
                        const seat = loc[4];
                        const inputEl = aircraftGrid.querySelector(`.ac-crew-email[data-index="${acIdx}"][data-seat="${seat}"]`);
                        setEmailFieldError(`ac-${acIdx}-${seat}`, inputEl, msg);
                    }
                } else if (loc[1] === "staff" && typeof loc[2] === "number") {
                    const stIdx = loc[2];
                    const stObj = sentStaff && sentStaff[stIdx];
                    const key = stObj ? normaliseStaffCallsign(stObj.callsign) : "";
                    if (key) {
                        const inputEl = document.querySelector(`.staff-email-input[data-staff-key="${key}"]`);
                        setEmailFieldError(`staff-${key}`, inputEl, msg);
                    }
                }
            });
            const joined = messages.join("; ") || "Please check highlighted fields.";
            showValidationBanner(joined);
            return joined;
        }
        return "Could not save setup. Please check highlighted fields.";
    }

    function getSelectedGroundStaff() {
        const readEmail = (id, key) => {
            const el = document.getElementById(id);
            const raw = el ? el.value : (currentSetup.staffEmails[key] || "");
            const trimmed = String(raw || "").trim();
            return trimmed ? trimmed : null;
        };
        const staff = [
            {
                role: "base",
                title: "Mission Radio Operator 1",
                callsign: "MRO 1",
                email: readEmail("staffEmailMro1", "MRO 1")
            }
        ];
        const mro2 = document.getElementById("staffMro2");
        const udf1 = document.getElementById("staffUdf1");
        const udf2 = document.getElementById("staffUdf2");
        if (mro2 && mro2.checked) {
            staff.push({
                role: "base",
                title: "Mission Radio Operator 2",
                callsign: "MRO 2",
                email: readEmail("staffEmailMro2", "MRO 2")
            });
        }
        if (udf1 && udf1.checked) {
            staff.push({
                role: "ground_team",
                title: "Ground Search Team 1",
                callsign: "UDF 1",
                email: readEmail("staffEmailUdf1", "UDF 1")
            });
        }
        if (udf2 && udf2.checked) {
            staff.push({
                role: "ground_team",
                title: "Ground Search Team 2",
                callsign: "UDF 2",
                email: readEmail("staffEmailUdf2", "UDF 2")
            });
        }
        return staff;
    }

    function updateStaffVisualState() {
        const pairs = [
            ["staffMro2", "staffBoxMro2", "staffEmailMro2"],
            ["staffUdf1", "staffBoxUdf1", "staffEmailUdf1"],
            ["staffUdf2", "staffBoxUdf2", "staffEmailUdf2"]
        ];
        pairs.forEach(([chkId, boxId, emailId]) => {
            const chk = document.getElementById(chkId);
            const box = document.getElementById(boxId);
            const emailIn = document.getElementById(emailId);
            if (chk && box) {
                box.classList.toggle("is-checked", chk.checked);
            }
            if (chk && emailIn) {
                emailIn.disabled = !chk.checked;
            }
        });
        const staff = getSelectedGroundStaff();
        const badge = document.getElementById("groundStaffCountBadge");
        if (badge) {
            badge.textContent = `${staff.length} Ground + 1 Command Seats`;
        }
    }

    function renderReadinessReview() {
        const checklistEl = document.getElementById("readinessChecklist");
        const manifestGrid = document.getElementById("readinessSummaryGrid");
        const totalEl = document.getElementById("manifestTotalSeats");
        const verdictEl = document.getElementById("readinessVerdictBadge");
        if (!checklistEl || !manifestGrid) return;

        const nameOk = validateExerciseName();
        const emailValidation = validateEmailFields();
        const seenCs = new Set();
        let csUniqueOk = true;
        let tailsOk = true;
        let crewOk = true;
        let aircrewSeats = 0;

        currentSetup.aircraft.forEach(ac => {
            const cs = String(ac.callsign || "").trim().toUpperCase();
            const tl = String(ac.tail || "").trim();
            const cr = Array.isArray(ac.crew) ? ac.crew : [];
            if (!cs || cs.length < 2 || seenCs.has(cs)) csUniqueOk = false;
            seenCs.add(cs);
            if (!tl || tl.length < 2) tailsOk = false;
            if (cr.length === 0) crewOk = false;
            aircrewSeats += cr.length;
        });

        const staff = getSelectedGroundStaff();
        const baseSeats = staff.filter(s => s.role === "base").length;
        const udfSeats = staff.filter(s => s.role === "ground_team").length;
        const commandSeats = 1; // Exercise Director / IC
        const totalPlanned = commandSeats + baseSeats + aircrewSeats + udfSeats;

        if (totalEl) totalEl.textContent = String(totalPlanned);

        const emailDetail = !emailValidation.allValid
            ? "Fix invalid or duplicate email"
            : emailValidation.assignedCount > 0
                ? `${emailValidation.assignedCount} seat(s) with Google email`
                : "Badge-only (no emails entered)";

        const checks = [
            { label: "Exercise designation configured", detail: nameOk ? "Valid" : "Needs 3-100 chars", ok: nameOk },
            { label: "Aircraft callsigns unique & formatted", detail: csUniqueOk ? `${currentSetup.aircraft.length} aircraft valid` : "Check callsigns", ok: csUniqueOk },
            { label: "Aircraft tail numbers assigned", detail: tailsOk ? "All tails valid" : "Missing tail number", ok: tailsOk },
            { label: "Aircrew positions staffed", detail: crewOk ? `${aircrewSeats} aircrew seats` : "Unstaffed aircraft", ok: crewOk },
            { label: "Participant Google email assignments", detail: emailDetail, ok: emailValidation.allValid },
            { label: "Tactical net control & ground teams", detail: `${baseSeats} Base · ${udfSeats} UDF`, ok: baseSeats >= 1 }
        ];

        const allOk = checks.every(c => c.ok);
        if (verdictEl) {
            verdictEl.className = "onb-status-chip " + (allOk ? "onb-chip-ok" : "onb-chip-warn");
            verdictEl.textContent = allOk ? "Ready to Save" : "Review Warnings";
        }

        checklistEl.innerHTML = "";
        checks.forEach(item => {
            const li = document.createElement("li");
            li.className = "onb-check-item " + (item.ok ? "is-ok" : "is-warn");
            const checkLabel = esc(item.label);
            const checkDetail = esc(item.detail);
            const statusClass = item.ok ? "onb-chip-ok" : "onb-chip-warn";
            li.innerHTML = `
                <span class="onb-check-item-left">
                    <span class="onb-check-icon" aria-hidden="true">${item.ok ? "&#10003;" : "!"}</span>
                    <span>${checkLabel}</span>
                </span>
                <span class="onb-status-chip ${statusClass} mono">${checkDetail}</span>
            `;
            checklistEl.appendChild(li);
        });

        const acSummary = currentSetup.aircraft.map(a => String(a.callsign || "").trim()).filter(Boolean).join(", ") || "None";
        const manifestItems = [
            { role: "Command / IC", count: `${commandSeats} Seat`, detail: "INSTR · /instructor" },
            { role: "Mission Base Radio", count: `${baseSeats} ${baseSeats === 1 ? "Seat" : "Seats"}`, detail: "MRO · /base & /radio" },
            { role: `Aircrew (${currentSetup.aircraft.length} Aircraft)`, count: `${aircrewSeats} ${aircrewSeats === 1 ? "Seat" : "Seats"}`, detail: `${acSummary} · /base` },
            { role: "Ground UDF Teams", count: `${udfSeats} ${udfSeats === 1 ? "Seat" : "Seats"}`, detail: udfSeats > 0 ? "UDF · /radio" : "None selected" }
        ];

        manifestGrid.innerHTML = "";
        manifestItems.forEach(m => {
            const box = document.createElement("div");
            box.className = "onb-manifest-card";
            const mRole = esc(m.role);
            const mCount = esc(m.count);
            const mDetail = esc(m.detail);
            box.innerHTML = `
                <span class="onb-manifest-role">${mRole}</span>
                <strong class="onb-manifest-count">${mCount}</strong>
                <span class="onb-manifest-detail mono">${mDetail}</span>
            `;
            manifestGrid.appendChild(box);
        });
    }

    function updateKpiStrip() {
        const kpiAc = document.getElementById("kpiAircraftCount");
        const kpiAcSub = document.getElementById("kpiAircraftSub");
        const kpiSeat = document.getElementById("kpiSeatCount");
        const kpiSeatSub = document.getElementById("kpiSeatSub");
        const kpiJoined = document.getElementById("kpiJoinedCount");
        const kpiJoinedSub = document.getElementById("kpiJoinedSub");
        const kpiReady = document.getElementById("kpiReadyCount");
        const kpiReadySub = document.getElementById("kpiReadySub");

        if (kpiAc) kpiAc.textContent = String(currentSetup.num_aircraft || currentSetup.aircraft.length || 1);
        if (kpiAcSub) {
            const callsigns = currentSetup.aircraft.map(a => String(a.callsign || "").trim()).filter(Boolean);
            kpiAcSub.textContent = callsigns.join(" · ") || "CAP 423";
        }

        const totalRoster = currentRoster.length;
        const signedInRows = currentRoster.filter(r => Boolean(r.last_login));
        const signedInCount = signedInRows.length;
        const oidcCount = signedInRows.filter(r => r.last_login_via === "oidc").length;
        const badgeCount = signedInCount - oidcCount;
        const emailAssignedCount = currentRoster.filter(r => Boolean(r.email)).length;

        if (kpiSeat) kpiSeat.textContent = String(totalRoster);
        if (kpiSeatSub) {
            kpiSeatSub.textContent = totalRoster > 0
                ? `${emailAssignedCount} with Google email · ${totalRoster} badges`
                : "Save roster to provision seats";
        }
        if (kpiJoined) kpiJoined.textContent = `${signedInCount} / ${totalRoster}`;
        if (kpiJoinedSub) {
            kpiJoinedSub.textContent = signedInCount > 0
                ? `${oidcCount} Google · ${badgeCount} badge`
                : "Awaiting participant sign-in";
        }

        if (kpiReady && latestReadyData && latestReadyData.summary) {
            const rdy = latestReadyData.summary.ready || 0;
            const tot = latestReadyData.summary.total || 0;
            const blkRaw = latestReadyData.summary.blocking;
            const blk = Array.isArray(blkRaw) ? blkRaw.length : (Number(blkRaw) || 0);
            kpiReady.textContent = `${rdy} / ${tot}`;
            if (kpiReadySub) {
                kpiReadySub.textContent = blk === 0 ? "All blocking seats GO" : `${blk} seat(s) completing checks`;
            }
        }
    }

    function buildSavePayload() {
        const staff = getSelectedGroundStaff();
        const dirRaw = directorEmailInput ? directorEmailInput.value.trim() : String(currentSetup.director_email || "").trim();
        const aircraftPayload = currentSetup.aircraft.map((ac, idx) => {
            const crewArr = Array.isArray(ac.crew) ? ac.crew : ["pilot", "observer"];
            const emailsOut = {};
            crewArr.forEach(seat => {
                const inputEl = aircraftGrid.querySelector(`.ac-crew-email[data-index="${idx}"][data-seat="${seat}"]`);
                const rawVal = inputEl ? inputEl.value : ((ac.emails && ac.emails[seat]) || "");
                const trimmed = String(rawVal || "").trim();
                if (trimmed) {
                    emailsOut[seat] = trimmed;
                }
            });
            return {
                id: ac.id || `ac-${idx + 1}`,
                callsign: String(ac.callsign || "").trim(),
                tail: String(ac.tail || "").trim(),
                df_model: ac.df_model || "Becker SAR-DF 517",
                crew: crewArr,
                emails: emailsOut
            };
        });

        return {
            name: (exNameInput && exNameInput.value.trim()) || "Civil Air Patrol SAREX Exercise",
            director_email: dirRaw || null,
            num_aircraft: currentSetup.num_aircraft,
            aircraft: aircraftPayload,
            staff: staff
        };
    }

    async function saveSetup() {
        hideValidationBanner();
        const nameOk = validateExerciseName();
        const acOk = validateAircraftFields();
        validateEmailFields();

        if (!nameOk || !acOk) {
            showToast("Please resolve highlighted aircraft or exercise name warnings before saving.", "warn");
            return;
        }

        const payload = buildSavePayload();

        saveSetupBtn.disabled = true;
        if (saveSetupBtnLabel) {
            saveSetupBtnLabel.textContent = "Saving Roster & Invites...";
        } else {
            saveSetupBtn.textContent = "Saving Roster & Invites...";
        }

        try {
            const res = await fetch("/api/setup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (!res.ok) {
                let err = null;
                try {
                    err = await res.json();
                } catch (parseErr) {
                    err = { detail: res.statusText };
                }
                const msg = applyServer422Errors(err, payload.staff);
                renderReadinessReview();
                showToast("Could not save setup: " + msg, "danger");
                return;
            }
            const data = await res.json();
            applyServerSetupData(data);
            renderStepper();
            renderAircraftCards();
            updateStaffVisualState();
            validateEmailFields();
            renderReadinessReview();
            renderRoster(currentRoster);
            await loadReadyStatus();
            updateKpiStrip();
            setActiveWorkflowStep(4, false);
            document.getElementById("rosterSection").scrollIntoView({ behavior: "smooth" });
            showToast(`Saved ${currentRoster.length} seats and updated participant invites`, "good");
        } catch (e) {
            showToast("Error saving setup: " + e.message, "danger");
        } finally {
            saveSetupBtn.disabled = false;
            if (saveSetupBtnLabel) {
                saveSetupBtnLabel.textContent = "Save Roster & Seat Invites";
            } else {
                saveSetupBtn.textContent = "Save Roster & Seat Invites";
            }
        }
    }

    async function resetSetup() {
        if (!confirm("Reset to default 1-aircraft and standard staff roster? Assigned emails will be cleared and existing participant sessions will be signed out.")) return;
        hideValidationBanner();
        try {
            const res = await fetch("/api/setup/reset", { method: "POST" });
            const data = await res.json();
            applyServerSetupData(data);
            validateExerciseName();
            renderStepper();
            renderAircraftCards();
            updateStaffVisualState();
            validateEmailFields();
            renderReadinessReview();
            renderRoster(currentRoster);
            await loadReadyStatus();
            updateKpiStrip();
            showToast("Reset exercise fleet, staff roster, and cleared assigned emails", "info");
        } catch (e) {
            showToast("Error resetting setup: " + e.message, "danger");
        }
    }

    // BEGIN T24 PURE INVITE MESSAGE
    // What "Email this invite" puts in the director's mail client (T23 C7).
    // A badge code is a bearer credential, so it is written into a message in
    // one case only: a seat that has no email assigned, where the badge is the
    // only way in. A seat with an email gets the sign-in page address and the
    // seat in plain words, nothing that could sign someone else in. The
    // Exercise Director's own seat never gets its code in a message at all:
    // that credential stays on the printed card.
    function buildInviteMessage(item, exTitle, origin) {
        const seatTitle = item.title || "Participant";
        const callsign = item.callsign || "ASSIGNED";
        const targetConsole = item.target_url || "/";
        const loginUrl = `${origin}/login`;
        const isDirector = item.role === "instructor";
        const byEmail = Boolean(item.email);
        const subject = `CAP V-SAR Exercise Invite: ${exTitle} — ${seatTitle} (${callsign})`;
        const bodyLines = [
            "Hello,",
            "",
            `You have been assigned a seat in the Civil Air Patrol V-SAR training exercise "${exTitle}".`,
            "",
            `Assigned Seat: ${seatTitle}`,
            `Callsign: ${callsign}`,
            `Station Console: ${origin}${targetConsole}`,
            `Sign-In Page: ${loginUrl}`
        ];
        if (byEmail) {
            bodyLines.push(`Assigned Google Email: ${item.email}`);
            bodyLines.push("");
            bodyLines.push("How to sign in:");
            bodyLines.push(`1. Open ${loginUrl} in your web browser.`);
            bodyLines.push(`2. Click "Sign in with Google" and use ${item.email}.`);
            bodyLines.push(`3. Complete your headset and station check in the Ready Room (${origin}/ready).`);
            bodyLines.push("");
            bodyLines.push("Your seat is tied to that email address; no badge code is needed. If the console");
            bodyLines.push("is offline on the day, the Exercise Director will hand you a printed badge card.");
        } else if (isDirector) {
            bodyLines.push("");
            bodyLines.push("How to sign in:");
            bodyLines.push(`1. Open ${loginUrl} in your web browser.`);
            bodyLines.push("2. Enter the Exercise Director badge code from your printed card.");
            bodyLines.push("   (The director badge code is never sent by email.)");
        } else {
            const joinUrl = `${origin}/join/${encodeURIComponent(item.code || "")}`;
            bodyLines.push("");
            bodyLines.push("How to sign in:");
            bodyLines.push(`1. Open your direct badge link: ${joinUrl}`);
            bodyLines.push(`   (Or open ${loginUrl} and enter badge code: ${item.code || ""})`);
            bodyLines.push(`2. Complete your headset and station check in the Ready Room (${origin}/ready).`);
            bodyLines.push("");
            bodyLines.push(`Offline / Backup Badge Code: ${item.code || ""}`);
            bodyLines.push(`Direct Badge Link: ${joinUrl}`);
        }
        bodyLines.push("");
        bodyLines.push("EXERCISE TRAFFIC ONLY - NOT A REAL DISTRESS");
        return { to: item.email || "", subject: subject, body: bodyLines.join("\n") };
    }
    // END T24 PURE INVITE MESSAGE

    function buildMailtoHref(item, exTitle, origin) {
        const msg = buildInviteMessage(item, exTitle, origin);
        return `mailto:${encodeURIComponent(msg.to)}?subject=${encodeURIComponent(msg.subject)}&body=${encodeURIComponent(msg.body)}`;
    }

    function renderRoster(roster) {
        if (inviteList) inviteList.innerHTML = "";
        rosterGrid.innerHTML = "";
        updatePrintHeader();

        const filtered = roster.filter(item => {
            if (activeRoleFilter !== "all" && item.role !== activeRoleFilter) {
                return false;
            }
            if (activeSearchQuery) {
                const hay = `${item.title || ""} ${item.callsign || ""} ${item.role || ""} ${item.assigned_name || ""} ${item.email || ""} ${item.code || ""}`.toLowerCase();
                if (!hay.includes(activeSearchQuery)) return false;
            }
            return true;
        });

        rosterCount.textContent = filtered.length === roster.length
            ? `${roster.length} Participants`
            : `${filtered.length} of ${roster.length} Participants`;
        if (offlineBadgeCountChip) {
            offlineBadgeCountChip.textContent = `${filtered.length} ${filtered.length === 1 ? "Badge" : "Badges"}`;
        }

        const host = window.location.hostname;
        const port = window.location.port ? `:${window.location.port}` : "";
        const protocol = window.location.protocol;
        const origin = `${protocol}//${host}${port}`;
        const exTitle = (exNameInput && exNameInput.value.trim()) || currentSetup.name || "Civil Air Patrol SAREX Exercise";

        if (filtered.length === 0) {
            const emptyMsg = `
                <div class="onb-empty-state">
                    <h3>No matching participant seats</h3>
                    <p>Adjust your role filter or search query, or click Save Roster &amp; Seat Invites in Step 3.</p>
                </div>
            `;
            if (inviteList) inviteList.innerHTML = emptyMsg;
            rosterGrid.innerHTML = emptyMsg;
            return;
        }

        filtered.forEach(item => {
            const roleRaw = String(item.role == null ? "" : item.role);
            let roleBadgeClass = "badge-aircrew";
            let rolePillClass = "role-aircrew";
            if (roleRaw === "instructor") {
                roleBadgeClass = "badge-instructor";
                rolePillClass = "role-instructor";
            } else if (roleRaw === "base") {
                roleBadgeClass = "badge-base";
                rolePillClass = "role-base";
            } else if (roleRaw === "ground_team") {
                roleBadgeClass = "badge-ground";
                rolePillClass = "role-ground";
            }

            const joinUrl = `${origin}/join/${encodeURIComponent(item.code || "")}`;
            const loginUrl = `${origin}/login`;
            const primarySignInUrl = item.email ? loginUrl : joinUrl;
            const primaryCopyKind = item.email ? "Sign-in link (/login)" : "Seat sign-in link";
            const badgeSrc = `/api/setup/badge/${encodeURIComponent(item.id)}.svg?origin=${encodeURIComponent(origin)}`;
            const mailtoHref = buildMailtoHref(item, exTitle, origin);

            // Pre-escape all server-sourced values before building HTML
            const roleLabel = esc(roleRaw.replace("_", " ").toUpperCase());
            const safeTitle = esc(item.title);
            const safeCallsign = esc(item.callsign || "");
            const safeAssigned = esc(item.assigned_name || "Assigned Station");
            const safeTarget = esc(item.target_url || "/");
            const safeCode = esc(item.code || "");
            const safeEmail = esc(item.email || "");
            const safePrimaryUrl = esc(primarySignInUrl);
            const safePrimaryKind = esc(primaryCopyKind);
            const safeJoinUrl = esc(joinUrl);
            const safeBadgeSrc = esc(badgeSrc);
            const safeMailto = esc(mailtoHref);
            const equipHint = esc(getRoleEquipmentHint(roleRaw));

            const hasJoined = Boolean(item.last_login);
            const viaLabel = item.last_login_via === "oidc"
                ? "Signed in with Google"
                : item.last_login_via === "badge"
                    ? "Signed in with badge"
                    : "Signed in";
            const joinStatusClass = hasJoined ? "good" : "warn";
            const joinStatusText = esc(hasJoined ? `${viaLabel} · ${formatTimestamp(item.last_login)}` : "Not signed in yet");

            const emailChipClass = item.email ? "info" : "untracked";
            const emailChipText = item.email ? safeEmail : "No email assigned · Badge only";

            // 1. Primary Invite Row in #inviteList
            if (inviteList) {
                const row = document.createElement("div");
                row.className = "onb-invite-row";
                row.innerHTML = `
                    <div class="onb-invite-seat">
                        <div class="onb-invite-seat-top">
                            <span class="onb-role-pill ${rolePillClass}">${roleLabel}</span>
                            <strong class="onb-invite-title">${safeTitle}</strong>
                            <span class="badge-callsign mono">${safeCallsign}</span>
                        </div>
                        <div class="notes">
                            <span>${safeAssigned}</span>
                            &middot;
                            <span class="mono">Opens ${safeTarget}</span>
                        </div>
                    </div>
                    <div class="onb-invite-chips">
                        <span class="onb-pill ${emailChipClass} mono" title="Assigned Google sign-in email">${emailChipText}</span>
                        <span class="onb-pill ${joinStatusClass}">${joinStatusText}</span>
                    </div>
                    <div class="onb-invite-actions">
                        <button type="button" class="primary btn-sm btn-copy" data-url="${safePrimaryUrl}" data-copy-kind="${safePrimaryKind}">Copy sign-in link</button>
                        <a href="${safeMailto}" class="onb-btn ghost btn-sm btn-email-invite">Email this invite</a>
                        <button type="button" class="ghost btn-sm btn-copy" data-url="${safeJoinUrl}" data-copy-kind="Backup badge link">Copy badge link</button>
                    </div>
                `;
                inviteList.appendChild(row);
            }

            // 2. Offline Fallback Badge Card in #rosterGrid
            const card = document.createElement("div");
            card.className = `roster-badge-card role-${roleRaw}`;
            card.innerHTML = `
                <div class="badge-top">
                    <span class="role-badge ${roleBadgeClass}">${roleLabel}</span>
                    <span class="badge-callsign mono">${safeCallsign}</span>
                </div>
                <div class="badge-title">${safeTitle}</div>
                <div class="badge-meta">
                    <span>${ emailChipText }</span>
                    <span class="onb-pill ${joinStatusClass}">${joinStatusText}</span>
                </div>

                <div class="badge-qr-container">
                    <img class="qr-canvas is-loading" width="150" height="150" alt="QR badge for ${safeCallsign}" src="${safeBadgeSrc}">
                    <span class="qr-label">Scan to join &middot; opens ${safeTarget}</span>
                </div>

                <div class="badge-code-block">
                    <span class="badge-code-label">
                        <span>Offline badge code (if no Google or camera)</span>
                        <span class="mono">128-BIT</span>
                    </span>
                    <code class="badge-code">${safeCode}</code>
                </div>

                <div class="badge-print-only">
                    <strong>Participant Sign-In Steps:</strong>
                    <ol>
                        <li>Open <code>/login</code> and click <strong>Sign in with Google</strong> (if your email is assigned), or scan this QR / enter the badge code above.</li>
                        <li>Confirm your seat assignment on the Boarding Pass screen.</li>
                        <li>Verify headset audio &amp; net status in <code>/ready</code> before launch.</li>
                    </ol>
                    <div class="print-equip">Station: ${safeTarget} &middot; ${equipHint}</div>
                </div>

                <div class="badge-actions no-print">
                    <button type="button" class="ghost btn-sm btn-copy" data-url="${safeJoinUrl}" data-copy-kind="Join link">Copy link</button>
                    <button type="button" class="ghost btn-sm btn-copy" data-url="${safeCode}" data-copy-kind="Badge code">Copy code</button>
                    <a href="${safeJoinUrl}" target="_blank" rel="noopener" class="navlink badge-open">Open</a>
                </div>
            `;

            const qrImg = card.querySelector(".qr-canvas");
            if (qrImg) {
                qrImg.addEventListener("load", () => qrImg.classList.remove("is-loading"));
                qrImg.addEventListener("error", () => qrImg.classList.remove("is-loading"));
            }

            rosterGrid.appendChild(card);
        });

        // Bind copy buttons in both #inviteList and #rosterGrid
        document.querySelectorAll("#rosterSection .btn-copy").forEach(btn => {
            btn.addEventListener("click", async () => {
                const url = btn.dataset.url;
                const kind = btn.dataset.copyKind || "Invite";
                try {
                    await navigator.clipboard.writeText(url);
                    const original = btn.textContent;
                    btn.textContent = "Copied!";
                    btn.classList.add("btn-copied");
                    showToast(`${kind} copied to clipboard`, "good");
                    setTimeout(() => {
                        btn.textContent = original;
                        btn.classList.remove("btn-copied");
                    }, 1800);
                } catch (e) {
                    prompt("Participant Sign-In Link:", url);
                }
            });
        });
    }

    function renderAttendanceTable() {
        if (!attendanceTableBody) return;
        attendanceTableBody.innerHTML = "";

        if (!currentRoster || currentRoster.length === 0) {
            attendanceTableBody.innerHTML = `
                <tr>
                    <td colspan="6" class="onb-table-empty">No seats provisioned yet. Click Save Roster &amp; Seat Invites in Step 3.</td>
                </tr>
            `;
            return;
        }

        const host = window.location.hostname;
        const port = window.location.port ? `:${window.location.port}` : "";
        const protocol = window.location.protocol;
        const origin = `${protocol}//${host}${port}`;
        const exTitle = (exNameInput && exNameInput.value.trim()) || currentSetup.name || "Civil Air Patrol SAREX Exercise";
        const readySeats = (latestReadyData && Array.isArray(latestReadyData.seats)) ? latestReadyData.seats : [];

        currentRoster.forEach((item, idx) => {
            const tr = document.createElement("tr");
            const matchedReady = matchReadySeat(item, readySeats, idx);

            const roleRaw = String(item.role == null ? "" : item.role);
            let rolePillClass = "role-aircrew";
            if (roleRaw === "instructor") rolePillClass = "role-instructor";
            if (roleRaw === "base") rolePillClass = "role-base";
            if (roleRaw === "ground_team") rolePillClass = "role-ground";
            const roleLabel = esc(roleRaw.replace("_", " ").toUpperCase());

            // Merge email, last_login, and last_login_via from roster + /api/ready
            const emailVal = item.email || (matchedReady && matchedReady.email) || null;
            const lastLoginVal = item.last_login || (matchedReady && matchedReady.last_login) || null;
            const lastViaVal = item.last_login_via || (matchedReady && matchedReady.last_login_via) || null;

            const hasLogin = Boolean(lastLoginVal);
            let loginBadgeClass = "warn";
            let loginMethodLabel = "Not signed in yet";
            let loginTimeLabel = emailVal ? "Awaiting Google or badge sign-in" : "Awaiting badge sign-in";
            if (hasLogin) {
                loginBadgeClass = "good";
                if (lastViaVal === "oidc") {
                    loginMethodLabel = "Signed in with Google";
                } else if (lastViaVal === "badge") {
                    loginMethodLabel = "Signed in with badge";
                } else {
                    loginMethodLabel = "Signed in";
                }
                loginTimeLabel = formatTimestamp(lastLoginVal);
            }

            let readyStatusClass = "untracked";
            let readyStatusLabel = "Not signed in yet";
            let readyDetailText = "No active station page";
            if (matchedReady) {
                const st = String(matchedReady.status || "invited").toLowerCase();
                if (st === "ready" || st === "flying") {
                    readyStatusClass = "good";
                    readyStatusLabel = st === "flying" ? "FLYING" : "READY (GO)";
                } else if (st === "on_net") {
                    readyStatusClass = "good";
                    readyStatusLabel = "ON THE NET";
                } else if (st === "joined") {
                    readyStatusClass = "info";
                    readyStatusLabel = "JOINED";
                } else if (st === "stale" || st === "lost") {
                    readyStatusClass = "warn";
                    readyStatusLabel = st.toUpperCase();
                } else {
                    readyStatusClass = "untracked";
                    readyStatusLabel = hasLogin ? "SIGNED IN" : "Not signed in yet";
                }
                const seenAgo = matchedReady.seen_ago;
                readyDetailText = seenAgo != null
                    ? `Seen ${Math.round(seenAgo)}s ago on ${matchedReady.page || "/"}`
                    : `Console ${item.target_url || "/"}`;
            }

            const joinUrl = `${origin}/join/${encodeURIComponent(item.code || "")}`;
            const loginUrl = `${origin}/login`;
            const primarySignInUrl = emailVal ? loginUrl : joinUrl;
            const mailtoHref = buildMailtoHref(
                Object.assign({}, item, { email: emailVal }),
                exTitle,
                origin
            );

            // Pre-escape all values before innerHTML assignment
            const safeTitle = esc(item.title);
            const safeAssigned = esc(item.assigned_name || "");
            const safeCallsign = esc(item.callsign || "");
            const safeTarget = esc(item.target_url || "/");
            const safeEmailHtml = emailVal
                ? `<span class="mono" style="font-weight:600">${esc(emailVal)}</span><div class="notes">Google sign-in enabled</div>`
                : `<span class="notes">No email assigned</span><div class="notes mono">Badge code only</div>`;
            const safeLoginMethod = esc(loginMethodLabel);
            const safeLoginTime = esc(loginTimeLabel);
            const safeReadyLabel = esc(readyStatusLabel);
            const safeReadyDetail = esc(readyDetailText);
            const safeCopyUrl = esc(primarySignInUrl);
            const safeMailto = esc(mailtoHref);

            tr.innerHTML = `
                <td>
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                        <span class="onb-role-pill ${rolePillClass}">${roleLabel}</span>
                        <strong>${safeTitle}</strong>
                    </div>
                    <div class="notes">${safeAssigned}</div>
                </td>
                <td>
                    <div class="mono" style="font-weight:700">${safeCallsign}</div>
                    <div class="notes mono">Opens ${safeTarget}</div>
                </td>
                <td>
                    ${safeEmailHtml}
                </td>
                <td>
                    <span class="onb-pill ${loginBadgeClass}">${safeLoginMethod}</span>
                    <div class="notes mono">${safeLoginTime}</div>
                </td>
                <td>
                    <span class="onb-pill ${readyStatusClass} mono">${safeReadyLabel}</span>
                    <div class="notes mono">${safeReadyDetail}</div>
                </td>
                <td class="text-right">
                    <div style="display:inline-flex;gap:6px;flex-wrap:wrap;justify-content:flex-end">
                        <button type="button" class="ghost btn-sm btn-copy-row" data-url="${safeCopyUrl}">Copy Link</button>
                        <a href="${safeMailto}" class="onb-btn ghost btn-sm">Email</a>
                    </div>
                </td>
            `;
            attendanceTableBody.appendChild(tr);
        });

        attendanceTableBody.querySelectorAll(".btn-copy-row").forEach(btn => {
            btn.addEventListener("click", async () => {
                const url = btn.dataset.url;
                try {
                    await navigator.clipboard.writeText(url);
                    showToast("Sign-in link copied to clipboard", "good");
                } catch (e) {
                    prompt("Participant Sign-In Link:", url);
                }
            });
        });
    }

    function matchReadySeat(rosterItem, readySeats, idx) {
        if (!readySeats || readySeats.length === 0) return null;
        const byId = readySeats.find(s => s.id && rosterItem.id && s.id === rosterItem.id);
        if (byId) return byId;
        const codePrefix = String(rosterItem.code || "").split("-")[0].toUpperCase();
        const csNorm = String(rosterItem.callsign || "").trim().toUpperCase();
        const titleNorm = String(rosterItem.title || "").trim().toUpperCase();

        return readySeats.find(s => {
            const sSeat = String(s.seat || "").toUpperCase();
            const sLabel = String(s.label || "").toUpperCase();
            if (codePrefix === "INSTR" && (sSeat === "IC" || sSeat === "DIRECTOR")) return true;
            if (csNorm === "MRO 1" && (sSeat === "MRO" || sSeat === "MRO1")) return true;
            if (csNorm === "MRO 2" && (sSeat === "MRO" || sSeat === "MRO2")) return true;
            if (csNorm === "UDF 1" && (sSeat === "UDF" || sSeat === "UDF1")) return true;
            if (csNorm === "UDF 2" && (sSeat === "UDF" || sSeat === "UDF2")) return true;
            if (sLabel && titleNorm && sLabel === titleNorm) return true;
            return false;
        }) || readySeats[idx] || null;
    }

    async function copyAllInviteLinks() {
        if (!currentRoster || currentRoster.length === 0) {
            showToast("No participant seats available to copy.", "warn");
            return;
        }
        const host = window.location.hostname;
        const port = window.location.port ? `:${window.location.port}` : "";
        const protocol = window.location.protocol;
        const origin = `${protocol}//${host}${port}`;
        const exTitle = (exNameInput && exNameInput.value.trim()) || currentSetup.name || "CAP V-SAR Exercise";

        const lines = [
            `=== ${exTitle} — PARTICIPANT SIGN-IN ROSTER ===`,
            `EXERCISE TRAFFIC ONLY · NOT A REAL DISTRESS`,
            `Sign-In Page: ${origin}/login`,
            ""
        ];
        currentRoster.forEach(item => {
            const joinUrl = `${origin}/join/${item.code}`;
            lines.push(`[${String(item.role || "").toUpperCase()}] ${item.title} (${item.callsign})`);
            if (item.email) {
                lines.push(`  Assigned Google Email : ${item.email} (Sign in with Google at ${origin}/login)`);
            } else {
                lines.push(`  Assigned Google Email : None (use badge link or code below)`);
            }
            lines.push(`  Offline Badge Link    : ${joinUrl}`);
            lines.push(`  Offline Badge Code    : ${item.code}`);
            lines.push("");
        });

        const text = lines.join("\n");
        try {
            await navigator.clipboard.writeText(text);
            showToast(`Copied sign-in details for all ${currentRoster.length} seats`, "good");
        } catch (e) {
            prompt("Copy all participant sign-in details:", text);
        }
    }

    function getRoleEquipmentHint(role) {
        if (role === "instructor") return "Director Console + Fault/Weather Controls";
        if (role === "base") return "Headset + Mic + CAP Form 110 Log";
        if (role === "ground_team") return "Mobile PTT + Compass Bearing Entry";
        return "Flight Deck + VHF/DF Receiver + Mic";
    }

    function formatTimestamp(ts) {
        if (!ts) return "Not signed in yet";
        const num = Number(ts);
        if (Number.isFinite(num) && num > 1e9) {
            try {
                const iso = new Date(num * 1000).toISOString();
                return iso.slice(0, 10) + " " + iso.slice(11, 16) + "Z";
            } catch (e) {
                // Fall through to string handling
            }
        }
        const s = String(ts);
        if (s.length >= 16 && s.includes("T")) {
            return s.slice(0, 10) + " " + s.slice(11, 16) + "Z";
        }
        return s;
    }

    window.addEventListener("DOMContentLoaded", init);
})();
