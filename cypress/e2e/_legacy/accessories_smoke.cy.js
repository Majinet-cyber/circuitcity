// cypress/e2e/accessories_smoke.cy.js

/**
 * Accessories smoke test for Phones vertical:
 *
 * 1. Logs in as EMPIRE manager
 * 2. Navigates to Accessories dashboard
 * 3. Navigates to Stock In Accessories
 * 4. Verifies no 500 errors
 * 5. Tests minimal flow (manual inputs, no camera)
 */

describe("Accessories smoke: navigation and minimal flow", () => {
  const CLICK_WAIT_MS = 3000;

  // Be patient with commands
  Cypress.config("defaultCommandTimeout", 30000);

  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("navigates to Accessories dashboard without 500 error", () => {
    cy.log("🔐 Logging in as EMPIRE manager");
    cy.loginAsOwner();

    cy.log("▶ Navigating to Accessories dashboard");

    // Try clicking sidebar link (if visible)
    cy.get("body").then(($body) => {
      const $accessoriesLink = $body.find('[data-testid="nav-phones-accessories"]');
      if ($accessoriesLink.length) {
        cy.wrap($accessoriesLink).scrollIntoView().click({ force: true });
      } else {
        // Fallback: direct URL visit
        cy.visit("/verticals/phones/accessories/");
      }
    });

    cy.wait(CLICK_WAIT_MS);

    // Verify no 500 error
    cy.get("body").should("not.contain", "Server Error (500)");
    cy.get("body").should("not.contain", "NoReverseMatch");

    // Verify page loaded
    cy.contains("Accessories", { matchCase: false, timeout: 10000 }).should("be.visible");
  });

  it("navigates to Stock In Accessories without 500 error", () => {
    cy.log("🔐 Logging in as EMPIRE manager");
    cy.loginAsOwner();

    cy.log("▶ Navigating to Stock In Accessories");

    // Try clicking sidebar link (if visible)
    cy.get("body").then(($body) => {
      const $stockInLink = $body.find('[data-testid="nav-phones-accessories-stockin"]');
      if ($stockInLink.length) {
        cy.wrap($stockInLink).scrollIntoView().click({ force: true });
      } else {
        // Fallback: direct URL visit
        cy.visit("/verticals/phones/accessories/stock-in/");
      }
    });

    cy.wait(CLICK_WAIT_MS);

    // Verify no 500 error
    cy.get("body").should("not.contain", "Server Error (500)");
    cy.get("body").should("not.contain", "NoReverseMatch");

    // Verify page loaded
    cy.contains("Stock In Accessories", { matchCase: false, timeout: 10000 }).should("be.visible");
  });

  it("completes minimal stock-in flow (manual inputs, no camera)", () => {
    cy.log("🔐 Logging in as EMPIRE manager");
    cy.loginAsOwner();

    cy.log("▶ Navigating to Stock In Accessories");
    cy.visit("/verticals/phones/accessories/stock-in/");
    cy.wait(CLICK_WAIT_MS);

    // Step 1: Choose category (click Powerbank card)
    cy.log("Step 1: Choose category");
    cy.contains("Powerbank", { matchCase: false, timeout: 10000 }).click({ force: true });
    cy.wait(2000);

    // Step 2: Create new product (click "Create New Product" button)
    cy.log("Step 2: Create new product");
    cy.contains("Create New Product", { matchCase: false }).click({ force: true });
    cy.wait(1000);

    // Fill in product name
    cy.get("#newProductName").type("Test Powerbank OPB-TEST", { force: true });
    cy.get("#newProductBrand").type("Oraimo", { force: true });
    cy.contains("button", "Continue", { matchCase: false }).click({ force: true });
    cy.wait(2000);

    // Step 3: Barcode option (choose "No Barcode")
    cy.log("Step 3: Skip barcode");
    cy.contains("No Barcode", { matchCase: false }).click({ force: true });
    cy.wait(2000);

    // Step 4: Prices
    cy.log("Step 4: Enter prices");
    cy.get("#orderPrice").clear().type("30000", { force: true });
    cy.get("#sellingPrice").clear().type("38000", { force: true });
    cy.contains("button", "Continue", { matchCase: false }).click({ force: true });
    cy.wait(2000);

    // Step 5: Quantity
    cy.log("Step 5: Enter quantity");
    cy.get("#quantity").clear().type("5", { force: true });
    cy.contains("button", "Save Stock", { matchCase: false }).click({ force: true });
    cy.wait(3000);

    // Verify success message
    cy.contains("Stock Added Successfully", { matchCase: false, timeout: 10000 }).should("be.visible");
    cy.log("✓ Minimal stock-in flow completed successfully");
  });

  it("completes minimal fast sell flow", () => {
    cy.log("🔐 Logging in as EMPIRE manager");
    cy.loginAsOwner();

    // First, ensure we have stock (visit stock-in and add if needed)
    cy.log("▶ Ensuring stock exists");
    cy.visit("/verticals/phones/accessories/stock-in/");
    cy.wait(CLICK_WAIT_MS);

    // Quick stock-in (reuse previous flow)
    cy.contains("Powerbank", { matchCase: false, timeout: 10000 }).click({ force: true });
    cy.wait(1000);

    // Try to select existing product or create new
    cy.get("body").then(($body) => {
      const $productCards = $body.find(".choice-card");
      if ($productCards.length > 0) {
        // Click first product
        cy.wrap($productCards.first()).click({ force: true });
      } else {
        // Create new product
        cy.contains("Create New Product", { matchCase: false }).click({ force: true });
        cy.get("#newProductName").type("Fast Sell Test Powerbank", { force: true });
        cy.contains("button", "Continue", { matchCase: false }).click({ force: true });
        cy.wait(1000);
        cy.contains("No Barcode", { matchCase: false }).click({ force: true });
        cy.wait(1000);
      }
    });

    cy.wait(1000);
    cy.get("#orderPrice").clear().type("25000", { force: true });
    cy.get("#sellingPrice").clear().type("32000", { force: true });
    cy.contains("button", "Continue", { matchCase: false }).click({ force: true });
    cy.wait(1000);
    cy.get("#quantity").clear().type("3", { force: true });
    cy.contains("button", "Save Stock", { matchCase: false }).click({ force: true });
    cy.wait(3000);

    // Now go to fast sell
    cy.log("▶ Navigating to Fast Sell");
    cy.visit("/verticals/phones/accessories/fast-sell/");
    cy.wait(CLICK_WAIT_MS);

    // Search for product
    cy.log("Searching for product");
    cy.get("#scanInput").type("Fast Sell Test", { force: true });
    cy.contains("button", "Search", { matchCase: false }).click({ force: true });
    cy.wait(2000);

    // Verify product card appears
    cy.get("#productCard").should("be.visible");

    // Set quantity and sell
    cy.log("Selling 1 unit");
    cy.get("#sellQuantity").clear().type("1", { force: true });
    cy.contains("button", "Sell Now", { matchCase: false }).click({ force: true });
    cy.wait(3000);

    // Verify success toast or message
    cy.contains("SOLD", { matchCase: false, timeout: 10000 }).should("be.visible");
    cy.log("✓ Minimal fast sell flow completed successfully");
  });
});
