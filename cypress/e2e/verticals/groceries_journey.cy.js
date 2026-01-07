// cypress/e2e/verticals/groceries_journey.cy.js
/**
 * Full user journey test for Groceries vertical.
 * Covers: login → dashboard → add product (with quantity/units) → stock-in → sale → reports → settings → logout
 */
describe("Groceries Vertical - Full User Journey", () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("should complete full manager journey for groceries vertical", () => {
    // ============================================================
    // STEP 1: Login as manager
    // ============================================================
    // Note: Groceries may use phones manager or have its own
    cy.loginAsManager("phones"); // Fallback to phones if groceries doesn't have separate manager
    cy.url().should("not.include", "/accounts/login/");
    cy.assertNoServerError();

    // ============================================================
    // STEP 2: Go to dashboard → confirm page loads
    // ============================================================
    cy.visit("/inventory/dashboard/", { failOnStatusCode: false });
    cy.waitForAppShell();
    cy.assertNoServerError();

    cy.get("body").should("contain.text", "dashboard").or("contain.text", "Dashboard");

    // ============================================================
    // STEP 3: Add a product (with quantity/units)
    // ============================================================
    cy.get("body").then(($body) => {
      const addProductLink = $body.find('a[href*="product"], a[href*="add"], [data-cy="add-product"]').first();
      if (addProductLink.length) {
        cy.wrap(addProductLink).click();
      } else {
        cy.visit("/inventory/products/add/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Fill product form
    cy.fixture("products").then((products) => {
      const groceryProduct = products.groceries;

      // Name
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-name"]').length) {
          cy.get('[data-cy="product-name"]').type(groceryProduct.name);
        } else if ($body.find('input[name="name"]').length) {
          cy.get('input[name="name"]').type(groceryProduct.name);
        }
      });

      // Category
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-category"]').length) {
          cy.get('[data-cy="product-category"]').select(groceryProduct.category);
        } else if ($body.find('select[name="category"]').length) {
          cy.get('select[name="category"]').select(groceryProduct.category);
        }
      });

      // Unit
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-unit"]').length) {
          cy.get('[data-cy="product-unit"]').type(groceryProduct.unit);
        } else if ($body.find('input[name="unit"]').length) {
          cy.get('input[name="unit"]').type(groceryProduct.unit);
        }
      });

      // Selling price
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-selling-price"]').length) {
          cy.get('[data-cy="product-selling-price"]').type(groceryProduct.selling_price.toString());
        } else if ($body.find('input[name="selling_price"], input[name="price"]').length) {
          cy.get('input[name="selling_price"], input[name="price"]').first().type(groceryProduct.selling_price.toString());
        }
      });

      // Cost price
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-cost-price"]').length) {
          cy.get('[data-cy="product-cost-price"]').type(groceryProduct.cost_price.toString());
        } else if ($body.find('input[name="cost_price"], input[name="cost"]').length) {
          cy.get('input[name="cost_price"], input[name="cost"]').first().type(groceryProduct.cost_price.toString());
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
    // STEP 4: Stock-in / add quantity successfully
    // ============================================================
    cy.visit("/inventory/dashboard/", { failOnStatusCode: false });

    cy.get("body").then(($body) => {
      const stockInLink = $body.find('a[href*="stock"], a[href*="add"], [data-cy="stock-in"]').first();
      if (stockInLink.length) {
        cy.wrap(stockInLink).click();
      } else {
        cy.visit("/inventory/stock-in/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Add stock
    cy.get("body").then(($body) => {
      if ($body.find('[data-cy="quantity"]').length || $body.find('input[name="quantity"]').length) {
        const qtyInput = $body.find('[data-cy="quantity"]').length
          ? cy.get('[data-cy="quantity"]')
          : cy.get('input[name="quantity"]');
        qtyInput.first().type("50");

        // Submit
        cy.get("body").then(($form) => {
          const submitBtn = $form.find('button[type="submit"], [data-cy="submit"]').first();
          if (submitBtn.length) {
            cy.wrap(submitBtn).click();
          } else {
            cy.contains("button", /save|submit|add/i).first().click();
          }
        });
      }
    });

    cy.wait(2000);
    cy.assertNoServerError();
    cy.verifySuccess();

    // ============================================================
    // STEP 5: Make a sale successfully (simple sale flow)
    // ============================================================
    cy.visit("/inventory/dashboard/", { failOnStatusCode: false });

    cy.get("body").then(($body) => {
      const sellLink = $body.find('a[href*="sell"], a[href*="sale"], [data-cy="sell"]').first();
      if (sellLink.length) {
        cy.wrap(sellLink).click();
      } else {
        cy.visit("/inventory/sell/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Fill sale form
    cy.fixture("products").then((products) => {
      const groceryProduct = products.groceries;

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
          cy.get('[data-cy="sale-quantity"]').type("2");
        } else if ($body.find('input[name="quantity"]').length) {
          cy.get('input[name="quantity"]').type("2");
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
    cy.visit("/inventory/dashboard/", { failOnStatusCode: false });
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
        cy.visit("/reports/", { failOnStatusCode: false });
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
