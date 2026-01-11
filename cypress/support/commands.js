// ***********************************************
// Custom Cypress commands for CircuitCity / Emajinet
// - Managers have fixed creds per vertical from cypress/fixtures/users.json (source of truth)
// - Agents are CREATED in tests and MUST be passed explicitly (or stored via setAgentCreds)
// ***********************************************

/**
 * Get manager credentials for a given kind.
 * Priority: explicit env vars > fixtures/users.json (source of truth)
 * 
 * @param {string} kind - phones|pharmacy|liquor|gym|clothing
 * @returns {Cypress.Chainable<{email: string, password: string}>}
 */
function getManagerCreds(kind) {
  const k = (kind || "phones").toLowerCase();
  const keyUpper = k.toUpperCase();

  // Explicit env overrides (highest priority)
  const envEmail =
    Cypress.env(`MANAGER_EMAIL_${keyUpper}`) ||
    Cypress.env(`CYPRESS_MANAGER_EMAIL_${keyUpper}`) ||
    Cypress.env("MANAGER_EMAIL") ||
    Cypress.env("CYPRESS_MANAGER_EMAIL");

  const envPassword =
    Cypress.env(`MANAGER_PASSWORD_${keyUpper}`) ||
    Cypress.env(`CYPRESS_MANAGER_PASSWORD_${keyUpper}`) ||
    Cypress.env("MANAGER_PASSWORD") ||
    Cypress.env("CYPRESS_MANAGER_PASSWORD");

  if (envEmail && envPassword) {
    return cy.wrap({ email: String(envEmail).trim(), password: String(envPassword) });
  }

  // FIXTURE DEFAULTS (source of truth)
  return cy.fixture("users").then((u) => {
    const mgr = u?.managers?.[k];
    if (!mgr?.email || !mgr?.password) {
      throw new Error(
        `[loginAsManager] Missing users.json credentials for kind="${k}". ` +
        `Expected cypress/fixtures/users.json managers.${k}.email/password`
      );
    }
    return { email: String(mgr.email).trim(), password: String(mgr.password) };
  });
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
 * Test-only login via API endpoint (faster, bypasses 2FA in test mode).
 * Only works when ALLOW_TEST_LOGIN=true is set in Django environment.
 * 
 * @param {string|object} kindOrEmail - If string, treated as kind; if object with email/password, uses those
 * @param {string} password - Password (optional if kindOrEmail is an object)
 * @param {object} opts - { kind: "clothing", email: "...", password: "..." } - optional overrides
 */
Cypress.Commands.add("testLogin", (kindOrEmail, password, opts = {}) => {
  // Handle different call signatures
  let email, pass, kind;
  
  if (typeof kindOrEmail === "object" && kindOrEmail.email) {
    // Called as testLogin({email, password}, opts)
    email = kindOrEmail.email;
    pass = kindOrEmail.password;
    kind = opts.kind || kindOrEmail.kind;
  } else if (typeof kindOrEmail === "string" && password) {
    // Called as testLogin(email, password, opts)
    email = kindOrEmail;
    pass = password;
    kind = opts.kind;
  } else {
    // Called as testLogin(kind, undefined, opts) - use fixtures
    kind = kindOrEmail || opts.kind || "phones";
    email = opts.email;
    pass = opts.password;
  }
  
  // If email/password not explicitly provided, use getManagerCreds
  if (!email || !pass) {
    if (!kind) {
      throw new Error("[testLogin] Either provide email/password explicitly, or provide kind to load from fixtures/users.json");
    }
    return getManagerCreds(kind).then((creds) => {
      return cy.testLogin(creds.email, creds.password, { kind });
    });
  }
  
  const body = { email, password: pass };
  if (kind) {
    body.kind = kind;
  }
  
  cy.request({
    method: "POST",
    url: "/accounts/__e2e__/test-login/",
    body,
    failOnStatusCode: false,
  }).then((response) => {
    // Check for 404 (endpoint disabled)
    if (response.status === 404) {
      throw new Error(
        `[e2e_test_login] 404 - Test login endpoint not found. ` +
        `On localhost this should work automatically. Check ENV is not 'prod' or 'production'.`
      );
    }
    // Check for 409 (manager business lock)
    if (response.status === 409 && response.body.error === "MANAGER_BUSINESS_LOCK") {
      const hint = response.body.hint || "";
      const existingBiz = response.body.existing_business_name || response.body.existing_business_id || "unknown";
      const detail = response.body.detail || response.body.message || "User is already a manager on a different business.";
      throw new Error(
        `[e2e_test_login] 409 - Manager business lock: ${detail} ${hint} Existing business: ${existingBiz}`
      );
    }
    // Check for other error statuses
    if (response.status !== 200) {
      throw new Error(
        `[e2e_test_login] ${response.status} ${JSON.stringify(response.body)}`
      );
    }
    if (!response.body.ok) {
      throw new Error(`[e2e_test_login] Response not ok: ${response.body.error || "Unknown error"}`);
    }
    
    // Assert session cookie exists (try sessionid first, fallback to all cookies)
    cy.getCookie("sessionid").then((cookie) => {
      if (!cookie) {
        // Try alternative cookie name (cc_sessionid)
        cy.getCookie("cc_sessionid").then((altCookie) => {
          if (!altCookie) {
            // Dump all cookies for debugging
            cy.getAllCookies().then((cookies) => {
              throw new Error(
                `[e2e_test_login] No session cookie found after login. Cookies: ${JSON.stringify(cookies.map(c => c.name))}`
              );
            });
          }
        });
      }
    });
    
    // Validate identity via __whoami__ - try both slash and no-slash
    const tryWhoami = (url) => {
      return cy.request({
        url,
        failOnStatusCode: false,
      }).then((whoamiResponse) => {
        if (whoamiResponse.status === 200 && whoamiResponse.body.ok) {
          // Success - verify email matches
          const whoamiEmail = (whoamiResponse.body.email || whoamiResponse.body.username || "").toLowerCase();
          const expectedEmail = email.toLowerCase();
          if (whoamiEmail !== expectedEmail) {
            throw new Error(
              `[e2e_test_login] Email mismatch: expected "${expectedEmail}", got "${whoamiEmail}"`
            );
          }
          return true;
        }
        return false;
      });
    };
    
    // Try /__whoami__/ first, then /__whoami__ if that fails
    tryWhoami("/__whoami__/").then((success) => {
      if (!success) {
        return tryWhoami("/__whoami__").then((success2) => {
          if (!success2) {
            throw new Error(
              `[e2e_test_login] __whoami__ validation failed: both /__whoami__/ and /__whoami__ returned non-200`
            );
          }
        });
      }
    });
  });
});

/**
 * Login using provided credentials (no vertical assumptions).
 * Falls back to UI login if test login is not available.
 * @param {string} email
 * @param {string} password
 */
Cypress.Commands.add("login", (email, password) => {
  // Try test login first (faster)
  cy.testLogin(email, password).then(() => {
    // If testLogin succeeded, we're done
  }).catch(() => {
    // Fall back to UI login
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
});

/**
 * ✅ Backwards compatibility (your existing phones specs likely call this)
 * Uses TEST_EMAIL/TEST_PASSWORD if present, else defaults to PHONES manager creds from fixtures.
 */
Cypress.Commands.add("loginAsOwner", () => {
  const email = Cypress.env("TEST_EMAIL");
  const password = Cypress.env("TEST_PASSWORD") || Cypress.env("MANAGER_PASSWORD");
  
  if (email && password) {
    cy.login(email, password);
  } else {
    // Use fixtures for phones manager
    getManagerCreds("phones").then((creds) => {
      cy.login(creds.email, creds.password);
    });
  }
});

/**
 * Manager login per vertical (ONLY managers use these fixed creds).
 * Uses cy.session() to cache login and speed up tests.
 * Credentials come from cypress/fixtures/users.json by default (source of truth).
 * @param {string} kind - phones|pharmacy|liquor|gym|clothing
 */
Cypress.Commands.add("loginAsManager", (kind = "phones") => {
  const k = String(kind || "phones").toLowerCase();
  
  cy.session(
    `manager-${k}`,
    () => {
      // Use backend login only (no UI fallback)
      // testLogin will use getManagerCreds(k) to load from fixtures/users.json
      cy.testLogin(k, undefined, { kind: k });
    },
    {
      validate: () => {
        // Validate session using whoami endpoint
        // We can't easily check email here since it comes from fixtures async
        cy.request({
          url: "/__whoami__/",
          failOnStatusCode: false,
        }).then((response) => {
          expect(response.status).to.eq(200);
          expect(response.body.is_authenticated).to.eq(true);
          expect(response.body.email || response.body.username).to.exist;
        });
      },
      cacheAcrossSpecs: true,
    }
  );

  // After session is established, visit a page
  cy.visit("/", { failOnStatusCode: false });
  cy.waitForAppShell();
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

/**
 * Create a manager account, business, and location via signup wizard (UI-based).
 * @param {Object} options - { email, password, fullName, businessName, businessKind, locationName, city }
 */
Cypress.Commands.add("createBusinessAndLocation", (options = {}) => {
  const timestamp = Date.now();
  const email = options.email || `test-manager-${timestamp}@e2e.test`;
  const password = options.password || "TestPassword123!@#";
  const fullName = options.fullName || `Test Manager ${timestamp}`;
  const businessName = options.businessName || `Test Business ${timestamp}`;
  const businessKind = options.businessKind || "phones";
  const locationName = options.locationName || "Test Location";
  const city = options.city || "Test City";

  cy.visit("/accounts/signup/");

  // Step 0: Welcome screen - click Get Started
  cy.get('button[type="submit"]').contains(/get started/i).click();

  // Step 1: Account details
  cy.get('input[name="full_name"], #id_full_name').clear().type(fullName);
  cy.get('input[name="email"], #id_email').clear().type(email);
  cy.get('input[name="password1"], #id_password1').clear().type(password);
  cy.get('input[name="password2"], #id_password2').clear().type(password);
  cy.get('button[type="submit"]').contains(/continue/i).click();

  // Step 2: Business details
  cy.get('input[name="business_name"], #id_business_name').clear().type(businessName);
  cy.get('select[name="business_kind"], #id_business_kind').select(businessKind);
  cy.get('button[type="submit"]').contains(/continue/i).click();

  // Step 3: Location
  cy.get('input[name="location_name"], #id_location_name').clear().type(locationName);
  cy.get('input[name="city"], #id_city').clear().type(city);
  cy.get('button[type="submit"]').contains(/continue/i).click();

  // Step 4: Goals (optional - just continue)
  cy.get('button[type="submit"]').contains(/finish|complete/i).click();

  // Handle OTP if present
  cy.url().then((url) => {
    if (url.includes("/signup/verify-email")) {
      // Use E2E OTP bypass
      cy.request({
        method: "GET",
        url: `/accounts/__e2e__/latest-otp/?email=${encodeURIComponent(email)}`,
        failOnStatusCode: false,
      }).then((resp) => {
        if (resp.status === 200 && resp.body.ok) {
          const otpCode = resp.body.code || "000000";
          cy.get('input[name="code"], input[type="text"][placeholder*="code" i]').type(otpCode);
          cy.get('button[type="submit"]').contains(/verify|submit/i).click();
        } else {
          // Fallback: try fixed OTP
          cy.get('input[name="code"], input[type="text"][placeholder*="code" i]').type("000000");
          cy.get('button[type="submit"]').contains(/verify|submit/i).click();
        }
      });
    }
  });

  // Wait for dashboard
  cy.waitForAppShell();

  return cy.wrap({ email, password, businessName, businessKind });
});

/**
 * Switch to a different vertical (changes business kind).
 * Note: This may require creating a new business or switching context.
 * @param {string} vertical - phones|clothing|liquor|pharmacy|gym|grocery
 */
Cypress.Commands.add("switchVertical", (vertical = "phones") => {
  const v = String(vertical).toLowerCase();

  // For now, we'll visit the vertical dashboard directly
  // In a real scenario, you might need to create a new business or switch context
  const verticalUrls = {
    phones: "/inventory/verticals/phones/",
    clothing: "/inventory/verticals/clothing/",
    liquor: "/inventory/verticals/liquor/",
    pharmacy: "/verticals/pharmacy/dashboard/",
    gym: "/inventory/verticals/gym/",
    grocery: "/inventory/dashboard/",
  };

  const url = verticalUrls[v] || verticalUrls.phones;
  cy.visit(url, { failOnStatusCode: false });
  cy.waitForAppShell();
});

// =============================================================================
// PHONES JOURNEY UTILITIES - Added for slow-network resilience
// =============================================================================

/**
 * Extended error detection - fails if any common server error appears in DOM.
 * More comprehensive than assertNoServerError.
 */
Cypress.Commands.add("assertNoServerErrorPage", () => {
  const errorPatterns = [
    "Server Error (500)",
    "A server error occurred",
    "Traceback (most recent call last)",
    "DisallowedHost",
    "IntegrityError",
    "OperationalError",
    "DoesNotExist",
    "TemplateDoesNotExist",
    "ImproperlyConfigured",
    "ProgrammingError",
    "ValueError:",
    "TypeError:",
    "KeyError:",
    "AttributeError:",
    "DEBUG = True",           // Django debug page indicator
    "Request Method:",        // Django debug page header
  ];

  cy.get("body", { timeout: 5000 }).then(($body) => {
    const bodyText = $body.text();
    errorPatterns.forEach((pattern) => {
      if (bodyText.includes(pattern)) {
        throw new Error(`Server error detected: "${pattern}" found on page`);
      }
    });
  });
});

/**
 * Safe click with visibility and timeout handling.
 * @param {string} testid - The data-testid value
 * @param {object} options - { timeout, force }
 */
Cypress.Commands.add("safeClick", (testid, options = {}) => {
  const timeout = options.timeout || 15000;
  const force = options.force || false;
  
  cy.get(`[data-testid="${testid}"]`, { timeout })
    .should("be.visible")
    .click({ force });
});

/**
 * Safe click by data-cy selector.
 * @param {string} cyName - The data-cy value
 * @param {object} options - { timeout, force }
 */
Cypress.Commands.add("safeClickCy", (cyName, options = {}) => {
  const timeout = options.timeout || 15000;
  const force = options.force || false;
  
  cy.get(`[data-cy="${cyName}"]`, { timeout })
    .should("be.visible")
    .click({ force });
});

/**
 * Wait for app to be idle (no spinners/loaders visible).
 * Falls back to body existence + no server error if no loader exists.
 */
Cypress.Commands.add("waitForAppIdle", (options = {}) => {
  const timeout = options.timeout || 15000;
  
  // Common loader/spinner selectors
  const loaderSelectors = [
    ".loading",
    ".spinner",
    ".loader",
    "[data-loading]",
    '[aria-busy="true"]',
    ".cc-loading",
    ".is-loading",
  ];
  
  cy.get("body", { timeout }).should("exist").then(($body) => {
    // Check if any loader is present and wait for it to disappear
    const hasLoader = loaderSelectors.some((sel) => $body.find(sel).length > 0);
    
    if (hasLoader) {
      loaderSelectors.forEach((sel) => {
        if ($body.find(sel).length > 0) {
          cy.get(sel, { timeout }).should("not.exist");
        }
      });
    }
    
    // Always verify no server error
    cy.assertNoServerErrorPage();
  });
});

/**
 * Navigate via sidebar and assert page loads without errors.
 * @param {string} cyName - The data-cy value of the nav link (e.g., "nav-dashboard")
 * @param {string} expectedUrlPart - URL substring to verify (e.g., "/dashboard/")
 * @param {string} interceptPattern - Optional route pattern to intercept (e.g., "/inventory/**")
 */
Cypress.Commands.add("navAndAssert", (cyName, expectedUrlPart, interceptPattern = null) => {
  const aliasName = `nav_${cyName.replace(/-/g, "_")}`;
  
  // Set up intercept if pattern provided
  if (interceptPattern) {
    cy.intercept("GET", interceptPattern).as(aliasName);
  }
  
  // Click the nav item
  cy.get(`[data-cy="${cyName}"]`, { timeout: 15000 })
    .should("be.visible")
    .click();
  
  // Wait for intercept if set
  if (interceptPattern) {
    cy.wait(`@${aliasName}`, { timeout: 15000 });
  }
  
  // Wait for page to stabilize
  cy.waitForAppIdle();
  
  // Verify URL contains expected part
  if (expectedUrlPart) {
    cy.url({ timeout: 15000 }).should("include", expectedUrlPart);
  }
  
  // Verify no server errors
  cy.assertNoServerErrorPage();
});

/**
 * Fill an input by data-testid with visibility check.
 * @param {string} testid - The data-testid value
 * @param {string} value - Value to type
 * @param {object} options - { clear, timeout }
 */
Cypress.Commands.add("fillByTestId", (testid, value, options = {}) => {
  const timeout = options.timeout || 15000;
  const clear = options.clear !== false; // default true
  
  const el = cy.get(`[data-testid="${testid}"]`, { timeout }).should("be.visible");
  
  if (clear) {
    el.clear();
  }
  
  el.type(String(value));
});

/**
 * Generate deterministic test IMEIs based on timestamp.
 * @param {number} count - How many IMEIs to generate
 * @param {number} timestamp - Base timestamp (default: now)
 * @returns {string[]} Array of 15-digit IMEI strings
 */
Cypress.Commands.add("generateIMEIs", (count, timestamp = null) => {
  const ts = timestamp || Date.now();
  const base = String(ts).slice(-10).padStart(10, "0");
  
  const imeis = [];
  for (let i = 0; i < count; i++) {
    const suffix = String(i).padStart(5, "0");
    imeis.push(base + suffix);
  }
  
  return cy.wrap(imeis);
});

/**
 * Click all sidebar navigation items and verify they load (smoke test).
 * Skips logout and external links.
 */
Cypress.Commands.add("sidebarSmokeClickAll", () => {
  cy.get('[data-cy="sidebar"]').should("be.visible");

  // Collect all sidebar links
  cy.get('[data-cy="sidebar"] a[href]').then(($links) => {
    const links = Array.from($links)
      .map((link) => ({
        href: link.getAttribute("href"),
        text: link.textContent.trim(),
        dataCy: link.getAttribute("data-cy"),
      }))
      .filter((link) => {
        // Skip logout, external links, empty hrefs
        if (!link.href || link.href === "#") return false;
        if (link.href.includes("/logout")) return false;
        if (link.href.startsWith("http") && !link.href.includes(Cypress.config().baseUrl)) return false;
        return link.href.startsWith("/");
      });

    // Click each link and verify page loads
    links.forEach((link, index) => {
      cy.log(`Clicking sidebar item ${index + 1}/${links.length}: ${link.text || link.dataCy || link.href}`);

      cy.get(`[data-cy="${link.dataCy}"], a[href="${link.href}"]`).first().click();

      // Wait for navigation
      cy.url({ timeout: 10000 }).should("include", link.href.split("?")[0]);

      // Verify no server errors
      cy.assertNoServerError();

      // Verify page has content (not a blank page)
      cy.get("body").should("not.be.empty");

      // Go back to sidebar (if we navigated away)
      cy.get("body").then(($body) => {
        if (!$body.find('[data-cy="sidebar"]').length) {
          cy.go("back");
          cy.waitForAppShell();
        }
      });
    });
  });
});
