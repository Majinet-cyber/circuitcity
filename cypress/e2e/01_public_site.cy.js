/**
 * TengaSale Cypress E2E — Public Site
 * Tests visitor/public facing pages at /site/
 */
describe("Public Site — Visitor", () => {
  it("visits landing page and sees professional TengaSale content", () => {
    cy.visit("/site/");
    cy.contains("TengaSale").should("be.visible");
    cy.contains("Malawi").should("be.visible");
    cy.get("title").should("contain", "TengaSale");
  });

  it("has no Yellow or KulaSell branding visible", () => {
    cy.visit("/site/");
    cy.get("body").invoke("text").then((text) => {
      expect(text).not.to.include("Yellow Africa");
      expect(text).not.to.include("KulaSell");
      expect(text).not.to.include("kulasell");
    });
  });

  it("shows legal links in footer", () => {
    cy.visit("/site/");
    cy.get("a").contains(/Terms|Privacy/).should("exist");
  });

  it("Make Payment link goes to /pay/", () => {
    cy.visit("/site/");
    cy.get("a[href*='/pay/']").first().should("exist");
  });

  it("visits terms page", () => {
    cy.visit("/site/terms/");
    cy.contains("TengaSale").should("be.visible");
    cy.get("body").invoke("text").then((text) => {
      expect(text).not.to.include("Yellow Africa");
    });
  });

  it("visits privacy policy page", () => {
    cy.visit("/site/privacy/");
    cy.contains("Privacy").should("be.visible");
  });
});
