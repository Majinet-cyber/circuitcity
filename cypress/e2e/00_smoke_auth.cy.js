// cypress/e2e/00_smoke_auth.cy.js
/**
 * Smoke test for authentication across all verticals.
 * Tests that login works correctly per vertical (shared auth but different routes/nav).
 */
describe("Authentication Smoke Test", () => {
  const verticals = ["phones", "clothing", "liquor", "pharmacy", "gym"];

  verticals.forEach((vertical) => {
    it(`should login as manager for ${vertical} vertical`, () => {
      cy.loginAsManager(vertical);

      // Verify we're logged in (not on login page)
      cy.url().should("not.include", "/accounts/login/");

      // Verify app shell is loaded
      cy.waitForAppShell();

      // Verify no server errors
      cy.assertNoServerError();
    });
  });

  it("should handle login failure gracefully", () => {
    cy.visit("/accounts/login/");

    // Try invalid credentials
    cy.get('input[name="username"], input[name="email"], [data-cy=login-email]')
      .first()
      .type("invalid@test.com");

    cy.get('input[name="password"], [data-cy=login-password]')
      .first()
      .type("wrongpassword", { log: false });

    cy.get('button[type="submit"], [data-cy=login-submit]')
      .first()
      .click();

    // Should stay on login page or show error
    cy.url().then((url) => {
      // Either still on login page or redirected with error
      if (url.includes("/accounts/login/")) {
        // Check for error message
        cy.get("body").should("contain.text", "error").or("contain.text", "invalid").or("contain.text", "incorrect");
      }
    });
  });

  it("should logout successfully", () => {
    cy.loginAsManager("phones");

    // Find and click logout
    cy.get("body").then(($body) => {
      const logoutLink = $body.find('a[href*="logout"], [data-cy="logout"]').first();
      if (logoutLink.length) {
        cy.wrap(logoutLink).click();
      } else {
        // Try visiting logout URL directly
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
});
