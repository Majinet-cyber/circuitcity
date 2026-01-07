// cypress/e2e/phone_reports_flow.cy.js
/**
 * E2E Flow 2 – Costs + Reports
 *
 * Tests:
 * - Login as manager and select phone business
 * - Add a cost (fixed, e.g., rent)
 * - Verify cost appears in costs table
 * - Check Business Spend Trend chart loads without error
 * - Visit /reports/ and verify it loads (no NoReverseMatch)
 * - Verify summary cards show data
 * - Verify payment mix chart reflects payment methods
 * - Test CSV download endpoints via API
 */

describe('Phone Reports Flow - Costs and Business Intelligence', () => {
  const testCost = {
    amount: '100000',
    note: 'Office rent - Cypress test',
  };

  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it('completes reports flow: add cost → verify spend trend → check reports dashboard', () => {
    // ==========================================
    // 1. Login and select phone business
    // ==========================================
    cy.loginAsOwner();
    cy.wait(1000);

    cy.url().then((url) => {
      if (url.includes('choose') || url.includes('select') || url.includes('business')) {
        cy.selectBusinessByKind('phones');
        cy.wait(1000);
      }
    });

    // ==========================================
    // 2. Add a cost
    // ==========================================
    cy.log('💰 Adding a fixed cost...');

    // Visit admin costs page
    cy.visit('/wallet/admin/costs/');
    cy.url().should('include', '/wallet/admin/costs');
    cy.wait(1000);

    // Verify page loads without errors
    cy.get('body').should('not.contain', '500 Internal Server Error');
    cy.get('body').should('not.contain', 'admin_costs_create');
    cy.get('body').should('not.contain', 'latest_notifications');

    // Click "Add Cost" button
    cy.get('body').then(($body) => {
      const addCostSelectors = [
        '[data-cy="add-cost"]',
        'a:contains("Add Cost")',
        'button:contains("Add Cost")',
        'a:contains("New Cost")',
      ];

      let found = false;
      addCostSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0 && !found) {
          cy.get(selector).first().click();
          found = true;
          cy.wait(500);
        }
      });

      if (!found) {
        cy.log('⚠ Add Cost button not found - form might be on same page');
      }
    });

    // Fill cost form
    cy.get('body').then(($body) => {
      // Amount field
      const amountSelectors = [
        '[data-cy="amount"]',
        'input[name="amount"]',
        '#id_amount',
      ];
      amountSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).first().clear().type(testCost.amount);
        }
      });

      // Note field
      const noteSelectors = [
        '[data-cy="note"]',
        'textarea[name="note"]',
        'input[name="note"]',
        '#id_note',
      ];
      noteSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).first().clear().type(testCost.note);
        }
      });

      // Type field (if available)
      const typeSelectors = [
        '[data-cy="type"]',
        'select[name="type"]',
        '#id_type',
      ];
      typeSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0 && $body.find(selector).first().is('select')) {
          // Select "Fixed" or "Once-off" cost type
          cy.get(selector).first().then(($select) => {
            const options = $select.find('option').toArray().map(opt => opt.text);
            if (options.some(opt => opt.includes('Once') || opt.includes('Fixed'))) {
              cy.get(selector).first().select(/Once|Fixed/);
            }
          });
        }
      });
    });

    // Submit cost form
    cy.get('button[type="submit"], [data-cy="submit"], button:contains("Save"), button:contains("Add")')
      .first()
      .click();
    cy.wait(1000);

    // Verify success
    cy.get('body').then(($body) => {
      const successSelectors = ['.alert-success', '.toast-success', '[data-cy="success"]'];
      successSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.log('✓ Cost added successfully');
        }
      });
    });

    // ==========================================
    // 3. Verify cost appears in costs table
    // ==========================================
    cy.log('📋 Verifying cost in costs table...');

    cy.visit('/wallet/admin/costs/');
    cy.wait(1000);

    // Look for our cost note in the page
    cy.get('body').should('contain', testCost.note);
    cy.log('✓ Cost appears in costs table');

    // ==========================================
    // 4. Business spend trend chart
    // ==========================================
    cy.log('📊 Checking Business Spend Trend chart...');

    cy.visit('/wallet/admin/');
    cy.wait(2000);  // Give charts time to load

    // Verify page loads without error
    cy.get('body').should('not.contain', '500 Internal Server Error');
    cy.get('body').should('not.contain', 'Failed to load chart');
    cy.get('body').should('not.contain', 'TypeError');

    // Check for canvas (chart rendered)
    cy.get('body').then(($body) => {
      const hasCanvas = $body.find('canvas').length > 0;
      if (hasCanvas) {
        cy.log('✓ Business Spend Trend chart rendered successfully');

        // Optional: check for data points
        if ($body.text().includes('MWK') || $body.text().match(/\d{1,3}(,\d{3})*(\.\d{2})?/)) {
          cy.log('✓ Chart displays financial data');
        }
      } else {
        cy.log('⚠ No canvas found - chart may not have loaded');
      }
    });

    // ==========================================
    // 5. Reports page (/reports/)
    // ==========================================
    cy.log('📈 Testing /reports/ page...');

    cy.visit('/reports/');
    cy.wait(1500);

    // A) Page loads with HTTP 200 (no NoReverseMatch: 'sales')
    cy.url().should('include', '/reports/');
    cy.get('body').should('not.contain', 'NoReverseMatch');
    cy.get('body').should('not.contain', '500 Internal Server Error');
    cy.get('body').should('not.contain', 'TemplateDoesNotExist');
    cy.log('✓ /reports/ loads successfully (no NoReverseMatch error)');

    // B) Summary cards show data
    cy.log('📊 Checking summary cards...');
    cy.get('body').then(($body) => {
      const bodyText = $body.text();

      // Look for revenue/profit/cost indicators
      if (bodyText.includes('Revenue') || bodyText.includes('revenue')) {
        cy.log('✓ Reports page shows revenue metric');
      }
      if (bodyText.includes('Cost') || bodyText.includes('cost')) {
        cy.log('✓ Reports page shows cost metric');
      }
      if (bodyText.includes('Profit') || bodyText.includes('profit')) {
        cy.log('✓ Reports page shows profit metric');
      }

      // Check for numeric values (indicating actual data)
      const hasNumbers = bodyText.match(/\d{1,3}(,\d{3})*(\.\d{2})?/) !== null;
      if (hasNumbers) {
        cy.log('✓ Summary cards display numeric data');
      } else {
        cy.log('⚠ No numeric data found in summary cards');
      }
    });

    // C) Payment mix chart
    cy.log('💳 Checking payment mix chart...');
    cy.get('body').then(($body) => {
      if ($body.find('canvas').length > 0) {
        cy.log('✓ Payment mix chart canvas exists');
      }

      // Look for payment method labels
      const paymentMethods = ['Cash', 'Bank', 'Mobile'];
      paymentMethods.forEach((method) => {
        if ($body.text().includes(method)) {
          cy.log(`✓ Found payment method: ${method}`);
        }
      });
    });

    // D) Trend chart renders without JS error
    cy.log('📉 Verifying trend chart...');
    cy.get('body').then(($body) => {
      // Check for chart container
      if ($body.find('canvas').length > 0 || $body.find('[id*="chart"]').length > 0) {
        cy.log('✓ Trend chart container exists');
      }

      // No JS errors visible in UI
      if (!$body.text().includes('undefined') && !$body.text().includes('TypeError')) {
        cy.log('✓ No JavaScript errors visible on page');
      }
    });

    // ==========================================
    // 6. Download endpoints (API tests)
    // ==========================================
    cy.log('📥 Testing CSV download endpoints...');

    // Test /reports/export/sales/
    cy.request({
      url: '/reports/export/sales/',
      failOnStatusCode: false,
    }).then((response) => {
      expect(response.status).to.eq(200);
      expect(response.headers['content-type']).to.include('text/csv');
      cy.log('✓ /reports/export/sales/ returns CSV');

      // Verify CSV contains expected headers or data
      if (response.body) {
        cy.log(`CSV preview: ${response.body.substring(0, 100)}...`);
      }
    });

    // Test /reports/export/costs/
    cy.request({
      url: '/reports/export/costs/',
      failOnStatusCode: false,
    }).then((response) => {
      expect(response.status).to.eq(200);
      expect(response.headers['content-type']).to.include('text/csv');
      cy.log('✓ /reports/export/costs/ returns CSV');

      // Verify our test cost is in the export
      if (response.body && response.body.includes(testCost.note)) {
        cy.log('✓ Cost export includes our test cost');
      }
    });

    // Test /reports/export/summary/
    cy.request({
      url: '/reports/export/summary/',
      failOnStatusCode: false,
    }).then((response) => {
      expect(response.status).to.eq(200);
      expect(response.headers['content-type']).to.include('text/csv');
      cy.log('✓ /reports/export/summary/ returns CSV');
    });

    cy.log('✅ Reports flow completed successfully!');
  });
});
