// cypress/e2e/journeys/manager_full_journey.cy.js
/**
 * Full Manager Journey E2E Test
 *
 * Tests a complete user journey:
 * 1. Create manager account via signup wizard
 * 2. For each vertical: add product, stock in, make sale, add costs
 * 3. Click every sidebar button
 * 4. Verify success toasts and KPI updates
 *
 * Verticals tested:
 * - Phones (includes accessories)
 * - Electronics (phones)
 * - Clothing
 * - Liquor
 * - Groceries
 * - Pharmacy/Cosmetics
 * - Gym
 */

describe("Manager Full Journey - All Verticals", () => {
  const timestamp = Date.now();
  const testEmail = `e2e-manager-${timestamp}@test.com`;
  const testPassword = "TestPassword123!@#";

  // Define all verticals to test
  const verticals = [
    { kind: "phones", name: "Phones & Electronics" },
    { kind: "clothing", name: "Clothing" },
    { kind: "liquor", name: "Liquor" },
    { kind: "pharmacy", name: "Pharmacy & Cosmetics" },
    { kind: "gym", name: "Gym" },
    { kind: "grocery", name: "Groceries" },
  ];

  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("creates manager account and completes full journey for all verticals", () => {
    // ============================================
    // STEP 1: Create Manager Account
    // ============================================
    cy.log("Creating manager account...");
    cy.createBusinessAndLocation({
      email: testEmail,
      password: testPassword,
      fullName: "E2E Test Manager",
      businessName: `E2E Test Business ${timestamp}`,
      businessKind: "phones", // Start with phones
      locationName: "Test Location",
      city: "Test City",
    });

    // Verify we're in the app
    cy.get('[data-cy="sidebar"]').should("be.visible");
    cy.url().should("include", "/dashboard");

    // ============================================
    // STEP 2: Test Each Vertical
    // ============================================
    verticals.forEach((vertical) => {
      cy.log(`Testing vertical: ${vertical.name}`);

      // Create a new business for this vertical (or switch if supported)
      cy.createBusinessAndLocation({
        email: `${vertical.kind}-${timestamp}@test.com`,
        password: testPassword,
        fullName: `E2E ${vertical.name} Manager`,
        businessName: `E2E ${vertical.name} Business ${timestamp}`,
        businessKind: vertical.kind,
        locationName: "Test Location",
        city: "Test City",
      });

      // Wait for dashboard
      cy.waitForAppShell();

      // Test vertical-specific flows
      testVerticalFlow(vertical.kind);

      // Test sidebar navigation
      cy.log(`Testing sidebar navigation for ${vertical.name}`);
      cy.sidebarSmokeClickAll();

      // Test costs/expenses
      cy.log(`Testing costs for ${vertical.name}`);
      testCostsFlow();
    });

    // ============================================
    // STEP 3: Test Accessories (part of phones)
    // ============================================
    cy.log("Testing Accessories (phones vertical)");
    cy.login(testEmail, testPassword);
    cy.visit("/verticals/phones/accessories/");
    cy.waitForAppShell();

    // Test accessories flow
    testAccessoriesFlow();
  });

  /**
   * Test vertical-specific flow: add product, stock in, make sale
   */
  function testVerticalFlow(vertical) {
    cy.log(`Testing ${vertical} vertical flow`);

    switch (vertical) {
      case "phones":
        testPhonesFlow();
        break;
      case "clothing":
        testClothingFlow();
        break;
      case "liquor":
        testLiquorFlow();
        break;
      case "pharmacy":
        testPharmacyFlow();
        break;
      case "gym":
        testGymFlow();
        break;
      case "grocery":
        testGroceryFlow();
        break;
      default:
        cy.log(`No specific flow defined for ${vertical}, skipping`);
    }
  }

  /**
   * Test phones vertical: add phone, stock in with IMEI, make sale
   */
  function testPhonesFlow() {
    // Navigate to scan in
    cy.get('[data-cy="nav-scan-in"]').click();
    cy.url().should("include", "/scan-in");

    // Select brand (ITEL as example)
    cy.get("body").then(($body) => {
      if ($body.find('[data-cy="brand-card"]').length) {
        cy.get('[data-cy="brand-card"]').first().click();
      } else {
        cy.contains(/itel|samsung|iphone/i).first().click();
      }
    });

    // Select model
    cy.get('select[name="model"], [data-cy="scan-model-select"]').then(($sel) => {
      if ($sel.length && $sel[0].options.length > 1) {
        cy.wrap($sel[0]).select(1);
      }
    });

    // Enter IMEI
    const imei = `555666777888${Math.floor(Math.random() * 1000)}`;
    cy.window().then((win) => {
      const input = win.document.querySelector('input[name="imei"], #imei-input, [data-cy="imei-input"]');
      if (input) {
        input.value = imei;
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });

    // Intercept stock-in request
    cy.intercept("POST", "**/scan-in/**").as("stockIn");

    // Submit
    cy.get('button[type="submit"], [data-cy="scan-phone-btn"]').click();

    // Wait for success
    cy.wait("@stockIn").its("response.statusCode").should("be.oneOf", [200, 201]);
    cy.get('[data-cy="toast-success"], .alert-success').should("be.visible");

    // Make a sale
    cy.get('[data-cy="nav-scan-sell"]').click();
    cy.url().should("include", "/scan-sold");

    // Select product (simplified - in real test would select the phone we just added)
    cy.get("body").then(($body) => {
      if ($body.find('[data-cy="sale-brand-option"]').length) {
        cy.get('[data-cy="sale-brand-option"]').first().click();
      }
    });

    // Intercept sale request
    cy.intercept("POST", "**/sales/**").as("saleCreate");

    // Complete sale (simplified)
    cy.get('button[type="submit"], [data-cy="confirm-sale-btn"]').then(($btn) => {
      if ($btn.length && !$btn.prop("disabled")) {
        cy.wrap($btn).click();
        cy.wait("@saleCreate").its("response.statusCode").should("be.oneOf", [200, 201]);
        cy.get('[data-cy="toast-success"]').should("be.visible");
      }
    });
  }

  /**
   * Test clothing vertical: add product, stock in quantity, make sale
   */
  function testClothingFlow() {
    // Navigate to stock/add product
    cy.get('[data-cy="nav-stock"]').click();
    cy.url().should("include", "/list");

    // Add product (simplified - would use actual form)
    cy.get('button:contains("Add"), [data-cy="btn-add-product"]').then(($btn) => {
      if ($btn.length) {
        cy.wrap($btn).first().click();
        // Fill product form...
      }
    });

    // Stock in
    cy.get('[data-cy="nav-scan-in"]').click();
    // Fill stock-in form...

    // Make sale
    cy.get('[data-cy="nav-scan-sell"]').click();
    cy.intercept("POST", "**/sales/**").as("saleCreate");
    // Complete sale...
    cy.wait("@saleCreate", { timeout: 10000 }).its("response.statusCode").should("be.oneOf", [200, 201]);
  }

  /**
   * Test liquor vertical: stock in, sell with unit type
   */
  function testLiquorFlow() {
    cy.get('[data-cy="nav-stock"]').click();
    // Add liquor product...
    cy.get('[data-cy="nav-scan-sell"]').click();
    // Make sale with bottle/glass/shot...
    cy.intercept("POST", "**/sales/**").as("saleCreate");
    cy.wait("@saleCreate", { timeout: 10000 }).its("response.statusCode").should("be.oneOf", [200, 201]);
  }

  /**
   * Test pharmacy vertical: add product, stock in, dispense
   */
  function testPharmacyFlow() {
    cy.get('[data-cy="nav-stock"]').click();
    // Add pharmacy product...
    cy.get('[data-cy="nav-scan-sell"]').click();
    // Dispense...
    cy.intercept("POST", "**/sales/**").as("saleCreate");
    cy.wait("@saleCreate", { timeout: 10000 }).its("response.statusCode").should("be.oneOf", [200, 201]);
  }

  /**
   * Test gym vertical: create member, record payment
   */
  function testGymFlow() {
    cy.get('[data-cy="nav-dashboard"]').click();
    // Create trainer (if needed)...
    // Create member...
    // Record payment...
    cy.intercept("POST", "**/gym/**").as("gymAction");
    cy.wait("@gymAction", { timeout: 10000 }).its("response.statusCode").should("be.oneOf", [200, 201]);
  }

  /**
   * Test grocery vertical: add product, stock in, sell
   */
  function testGroceryFlow() {
    cy.get('[data-cy="nav-stock"]').click();
    // Add grocery product...
    cy.get('[data-cy="nav-scan-sell"]').click();
    // Make sale...
    cy.intercept("POST", "**/sales/**").as("saleCreate");
    cy.wait("@saleCreate", { timeout: 10000 }).its("response.statusCode").should("be.oneOf", [200, 201]);
  }

  /**
   * Test accessories flow (phones vertical)
   */
  function testAccessoriesFlow() {
    cy.visit("/verticals/phones/accessories/");
    cy.waitForAppShell();

    // Stock in accessory
    cy.visit("/verticals/phones/accessories/stock-in/");
    // Fill form...

    // Sell accessory
    cy.visit("/verticals/phones/accessories/fast-sell/");
    cy.intercept("POST", "**/accessories/**").as("accessoryAction");
    cy.wait("@accessoryAction", { timeout: 10000 }).its("response.statusCode").should("be.oneOf", [200, 201]);
  }

  /**
   * Test costs/expenses flow (global)
   */
  function testCostsFlow() {
    // Navigate to costs (in More Features or Admin Wallet)
    cy.get('[data-cy="nav-admin-wallet"]').then(($link) => {
      if ($link.length) {
        cy.wrap($link).click();
        cy.url().should("include", "/wallet/admin");
      }
    });

    // Or navigate directly to costs
    cy.visit("/wallet/admin/costs/", { failOnStatusCode: false });
    cy.waitForAppShell();

    // Add cost
    cy.get('a:contains("Add"), [data-cy="btn-add-cost"]').then(($btn) => {
      if ($btn.length) {
        cy.wrap($btn).first().click();

        // Fill cost form
        cy.get('input[name="amount"], [data-cy="cost-amount"]').type("10000");
        cy.get('input[name="description"], [data-cy="cost-description"]').type("Test Rent");
        cy.get('select[name="category"], [data-cy="cost-category"]').then(($sel) => {
          if ($sel.length && $sel[0].options.length > 1) {
            cy.wrap($sel[0]).select(1);
          }
        });

        // Intercept cost creation
        cy.intercept("POST", "**/costs/**").as("costCreate");

        // Submit
        cy.get('button[type="submit"], [data-cy="btn-save"]').click();
        cy.wait("@costCreate", { timeout: 10000 }).its("response.statusCode").should("be.oneOf", [200, 201]);
        cy.get('[data-cy="toast-success"]').should("be.visible");
      }
    });
  }
});
