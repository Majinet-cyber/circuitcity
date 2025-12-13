// cypress/e2e/gym_membership_numbers.cy.js

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
  const cleaned = String(text || "").replace(/,/g, "");
  const m = cleaned.match(/(\d+)/);
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

function clickSaveMember() {
  cy.contains("button", /Save Member/i, { timeout: 20000 })
    .scrollIntoView()
    .click({ force: true });
}

/**
 * Optional KPI read (won't fail the test if KPI cards aren't present)
 */
function maybeReadKpiByLabel(labelRe) {
  return cy.get("body").then(($body) => {
    const candidates = [".kpi-card", ".stat-card", ".dashboard-kpi", ".card", "[data-cy='kpi-card']"];

    for (const sel of candidates) {
      const $cards = $body.find(sel);
      if (!$cards.length) continue;

      const $match = $cards.filter((_, node) => {
        const t = (node.innerText || node.textContent || "").trim();
        return labelRe.test(t);
      });

      if ($match.length) {
        const n = numFromText($match.first().text());
        if (typeof n === "number") return n;
      }
    }
    return null;
  });
}

describe("Gym: Add Member → numbers move", () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();

    // ✅ uses your commands.js mapping (gym -> yuji@gmail.com)
    cy.loginAsManager("gym");

    // ✅ canonical dashboard (your URLconf: path("", name="dashboard"))
    visitFast("/gym/");
    cy.waitForAppShell();
    assertNoServerError();
  });

  it("adds a member and increases members count (and KPIs if present)", () => {
    const memberName = "Chris Jade";
    const phone = `099${Math.floor(1000000 + Math.random() * 9000000)}`;
    const email = `chris.jade.${Date.now()}@example.com`;

    // Baseline (strong): members list count
    let membersBefore = null;
    visitFast("/gym/members/");
    cy.waitForAppShell();
    assertNoServerError();

    cy.get("body").then(($b) => {
      // if table exists, count rows; otherwise fallback to any "Member" cards/list items
      const $rows = $b.find("table tbody tr");
      if ($rows.length) {
        membersBefore = $rows.length;
        return;
      }

      const $items = $b.find(".member-card, .member-item, li");
      membersBefore = $items.length || 0;
    });

    // Baseline KPIs (optional)
    let totalKpiBefore = null;
    visitFast("/gym/");
    cy.waitForAppShell();
    assertNoServerError();
    maybeReadKpiByLabel(/total\s+members/i).then((n) => (totalKpiBefore = n));

    // Add member
    visitFast("/gym/member/add/");
    cy.waitForAppShell();
    assertNoServerError();

    // ✅ Name + Phone use labels on your page
    fillByLabel(/^\s*Name\b/i, memberName);
    fillByLabel(/Phone\s*Number/i, phone);

    // ✅ Email has NO <label> in your UI (it's a plain text heading),
    // so fill it by selectors only.
    cy.get("body").then(($b) => {
      const hasEmail =
        $b.find("#id_email, input[name='email'], input[type='email'], input[placeholder*='Email']").filter(":visible")
          .length > 0;

      if (hasEmail) {
        fillFirstExisting(
          ["#id_email", "input[name='email']", "input[type='email']", "input[placeholder*='Email']"],
          email
        );
      }
    });

    clickSaveMember();
    cy.waitForAppShell();
    assertNoServerError();
