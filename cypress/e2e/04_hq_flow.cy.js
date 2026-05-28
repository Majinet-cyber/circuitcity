// cypress/e2e/04_hq_flow.cy.js
// HQ dashboard flow tests

describe("HQ Command Center", () => {
  beforeEach(() => {
    cy.loginHQ();
  });

  it("accesses HQ dashboard", () => {
    cy.visit("/tengasale/hq/");
    cy.get('[data-testid="hq-dashboard"]').should("exist");
    cy.contains("HQ Command Center").should("be.visible");
  });

  it("HQ has KPIs visible", () => {
    cy.visit("/tengasale/hq/");
    cy.contains("Merchants").should("be.visible");
    cy.contains("Underwriters").should("be.visible");
  });

  it("can navigate to commissions page", () => {
    cy.visit("/tengasale/hq/commissions/");
    cy.contains("Commission").should("be.visible");
  });

  it("can navigate to merchant payouts page", () => {
    cy.visit("/tengasale/hq/merchant-payouts/");
    cy.contains("Payout").should("be.visible");
  });

  it("can navigate to reports page", () => {
    cy.visit("/tengasale/hq/reports/");
    cy.contains("Reports").should("be.visible");
  });

  it("can navigate to simulations page", () => {
    cy.visit("/tengasale/hq/simulations/");
    cy.contains("Simulation").should("be.visible");
  });

  it("HQ does not expose Yellow/KulaSell", () => {
    cy.visit("/tengasale/hq/");
    cy.get("body").should("not.contain.text", "KulaSell");
    cy.get("body").should("not.contain.text", "Yellow Africa");
  });
});
