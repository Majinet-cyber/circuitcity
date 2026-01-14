/**
 * Header Dropdown Smoke Tests
 * Tests the notification bell and profile/user menu dropdown behavior
 * Verifies Dec 20 clean behavior is maintained:
 * - Dropdowns closed by default
 * - Open on click
 * - Close on outside click
 * - No auto-open behavior
 */

describe('Header Dropdowns', () => {
  beforeEach(() => {
    // Login as manager to see the header
    cy.login('manager');
    // Visit dashboard to ensure header is rendered
    cy.visit('/dashboard/');
    // Wait for page to fully load
    cy.get('.cc-header', { timeout: 10000 }).should('be.visible');
  });

  describe('Notification Dropdown', () => {
    it('should be closed by default on page load', () => {
      // The notification menu should NOT have the 'show' class
      cy.get('[data-testid="notif-menu"]').should('not.have.class', 'show');
      // The toggle button should have aria-expanded="false"
      cy.get('[data-testid="notif-toggle"]').should('have.attr', 'aria-expanded', 'false');
    });

    it('should open when clicking the bell icon', () => {
      // Click the notification button
      cy.get('[data-testid="notif-toggle"]').click();
      // The menu should now be visible
      cy.get('[data-testid="notif-menu"]').should('have.class', 'show');
      cy.get('[data-testid="notif-toggle"]').should('have.attr', 'aria-expanded', 'true');
    });

    it('should close when clicking outside', () => {
      // Open the dropdown
      cy.get('[data-testid="notif-toggle"]').click();
      cy.get('[data-testid="notif-menu"]').should('have.class', 'show');
      
      // Click outside (on the main content area)
      cy.get('main.cc-page').click({ force: true });
      
      // Dropdown should be closed
      cy.get('[data-testid="notif-menu"]').should('not.have.class', 'show');
    });

    it('should remain closed after page refresh', () => {
      // Reload the page
      cy.reload();
      cy.get('.cc-header', { timeout: 10000 }).should('be.visible');
      
      // Verify dropdown is still closed
      cy.get('[data-testid="notif-menu"]').should('not.have.class', 'show');
      cy.get('[data-testid="notif-toggle"]').should('have.attr', 'aria-expanded', 'false');
    });
  });

  describe('User/Profile Dropdown', () => {
    it('should be closed by default on page load', () => {
      // The user menu should NOT have the 'show' class
      cy.get('#userMenu').should('not.have.class', 'show');
      // The toggle button should have aria-expanded="false"
      cy.get('#userMenuBtn').should('have.attr', 'aria-expanded', 'false');
    });

    it('should open when clicking the avatar', () => {
      // Click the user menu button
      cy.get('#userMenuBtn').click();
      // The menu should now be visible
      cy.get('#userMenu').should('have.class', 'show');
      cy.get('#userMenuBtn').should('have.attr', 'aria-expanded', 'true');
    });

    it('should close when clicking outside', () => {
      // Open the dropdown
      cy.get('#userMenuBtn').click();
      cy.get('#userMenu').should('have.class', 'show');
      
      // Click outside (on the main content area)
      cy.get('main.cc-page').click({ force: true });
      
      // Dropdown should be closed
      cy.get('#userMenu').should('not.have.class', 'show');
    });

    it('should contain Profile & Settings link', () => {
      // Open the dropdown
      cy.get('#userMenuBtn').click();
      cy.get('#userMenu').should('have.class', 'show');
      
      // Verify menu contents
      cy.get('#userMenu').contains('Profile').should('be.visible');
      cy.get('#userMenu').contains('Settings').should('be.visible');
      cy.get('#userMenu').contains('Logout').should('be.visible');
    });
  });

  describe('Dropdown Isolation', () => {
    it('should only have one notification dropdown open at a time', () => {
      // Open notification dropdown
      cy.get('[data-testid="notif-toggle"]').click();
      cy.get('[data-testid="notif-menu"]').should('have.class', 'show');
      
      // Click user menu - notification should close
      cy.get('#userMenuBtn').click();
      cy.get('#userMenu').should('have.class', 'show');
      cy.get('[data-testid="notif-menu"]').should('not.have.class', 'show');
    });

    it('should not have duplicate dropdown elements', () => {
      // There should be exactly one notification dropdown
      cy.get('[data-testid="notif-dropdown"]').should('have.length', 1);
      cy.get('[data-testid="notif-menu"]').should('have.length', 1);
      
      // There should be exactly one user menu
      cy.get('#userMenu').should('have.length', 1);
      cy.get('#userMenuBtn').should('have.length', 1);
    });
  });

  describe('Navigation Persistence', () => {
    it('should keep dropdowns closed after navigating to another page', () => {
      // Click a navigation link (e.g., to stock list)
      cy.get('.cc-sidebar a[href*="inventory"]').first().click({ force: true });
      
      // Wait for page to load
      cy.get('.cc-header', { timeout: 10000 }).should('be.visible');
      
      // Verify dropdowns are closed
      cy.get('[data-testid="notif-menu"]').should('not.have.class', 'show');
      cy.get('#userMenu').should('not.have.class', 'show');
    });
  });
});

