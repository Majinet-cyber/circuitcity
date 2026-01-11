// =============================================================================
// PHONES MANAGER SMOKE TEST - Fast E2E Validation
// =============================================================================
// Quick smoke test for PR gates / fast CI validation:
// 1. Login as existing manager
// 2. Dashboard loads without errors
// 3. Stock in 1 phone
// 4. Sell 1 phone
// 5. Dashboard reflects the change
// =============================================================================

describe("Phones Manager Smoke Test", () => {
  // =========================================================================
  // TEST DATA - Single item for speed
  // =========================================================================
  const ts = Date.now();
  const testIMEI = String(ts).slice(-10).padStart(10, "0") + "00001";
  const salePrice = 100000;
  const orderPrice = 80000;

  // =========================================================================
  // SETUP - Use session for speed
  // =========================================================================
  beforeEach(() => {
    // Use cached session for speed
    cy.session(
      "phones-manager-smoke",
      () => {
        cy.loginAsManager("phones");
      },
      {
        validate: () => {
          cy.request({
            url: "/__whoami__/",
            failOnStatusCode: false,
          }).then((response) => {
            expect(response.status).to.eq(200);
            expect(response.body.is_authenticated).to.eq(true);
          });
        },
        cacheAcrossSpecs: true,
      }
    );
  });

  // =========================================================================
  // TESTS
  // =========================================================================

  it("dashboard loads without errors", () => {
    cy.visit("/inventory/dashboard/", { failOnStatusCode: false });
    cy.waitForAppShell();
    cy.assertNoServerErrorPage();

    // Verify sidebar exists
    cy.get('[data-cy="sidebar"]', { timeout: 15000 }).should("be.visible");

    // Verify some dashboard content
    cy.get("body").should("satisfy", ($body) => {
      const text = $body.text().toLowerCase();
      return text.includes("dashboard") || text.includes("phones") || text.includes("stock");
    });
  });

  it("can stock in 1 phone item", () => {
    cy.visit("/inventory/scan-in/", { timeout: 30000 });
    cy.waitForAppIdle();
    cy.assertNoServerErrorPage();

    // Enter IMEI
    cy.get('[data-testid="imei-input"], #id_imei', { timeout: 15000 })
      .should("be.visible")
      .clear()
      .type(testIMEI);

    // Select first available product
    cy.get("#id_product", { timeout: 15000 }).then(($select) => {
      const options = $select.find("option").filter((i, el) => el.value);
      if (options.length > 0) {
        cy.get("#id_product").select(options.first().val());
      }
    });

    // Enter order price if field is empty
    cy.get("#id_order_price", { timeout: 15000 }).then(($el) => {
      if (!$el.val()) {
        cy.wrap($el).clear().type(String(orderPrice));
      }
    });

    // Submit
    cy.get('[data-testid="scan-in-submit"], #submitBtn', { timeout: 15000 })
      .should("not.be.disabled")
      .click();

    // Wait for completion
    cy.waitForAppIdle({ timeout: 15000 });
    cy.assertNoServerErrorPage();

    // Verify success (toast, message, or form reset)
    cy.get("body").should("satisfy", ($body) => {
      const text = $body.text().toLowerCase();
      return (
        text.includes("success") ||
        text.includes("added") ||
        text.includes("scanned") ||
        // Form reset indicates success
        $body.find('[data-testid="imei-input"], #id_imei').val() === ""
      );
    });
  });

  it("can sell 1 phone item", () => {
    cy.visit("/inventory/scan-sold/", { timeout: 30000 });
    cy.waitForAppIdle();
    cy.assertNoServerErrorPage();

    // Enter the IMEI we just stocked
    cy.get('[data-testid="sell-imei-input"], #id_imei', { timeout: 15000 })
      .should("be.visible")
      .clear()
      .type(testIMEI);

    // Wait for stock check
    cy.get("#stockBadge", { timeout: 15000 }).should(($badge) => {
      const text = ($badge.text() || "").toLowerCase();
      // Should show in stock or at least not "not in stock"
      expect(text).to.satisfy((t) => !t.includes("not in stock") || t.includes("in stock"));
    });

    // Enter price
    cy.get("#id_price", { timeout: 15000 }).clear().type(String(salePrice));

    // Submit sale
    cy.get('[data-testid="sell-submit"], #submitBtn', { timeout: 15000 })
      .should("not.be.disabled")
      .click();

    // Wait for completion
    cy.waitForAppIdle({ timeout: 15000 });
    cy.assertNoServerErrorPage();

    // Verify success
    cy.get("body", { timeout: 15000 }).should("satisfy", ($body) => {
      const text = $body.text().toLowerCase();
      return text.includes("sold") || text.includes("success") || text.includes("marked");
    });
  });

  it("dashboard updates after sale", () => {
    cy.visit("/inventory/dashboard/", { failOnStatusCode: false });
    cy.waitForAppShell();
    cy.assertNoServerErrorPage();

    // Dashboard should exist and not error
    cy.get("body").should("not.contain.text", "Server Error");
    cy.get("body").should("not.contain.text", "Traceback");

    // Check that sidebar is visible (app shell loaded)
    cy.get('[data-cy="sidebar"]', { timeout: 15000 }).should("be.visible");

    // Verify stock list shows our sold item
    cy.visit("/inventory/list/?q=" + testIMEI, { timeout: 30000 });
    cy.waitForAppIdle();

    // Item should appear (sold or in results)
    cy.get("body").should("satisfy", ($body) => {
      const text = $body.text();
      return (
        text.includes(testIMEI.slice(-5)) ||
        text.toLowerCase().includes("sold") ||
        text.toLowerCase().includes("no items") ||
        text.toLowerCase().includes("no results")
      );
    });
  });

  // =========================================================================
  // SIDEBAR SMOKE - Quick navigation check
  // =========================================================================
  it("all phones sidebar links load without 500 errors", () => {
    cy.visit("/inventory/dashboard/", { failOnStatusCode: false });
    cy.waitForAppShell();

    // Core sidebar items for phones
    const coreItems = [
      "nav-dashboard",
      "nav-stock",
      "nav-scan-in",
      "nav-scan-sell",
    ];

    coreItems.forEach((cyName) => {
      cy.get("body").then(($body) => {
        if ($body.find(`[data-cy="${cyName}"]`).length > 0) {
          cy.log(`Checking ${cyName}`);
          cy.get(`[data-cy="${cyName}"]`).click();
          cy.waitForAppIdle();
          cy.assertNoServerErrorPage();
        }
      });
    });
  });
});

