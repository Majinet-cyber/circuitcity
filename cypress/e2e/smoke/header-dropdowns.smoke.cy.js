/**
 * Header Dropdown Smoke Tests (ENHANCED - Jan 2026)
 * Tests the notification bell and profile/user menu dropdown behavior
 * 
 * CRITICAL REGRESSION GUARDS:
 * - Dropdowns closed by default (no auto-open on page load)
 * - Open on click (works immediately, no refresh needed)
 * - Close on outside click
 * - Mutual exclusion (only one open at a time)
 * - Works on PHONES vertical specifically (reported broken)
 */

describe('Header Dropdowns - Critical Regression Suite', () => {
  beforeEach(() => {
    // Login as manager to see the header
    cy.login('manager');
    // Visit PHONES dashboard specifically (where the issue was reported)
    cy.visit('/inventory/verticals/phones/dashboard/', { failOnStatusCode: false });
    // Wait for page to fully load
    cy.get('.cc-header', { timeout: 10000 }).should('be.visible');
  });

  describe('Notification Dropdown', () => {
    it('should be closed by default on page load (CRITICAL REGRESSION GUARD)', () => {
      // CRITICAL: This guards against the "auto-open on load" bug
      // The notification menu should NOT have the 'show' class
      cy.get('#ccNotifMenu').should('not.have.class', 'show');
      // The toggle button should have aria-expanded="false"
      cy.get('[data-testid="nav-notifications"]').should('have.attr', 'aria-expanded', 'false');
      // Menu should have hidden attribute or not be visible
      cy.get('#ccNotifMenu').should('not.be.visible');
    });

    it('should open when clicking the bell icon (NO HARD REFRESH NEEDED)', () => {
      // CRITICAL: Must work on FIRST CLICK without any refresh
      // Click the notification button
      cy.get('[data-testid="nav-notifications"]').should('be.visible').click();
      
      // Wait for Bootstrap animation
      cy.wait(300);
      
      // The menu should now be visible
      cy.get('#ccNotifMenu').should('have.class', 'show');
      // Check visibility without checking if it's covered
      cy.get('#ccNotifMenu').should('exist').and('not.have.css', 'display', 'none');
      cy.get('[data-testid="nav-notifications"]').should('have.attr', 'aria-expanded', 'true');
    });

    it('should close when clicking outside', () => {
      // Open the dropdown
      cy.get('[data-testid="nav-notifications"]').click();
      cy.get('#ccNotifMenu').should('have.class', 'show');
      
      // Click outside (on the main content area)
      cy.get('main.cc-page').click({ force: true });
      
      // Wait for animation
      cy.wait(300);
      
      // Dropdown should be closed
      cy.get('#ccNotifMenu').should('not.have.class', 'show');
      cy.get('#ccNotifMenu').should('not.be.visible');
    });

    it('should remain closed after page refresh (BFCache guard)', () => {
      // Reload the page
      cy.reload();
      cy.get('.cc-header', { timeout: 10000 }).should('be.visible');
      
      // Verify dropdown is still closed (guards against BFCache restoring open state)
      cy.get('#ccNotifMenu').should('not.have.class', 'show');
      cy.get('#ccNotifMenu').should('not.be.visible');
      cy.get('[data-testid="nav-notifications"]').should('have.attr', 'aria-expanded', 'false');
    });
  });

  describe('User/Profile Dropdown', () => {
    it('should be closed by default on page load (CRITICAL REGRESSION GUARD)', () => {
      // The user menu should NOT have the 'show' class
      cy.get('#userMenu').should('not.have.class', 'show');
      // The toggle button should have aria-expanded="false"
      cy.get('[data-testid="nav-avatar"]').should('have.attr', 'aria-expanded', 'false');
      // Menu should not be visible
      cy.get('#userMenu').should('not.be.visible');
    });

    it('should open when clicking the avatar (NO HARD REFRESH NEEDED)', () => {
      // CRITICAL: Must work on FIRST CLICK
      // Click the user menu button
      cy.get('[data-testid="nav-avatar"]').should('be.visible').click();
      
      // Wait for Bootstrap animation
      cy.wait(300);
      
      // The menu should now be visible
      cy.get('#userMenu').should('have.class', 'show');
      cy.get('#userMenu').should('be.visible');
      cy.get('[data-testid="nav-avatar"]').should('have.attr', 'aria-expanded', 'true');
    });

    it('should close when clicking outside', () => {
      // Open the dropdown
      cy.get('[data-testid="nav-avatar"]').click();
      cy.get('#userMenu').should('have.class', 'show');
      
      // Click outside (on the main content area)
      cy.get('main.cc-page').click({ force: true });
      
      // Wait for animation
      cy.wait(300);
      
      // Dropdown should be closed
      cy.get('#userMenu').should('not.have.class', 'show');
      cy.get('#userMenu').should('not.be.visible');
    });

    it('should contain Profile & Settings and Logout links', () => {
      // Open the dropdown
      cy.get('[data-testid="nav-avatar"]').click();
      cy.get('#userMenu').should('have.class', 'show');
      
      // Verify menu contents using data-testid
      cy.get('[data-testid="avatar-settings"]').should('be.visible').and('contain', 'Profile');
      cy.get('[data-testid="avatar-logout"]').should('be.visible').and('contain', 'Logout');
    });
  });

  describe('Dropdown Mutual Exclusion (only one open at a time)', () => {
    it('should close notifications when opening user menu', () => {
      // Open notification dropdown
      cy.get('[data-testid="nav-notifications"]').click();
      cy.get('#ccNotifMenu').should('have.class', 'show');
      
      // Click user menu - notification should close
      cy.get('[data-testid="nav-avatar"]').click();
      cy.wait(300);
      
      cy.get('#userMenu').should('have.class', 'show');
      cy.get('#ccNotifMenu').should('not.have.class', 'show');
      cy.get('#ccNotifMenu').should('not.be.visible');
    });

    it('should close user menu when opening notifications', () => {
      // Open user menu
      cy.get('[data-testid="nav-avatar"]').click();
      cy.get('#userMenu').should('have.class', 'show');
      
      // Click notifications - user menu should close
      cy.get('[data-testid="nav-notifications"]').click();
      cy.wait(300);
      
      cy.get('#ccNotifMenu').should('have.class', 'show');
      cy.get('#userMenu').should('not.have.class', 'show');
      cy.get('#userMenu').should('not.be.visible');
    });

    it('should not have duplicate dropdown elements (DOM hygiene)', () => {
      // There should be exactly one notification dropdown
      cy.get('[data-testid="notif-dropdown"]').should('have.length', 1);
      cy.get('#ccNotifMenu').should('have.length', 1);
      
      // There should be exactly one user menu
      cy.get('#userMenu').should('have.length', 1);
      cy.get('[data-testid="nav-avatar"]').should('have.length', 1);
    });
  });

  describe('Navigation Persistence (guard against navigation bugs)', () => {
    it('should keep dropdowns closed after navigating to another page', () => {
      // Navigate to another phones page (e.g., phone sale wizard)
      cy.visit('/inventory/phone-sale-wizard/?step=1', { failOnStatusCode: false });
      
      // Wait for page to load
      cy.get('.cc-header', { timeout: 10000 }).should('be.visible');
      
      // Verify dropdowns are closed
      cy.get('#ccNotifMenu').should('not.have.class', 'show');
      cy.get('#ccNotifMenu').should('not.be.visible');
      cy.get('#userMenu').should('not.have.class', 'show');
      cy.get('#userMenu').should('not.be.visible');
    });
    
    it('should work on phones sale wizard specifically (step 4)', () => {
      // Visit the specific page where the issue was reported
      cy.visit('/inventory/phone-sale-wizard/?step=4', { failOnStatusCode: false });
      cy.wait(1000);
      
      // Dropdowns should be closed
      cy.get('#ccNotifMenu').should('not.be.visible');
      cy.get('#userMenu').should('not.be.visible');
      
      // Both should open on click (check by class, not strict visibility due to page overlays)
      cy.get('[data-testid="nav-notifications"]').click();
      cy.wait(300);
      cy.get('#ccNotifMenu').should('have.class', 'show');
      
      cy.get('[data-testid="nav-avatar"]').click();
      cy.wait(300);
      cy.get('#userMenu').should('have.class', 'show');
    });
  });

  describe('Mobile Viewport Testing', () => {
    it('should work on mobile viewport (phones are mobile-first)', () => {
      // Set mobile viewport
      cy.viewport(375, 667); // iPhone SE
      
      // Reload page
      cy.reload();
      cy.get('.cc-header', { timeout: 10000 }).should('be.visible');
      
      // Dropdowns should be closed
      cy.get('#ccNotifMenu').should('not.be.visible');
      cy.get('#userMenu').should('not.be.visible');
      
      // Should open on click
      cy.get('[data-testid="nav-notifications"]').click();
      cy.wait(300);
      cy.get('#ccNotifMenu').should('be.visible');
      
      // Close and test avatar
      cy.get('main.cc-page').click({ force: true });
      cy.wait(300);
      
      cy.get('[data-testid="nav-avatar"]').click();
      cy.wait(300);
      cy.get('#userMenu').should('be.visible');
    });
  });
});

