// cypress/e2e/settings/settings_white_ui.cy.js
/**
 * Cypress E2E tests for Settings UI (Clean White Theme)
 * Verifies that settings pages have consistent white background and no blue tinted panels.
 */

describe('Settings UI - Clean White Theme', () => {
  beforeEach(() => {
    // Login as manager
    cy.visit('/accounts/login/');
    cy.get('input[name="username"]').type('testmanager');
    cy.get('input[name="password"]').type('testpass123');
    cy.get('button[type="submit"]').click();
    
    // Wait for login to complete
    cy.url().should('not.include', '/login');
  });

  describe('Settings Profile Page', () => {
    it('should have clean white background', () => {
      cy.visit('/accounts/settings/profile/');
      
      // Check main settings root has white background
      cy.get('[data-testid="settings-root"]')
        .should('exist')
        .should('have.css', 'background-color', 'rgb(255, 255, 255)'); // white
    });

    it('should have white card backgrounds', () => {
      cy.visit('/accounts/settings/profile/');
      
      // Settings card should have white background
      cy.get('.settings-card')
        .should('exist')
        .should('have.css', 'background-color', 'rgb(255, 255, 255)'); // white
    });

    it('should not have blue tinted backgrounds', () => {
      cy.visit('/accounts/settings/profile/');
      
      // Check that no elements have blue-ish backgrounds (except buttons/badges)
      cy.get('.settings-card').within(() => {
        cy.get('.card-body')
          .should('have.css', 'background-color', 'rgb(255, 255, 255)');
      });
    });

    it('should have consistent typography', () => {
      cy.visit('/accounts/settings/profile/');
      
      cy.get('.settings-title')
        .should('exist')
        .should('have.css', 'font-weight', '700'); // bold
    });
  });

  describe('Settings Security Page', () => {
    it('should have clean white background', () => {
      cy.visit('/accounts/settings/security/');
      
      cy.get('[data-testid="settings-root"]')
        .should('have.css', 'background-color', 'rgb(255, 255, 255)');
    });

    it('should render password change card with white background', () => {
      cy.visit('/accounts/settings/security/');
      
      cy.contains('Change Password')
        .closest('.card')
        .should('have.css', 'background-color', 'rgb(255, 255, 255)');
    });

    it('should render 2FA card with white background', () => {
      cy.visit('/accounts/settings/security/');
      
      cy.contains('Two-Factor Authentication')
        .closest('.card')
        .should('have.css', 'background-color', 'rgb(255, 255, 255)');
    });
  });

  describe('Settings Sessions Page', () => {
    it('should have clean white background', () => {
      cy.visit('/accounts/settings/sessions/');
      
      cy.get('[data-testid="settings-root"]')
        .should('have.css', 'background-color', 'rgb(255, 255, 255)');
    });
  });

  describe('Settings Navigation Tabs', () => {
    it('should have clean tabs with no blue background', () => {
      cy.visit('/accounts/settings/profile/');
      
      cy.get('.nav-tabs').within(() => {
        // Inactive tabs should have transparent background
        cy.get('.nav-link:not(.active)')
          .first()
          .should('have.css', 'background-color', 'rgba(0, 0, 0, 0)'); // transparent
        
        // Active tab should also be transparent (only blue underline)
        cy.get('.nav-link.active')
          .should('have.css', 'background-color', 'rgba(0, 0, 0, 0)'); // transparent
      });
    });
  });

  describe('Settings Form Elements', () => {
    it('should have clean white form inputs', () => {
      cy.visit('/accounts/settings/profile/');
      
      cy.get('.form-control').first().should('have.css', 'background-color', 'rgb(255, 255, 255)');
    });

    it('should have white select dropdowns', () => {
      cy.visit('/accounts/settings/profile/');
      
      cy.get('.form-select').first().should('have.css', 'background-color', 'rgb(255, 255, 255)');
    });
  });
});

