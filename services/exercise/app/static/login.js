/**
 * CAP V-SAR Participant Login Controller
 * Handles Google / OIDC provider discovery, badge code verification,
 * smart /join/{code} URL extraction, active session detection, sign-out,
 * and plain-language error messages for CAP volunteers.
 */
(function() {
    // BEGIN F2-6 PURE NEXT URL
    // `next` arrives in the query string, so anyone can put anything in it. Only
    // a same-origin path is followed: it must start with exactly one "/", and
    // carry no backslash or control character, because browsers read "/\\x" and
    // "/<tab>/x" as "//x" - a protocol-relative URL to another host. Anything
    // else is dropped and the login falls back to the role's own landing page.
    function safeNext(raw, origin) {
        if (typeof raw !== "string" || raw === "") return null;
        if (raw[0] !== "/" || raw[1] === "/" || raw[1] === "\\") return null;
        if (/[\\\u0000-\u001f\u007f]/.test(raw)) return null;
        try {
            const base = origin || window.location.origin;
            if (new URL(raw, base).origin !== base) return null;
        } catch (e) { return null; }
        return raw;
    }
    // END F2-6 PURE NEXT URL

    const loginForm = document.getElementById("loginForm");
    const accessCodeInput = document.getElementById("accessCode");
    const loginSubmitBtn = document.getElementById("loginSubmitBtn");
    const loginError = document.getElementById("loginError");
    const pasteCodeBtn = document.getElementById("pasteCodeBtn");
    const codeFormatHint = document.getElementById("codeFormatHint");
    const loginDestPreview = document.getElementById("loginDestPreview");
    const loginSubtitleHint = document.getElementById("loginSubtitleHint");
    const activeSessionBanner = document.getElementById("activeSessionBanner");
    const activeSessionTitle = document.getElementById("activeSessionTitle");
    const activeSessionMeta = document.getElementById("activeSessionMeta");
    const activeSessionContinueBtn = document.getElementById("activeSessionContinueBtn");
    const activeSessionLogoutBtn = document.getElementById("activeSessionLogoutBtn");
    const loginZuluClock = document.getElementById("loginZuluClock");
    const loginThemeToggle = document.getElementById("loginThemeToggle");

    // OIDC & Badge section elements
    const oidcSection = document.getElementById("oidcSection");
    const oidcLoginBtn = document.getElementById("oidcLoginBtn");
    const oidcLoginLabel = document.getElementById("oidcLoginLabel");
    const oidcDivider = document.getElementById("oidcDivider");
    const badgeSection = document.getElementById("badgeSection");
    const badgeSectionTitle = document.getElementById("badgeSectionTitle");
    const badgeFallbackTag = document.getElementById("badgeFallbackTag");

    const urlParams = new URLSearchParams(window.location.search);
    const nextUrl = safeNext(urlParams.get("next"));
    const errorParam = urlParams.get("error");
    const codeParam = urlParams.get("code");

    initTheme();
    startClock();
    loadProviders();
    checkExistingSession();

    if (nextUrl && loginDestPreview) {
        loginDestPreview.textContent = `Requested station: ${nextUrl}`;
        loginDestPreview.style.display = "inline-flex";
    }

    if (codeParam) {
        accessCodeInput.value = extractCodeFromRaw(codeParam);
        updateFormatHint();
    }

    // Plain-language error messages for CAP volunteers (no technical jargon)
    if (errorParam === "oidc_cancelled") {
        showError(
            "Sign-in was cancelled. Click the Sign in with Google button to try again, " +
            "or sign in below with the badge code from your briefing card."
        );
    } else if (errorParam === "oidc_failed") {
        showError(
            "Google sign-in did not complete. Your sign-in attempt may have expired, " +
            "your email address may not be verified, or your account may be outside your wing's organization domain. " +
            "Please try again, or use your badge code below."
        );
    } else if (errorParam === "invalid_code") {
        // A verified email with no seat never comes back here: the callback
        // answers it with its own 403 page ("no seat", CONTRACT §4), so there
        // is no error=no_seat value to handle.
        const attempted = codeParam ? ` ("${codeParam}")` : "";
        showError(
            `That badge code${attempted} was not recognized or was replaced when the Exercise Director updated the roster. ` +
            "Check the code on your current briefing card, or sign in with Google if your email was assigned a seat."
        );
    } else if (errorParam === "instructor_required") {
        showError(
            "Exercise Director sign-in is required to open that screen. " +
            "Please sign in with the Exercise Director Google account or the Instructor badge code."
        );
    }

    async function loadProviders() {
        try {
            const res = await fetch("/api/auth/providers", { cache: "no-store" });
            if (!res.ok) return;
            const data = await res.json();
            const oidc = data && data.oidc;
            if (oidc && oidc.enabled) {
                const label = String(oidc.label || "Sign in with Google");
                const baseLoginUrl = safeNext(oidc.login_url) || "/auth/oidc/login";
                const fullHref = nextUrl
                    ? `${baseLoginUrl}?next=${encodeURIComponent(nextUrl)}`
                    : baseLoginUrl;

                if (oidcLoginLabel) {
                    oidcLoginLabel.textContent = label;
                }
                if (oidcLoginBtn) {
                    oidcLoginBtn.setAttribute("href", fullHref);
                }
                if (oidcSection) {
                    oidcSection.style.display = "block";
                }
                if (oidcDivider) {
                    oidcDivider.style.display = "flex";
                }
                if (badgeSection) {
                    badgeSection.classList.add("is-secondary");
                }
                if (badgeSectionTitle) {
                    badgeSectionTitle.textContent = "Sign in with a badge code (offline / field use)";
                }
                if (badgeFallbackTag) {
                    badgeFallbackTag.style.display = "inline-flex";
                }
                if (loginSubtitleHint) {
                    loginSubtitleHint.textContent =
                        "Sign in with the Google account assigned to your seat, or use the badge code from your briefing card.";
                }
                if (loginSubmitBtn) {
                    loginSubmitBtn.classList.remove("primary");
                    loginSubmitBtn.classList.add("ghost");
                }
            } else {
                // OIDC not configured: show only the badge login as primary
                if (oidcSection) oidcSection.style.display = "none";
                if (oidcDivider) oidcDivider.style.display = "none";
                if (badgeSection) badgeSection.classList.remove("is-secondary");
                if (badgeSectionTitle) badgeSectionTitle.textContent = "Sign in with a badge code";
                if (badgeFallbackTag) badgeFallbackTag.style.display = "none";
                if (loginSubtitleHint) {
                    loginSubtitleHint.textContent =
                        "Enter the badge code from your briefing card, paste your invite link, or scan your QR badge.";
                }
            }
        } catch (e) {
            // Offline or unreachable: badge form stays visible as primary
        }
    }

    function initTheme() {
        try {
            const saved = localStorage.getItem("cap_vsar_theme");
            if (saved === "light" || saved === "dark") {
                document.documentElement.setAttribute("data-theme", saved);
                document.body.setAttribute("data-theme", saved);
            }
        } catch (e) {
            // Ignore storage errors
        }
        if (loginThemeToggle) {
            loginThemeToggle.addEventListener("click", () => {
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
            });
        }
    }

    function startClock() {
        if (!loginZuluClock) return;
        const tick = () => {
            loginZuluClock.textContent = new Date().toISOString().slice(11, 19) + "Z";
        };
        tick();
        setInterval(tick, 1000);
    }

    async function checkExistingSession() {
        if (!activeSessionBanner) return;
        try {
            const res = await fetch("/api/auth/me");
            if (!res.ok) return;
            const data = await res.json();
            if (data && data.authenticated) {
                const dest = nextUrl || safeNext(data.target_url) || "/";
                if (activeSessionTitle) {
                    activeSessionTitle.textContent = `Signed in as ${data.title || "Participant"}`;
                }
                if (activeSessionMeta) {
                    const viaLabel = data.via === "oidc"
                        ? (data.email ? `Signed in with Google (${data.email})` : "Signed in with Google")
                        : "Signed in with badge code";
                    activeSessionMeta.textContent =
                        `Callsign: ${data.callsign || "ASSIGNED"} · Role: ${String(data.role || "").toUpperCase()} · ${viaLabel}`;
                }
                if (activeSessionContinueBtn) {
                    activeSessionContinueBtn.setAttribute("href", dest);
                    activeSessionContinueBtn.textContent = `Continue to ${dest} \u2192`;
                }
                activeSessionBanner.style.display = "flex";
            }
        } catch (e) {
            // Silent fallback when offline or unauthenticated
        }
    }

    if (activeSessionLogoutBtn) {
        activeSessionLogoutBtn.addEventListener("click", async () => {
            try {
                await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
            } catch (e) {
                // Ignore network error
            }
            activeSessionBanner.style.display = "none";
        });
    }

    function extractCodeFromRaw(raw) {
        if (!raw) return "";
        let trimmed = String(raw).trim();
        const joinMatch = trimmed.match(/\/join\/([^/?#\s]+)/i);
        if (joinMatch && joinMatch[1]) {
            try {
                trimmed = decodeURIComponent(joinMatch[1]);
            } catch (e) {
                trimmed = joinMatch[1];
            }
        }
        return trimmed.toUpperCase();
    }

    function updateFormatHint() {
        if (!codeFormatHint) return;
        const val = accessCodeInput.value.trim();
        if (!val) {
            codeFormatHint.className = "onb-field-feedback";
            codeFormatHint.textContent = "Tip: You can paste either your badge code or a full /join/... invite link.";
            return;
        }
        if (val.length < 12) {
            codeFormatHint.className = "onb-field-feedback is-valid";
            codeFormatHint.textContent = "Enter the complete code printed on your badge (including the characters after the hyphen).";
            return;
        }
        codeFormatHint.className = "onb-field-feedback is-valid";
        codeFormatHint.textContent = "Badge code format recognized — ready to sign in.";
    }

    accessCodeInput.addEventListener("input", () => {
        accessCodeInput.value = extractCodeFromRaw(accessCodeInput.value);
        hideError();
        updateFormatHint();
    });

    accessCodeInput.addEventListener("paste", (e) => {
        const clip = e.clipboardData && e.clipboardData.getData("text");
        if (clip && clip.includes("/join/")) {
            e.preventDefault();
            accessCodeInput.value = extractCodeFromRaw(clip);
            hideError();
            updateFormatHint();
        }
    });

    if (pasteCodeBtn) {
        pasteCodeBtn.addEventListener("click", async () => {
            try {
                const text = await navigator.clipboard.readText();
                if (text) {
                    accessCodeInput.value = extractCodeFromRaw(text);
                    hideError();
                    updateFormatHint();
                    accessCodeInput.focus();
                }
            } catch (e) {
                accessCodeInput.focus();
            }
        });
    }

    loginForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const code = extractCodeFromRaw(accessCodeInput.value);
        accessCodeInput.value = code;
        if (!code) {
            showError("Please enter or paste the participant badge code from your briefing card.");
            accessCodeInput.focus();
            return;
        }
        submitLogin(code);
    });

    async function submitLogin(code) {
        loginSubmitBtn.disabled = true;
        loginSubmitBtn.textContent = "Checking Badge Code...";
        hideError();

        try {
            const res = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code })
            });

            if (!res.ok) {
                const err = await res.json();
                showError(err.detail || "Badge code not recognized. Check your briefing card and try again.");
                return;
            }

            const data = await res.json();
            const destination = nextUrl || data.target_url || "/";
            window.location.href = destination;
        } catch (e) {
            showError("Could not reach the exercise console: " + e.message);
        } finally {
            loginSubmitBtn.disabled = false;
            loginSubmitBtn.textContent = "Sign in with Badge Code";
        }
    }

    function showError(msg) {
        loginError.textContent = msg;
        loginError.style.display = "block";
    }

    function hideError() {
        loginError.style.display = "none";
        loginError.textContent = "";
    }
})();
