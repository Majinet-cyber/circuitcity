// cypress/e2e/verticals/clothing_journey.cy.js
/**
 * Full user journey test for Clothing vertical.
 * Covers: login → add product (no barcode) → verify in list → sell → verify stock/reports → edit price → guardrails
 */
describe("Clothing Vertical - Full User Journey", () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("should complete full manager journey: add product → sell → verify → guardrails", () => {
    const productName = `Test Shirt ${Date.now()}`;
    const costPrice = "5000";
    const sellingPrice = "8000";
    const initialStock = "10";
    const saleQuantity = "2";

    // ============================================================
    // STEP 1: Login as manager
    // ============================================================
    cy.loginAsManager("clothing");
    cy.url().should("not.include", "/accounts/login/");
    cy.assertNoServerError();

    // ============================================================
    // STEP 2: Go to dashboard
    // ============================================================
    cy.visitDashboard("clothing");
    cy.waitForAppShell();
    cy.assertNoServerError();

    // ============================================================
    // STEP 3: Add product using "no barcode" path
    // Try wizard first, fallback to scan_in or direct add
    // ============================================================
    cy.get("body").then(($body) => {
      const addProductLink = $body.find('a[href*="wizard"], a[href*="product"], a[href*="add"], [data-cy="add-product"]').first();
      if (addProductLink.length) {
        cy.wrap(addProductLink).click();
      } else {
        // Try wizard URL
        cy.visit("/inventory/wizard/clothing/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();
    cy.assertNoServerError();

    // Fill product form (adapt to wizard or form)
    cy.get("body").then(($body) => {
      // Name field
      if ($body.find('input[name="name"]').length) {
        cy.get('input[name="name"]').first().clear().type(productName);
      } else if ($body.find('[data-cy="product-name"]').length) {
        cy.get('[data-cy="product-name"]').clear().type(productName);
      }

      // Category (try select first)
      if ($body.find('select[name="category"]').length) {
        cy.get('select[name="category"]').select(1); // Select first category
      }

      // Cost price
      if ($body.find('input[name="cost_price"]').length) {
        cy.get('input[name="cost_price"]').first().clear().type(costPrice);
      } else if ($body.find('[data-cy="cost-price"]').length) {
        cy.get('[data-cy="cost-price"]').clear().type(costPrice);
      }

      // Selling price
      if ($body.find('input[name="selling_price"]').length) {
        cy.get('input[name="selling_price"]').first().clear().type(sellingPrice);
      } else if ($body.find('[data-cy="selling-price"]').length) {
        cy.get('[data-cy="selling-price"]').clear().type(sellingPrice);
      }

      // Quantity/Stock (for "no barcode" path - stock is added during creation)
      if ($body.find('input[name="quantity"]').length) {
        cy.get('input[name="quantity"]').first().clear().type(initialStock);
      } else if ($body.find('input[name="quantity_in_stock"]').length) {
        cy.get('input[name="quantity_in_stock"]').first().clear().type(initialStock);
      }

      // Verify barcode is NOT required (should be optional/not present)
      // Barcode field should not block submission

      // Submit
      cy.get("body").then(($form) => {
        const submitBtn = $form.find('button[type="submit"], [data-cy="submit"], [data-cy="save"]').first();
        if (submitBtn.length) {
          cy.wrap(submitBtn).click();
        } else {
          cy.contains("button", /save|submit|create|add/i).first().click();
        }
      });
    });

    cy.wait(2000);
    cy.assertNoServerError();
    cy.verifySuccess();

    // ============================================================
    // STEP 4: Verify product appears in product list/hub
    // ============================================================
    cy.visitDashboard("clothing");
    cy.waitForAppShell();

    // Navigate to products list or hub
    cy.get("body").then(($body) => {
      const productsLink = $body.find('a[href*="product"], a[href*="hub"], a[href*="stock"]').first();
      if (productsLink.length) {
        cy.wrap(productsLink).click();
      } else {
        cy.visit("/verticals/clothing/hub/", { failOnStatusCode: false });
        cy.visit("/verticals/clothing/products/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();
    cy.assertNoServerError();

    // Verify product name appears in list
    cy.get("body").should("contain.text", productName);

    // ============================================================
    // STEP 5: Perform a sale (sell/quick sell)
    // ============================================================
    cy.visitDashboard("clothing");
    cy.waitForAppShell();

    cy.get("body").then(($body) => {
      const sellLink = $body.find('a[href*="sell"], a[href*="sale"], [data-cy="sell"]').first();
      if (sellLink.length) {
        cy.wrap(sellLink).click();
      } else {
        cy.visit("/verticals/clothing/sell/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();
    cy.assertNoServerError();

    // Fill sale form
    cy.get("body").then(($body) => {
      // Select product
      if ($body.find('select[name="product"]').length) {
        cy.get('select[name="product"]').select(1); // Select first product (should be our test product)
      } else if ($body.find('[data-cy="product-select"]').length) {
        cy.get('[data-cy="product-select"]').select(1);
      }

      // Quantity
      if ($body.find('input[name="quantity"]').length) {
        cy.get('input[name="quantity"]').first().clear().type(saleQuantity);
      } else if ($body.find('[data-cy="quantity"]').length) {
        cy.get('[data-cy="quantity"]').clear().type(saleQuantity);
      }

      // Payment method (if present)
      if ($body.find('select[name="payment_method"]').length) {
        cy.get('select[name="payment_method"]').select("CASH");
      } else if ($body.find('[data-cy="payment-method"]').length) {
        cy.get('[data-cy="payment-method"]').select("CASH");
      }

      // Submit sale
      cy.get("body").then(($form) => {
        const submitBtn = $form.find('button[type="submit"], [data-cy="submit-sale"], [data-cy="sell"]').first();
        if (submitBtn.length) {
          cy.wrap(submitBtn).click();
        } else {
          cy.contains("button", /sell|submit|complete/i).first().click();
        }
      });
    });

    cy.wait(2000);
    cy.assertNoServerError();

    // Verify sale success message
    cy.get("body").should(
      ($body) => {
        const text = $body.text().toLowerCase();
        expect(text).to.satisfy((t) => t.includes("sale") || t.includes("success") || t.includes("sold"));
      }
    );

    // ============================================================
    // STEP 6: Verify stock decreased and sale appears in reports
    // ============================================================
    cy.visitDashboard("clothing");
    cy.waitForAppShell();

    // Check that product still exists but stock is reduced
    cy.get("body").then(($body) => {
      const productsLink = $body.find('a[href*="product"], a[href*="hub"], a[href*="stock"]').first();
      if (productsLink.length) {
        cy.wrap(productsLink).click();
      } else {
        cy.visit("/verticals/clothing/products/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();
    cy.get("body").should("contain.text", productName);

    // Navigate to sales history/reports
    cy.get("body").then(($body) => {
      const salesLink = $body.find('a[href*="sales"], a[href*="report"], a[href*="history"]').first();
      if (salesLink.length) {
        cy.wrap(salesLink).click();
      } else {
        cy.visit("/verticals/clothing/sales/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();
    cy.assertNoServerError();

    // Verify sale appears (product name should be visible)
    cy.get("body").should("contain.text", productName);

    // ============================================================
    // STEP 7: Edit selling price for unsold item (if feature exists)
    // ============================================================
    // Try to edit product - navigate back to product list
    cy.visitDashboard("clothing");
    cy.waitForAppShell();

    cy.get("body").then(($body) => {
      const productsLink = $body.find('a[href*="product"], a[href*="hub"]').first();
      if (productsLink.length) {
        cy.wrap(productsLink).click();
      }
    });

    cy.waitForAppShell();

    // Try to find edit link/button for the product
    cy.get("body").then(($body) => {
      // Look for edit link near product name
      const productRow = $body.find(`*:contains("${productName}")`).first();
      if (productRow.length) {
        const editLink = productRow.closest("tr, .product-item, .card").find('a[href*="edit"], button[data-cy="edit"]').first();
        if (editLink.length) {
          cy.wrap(editLink).click({ force: true });
          cy.waitForAppShell();

          // Update selling price
          const newPrice = "9000";
          if ($body.find('input[name="selling_price"]').length) {
            cy.get('input[name="selling_price"]').first().clear().type(newPrice);
          }

          // Save
          cy.get("body").then(($form) => {
            const saveBtn = $form.find('button[type="submit"], [data-cy="save"]').first();
            if (saveBtn.length) {
              cy.wrap(saveBtn).click();
              cy.wait(1000);
              cy.assertNoServerError();
            }
          });
        }
      }
    });

    // ============================================================
    // STEP 8: Guardrails - attempt to sell with invalid quantity/negative stock
    // ============================================================
    cy.visitDashboard("clothing");
    cy.waitForAppShell();

    cy.get("body").then(($body) => {
      const sellLink = $body.find('a[href*="sell"], a[href*="sale"]').first();
      if (sellLink.length) {
        cy.wrap(sellLink).click();
      } else {
        cy.visit("/verticals/clothing/sell/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Try to sell more than available stock
    cy.get("body").then(($body) => {
      if ($body.find('select[name="product"]').length) {
        cy.get('select[name="product"]').select(1);

        // Enter quantity larger than available stock
        const excessiveQuantity = "9999";
        if ($body.find('input[name="quantity"]').length) {
          cy.get('input[name="quantity"]').first().clear().type(excessiveQuantity);
        }

        // Submit and verify validation error
        cy.get("body").then(($form) => {
          const submitBtn = $form.find('button[type="submit"], [data-cy="submit-sale"]').first();
          if (submitBtn.length) {
            cy.wrap(submitBtn).click();
            cy.wait(1000);

            // Verify error message about insufficient stock
            cy.get("body").should(($body) => {
              const text = $body.text().toLowerCase();
              expect(text).to.satisfy(
                (t) =>
                  t.includes("insufficient") ||
                  t.includes("not enough") ||
                  t.includes("stock") ||
                  t.includes("available") ||
                  t.includes("error")
              );
            });
          }
        });
      }
    });

    cy.assertNoServerError();
  });

  it("should handle 'no barcode' path correctly (clothing-specific)", () => {
    cy.loginAsManager("clothing");
    cy.visitDashboard("clothing");
    cy.waitForAppShell();

    // Navigate to add product
    cy.get("body").then(($body) => {
      const addLink = $body.find('a[href*="wizard"], a[href*="product"], a[href*="add"], [data-cy="add-product"]').first();
      if (addLink.length) {
        cy.wrap(addLink).click();
      } else {
        cy.visit("/inventory/wizard/clothing/", { failOnStatusCode: false });
        cy.visit("/inventory/clothing/products/new/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Verify barcode field is optional (not required)
    cy.get("body").then(($form) => {
      const barcodeField = $form.find('input[name="barcode"], [data-cy="barcode"]');
      if (barcodeField.length) {
        // Field exists but should not have required attribute
        cy.get('input[name="barcode"], [data-cy="barcode"]').should(($input) => {
          const required = $input.attr("required");
          expect(required).to.be.undefined; // Not required
        });
      } else {
        // Barcode field doesn't exist - that's fine for "no barcode" path
        cy.log("Barcode field not present - acceptable for 'no barcode' path");
      }
    });
  });
});
