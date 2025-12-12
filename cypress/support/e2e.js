// ***********************************************************
// cypress/support/e2e.js
// This file is processed and loaded automatically before your test files.
// ***********************************************************

// Import commands.js
import "./commands";

// Hide fetch/XHR logs to reduce noise (safe + guarded)
(function hideRequestLogs() {
  try {
    const topWin = window.top;
    if (!topWin || !topWin.document || !topWin.document.head) return;

    if (!topWin.document.head.querySelector("[data-hide-command-log-request]")) {
      const style = topWin.document.createElement("style");
      style.innerHTML = `
        .command-name-request,
        .command-name-xhr { display: none !important; }
      `;
      style.setAttribute("data-hide-command-log-request", "");
      topWin.document.head.appendChild(style);
    }
  } catch (e) {
    // Ignore timing / cross-origin quirks in the Cypress runner
  }
})();

// IMPORTANT: do NOT blanket-ignore all uncaught exceptions (it hides real bugs)
// Only ignore known benign browser noise.
const IGNORED_UNCAUGHT = [
  "ResizeObserver loop limit exceeded",
  "ResizeObserver loop completed with undelivered notifications",
];

Cypress.on("uncaught:exception", (err) => {
  const msg = String(err?.message || "");
  if (IGNORED_UNCAUGHT.some((m) => msg.includes(m))) {
    return false; // don't fail the test for these
  }
  // otherwise: let Cypress fail (so we catch real regressions)
});
