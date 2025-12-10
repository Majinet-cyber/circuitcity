// cypress/e2e/phones_scan_in_flow.cy.js

/**
 * Generate a random 15-digit IMEI-style string
 */
function generateRandomImei() {
  return Array.from({ length: 15 }, () =>
    Math.floor(Math.random() * 10)
  ).join("");
}

/**
 * Phones flow:
 *
 * 1. Login as manager (cy.loginAsOwner)
 * 2. Go to Scan In Phones
 * 3. Click ITEL, choose first ITEL model
 * 4. Scan in a random 15-digit IMEI
 * 5. Verify IMEI appears in Stock List
 * 6. Open Scan & Sell wizard
 * 7. Choose ITEL + same model + specs
 * 8. Paste same IMEI, set price 500000, pick any payment
 * 9. Confirm sale and verify success
 */

describe("Phones flow: ITEL scan-in → sell same phone", () => {
  const BRAND = "ITEL";

  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("scans an ITEL phone into stock, then sells that exact IMEI", () => {
    // One fresh IMEI for the whole journey
    const IMEI = generateRandomImei();

    // ----------------------------------------------------------
    // STEP 1: Login as EMPIRE manager (using custom command)
    // ----------------------------------------------------------
    cy.loginAsOwner();

    cy.url({ timeout: 60000 }).should("include", "/inventory/verticals/phones/");

    // ----------------------------------------------------------
    // STEP 2: Go to Scan In Phones
    // ----------------------------------------------------------
    cy.visit("/inventory/scan-in/");

    cy.contains(".card, .brand-card, button, [data-cy=brand-card]", new RegExp(BRAND, "i"))
      .first()
      .click();

    cy.contains(/ITEL Models/i, { timeout: 20000 }).should("exist");

    // ----------------------------------------------------------
    // STEP 3: Choose first ITEL model, remember its text
    // ----------------------------------------------------------
    cy.get("select", { timeout: 20000 })
      .first()
      .as("modelSelect")
      .select(1, { force: true }); // index 0 is placeholder

    // Capture the selected model text, e.g. "ITEL A90 (3+128)"
    cy.get("@modelSelect")
      .find("option:selected")
      .invoke("text")
      .then((text) => text.trim())
      .as("selectedModel");

    // ----------------------------------------------------------
    // STEP 4: Enter IMEI and submit scan
    // ----------------------------------------------------------
    cy.window().then((win) => {
      const doc = win.document;
      const input =
        doc.querySelector("input[name='imei']") ||
        doc.querySelector("#imei-input") ||
        doc.querySelector("[data-cy='imei-input']");

      if (!input) {
        throw new Error("IMEI input not found on Scan In page");
      }
      input.value = IMEI;
    });

    cy.window().then((win) => {
      const form =
        win.document.querySelector("form#scan-form") ||
        win.document.querySelector("#scan-form-wrapper form");

      if (!form) {
        throw new Error("Scan-in form not found");
      }
      form.submit();
    });

    cy.contains(/added to stock|scanned .* added to stock/i, {
      timeout: 15000,
    }).should("exist");

    // ----------------------------------------------------------
    // STEP 5: Verify in Stock List
    // ----------------------------------------------------------
    cy.visit("/inventory/list/");

    cy.get(
      "input[placeholder*='Search IMEI'], input[placeholder*='Search IMEI/brand/model']",
      { timeout: 20000 }
    )
      .first()
      .clear()
      .type(IMEI);

    cy.contains("td", IMEI, { timeout: 20000 }).should("exist");

    // ----------------------------------------------------------
    // STEP 6: Go to Scan & Sell wizard
    // ----------------------------------------------------------
    cy.visit("/inventory/phone-sale-wizard/");

    // Step 1: choose brand ITEL
    cy.contains(
      "[data-cy='sale-brand-option'], .brand-card, .card, button",
      new RegExp(BRAND, "i")
    )
      .first()
      .click();

    cy.contains("button", /continue|next/i)
      .first()
      .click();

    // Step 2: choose same model as in scan-in
    cy.get("@selectedModel").then((modelText) => {
      cy.contains(
        "[data-cy='sale-model-option'], .model-card, .card, button",
        new RegExp(modelText.replace(/\s+/g, " ").trim(), "i")
      )
        .first()
        .click();
    });

    cy.contains("button", /continue|next/i)
      .first()
      .click();

    // Step 3: choose specs if that step exists
    cy.get("body").then(($body) => {
      const specSelector =
        "[data-cy='sale-spec-option'], .spec-card, .variant-card, .option-card";

      if ($body.find(specSelector).length > 0) {
        cy.get(specSelector).first().click();
        cy.contains("button", /continue|next/i)
          .first()
          .click();
      }
    });

    // ----------------------------------------------------------
    // STEP 7: Enter same IMEI in the wizard
    // ----------------------------------------------------------
    cy.get(
      "input[name='imei'], input[placeholder*='IMEI Number'], input[placeholder*='Enter 15-digit IMEI']",
      { timeout: 20000 }
    )
      .should("be.visible")
      .clear()
      .type(IMEI);

    cy.contains("button", /continue|next/i)
      .first()
      .click();

    // ----------------------------------------------------------
    // STEP 8: Set selling price & pick any payment method
    // ----------------------------------------------------------
    cy.get(
      "input[name='selling_price'], input[name='price'], [data-cy='selling-price']",
      { timeout: 20000 }
    )
      .should("be.visible")
      .clear()
      .type("500000");

    cy.get("body").then(($body) => {
      const labels = [
        "Cash",
        "Bank",
        "Mobile Money",
        "Airtel Money",
        "TNM Mpamba",
      ];
      let clicked = false;

      labels.forEach((label) => {
        if (!clicked && $body.find(`button:contains("${label}")`).length > 0) {
          cy.contains("button", label).click();
          clicked = true;
        }
      });

      if (!clicked && $body.find("[data-cy^='payment-']").length > 0) {
        cy.get("[data-cy^='payment-']").first().click();
      }
    });

    cy.contains("button", /complete sale|confirm sale|finish|submit|save/i)
      .first()
      .click();

    // ----------------------------------------------------------
    // STEP 9: Verify sale success
    // ----------------------------------------------------------
    cy.get("body", { timeout: 20000 }).should(($body) => {
      const text = $body.text().toLowerCase();
      expect(text).to.satisfy((t) =>
        t.includes("sale") &&
        (t.includes("success") || t.includes("completed") || t.includes("recorded"))
      );
    });
  });
});
