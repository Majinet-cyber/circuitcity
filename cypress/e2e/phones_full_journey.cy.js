// cypress/e2e/phone_manager_flow.cy.js
/**
 * Simple phones manager flow:
 *
 * 1. Login as manager
 * 2. Add TECNO phone model "Spark 40 4+128"
 * 3. Scan in one phone with a test IMEI
 * 4. Sell that exact phone via the sale wizard
 */

describe("Phones manager flow: add TECNO model → scan in → sell once", () => {
  const BRAND = "TECNO";
  const MODEL = "Spark 40 4+128";
  const IMEI = "123456789012345";     // any 15-digit test IMEI
  const ORDER_PRICE = "250000";       // adjust if you like
  const SELL_PRICE = "300000";        // selling price used in sale step

  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("creates TECNO model, scans stock in, and sells that phone", () => {
    // 1. Login (uses your custom command)
    cy.loginAsOwner();

    // ----------------------------------------------------------
    // STEP 1: Add TECNO phone model "Spark 40 4+128"
    // ----------------------------------------------------------
    cy.visit("/inventory/phone-products/");

    // Find TECNO brand card
    cy.contains(".brand-card, .card", BRAND)
      .first()
      .as("tecnoCard");

    cy.get("@tecnoCard").within(() => {
      // Click "Add model" (adjust text if different)
      cy.contains("button, a", /add model|add phone|create model/i)
        .first()
        .click({ force: true });
    });

    // Fill model form (page or modal)
    cy.get("input[name='name'], input[name='model_name']")
      .should("be.visible")
      .clear()
      .type(MODEL);

    cy.get("input[name='order_price'], input[name='cost_price']")
      .first()
      .clear()
      .type(ORDER_PRICE);

    cy.contains("button, a", /save|create|add/i)
      .first()
      .click();

    // Confirm model now exists somewhere on the products page
    cy.contains(MODEL).should("exist");

    // ----------------------------------------------------------
    // STEP 2: Scan in a phone for that model
    // ----------------------------------------------------------
    cy.visit("/inventory/scan-in/");

    // Choose TECNO brand card on Scan In page
    cy.contains(
      "[data-cy='scan-brand-card'], .phone-brand-card, .card",
      BRAND
    )
      .first()
      .click();

    // Choose the model from dropdown
    cy.get("select[name='model'], [data-cy='scan-model-select']")
      .should("be.visible")
      .select(MODEL);

    // Click button that reveals IMEI form (e.g. "Scan In Phone")
    cy.contains("button, a", /scan in phone|scan phone|add stock/i)
      .first()
      .click();

    // IMPORTANT: Only interact with the VISIBLE IMEI input
    // This avoids the hidden #imei-input inside #scan-form-wrapper
    cy.get(
      "input[name='imei']:visible, #imei-input:visible, [data-cy='imei-input']:visible"
    )
      .should("be.visible")
      .clear()
      .type(IMEI);

    cy.contains("button, a", /save phone|save|add phone/i)
      .first()
      .click();

    // Confirm IMEI appears in inventory stock list
    cy.visit("/inventory/list/");
    cy.contains(IMEI).should("exist");

    // ----------------------------------------------------------
    // STEP 3: Sell that phone via phone sale wizard
    // ----------------------------------------------------------
    cy.visit("/inventory/phone-sale-wizard/");

    // Wizard Step 1: choose brand TECNO
    cy.contains(
      "[data-cy='sale-brand-option'], .brand-option, .card",
      BRAND
    )
      .first()
      .click();

    cy.contains("button", /continue|next/i)
      .first()
      .click();

    // Wizard Step 2: choose model Spark 40 4+128
    cy.contains(
      "[data-cy='sale-model-option'], .model-option, .card",
      MODEL
    )
      .first()
      .click();

    cy.contains("button", /continue|next/i)
      .first()
      .click();

    // Wizard Step 3: enter IMEI (use ONLY visible field)
    cy.get(
      "input[name='imei']:visible, [data-cy='sale-imei-input']:visible"
    )
      .should("be.visible")
      .clear()
      .type(IMEI);

    cy.contains("button", /continue|next/i)
      .first()
      .click();

    // Wizard Step 4: set price and payment method
    cy.get(
      "input[name='selling_price'], [data-cy='selling-price']"
    )
      .should("be.visible")
      .clear()
      .type(SELL_PRICE);

    // Choose any payment button that exists (Cash / Bank / Mobile Money)
    cy.get("body").then(($body) => {
      if ($body.find("button:contains('Cash')").length) {
        cy.contains("button", "Cash").click();
      } else if ($body.find("button:contains('Bank')").length) {
        cy.contains("button", "Bank").click();
      } else if ($body.find("button:contains('Mobile Money')").length) {
        cy.contains("button", "Mobile Money").click();
      }
    });

    cy.contains(
      "button",
      /complete sale|confirm sale|finish|submit/i
    )
      .first()
      .click();

    // ----------------------------------------------------------
    // STEP 4: Basic success checks
    // ----------------------------------------------------------

    // Check for a generic success message
    cy.get("body").should(($body) => {
      const text = $body.text().toLowerCase();
      expect(text).to.satisfy((t) =>
        t.includes("sale") && (t.includes("success") || t.includes("completed") || t.includes("recorded"))
      );
    });

    // Optional: check that IMEI now shows as sold in stock list
    cy.visit("/inventory/list/");
    cy.contains(IMEI)
      .parents("tr")
      .within(() => {
        // Adjust this to whatever you display for sold items
        cy.contains(/sold|out/i).should("exist");
      });
  });
});
