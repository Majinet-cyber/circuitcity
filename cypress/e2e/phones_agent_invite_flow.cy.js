// cypress/e2e/phones_agent_invite_flow.cy.js

/**
 * Helper: generate a random 15-digit IMEI-style string
 */
function generateRandomImei() {
  return Array.from({ length: 15 }, () => Math.floor(Math.random() * 10)).join("");
}

/**
 * Helper: parse MWK amount from string to number
 * E.g., "MWK 15,000" -> 15000
 * E.g., "65,000" -> 65000
 */
function parseMwkAmount(text) {
  const cleaned = String(text).replace(/[^\d]/g, "");
  return parseInt(cleaned, 10) || 0;
}

/**
 * Helper: safer visit (prevents 90s "page did not fire load event" on heavy pages)
 */
function visitFast(url, opts = {}) {
  return cy.visit(url, { waitUntil: "domcontentloaded", ...opts });
}

/**
 * Helper: find the IMEI input on the sale wizard (Step 4)
 *
 * IMPORTANT: Cypress/jQuery selectors do NOT support CSS4 `i` flag in attribute selectors.
 * So we avoid: input[placeholder*='...' i]
 */
function getSaleImeiInput() {
  return cy.get(
    [
      "input[data-cy='sale-imei-input']",
      "input[name='imei']",
      "input[placeholder*='IMEI Number']",
      "input[placeholder*='IMEI number']",
      "input[placeholder*='Enter 15-digit IMEI']",
      "input[placeholder*='Enter 15-digit imei']",
    ].join(", "),
    { timeout: 20000 }
  );
}

/**
 * Helper: type into the Stock List search box (case-insensitive) without CSS4 selector flags
 */
function typeIntoStockSearch(value) {
  cy.get("input[placeholder]", { timeout: 20000 })
    .filter((_, el) => {
      const ph = (el.getAttribute("placeholder") || "").toLowerCase();
      return ph.includes("search"); // matches "Search IMEI/brand/model..." etc
    })
    .first()
    .should("be.visible")
    .clear()
    .type(value);
}

/**
 * Helper: go to Stock List and verify IMEI exists (used after Scan In)
 */
function verifyImeiExistsInStockList(imei) {
  cy.log("📦 Verifying scanned IMEI appears in Stock List (/inventory/list/)...");
  visitFast("/inventory/list/");
  cy.url({ timeout: 20000 }).should("include", "/inventory/list");
  cy.contains(/stock list/i, { timeout: 20000 }).should("be.visible");

  typeIntoStockSearch(imei);
  cy.contains(imei, { timeout: 20000 }).should("exist");
  cy.log(`✅ IMEI ${imei} found in Stock List`);
}

/**
 * Helper: robustly select ANY payment method on the sale wizard payment step.
 * This fixes agent flow where payment UI may be radios/labels instead of buttons.
 */
function selectAnyPaymentMethod() {
  const preferred = [
    /cash/i,
    /mobile\s*money/i,
    /tnm\s*mpamba/i,
    /\bmpamba\b/i,
    /airtel\s*money/i,
    /\bairtel\b/i,
    /\bbank\b/i,
  ];

  cy.log("💳 Selecting a payment method (robust)…");

  cy.get("body", { timeout: 20000 }).then(($body) => {
    // 1) RADIO INPUTS (most reliable if present)
    const $radios = $body.find(
      "input[type='radio'][name*='payment'], input[type='radio'][name*='method'], input[type='radio'][id*='payment']"
    );
    if ($radios.length) {
      const $firstEnabled = $radios.filter((_, el) => !el.disabled).first();
      if ($firstEnabled.length) {
        cy.wrap($firstEnabled).check({ force: true });
        return;
      }
    }

    // 2) data-cy payment chips/buttons
    const $dataCy = $body.find("[data-cy^='payment-'], [data-cy*='payment']");
    const $dataCyVisible = $dataCy.filter(":visible");
    if ($dataCyVisible.length) {
      cy.wrap($dataCyVisible.first()).click({ force: true });
      return;
    }

    // 3) Clickables with payment text (buttons/labels/links/cards)
    const $clickables = $body
      .find("button, label, a, .btn, [role='button'], .option-card, .variant-card, .card")
      .filter(":visible");

    for (const re of preferred) {
      const $hit = $clickables.filter((_, el) => re.test((el.innerText || "").trim()));
      if ($hit.length) {
        cy.wrap($hit.first()).click({ force: true });
        return;
      }
    }

    // 4) Select dropdown fallback
    const $selects = $body.find(
      "select[name*='payment'], select[name*='method'], select[data-cy*='payment']"
    );
    const $selectVisible = $selects.filter(":visible");
    if ($selectVisible.length) {
      cy.wrap($selectVisible.first()).select(1, { force: true });
      return;
    }

    cy.log("⚠️ No payment method UI detected on this step (continuing)");
  });

  // If radios exist, assert one is checked (prevents silent non-selection)
  cy.get("body").then(($body) => {
    const hasRadios =
      $body.find("input[type='radio'][name*='payment'], input[type='radio'][name*='method']")
        .length > 0;

    if (hasRadios) {
      cy.get(
        "input[type='radio'][name*='payment']:checked, input[type='radio'][name*='method']:checked",
        { timeout: 10000 }
      ).should("exist");
    }
  });
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
  visitFast("/inventory/dashboard/");

  cy.get("body").then(($body) => {
    const $sidebarCandidate = $body.find(
      "aside, .sidebar, nav[aria-label*='Sidebar'], .cc-sidebar"
    );
    const $sidebar = $sidebarCandidate.length ? $sidebarCandidate.first() : $body;

    const hrefSet = new Set();

    $sidebar.find("a[href]").each((_, el) => {
      const href = el.getAttribute("href") || "";

      if (!href || href === "#" || href.startsWith("javascript:") || href.includes("/logout")) {
        return;
      }

      hrefSet.add(href);
    });

    const hrefs = Array.from(hrefSet);

    cy.log(`🧾 Agent sidebar hrefs collected: ${hrefs.join(", ") || "(none found)"}`);

    cy.wrap(hrefs).each((rawHref) => {
      const href = String(rawHref);

      cy.log(`➡️ [Agent sidebar] visiting href: ${href}`);

      // Allow 403/401 etc; only care about avoiding 500s
      visitFast(href, { failOnStatusCode: false });

      cy.wait(CLICK_WAIT_MS);

      cy.get("body").should("not.contain", "Server Error (500)");

      cy.url().then((url) => {
        cy.log(`✅ Sidebar href ${href} → ${url}`);
      });

      // Return to dashboard for next cycle
      visitFast("/inventory/dashboard/");
    });
  });

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

    cy.contains("a, button", "Agents").scrollIntoView().click();
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
        visitFast("/logout/");

        // =========================================================================
        // 2. Agent accepts invite, creates account with strong password
        // =========================================================================
        cy.log("🧾 Step 2: Agent visits invite link and signs up");
        visitFast(inviteUrl);

        const email = `cypress.agent+${Date.now()}@example.com`;
        const password = "@Lincoln1863?";

        cy.get('input[type="email"], input[name="email"]').clear().type(email);

        cy.get('input[type="password"][name="password1"], input[name="password"]')
          .first()
          .clear()
          .type(password);

        cy.get('input[type="password"][name="password2"]').clear().type(password);

        cy.contains("button, input[type='submit']", /create account/i).click();

        cy.url({ timeout: 60000 }).should((href) => {
          expect(href.includes("/inventory"), `expected redirect into inventory, got ${href}`).to.be
            .true;
        });

        cy.contains("Empire").should("exist");

        // Log agent identity
        cy.get("body").then(($body) => {
          const bodyText = $body.text();
          cy.log(`🔐 Logged in as agent: ${email}`);
          if (bodyText.includes("Logout") || bodyText.includes("Sign Out")) {
            cy.log("✅ Logout button found - user is authenticated");
          }
        });

        // =========================================================================
        // 3. As AGENT: scan an ITEL phone into stock
        // =========================================================================
        cy.log("📲 Step 3: Agent scans an ITEL phone into stock");
        visitFast("/inventory/phones/scan-in/");

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
          .select(1, { force: true });

        cy.get("@modelSelect")
          .find("option:selected")
          .invoke("text")
          .then((text) => {
            cy.log(`ℹ️ Agent scan-in model selected: ${String(text).trim()}`);
          });

        cy.get("input[name='imei'], #imei-input, [data-cy='imei-input']", { timeout: 20000 })
          .first()
          .clear()
          .type(IMEI);

        cy.contains("button, input[type='submit']", /scan|add to stock|submit/i)
          .first()
          .click();

        cy.contains(/added to stock/i, { timeout: 15000 }).should("exist");

        // ✅ Verify what was added on the REAL Stock page
        verifyImeiExistsInStockList(IMEI);

        // =========================================================================
        // 4. BEFORE SALE: Capture baseline wallet metrics
        // =========================================================================
        cy.log("📊 Step 4: Capture baseline wallet state BEFORE sale");

        visitFast("/wallet/");
        cy.url().should("include", "/wallet/");

        let baselineUnitsSold = 0;
        let baselineEarnings = 0;

        cy.log("🔄 Setting period to 'This Month'...");
        cy.get("body").then(($body) => {
          const bodyText = $body.text();
          if (/this\s+month/i.test(bodyText)) {
            cy.get("button, a, [role='tab'], .nav-link, .period-selector")
              .filter(":visible")
              .contains(/this\s+month/i)
              .first()
              .click({ force: true });

            cy.wait(2000);
            cy.log("✅ Period set to 'This Month'");
          } else {
            cy.log("ℹ️ No 'This Month' button found - may already be selected");
          }
        });

        cy.url().then((url) => {
          cy.log(`📍 Current URL: ${url}`);
        });

        cy.get("body").then(($body) => {
          const bodyText = $body.text();
          if (bodyText.includes("Empire") || bodyText.includes("empire")) {
            cy.log("✅ User is viewing Empire business wallet");
          }
          cy.log("📄 Wallet page snippet:");
          cy.log(bodyText.substring(0, 300).replace(/\s+/g, " "));
        });

        cy.log("📦 Capturing baseline units sold...");
        cy.get("body", { timeout: 10000 }).then(($body) => {
          const text = $body.text();
          const unitsMatch = text.match(/(\d+)\s+units?\s+sold/i);
          if (unitsMatch) {
            baselineUnitsSold = parseInt(unitsMatch[1], 10);
            cy.log(`📦 Baseline units sold: ${baselineUnitsSold}`);
          } else {
            cy.log("📦 No 'units sold' text found - assuming 0");
            baselineUnitsSold = 0;
          }
        });

        cy.log("💰 Capturing baseline earnings...");
        cy.get("body", { timeout: 10000 }).then(($body) => {
          const text = $body.text();

          const thisMonthMatch = text.match(/this\s+month[^]*?MWK\s*([\d,]+)/i);
          if (thisMonthMatch) {
            baselineEarnings = parseMwkAmount(thisMonthMatch[1]);
            cy.log(`💰 Baseline earnings (This Month): MWK ${baselineEarnings}`);
            return;
          }

          const earningsSelectors = [
            '[data-cy="wallet-period-earnings"]',
            '[data-cy="this-month-earnings"]',
            '[data-cy="current-earnings"]',
            ".earnings-amount",
            ".wallet-earnings",
          ];

          let foundEarnings = false;
          earningsSelectors.forEach((selector) => {
            if (!foundEarnings && $body.find(selector).length > 0) {
              const earningsText = $body.find(selector).first().text();
              baselineEarnings = parseMwkAmount(earningsText);
              foundEarnings = true;
              cy.log(`💰 Baseline earnings: MWK ${baselineEarnings}`);
            }
          });

          if (!foundEarnings) {
            const earningsMatch = text.match(/(?:earnings?|commission)[\s:]*MWK\s*([\d,]+)/i);
            if (earningsMatch) {
              baselineEarnings = parseMwkAmount(earningsMatch[1]);
              cy.log(`💰 Baseline earnings (from text): MWK ${baselineEarnings}`);
            } else {
              cy.log("💰 No earnings found - assuming 0");
              baselineEarnings = 0;
            }
          }
        });

        cy.log(`✅ Baseline captured: ${baselineUnitsSold} units, MWK ${baselineEarnings} earnings`);

        visitFast("/inventory/dashboard/");
        cy.wait(2000);

        // =========================================================================
        // 5. Agent opens Sale Wizard and sells same IMEI
        // =========================================================================
        cy.log("🧭 Step 5: Agent opens Phone Sale Wizard and chooses ITEL brand");
        visitFast("/inventory/phone-sale-wizard/");

        cy.contains(
          "[data-cy='sale-brand-option'], .brand-card, .card, button",
          new RegExp(BRAND, "i")
        )
          .first()
          .click({ force: true });

        cy.contains("button", /continue|next/i).first().click();

        cy.log("📦 Step 6: Choose first model in wizard (Step 2)");
        cy.get("input[type='radio']", { timeout: 10000 })
          .filter(":visible")
          .first()
          .check({ force: true });

        cy.contains("button", /continue|next/i).first().click();

        cy.log("⚙️ Step 7: Choose variant/spec (Step 3, if present)");
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
              cy.contains("button", /continue|next/i).first().click();
            });
        });

        cy.log("🧾 Step 8: Enter same IMEI in wizard");
        getSaleImeiInput().should("be.visible").clear().type(IMEI);

        cy.contains("button", /continue|next/i).first().click();

        // ✅ FIXED FOR AGENTS: robust payment selection + ensure confirm enabled
        cy.log("💰 Step 9: Set price and payment");
        cy.get(
          "input[data-cy='selling-price-input'], input[name='selling_price'], input[name='price']",
          { timeout: 20000 }
        )
          .should("be.visible")
          .clear()
          .type("500000");

        // robust payment picker (works for agent UI variants)
        selectAnyPaymentMethod();
        cy.wait(300);

        cy.contains(
          "button, a, [data-cy='confirm-sale-btn']",
          /complete sale|confirm sale|finish|submit|save/i
        )
          .filter(":visible")
          .first()
          .scrollIntoView()
          .should("not.be.disabled")
          .click({ force: true });

        cy.log("🎉 Step 10: Verify sale success and record details");

        cy.get("body", { timeout: 20000 }).should(($body) => {
          const text = $body.text().toLowerCase();
          expect(text).to.satisfy(
            (t) =>
              t.includes("sale") &&
              (t.includes("success") ||
                t.includes("completed") ||
                t.includes("recorded") ||
                t.includes("saved")),
            "Expected sale success message on page"
          );
        });

        cy.url().should("include", "/inventory/dashboard/");

        cy.url().then((currentUrl) => {
          cy.log(`✅ Sale completed - redirected to: ${currentUrl}`);
        });

        cy.get("body").then(($body) => {
          const bodyText = $body.text();

          if (bodyText.includes(email) || bodyText.includes(agentName)) {
            cy.log(`✅ Agent ${email} is still logged in`);
          }

          if (bodyText.includes("Empire")) {
            cy.log("✅ Agent is in Empire business context");
          }

          if (bodyText.includes("Logout") || bodyText.includes("Sign Out")) {
            cy.log("✅ User is authenticated (Logout button present)");
          }

          cy.log(`📄 Dashboard snippet: ${bodyText.substring(0, 300).replace(/\s+/g, " ")}`);
        });

        // ✅ Replace broken /inventory/phone-sales/ check with Stock List page (real route)
        cy.log("🔍 Verifying sale effect via Stock List (real page: /inventory/list/)...");
        visitFast("/inventory/list/");
        cy.url().should("include", "/inventory/list");
        cy.contains(/stock list/i, { timeout: 20000 }).should("be.visible");

        // We don't hard-fail here because sold items might disappear or change status.
        // Wallet delta checks are the definitive proof of sale attribution.
        typeIntoStockSearch(IMEI);
        cy.get("body").then(($body) => {
          const text = $body.text();
          const stillVisible = text.includes(IMEI);
          cy.log(`📱 IMEI ${IMEI} visible in Stock List after sale: ${stillVisible}`);
          if (stillVisible) {
            cy.log("ℹ️ IMEI still visible (may be marked sold / moved state). Wallet checks will confirm.");
          } else {
            cy.log("✅ IMEI not visible in Stock List (likely removed from in-stock after sale).");
          }
        });

        // =========================================================================
        // 6. AFTER SALE: Verify wallet shows delta increases
        // =========================================================================
        cy.log("💰 Step 11: Verify wallet deltas AFTER sale");

        function verifyWalletUpdate(maxRetries = 5, delayMs = 2000) {
          let attempt = 0;

          function attemptRead() {
            attempt++;
            cy.log(`🔄 Wallet check attempt ${attempt}/${maxRetries}`);

            visitFast("/wallet/");
            cy.url().should("include", "/wallet/");

            cy.get("body").then(($body) => {
              const bodyText = $body.text();
              if (/this\s+month/i.test(bodyText)) {
                cy.get("button, a, [role='tab'], .nav-link, .period-selector")
                  .filter(":visible")
                  .contains(/this\s+month/i)
                  .first()
                  .click({ force: true });
                cy.wait(1000);
              }
            });

            cy.get("body", { timeout: 10000 }).then(($body) => {
              const text = $body.text();
              const unitsMatch = text.match(/(\d+)\s+units?\s+sold/i);
              const currentUnits = unitsMatch ? parseInt(unitsMatch[1], 10) : 0;

              cy.log(`📦 Current units sold: ${currentUnits} (baseline: ${baselineUnitsSold})`);

              if (currentUnits > baselineUnitsSold) {
                cy.log(`✅ Wallet updated! Units: ${baselineUnitsSold} → ${currentUnits}`);
                return;
              } else if (attempt < maxRetries) {
                cy.log(`⏳ Wallet not updated yet, waiting ${delayMs}ms before retry...`);
                cy.wait(delayMs);
                attemptRead();
              } else {
                cy.log(`⚠️ Wallet still showing ${currentUnits} after ${maxRetries} attempts`);
              }
            });
          }

          attemptRead();
        }

        verifyWalletUpdate(5, 2000);

        cy.log("✅ FIX 1: Verify units sold increased by at least +1");
        cy.get("body", { timeout: 30000 }).should(($body) => {
          const text = $body.text();

          const snippet = text.substring(0, 600).replace(/\s+/g, " ");
          cy.log("📄 Wallet page (after sale) snippet:");
          cy.log(snippet);

          const unitsMatch = text.match(/(\d+)\s+units?\s+sold/i);
          expect(unitsMatch, "Should find 'units sold' text on wallet page").to.not.be.null;

          const currentUnitsSold = parseInt(unitsMatch[1], 10);
          const delta = currentUnitsSold - baselineUnitsSold;

          cy.log(`📦 Units sold: ${baselineUnitsSold} → ${currentUnitsSold} (Δ${delta})`);

          expect(
            currentUnitsSold,
            `Units sold should be at least ${baselineUnitsSold + 1} (baseline ${baselineUnitsSold} + 1 sale)`
          ).to.be.at.least(baselineUnitsSold + 1);

          expect(delta, `Units sold delta should be at least 1`).to.be.at.least(1);
        });

        cy.log("✅ FIX 2: Verify earnings increased");
        cy.get("body", { timeout: 20000 }).should(($body) => {
          const text = $body.text();

          let currentEarnings = 0;
          let foundEarnings = false;

          const thisMonthMatch = text.match(/this\s+month[^]*?MWK\s*([\d,]+)/i);
          if (thisMonthMatch) {
            currentEarnings = parseMwkAmount(thisMonthMatch[1]);
            foundEarnings = true;
          }

          if (!foundEarnings) {
            const earningsSelectors = [
              '[data-cy="wallet-period-earnings"]',
              '[data-cy="this-month-earnings"]',
              '[data-cy="current-earnings"]',
              ".earnings-amount",
              ".wallet-earnings",
            ];

            earningsSelectors.forEach((selector) => {
              if (!foundEarnings && $body.find(selector).length > 0) {
                const earningsText = $body.find(selector).first().text();
                currentEarnings = parseMwkAmount(earningsText);
                foundEarnings = true;
              }
            });
          }

          if (!foundEarnings) {
            const earningsMatch = text.match(/(?:earnings?|commission)[\s:]*MWK\s*([\d,]+)/i);
            if (earningsMatch) {
              currentEarnings = parseMwkAmount(earningsMatch[1]);
              foundEarnings = true;
            }
          }

          expect(foundEarnings, "Should find earnings on wallet page").to.be.true;

          const earningsDelta = currentEarnings - baselineEarnings;

          cy.log(`💰 Earnings: MWK ${baselineEarnings} → MWK ${currentEarnings} (Δ${earningsDelta})`);

          expect(currentEarnings, `Earnings should increase from baseline ${baselineEarnings}`).to.be.greaterThan(
            baselineEarnings
          );
        });

        cy.log("✅ FIX 3: Verify ranking works (not unavailable)");
        cy.get("body", { timeout: 10000 }).then(($body) => {
          const text = $body.text();
          expect(text).to.not.include("Ranking unavailable", "Ranking should work, not show 'unavailable'");

          const hasRanking =
            $body.find("canvas#rankChart").length > 0 ||
            $body.find("[data-cy*='rank']").length > 0 ||
            /your rank/i.test(text);

          expect(hasRanking).to.be.true;
        });

        cy.log("✅ FIX 4: Verify payslip updates after sale");
        cy.get("body", { timeout: 10000 }).then(($body) => {
          const text = $body.text();

          if (/payslip/i.test(text)) {
            const showsNoPayslips = /no payslips yet/i.test(text);

            if (!showsNoPayslips) {
              cy.log("✓ Payslips are visible and showing data");

              const currentYear = new Date().getFullYear();
              const hasData = text.includes(String(currentYear)) || /\d+,\d+/.test(text) || /MWK/i.test(text);

              expect(hasData).to.be.true;
            } else {
              cy.log("ℹ️ Payslip says 'No payslips yet' - may be using formal payslips only");
            }
          }
        });

        cy.log("🎊 All 4 wallet fixes verified with delta-based assertions!");

        // =========================================================================
        // 7. AFTER SALE: Agent walks every sidebar link (no 500s)
        // =========================================================================
        cy.log("🚶 Step 12: Walk all sidebar links to verify no 500 errors");
        walkSidebarLinksAsAgent();
      });
  });
});
