/**
 * CAP V-SAR Participant Login Controller
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

    const urlParams = new URLSearchParams(window.location.search);
    const nextUrl = safeNext(urlParams.get("next"));
    const errorParam = urlParams.get("error");
    const codeParam = urlParams.get("code");

    if (codeParam) {
        accessCodeInput.value = codeParam.toUpperCase();
    }

    if (errorParam === "invalid_code") {
        showError(`Invalid or expired access code: "${codeParam || ''}". Please verify your badge.`);
    } else if (errorParam === "instructor_required") {
        showError("Instructor privilege required to access the requested console. Please log in with an instructor code.");
    }

    accessCodeInput.addEventListener("input", () => {
        accessCodeInput.value = accessCodeInput.value.toUpperCase();
        hideError();
    });

    loginForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const code = accessCodeInput.value.trim().toUpperCase();
        if (!code) return;
        submitLogin(code);
    });

    async function submitLogin(code) {
        loginSubmitBtn.disabled = true;
        loginSubmitBtn.textContent = "Verifying Code...";
        hideError();

        try {
            const res = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code })
            });

            if (!res.ok) {
                const err = await res.json();
                showError(err.detail || "Authentication failed. Invalid access code.");
                return;
            }

            const data = await res.json();
            // Redirect to target destination or next param
            const destination = nextUrl || data.target_url || "/";
            window.location.href = destination;
        } catch (e) {
            showError("Network connection error: " + e.message);
        } finally {
            loginSubmitBtn.disabled = false;
            loginSubmitBtn.textContent = "Connect to Exercise Net";
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
