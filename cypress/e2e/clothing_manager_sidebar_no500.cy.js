describe("Clothing (Manager) sidebar smoke: no 500s", () => {
  const WAIT_MS = 10000;

  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();

    // Prefer manager creds if present, otherwise fall back to owner creds
    const creds = Cypress.env("CREDS") || {};
    const role = creds?.clothing?.manager ? "manager" : "owner";

    cy.loginAs("clothing", role);

    cy.visit("/verticals/clothing/dashboard/", { failOnStatusCode: false });
    cy.get("body").should("not.contain", "A server error occurred");
    cy.get("body").should("not.contain", "Server Error (500)");
  });

  it("visits every sidebar route and confirms no HTTP 500", () => {
    cy.sidebarHrefs().then((hrefs) => {
      expect(hrefs.length, "sidebar href count").to.be.greaterThan(0);

      cy.wrap(hrefs, { log: false }).each((href) => {
        // 1) Hard check: HTTP status must not be 500
        cy.request({
          url: href,
          failOnStatusCode: false,
        }).then((resp) => {
          expect(resp.status, `GET ${href} status`).to.not.eq(500);
        });

        // 2) UI check: page should not show 500 error page text
        cy.visit(href, { failOnStatusCode: false });
        cy.wait(WAIT_MS);

        cy.get("body").should("not.contain", "A server error occurred");
        cy.get("body").should("not.contain", "Server Error (500)");
        cy.get("body").should("not.contain", "Traceback");
      });
    });
  });
});
