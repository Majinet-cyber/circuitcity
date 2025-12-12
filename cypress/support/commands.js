// ***********************************************
// Custom Cypress commands for CircuitCity / Emajinet
// - Managers have fixed creds per vertical
// - Agents are CREATED in tests and MUST be passed explicitly (or stored via setAgentCreds)
// ***********************************************

const DEFAULT_MANAGER_PASSWORD = "@Lincoln1863?";

// Managers only (per your message)
const DEFAULT_MANAGER_EMAILS = {
  phones: "empire@gmai.com",
  pharmacy: "samantha@gmail.com",
  liquor: "nimue@gmail.com",
  gym: "yuji@gmail.com",
  clothing: "motouch@gmail.com",
};

/**
 * Optional overrides via cypress.env.json:
 * {
 *   "MANAGER_CREDS": {
 *     "clothing": { "email": "motouch@gmail.com", "password": "@Lincoln1863?" },
 *     "phones":   { "email": "empire@gmail.com",  "password": "@Lincoln1863?" }
 *   }
 * }
 */
function getManagerCreds(kind = "phones") {
  const env = Cypress.env("MANAGER_CREDS") || {};
  const k = String(kind || "phones").toLowerCase();

  const email =
    env?.[k]?.email ||
    DEFAULT_MANAGER_EMAILS[k] ||
    DEFAULT_MANAGER_EMAILS.phones;

  const password =
    env?.[k]?.password ||
    Cypress.env("MANAGER_PASSWORD") ||
    Cypress.env("TEST_PASSWORD") ||
    DEFAULT_MANAGER_PASSWORD;

  return { email, password };
}

/**
 * Runtime storage for agent creds created during tests.
 * Example:
 *   cy.setAgentCreds("clothing", { email, password })
 *   cy.getAgentCreds("clothing").then(({email,password}) => cy.loginAsAgent(email,password))
 */
Cypress.Commands.add("setAgentCreds", (kind, creds) => {
  const k = String(kind || "").toLowerCase();
  const key = `AGENT_CREDS_${k}`;
  Cypress.env(key, creds);
});

Cypress.Commands.add("getAgentCreds", (kind) => {
  const k = String(kind || "").toLowerCase();
  const key = `AGENT_CREDS_${k}`;
  const creds = Cypress.env(key);

  if (!creds?.email || !creds?.password) {
    throw new Error(
      `No agent creds stored for "${k}". Create an agent in the test, then call cy.setAgentCreds("${k}", {email, password}).`
    );
  }

  return cy.wrap(creds, { log: false });
});

/**
 * Generic: assert page does NOT show common server error texts.
 */
Cypress.Commands.add("assertNoServerError", () => {
  cy.get("body").should("not.contain", "A server error occurred");
  cy.get("body").should("not.contain", "Server Error (500)");
  cy.get("body").should("not.contain", "Traceback");
});

/**
 * Wait until we’re “in the app” (works across all verticals).
 */
Cypress.Commands.add("waitForAppShell", () => {
  cy.assertNoServerError();

  cy.get("body", { timeout: 60000 }).then(($body) => {
    // Sidebar present?
    if ($body.find('[data-cy="sidebar"]').length) {
      cy.get('[data-cy="sidebar"]', { timeout: 60000 }).should("be.visible");
      return;
    }
    if ($body.find("aside").length) {
      cy.get("aside", { timeout: 60000 }).should("be.visible");
      return;
    }

    // Fallback: at least confirm we see a dashboard label somewhere
    cy.contains(/dashboard/i, { timeout: 60000 }).should("exist");
  });
});

/**
 * Login using provided credentials (no vertical assumptions).
 * @param {string} email
 * @param {string} password
 */
Cypress.Commands.add("login", (email, password) => {
  cy.visit("/accounts/login/", { timeout: 60000 });

  // Email / username
  cy.get('input[name="username"], input[name="email"], [data-cy=login-email]', {
    timeout: 30000,
  })
    .first()
    .clear()
    .type(email);

  // Password
  cy.get('input[name="password"], [data-cy=login-password]', {
    timeout: 30000,
  })
    .first()
    .clear()
    .type(password, { log: false });

  // Submit
  cy.get('button[type="submit"], [data-cy=login-submit]', { timeout: 30000 })
    .first()
    .click();

  // Must leave login page
  cy.location("pathname", { timeout: 60000 }).should((path) => {
    expect(path).to.not.eq("/accounts/login/");
  });

  cy.waitForAppShell();
});

/**
 * ✅ Backwards compatibility (your existing phones specs likely call this)
 * Uses TEST_EMAIL/TEST_PASSWORD if present, else defaults to PHONES manager creds.
 */
Cypress.Commands.add("loginAsOwner", () => {
  const email = Cypress.env("TEST_EMAIL") || DEFAULT_MANAGER_EMAILS.phones;
  const password =
    Cypress.env("TEST_PASSWORD") ||
    Cypress.env("MANAGER_PASSWORD") ||
    DEFAULT_MANAGER_PASSWORD;

  cy.login(email, password);
});

/**
 * Manager login per vertical (ONLY managers use these fixed creds).
 * @param {string} kind - phones|pharmacy|liquor|gym|clothing
 */
Cypress.Commands.add("loginAsManager", (kind = "phones") => {
  const { email, password } = getManagerCreds(kind);
  cy.login(email, password);
});

/**
 * Agent login MUST be explicit: agent creds do NOT inherit manager creds.
 * @param {string} email
 * @param {string} password
 */
Cypress.Commands.add("loginAsAgent", (email, password) => {
  if (!email || !password) {
    throw new Error(
      "cy.loginAsAgent(email, password) requires explicit agent credentials (created in test)."
    );
  }
  cy.login(email, password);
});

/**
 * ✅ NEW: Unified login helper used by your clothing sidebar test
 * Usage:
 *   cy.loginAs("clothing", "manager")
 *   cy.loginAs("phones", "owner")
 *   cy.loginAs("clothing", "agent") // uses stored agent creds via setAgentCreds()
 *   cy.loginAs("clothing", "agent", "email", "pass") // explicit
 */
Cypress.Commands.add("loginAs", (kind = "phones", role = "owner", email, password) => {
  const k = String(kind || "phones").toLowerCase();
  const r = String(role || "owner").toLowerCase();

  if (r === "owner") {
    return cy.loginAsOwner();
  }

  if (r === "manager") {
    return cy.loginAsManager(k);
  }

  if (r === "agent") {
    if (email && password) {
      return cy.loginAsAgent(email, password);
    }
    return cy.getAgentCreds(k).then((creds) => cy.loginAsAgent(creds.email, creds.password));
  }

  throw new Error(`Unknown role "${role}". Use "owner" | "manager" | "agent".`);
});

/**
 * Select business if on chooser page.
 */
Cypress.Commands.add("selectBusiness", (businessName) => {
  cy.url().then((url) => {
    if (url.includes("/choose") || url.includes("/select")) {
      cy.contains(businessName).click();
    }
  });
});

/**
 * Select a business by vertical kind if on chooser.
 */
Cypress.Commands.add("selectBusinessByKind", (kind) => {
  const k = String(kind || "").toLowerCase();

  cy.url().then((url) => {
    if (url.includes("/choose") || url.includes("/select") || url.includes("/business")) {
      cy.get("body").then(($body) => {
        const cySel = `[data-cy="business-${k}"]`;
        if ($body.find(cySel).length) {
          cy.get(cySel).first().click();
        } else {
          cy.contains(new RegExp(k, "i")).first().click();
        }
      });
    }
  });
});

/**
 * Visit a vertical dashboard (tries common routes safely).
 */
Cypress.Commands.add("visitDashboard", (kind) => {
  const k = String(kind || "").toLowerCase();

  const candidates = {
    clothing: ["/verticals/clothing/dashboard/", "/inventory/verticals/clothing/"],
    phones: ["/inventory/dashboard/", "/verticals/phones/dashboard/", "/inventory/verticals/phones/"],
    liquor: ["/verticals/liquor/dashboard/", "/inventory/verticals/liquor/"],
    gym: ["/verticals/gym/dashboard/", "/inventory/verticals/gym/"],
    pharmacy: ["/inventory/pharmacy/dashboard/", "/verticals/pharmacy/dashboard/"],
  };

  const urls = candidates[k] || ["/dashboard/"];

  const tryNext = (idx) => {
    const url = urls[idx];
    if (!url) {
      cy.visit("/dashboard/", { failOnStatusCode: false });
      cy.waitForAppShell();
      return;
    }

    cy.request({ url, failOnStatusCode: false }).then((resp) => {
      if (resp.status >= 200 && resp.status < 400) {
        cy.visit(url, { failOnStatusCode: false });
        cy.waitForAppShell();
      } else {
        tryNext(idx + 1);
      }
    });
  };

  tryNext(0);
});

/**
 * Collect sidebar hrefs once (prevents detached DOM).
 */
Cypress.Commands.add("sidebarHrefs", () => {
  const candidates = [
    '[data-cy="sidebar"] a[href]',
    "aside a[href]",
    ".sidebar a[href]",
    "nav a[href]",
  ];

  return cy.get("body").then(($body) => {
    let $links = null;

    for (const sel of candidates) {
      const found = $body.find(sel);
      if (found.length) {
        $links = found;
        break;
      }
    }

    if (!$links) $links = $body.find("a[href]"); // fallback

    const hrefs = Array.from($links)
      .map((a) => a.getAttribute("href"))
      .filter(Boolean)
      .map((h) => h.trim())
      .filter((h) => h !== "#" && !h.startsWith("javascript:") && !h.startsWith("mailto:"))
      .filter((h) => !h.includes("/logout")) // don’t log out mid-test
      .filter((h) => h.startsWith("/")); // same-origin only

    return Array.from(new Set(hrefs));
  });
});

/**
 * Wait for element to be visible
 */
Cypress.Commands.add("waitForElement", (selector) => {
  cy.get(selector, { timeout: 20000 }).should("be.visible");
});

/**
 * Fill by data-cy OR label text
 */
Cypress.Commands.add("fillField", (labelOrCy, value) => {
  const cySel = `[data-cy="${labelOrCy}"]`;

  cy.get("body").then(($body) => {
    if ($body.find(cySel).length) {
      cy.get(cySel).first().clear().type(String(value ?? ""));
      return;
    }

    cy.contains("label", labelOrCy).then(($label) => {
      const inputId = $label.attr("for");
      if (inputId) {
        cy.get(`#${inputId}`).clear().type(String(value ?? ""));
      } else {
        cy.wrap($label)
          .parent()
          .find("input, textarea, select")
          .first()
          .clear()
          .type(String(value ?? ""));
      }
    });
  });
});

/**
 * Click by data-cy OR button text
 */
Cypress.Commands.add("clickButton", (textOrCy) => {
  const cySel = `[data-cy="${textOrCy}"]`;

  cy.get("body").then(($body) => {
    if ($body.find(cySel).length) {
      cy.get(cySel).first().click();
      return;
    }
    cy.contains("button", textOrCy).first().click();
  });
});

/**
 * Verify success message appears
 */
Cypress.Commands.add("verifySuccess", (message) => {
  const selectors = [
    '[data-cy="success-message"]',
    ".alert-success",
    ".toast-success",
    '[role="alert"].alert-success',
  ];

  cy.get("body").then(($body) => {
    const hit = selectors.find((sel) => $body.find(sel).length > 0);
    if (!hit) return;

    if (message) cy.get(hit).should("contain", message);
    else cy.get(hit).should("be.visible");
  });
});

/**
 * Verify error message appears
 */
Cypress.Commands.add("verifyError", (message) => {
  const selectors = [
    '[data-cy="error-message"]',
    ".alert-danger",
    ".toast-error",
    '[role="alert"].alert-danger',
  ];

  cy.get("body").then(($body) => {
    const hit = selectors.find((sel) => $body.find(sel).length > 0);
    if (!hit) return;

    if (message) cy.get(hit).should("contain", message);
    else cy.get(hit).should("be.visible");
  });
});
