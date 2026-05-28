/**
 * TengaSale Cypress E2E — Security & Role Isolation
 * Tests that roles cannot access pages outside their permission scope
 */
describe("Security — Role Isolation", () => {
  it("customer/visitor cannot access /sales/", () => {
    cy.clearCookies();
    cy.visit("/sales/", { failOnStatusCode: false });
    cy.url().should("include", "/login/");
  });

  it("unauthenticated cannot access underwriter wallet", () => {
    cy.clearCookies();
    cy.visit("/sales/wallet/", { failOnStatusCode: false });
    cy.url().should("include", "/login/");
  });

  it("merchant cannot access HQ", () => {
    cy.loginAsMerchant();
    cy.visit("/tengasale/hq/", { failOnStatusCode: false });
    cy.url().should("not.include", "/tengasale/hq/");
  });

  it("public /pay/ does not expose internal field names", () => {
    cy.visit("/pay/");
    cy.get("body").invoke("text").then((text) => {
      expect(text).not.to.include("commission");
      expect(text).not.to.include("wht_amount");
      expect(text).not.to.include("national_id");
    });
  });

  it("invalid correction token returns error page", () => {
    cy.visit("/applications/invalid-token-xyz/correct/", { failOnStatusCode: false });
    cy.get("body").should("be.visible");
    cy.get("body").invoke("text").then((text) => {
      // Should show an error, not full application data
      expect(text).not.to.include("CommissionLedger");
      expect(text).not.to.include("AuditLog");
    });
  });
});

describe("Security — Masked Data on /pay/", () => {
  it("phone numbers are masked in portal", () => {
    cy.visit("/pay/");
    cy.get("body").invoke("text").then((text) => {
      // Should not show full 9-digit phone
      const fullPhonePattern = /\b\d{9}\b/;
      expect(fullPhonePattern.test(text)).to.be.false;
    });
  });
});
