/**
 * CAP V-SAR Participant Login Controller
 */
(function() {
    const loginForm = document.getElementById("loginForm");
    const accessCodeInput = document.getElementById("accessCode");
    const loginSubmitBtn = document.getElementById("loginSubmitBtn");
    const loginError = document.getElementById("loginError");

    const urlParams = new URLSearchParams(window.location.search);
    const nextUrl = urlParams.get("next");
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

    document.querySelectorAll(".btn-code-shortcut").forEach(btn => {
        btn.addEventListener("click", () => {
            accessCodeInput.value = btn.dataset.code;
            submitLogin(btn.dataset.code);
        });
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
