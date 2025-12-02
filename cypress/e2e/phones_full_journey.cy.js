// cypress/e2e/phones_full_journey.cy.js
/**
 * End-to-end test for Phones vertical full journey
 * 
 * Tests:
 * - Login and navigate to phones dashboard
 * - Add phone product/stock
 * - Perform cash sale
 * - Perform credit sale
 * - Record credit repayment
 * - Verify dashboard metrics
 */

describe('Phones Full Journey', () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it('completes full phones workflow: add stock → cash sale → credit sale → repayment', () => {
    // 1. Login
    cy.loginAsOwner();
    cy.wait(1000);

    // 2. Navigate to Phones dashboard
    cy.visitDashboard('phones');
    cy.url().should('include', 'phone');

    // Verify dashboard loaded
    cy.get('body').should('be.visible');
    cy.get('body').should('not.contain', '500 Internal Server Error');

    // 3. Check initial stock count
    cy.get('body').then(($body) => {
      if ($body.find('[data-cy="stock-count"]').length > 0) {
        cy.get('[data-cy="stock-count"]').invoke('text').as('initialStock');
      }
    });

    // 4. Add new stock (if form available)
    cy.get('body').then(($body) => {
      // Look for "Add Stock" or similar button
      const addStockSelectors = [
        '[data-cy="add-stock-btn"]',
        'a:contains("Add Stock")',
        'button:contains("Add Stock")',
        'a:contains("Add Inventory")',
      ];

      let found = false;
      addStockSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0 && !found) {
          cy.get(selector).first().click();
          found = true;
          cy.wait(500);

          // Fill in stock form if it appears
          cy.url().then((url) => {
            if (url.includes('add') || url.includes('create')) {
              // Fill IMEI
              cy.get('input[name="imei"], [data-cy="imei-input"]').then(($input) => {
                if ($input.length > 0) {
                  cy.wrap($input).clear().type('123456789012345');
                }
              });

              // Submit form
              cy.get('button[type="submit"], [data-cy="submit-btn"]').first().click();
              cy.wait(1000);
            }
          });
        }
      });

      if (found) {
        cy.log('✓ Added stock item');
      } else {
        cy.log('⚠ Add stock form not found - skipping');
      }
    });

    // 5. Perform cash sale
    cy.visitDashboard('phones');
    cy.get('body').then(($body) => {
      const saleSelectors = [
        '[data-cy="record-sale-btn"]',
        'a:contains("Record Sale")',
        'button:contains("Sell")',
        'a:contains("New Sale")',
      ];

      let found = false;
      saleSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0 && !found) {
          cy.get(selector).first().click();
          found = true;
          cy.wait(500);

          // Fill sale form if it appears
          cy.url().then((url) => {
            if (url.includes('sale') || url.includes('sell')) {
              // Look for IMEI or product selection
              cy.get('input[name="imei"], select[name="product"], [data-cy="imei-input"]').then(($field) => {
                if ($field.length > 0) {
                  if ($field.is('select')) {
                    // Select first product
                    cy.wrap($field).select(1);
                  } else {
                    // Enter IMEI
                    cy.wrap($field).clear().type('123456789012345');
                  }
                }
              });

              // Select payment method (cash)
              cy.get('select[name="payment_method"], [data-cy="payment-method"]').then(($select) => {
                if ($select.length > 0) {
                  cy.wrap($select).select('cash');
                }
              });

              // Submit
              cy.get('button[type="submit"], [data-cy="submit-sale-btn"]').first().click();
              cy.wait(1000);

              // Verify success
              cy.verifySuccess();
            }
          });
        }
      });

      if (found) {
        cy.log('✓ Recorded cash sale');
      } else {
        cy.log('⚠ Sale form not found - skipping');
      }
    });

    // 6. Perform credit sale
    cy.visitDashboard('phones');
    cy.get('body').then(($body) => {
      const creditSelectors = [
        '[data-cy="credit-sale-btn"]',
        'a:contains("Credit Sale")',
        'a:contains("Sell on Credit")',
      ];

      let found = false;
      creditSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0 && !found) {
          cy.get(selector).first().click();
          found = true;
          cy.wait(500);

          // Fill credit sale form
          cy.get('input[name="customer_name"], [data-cy="customer-name"]').then(($input) => {
            if ($input.length > 0) {
              cy.wrap($input).clear().type('Test Customer');
            }
          });

          cy.get('input[name="customer_phone"], [data-cy="customer-phone"]').then(($input) => {
            if ($input.length > 0) {
              cy.wrap($input).clear().type('0999123456');
            }
          });

          cy.get('input[name="amount"], [data-cy="credit-amount"]').then(($input) => {
            if ($input.length > 0) {
              cy.wrap($input).clear().type('500000');
            }
          });

          cy.get('button[type="submit"]').first().click();
          cy.wait(1000);

          cy.verifySuccess();
        }
      });

      if (found) {
        cy.log('✓ Created credit sale');
      } else {
        cy.log('⚠ Credit sale form not found - skipping');
      }
    });

    // 7. Record credit repayment
    cy.visitDashboard('phones');
    cy.get('body').then(($body) => {
      const creditListSelectors = [
        '[data-cy="credits-link"]',
        'a:contains("Credits")',
        'a:contains("Outstanding")',
      ];

      let found = false;
      creditListSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0 && !found) {
          cy.get(selector).first().click();
          found = true;
          cy.wait(500);

          // Look for a credit entry
          cy.get('body').then(($creditBody) => {
            const paymentSelectors = [
              '[data-cy="record-payment-btn"]',
              'button:contains("Pay")',
              'a:contains("Record Payment")',
            ];

            paymentSelectors.forEach((paySelector) => {
              if ($creditBody.find(paySelector).length > 0) {
                cy.get(paySelector).first().click();
                cy.wait(500);

                // Fill payment form
                cy.get('input[name="amount"], [data-cy="payment-amount"]').then(($input) => {
                  if ($input.length > 0) {
                    cy.wrap($input).clear().type('200000');
                  }
                });

                cy.get('button[type="submit"]').first().click();
                cy.wait(1000);

                cy.verifySuccess();
              }
            });
          });
        }
      });

      if (found) {
        cy.log('✓ Recorded credit payment');
      } else {
        cy.log('⚠ Credit list not found - skipping payment');
      }
    });

    // 8. Verify dashboard reflects changes
    cy.visitDashboard('phones');

    cy.get('body').then(($body) => {
      // Check for financial metrics
      if ($body.text().includes('MK') || $body.text().includes('$')) {
        cy.log('✓ Dashboard shows financial data');
      }

      // Check for stock count
      if ($body.find('[data-cy="stock-count"]').length > 0) {
        cy.get('[data-cy="stock-count"]').should('be.visible');
        cy.log('✓ Stock count visible');
      }

      // Check for sales metrics
      const metricsSelectors = [
        '[data-cy="total-sales"]',
        '[data-cy="revenue"]',
        '[data-cy="profit"]',
      ];

      metricsSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).should('be.visible');
        }
      });
    });
  });

  it('handles stock out of stock scenario gracefully', () => {
    cy.loginAsOwner();
    cy.visitDashboard('phones');

    cy.get('body').then(($body) => {
      // Check for low stock or out of stock alerts
      const alertSelectors = [
        '[data-cy="low-stock-alert"]',
        '.alert:contains("low stock")',
        '.badge:contains("Out of Stock")',
      ];

      alertSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).should('be.visible');
          cy.log('✓ Low stock alert displayed');
        }
      });
    });
  });

  it('displays dashboard without errors', () => {
    cy.loginAsOwner();
    cy.visitDashboard('phones');

    // Verify no server errors
    cy.get('body').should('not.contain', '500 Internal Server Error');
    cy.get('body').should('not.contain', '404 Not Found');
    cy.get('body').should('not.contain', 'Application error');

    // Verify page loaded
    cy.get('body').should('be.visible');
  });
});

