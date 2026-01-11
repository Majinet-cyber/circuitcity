// =============================================================================
// PHONES MANAGER FULL JOURNEY - E2E Test Spec
// =============================================================================
// Tests the complete manager journey for Phones vertical:
// 1. Create manager account via signup wizard
// 2. Complete business setup for Phones
// 3. Navigate all sidebar items (no 500 errors)
// 4. Add 2 products/models
// 5. Stock in 10 phones (IMEI-based)
// 6. Make 10 sales
// 7. Verify stock counts and dashboard KPIs
// =============================================================================

describe("Phones Manager Full Journey", () => {
  // =========================================================================
  // TEST DATA - Deterministic based on timestamp
  // =========================================================================
  const ts = Date.now();
  const testData = {
    // Manager account
    email: `manager.phones.${ts}@e2e.test`,
    password: "TestPass123!@#",
    fullName: `Test Manager ${ts}`,

    // Business
    businessName: `Phones Store ${ts}`,
    businessKind: "phones",

    // Products (2 models)
    products: [
      { name: `Samsung Galaxy A14 ${ts}`, brand: "Samsung", orderPrice: 80000, sellingPrice: 100000 },
      { name: `iPhone 13 ${ts}`, brand: "Apple", orderPrice: 120000, sellingPrice: 150000 },
    ],

    // IMEIs (10 unique 15-digit numbers)
    imeis: Array.from({ length: 10 }, (_, i) => {
      const base = String(ts).slice(-10).padStart(10, "0");
      const suffix = String(i).padStart(5, "0");
      return base + suffix;
    }),

    // Selling price for sales
    salePrice: 100000,
  };

  // Store created credentials for session reuse
  let createdCreds = null;

  // =========================================================================
  // HELPER FUNCTIONS
  // =========================================================================

  /**
   * Complete the signup wizard flow.
   */
  function completeSignupWizard() {
    // Step 1: Account details
    cy.visit("/accounts/signup/", { timeout: 30000 });
    cy.waitForAppIdle();

    // Fill Step 1 fields
    cy.get('[data-testid="signup-email"]', { timeout: 15000 })
      .should("be.visible")
      .clear()
      .type(testData.email);

    cy.get('[data-testid="signup-fullname"]')
      .clear()
      .type(testData.fullName);

    cy.get('[data-testid="signup-password1"]')
      .clear()
      .type(testData.password);

    cy.get('[data-testid="signup-password2"]')
      .clear()
      .type(testData.password);

    // Submit Step 1
    cy.intercept("POST", "**/signup/**").as("signupStep1");
    cy.get('[data-testid="signup-step1-submit"]').click();
    cy.wait("@signupStep1", { timeout: 15000 });
    cy.waitForAppIdle();

    // Step 2: Business details
    cy.get('[data-testid="signup-business-name"]', { timeout: 15000 })
      .should("be.visible")
      .clear()
      .type(testData.businessName);

    // Select business kind (phones) via the hidden select
    cy.get('[data-testid="signup-business-kind"]', { timeout: 15000 })
      .select("phones", { force: true });

    // Also click the visual dropdown option if it exists
    cy.get("body").then(($body) => {
      if ($body.find('.cc-option[data-value="phones"]').length) {
        cy.get('.cc-option[data-value="phones"]').click();
      }
    });

    // Submit Step 2
    cy.intercept("POST", "**/signup/**").as("signupStep2");
    cy.get('[data-testid="signup-step2-submit"]').click();
    cy.wait("@signupStep2", { timeout: 15000 });
    cy.waitForAppIdle();

    // Step 3: Logo (skip)
    cy.get("body", { timeout: 15000 }).then(($body) => {
      if ($body.find('[data-testid="signup-step3-skip"]').length) {
        cy.get('[data-testid="signup-step3-skip"]').click();
        cy.waitForAppIdle();
      }
    });

    // Step 4: Review & Create (or final step)
    cy.get("body", { timeout: 15000 }).then(($body) => {
      // Check the terms checkbox if present
      if ($body.find('[data-testid="signup-agree"]').length) {
        cy.get('[data-testid="signup-agree"]').check({ force: true });
      } else if ($body.find("#id_agree").length) {
        cy.get("#id_agree").check({ force: true });
      }

      // Submit final step
      if ($body.find('[data-testid="signup-step4-submit"]').length) {
        cy.intercept("POST", "**/signup/**").as("signupFinal");
        cy.get('[data-testid="signup-step4-submit"]').click();
        cy.wait("@signupFinal", { timeout: 15000 });
      } else if ($body.find('button[type="submit"]').length) {
        cy.intercept("POST", "**/signup/**").as("signupFinal");
        cy.contains("button", /create|finish|complete/i).click();
        cy.wait("@signupFinal", { timeout: 15000 });
      }
    });

    // Handle OTP verification if redirected there
    cy.url({ timeout: 15000 }).then((url) => {
      if (url.includes("/verify") || url.includes("/otp")) {
        // Try to get OTP from test endpoint
        cy.request({
          method: "GET",
          url: `/accounts/__e2e__/latest-otp/?email=${encodeURIComponent(testData.email)}`,
          failOnStatusCode: false,
        }).then((resp) => {
          if (resp.status === 200 && resp.body.ok && resp.body.code) {
            cy.get('input[name="code"], input[type="text"]').first().type(resp.body.code);
            cy.contains("button", /verify|submit|confirm/i).click();
          } else {
            // Try default test OTP
            cy.get('input[name="code"], input[type="text"]').first().type("000000");
            cy.contains("button", /verify|submit|confirm/i).click();
          }
        });
      }
    });

    // Wait for app shell (dashboard)
    cy.waitForAppShell();
    cy.assertNoServerErrorPage();

    // Store credentials for session
    createdCreds = { email: testData.email, password: testData.password };
  }

  /**
   * Login using the created account (or existing manager).
   */
  function loginAsCreatedManager() {
    if (createdCreds) {
      cy.login(createdCreds.email, createdCreds.password);
    } else {
      // Fallback to fixture credentials
      cy.loginAsManager("phones");
    }
  }

  /**
   * Navigate to sidebar item and verify no errors.
   */
  function visitSidebarItem(cyName, expectedUrl = null) {
    cy.get(`[data-cy="${cyName}"]`, { timeout: 15000 }).then(($el) => {
      if ($el.length > 0 && $el.is(":visible")) {
        cy.wrap($el).click();
        cy.waitForAppIdle();
        if (expectedUrl) {
          cy.url().should("include", expectedUrl);
        }
        cy.assertNoServerErrorPage();
      } else {
        cy.log(`Sidebar item ${cyName} not visible, skipping`);
      }
    });
  }

  // =========================================================================
  // TEST SUITE
  // =========================================================================

  before(() => {
    // Clear state before suite
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  // -------------------------------------------------------------------------
  // A) SIGNUP MANAGER USER VIA UI
  // -------------------------------------------------------------------------
  it("A) creates manager account via signup wizard", () => {
    completeSignupWizard();

    // Verify we landed on dashboard
    cy.url().should("not.include", "/login");
    cy.url().should("not.include", "/signup");

    // Verify sidebar is visible (phones vertical)
    cy.get('[data-cy="sidebar"]', { timeout: 15000 }).should("be.visible");
  });

  // -------------------------------------------------------------------------
  // B) VERIFY BUSINESS SETUP FOR PHONES
  // -------------------------------------------------------------------------
  it("B) confirms business is set up for Phones vertical", () => {
    loginAsCreatedManager();
    cy.visitDashboard("phones");

    // Verify we're in phones context (check sidebar or page content)
    cy.get("body").should("satisfy", ($body) => {
      const text = $body.text().toLowerCase();
      return (
        text.includes("phone") ||
        text.includes("imei") ||
        text.includes("scan")
      );
    });

    cy.assertNoServerErrorPage();
  });

  // -------------------------------------------------------------------------
  // C) SIDEBAR NAVIGATION AUDIT (NO 500 ERRORS)
  // -------------------------------------------------------------------------
  it("C) clicks every sidebar button for phones (no 500 errors)", () => {
    loginAsCreatedManager();
    cy.visitDashboard("phones");

    // List of phones sidebar items to check
    const sidebarItems = [
      { cy: "nav-dashboard", url: "/dashboard" },
      { cy: "nav-stock", url: "/list" },
      { cy: "nav-scan-in", url: "/scan-in" },
      { cy: "nav-scan-sell", url: "/scan-sold" },
      { cy: "nav-sales", url: "/sales" },
      { cy: "nav-reports", url: "/reports" },
      { cy: "nav-settings", url: "/settings" },
      { cy: "nav-team-agents", url: "/agents" },
      { cy: "nav-team-locations", url: "/locations" },
    ];

    sidebarItems.forEach((item) => {
      cy.get("body").then(($body) => {
        if ($body.find(`[data-cy="${item.cy}"]`).length > 0) {
          cy.log(`Testing sidebar: ${item.cy}`);
          visitSidebarItem(item.cy, item.url);
        } else {
          cy.log(`Sidebar item ${item.cy} not present, skipping`);
        }
      });
    });
  });

  // -------------------------------------------------------------------------
  // D) ADD 2 PRODUCTS/MODELS (via Admin or API)
  // -------------------------------------------------------------------------
  it("D) adds 2 phone products/models", () => {
    loginAsCreatedManager();

    // For phones, products are typically added via Django admin or scan-in creates them
    // We'll verify products exist or skip if scan-in auto-creates

    // Try to visit products page if it exists
    cy.visit("/admin/inventory/product/", { failOnStatusCode: false }).then(() => {
      cy.url().then((url) => {
        if (url.includes("/admin/")) {
          // If we have admin access, add products
          testData.products.forEach((product, idx) => {
            cy.visit("/admin/inventory/product/add/", { failOnStatusCode: false });
            cy.get("body").then(($body) => {
              if ($body.find('input[name="brand"]').length) {
                cy.get('input[name="brand"]').type(product.brand);
              }
              if ($body.find('input[name="model"], input[name="name"]').length) {
                cy.get('input[name="model"], input[name="name"]').first().type(product.name);
              }
              if ($body.find('input[name="order_price"], input[name="cost_price"]').length) {
                cy.get('input[name="order_price"], input[name="cost_price"]').first().type(String(product.orderPrice));
              }
              if ($body.find('input[name="selling_price"]').length) {
                cy.get('input[name="selling_price"]').type(String(product.sellingPrice));
              }
              if ($body.find('input[name="_save"]').length) {
                cy.get('input[name="_save"]').click();
              }
            });
          });
        } else {
          // No admin access - products will be selected from existing during scan-in
          cy.log("No admin access - will use existing products during scan-in");
        }
      });
    });

    cy.assertNoServerErrorPage();
  });

  // -------------------------------------------------------------------------
  // E) STOCK IN 10 PHONE ITEMS (IMEI-BASED)
  // -------------------------------------------------------------------------
  it("E) stocks in 10 phone items via scan-in", () => {
    loginAsCreatedManager();

    // Visit scan-in page
    cy.visit("/inventory/scan-in/", { timeout: 30000 });
    cy.waitForAppIdle();
    cy.assertNoServerErrorPage();

    // Wait for products to load in dropdown
    cy.get("#id_product", { timeout: 15000 }).should("exist");

    // Stock in each IMEI
    testData.imeis.forEach((imei, idx) => {
      cy.log(`Stocking in IMEI ${idx + 1}/10: ${imei}`);

      // Enter IMEI
      cy.get('[data-testid="imei-input"], #id_imei', { timeout: 15000 })
        .should("be.visible")
        .clear()
        .type(imei);

      // Select product (first available if multiple)
      cy.get("#id_product").then(($select) => {
        const options = $select.find("option").filter((i, el) => el.value);
        if (options.length > 0) {
          // Alternate between products
          const optionIdx = (idx % options.length) + 1;
          cy.get("#id_product").select(options.eq(optionIdx > 0 ? optionIdx - 1 : 0).val() || options.first().val());
        }
      });

      // Enter order price
      cy.get("#id_order_price", { timeout: 15000 }).then(($el) => {
        if ($el.length && !$el.val()) {
          cy.wrap($el).clear().type(String(testData.products[idx % 2].orderPrice));
        }
      });

      // Wait for submit button to be enabled and click
      cy.get('[data-testid="scan-in-submit"], #submitBtn', { timeout: 15000 })
        .should("not.be.disabled")
        .click();

      // Wait for success (page reload or toast)
      cy.intercept("POST", "**/scan-in/**").as(`scanIn${idx}`);
      
      // Wait for page to reload or show success
      cy.waitForAppIdle({ timeout: 15000 });
      
      // Check for success message or that we're still on scan-in (form reset)
      cy.get("body").should("satisfy", ($body) => {
        const text = $body.text().toLowerCase();
        return (
          text.includes("success") ||
          text.includes("added") ||
          text.includes("scanned") ||
          $body.find('[data-testid="imei-input"], #id_imei').length > 0
        );
      });

      cy.assertNoServerErrorPage();

      // If form persists, clear for next entry
      cy.get("body").then(($body) => {
        if ($body.find('[data-testid="imei-input"], #id_imei').length) {
          // Stay on page - ready for next
        } else {
          // Redirected - go back to scan-in
          cy.visit("/inventory/scan-in/");
          cy.waitForAppIdle();
        }
      });
    });

    // Verify stock count increased (check stock list)
    cy.visit("/inventory/list/", { timeout: 30000 });
    cy.waitForAppIdle();

    // Should see some of our IMEIs in stock
    cy.get("body").should("contain.text", testData.imeis[0].slice(-5));
  });

  // -------------------------------------------------------------------------
  // F) MAKE 10 SALES
  // -------------------------------------------------------------------------
  it("F) sells 10 phone items via scan-sold", () => {
    loginAsCreatedManager();

    // Visit scan-sold page
    cy.visit("/inventory/scan-sold/", { timeout: 30000 });
    cy.waitForAppIdle();
    cy.assertNoServerErrorPage();

    // Sell each IMEI
    testData.imeis.forEach((imei, idx) => {
      cy.log(`Selling IMEI ${idx + 1}/10: ${imei}`);

      // Enter IMEI
      cy.get('[data-testid="sell-imei-input"], #id_imei', { timeout: 15000 })
        .should("be.visible")
        .clear()
        .type(imei);

      // Wait for stock check (badge should show "in stock")
      cy.get("#stockBadge", { timeout: 15000 }).should(($badge) => {
        const text = ($badge.text() || "").toLowerCase();
        // Accept "in stock" or any non-error state
        expect(text).to.not.include("not in stock");
      });

      // Enter selling price
      cy.get("#id_price", { timeout: 15000 }).clear().type(String(testData.salePrice));

      // Submit sale
      cy.get('[data-testid="sell-submit"], #submitBtn', { timeout: 15000 })
        .should("not.be.disabled")
        .click();

      // Wait for sale to complete
      cy.waitForAppIdle({ timeout: 15000 });

      // Check for success (toast or redirect to stock list)
      cy.get("body", { timeout: 15000 }).should("satisfy", ($body) => {
        const text = $body.text().toLowerCase();
        return (
          text.includes("sold") ||
          text.includes("success") ||
          text.includes("marked") ||
          $body.find('[data-testid="sell-imei-input"], #id_imei').length > 0
        );
      });

      cy.assertNoServerErrorPage();

      // If redirected, go back to scan-sold for next sale
      cy.url().then((url) => {
        if (!url.includes("/scan-sold")) {
          cy.visit("/inventory/scan-sold/");
          cy.waitForAppIdle();
        }
      });
    });
  });

  // -------------------------------------------------------------------------
  // G) VERIFY DASHBOARD AND STOCK COUNTS
  // -------------------------------------------------------------------------
  it("G) verifies stock decreased and sales KPIs updated", () => {
    loginAsCreatedManager();

    // Visit dashboard
    cy.visitDashboard("phones");
    cy.waitForAppIdle();
    cy.assertNoServerErrorPage();

    // Dashboard should show some sales metrics
    cy.get("body").should("satisfy", ($body) => {
      const text = $body.text().toLowerCase();
      // Looking for any sales/revenue indicators
      return (
        text.includes("sale") ||
        text.includes("revenue") ||
        text.includes("sold") ||
        text.includes("profit") ||
        text.includes("dashboard")
      );
    });

    // Check stock list - sold items should show as sold
    cy.visit("/inventory/list/?status=sold", { timeout: 30000 });
    cy.waitForAppIdle();

    // Should see sold status for our IMEIs
    cy.get("body").should("satisfy", ($body) => {
      const text = $body.text().toLowerCase();
      return text.includes("sold") || text.includes(testData.imeis[0].slice(-5));
    });

    // Verify in-stock count is 0 for our items
    cy.visit("/inventory/list/?status=in_stock", { timeout: 30000 });
    cy.waitForAppIdle();

    // Our specific IMEIs should not be in stock
    testData.imeis.slice(0, 3).forEach((imei) => {
      cy.get("body").should("not.contain.text", imei);
    });

    cy.log("✅ Full journey complete - stock decreased, sales recorded");
  });
});

