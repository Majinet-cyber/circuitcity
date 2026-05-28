/**
 * TengaSale Cypress E2E — HQ Command Center
 * Tests /hq/ dashboard, reports, simulations
 */
describe("HQ Command Center", () => {
  beforeEach(() => {
    cy.loginAsHQ();
  });

  it("HQ can access dashboard", () => {
    cy.visit("/tengasale/hq/");
    cy.get('[data-testid="hq-dashboard"]').should("exist");
    cy.contains("TengaSale").should("be.visible");
  });

  it("HQ dashboard has no Yellow references", () => {
    cy.visit("/tengasale/hq/");
    cy.get("body").invoke("text").then((text) => {
      expect(text).not.to.include("Yellow Africa");
      expect(text).not.to.include("KulaSell");
    });
  });

  it("HQ can access commissions", () => {
    cy.visit("/tengasale/hq/commissions/");
    cy.contains("Commission").should("be.visible");
  });

  it("HQ can access merchant payouts", () => {
    cy.visit("/tengasale/hq/merchant-payouts/");
    cy.contains("Merchant").should("be.visible");
  });

  it("HQ can access reports", () => {
    cy.visit("/tengasale/hq/reports/");
    cy.contains("Reports").should("be.visible");
  });

  it("HQ can access simulations", () => {
    cy.visit("/tengasale/hq/simulations/");
    cy.contains("Simulation").should("be.visible");
  });

  it("HQ simulation form has required fields", () => {
    cy.visit("/tengasale/hq/simulations/");
    cy.get("input[name='cash_price'], input[name='selling_total']").should("exist");
  });
});

describe("HQ — Access Control", () => {
  it("non-HQ user cannot access HQ dashboard", () => {
    cy.loginAsMerchant();
    cy.visit("/tengasale/hq/");
    cy.url().should("not.include", "/tengasale/hq/");
  });

  it("unauthenticated user cannot access HQ dashboard", () => {
    cy.clearCookies();
    cy.visit("/tengasale/hq/");
    cy.url().should("include", "/login/");
  });
});
