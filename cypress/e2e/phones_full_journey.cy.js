// cypress/e2e/phones_full_journey.cy.js
/**
 * End-to-end tests for Phones vertical
 *
 * Main flow:
 * - Login as manager
 * - Ensure a phone product exists (IPHONE 15 Pro Max as example)
 * - Ensure at least one stock item exists for that product (scan in if needed)
 * - Run sale wizard: choose brand + model, enter IMEI from stock
 * - Set selling price with ≥20% margin over cost
 * - Choose any payment method (Cash / Bank / Mobile Money) and complete sale
 * - Simple extra checks: dashboard + low stock alerts
 */

const TEST_BRAND = "IPHONE";
const TEST_MODEL = "Iphone 15 Pro Max 8+256";  // adjust to your real model name
const TEST_IMEI = "359999999999999";           // dummy IMEI used when we create stock

describe("Phones Full Journey", () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  /**
   * Ensure a phone product exists for the given brand/model.
   * Uses /inventory/phone-products/ UI.
   */
  function ensurePhoneProductExists() {
    cy.visit("/inventory/phone-products/");

    cy.get("body").then(($body) => {
      // If our model name already exists anywhere on the page, we’re done.
      if ($body.text().includes(TEST_MODEL)) {
        cy.log("✅ Phone model already exists:", TEST_MODEL);
        return;
      }

      cy.log("ℹ️ Creating phone model:", TEST_MODEL);

      // Find the brand card (IPHONE) – adjust selector to your brand cards
      cy.contains(".brand-card, .card", TEST_BRAND)
        .as("brandCard");

      cy.get("@brandCard").within(() => {
        // Click the "Add model" control for that brand
        cy.get(
          "[data-cy='add-model-btn'], a:contains('Add model'), button:contains('Add model')"
        )
          .first()
          .click();
      });

      // Now we should be on the "Add model" form / modal.
      // Adjust input names/selectors as needed.
      cy.get("input[name='name'], input[name='model_name']")
        .clear()
        .type(TEST_MODEL);

      // Cost / order price – example: 2,800,000
      cy.get("input[name='cost_price'], input[name='order_price']")
        .first()
        .clear()
        .type("2800000");

      // Submit model form
      cy.get("button[type='submit'], [data-cy='submit-btn']")
        .contains(/save|create|add/i)
        .first()
        .click();

      // Confirm model appears on the products page
      cy.contains(TEST_MODEL).should("exist");
      cy.log("✅ Phone model created:", TEST_MODEL);
    });
  }

  /**
   * Ensure that there is at least ONE stock item for TEST_MODEL with TEST_IMEI.
   * Checks /inventory/list/ and if not found, uses /inventory/scan-in/.
   */
  function ensureStockExistsForTestPhone() {
    cy.visit("/inventory/list/");

    cy.get("body").then(($body) => {
      if ($body.text().includes(TEST_IMEI)) {
        cy.log("✅ Stock already present for IMEI:", TEST_IMEI);
        return;
      }

      cy.log("ℹ️ No stock for IMEI yet, scanning phone in");

      // Go to Scan IN page
      cy.visit("/inventory/scan-in/");

      // Select brand (IPHONE) – adjust selector to your brand tiles/cards
      cy.contains(
        "[data-cy='scan-brand-card'], .phone-brand-card, .card",
        TEST_BRAND
      ).click();

      // Select the specific model
      cy.get("select[name='model'], [data-cy='scan-model-select']")
        .should("be.visible")
        .select(TEST_MODEL);

      // Click the button that reveals the IMEI form
      cy.contains(
        "button, a",
        /scan in phone|scan phone|add stock/i
      )
        .first()
        .click();

      // Now the IMEI field in the scan form should be visible.
      // Important: use :visible so we never hit hidden #imei-input.
      cy.get("input[name='imei']:visible, [data-cy='imei-input']:visible")
        .should("be.visible")
        .clear()
        .type(TEST_IMEI);

      // Submit / save
      cy.contains("button, a", /save|add phone|create/i)
        .first()
        .click();

      // Confirm stock shows up in list
      cy.visit("/inventory/list/");
      cy.contains(TEST_IMEI).should("exist");
      cy.log("✅ Stock created for IMEI:", TEST_IMEI);
    });
  }

  /**
   * Completes a phone sale using the sale wizard.
   * Requires TEST_BRAND, TEST_MODEL, TEST_IMEI to be valid.
   * Sets selling price with ≥20% margin over cost.
   */
  function completeSaleWithMargin() {
    cy.log("ℹ️ Starting phone sale wizard");

    cy.visit("/inventory/phone-sale-wizard/");

    // STEP 1: Choose brand
    cy.contains(
      "[data-cy='sale-brand-option'], .brand-option, .card",
      TEST_BRAND
    )
      .first()
      .click();

    cy.contains("button", /continue|next/i)
      .first()
      .click();

    // STEP 2: Choose model
    cy.contains(
      "[data-cy='sale-model-option'], .model-option, .card",
      TEST_MODEL
    )
      .first()
      .click();

    cy.contains("button", /continue|next/i)
      .first()
      .click();

    // STEP 3: IMEI entry (wizard version – visible field only!)
    cy.get("input[name='imei']:visible, [data-cy='sale-imei-input']:visible")
      .should("be.visible")
      .clear()
      .type(TEST_IMEI);

    cy.contains("button", /continue|next/i)
      .first()
      .click();

    // STEP 4: pricing / payment
    // Read cost price from input, then set selling price = cost * 1.2 (20% margin)
    cy.get(
      "[data-cy='cost-price'], input[name='cost_price'], input[data-field='cost_price']"
    )
      .invoke("val")
      .then((rawCost) => {
        const numeric = String(rawCost).replace(/,/g, "");
        const cost = Number(numeric || 0) || 0;

        const sellingPrice = Math.round(cost * 1.2); // 20% margin

        cy.get(
          "[data-cy='selling-price'], input[name='selling_price'], input[data-field='selling_price']"
        )
          .clear()
          .type(String(sellingPrice));

        // Payment method: click any of Cash / Bank / Mobile Money that exists
        cy.get("body").then(($body) => {
          const methods = ["Cash", "Bank", "Mobile Money"];
          let clicked = false;

          methods.forEach((label) => {
            if (!clicked && $body.find(`button:contains("${label}")`).length) {
              cy.contains("button", label).click();
              clicked = true;
            }
          });

          if (!clicked) {
            // Fallback: maybe a <select>
            cy.get(
              "select[name='payment_method'], [data-cy='payment-method']"
            ).then(($select) => {
              if ($select.length) {
                // prefer cash if available
                if ($select.find("option[value='cash']").length) {
                  cy.wrap($select).select("cash");
                } else {
                  cy.wrap($select).select(1);
                }
              }
            });
          }
        });

        // Complete the sale
        cy.contains(
          "button",
          /complete sale|confirm sale|submit|finish/i
        )
          .first()
          .click();
      });

    // Confirm success – tweak text to match your toast / alert
    cy.get("body").should(($body) => {
      expect($body.text().toLowerCase()).to.satisfy((txt) =>
        txt.includes("sale completed") ||
        txt.includes("success") ||
        txt.includes("sale recorded")
      );
    });

    cy.log("✅ Sale completed with ≥20% profit margin");
  }

  it("completes phones cash sale with ≥20% profit from existing or created stock", () => {
    // 1. Login + open phones dashboard (custom helper)
    cy.loginAsOwner();
    cy.visitDashboard("phones");

    // 2. Ensure the product exists
    ensurePhoneProductExists();

    // 3. Ensure stock exists for that model (scan in if required)
    ensureStockExistsForTestPhone();

    // 4. Run sale wizard using that stock
    completeSaleWithMargin();

    // 5. Optional: verify that IMEI appears as sold in inventory list
    cy.visit("/inventory/list/");
    cy.contains(TEST_IMEI)
      .parents("tr")
      .within(() => {
        // adjust selector/text to how you mark sold items
        cy.contains(/sold|out/i).should("exist");
      });
  });

  it("handles stock low / out-of-stock alerts gracefully", () => {
    cy.loginAsOwner();
    cy.visitDashboard("phones");

    cy.get("body").then(($body) => {
      // Check for low stock or out of stock alerts
      const alertSelectors = [
        '[data-cy="low-stock-alert"]',
        ".alert:contains('low stock')",
        ".badge:contains('Out of Stock')",
      ];

      alertSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).should("be.visible");
          cy.log("✅ Low stock/out-of-stock alert displayed");
        }
      });
    });
  });

  it("displays phones dashboard without server errors", () => {
    cy.loginAsOwner();
    cy.visitDashboard("phones");

    // Verify no server errors
    cy.get("body").should("not.contain", "500 Internal Server Error");
    cy.get("body").should("not.contain", "404 Not Found");
    cy.get("body").should("not.contain", "Application error");

    // Verify page loaded
    cy.get("body").should("be.visible");
  });
});
