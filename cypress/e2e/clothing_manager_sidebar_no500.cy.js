// cypress/e2e/clothing_manager_sidebar_no500.cy.js

function visitFast(url, opts = {}) {
  return cy.visit(url, {
    failOnStatusCode: false,
    waitUntil: "domcontentloaded",
    timeout: 120000,
    ...opts,
  });
}

function assertNoServerError() {
  cy.get("body").should("not.contain", "Server Error (500)");
  cy.get("body").should("not.contain", "Traceback");
}

function numFromText(text) {
  const m = String(text).match(/(\d+)/);
  return m ? parseInt(m[1], 10) : null;
}

function fillFirstExisting(selectors, value) {
  return cy.get("body").then(($body) => {
    const sel = selectors.find((s) => $body.find(s).filter(":visible").length);
    if (!sel) throw new Error(`Could not find field. Tried: ${selectors.join(", ")}`);

    cy.get(sel)
      .filter(":visible")
      .first()
      .scrollIntoView()
      .should("be.visible")
      .clear({ force: true })
      .type(String(value), { force: true });
  });
}

function fillByLabel(labelRe, value) {
  cy.contains("label", labelRe, { timeout: 20000 }).then(($label) => {
    const forId = $label.attr("for");
    if (forId) {
      cy.get(`#${forId}`)
        .scrollIntoView()
        .should("be.visible")
        .clear({ force: true })
        .type(String(value), { force: true });
      return;
    }

    cy.wrap($label)
      .parent()
      .find("input, textarea, select")
      .filter(":visible")
      .first()
      .scrollIntoView()
      .should("be.visible")
      .clear({ force: true })
      .type(String(value), { force: true });
  });
}

function clickSubmitSmart() {
  cy.get("body").then(($b) => {
    const $submit = $b.find("button[type='submit'], input[type='submit']");
    if ($submit.length) {
      cy.wrap($submit.last()).scrollIntoView().click({ force: true });
      return;
    }

    cy.contains("button, input", /Complete|Confirm|Sell|Finish|Record|Submit|Save/i, {
      timeout: 20000,
    })
      .last()
      .scrollIntoView()
      .click({ force: true });
  });
}

/**
 * Scope to the "Choose an Item to Sell" section (avoids matching in Recent Sales)
 */
function withinChooseItemSection(cb) {
  cy.contains(/Choose an Item to Sell/i, { timeout: 20000 }).then(($h) => {
    const $ = Cypress.$;
    const $anc = $h.parents();
    let $root = null;

    for (let i = 0; i < $anc.length; i++) {
      const el = $anc[i];
      const txt = el?.innerText || "";
      if (/Continue to Details/i.test(txt) && /Stock/i.test(txt)) {
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
    .invoke("text")
    .then((t) => {
      // supports: "Stock: 6 units" OR "Stock 6" OR "6 units"
      const m1 = String(t).match(/stock\s*[:\-]?\s*(\d+)/i);
      const m2 = String(t).match(/(\d+)\s*units?/i);
      const n = m1 ? parseInt(m1[1], 10) : m2 ? parseInt(m2[1], 10) : null;

      expect(n, `stock number parsed from card:\n${t}`).to.be.a("number");
      return n;
    });
}

function waitForStockToDecrease({ pickSuit, beforeStock, maxRetries = 6, delayMs = 1200 }) {
  let attempt = 0;

  function tick() {
    attempt += 1;
    cy.log(`🔁 Stock decrease check ${attempt}/${maxRetries}`);

    visitFast("/verticals/clothing/sell/");
    cy.waitForAppShell();
    assertNoServerError();

    withinChooseItemSection(() => {
      cy.get(".product-card", { timeout: 20000 })
        .filter(":visible")
        .should("have.length.greaterThan", 0)
        .then(($cards) => {
          const cardsArr = Array.from($cards);
          const suitEl = pickSuit ? cardsArr.find((el) => /Suit/i.test(el.innerText || "")) : null;
          const target = suitEl ? suitEl : cardsArr[0];

          readStockFromCard(target).then((current) => {
            cy.log(`📦 Stock now: ${current} (before: ${beforeStock})`);

            if (current < beforeStock) {
              expect(current, "stock should decrease after sale").to.be.lessThan(beforeStock);
              return;
            }

            if (attempt < maxRetries) {
              cy.wait(delayMs);
              tick();
              return;
            }

            expect(current, `stock should decrease after sale (after ${maxRetries} retries)`).to.be.lessThan(
              beforeStock
            );
          });
        });
    });
  }

  tick();
}

describe("Clothing: Add Stock → Sell one unit (cash) → stock decreases", () => {
  const ADD_QTY = 11;
  const COST = 200000;
  const STOCK_SELLING_PRICE = 300000; // scan-in (optional)
  const SALE_PRICE = 500000; // on Complete Sale page

  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();

    // ✅ keep your working clothing login
    cy.loginAsManager("clothing");

    // ✅ IMPORTANT: bypass cy.visitDashboard("clothing") (it uses cy.request and times out)
    visitFast("/verticals/clothing/dashboard/");
    cy.waitForAppShell();
    cy.contains("This page is only available for clothing businesses").should("not.exist");
    assertNoServerError();
  });

  it("adds stock then sells one unit (cash) and stock decreases", () => {
    // 1) Scan IN (leave size/color as-is)
    visitFast("/verticals/clothing/scan-in/");
    cy.waitForAppShell();
    assertNoServerError();

    // Prefer Suit category if present
    let pickSuit = false;
    cy.get("body").then(($b) => {
      pickSuit = /\bSuit\b/i.test($b.text());
      if (pickSuit) {
        cy.contains(/^Suit$/i).click({ force: true });
      } else {
        cy.contains(/Dress|Shirt|Trousers|Shoes|Jacket|Skirt|Other/i)
          .first()
          .click({ force: true });
      }
    });

    // 🔥 remove invalid CSS4 selectors with ` i `
    fillFirstExisting(["#id_quantity", "#id_qty", "input[name='quantity']", "input[name='qty']"], ADD_QTY);

    fillFirstExisting(
      ["#id_cost_price", "#id_cost", "input[name='cost_price']", "input[name='cost']", "input[name='unit_cost']"],
      COST
    );

    fillFirstExisting(
      ["#id_selling_price", "#id_price", "input[name='selling_price']", "input[name='price']"],
      STOCK_SELLING_PRICE
    );

    cy.contains("button", /Add to Stock/i).scrollIntoView().click({ force: true });
    assertNoServerError();

    // 2) SELL: pick Suit card if present, otherwise first card
    visitFast("/verticals/clothing/sell/");
    cy.waitForAppShell();
    assertNoServerError();

    withinChooseItemSection(() => {
      cy.get(".product-card", { timeout: 20000 })
        .should("have.length.greaterThan", 0)
        .then(($cards) => {
          const cardsArr = Array.from($cards);
          const suitEl = pickSuit ? cardsArr.find((el) => /Suit/i.test(el.innerText || "")) : null;
          const target = suitEl ? suitEl : cardsArr[0];

          readStockFromCard(target).then((n) => cy.wrap(n).as("stockAfterAdd"));
          cy.wrap(target).click({ force: true });
        });
    });

    cy.contains("button, a", /Continue to Details/i, { timeout: 20000 })
      .scrollIntoView()
      .click({ force: true });

    cy.contains(/Complete the Sale/i, { timeout: 20000 }).should("be.visible");
    assertNoServerError();

    // 3) Set selling price = 500,000 then submit (leave payment as default Cash)
    fillByLabel(/Selling Price/i, SALE_PRICE);
    clickSubmitSmart();

    cy.contains(/Choose an Item to Sell/i, { timeout: 20000 }).should("exist");
    assertNoServerError();

    // 4) Verify stock decreased (retry)
    cy.get("@stockAfterAdd").then((afterAdd) => {
      waitForStockToDecrease({
        pickSuit,
        beforeStock: Number(afterAdd),
        maxRetries: 6,
        delayMs: 1200,
      });
    });
  });
});
