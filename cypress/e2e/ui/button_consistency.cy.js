// cypress/e2e/ui/button_consistency.cy.js
/**
 * Cypress E2E tests for Button Consistency (SSOT)
 * Verifies primary buttons use consistent blue color and hover states across all verticals.
 */

describe('Button Consistency - SSOT Design Tokens', () => {
  beforeEach(() => {
    cy.visit('/accounts/login/');
    cy.get('input[name="username"]').type('testmanager');
    cy.get('input[name="password"]').type('testpass123');
    cy.get('button[type="submit"]').click();
    cy.url().should('not.include', '/login');
  });

  describe('Primary Button Styling', () => {
    it('should have consistent primary button color on settings page', () => {
      cy.visit('/accounts/settings/profile/');
      
      // Primary button should use --cc-primary color
      cy.get('.btn-cc-primary, .btn-primary')
        .first()
        .should('have.css', 'background-color', 'rgb(37, 99, 235)'); // #2563eb
    });

    it('should have consistent hover state (same blue, slightly darker)', () => {
      cy.visit('/accounts/settings/profile/');
      
      const primaryButton = cy.get('.btn-cc-primary, .btn-primary').first();
      
      // Get initial color
      primaryButton.should('have.css', 'background-color', 'rgb(37, 99, 235)'); // #2563eb
      
      // Hover over button
      primaryButton.trigger('mouseover');
      
      // Hover color should be darker blue (NOT a different blue)
      // Expected: rgb(29, 78, 216) = #1d4ed8 (--cc-primary-hover)
      primaryButton.should('have.css', 'background-color', 'rgb(29, 78, 216)');
    });

    it('should NOT flip to a weird blue on hover', () => {
      cy.visit('/accounts/settings/profile/');
      
      const button = cy.get('.btn-cc-primary, .btn-primary').first();
      
      // Store original color
      let originalColor;
      button.then($btn => {
        originalColor = $btn.css('background-color');
      });
      
      // Hover
      button.trigger('mouseover');
      
      // Hover color should be in the same blue family (not cyan, not purple, etc.)
      button.then($btn => {
        const hoverColor = $btn.css('background-color');
        
        // Both should be blue (R < G and R < B in RGB)
        const parseRgb = (rgb) => {
          const match = rgb.match(/rgb\((\d+), (\d+), (\d+)\)/);
          return match ? [parseInt(match[1]), parseInt(match[2]), parseInt(match[3])] : [0, 0, 0];
        };
        
        const [r, g, b] = parseRgb(hoverColor);
        
        // Blue hue: B should be highest, R should be lowest
        expect(b).to.be.greaterThan(r);
        expect(b).to.be.greaterThan(g);
      });
    });
  });

  describe('Button Consistency Across Verticals', () => {
    const verticalsToTest = [
      '/inventory/dashboard/',
      '/inventory/phones/dashboard/',
      '/inventory/cement/dashboard/',
      '/inventory/gym/dashboard/',
    ];

    verticalsToTest.forEach((url) => {
      it(`should have consistent primary button styling on ${url}`, () => {
        cy.visit(url);
        
        // Find any primary button
        cy.get('.btn-primary, .btn-cc-primary').then($buttons => {
          if ($buttons.length > 0) {
            // Check first primary button has correct color
            cy.wrap($buttons.first())
              .should('have.css', 'background-color', 'rgb(37, 99, 235)'); // #2563eb
          }
        });
      });
    });
  });

  describe('Secondary and Outline Buttons', () => {
    it('should have consistent secondary button styling', () => {
      cy.visit('/accounts/settings/profile/');
      
      cy.get('.btn-secondary, .btn-outline-secondary').then($buttons => {
        if ($buttons.length > 0) {
          // Secondary buttons should NOT be primary blue
          cy.wrap($buttons.first())
            .should('not.have.css', 'background-color', 'rgb(37, 99, 235)');
        }
      });
    });

    it('should have transparent outline button background', () => {
      cy.visit('/accounts/settings/profile/');
      
      cy.get('.btn-outline-primary, .btn-cc-outline').then($buttons => {
        if ($buttons.length > 0) {
          cy.wrap($buttons.first())
            .should('have.css', 'background-color', 'rgba(0, 0, 0, 0)'); // transparent
        }
      });
    });
  });

  describe('Button Focus States', () => {
    it('should have accessible focus ring on primary button', () => {
      cy.visit('/accounts/settings/profile/');
      
      const button = cy.get('.btn-cc-primary, .btn-primary').first();
      
      // Focus button
      button.focus();
      
      // Should have focus outline (accessibility)
      button.should('have.css', 'box-shadow').and('not.equal', 'none');
    });
  });

  describe('Danger Zone Buttons', () => {
    it('should have red danger buttons (not blue)', () => {
      cy.visit('/accounts/settings/danger-zone/');
      
      cy.get('.btn-danger').then($buttons => {
        if ($buttons.length > 0) {
          // Danger buttons should be red
          cy.wrap($buttons.first())
            .should('have.css', 'background-color')
            .and('match', /rgb\(2[0-9]{2}, [0-9]+, [0-9]+\)/); // Red-ish color
        }
      });
    });
  });

  describe('Font Consistency', () => {
    it('should use consistent font family across buttons', () => {
      cy.visit('/accounts/settings/profile/');
      
      cy.get('.btn-cc-primary, .btn-primary').first()
        .should('have.css', 'font-family')
        .and('include', 'system-ui'); // or whatever your --cc-font-family is
    });

    it('should have consistent font weight on buttons', () => {
      cy.visit('/accounts/settings/profile/');
      
      cy.get('.btn-cc-primary, .btn-primary').first()
        .should('have.css', 'font-weight', '500'); // Medium weight
    });
  });
});

