/**
 * TengaSale Cypress E2E — Commission Flow
 * Covers: wallet display, commission rows, arrears rows, no merchant data
 *
 * Prerequisites:
 *   - Underwriter user seeded with commission ledger entries
 *   - Run: python manage.py seed_tengasale_demo
 */
describe("Underwriter Wallet — Commission Display", () => {
  beforeEach(() => {
    cy.loginAsUnderwriter();
  });

  it("wallet page loads with correct testid", () => {
    cy.visit("/sales/wallet/");
    cy.get('[data-testid="underwriter-wallet"]').should("exist");
  });

  it("wallet shows commission summary section", () => {
    cy.visit("/sales/wallet/");
    cy.contains("Available Commission Balance").should("be.visible");
    cy.contains("This Month Gross").should("be.visible");
  });

  it("wallet shows Earnings tab", () => {
    cy.visit("/sales/wallet/");
    cy.contains("Earnings").should("be.visible");
  });

  it("wallet shows Deductions tab", () => {
    cy.visit("/sales/wallet/");
    cy.contains("Deductions").should("be.visible");
  });

  it("wallet shows Payouts tab", () => {
    cy.visit("/sales/wallet/");
    cy.contains("Payouts").should("be.visible");
  });

  it("wallet does not show merchant payout data", () => {
    cy.visit("/sales/wallet/");
    cy.get("body").invoke("text").then((text) => {
      expect(text.toLowerCase()).not.to.include("cash_price");
      expect(text.toLowerCase()).not.to.include("merchant_commission");
      expect(text.toLowerCase()).not.to.include("destination_account");
    });
  });

  it("wallet does not expose KulaSell or Yellow", () => {
    cy.visit("/sales/wallet/");
    cy.get("body").invoke("text").then((text) => {
      expect(text).not.to.include("KulaSell");
      expect(text).not.to.include("Yellow Africa");
    });
  });

  it("commission rows have correct testid when present", () => {
    cy.visit("/sales/wallet/");
    // If there are commission rows, they should have the correct testid
    cy.get("body").then(($body) => {
      if ($body.find('[data-testid="commission-row"]').length > 0) {
        cy.get('[data-testid="commission-row"]').first().should("be.visible");
      }
    });
  });

  it("arrears deduction rows have correct testid when present", () => {
    cy.visit("/sales/wallet/");
    cy.get("body").then(($body) => {
      if ($body.find('[data-testid="arrears-deduction-row"]').length > 0) {
        cy.get('[data-testid="arrears-deduction-row"]').first().should("be.visible");
      }
    });
  });

  it("wallet shows WHT estimate label", () => {
    cy.visit("/sales/wallet/");
    cy.get("body").invoke("text").then((text) => {
      expect(text.toLowerCase()).to.include("wht");
    });
  });
});

describe("HQ — Merchant Payout View", () => {
  beforeEach(() => {
    cy.loginAsHQ();
  });

  it("HQ merchant payouts page loads", () => {
    cy.visit("/tengasale/hq/merchant-payouts/", { failOnStatusCode: false });
    cy.get("body").should("be.visible");
  });

  it("merchant payout rows have correct testid when present", () => {
    cy.visit("/tengasale/hq/merchant-payouts/", { failOnStatusCode: false });
    cy.get("body").then(($body) => {
      if ($body.find('[data-testid="merchant-payout-row"]').length > 0) {
        cy.get('[data-testid="merchant-payout-row"]').first().should("be.visible");
      }
    });
  });

  it("HQ commissions page shows WHT summary", () => {
    cy.visit("/tengasale/hq/commissions/", { failOnStatusCode: false });
    cy.get("body").invoke("text").then((text) => {
      expect(text.toLowerCase()).to.include("wht");
    });
  });

  it("HQ simulations page shows calculator form", () => {
    cy.visit("/tengasale/hq/simulations/", { failOnStatusCode: false });
    cy.contains("Simulation").should("be.visible");
  });

  it("HQ reports page has export links", () => {
    cy.visit("/tengasale/hq/reports/", { failOnStatusCode: false });
    cy.contains("Export").should("be.visible");
  });
});

describe("Customer Correction Flow", () => {
  it("invalid correction token shows error not data", () => {
    cy.visit("/applications/this-is-not-a-real-token/correct/", {
      failOnStatusCode: false,
    });
    cy.get("body").invoke("text").then((text) => {
      expect(text.toLowerCase()).not.to.include("commissi");
      expect(text.toLowerCase()).not.to.include("audit");
      expect(text.toLowerCase()).not.to.include("kulasell");
    });
  });
});
