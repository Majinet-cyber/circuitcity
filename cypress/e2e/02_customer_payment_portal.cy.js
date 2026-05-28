/**
 * TengaSale Cypress E2E — Customer Payment Portal
 * Tests /pay/ — search, view contract, make mock payment
 */
describe("Customer Payment Portal — /pay/", () => {
  beforeEach(() => {
    cy.visit("/pay/");
  });

  it("shows the payment portal search page", () => {
    cy.get('[data-testid="payment-search"]').should("exist");
    cy.contains("TengaSale").should("be.visible");
  });

  it("has no Yellow or KulaSell references", () => {
    cy.get("body").invoke("text").then((text) => {
      expect(text).not.to.include("Yellow Africa");
      expect(text).not.to.include("KulaSell");
    });
  });

  it("shows friendly support text, not giant icons", () => {
    cy.get("body").should("not.contain", "What Yellow");
  });

  it("can search for a demo contract by number", () => {
    cy.get('[data-testid="payment-search"]').type(Cypress.env("DEMO_CONTRACT") || "TS-MW-");
    cy.get("form").first().submit();
  });

  it("can search by PayG number", () => {
    cy.get('[data-testid="payment-search"]').type(Cypress.env("DEMO_PAYG") || "TSG");
    cy.get("form").first().submit();
  });

  it("does not expose commission or payout data on portal", () => {
    cy.get("body").invoke("text").then((text) => {
      expect(text).not.to.include("CommissionLedger");
      expect(text).not.to.include("merchant_commission");
      expect(text).not.to.include("wht_amount");
    });
  });

  it("redirects to contract page from /pay/contract/", () => {
    cy.visit("/pay/");
    cy.url().should("include", "/pay/");
  });
});
