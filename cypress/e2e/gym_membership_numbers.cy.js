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

function clickButtonByRegexList(regexList) {
  return cy.get("body").then(($b) => {
    const found = regexList.find((re) =>
      $b
        .find("button,a,input[type='submit']")
        .toArray()
        .some((el) => re.test((el.innerText || el.value || "").trim()))
    );
    if (!found) throw new Error(`Could not find button matching any of: ${regexList.map(String).join(", ")}`);

    cy.contains("button,a,input[type='submit']", found, { timeout: 20000 })
      .filter(":visible")
      .first()
      .scrollIntoView()
      .click({ force: true });
  });
}

/**
 * Click the "View" action for a member row reliably.
 * Works even if the button has icons/extra whitespace.
 */
function clickViewForMember(memberName) {
  // Find the row via the cell text (more reliable than tr contains)
  cy.contains("td,th", memberName, { timeout: 20000 })
    .closest("tr")
    .as("memberRow");

  cy.get("@memberRow").scrollIntoView();

  cy.get("@memberRow")
    .find("a,button")
    .filter(":visible")
    .then(($els) => {
      const list = Array.from($els);

      const pick = list.find((el) => {
        const t = (el.innerText || "").replace(/\s+/g, " ").trim();
        const aria = (el.getAttribute("aria-label") || "").trim();
        const title = (el.getAttribute("title") || "").trim();
        return /\bview\b/i.test(t) || /\bview\b/i.test(aria) || /\bview\b/i.test(title);
      });

      if (pick) {
        cy.wrap(pick).click({ force: true });
      } else {
        // Fallback: if for some reason text isn't present (icon-only),
        // click the first action button in the row
        cy.wrap($els.first()).click({ force: true });
      }
    });
}

/**
 * Select an option in a <select> whose visible text contains a substring (memberName)
 * If already selected correctly, do nothing.
 */
function selectOptionContains(selectSelectors, containsText) {
  return cy.get("body").then(($body) => {
    const sel = selectSelectors.find((s) => $body.find(s).filter(":visible").length);
    if (!sel) throw new Error(`Could not find select. Tried: ${selectSelectors.join(", ")}`);

    cy.get(sel)
      .filter(":visible")
      .first()
      .then(($select) => {
        const selectedText = ($select.find("option:selected").text() || "").trim();
        if (selectedText.includes(containsText)) return;

        const $opt = $select
          .find("option")
          .filter((_, o) => (o.textContent || "").includes(containsText))
          .first();

        if (!$opt.length) {
          throw new Error(`Could not find option containing "${containsText}" in select ${sel}`);
        }
        const val = $opt.attr("value");
        cy.wrap($select).select(val, { force: true });
      });
  });
}

function parseDateLoose(text) {
  if (!text) return null;
  const t = String(text).trim();

  const iso = t.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]));

  const dmy = t.match(/(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})/);
  if (dmy) return new Date(Number(dmy[3]), Number(dmy[2]) - 1, Number(dmy[1]));

  const native = new Date(t);
  if (!isNaN(native.getTime())) return native;

  return null;
}

function addDays(date, days) {
  const d = new Date(date.getTime());
  d.setDate(d.getDate() + days);
  d.setHours(0, 0, 0, 0);
  return d;
}

function daysBetween(a, b) {
  const one = new Date(a.getFullYear(), a.getMonth(), a.getDate()).getTime();
  const two = new Date(b.getFullYear(), b.getMonth(), b.getDate()).getTime();
  return Math.round((two - one) / (1000 * 60 * 60 * 24));
}

describe("Gym: Add Member → Add Payment → Mark as Paid → verify 30/30", () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();

    // ✅ gym login mapping
    cy.loginAsManager("gym");

    visitFast("/gym/");
    cy.waitForAppShell?.();
    assertNoServerError();
  });

  it("adds a member then records a payment and verifies membership numbers", () => {
    const unique = Date.now();
    const memberName = `Cypress Gym ${unique}`;
    const phone = `099${Math.floor(1000000 + Math.random() * 9000000)}`;
    const email = `cypress.gym.${unique}@example.com`;

    // 1) Members list
    visitFast("/gym/members/");
    cy.waitForAppShell?.();
    assertNoServerError();

    // 2) Add Member
    cy.contains("a,button", /add member/i, { timeout: 20000 })
      .filter(":visible")
      .first()
      .click({ force: true });

    cy.waitForAppShell?.();
    assertNoServerError();

    // 3) Fill form
    fillByLabel(/^\s*Name\b/i, memberName);
    fillByLabel(/Phone\s*Number/i, phone);

    // Email optional/unlabeled
    cy.get("body").then(($b) => {
      const hasEmail =
        $b
          .find("#id_email, input[name='email'], input[type='email'], input[placeholder*='Email']")
          .filter(":visible").length > 0;

      if (hasEmail) {
        fillFirstExisting(
          ["#id_email", "input[name='email']", "input[type='email']", "input[placeholder*='Email']"],
          email
        );
      }
    });

    // Save member
    clickButtonByRegexList([/Save Member/i, /^Save$/i, /Create/i, /Add/i]);

    cy.waitForAppShell?.();
    assertNoServerError();

    // 4) Back to members list and ensure member exists
    visitFast("/gym/members/");
    cy.waitForAppShell?.();
    assertNoServerError();

    cy.contains("body", memberName, { timeout: 20000 }).should("be.visible");

    // ✅ FIXED: click View reliably
    clickViewForMember(memberName);

    cy.waitForAppShell?.();
    assertNoServerError();

    // 5) On member detail: click Add Payment
    cy.contains("a,button", /add payment/i, { timeout: 20000 })
      .filter(":visible")
      .first()
      .click({ force: true });

    cy.waitForAppShell?.();
    assertNoServerError();

    cy.location("pathname", { timeout: 20000 }).should("include", "/gym/payment/add");

    // 6) Choose member in dropdown (if not preselected)
    // Try data-cy first, then fallback to other selectors
    selectOptionContains(
      ["select[data-cy='gym-payment-member']", "#id_member", "select[name='member']"],
      memberName
    );

    // 7) Membership amount = 55000 (for 30 days)
    fillFirstExisting(
      ["input[data-cy='gym-payment-membership-amount']", "#id_membership_amount", "input[name='membership_amount']"],
      "55000"
    );

    // 8) Select a trainer (Steve, Lester, or Philip)
    cy.get("body").then(($body) => {
      const trainerSelect = $body.find("select[data-cy='gym-payment-trainer']");
      if (trainerSelect.length > 0) {
        // Find an available trainer option (Steve, Lester, or Philip)
        cy.get("select[data-cy='gym-payment-trainer']").then(($select) => {
          const options = $select.find("option");
          let trainerFound = false;

          for (const opt of options) {
            const text = (opt.textContent || "").trim();
            if (text && text !== "No trainer" && text !== "---------") {
              // Select this trainer
              cy.get("select[data-cy='gym-payment-trainer']").select(opt.value, { force: true });
              trainerFound = true;
              break;
            }
          }

          if (!trainerFound) {
            cy.log("Warning: No trainers available in dropdown");
          }
        });
      }
    });

    // 9) Enter trainer fee = 15000
    fillFirstExisting(
      ["input[data-cy='gym-payment-trainer-fee']", "#id_trainer_fee", "input[name='trainer_fee']"],
      "15000"
    );

    // 10) Click MARK AS PAID using data-cy
    cy.get("button[data-cy='gym-payment-submit']").should("be.visible").click({ force: true });

    cy.waitForAppShell?.();
    assertNoServerError();

    // 11) Verify membership numbers (55,000 MWK should grant 30 days)
    // Expected: 55,000 / (55,000/30) = 30 days
    // Trainer fee of 15,000 should NOT add days (only membership amount counts)
    cy.contains("body", /30\s*\/\s*30/i, { timeout: 20000 }).should("be.visible");
    cy.contains("body", /Days Left/i, { timeout: 20000 });

    // Verify status badge shows "Active" (not "In Arrears")
    cy.get("body").then(($body) => {
      const statusText = $body.text();
      expect(statusText).to.match(/Active/i);
      expect(statusText).to.not.match(/In Arrears/i);
    });

    // Verify payment history shows total paid (55,000 membership + 15,000 trainer = 70,000)
    cy.get("body").then(($body) => {
      const text = $body.text();
      // Should contain 70,000 (total) OR show breakdown of membership + trainer
      // At minimum, should show the payment was recorded
      expect(text).to.match(/70,?000|55,?000.*15,?000/i);
    });

    // Next payment date exists and ~30 days from today (membership amount is 55,000 = 30 days)
    cy.contains("body", /Next Payment/i, { timeout: 20000 }).then(($el) => {
      const text = $el.closest("div,section,article,li,td,th,tr").text().trim();
      const dt = parseDateLoose(text);

      if (dt) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        // For 55,000 MWK membership amount at 55,000/30 days rate, expect 30 days
        const expected = addDays(today, 30);

        const diff = Math.abs(daysBetween(expected, dt));
        expect(diff, `Expected next payment ~30 days from today. Got ${dt}`).to.be.lte(2);
      }
    });

    // Optionally: visit dashboard and verify Trainers Ranking
    cy.log("Checking Trainers Ranking on dashboard...");
    visitFast("/gym/");
    cy.waitForAppShell?.();
    assertNoServerError();

    // Look for Trainers Ranking section
    cy.get("body").then(($body) => {
      const text = $body.text();
      // Dashboard should contain Trainers Ranking with at least 15,000 fees
      if (text.includes("Trainers Ranking") || text.includes("Trainer Performance")) {
        cy.contains("body", /15,?000/i, { timeout: 10000 }).should("be.visible");
      } else {
        cy.log("Note: Trainers Ranking section not found on dashboard (may be hidden if no data)");
      }
    });
  });
});
