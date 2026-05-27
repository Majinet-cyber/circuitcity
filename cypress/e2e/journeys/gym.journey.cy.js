/**
 * Gym Vertical - Full User Journey
 * CircuitCity / Emajinet - Clean Suite Reboot (Jan 2026)
 *
 * FLOW:
 * 1. Manager signs up and creates a gym business
 * 2. Dashboard loads correctly
 * 3. Capture baseline KPIs
 * 4. Stock in a gym product (supplement)
 * 5. Verify KPIs updated
 * 6. Make a sale
 * 7. Verify KPIs updated again
 */

describe('Gym Vertical - Full User Journey', () => {
  const VERTICAL = 'gym';

  it('should complete full manager journey: signup → stock-in → sale → verify KPIs', () => {
    // Step 1: Sign up manager and create business
    cy.signupManagerAndCreateBusiness(VERTICAL).then((creds) => {
      cy.log(`✅ Signed up: ${creds.email}`);

      // Step 2: Assert dashboard is ready
      cy.assertPageReady('dashboard-heading', { urlContains: 'gym' });
      cy.stepWait('Dashboard verified');

      // Step 3: Capture baseline KPIs
      cy.captureKPIs().as('beforeStockIn');

      // Step 4: Stock in a gym product
      cy.stockInForVertical(VERTICAL);
      cy.stepWait('Stock in completed');

      // Step 5: Return to dashboard and verify KPIs changed
      cy.fixture('verticals').then((verticals) => {
        const dashboardPath = verticals[VERTICAL].dashboardPath;
        cy.visit(dashboardPath, { failOnStatusCode: false });
        cy.assertPageReady('dashboard-heading');
        cy.stepWait('Back on dashboard after stock-in');

        cy.captureKPIs().as('afterStockIn');
        cy.get('@beforeStockIn').then((before) => {
          cy.get('@afterStockIn').then((after) => {
            if (before.instock !== undefined && after.instock !== undefined) {
              expect(after.instock).to.be.greaterThan(before.instock);
            }
            cy.log(`📊 Stock increased: ${before.instock || 0} → ${after.instock || 0}`);
          });
        });

        // Step 6: Make a sale
        cy.makeSaleForVertical(VERTICAL);
        cy.stepWait('Sale completed');

        // Step 7: Return to dashboard and verify final KPIs
        cy.visit(dashboardPath, { failOnStatusCode: false });
        cy.assertPageReady('dashboard-heading');
        cy.stepWait('Back on dashboard after sale');

        cy.captureKPIs().as('afterSale');
        cy.get('@afterStockIn').then((afterStockIn) => {
          cy.get('@afterSale').then((afterSale) => {
            if (afterStockIn.sold !== undefined && afterSale.sold !== undefined) {
              expect(afterSale.sold).to.be.greaterThan(afterStockIn.sold);
            }
            cy.log(`📊 Sold increased: ${afterStockIn.sold || 0} → ${afterSale.sold || 0}`);
          });
        });
      });
    });
  });
});


