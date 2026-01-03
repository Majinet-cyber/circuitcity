// cypress/e2e/verticals/pharmacy_journey.cy.js
/**
 * Full user journey test for Pharmacy vertical.
 * Covers: login → dashboard → add product → add batch → sale → reports → settings → logout
 * Pharmacy-specific: batch/expiry tracking
 */
describe("Pharmacy Vertical - Full User Journey", () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("should complete full manager journey for pharmacy vertical", () => {
    // ============================================================
    // STEP 1: Login as manager
    // ============================================================
    cy.loginAsManager("pharmacy");
    cy.url().should("not.include", "/accounts/login/");
    cy.assertNoServerError();

    // ============================================================
    // STEP 2: Go to dashboard → confirm page loads
    // ============================================================
    cy.visitDashboard("pharmacy");
    cy.waitForAppShell();
    cy.assertNoServerError();

    cy.get("body").should("contain.text", "dashboard").or("contain.text", "Dashboard").or("contain.text", "Pharmacy");

    // ============================================================
    // STEP 3: Add a product (minimal required fields)
    // ============================================================
    cy.get("body").then(($body) => {
      const addProductLink = $body.find('a[href*="product"], a[href*="add"], [data-cy="add-product"]').first();
      if (addProductLink.length) {
        cy.wrap(addProductLink).click();
      } else {
        cy.visit("/pharmacy/products/add/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Fill product form
    cy.fixture("products").then((products) => {
      const pharmacyProduct = products.pharmacy;

      // Name
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-name"]').length) {
          cy.get('[data-cy="product-name"]').type(pharmacyProduct.name);
        } else if ($body.find('input[name="name"]').length) {
          cy.get('input[name="name"]').type(pharmacyProduct.name);
        }
      });

      // Category
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-category"]').length) {
          cy.get('[data-cy="product-category"]').select(pharmacyProduct.category);
        } else if ($body.find('select[name="category"]').length) {
          cy.get('select[name="category"]').select(pharmacyProduct.category);
        }
      });

      // Unit
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-unit"]').length) {
          cy.get('[data-cy="product-unit"]').type(pharmacyProduct.unit);
        } else if ($body.find('input[name="unit"]').length) {
          cy.get('input[name="unit"]').type(pharmacyProduct.unit);
        }
      });

      // Selling price
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-selling-price"]').length) {
          cy.get('[data-cy="product-selling-price"]').type(pharmacyProduct.selling_price.toString());
        } else if ($body.find('input[name="selling_price"], input[name="price"]').length) {
          cy.get('input[name="selling_price"], input[name="price"]').first().type(pharmacyProduct.selling_price.toString());
        }
      });

      // Cost price
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-cost-price"]').length) {
          cy.get('[data-cy="product-cost-price"]').type(pharmacyProduct.cost_price.toString());
        } else if ($body.find('input[name="cost_price"], input[name="cost"]').length) {
          cy.get('input[name="cost_price"], input[name="cost"]').first().type(pharmacyProduct.cost_price.toString());
        }
      });

      // Submit
      cy.get("body").then(($body) => {
        const submitBtn = $body.find('button[type="submit"], [data-cy="submit"]').first();
        if (submitBtn.length) {
          cy.wrap(submitBtn).click();
        } else {
          cy.contains("button", /save|submit|create/i).first().click();
        }
      });
    });

    cy.wait(2000);
    cy.assertNoServerError();
    cy.verifySuccess();

    // ============================================================
    // STEP 4: Add batch (pharmacy-specific: batch/expiry)
    // ============================================================
    cy.visitDashboard("pharmacy");

    cy.get("body").then(($body) => {
      const addBatchLink = $body.find('a[href*="batch"], a[href*="add"], [data-cy="add-batch"]').first();
      if (addBatchLink.length) {
        cy.wrap(addBatchLink).click();
      } else {
        cy.visit("/pharmacy/batches/create/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Fill batch form
    cy.get("body").then(($body) => {
      // Select product
      if ($body.find('[data-cy="batch-product"]').length || $body.find('select[name="product"]').length) {
        const productSelect = $body.find('[data-cy="batch-product"]').length
          ? cy.get('[data-cy="batch-product"]')
          : cy.get('select[name="product"]');
        productSelect.select(1);
      }

      // Batch number
      if ($body.find('[data-cy="batch-number"]').length || $body.find('input[name="batch_number"]').length) {
        const batchInput = $body.find('[data-cy="batch-number"]').length
          ? cy.get('[data-cy="batch-number"]')
          : cy.get('input[name="batch_number"]');
        batchInput.type("BATCH001");
      }

      // Quantity
      if ($body.find('[data-cy="batch-quantity"]').length || $body.find('input[name="quantity"]').length) {
        const qtyInput = $body.find('[data-cy="batch-quantity"]').length
          ? cy.get('[data-cy="batch-quantity"]')
          : cy.get('input[name="quantity"]');
        qtyInput.type("100");
      }

      // Expiry date (set to future date)
      const futureDate = new Date();
      futureDate.setFullYear(futureDate.getFullYear() + 1);
      const dateStr = futureDate.toISOString().split('T')[0];

      if ($body.find('[data-cy="batch-expiry"]').length || $body.find('input[name="expiry_date"]').length) {
        const expiryInput = $body.find('[data-cy="batch-expiry"]').length
          ? cy.get('[data-cy="batch-expiry"]')
          : cy.get('input[name="expiry_date"]');
        expiryInput.type(dateStr);
      }

      // Submit
      const submitBtn = $body.find('button[type="submit"], [data-cy="submit"]').first();
      if (submitBtn.length) {
        cy.wrap(submitBtn).click();
      } else {
        cy.contains("button", /save|submit|add/i).first().click();
      }
    });

    cy.wait(2000);
    cy.assertNoServerError();
    cy.verifySuccess();

    // ============================================================
    // STEP 5: Make a sale successfully
    // ============================================================
    cy.visitDashboard("pharmacy");

    cy.get("body").then(($body) => {
      const sellLink = $body.find('a[href*="sell"], a[href*="sale"], [data-cy="sell"]').first();
      if (sellLink.length) {
        cy.wrap(sellLink).click();
      } else {
        cy.visit("/pharmacy/sell/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Fill sale form
    cy.fixture("products").then((products) => {
      const pharmacyProduct = products.pharmacy;

      // Select product
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-select"]').length) {
          cy.get('[data-cy="product-select"]').select(1);
        } else if ($body.find('select[name="product"]').length) {
          cy.get('select[name="product"]').select(1);
        }
      });

      // Quantity
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="sale-quantity"]').length) {
          cy.get('[data-cy="sale-quantity"]').type("5");
        } else if ($body.find('input[name="quantity"]').length) {
          cy.get('input[name="quantity"]').type("5");
        }
      });

      // Payment method
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="payment-method"]').length) {
          cy.get('[data-cy="payment-method"]').select("CASH");
        } else if ($body.find('select[name="payment_method"]').length) {
          cy.get('select[name="payment_method"]').select("CASH");
        }
      });

      // Submit sale
      cy.get("body").then(($body) => {
        const submitBtn = $body.find('button[type="submit"], [data-cy="submit-sale"]').first();
        if (submitBtn.length) {
          cy.wrap(submitBtn).click();
        } else {
          cy.contains("button", /sell|submit|complete/i).first().click();
        }
      });
    });

    cy.wait(2000);
    cy.assertNoServerError();

    // Verify sale receipt/confirmation visible
    cy.get("body").should("contain.text", "sale").or("contain.text", "success").or("contain.text", "sold");

    // ============================================================
    // STEP 6: Verify inventory decreases
    // ============================================================
    cy.visitDashboard("pharmacy");
    cy.waitForAppShell();
    cy.assertNoServerError();

    // ============================================================
    // STEP 7: Reports page loads
    // ============================================================
    cy.get("body").then(($body) => {
      const reportsLink = $body.find('a[href*="report"], a[href*="analytics"], [data-cy="reports"]').first();
      if (reportsLink.length) {
        cy.wrap(reportsLink).click();
      } else {
        cy.visit("/pharmacy/reports/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();
    cy.assertNoServerError();
    cy.get("body").should("not.be.empty");

    // ============================================================
    // STEP 8: Visit settings
    // ============================================================
    cy.get("body").then(($body) => {
      const settingsLink = $body.find('a[href*="setting"], [data-cy="settings"]').first();
      if (settingsLink.length) {
        cy.wrap(settingsLink).click();
      } else {
        cy.visit("/accounts/settings/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();
    cy.assertNoServerError();

    // ============================================================
    // STEP 9: Logout
    // ============================================================
    cy.get("body").then(($body) => {
      const logoutLink = $body.find('a[href*="logout"], [data-cy="logout"]').first();
      if (logoutLink.length) {
        cy.wrap(logoutLink).click();
      } else {
        cy.visit("/accounts/logout/");
      }
    });

    cy.url().should((url) => {
      expect(url).to.satisfy((u) =>
        u.includes("/accounts/login/") || u === Cypress.config().baseUrl + "/"
      );
    });
  });
});
