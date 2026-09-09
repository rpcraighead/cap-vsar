/* ==========================================================================
   CAP V-SAR Product Website JavaScript
   Interactive components: Lightbox, Tabs, RF Calculator, Mobile Nav
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
  initMobileNav();
  initTabs();
  initLightbox();
  initRfCalculator();
  initCodeCopy();
});

/* Mobile Navigation Toggle */
function initMobileNav() {
  const toggle = document.querySelector(".mobile-toggle");
  const navbar = document.querySelector(".navbar");

  if (toggle && navbar) {
    toggle.addEventListener("click", () => {
      navbar.classList.toggle("open");
    });
  }
}

/* Tab Component */
function initTabs() {
  const tabContainers = document.querySelectorAll(".tabs-container");

  tabContainers.forEach((container) => {
    const buttons = container.querySelectorAll(".tab-btn");
    const panes = container.querySelectorAll(".tab-pane");

    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetId = btn.getAttribute("data-target");

        // Deactivate all
        buttons.forEach((b) => b.classList.remove("active"));
        panes.forEach((p) => p.classList.remove("active"));

        // Activate selected
        btn.classList.add("active");
        const targetPane = container.querySelector(`#${targetId}`);
        if (targetPane) {
          targetPane.classList.add("active");
        }
      });
    });
  });
}

/* Lightbox Modal for High-Resolution Screenshots */
function initLightbox() {
  const modal = document.getElementById("lightboxModal");
  if (!modal) return;

  const modalImg = modal.querySelector(".lightbox-image");
  const modalCap = modal.querySelector(".lightbox-caption");
  const closeBtn = modal.querySelector(".lightbox-close");

  // Clickable triggers
  const zoomTriggers = document.querySelectorAll("[data-lightbox]");

  zoomTriggers.forEach((el) => {
    el.addEventListener("click", () => {
      const src = el.getAttribute("data-lightbox");
      const caption = el.getAttribute("data-caption") || "";

      modalImg.src = src;
      modalCap.textContent = caption;
      modal.classList.add("active");
      document.body.style.overflow = "hidden";
    });
  });

  const closeModal = () => {
    modal.classList.remove("active");
    document.body.style.overflow = "";
  };

  if (closeBtn) closeBtn.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("active")) {
      closeModal();
    }
  });
}

/* Interactive RF Horizon & Propagation Calculator */
function initRfCalculator() {
  const txAltInput = document.getElementById("calcTxAlt");
  const rxAltInput = document.getElementById("calcRxAlt");
  const freqInput = document.getElementById("calcFreq");
  const txPwrInput = document.getElementById("calcTxPwr");

  const outHorizon = document.getElementById("calcOutHorizon");
  const outFspl = document.getElementById("calcOutFspl");
  const outMargin = document.getElementById("calcOutMargin");

  if (!txAltInput || !rxAltInput || !outHorizon) return;

  function calculate() {
    const hTx = parseFloat(txAltInput.value) || 0; // ft AGL
    const hRx = parseFloat(rxAltInput.value) || 0; // ft AGL
    const freq = parseFloat(freqInput ? freqInput.value : 121.5) || 121.5; // MHz
    const txPwr = parseFloat(txPwrInput ? txPwrInput.value : 100) || 100; // mW

    // Radio Line of Sight (nautical miles): d ≈ 1.23 * (sqrt(h_tx) + sqrt(h_rx))
    const dHorizonNm = 1.23 * (Math.sqrt(Math.max(0, hTx)) + Math.sqrt(Math.max(0, hRx)));

    // Path loss at radio horizon (dB): FSPL = 32.44 + 20*log10(d_km) + 20*log10(f_MHz)
    const dKm = Math.max(1, dHorizonNm * 1.852);
    const fsplDb = 32.44 + 20 * Math.log10(dKm) + 20 * Math.log10(freq);

    // Transmit power in dBm: P_dBm = 10 * log10(P_mW)
    const txPwrDbm = 10 * Math.log10(Math.max(1, txPwr));
    // Approximate received power at horizon: P_rx = P_tx - FSPL + G_ant
    const rxSensDbm = -107; // Typical DF receiver sensitivity (~1 uV)
    const rxPwrDbm = txPwrDbm - fsplDb + 2; // +2 dBi antenna gain
    const marginDb = rxPwrDbm - rxSensDbm;

    outHorizon.textContent = `${dHorizonNm.toFixed(1)} NM`;
    if (outFspl) outFspl.textContent = `${fsplDb.toFixed(1)} dB`;
    if (outMargin) {
      outMargin.textContent = marginDb >= 0 ? `+${marginDb.toFixed(1)} dB (Solid)` : `${marginDb.toFixed(1)} dB (Marginal)`;
      outMargin.style.color = marginDb >= 0 ? "#10b981" : "#ef4444";
    }
  }

  [txAltInput, rxAltInput, freqInput, txPwrInput].forEach((el) => {
    if (el) el.addEventListener("input", calculate);
  });

  calculate();
}

/* Copy Code Snippets to Clipboard */
function initCodeCopy() {
  const codeBlocks = document.querySelectorAll(".tech-box");

  codeBlocks.forEach((box) => {
    const copyBtn = box.querySelector(".copy-btn");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        const code = box.querySelector("code");
        if (code) {
          navigator.clipboard.writeText(code.innerText).then(() => {
            const originalText = copyBtn.textContent;
            copyBtn.textContent = "Copied!";
            setTimeout(() => {
              copyBtn.textContent = originalText;
            }, 2000);
          });
        }
      });
    }
  });
}

