/**
 * CAP V-SAR Exercise & Fleet Setup Controller
 * Manages aircraft fleet, staff roster, code generation, and client-side QR rendering.
 */
(function() {
    let currentSetup = {
        name: "Civil Air Patrol SAREX Exercise",
        num_aircraft: 1,
        aircraft: [
            { id: "ac-1", callsign: "CAP 423", tail: "N499CP", df_model: "Becker SAR-DF 517", crew: ["pilot", "observer", "scanner"] }
        ],
        staff: [
            { role: "base", title: "Mission Radio Operator 1", callsign: "MRO 1" },
            { role: "base", title: "Mission Radio Operator 2", callsign: "MRO 2" },
            { role: "ground_team", title: "Ground Search Team 1", callsign: "UDF 1" }
        ]
    };
    let scenarios = [];

    // DOM Elements
    const exNameInput = document.getElementById("exName");
    const exScenarioSelect = document.getElementById("exScenario");
    const scenarioDesc = document.getElementById("scenarioDesc");
    const aircraftGrid = document.getElementById("aircraftGrid");
    const saveSetupBtn = document.getElementById("saveSetupBtn");
    const resetSetupBtn = document.getElementById("resetSetupBtn");
    const printBadgesBtn = document.getElementById("printBadgesBtn");
    const rosterGrid = document.getElementById("rosterGrid");
    const rosterCount = document.getElementById("rosterCount");
    const userBadge = document.getElementById("userBadge");
    const logoutBtn = document.getElementById("logoutBtn");

    async function init() {
        await checkAuth();
        await loadScenarios();
        await loadSetup();
        bindEvents();
    }

    async function checkAuth() {
        try {
            const res = await fetch("/api/auth/me");
            const data = await res.json();
            if (data.authenticated && data.role === "instructor") {
                userBadge.textContent = "👤 " + (data.title || "Instructor");
            } else if (!data.authenticated) {
                // If unauthenticated and tokens configured, redirect to login
                const testRes = await fetch("/api/setup");
                if (testRes.status === 403 || testRes.status === 401) {
                    window.location.href = "/login?next=/setup";
                }
            }
        } catch (e) {
            console.error("Auth check failed", e);
        }
    }

    async function loadScenarios() {
        try {
            const res = await fetch("/api/scenarios");
            scenarios = await res.json();
            exScenarioSelect.innerHTML = "";
            scenarios.forEach(sc => {
                const opt = document.createElement("option");
                opt.value = sc.id;
                opt.textContent = sc.name;
                exScenarioSelect.appendChild(opt);
            });
            updateScenarioDesc();
        } catch (e) {
            console.error("Failed to load scenarios", e);
        }
    }

    function updateScenarioDesc() {
        const sc = scenarios.find(s => s.id === exScenarioSelect.value);
        if (sc) {
            scenarioDesc.textContent = (sc.notes || "") + (sc.band ? ` | Band: ${sc.band} MHz` : "");
        } else {
            scenarioDesc.textContent = "";
        }
    }

    async function loadSetup() {
        try {
            const res = await fetch("/api/setup");
            if (res.status === 403) {
                window.location.href = "/login?next=/setup";
                return;
            }
            const data = await res.json();
            if (data.name) exNameInput.value = data.name;
            if (data.config && data.config.aircraft) {
                currentSetup.aircraft = data.config.aircraft;
                currentSetup.num_aircraft = data.num_aircraft || data.config.aircraft.length || 1;
            }
            renderStepper();
            renderAircraftCards();
            renderRoster(data.roster || []);
        } catch (e) {
            console.error("Failed to load setup", e);
            renderStepper();
            renderAircraftCards();
        }
    }

    function bindEvents() {
        exScenarioSelect.addEventListener("change", updateScenarioDesc);

        // Aircraft Count Stepper buttons
        document.querySelectorAll(".btn-stepper").forEach(btn => {
            btn.addEventListener("click", () => {
                const count = parseInt(btn.dataset.count, 10);
                setAircraftCount(count);
            });
        });

        // Save & Generate
        saveSetupBtn.addEventListener("click", saveSetup);
        resetSetupBtn.addEventListener("click", resetSetup);
        printBadgesBtn.addEventListener("click", () => window.print());

        if (logoutBtn) {
            logoutBtn.addEventListener("click", async () => {
                await fetch("/api/auth/logout", { method: "POST" });
                window.location.href = "/login";
            });
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
                crew: ["pilot", "observer", "scanner"]
            });
        }
        if (currentSetup.aircraft.length > count) {
            currentSetup.aircraft = currentSetup.aircraft.slice(0, count);
        }
        renderStepper();
        renderAircraftCards();
    }

    function renderAircraftCards() {
        aircraftGrid.innerHTML = "";
        currentSetup.aircraft.forEach((ac, idx) => {
            const card = document.createElement("div");
            card.className = "ac-config-card";
            card.innerHTML = `
                <div class="ac-card-header">
                    <b>✈️ Aircraft ${idx + 1}</b>
                    <span class="tag mono">${ac.callsign}</span>
                </div>
                <div class="form-grid" style="margin-top:10px">
                    <div>
                        <label>Call Sign</label>
                        <input type="text" class="ac-callsign" data-index="${idx}" value="${ac.callsign}">
                    </div>
                    <div>
                        <label>Tail Number</label>
                        <input type="text" class="ac-tail" data-index="${idx}" value="${ac.tail}">
                    </div>
                </div>
                <div style="margin-top:8px">
                    <label>Direction Finder (DF) Receiver Model</label>
                    <select class="ac-df" data-index="${idx}">
                        <option value="Becker SAR-DF 517" ${ac.df_model.includes("517") ? "selected" : ""}>Becker SAR-DF 517 (Standard)</option>
                        <option value="RHOTHETA RT-600" ${ac.df_model.includes("600") ? "selected" : ""}>RHOTHETA RT-600 (Advanced 19-Channel Grid)</option>
                    </select>
                </div>
                <div style="margin-top:10px">
                    <label>Aircrew Positions to Staff</label>
                    <div class="crew-options">
                        <label class="checkbox-inline">
                            <input type="checkbox" class="crew-pilot" data-index="${idx}" ${ac.crew.includes("pilot") ? "checked" : ""}> Pilot
                        </label>
                        <label class="checkbox-inline">
                            <input type="checkbox" class="crew-obs" data-index="${idx}" ${ac.crew.includes("observer") ? "checked" : ""}> Observer
                        </label>
                        <label class="checkbox-inline">
                            <input type="checkbox" class="crew-scn" data-index="${idx}" ${ac.crew.includes("scanner") ? "checked" : ""}> Scanner
                        </label>
                    </div>
                </div>
            `;
            aircraftGrid.appendChild(card);
        });

        // Bind aircraft card inputs
        aircraftGrid.querySelectorAll(".ac-callsign").forEach(el => {
            el.addEventListener("input", e => {
                const i = parseInt(e.target.dataset.index, 10);
                currentSetup.aircraft[i].callsign = e.target.value;
            });
        });
        aircraftGrid.querySelectorAll(".ac-tail").forEach(el => {
            el.addEventListener("input", e => {
                const i = parseInt(e.target.dataset.index, 10);
                currentSetup.aircraft[i].tail = e.target.value;
            });
        });
        aircraftGrid.querySelectorAll(".ac-df").forEach(el => {
            el.addEventListener("change", e => {
                const i = parseInt(e.target.dataset.index, 10);
                currentSetup.aircraft[i].df_model = e.target.value;
            });
        });
        aircraftGrid.querySelectorAll(".crew-pilot, .crew-obs, .crew-scn").forEach(el => {
            el.addEventListener("change", () => {
                aircraftGrid.querySelectorAll(".ac-config-card").forEach((c, idx) => {
                    const crew = [];
                    if (c.querySelector(".crew-pilot").checked) crew.push("pilot");
                    if (c.querySelector(".crew-obs").checked) crew.push("observer");
                    if (c.querySelector(".crew-scn").checked) crew.push("scanner");
                    currentSetup.aircraft[idx].crew = crew;
                });
            });
        });
    }

    async function saveSetup() {
        saveSetupBtn.disabled = true;
        saveSetupBtn.textContent = "Generating Roster & Codes...";

        // Collect ground staff
        const staff = [
            { role: "base", title: "Mission Radio Operator 1", callsign: "MRO 1" }
        ];
        if (document.getElementById("staffMro2").checked) {
            staff.push({ role: "base", title: "Mission Radio Operator 2", callsign: "MRO 2" });
        }
        if (document.getElementById("staffUdf1").checked) {
            staff.push({ role: "ground_team", title: "Ground Search Team 1", callsign: "UDF 1" });
        }
        if (document.getElementById("staffUdf2").checked) {
            staff.push({ role: "ground_team", title: "Ground Search Team 2", callsign: "UDF 2" });
        }

        const payload = {
            name: exNameInput.value.trim() || "Civil Air Patrol SAREX Exercise",
            num_aircraft: currentSetup.num_aircraft,
            aircraft: currentSetup.aircraft,
            staff: staff
        };

        try {
            const res = await fetch("/api/setup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (!res.ok) {
                const err = await res.json();
                alert("Failed to save setup: " + (err.detail || res.statusText));
                return;
            }
            const data = await res.json();
            renderRoster(data.roster || []);
            document.getElementById("rosterSection").scrollIntoView({ behavior: "smooth" });
        } catch (e) {
            alert("Error saving setup: " + e.message);
        } finally {
            saveSetupBtn.disabled = false;
            saveSetupBtn.textContent = "Generate Roster & Invite Codes";
        }
    }

    async function resetSetup() {
        if (!confirm("Reset to default 1-aircraft and standard staff roster?")) return;
        try {
            const res = await fetch("/api/setup/reset", { method: "POST" });
            const data = await res.json();
            currentSetup.aircraft = data.config.aircraft;
            currentSetup.num_aircraft = data.num_aircraft || 1;
            renderStepper();
            renderAircraftCards();
            renderRoster(data.roster || []);
        } catch (e) {
            alert("Error resetting setup: " + e.message);
        }
    }

    function renderRoster(roster) {
        rosterGrid.innerHTML = "";
        rosterCount.textContent = `${roster.length} Participants`;

        const host = window.location.hostname;
        // Construct mobile friendly port: if accessing over standard Caddy port 8743 or current port
        const port = window.location.port ? `:${window.location.port}` : "";
        const protocol = window.location.protocol;

        roster.forEach(item => {
            const card = document.createElement("div");
            card.className = `roster-badge-card role-${item.role}`;

            const joinUrl = `${protocol}//${host}${port}/join/${item.code}`;
            const qrId = `qr-${item.code.replace(/[^a-zA-Z0-9]/g, "_")}`;

            let roleBadgeClass = "badge-aircrew";
            if (item.role === "instructor") roleBadgeClass = "badge-instructor";
            if (item.role === "base") roleBadgeClass = "badge-base";
            if (item.role === "ground_team") roleBadgeClass = "badge-ground";

            card.innerHTML = `
                <div class="badge-top">
                    <span class="role-badge ${roleBadgeClass}">${item.role.toUpperCase()}</span>
                    <span class="badge-code mono">${item.code}</span>
                </div>
                <div class="badge-title">${item.title}</div>
                <div class="badge-meta mono">Callsign: <b>${item.callsign || "-"}</b></div>

                <div class="badge-qr-container">
                    <div id="${qrId}" class="qr-canvas"></div>
                    <span class="qr-label">Scan with camera to join</span>
                </div>

                <div class="badge-dest-info">
                    <span class="dest-tag">Target: <b>${item.target_url || "/"}</b></span>
                </div>

                <div class="badge-actions no-print">
                    <button class="ghost btn-sm btn-copy" data-url="${joinUrl}">Copy Invite Link</button>
                    <a href="${joinUrl}" target="_blank" class="navlink" style="color:var(--blue);border-color:var(--line);text-align:center;font-size:11px">Open</a>
                </div>
            `;
            rosterGrid.appendChild(card);

            // Render vector QR code
            setTimeout(() => {
                if (window.QRCode) {
                    new QRCode(qrId, {
                        text: joinUrl,
                        width: 130,
                        height: 130,
                        colorDark: "#0B2545",
                        colorLight: "#FFFFFF",
                        correctLevel: 1
                    });
                }
            }, 10);
        });

        // Copy button handlers
        rosterGrid.querySelectorAll(".btn-copy").forEach(btn => {
            btn.addEventListener("click", async () => {
                const url = btn.dataset.url;
                try {
                    await navigator.clipboard.writeText(url);
                    const original = btn.textContent;
                    btn.textContent = "✓ Copied!";
                    btn.classList.add("btn-copied");
                    setTimeout(() => {
                        btn.textContent = original;
                        btn.classList.remove("btn-copied");
                    }, 1800);
                } catch (e) {
                    prompt("Participant Invite Link:", url);
                }
            });
        });
    }

    window.addEventListener("DOMContentLoaded", init);
})();

