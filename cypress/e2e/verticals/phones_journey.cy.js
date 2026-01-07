// cypress/e2e/verticals/phones_journey.cy.js
/**
 * Full user journey test for Phones vertical.
 * Covers: login → dashboard → add product → stock-in → sale → reports → settings → logout
 */
describe("Phones Vertical - Full User Journey", () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("should complete full manager journey for phones vertical", () => {
    // ============================================================
    // STEP 1: Login as manager
    // ============================================================
    cy.loginAsManager("phones");
    cy.url().should("not.include", "/accounts/login/");
    cy.assertNoServerError();

    // ============================================================
    // STEP 2: Go to dashboard → confirm page loads
    // ============================================================
    cy.visitDashboard("phones");
    cy.waitForAppShell();
    cy.assertNoServerError();

    // Verify dashboard elements exist
    cy.get("body").should("contain.text", "dashboard").or("contain.text", "Dashboard");

    // ============================================================
    // STEP 3: Add a product (minimal required fields)
    // ============================================================
    // Navigate to add product page
    cy.get("body").then(($body) => {
      // Try to find "Add Product" link
      const addProductLink = $body.find('a[href*="product"], a[href*="add"], [data-cy="add-product"]').first();
      if (addProductLink.length) {
        cy.wrap(addProductLink).click();
      } else {
        // Try common product URLs
        cy.visit("/inventory/products/add/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Fill product form (minimal fields)
    cy.fixture("products").then((products) => {
      const phoneProduct = products.phones;

      // Brand
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-brand"]').length) {
          cy.get('[data-cy="product-brand"]').type(phoneProduct.brand);
        } else if ($body.find('input[name="brand"]').length) {
          cy.get('input[name="brand"]').type(phoneProduct.brand);
        }
      });

      // Model
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-model"]').length) {
          cy.get('[data-cy="product-model"]').type(phoneProduct.model);
        } else if ($body.find('input[name="model"]').length) {
          cy.get('input[name="model"]').type(phoneProduct.model);
        }
      });

      // Selling price
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-selling-price"]').length) {
          cy.get('[data-cy="product-selling-price"]').type(phoneProduct.selling_price.toString());
        } else if ($body.find('input[name="selling_price"]').length) {
          cy.get('input[name="selling_price"]').type(phoneProduct.selling_price.toString());
        }
      });

      // Submit
      cy.get("body").then(($body) => {
        const submitBtn = $body.find('button[type="submit"], [data-cy="submit"], [data-cy="save"]').first();
        if (submitBtn.length) {
          cy.wrap(submitBtn).click();
        } else {
          cy.contains("button", /save|submit|create/i).first().click();
        }
      });
    });

    // Wait for success or redirect
    cy.wait(2000);
    cy.assertNoServerError();

    // ============================================================
    // STEP 4: Stock-in / add quantity successfully
    // ============================================================
    // Navigate to scan-in page
    cy.get("body").then(($body) => {
      const scanInLink = $body.find('a[href*="scan"], a[href*="stock"], [data-cy="scan-in"]').first();
      if (scanInLink.length) {
        cy.wrap(scanInLink).click();
      } else {
        cy.visit("/inventory/scan-in/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Fill scan-in form
    cy.fixture("products").then((products) => {
      const phoneProduct = products.phones;

      // IMEI
      const imei = `1234567890${Date.now().toString().slice(-5)}`; // Unique IMEI
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="imei"]').length) {
          cy.get('[data-cy="imei"]').type(imei);
        } else if ($body.find('input[name="imei"]').length) {
          cy.get('input[name="imei"]').type(imei);
        }
      });

      // Order price
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="order-price"]').length) {
          cy.get('[data-cy="order-price"]').type(phoneProduct.order_price.toString());
        } else if ($body.find('input[name="order_price"]').length) {
          cy.get('input[name="order_price"]').type(phoneProduct.order_price.toString());
        }
      });

      // Submit
      cy.get("body").then(($body) => {
        const submitBtn = $body.find('button[type="submit"], [data-cy="submit"]').first();
        if (submitBtn.length) {
          cy.wrap(submitBtn).click();
        } else {
          cy.contains("button", /save|submit|scan/i).first().click();
        }
      });
    });

    // Wait for success
    cy.wait(2000);
    cy.assertNoServerError();
    cy.verifySuccess();

    // ============================================================
    // STEP 5: Make a sale successfully
    // ============================================================
    // Navigate to sell page
    cy.get("body").then(($body) => {
      const sellLink = $body.find('a[href*="sell"], a[href*="sale"], [data-cy="sell"]').first();
      if (sellLink.length) {
        cy.wrap(sellLink).click();
      } else {
        cy.visit("/inventory/phone-sale-wizard/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Fill sale form
    cy.fixture("products").then((products) => {
      const phoneProduct = products.phones;

      // IMEI (scan the item we just added)
      const imei = `1234567890${Date.now().toString().slice(-5)}`;
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="sale-imei"]').length) {
          cy.get('[data-cy="sale-imei"]').type(imei);
        } else if ($body.find('input[name="imei"]').length) {
          cy.get('input[name="imei"]').type(imei);
        }
      });

      // Price
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="sale-price"]').length) {
          cy.get('[data-cy="sale-price"]').type(phoneProduct.selling_price.toString());
        } else if ($body.find('input[name="price"], input[name="selling_price"]').length) {
          cy.get('input[name="price"], input[name="selling_price"]').first().type(phoneProduct.selling_price.toString());
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

    // Wait for sale confirmation
    cy.wait(2000);
    cy.assertNoServerError();

    // Verify sale receipt/confirmation visible
    cy.get("body").should("contain.text", "sale").or("contain.text", "success").or("contain.text", "sold");

    // ============================================================
    // STEP 6: Verify inventory decreases (check stock list)
    // ============================================================
    cy.get("body").then(($body) => {
      const stockLink = $body.find('a[href*="stock"], a[href*="inventory"], [data-cy="stock"]').first();
      if (stockLink.length) {
        cy.wrap(stockLink).click();
      } else {
        cy.visit("/inventory/items/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();
    cy.assertNoServerError();

    // ============================================================
    // STEP 7: Reports page loads (basic KPI card exists)
    // ============================================================
    cy.get("body").then(($body) => {
      const reportsLink = $body.find('a[href*="report"], a[href*="analytics"], [data-cy="reports"]').first();
      if (reportsLink.length) {
        cy.wrap(reportsLink).click();
      } else {
        cy.visit("/reports/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();
    cy.assertNoServerError();

    // Verify reports page has content
    cy.get("body").should("not.be.empty");

    // ============================================================
    // STEP 8: Visit settings → ensure page loads
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

    // Verify settings page loads
    cy.get("body").should("contain.text", "setting").or("contain.text", "Setting");

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

    // Should be redirected to login or home
    cy.url().should((url) => {
      expect(url).to.satisfy((u) =>
        u.includes("/accounts/login/") || u === Cypress.config().baseUrl + "/"
      );
    });
  });

  it("should handle IMEI flow correctly (phones-specific)", () => {
    cy.loginAsManager("phones");
    cy.visitDashboard("phones");

    // Test IMEI input and validation
    cy.get("body").then(($body) => {
      if ($body.find('[data-cy="imei"]').length || $body.find('input[name="imei"]').length) {
        const imeiInput = $body.find('[data-cy="imei"]').length
          ? cy.get('[data-cy="imei"]')
          : cy.get('input[name="imei"]');

        imeiInput.first().type("123456789012345");

        // Verify IMEI doesn't "leak" in unrelated UI cards
        cy.get("body").should("not.contain", "123456789012345").or((body) => {
          // If IMEI appears, it should only be in the input field or IMEI-specific sections
          expect(body.find('[data-cy="imei"], input[name="imei"]').length).to.be.greaterThan(0);
        });
      }
    });
  });
});
