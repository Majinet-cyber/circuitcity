// cypress/e2e/phones_agent_invite_flow.cy.js

/**
 * Generate a random 15-digit IMEI-style string
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
      "input[placeholder*='Enter 15-digit IMEI' i]"
    ].join(", "),
    { timeout: 20000 }
  );
}

/**
 * Phones: Agent invite + signup + sale flow
 *
 * Flow:
 * - Manager logs in and goes to Phones dashboard
 * - Opens Agents page from sidebar
 * - Creates an invite for a random agent name
 * - Copies invite link from share text
 * - Logs out
 * - Opens invite link, signs up as new agent (strong password)
 * - Lands inside the business as that agent
 * - Agent scans an ITEL phone into stock
 * - Agent sells that exact IMEI via the phone sale wizard
 */

describe("Phones agent invite + sale flow", () => {
  const BRAND = "ITEL";

  it("invites a new agent, completes signup, then agent scans & sells a phone", () => {
    const IMEI = generateRandomImei();
    cy.log(`🔢 Generated IMEI for agent: ${IMEI}`);

    // -------------------------------------------------------------------
    // 1. Login as owner/manager and ensure we are in inventory
    // -------------------------------------------------------------------
    cy.loginAsOwner();
    cy.visitDashboard("phones");
    cy.url().should("include", "/inventory");

    // -------------------------------------------------------------------
    // 2. Go to Agents page via sidebar
    // -------------------------------------------------------------------
    cy.contains("a, button", "Agents")
      .scrollIntoView()
      .click();

    cy.url().should("include", "/tenants/manager/agents/");

    // -------------------------------------------------------------------
    // 3. Create an invite
    // -------------------------------------------------------------------
    const agentName = `CypressAgent-${Date.now()}`;

    cy.get('input[name="invited_name"], input[placeholder*="e.g. Alice"]')
      .clear()
      .type(agentName);

    cy.contains("button, a", "Create Invite").click();

    cy.contains("Pending invites");
    cy.contains(agentName).should("exist");

    // -------------------------------------------------------------------
    // 4. Grab invite link from share text
    // -------------------------------------------------------------------
    cy.get("textarea, input[name='invite_link'], input[readonly]")
      .first()
      .invoke("val")
      .then((rawText) => {
        const text = String(rawText || "");
        const match = text.match(/https?:\/\/\S+/);

        expect(match, "found invite URL in share text").to.not.be.null;

        const inviteUrl = match[0];

        // -----------------------------------------------------------------
        // 5. Log out manager, visit invite URL as "incognito" agent
        // -----------------------------------------------------------------
        cy.visit("/logout/");
        cy.visit(inviteUrl);

        const email = `cypress.agent+${Date.now()}@example.com`;
        const password = "@Lincoln1863?"; // strong password as requested

        cy.get("input[type='email'], input[name='email']").type(email);

        cy.get(
          "input[type='password'][name='password1'], input[name='password']"
        )
          .first()
          .type(password);

        cy.get("input[type='password'][name='password2']").type(password);

        cy.contains("button, input[type='submit']", "Create account").click();

        // -----------------------------------------------------------------
        // 6. Assert agent lands inside the business (redirect into inventory)
        // -----------------------------------------------------------------
        cy.url({ timeout: 60000 }).should("include", "/inventory");
        cy.contains("Empire").should("exist"); // brand/business name visible

        // =================================================================
        // AGENT FLOW: scan an ITEL phone into stock, then sell it
        // =================================================================

        // --------------------------------------------------------------
        // 7. Agent → Scan In Phones and pick ITEL brand
        // --------------------------------------------------------------
        cy.log("📲 Agent: go to Scan IN Phones and pick ITEL");
        cy.visit("/inventory/phones/scan-in/");

        cy.contains(
          ".card, .brand-card, button, [data-cy=brand-card]",
          new RegExp(BRAND, "i")
        )
          .first()
          .click();

        cy.contains(/ITEL Models/i, { timeout: 20000 }).should("exist");

        // --------------------------------------------------------------
        // 8. Agent → Choose first ITEL model (dropdown)
        // --------------------------------------------------------------
        cy.log("📦 Agent: choose first ITEL model in dropdown");
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

        // --------------------------------------------------------------
        // 9. Agent → Enter IMEI and submit scan
        // --------------------------------------------------------------
        cy.log("📡 Agent: enter IMEI and submit scan");
        cy.get("input[name='imei'], #imei-input, [data-cy='imei-input']", {
          timeout: 20000
        })
          .first()
          .clear()
          .type(IMEI);

        cy.contains("button, input[type='submit']", /scan|add to stock|submit/i)
          .first()
          .click();

        cy.contains(/added to stock/i, { timeout: 15000 }).should("exist");

        // --------------------------------------------------------------
        // 10. (Optional) Soft check IMEI in Stock List
        // --------------------------------------------------------------
        cy.log("📋 Agent: soft check IMEI in Stock List");
        cy.visit("/inventory/list/");

        cy.get(
          "input[placeholder*='Search IMEI' i], input[placeholder*='Search IMEI/brand/model' i]",
          { timeout: 20000 }
        )
          .first()
          .clear()
          .type(IMEI);

        cy.wait(1000);

        cy.get("body", { timeout: 20000 }).then(($body) => {
          const found = $body
            .find("td")
            .toArray()
            .some((el) => el.innerText.includes(IMEI));

          if (found) {
            cy.log("✅ Agent: IMEI found in stock list");
          } else {
            cy.log("⚠️ Agent: IMEI NOT found in stock list – continuing anyway");
          }
        });

        // --------------------------------------------------------------
        // 11. Agent → Open Phone Sale Wizard and choose ITEL brand
        // --------------------------------------------------------------
        cy.log("🧭 Agent: open Phone Sale Wizard and choose ITEL");
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

        // --------------------------------------------------------------
        // 12. Wizard Step 2 – choose first visible model radio
        // --------------------------------------------------------------
        cy.log("📦 Agent: choose first model in wizard (Step 2)");
        cy.get("input[type='radio']", { timeout: 10000 })
          .filter(":visible")
          .first()
          .check({ force: true });

        cy.contains("button", /continue|next/i)
          .first()
          .click();

        // --------------------------------------------------------------
        // 13. Wizard Step 3 – click first visible variant card (if step exists)
        // --------------------------------------------------------------
        cy.log("⚙️ Agent: choose variant/spec (Step 3, if present)");
        cy.get("body").then(($body) => {
          const isVariantStep = /variant/i.test($body.text());
          if (!isVariantStep) {
            cy.log("ℹ️ Agent: no variant step detected – skipping to IMEI");
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

        // --------------------------------------------------------------
        // 14. Wizard IMEI step – enter same IMEI
        // --------------------------------------------------------------
        cy.log("🧾 Agent: enter same IMEI in wizard");
        getSaleImeiInput()
          .should("be.visible")
          .clear()
          .type(IMEI);

        cy.contains("button", /continue|next/i)
          .first()
          .click();

        // --------------------------------------------------------------
        // 15. Set selling price & pick any payment method
        // --------------------------------------------------------------
        cy.log("💰 Agent: set price and payment");
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
            "TNM Mpamba"
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

        // --------------------------------------------------------------
        // 16. Verify sale success
        // --------------------------------------------------------------
        cy.log("🎉 Agent: verify sale success");
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
      });
  });
});
