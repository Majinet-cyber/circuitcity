// cypress/e2e/clothing_manager_sidebar_no500.cy.js

function numFromText(text) {
  const m = String(text).match(/(\d+)/);
  return m ? parseInt(m[1], 10) : null;
}

function fillFirstExisting(selectors, value) {
  return cy.get("body").then(($body) => {
    const sel = selectors.find((s) => $body.find(s).length);
    if (!sel) throw new Error(`Could not find field. Tried: ${selectors.join(", ")}`);
    cy.get(sel)
      .first()
      .scrollIntoView()
      .should("be.visible")
      .clear({ force: true })
      .type(String(value), { force: true });
  });
}

function withinChooseItemSection(cb) {
  cy.contains(/Choose an Item to Sell/i).then(($h) => {
    const $ = Cypress.$;
    const $anc = $h.parents();
    let $root = null;

    // pick an ancestor that contains Continue button + at least one Stock label
    for (let i = 0; i < $anc.length; i++) {
      const el = $anc[i];
      const txt = el?.innerText || "";
      if (/Continue to Details/i.test(txt) && /Stock:\s*\d+\s*units/i.test(txt)) {
        $root = $(el);
        break;
      }
    }

    if (!$root) $root = $h.closest("div");
    cy.wrap($root).within(cb);
  });
}

function readStockFromCard($cardLike) {
  return cy
    .wrap($cardLike)
    .contains(/Stock:\s*\d+\s*units/i)
    .invoke("text")
    .then((t) => {
      const n = numFromText(t);
      expect(n, "stock number parsed").to.be.a("number");
      return n;
    });
}

describe("Clothing: Add Stock → Sell FIRST item (cash) → stock decreases", () => {
  const ADD_QTY = 11;
  const COST = 200000;
  const PRICE = 300000;

  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();

    cy.loginAsManager("clothing");
    cy.visitDashboard("clothing");
    cy.contains("This page is only available for clothing businesses").should("not.exist");
  });

  it("adds stock then sells one unit (cash) and stock decreases", () => {
    // 1) Scan IN (leave size/color as-is)
    cy.visit("/verticals/clothing/scan-in/", { failOnStatusCode: false });
    cy.waitForAppShell();

    // Click any category (prefer Suit if present)
    cy.get("body").then(($b) => {
      if ($b.text().match(/\bSuit\b/i)) {
        cy.contains(/^Suit$/i).click({ force: true });
      } else {
        cy.contains(/Dress|Shirt|Trousers|Shoes|Jacket|Skirt|Other/i)
          .first()
          .click({ force: true });
      }
    });

    // Only fill quantity + prices
    fillFirstExisting(
      ["#id_quantity", "input[name='quantity']", "input[name*='quantity' i]", "input[name*='qty' i]"],
      ADD_QTY
    );
    fillFirstExisting(
      ["#id_cost_price", "#id_cost", "input[name*='cost_price' i]", "input[name*='cost' i]"],
      COST
    );
    fillFirstExisting(
      ["#id_selling_price", "#id_price", "input[name*='selling_price' i]", "input[name*='selling' i]", "input[name*='price' i]"],
      PRICE
    );

    cy.contains("button", /Add to Stock/i).click({ force: true });
    cy.assertNoServerError();

    // 2) SELL: pick FIRST card and continue
    cy.visit("/verticals/clothing/sell/", { failOnStatusCode: false });
    cy.waitForAppShell();

    withinChooseItemSection(() => {
      // ✅ DO NOT use cy.get("body") here (scoped). Just find cards directly.
      cy.get(".product-card", { timeout: 20000 })
        .should("have.length.greaterThan", 0)
        .first()
        .as("pickedCard");

      cy.get("@pickedCard").then(($card) => {
        readStockFromCard($card).then((n) => cy.wrap(n).as("stockAfterAdd"));
      });

      cy.get("@pickedCard").click({ force: true });
    });

    cy.contains("button, a", /Continue to Details/i)
      .scrollIntoView()
      .click({ force: true });

    cy.assertNoServerError();

    // 3) Complete sale (prefilled, just submit)
    cy.contains("button", /Complete|Confirm|Sell|Finish|Record/i)
      .scrollIntoView()
      .click({ force: true });

    cy.assertNoServerError();

    // 4) Back to SELL: verify FIRST card stock decreased
    cy.visit("/verticals/clothing/sell/", { failOnStatusCode: false });
    cy.waitForAppShell();

    withinChooseItemSection(() => {
      cy.get(".product-card", { timeout: 20000 })
        .should("have.length.greaterThan", 0)
        .first()
        .then(($card2) => {
          readStockFromCard($card2).then((afterSale) => {
            cy.get("@stockAfterAdd").then((afterAdd) => {
              expect(afterSale, "stock should decrease after sale").to.be.lessThan(Number(afterAdd));
            });
          });
        });
    });
  });
});
