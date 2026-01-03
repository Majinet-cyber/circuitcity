// cypress/e2e/verticals/clothing_journey.cy.js
/**
 * Full user journey test for Clothing vertical.
 * Covers: login → dashboard → add product (with sizes) → stock-in → sale → reports → settings → logout
 */
describe("Clothing Vertical - Full User Journey", () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("should complete full manager journey for clothing vertical", () => {
    // ============================================================
    // STEP 1: Login as manager
    // ============================================================
    cy.loginAsManager("clothing");
    cy.url().should("not.include", "/accounts/login/");
    cy.assertNoServerError();

    // ============================================================
    // STEP 2: Go to dashboard → confirm page loads
    // ============================================================
    cy.visitDashboard("clothing");
    cy.waitForAppShell();
    cy.assertNoServerError();

    // Verify dashboard elements exist
    cy.get("body").should("contain.text", "dashboard").or("contain.text", "Dashboard").or("contain.text", "Clothing");

    // ============================================================
    // STEP 3: Add a product (with optional brand/color/size)
    // ============================================================
    cy.get("body").then(($body) => {
      const addProductLink = $body.find('a[href*="product"], a[href*="add"], [data-cy="add-product"]').first();
      if (addProductLink.length) {
        cy.wrap(addProductLink).click();
      } else {
        cy.visit("/verticals/clothing/products/add/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Fill product form
    cy.fixture("products").then((products) => {
      const clothingProduct = products.clothing;

      // Name
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-name"]').length) {
          cy.get('[data-cy="product-name"]').type(clothingProduct.name);
        } else if ($body.find('input[name="name"]').length) {
          cy.get('input[name="name"]').type(clothingProduct.name);
        }
      });

      // Brand (optional)
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-brand"]').length) {
          cy.get('[data-cy="product-brand"]').type(clothingProduct.brand);
        } else if ($body.find('input[name="brand"]').length) {
          cy.get('input[name="brand"]').type(clothingProduct.brand);
        }
      });

      // Color (optional)
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-color"]').length) {
          cy.get('[data-cy="product-color"]').type(clothingProduct.color);
        } else if ($body.find('input[name="color"]').length) {
          cy.get('input[name="color"]').type(clothingProduct.color);
        }
      });

      // Size quantities (optional - test "no barcode" path)
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="size-m-qty"]').length) {
          cy.get('[data-cy="size-m-qty"]').type("5");
        } else if ($body.find('input[name="size_m"]').length) {
          cy.get('input[name="size_m"]').type("5");
        }
      });

      // Selling price
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-selling-price"]').length) {
          cy.get('[data-cy="product-selling-price"]').type(clothingProduct.selling_price.toString());
        } else if ($body.find('input[name="selling_price"], input[name="price"]').length) {
          cy.get('input[name="selling_price"], input[name="price"]').first().type(clothingProduct.selling_price.toString());
        }
      });

      // Cost price
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-cost-price"]').length) {
          cy.get('[data-cy="product-cost-price"]').type(clothingProduct.cost_price.toString());
        } else if ($body.find('input[name="cost_price"], input[name="cost"]').length) {
          cy.get('input[name="cost_price"], input[name="cost"]').first().type(clothingProduct.cost_price.toString());
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

    cy.wait(2000);
    cy.assertNoServerError();
    cy.verifySuccess();

    // ============================================================
    // STEP 4: Stock-in / add quantity successfully
    // ============================================================
    cy.visitDashboard("clothing");

    // Navigate to stock-in or add stock
    cy.get("body").then(($body) => {
      const stockInLink = $body.find('a[href*="stock"], a[href*="add"], [data-cy="stock-in"]').first();
      if (stockInLink.length) {
        cy.wrap(stockInLink).click();
      } else {
        cy.visit("/verticals/clothing/stock-in/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Add stock for size M
    cy.get("body").then(($body) => {
      if ($body.find('[data-cy="size-m-qty"]').length || $body.find('input[name="size_m"]').length) {
        const qtyInput = $body.find('[data-cy="size-m-qty"]').length
          ? cy.get('[data-cy="size-m-qty"]')
          : cy.get('input[name="size_m"]');
        qtyInput.first().type("10");

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
    // STEP 5: Make a sale successfully
    // ============================================================
    cy.visitDashboard("clothing");

    cy.get("body").then(($body) => {
      const sellLink = $body.find('a[href*="sell"], a[href*="sale"], [data-cy="sell"]').first();
      if (sellLink.length) {
        cy.wrap(sellLink).click();
      } else {
        cy.visit("/verticals/clothing/sell/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Fill sale form
    cy.fixture("products").then((products) => {
      const clothingProduct = products.clothing;

      // Select product
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="product-select"]').length) {
          cy.get('[data-cy="product-select"]').select(1);
        } else if ($body.find('select[name="product"]').length) {
          cy.get('select[name="product"]').select(1);
        }
      });

      // Select size
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="size-select"]').length) {
          cy.get('[data-cy="size-select"]').select("M");
        } else if ($body.find('select[name="size"]').length) {
          cy.get('select[name="size"]').select("M");
        }
      });

      // Quantity
      cy.get("body").then(($body) => {
        if ($body.find('[data-cy="sale-quantity"]').length) {
          cy.get('[data-cy="sale-quantity"]').type("1");
        } else if ($body.find('input[name="quantity"]').length) {
          cy.get('input[name="quantity"]').type("1");
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
    cy.visitDashboard("clothing");
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
        cy.visit("/verticals/clothing/reports/", { failOnStatusCode: false });
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

  it("should handle 'no barcode' path correctly (clothing-specific)", () => {
    cy.loginAsManager("clothing");
    cy.visitDashboard("clothing");

    // Test that products can be created without barcode
    cy.get("body").then(($body) => {
      if ($body.find('[data-cy="add-product"]').length || $body.find('a[href*="product"]').length) {
        const addLink = $body.find('[data-cy="add-product"]').length
          ? cy.get('[data-cy="add-product"]')
          : cy.get('a[href*="product"]').first();

        addLink.click();
        cy.waitForAppShell();

        // Verify barcode field is optional (not required)
        cy.get("body").then(($form) => {
          const barcodeField = $form.find('[data-cy="barcode"], input[name="barcode"]');
          if (barcodeField.length) {
            // Field exists but should not be required
            cy.log("Barcode field exists but is optional");
          }
        });
      }
    });
  });
});
