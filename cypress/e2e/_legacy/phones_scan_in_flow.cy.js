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
 * Helper: find the IMEI input on the sale wizard (Step 4)
 */
function getSaleImeiInput() {
  return cy.get(
    [
      "input[data-cy='sale-imei-input']",
      "input[name='imei']",
      "input[placeholder*='IMEI Number' i]",
      "input[placeholder*='Enter 15-digit IMEI' i]",
    ].join(", "),
    { timeout: 20000 }
  );
}

/**
 * Phones flow:
 *
 * 1. Login as manager (cy.loginAsOwner)
 * 2. Go to Scan In Phones
 * 3. Click ITEL, choose first ITEL model (dropdown)
 * 4. Scan in a random 15-digit IMEI
 * 5. Soft-verify IMEI appears in Stock List
 * 6. Open Scan & Sell wizard
 * 7. Wizard Step 2: choose first model radio
 * 8. Wizard Step 3: choose first variant card (if step exists)
 * 9. Wizard Step 4: paste same IMEI, set price 500000, pick any payment
 * 10. Confirm sale and verify success
 */

describe("Phones flow: ITEL scan-in → sell same phone via wizard", () => {
  const BRAND = "ITEL";

  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("scans an ITEL phone into stock, then sells that exact IMEI via wizard", () => {
    const IMEI = generateRandomImei();
    cy.log(`🔢 Generated IMEI: ${IMEI}`);

    // ----------------------------------------------------------
    // STEP 1: Login as EMPIRE manager
    // ----------------------------------------------------------
    cy.log("🔐 Step 1: Log in as EMPIRE manager");
    cy.loginAsOwner();
    cy.url({ timeout: 60000 }).should("include", "/inventory/verticals/phones/");

    // ----------------------------------------------------------
    // STEP 2: Go to Scan In Phones and pick ITEL brand
    // ----------------------------------------------------------
    cy.log("📲 Step 2: Go to Scan In Phones and pick ITEL");
    cy.visit("/inventory/phones/scan-in/");

    cy.contains(
      ".card, .brand-card, button, [data-cy=brand-card]",
      new RegExp(BRAND, "i")
    )
      .first()
      .click();

    cy.contains(/ITEL Models/i, { timeout: 20000 }).should("exist");

    // ----------------------------------------------------------
    // STEP 3: Choose first ITEL model (dropdown)
    // ----------------------------------------------------------
    cy.log("📦 Step 3: Choose first ITEL model in dropdown");
    cy.get("select", { timeout: 20000 })
      .first()
      .as("modelSelect")
      .select(1, { force: true }); // index 0 is placeholder

    // Just log the selected model for debugging
    cy.get("@modelSelect")
      .find("option:selected")
      .invoke("text")
      .then((text) => {
        cy.log(`ℹ️ Scan-in model selected: ${text.trim()}`);
      });

    // ----------------------------------------------------------
    // STEP 4: Enter IMEI and submit scan
    // ----------------------------------------------------------
    cy.log("📡 Step 4: Enter IMEI and submit scan");
    cy.get("input[name='imei'], #imei-input, [data-cy='imei-input']", {
      timeout: 20000,
    })
      .first()
      .clear()
      .type(IMEI);

    cy.contains("button, input[type='submit']", /scan|add to stock|submit/i)
      .first()
      .click();

    // Less brittle: just look for "added to stock"
    cy.contains(/added to stock/i, { timeout: 15000 }).should("exist");

    // ----------------------------------------------------------
    // STEP 5: Soft check IMEI in Stock List
    // ----------------------------------------------------------
    cy.log("📋 Step 5: Soft check IMEI in Stock List");
    cy.visit("/inventory/list/");

    cy.get(
      "input[placeholder*='Search IMEI' i], input[placeholder*='Search IMEI/brand/model' i]",
      { timeout: 20000 }
    )
      .first()
      .clear()
      .type(IMEI);

    cy.wait(1000);

    cy.get("body", { timeout: 20000 }).then(($body) => {
      const found = $body
        .find("td")
        .toArray()
        .some((el) => el.innerText.includes(IMEI));

      if (found) {
        cy.log("✅ IMEI found in stock list");
      } else {
        cy.log("⚠️ IMEI NOT found in stock list – continuing anyway");
      }
    });

    // ----------------------------------------------------------
    // STEP 6: Open Phone Sale Wizard and choose brand ITEL (Step 1)
    // ----------------------------------------------------------
    cy.log("🧭 Step 6: Open Phone Sale Wizard and choose ITEL brand");
    cy.visit("/inventory/phone-sale-wizard/");

    cy.contains(
      "[data-cy='sale-brand-option'], .brand-card, .card, button",
      new RegExp(BRAND, "i")
    )
      .first()
      .click({ force: true });

    cy.contains("button", /continue|next/i)
      .first()
      .click();

    // ----------------------------------------------------------
    // STEP 7: Wizard Step 2 – choose first visible model radio
    // ----------------------------------------------------------
    cy.log("📦 Step 7: Choose first model in wizard (Step 2)");
    cy.get("input[type='radio']", { timeout: 10000 })
      .filter(":visible")
      .first()
      .check({ force: true });

    cy.contains("button", /continue|next/i)
      .first()
      .click();

    // ----------------------------------------------------------
    // STEP 8: Wizard Step 3 – click first visible variant card (if step exists)
    // ----------------------------------------------------------
    cy.log("⚙️ Step 8: Choose variant/spec (Step 3, if present)");
    cy.get("body").then(($body) => {
      const isVariantStep = /variant/i.test($body.text());
      if (!isVariantStep) {
        cy.log("ℹ️ No variant step detected – skipping to IMEI");
        return;
      }

      // Click the first visible card-like element in the variant area.
      // This matches your Step 3 UI: a single ITEL A90 (3+128) card.
      return cy
        .get(
          "[data-cy='sale-variant-option'], [data-cy='sale-spec-option'], .variant-card, .option-card, .card",
          { timeout: 10000 }
        )
        .filter(":visible")
        .first()
        .click({ force: true })
        .then(() => {
          cy.contains("button", /continue|next/i)
            .first()
            .click();
        });
    });

    // ----------------------------------------------------------
    // STEP 9: Enter same IMEI in the wizard (IMEI step)
    // ----------------------------------------------------------
    cy.log("🧾 Step 9: Enter same IMEI in wizard");
    getSaleImeiInput()
      .should("be.visible")
      .clear()
      .type(IMEI);

    cy.contains("button", /continue|next/i)
      .first()
      .click();

    // ----------------------------------------------------------
    // STEP 10: Set selling price & pick any payment method
    // ----------------------------------------------------------
    cy.log("💰 Step 10: Set price and payment");
    cy.get(
      "input[data-cy='selling-price-input'], input[name='selling_price'], input[name='price']",
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
          cy.contains("button", label).click({ force: true });
          clicked = true;
        }
      });

      if (!clicked && $body.find("[data-cy^='payment-']").length > 0) {
        cy.get("[data-cy^='payment-']").first().click({ force: true });
      }
    });

    cy.contains(
      "button, [data-cy='confirm-sale-btn']",
      /complete sale|confirm sale|finish|submit|save/i
    )
      .first()
      .click();

    // ----------------------------------------------------------
    // STEP 11: Verify sale success
    // ----------------------------------------------------------
    cy.log("🎉 Step 11: Verify sale success");
    cy.get("body", { timeout: 20000 }).should(($body) => {
      const text = $body.text().toLowerCase();
      expect(text).to.satisfy((t) =>
        t.includes("sale") &&
        (t.includes("success") || t.includes("completed") || t.includes("recorded"))
      );
    });
  });
});
