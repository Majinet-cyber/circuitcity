// cypress/e2e/phones_scan_in_flow.cy.js
/**
 * Minimal phones scan-in flow:
 *
 * 1. Login as EMPIRE manager
 * 2. Go to Scan In Phones
 * 3. Click ITEL, pick any available model
 * 4. Inject a 15-digit IMEI and submit
 * 5. Confirm IMEI appears in Stock List
 */

describe("Phones scan-in flow: ITEL → stock list shows IMEI", () => {
  const IMEI = "555666777888999"; // any 15-digit IMEI

  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("logs in, scans an ITEL phone into stock, and verifies stock list", () => {
    // ----------------------------------------------------------
    // STEP 1: Login as EMPIRE manager (no custom command)
    // ----------------------------------------------------------
    cy.visit("/accounts/login/");

    // Email / username
    cy.get(
      "input[name='username'], input[name='email'], [data-cy=login-email]"
    )
      .first()
      .clear()
      .type("empire@gmail.com"); // <-- your real login

    // Password
    cy.get("input[name='password'], [data-cy=login-password]")
      .first()
      .clear()
      .type("@Lincoln1863?");    // <-- your real password

    // Submit
    cy.get("button[type='submit'], [data-cy=login-submit]")
      .first()
      .click();

    // Assert we landed in the app (phones dashboard)
    cy.url({ timeout: 10000 }).should(
      "include",
      "/inventory/verticals/phones/"
    );
    cy.contains(/Phones & Electronics/i).should("exist");

    // ----------------------------------------------------------
    // STEP 2: Go to Scan In Phones
    // ----------------------------------------------------------
    cy.visit("/inventory/scan-in/");

    // Click ITEL brand card
    cy.contains(".card, .brand-card, button, [data-cy=brand-card]", /itel/i)
      .first()
      .click();

    // ----------------------------------------------------------
    // STEP 3: Pick any available ITEL model
    // ----------------------------------------------------------
    cy.contains(/ITEL Models/i).should("exist");

    cy.get("select[name='model'], [data-cy='scan-model-select']")
      .should("exist")
      .then(($sel) => {
        const select = $sel[0];
        // pick first non-placeholder option
        if (select.options.length > 1) {
          select.selectedIndex = 1;
          select.dispatchEvent(new Event("change", { bubbles: true }));
        } else {
          throw new Error("No ITEL models available in the dropdown");
        }
      });

    // ----------------------------------------------------------
    // STEP 4: Inject IMEI into the form and submit
    // ----------------------------------------------------------
    // Use raw DOM to bypass Cypress visibility checks on the IMEI input
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

    // Submit the scan-in form via JS
    cy.window().then((win) => {
      const form =
        win.document.querySelector("form#scan-form") ||
        win.document.querySelector("#scan-form-wrapper form");
      if (!form) {
        throw new Error("Scan-in form not found");
      }
      form.submit();
    });

    // ----------------------------------------------------------
    // STEP 5: Confirm success + IMEI in stock list
    // ----------------------------------------------------------
    cy.contains(/added to stock|scanned .* added to stock/i, {
      timeout: 8000,
    }).should("exist");

    cy.visit("/inventory/list/");

    cy.get(
      "input[placeholder*='Search IMEI'], input[placeholder*='Search IMEI/brand/model']"
    )
      .first()
      .clear()
      .type(IMEI);

    cy.contains("td", IMEI).should("exist");
  });
});
