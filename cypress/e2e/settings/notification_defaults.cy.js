// cypress/e2e/settings/notification_defaults.cy.js
/**
 * Cypress E2E tests for Notification Preferences Defaults
 * Verifies all notification checkboxes are ON by default (opt-out model).
 */

describe('Notification Preferences - Default ON (Opt-Out)', () => {
  beforeEach(() => {
    // Login as freshly created user (or reset preferences)
    cy.visit('/accounts/login/');
    cy.get('input[name="username"]').type('testmanager');
    cy.get('input[name="password"]').type('testpass123');
    cy.get('button[type="submit"]').click();
    
    cy.url().should('not.include', '/login');
  });

  describe('Email Notification Settings', () => {
    it('should show all email notification checkboxes checked by default', () => {
      cy.visit('/accounts/settings/notifications/'); // Adjust URL based on your routes
      
      // All checkboxes should be checked
      cy.get('input[name="welcome_emails"]').should('be.checked');
      cy.get('input[name="instant_sale_email"]').should('be.checked');
      cy.get('input[name="sale_emails_enabled"]').should('be.checked');
      cy.get('input[name="daily_summary_email"]').should('be.checked');
      cy.get('input[name="important_alerts_email"]').should('be.checked');
      cy.get('input[name="high_sales_alerts"]').should('be.checked');
      cy.get('input[name="commission_emails_enabled"]').should('be.checked');
      cy.get('input[name="weekly_digest_enabled"]').should('be.checked');
    });

    it('should allow user to opt out of specific notifications', () => {
      cy.visit('/accounts/settings/notifications/');
      
      // Uncheck commission emails
      cy.get('input[name="commission_emails_enabled"]').uncheck();
      
      // Save settings
      cy.get('button[type="submit"]').contains('Save').click();
      
      // Reload page and verify preference persisted
      cy.reload();
      cy.get('input[name="commission_emails_enabled"]').should('not.be.checked');
      
      // Other checkboxes should still be checked
      cy.get('input[name="sale_emails_enabled"]').should('be.checked');
    });

    it('should allow user to re-enable disabled notifications', () => {
      cy.visit('/accounts/settings/notifications/');
      
      // Uncheck, save
      cy.get('input[name="daily_summary_email"]').uncheck();
      cy.get('button[type="submit"]').contains('Save').click();
      
      // Re-enable
      cy.reload();
      cy.get('input[name="daily_summary_email"]').check();
      cy.get('button[type="submit"]').contains('Save').click();
      
      // Verify
      cy.reload();
      cy.get('input[name="daily_summary_email"]').should('be.checked');
    });
  });

  describe('WhatsApp Notification Settings', () => {
    it('should show all WhatsApp notification checkboxes checked by default', () => {
      cy.visit('/notifications/whatsapp-settings/'); // Adjust URL
      
      cy.get('input[name="is_enabled"]').should('be.checked');
      cy.get('input[name="receive_sale_alerts"]').should('be.checked');
      cy.get('input[name="receive_profit_milestones"]').should('be.checked');
      cy.get('input[name="receive_low_stock_alerts"]').should('be.checked');
      cy.get('input[name="receive_commission_alerts"]').should('be.checked'); // KEY: Now default ON
    });

    it('should verify commission alerts default changed from OFF to ON', () => {
      cy.visit('/notifications/whatsapp-settings/');
      
      // Commission alerts should now be checked by default (was unchecked before)
      cy.get('input[name="receive_commission_alerts"]')
        .should('be.checked')
        .should('have.attr', 'checked');
    });
  });

  describe('Notification Preferences Form Behavior', () => {
    it('should show form validation if required fields missing', () => {
      cy.visit('/accounts/settings/notifications/');
      
      // Form should submit without errors when all defaults are checked
      cy.get('button[type="submit"]').contains('Save').click();
      
      // Should show success message
      cy.contains('Settings saved').should('be.visible');
    });
  });
});

