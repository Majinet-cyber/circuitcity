const VERTICAL = "pharmacy";

function visitFast(url, opts = {}) {
  return cy.visit(url, { waitUntil: "domcontentloaded", ...opts });
}

describe("Pharmacy - Smoke", () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
    cy.loginAsOwner();
  });

  it("dashboard loads", () => {
    visitFast(`/verticals/${VERTICAL}/dashboard/`);
    cy.contains(/(pharmacy|dashboard)/i).should("exist");
  });

  it("no sidebar links should 500 (pharmacy-only)", () => {
    visitFast(`/verticals/${VERTICAL}/dashboard/`);

    cy.get("body").then(($body) => {
      const hrefs = Array.from($body.find(`a[href*='/verticals/${VERTICAL}/']`))
        .map((a) => a.getAttribute("href"))
        .filter(Boolean);

      const unique = [...new Set(hrefs)];

      cy.wrap(unique).each((href) => {
        cy.request({ url: href, failOnStatusCode: false }).then((res) => {
          expect(res.status, `GET ${href}`).to.be.lessThan(500);
        });
      });
    });
  });
});
