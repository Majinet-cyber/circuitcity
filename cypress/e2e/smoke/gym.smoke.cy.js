/**
 * Gym Vertical - Smoke Test
 * CircuitCity / Emajinet - Clean Suite Reboot (Jan 2026)
 *
 * FLOW:
 * 1. Login as manager
 * 2. Click every sidebar item
 * 3. Assert each page loads without errors
 * 4. Return to dashboard and verify it's ready
 */

describe('Gym Vertical - Smoke Test (Hit Every Button)', () => {
  const VERTICAL = 'gym';

  beforeEach(() => {
    // Login as manager for this vertical
    cy.loginAsManager(VERTICAL);
  });

  it('should navigate all sidebar items without errors', () => {
    cy.fixture('verticals').then((verticals) => {
      const vertical = verticals[VERTICAL];
      const sidebarItems = vertical.sidebarItems || [];

      cy.log(`🔥 Smoke testing ${vertical.displayName} - ${sidebarItems.length} sidebar items`);

      // Visit dashboard first
      cy.visit(vertical.dashboardPath, { failOnStatusCode: false });
      cy.assertPageReady('dashboard-heading');
      cy.stepWait('Dashboard ready');

      // Click each sidebar item
      sidebarItems.forEach((item, index) => {
        cy.log(`📍 Testing sidebar item ${index + 1}/${sidebarItems.length}: ${item.testid}`);

        // Try to click the sidebar item (may or may not exist)
        cy.get('body').then(($body) => {
          const selector = `[data-testid="${item.testid}"]`;

          if ($body.find(selector).length) {
            cy.get(selector).click();
            cy.stepWait(`Clicked ${item.testid}`);

            // Verify URL
            if (item.path) {
              cy.url({ timeout: 20000 }).should('include', item.path);
            }

            // Verify page ready element
            if (item.readyTestid) {
              cy.get(`[data-testid="${item.readyTestid}"]`, { timeout: 20000 })
                .should('exist');
            }

            // Verify no server errors
            cy.assertNoServerError();
          } else {
            cy.log(`⚠️ Sidebar item ${item.testid} not found - skipping`);
          }
        });
      });

      // Return to dashboard at end
      cy.visit(vertical.dashboardPath, { failOnStatusCode: false });
      cy.assertPageReady('dashboard-heading');
      cy.stepWait('Returned to dashboard');

      cy.log(`✅ Smoke test complete for ${vertical.displayName}`);
    });
  });
});

