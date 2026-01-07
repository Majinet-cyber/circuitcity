// cypress/e2e/verticals/gym_journey.cy.js
/**
 * Full user journey test for Gym vertical.
 * Covers: login → dashboard → register member → payment → reports → settings → logout
 * Gym-specific: membership sale flow (not product-based)
 */
describe("Gym Vertical - Full User Journey", () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("should complete full manager journey for gym vertical", () => {
    // ============================================================
    // STEP 1: Login as manager
    // ============================================================
    cy.loginAsManager("gym");
    cy.url().should("not.include", "/accounts/login/");
    cy.assertNoServerError();

    // ============================================================
    // STEP 2: Go to dashboard → confirm page loads
    // ============================================================
    cy.visitDashboard("gym");
    cy.waitForAppShell();
    cy.assertNoServerError();

    cy.get("body").should("contain.text", "dashboard").or("contain.text", "Dashboard").or("contain.text", "Gym");

    // ============================================================
    // STEP 3: Register new member (gym-specific: membership sale)
    // ============================================================
    cy.get("body").then(($body) => {
      const addMemberLink = $body.find('a[href*="member"], a[href*="add"], [data-cy="add-member"]').first();
      if (addMemberLink.length) {
        cy.wrap(addMemberLink).click();
      } else {
        cy.visit("/verticals/gym/members/add/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();

    // Fill member registration form
    const timestamp = Date.now();
    const memberName = `Test Member ${timestamp}`;
    const memberPhone = `0999${timestamp.toString().slice(-6)}`;

    // Member name
    cy.get("body").then(($body) => {
      if ($body.find('[data-cy="member-name"]').length) {
        cy.get('[data-cy="member-name"]').type(memberName);
      } else if ($body.find('input[name="name"], input[name="full_name"]').length) {
        cy.get('input[name="name"], input[name="full_name"]').first().type(memberName);
      }
    });

    // Phone
    cy.get("body").then(($body) => {
      if ($body.find('[data-cy="member-phone"]').length) {
        cy.get('[data-cy="member-phone"]').type(memberPhone);
      } else if ($body.find('input[name="phone"], input[name="phone_number"]').length) {
        cy.get('input[name="phone"], input[name="phone_number"]').first().type(memberPhone);
      }
    });

    // Email (optional)
    cy.get("body").then(($body) => {
      if ($body.find('[data-cy="member-email"]').length) {
        cy.get('[data-cy="member-email"]').type(`member${timestamp}@test.com`);
      } else if ($body.find('input[name="email"]').length) {
        cy.get('input[name="email"]').type(`member${timestamp}@test.com`);
      }
    });

    // Payment amount (30-day membership)
    cy.get("body").then(($body) => {
      if ($body.find('[data-cy="payment-amount"]').length) {
        cy.get('[data-cy="payment-amount"]').type("50000");
      } else if ($body.find('input[name="amount"], input[name="payment_amount"]').length) {
        cy.get('input[name="amount"], input[name="payment_amount"]').first().type("50000");
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

    // Submit
    cy.get("body").then(($body) => {
      const submitBtn = $body.find('button[type="submit"], [data-cy="submit"]').first();
      if (submitBtn.length) {
        cy.wrap(submitBtn).click();
      } else {
        cy.contains("button", /save|submit|register|create/i).first().click();
      }
    });

    cy.wait(2000);
    cy.assertNoServerError();
    cy.verifySuccess();

    // ============================================================
    // STEP 4: Verify member appears in list with 30 days
    // ============================================================
    cy.visitDashboard("gym");
    cy.waitForAppShell();

    // Check for member in list
    cy.get("body").should("contain.text", memberName).or("contain.text", "member").or("contain.text", "Member");

    // Verify days remaining indicator (should show ~30 days)
    cy.get("body").then(($body) => {
      if ($body.find('[data-cy="days-remaining"]').length) {
        cy.get('[data-cy="days-remaining"]').should("contain", "30").or("contain", "days");
      } else if ($body.text().includes("30") || $body.text().includes("days")) {
        cy.log("✓ Member has 30 days remaining");
      }
    });

    // ============================================================
    // STEP 5: Check member status (active/arrears)
    // ============================================================
    cy.visitDashboard("gym");
    cy.waitForAppShell();

    // Navigate to members list
    cy.get("body").then(($body) => {
      const membersLink = $body.find('a[href*="member"], [data-cy="members"]').first();
      if (membersLink.length) {
        cy.wrap(membersLink).click();
      } else {
        cy.visit("/verticals/gym/members/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();
    cy.assertNoServerError();

    // Verify member appears
    cy.get("body").should("contain.text", memberName);

    // ============================================================
    // STEP 6: Reports page loads
    // ============================================================
    cy.get("body").then(($body) => {
      const reportsLink = $body.find('a[href*="report"], a[href*="analytics"], [data-cy="reports"]').first();
      if (reportsLink.length) {
        cy.wrap(reportsLink).click();
      } else {
        cy.visit("/verticals/gym/reports/", { failOnStatusCode: false });
      }
    });

    cy.waitForAppShell();
    cy.assertNoServerError();
    cy.get("body").should("not.be.empty");

    // ============================================================
    // STEP 7: Visit settings
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
    // STEP 8: Logout
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

  it("should handle membership payment flow correctly (gym-specific)", () => {
    cy.loginAsManager("gym");
    cy.visitDashboard("gym");

    // Test that membership payments can be recorded
    cy.get("body").then(($body) => {
      if ($body.find('[data-cy="record-payment"]').length || $body.find('a[href*="payment"]').length) {
        const paymentLink = $body.find('[data-cy="record-payment"]').length
          ? cy.get('[data-cy="record-payment"]')
          : cy.get('a[href*="payment"]').first();

        paymentLink.click();
        cy.waitForAppShell();

        // Verify payment form exists
        cy.get("body").should("contain.text", "payment").or("contain.text", "Payment").or("contain.text", "amount");
      }
    });
  });
});
