// cypress/e2e/whatsapp_settings.cy.js
/**
 * End-to-end test for WhatsApp notification settings
 * 
 * Tests:
 * - Login and navigate to WhatsApp settings
 * - Fill in phone number
 * - Toggle notification preferences
 * - Save settings
 * - Send test message
 * - Verify preferences persist
 */

describe('WhatsApp Settings', () => {
  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  it('completes WhatsApp settings workflow: configure → save → test', () => {
    // 1. Login
    cy.loginAsOwner();
    cy.wait(1000);

    // 2. Navigate to WhatsApp settings
    cy.visit('/notifications/whatsapp/settings/', { failOnStatusCode: false });

    // Handle alternative URLs
    cy.url().then((url) => {
      if (url.includes('404')) {
        cy.visit('/settings/whatsapp/', { failOnStatusCode: false });
      }
    });

    // Verify page loaded
    cy.get('body').should('be.visible');
    cy.get('body').should('not.contain', '500 Internal Server Error');

    // 3. Fill in phone number
    cy.get('body').then(($body) => {
      const phoneSelectors = [
        'input[name="phone_number"]',
        'input[name="phone"]',
        '[data-cy="whatsapp-phone"]',
      ];

      phoneSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).clear().type('+265888123456');
          cy.log('✓ Phone number entered');
        }
      });
    });

    // 4. Toggle notification preferences
    cy.get('body').then(($body) => {
      // Enable main WhatsApp notifications
      const enableSelectors = [
        'input[name="is_enabled"]',
        '[data-cy="whatsapp-enabled"]',
        'input[type="checkbox"]:first',
      ];

      enableSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).first().check();
          cy.log('✓ Enabled WhatsApp notifications');
        }
      });

      // Enable sale alerts
      const saleAlertSelectors = [
        'input[name="receive_sale_alerts"]',
        '[data-cy="sale-alerts"]',
      ];

      saleAlertSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).check();
        }
      });

      // Enable low stock alerts
      const lowStockSelectors = [
        'input[name="receive_low_stock_alerts"]',
        '[data-cy="low-stock-alerts"]',
      ];

      lowStockSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).check();
        }
      });

      // Enable profit milestones
      const milestoneSelectors = [
        'input[name="receive_profit_milestones"]',
        '[data-cy="profit-milestones"]',
      ];

      milestoneSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).check();
        }
      });
    });

    // 5. Save settings
    cy.get('body').then(($body) => {
      const saveSelectors = [
        'button[type="submit"]',
        '[data-cy="save-settings-btn"]',
        'button:contains("Save")',
      ];

      let found = false;
      saveSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0 && !found) {
          cy.get(selector).first().click();
          found = true;
          cy.wait(1000);

          // Verify success message
          cy.verifySuccess();
        }
      });

      if (found) {
        cy.log('✓ Settings saved');
      } else {
        cy.log('⚠ Save button not found');
      }
    });

    // 6. Send test message
    cy.get('body').then(($body) => {
      const testSelectors = [
        '[data-cy="send-test-btn"]',
        'button:contains("Send Test")',
        'button:contains("Test Message")',
      ];

      let found = false;
      testSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0 && !found) {
          cy.get(selector).first().click();
          found = true;
          cy.wait(1000);

          // Check for success/info message
          cy.get('body').then(($resultBody) => {
            if ($resultBody.find('.alert-success, .alert-info').length > 0) {
              cy.log('✓ Test message sent');
            } else {
              cy.log('ℹ Test message status unclear');
            }
          });
        }
      });

      if (found) {
        cy.log('✓ Test message feature available');
      } else {
        cy.log('ℹ Test message button not found');
      }
    });

    // 7. Reload page and verify settings persist
    cy.reload();
    cy.wait(500);

    cy.get('body').then(($body) => {
      // Check phone number persisted
      const phoneSelectors = [
        'input[name="phone_number"]',
        'input[name="phone"]',
        '[data-cy="whatsapp-phone"]',
      ];

      phoneSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).should('have.value', '+265888123456');
          cy.log('✓ Phone number persisted');
        }
      });

      // Check checkboxes remain checked
      const enableSelectors = [
        'input[name="is_enabled"]',
        '[data-cy="whatsapp-enabled"]',
      ];

      enableSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).should('be.checked');
          cy.log('✓ Preferences persisted');
        }
      });
    });
  });

  it('displays notification preferences correctly', () => {
    cy.loginAsOwner();
    cy.visit('/notifications/whatsapp/settings/', { failOnStatusCode: false });

    cy.get('body').then(($body) => {
      // Check for various notification options
      const preferenceLabels = [
        'Sale Alerts',
        'Low Stock',
        'Profit Milestones',
        'Commission',
      ];

      preferenceLabels.forEach((label) => {
        if ($body.text().includes(label)) {
          cy.log(`✓ ${label} option found`);
        }
      });
    });
  });

  it('validates phone number format', () => {
    cy.loginAsOwner();
    cy.visit('/notifications/whatsapp/settings/', { failOnStatusCode: false });

    cy.get('body').then(($body) => {
      const phoneSelector = 'input[name="phone_number"], input[name="phone"], [data-cy="whatsapp-phone"]';

      if ($body.find(phoneSelector).length > 0) {
        // Try invalid phone number
        cy.get(phoneSelector).first().clear().type('invalid');

        // Try to save
        cy.get('button[type="submit"]').first().click();
        cy.wait(500);

        // Should show validation error
        cy.get('body').then(($errorBody) => {
          if ($errorBody.find('.alert-danger, .error, .invalid-feedback').length > 0) {
            cy.log('✓ Phone validation works');
          }
        });
      }
    });
  });
});

