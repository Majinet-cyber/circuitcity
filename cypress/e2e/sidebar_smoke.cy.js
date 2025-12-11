// cypress/e2e/sidebar_smoke.cy.js

/**
 * Sidebar smoke test:
 *
 * 1. Logs in as EMPIRE manager
 * 2. Clicks main sidebar nav items (with a short wait between each)
 * 3. Verifies we don't see a "Server Error (500)" page
 * 4. Goes to Costs, adds a small test cost
 * 5. Returns to Inventory Dashboard and hits remaining BUSINESS items
 */

describe("Sidebar smoke: visit all nav items + add cost", () => {
  // Hit these first, before Costs
  const SIDEBAR_BEFORE_COST = [
    "Phone Dashboard",
    "Inventory Dashboard",
    "Stock",
    "Products",
    "Scan IN",
    "Scan & Sell",
    "Time Logs",
    "My Wallet",
    "Admin Wallet",
  ];

  // Hit these after we’ve created a cost (all visible in your sidebar)
  const SIDEBAR_AFTER_COST = [
    "Simulator",
    "Agents",
    "Locations",
    "Data Backup",
    "Choose Plan",
    "Orders",
    "Layby",
  ];

  // Optional items – click them only if they exist
  const OPTIONAL_ITEMS = ["Reports"];

  const CLICK_WAIT_MS = 6000; // slow Cypress down between clicks

  // Be a bit more patient with commands
  Cypress.config("defaultCommandTimeout", 30000);

  /**
   * Helper: click a sidebar item by visible label (required item).
   */
  const clickSidebar = (label) => {
    cy.log(`▶ Sidebar: ${label}`);

    cy.contains(
      "a, button, .nav-link, .sidebar-link, .sidebar-item, li, span",
      label,
      { matchCase: false }
    ).then(($el) => {
      cy.wrap($el).scrollIntoView().click({ force: true });
    });

    cy.wait(CLICK_WAIT_MS);
    cy.get("body").should("not.contain", "Server Error (500)");
  };

  /**
   * Helper: click a sidebar item ONLY if it exists (for optional items
   * like "Reports" that might be hidden / feature-flagged).
   */
  const clickSidebarIfPresent = (label) => {
    cy.log(`▶ Sidebar (optional): ${label}`);

    cy.get("body").then(($body) => {
      const selector =
        "a, button, .nav-link, .sidebar-link, .sidebar-item, li, span";

      const $matches = $body
        .find(selector)
        .filter((i, el) => el.innerText.trim().toLowerCase() === label.toLowerCase());

      if (!$matches.length) {
        cy.log(`ℹ️ Sidebar item "${label}" not present – skipping.`);
        return;
      }

      cy.wrap($matches.first()).scrollIntoView().click({ force: true });
      cy.wait(CLICK_WAIT_MS);
      cy.get("body").should("not.contain", "Server Error (500)");
    });
  };

  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("logs in, hits every sidebar item, adds a cost, then returns to dashboard", () => {
    // ----------------------------------------------------------
    // STEP 1: Login
    // ----------------------------------------------------------
    cy.log("🔐 Logging in as EMPIRE manager");
    cy.loginAsOwner();
    cy.url().should("include", "/inventory");

    // ----------------------------------------------------------
    // STEP 2: Visit each sidebar item BEFORE Costs
    // ----------------------------------------------------------
    cy.wrap(SIDEBAR_BEFORE_COST).each((rawLabel) => {
      const label = String(rawLabel);
      clickSidebar(label);
    });

    // ----------------------------------------------------------
    // STEP 3: Go to Costs and add a smoke-test cost
    // ----------------------------------------------------------
    clickSidebar("Costs");

    const timestamp = Date.now();
    const costName = `sidebar-smoke-test cost ${timestamp}`;
    const amount = "1000";

    cy.log("💰 Adding sidebar smoke-test cost");

    // Fill in cost name
    cy.get('[data-cy="cost-name-input"]')
      .should("be.visible")
      .clear()
      .type(costName);

    // Fill in amount
    cy.get('[data-cy="cost-amount-input"]')
      .should("be.visible")
      .clear()
      .type(amount);

    // Click Add
    cy.get('[data-cy="cost-add-btn"]').click({ force: true });

    cy.wait(CLICK_WAIT_MS);

    // Success banner check (robust)
    cy.contains(
      ".alert, .alert-success, [role='alert'], body",
      "added successfully",
      { matchCase: false }
    ).should("contain", costName);

    // Optional table assertion: only if table exists
    cy.get("body").then(($body) => {
      const table = $body.find('[data-cy="costs-table"]');
      if (table.length) {
        cy.wrap(table).should("contain", costName);
      } else {
        cy.log(
          "ℹ️ [data-cy='costs-table'] not present yet, skipping table assertion"
        );
      }
    });

    // ----------------------------------------------------------
    // STEP 4: Back to Inventory Dashboard (so we SEE the effect)
    // ----------------------------------------------------------
    clickSidebar("Inventory Dashboard");
    cy.url().should("include", "/inventory/dashboard");

    // ----------------------------------------------------------
    // STEP 5: Hit remaining BUSINESS sidebar items
    // ----------------------------------------------------------
    cy.wrap(SIDEBAR_AFTER_COST).each((rawLabel) => {
      const label = String(rawLabel);
      clickSidebar(label);
    });

    // Optional items (e.g. Reports)
    cy.wrap(OPTIONAL_ITEMS).each((rawLabel) => {
      const label = String(rawLabel);
      clickSidebarIfPresent(label);
    });

    // Finish at Inventory Dashboard again
    clickSidebar("Inventory Dashboard");
    cy.url().should("include", "/inventory/dashboard");

    cy.log("✅ Sidebar smoke test complete (no 500s, cost created, nav walked)");
  });
});
