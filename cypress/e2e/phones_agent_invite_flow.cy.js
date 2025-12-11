// cypress/e2e/phones_agent_invite_flow.cy.js

/**
 * Helper: generate a random 15-digit IMEI-style string
 */
function generateRandomImei() {
  return Array.from({ length: 15 }, () =>
    Math.floor(Math.random() * 10)
  ).join("");
}

/**
 * Helper: find the IMEI input on the sale wizard (Step 4)
 */
function getSaleImeiInput() {
  return cy.get(
    [
      "input[data-cy='sale-imei-input']",
      "input[name='imei']",
      "input[placeholder*='IMEI Number' i]",
      "input[placeholder*='Enter 15-digit IMEI' i]",
    ].join(", "),
    { timeout: 20000 }
  );
}

/**
 * Helper: as the logged in agent, walk all sidebar links
 * and make sure none of them throw a 500 error.
 *
 * We avoid "detached DOM" by:
 *  - collecting all sidebar hrefs once on dashboard
 *  - then using cy.visit(href, { failOnStatusCode: false }) for each one
 */
function walkSidebarLinksAsAgent() {
  const CLICK_WAIT_MS = 10000; // 10 seconds between pages

  cy.log("🧭 Sidebar smoke as AGENT – visit each sidebar href, assert no 500s");

  // Start from dashboard for a clean baseline
  cy.visit("/inventory/dashboard/");

  cy.get("body").then(($body) => {
    // Try to find a sidebar/nav wrapper
    const $sidebarCandidate = $body.find(
      "aside, .sidebar, nav[aria-label*='Sidebar'], .cc-sidebar"
    );
    const $sidebar = $sidebarCandidate.length ? $sidebarCandidate.first() : $body;

    const hrefSet = new Set();

    $sidebar.find("a[href]").each((_, el) => {
      const href = el.getAttribute("href") || "";

      // Skip invalid / junk / auth links
      if (
        !href ||
        href === "#" ||
        href.startsWith("javascript:") ||
        href.includes("/logout")
      ) {
        return;
      }

      hrefSet.add(href);
    });

    const hrefs = Array.from(hrefSet);

    cy.log(`🧾 Agent sidebar hrefs collected: ${hrefs.join(", ") || "(none found)"}`);

    // Now iterate over the hrefs with Cypress
    cy.wrap(hrefs).each((rawHref) => {
      const href = String(rawHref);

      cy.log(`➡️ [Agent sidebar] visiting href: ${href}`);

      // ⭐ Allow 403 / 401 / etc – we only care about avoiding 500s
      cy.visit(href, { failOnStatusCode: false });

      // Let page render
      cy.wait(CLICK_WAIT_MS);

      // Assert no 500 error in the rendered HTML
      cy.get("body").should("not.contain", "Server Error (500)");

      // Log where we landed
      cy.url().then((url) => {
        cy.log(`✅ Sidebar href ${href} → ${url}`);
      });

      // Return to dashboard for the next cycle
      cy.visit("/inventory/dashboard/");
    });
  });

  // Final sanity check: dashboard is healthy
  cy.get("body").should("not.contain", "Server Error (500)");
  cy.url().should("include", "/inventory/dashboard/");
}

describe("Phones agent invite + sale + sidebar smoke", () => {
  const BRAND = "ITEL";

  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it("invites a new agent, completes signup, then agent scans & sells a phone and walks sidebar (no 500s)", () => {
    const IMEI = generateRandomImei();
    cy.log(`🔢 Generated IMEI: ${IMEI}`);

    // =========================================================================
    // 1. Manager logs in and creates an AGENT invite
    // =========================================================================
    cy.log("🔐 Step 1: Log in as EMPIRE manager and open Agents page");
    cy.loginAsOwner();
    cy.visitDashboard("phones");
    cy.url({ timeout: 60000 }).should("include", "/inventory");

    cy.contains("a, button", "Agents")
      .scrollIntoView()
      .click();

    cy.url().should("include", "/tenants/manager/agents/");

    const agentName = `CypressAgent-${Date.now()}`;

    cy.get('input[name="invited_name"], input[placeholder*="e.g. Alice"]')
      .clear()
      .type(agentName);

    cy.contains("button, a", "Create Invite").click();

    cy.contains("Pending invites");
    cy.contains(agentName).should("exist");

    // Grab invite URL from share text
    cy.get("textarea, input[name='invite_link'], input[readonly]")
      .first()
      .invoke("val")
      .then((rawText) => {
        const text = String(rawText || "");
        const match = text.match(/https?:\/\/\S+/);

        expect(match, "found invite URL in share text").to.not.be.null;
        const inviteUrl = match[0];

        // Log out manager to simulate incognito agent signup
        cy.visit("/logout/");

        // =========================================================================
        // 2. Agent accepts invite, creates account with strong password
        // =========================================================================
        cy.log("🧾 Step 2: Agent visits invite link and signs up");
        cy.visit(inviteUrl);

        const email = `cypress.agent+${Date.now()}@example.com`;
        // Strong password: at least 12 chars, uppercase, lowercase, digit, symbol
        const password = "@Lincoln1863?";

        // Name/username is pre-filled from invite name; we only set email + password
        cy.get('input[type="email"], input[name="email"]')
          .clear()
          .type(email);

        cy.get('input[type="password"][name="password1"], input[name="password"]')
          .first()
          .clear()
          .type(password);

        cy.get('input[type="password"][name="password2"]')
          .clear()
          .type(password);

        cy.contains("button, input[type='submit']", /create account/i).click();

        // After signup, user should be inside inventory (choose business / dashboard)
        cy.url({ timeout: 60000 }).should((href) => {
          expect(
            href.includes("/inventory"),
            `expected redirect into inventory, got ${href}`
          ).to.be.true;
        });

        cy.contains("Empire").should("exist"); // business name somewhere on page

        // =========================================================================
        // 3. As AGENT: scan an ITEL phone into stock
        // =========================================================================
        cy.log("📲 Step 3: Agent scans an ITEL phone into stock");
        cy.visit("/inventory/phones/scan-in/");

        cy.contains(
          ".card, .brand-card, button, [data-cy=brand-card]",
          new RegExp(BRAND, "i")
        )
          .first()
          .click();

        cy.contains(/ITEL Models/i, { timeout: 20000 }).should("exist");

        cy.get("select", { timeout: 20000 })
          .first()
          .as("modelSelect")
          .select(1, { force: true }); // index 0 is placeholder

        cy.get("@modelSelect")
          .find("option:selected")
          .invoke("text")
          .then((text) => {
            cy.log(`ℹ️ Agent scan-in model selected: ${text.trim()}`);
          });

        cy.get("input[name='imei'], #imei-input, [data-cy='imei-input']", {
          timeout: 20000,
        })
          .first()
          .clear()
          .type(IMEI);

        cy.contains("button, input[type='submit']", /scan|add to stock|submit/i)
          .first()
          .click();

        cy.contains(/added to stock/i, { timeout: 15000 }).should("exist");

        // =========================================================================
        // 4. Agent opens Sale Wizard and sells same IMEI
        // =========================================================================
        cy.log("🧭 Step 4: Agent opens Phone Sale Wizard and chooses ITEL brand");
        cy.visit("/inventory/phone-sale-wizard/");

        cy.contains(
          "[data-cy='sale-brand-option'], .brand-card, .card, button",
          new RegExp(BRAND, "i")
        )
          .first()
          .click({ force: true });

        cy.contains("button", /continue|next/i)
          .first()
          .click();

        cy.log("📦 Step 5: Choose first model in wizard (Step 2)");
        cy.get("input[type='radio']", { timeout: 10000 })
          .filter(":visible")
          .first()
          .check({ force: true });

        cy.contains("button", /continue|next/i)
          .first()
          .click();

        cy.log("⚙️ Step 6: Choose variant/spec (Step 3, if present)");
        cy.get("body").then(($body) => {
          const isVariantStep = /variant/i.test($body.text());
          if (!isVariantStep) {
            cy.log("ℹ️ No variant step detected – skipping to IMEI");
            return;
          }

          return cy
            .get(
              "[data-cy='sale-variant-option'], [data-cy='sale-spec-option'], .variant-card, .option-card, .card",
              { timeout: 10000 }
            )
            .filter(":visible")
            .first()
            .click({ force: true })
            .then(() => {
              cy.contains("button", /continue|next/i)
                .first()
                .click();
            });
        });

        cy.log("🧾 Step 7: Enter same IMEI in wizard");
        getSaleImeiInput()
          .should("be.visible")
          .clear()
          .type(IMEI);

        cy.contains("button", /continue|next/i)
          .first()
          .click();

        cy.log("💰 Step 8: Set price and payment");
        cy.get(
          "input[data-cy='selling-price-input'], input[name='selling_price'], input[name='price']",
          { timeout: 20000 }
        )
          .should("be.visible")
          .clear()
          .type("500000");

        cy.get("body").then(($body) => {
          const labels = [
            "Cash",
            "Bank",
            "Mobile Money",
            "Airtel Money",
            "TNM Mpamba",
          ];
          let clicked = false;

          labels.forEach((label) => {
            if (!clicked && $body.find(`button:contains("${label}")`).length > 0) {
              cy.contains("button", label).click({ force: true });
              clicked = true;
            }
          });

          if (!clicked && $body.find("[data-cy^='payment-']").length > 0) {
            cy.get("[data-cy^='payment-']").first().click({ force: true });
          }
        });

        cy.contains(
          "button, [data-cy='confirm-sale-btn']",
          /complete sale|confirm sale|finish|submit|save/i
        )
          .first()
          .click();

        cy.log("🎉 Step 9: Verify sale success banner and dashboard");
        cy.get("body", { timeout: 20000 }).should(($body) => {
          const text = $body.text().toLowerCase();
          expect(text).to.satisfy(
            (t) =>
              t.includes("sale") &&
              (t.includes("success") ||
                t.includes("completed") ||
                t.includes("recorded"))
          );
        });

        cy.url().should("include", "/inventory/dashboard/");

        // =========================================================================
        // 5. AFTER SALE: Agent walks every sidebar link (no 500s, 10s between)
        // =========================================================================
        walkSidebarLinksAsAgent();
      });
  });
});
