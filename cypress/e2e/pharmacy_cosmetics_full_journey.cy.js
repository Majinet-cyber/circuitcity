// cypress/e2e/pharmacy_cosmetics_full_journey.cy.js

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

function ensureNotLoggedOut() {
  return cy.location("pathname", { timeout: 20000 }).then((p) => {
    if (String(p).includes("/accounts/login")) {
      cy.log("⚠️ Redirected to login mid-test. Re-logging into PHARMACY...");
      cy.loginAsManager("pharmacy");
      visitFast("/verticals/pharmacy/dashboard/");
      cy.waitForAppShell?.();
      assertNoServerError();
      cy.location("pathname").should("not.include", "/accounts/login");
    }
  });
}

/**
 * Find a "label-ish" element by text, then fill/select the nearest input/select.
 * Works even if the UI uses <div class="form-label"> instead of <label>.
 */
function fillNearText(labelRe, value) {
  const labelSelectors = "label,.form-label,.fw-semibold,.small,.text-muted,div,span";

  return cy.get("body").then(($b) => {
    const candidates = $b.find(labelSelectors).toArray();
    const hit = candidates.find((el) => labelRe.test((el.innerText || "").replace(/\s+/g, " ").trim()));

    if (!hit) throw new Error(`Could not find field label matching: ${labelRe}`);

    const $hit = Cypress.$(hit);

    // 1) If it’s a real <label for="...">
    const forId = $hit.attr("for");
    if (forId && $b.find(`#${forId}`).length) {
      cy.get(`#${forId}`)
        .filter(":visible")
        .first()
        .scrollIntoView()
        .clear({ force: true })
        .type(String(value), { force: true });
      return;
    }

    // 2) Otherwise, find nearest input/select/textarea in same block
    const block = $hit.closest(".mb-3,.form-group,.field,div");
    const $field = block.find("input,textarea,select").filter(":visible").first();

    if ($field.length) {
      const tag = ($field.prop("tagName") || "").toLowerCase();
      if (tag === "select") {
        // for selects, value must be handled by select helper (use selectNearText)
        cy.wrap($field).then(() => {
          throw new Error(`fillNearText found a SELECT for ${labelRe}. Use selectNearText instead.`);
        });
        return;
      }

      cy.wrap($field)
        .scrollIntoView()
        .clear({ force: true })
        .type(String(value), { force: true });
      return;
    }

    throw new Error(`Found label for ${labelRe} but could not find nearest input/select/textarea.`);
  });
}

function selectNearText(labelRe, optionContainsText) {
  const labelSelectors = "label,.form-label,.fw-semibold,.small,.text-muted,div,span";

  return cy.get("body").then(($b) => {
    const candidates = $b.find(labelSelectors).toArray();
    const hit = candidates.find((el) => labelRe.test((el.innerText || "").replace(/\s+/g, " ").trim()));
    if (!hit) throw new Error(`Could not find select label matching: ${labelRe}`);

    const $hit = Cypress.$(hit);
    const block = $hit.closest(".mb-3,.form-group,.field,div");
    const $select = block.find("select").filter(":visible").first();

    if (!$select.length) throw new Error(`Found label for ${labelRe} but no visible <select> in same block.`);

    cy.wrap($select).then(($s) => {
      const opts = $s.find("option").toArray();
      const pick = opts.find((o) =>
        String(o.textContent || "")
          .toLowerCase()
          .includes(String(optionContainsText).toLowerCase())
      );
      if (!pick) throw new Error(`Could not find option containing "${optionContainsText}" for ${labelRe}`);
      cy.wrap($s).select(pick.value, { force: true });
    });
  });
}

/**
 * Fallback: fill an input by placeholder substring (case-insensitive) OR by name/id includes.
 */
function fillSmart({ labelRe, placeholderIncludes = [], nameOrIdIncludes = [], value }) {
  return cy.get("body").then(($b) => {
    // Try label-first (most reliable)
    try {
      return fillNearText(labelRe, value);
    } catch (e) {
      // continue to fallback
    }

    // Fallback: scan visible inputs
    const inputs = $b.find("input,textarea").filter(":visible").toArray();

    const pick = inputs.find((el) => {
      const ph = (el.getAttribute("placeholder") || "").toLowerCase();
      const nm = (el.getAttribute("name") || "").toLowerCase();
      const id = (el.getAttribute("id") || "").toLowerCase();

      const okPH = placeholderIncludes.some((s) => ph.includes(String(s).toLowerCase()));
      const okNI = nameOrIdIncludes.some((s) => nm.includes(String(s).toLowerCase()) || id.includes(String(s).toLowerCase()));

      return okPH || okNI;
    });

    if (!pick) {
      throw new Error(
        `Could not find field for ${labelRe}. Tried label, placeholderIncludes=${JSON.stringify(
          placeholderIncludes
        )}, nameOrIdIncludes=${JSON.stringify(nameOrIdIncludes)}`
      );
    }

    cy.wrap(pick)
      .scrollIntoView()
      .clear({ force: true })
      .type(String(value), { force: true });
  });
}

function clickSidebar(labelRe) {
  ensureNotLoggedOut();
  cy.contains("a,button", labelRe, { timeout: 20000 })
    .filter(":visible")
    .first()
    .scrollIntoView()
    .click({ force: true });

  cy.waitForAppShell?.();
  assertNoServerError();
  ensureNotLoggedOut();
}

function fmtMMDDYYYY(d) {
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const yyyy = d.getFullYear();
  return `${mm}/${dd}/${yyyy}`;
}

function chooseAnyPaymentMix() {
  cy.get("body").then(($b) => {
    const selectSel = [
      "select[name='payment_mix']",
      "select#id_payment_mix",
      "select[name='payment_method']",
      "select#id_payment_method",
      "select[name='payment_type']",
      "select#id_payment_type",
    ].find((s) => $b.find(s).filter(":visible").length);

    if (selectSel) {
      cy.get(selectSel)
        .filter(":visible")
        .first()
        .then(($select) => {
          const opts = Array.from($select[0].options || []).filter(
            (o) => o.value && !/select/i.test(o.text || "")
          );
          if (opts.length) cy.wrap($select).select(opts[0].value, { force: true });
        });
      return;
    }

    const radio = $b.find("input[type='radio']").filter(":visible");
    if (radio.length) {
      cy.wrap(radio.first()).check({ force: true });
      return;
    }

    // fallback: click any visible payment button/tab
    const btn = $b
      .find("button,a")
      .filter(":visible")
      .toArray()
      .find((el) => {
        const t = (el.innerText || "").toLowerCase();
        return t.includes("cash") || t.includes("mixed") || t.includes("mpamba") || t.includes("airtel") || t.includes("card");
      });
    if (btn) cy.wrap(btn).click({ force: true });
  });
}

describe("Pharmacy: Dashboard → Stock In → Dashboard → Sell (Skin Care)", () => {
  it("adds stock then sells it", () => {
    cy.clearCookies();
    cy.clearLocalStorage();

    // ✅ vertical-aware login (same as gym)
    cy.loginAsManager("pharmacy");

    // 1) Dashboard and wait 10s
    visitFast("/verticals/pharmacy/dashboard/");
    cy.waitForAppShell?.();
    assertNoServerError();
    ensureNotLoggedOut();
    cy.wait(10000);

    // 2) Stock In
    clickSidebar(/stock\s*in/i);
    cy.location("pathname", { timeout: 20000 }).should("include", "/pharmacy/stock-in");

    const unique = Date.now();
    const productName = `Cypress Skin Care ${unique}`;
    const barcode = `BC-${unique}`;
    const supplier = `Supplier ${unique}`;

    const today = new Date();
    const manufacture = fmtMMDDYYYY(today);

    const nextYearDec20 = new Date(today);
    nextYearDec20.setFullYear(today.getFullYear() + 1);
    nextYearDec20.setMonth(11, 20); // Dec 20
    const expiry = fmtMMDDYYYY(nextYearDec20);

    // --- Fill Stock In Form (based on your UI labels) ---

    // Product Name (this was failing — now filled by label/nearest input)
    fillSmart({
      labelRe: /product\s*name/i,
      placeholderIncludes: ["paracetamol", "product"],
      nameOrIdIncludes: ["product", "name", "title"],
      value: productName,
    });

    // SKU / Barcode
    fillSmart({
      labelRe: /(sku|barcode)/i,
      placeholderIncludes: ["optional", "barcode", "sku"],
      nameOrIdIncludes: ["barcode", "sku"],
      value: barcode,
    });

    // Category = Skin Care
    selectNearText(/category/i, "Skin Care");

    // Quantity = 20
    fillSmart({
      labelRe: /^quantity/i,
      placeholderIncludes: [],
      nameOrIdIncludes: ["quantity", "qty"],
      value: "20",
    });

    // Manufacture Date = today
    fillSmart({
      labelRe: /manufacture\s*date/i,
      placeholderIncludes: ["mm/dd/yyyy"],
      nameOrIdIncludes: ["manufacture"],
      value: manufacture,
    });

    // Expiry Date = Dec 20 next year
    fillSmart({
      labelRe: /expiry\s*date/i,
      placeholderIncludes: ["mm/dd/yyyy"],
      nameOrIdIncludes: ["expiry"],
      value: expiry,
    });

    // Cost Price
    fillSmart({
      labelRe: /cost\s*price/i,
      placeholderIncludes: ["0.00"],
      nameOrIdIncludes: ["cost"],
      value: "70000",
    });

    // Selling Price
    fillSmart({
      labelRe: /selling\s*price/i,
      placeholderIncludes: ["0.00"],
      nameOrIdIncludes: ["sell"],
      value: "120000",
    });

    // Supplier
    fillSmart({
      labelRe: /supplier/i,
      placeholderIncludes: ["supplier"],
      nameOrIdIncludes: ["supplier"],
      value: supplier,
    });

    // Batch Number (required on your form)
    fillSmart({
      labelRe: /batch\s*number/i,
      placeholderIncludes: ["bt-"],
      nameOrIdIncludes: ["batch"],
      value: `BT-${unique}`,
    });

    // Add to Stock
    cy.contains("button", /add\s*to\s*stock/i, { timeout: 20000 })
      .filter(":visible")
      .scrollIntoView()
      .click({ force: true });

    cy.waitForAppShell?.();
    assertNoServerError();
    ensureNotLoggedOut();

    // 3) Back to Dashboard and wait 10s
    clickSidebar(/pharmacy\s*dashboard/i);
    cy.wait(10000);

    // 4) Sell
    clickSidebar(/^sell$/i);

    // pick the product we added (search if exists)
    cy.get("body").then(($b) => {
      const search = $b.find("input[type='search'], input[name='search'], input[placeholder*='Search']").filter(":visible");
      if (search.length) {
        cy.wrap(search.first()).clear({ force: true }).type(productName, { force: true });
      }
    });

    // click product card/row containing productName
    cy.contains(
      "[data-cy='product-card'], .product-card, .card, tr, td, a, button, div",
      productName,
      { timeout: 20000 }
    )
      .scrollIntoView()
      .click({ force: true });

    cy.waitForAppShell?.();
    assertNoServerError();
    ensureNotLoggedOut();

    // quantity = 2
    cy.get("body").then(($b) => {
      const qtySel = ["#id_quantity", "input[name='quantity']", "#id_qty", "input[name='qty']"].find(
        (s) => $b.find(s).filter(":visible").length
      );
      if (qtySel) cy.get(qtySel).filter(":visible").first().clear({ force: true }).type("2", { force: true });
    });

    // selling price = 120000
    cy.get("body").then(($b) => {
      const priceSel = ["#id_selling_price", "input[name='selling_price']", "#id_price", "input[name='price']"].find(
        (s) => $b.find(s).filter(":visible").length
      );
      if (priceSel) cy.get(priceSel).filter(":visible").first().clear({ force: true }).type("120000", { force: true });
    });

    // choose any payment mix
    chooseAnyPaymentMix();

    // complete sale
    cy.get("body").then(($b) => {
      const hasDataCy = $b.find("button[data-cy='complete-sale']").filter(":visible").length > 0;
      if (hasDataCy) {
        cy.get("button[data-cy='complete-sale']").first().click({ force: true });
      } else {
        cy.contains("button,a,input[type='submit']", /(sell|complete|confirm|finish|record)/i, { timeout: 20000 })
          .filter(":visible")
          .first()
          .scrollIntoView()
          .click({ force: true });
      }
    });

    cy.waitForAppShell?.();
    assertNoServerError();
    ensureNotLoggedOut();

    // success
    cy.contains("body", /(success|completed|receipt|sold)/i, { timeout: 20000 }).should("be.visible");
  });
});
