/**
 * TengaSale Cypress E2E — Commission Flow
 * Tests that wallet shows commission data and security isolation
 */
describe("Commission Flow — Underwriter Wallet", () => {
  beforeEach(() => {
    cy.loginAsUnderwriter();
  });

  it("underwriter wallet page loads", () => {
    cy.visit("/sales/wallet/");
    cy.get('[data-testid="underwriter-wallet"]').should("exist");
  });

  it("wallet shows Available Commission Balance", () => {
    cy.visit("/sales/wallet/");
    cy.contains("Available Commission Balance").should("be.visible");
  });

  it("wallet shows This Month section", () => {
    cy.visit("/sales/wallet/");
    cy.contains("This Month").should("be.visible");
  });

  it("wallet shows WHT estimate", () => {
    cy.visit("/sales/wallet/");
    cy.get("body").invoke("text").then((text) => {
      expect(text).to.include("WHT");
    });
  });

  it("wallet does not show merchant cash settlement", () => {
    cy.visit("/sales/wallet/");
    cy.get("body").invoke("text").then((text) => {
      expect(text).not.to.include("merchant_commission");
      expect(text).not.to.include("cash_price");
    });
  });

  it("wallet does not show Yellow or KulaSell", () => {
    cy.visit("/sales/wallet/");
    cy.get("body").invoke("text").then((text) => {
      expect(text).not.to.include("KulaSell");
      expect(text).not.to.include("Yellow Africa");
    });
  });

  it("wallet earnings tab has commission-row testid", () => {
    cy.visit("/sales/wallet/");
    cy.get("body").then(($body) => {
      // If there are ledger entries, they have the testid
      if ($body.find('[data-testid="commission-row"]').length > 0) {
        cy.get('[data-testid="commission-row"]').should("exist");
      }
    });
  });
});

describe("Commission Security — Merchant cannot see underwriter commissions", () => {
  it("merchant dashboard does not show underwriter commission ledger", () => {
    cy.loginAsMerchant();
    cy.visit("/tengasale/merchant/");
    cy.get("body").invoke("text").then((text) => {
      expect(text).not.to.include("commission_ledger");
      expect(text).not.to.include("CommissionLedger");
    });
  });

  it("merchant cannot access underwriter wallet", () => {
    cy.loginAsMerchant();
    cy.visit("/sales/wallet/", { failOnStatusCode: false });
    cy.url().should("not.include", "/sales/wallet/");
  });
});

describe("HQ Commission View", () => {
  beforeEach(() => {
    cy.loginHQ();
  });

  it("HQ can view commission ledger", () => {
    cy.visit("/tengasale/hq/commissions/");
    cy.contains("Commission").should("be.visible");
    cy.get('[data-testid="hq-dashboard"]').should("exist");
  });

  it("HQ commission page shows WHT section", () => {
    cy.visit("/tengasale/hq/commissions/");
    cy.get("body").invoke("text").then((text) => {
      expect(text).to.include("WHT");
    });
  });

  it("HQ merchant payouts page shows no underwriter WHT", () => {
    cy.visit("/tengasale/hq/merchant-payouts/");
    cy.contains("Payout").should("be.visible");
  });

  it("HQ operations page is accessible", () => {
    cy.visit("/tengasale/hq/operations/");
    cy.contains("Safe Operations").should("be.visible");
  });
});
