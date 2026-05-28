/**
 * TengaSale Cypress E2E — Merchant Flow
 * Tests merchant application submission flow
 */
describe("Merchant Flow", () => {
  beforeEach(() => {
    cy.loginAsMerchant();
  });

  it("merchant can access their dashboard", () => {
    cy.visit("/tengasale/merchant/");
    cy.get("body").should("be.visible");
    cy.contains("Merchant").should("be.visible");
  });

  it("merchant can view applications list", () => {
    cy.visit("/applications/active/");
    cy.get("body").should("be.visible");
  });

  it("merchant can start a new application", () => {
    cy.visit("/applications/new/");
    cy.get("body").should("be.visible");
  });

  it("merchant dashboard shows no underwriter commission data", () => {
    cy.visit("/tengasale/merchant/");
    cy.get("body").invoke("text").then((text) => {
      expect(text).not.to.include("underwriter_commission");
      expect(text).not.to.include("arrears_deduction");
      expect(text).not.to.include("wht_amount");
    });
  });

  it("merchant cannot access /sales/", () => {
    cy.visit("/sales/", { failOnStatusCode: false });
    cy.url().should("not.include", "/sales/");
  });

  it("merchant cannot access HQ dashboard", () => {
    cy.visit("/tengasale/hq/", { failOnStatusCode: false });
    cy.url().should("not.include", "/tengasale/hq/");
  });

  it("merchant sees no Yellow or KulaSell branding", () => {
    cy.visit("/tengasale/merchant/");
    cy.get("body").invoke("text").then((text) => {
      expect(text).not.to.include("KulaSell");
      expect(text).not.to.include("Yellow Africa");
    });
  });
});
