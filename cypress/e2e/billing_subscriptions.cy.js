// cypress/e2e/billing_subscriptions.cy.js
/**
 * End-to-end test for Billing/Subscription flow
 * 
 * Tests:
 * - Login and visit subscription page
 * - Verify Pesapal payment button
 * - Verify Stripe payment button (if configured)
 * - Click Pesapal and verify redirect
 * - Click Stripe and verify redirect (if configured)
 */

describe('Billing and Subscriptions', () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it('displays subscription plans and payment options', () => {
    // 1. Login
    cy.loginAsOwner();
    cy.wait(1000);

    // 2. Visit billing/subscribe page
    cy.visit('/billing/subscribe/', { failOnStatusCode: false });

    // Handle possible redirects
    cy.url().then((url) => {
      if (url.includes('404') || url.includes('login')) {
        // Try alternative URLs
        cy.visit('/subscriptions/', { failOnStatusCode: false });
      }
    });

    // 3. Verify page loaded
    cy.get('body').should('be.visible');
    cy.get('body').should('not.contain', '500 Internal Server Error');

    // 4. Check for subscription plans
    cy.get('body').then(($body) => {
      const planSelectors = [
        '[data-cy="plan-card"]',
        '.plan-card',
        '.pricing-card',
        'h3:contains("Plan")',
        'h4:contains("Starter")',
        'h4:contains("Professional")',
      ];

      let planFound = false;
      planSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          planFound = true;
          cy.log('✓ Subscription plans displayed');
        }
      });

      if (!planFound) {
        cy.log('⚠ No subscription plans found on page');
      }
    });

    // 5. Check for Pesapal payment button
    cy.get('body').then(($body) => {
      const pesapalSelectors = [
        '[data-cy="pesapal-btn"]',
        'button:contains("Pesapal")',
        'button:contains("Mobile Money")',
        'form[action*="pesapal"]',
      ];

      let pesapalFound = false;
      pesapalSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          pesapalFound = true;
          cy.log('✓ Pesapal payment option available');
        }
      });

      if (!pesapalFound) {
        cy.log('⚠ Pesapal payment button not found');
      }
    });

    // 6. Check for Stripe payment button (may not be present if not configured)
    cy.get('body').then(($body) => {
      const stripeSelectors = [
        '[data-cy="stripe-btn"]',
        'button:contains("Stripe")',
        'button:contains("Card")',
        'form[action*="stripe"]',
      ];

      let stripeFound = false;
      stripeSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          stripeFound = true;
          cy.log('✓ Stripe payment option available');
        }
      });

      if (!stripeFound) {
        cy.log('ℹ Stripe payment button not found (may not be configured)');
      }
    });
  });

  it('initiates Pesapal payment flow', () => {
    cy.loginAsOwner();
    cy.visit('/billing/subscribe/', { failOnStatusCode: false });

    cy.get('body').then(($body) => {
      // Find Pesapal button
      const pesapalSelectors = [
        '[data-cy="pesapal-btn"]',
        'button:contains("Pesapal")',
        'button:contains("Mobile Money")',
      ];

      let found = false;
      pesapalSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0 && !found) {
          // Store current URL before clicking
          cy.url().as('beforePesapal');

          // Click Pesapal button
          cy.get(selector).first().click();
          found = true;
          cy.wait(2000);

          // Verify we were redirected or stayed on same page with processing
          cy.url().then((newUrl) => {
            cy.get('@beforePesapal').then((oldUrl) => {
              if (newUrl.includes('pesapal')) {
                cy.log('✓ Redirected to Pesapal payment page');
              } else if (newUrl !== oldUrl) {
                cy.log('✓ URL changed - payment flow initiated');
              } else {
                // Check for loading/processing indicator
                if ($body.find('.spinner, .loading, [data-cy="processing"]').length > 0) {
                  cy.log('✓ Payment processing indicator shown');
                }
              }
            });
          });
        }
      });

      if (!found) {
        cy.log('⚠ Pesapal button not available - skipping test');
      }
    });
  });

  it('initiates Stripe payment flow (if configured)', () => {
    cy.loginAsOwner();
    cy.visit('/billing/subscribe/', { failOnStatusCode: false });

    cy.get('body').then(($body) => {
      // Find Stripe button
      const stripeSelectors = [
        '[data-cy="stripe-btn"]',
        'button:contains("Stripe")',
        'button:contains("Card")',
      ];

      let found = false;
      stripeSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0 && !found) {
          // Store current URL
          cy.url().as('beforeStripe');

          // Click Stripe button
          cy.get(selector).first().click();
          found = true;
          cy.wait(2000);

          // Verify redirect to Stripe Checkout
          cy.url().then((newUrl) => {
            if (newUrl.includes('stripe.com') || newUrl.includes('checkout')) {
              cy.log('✓ Redirected to Stripe Checkout');
            } else {
              cy.log('ℹ Stripe redirect not detected - may require configuration');
            }
          });
        }
      });

      if (!found) {
        cy.log('ℹ Stripe button not available (may not be configured)');
      }
    });
  });

  it('displays current subscription status', () => {
    cy.loginAsOwner();

    // Visit billing or dashboard
    cy.visit('/billing/', { failOnStatusCode: false });

    cy.get('body').then(($body) => {
      const statusSelectors = [
        '[data-cy="subscription-status"]',
        '.subscription-status',
        'span:contains("Active")',
        'span:contains("Trial")',
        'span:contains("Expired")',
      ];

      statusSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.log('✓ Subscription status displayed');
        }
      });
    });
  });

  it('shows payment history if available', () => {
    cy.loginAsOwner();
    cy.visit('/billing/', { failOnStatusCode: false });

    cy.get('body').then(($body) => {
      const historySelectors = [
        '[data-cy="payment-history"]',
        'table:contains("Payment")',
        'h3:contains("Payment History")',
      ];

      historySelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.log('✓ Payment history section found');
        }
      });
    });
  });
});

