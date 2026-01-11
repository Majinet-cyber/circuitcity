/**
 * Cypress E2E Tests for UI/UX Standardization
 * 
 * These tests ensure:
 * 1. Post-auth redirects always go to dashboard (NOT analytics)
 * 2. Mobile nav "Home" goes to vertical dashboard
 * 3. HQ sidebar is sticky and usable
 * 4. Phones stock page shows full IMEI + full product (no ellipsis)
 * 5. Phones wizard cards don't overflow on mobile
 */

describe('UI/UX Standardization Tests', () => {
  
  beforeEach(() => {
    // Login helper
    cy.login('testuser', 'testpass123');
  });

  describe('Post-Auth Redirects (CRITICAL)', () => {
    
    it('should redirect to dashboard after login (NOT analytics)', () => {
      cy.logout();
      
      cy.visit('/accounts/login/');
      cy.get('input[name="identifier"]').type('testuser');
      cy.get('input[name="password"]').type('testpass123');
      cy.get('button[type="submit"]').click();
      
      // Should land on dashboard
      cy.url().should('match', /dashboard|inventory/);
      cy.url().should('not.include', 'analytics');
      cy.url().should('not.include', 'insights');
    });

    it('should redirect to phones dashboard after signup for phones business', () => {
      cy.logout();
      
      // Complete signup flow (simplified)
      cy.visit('/accounts/signup/');
      cy.get('input[name="email"]').type('newuser@example.com');
      cy.get('input[name="username"]').type('newuser');
      cy.get('input[name="password1"]').type('SecurePass123!');
      cy.get('input[name="password2"]').type('SecurePass123!');
      
      // Select phones business
      cy.get('[data-vertical="phones"]').click();
      
      cy.get('button[type="submit"]').click();
      
      // Should land on phones dashboard (NOT analytics)
      cy.url().should('match', /phone|inventory.*dashboard/);
      cy.url().should('not.include', 'analytics');
    });

    it('should redirect to clothing dashboard after signup for clothing business', () => {
      cy.logout();
      
      cy.visit('/accounts/signup/');
      cy.get('input[name="email"]').type('clothinguser@example.com');
      cy.get('input[name="username"]').type('clothinguser');
      cy.get('input[name="password1"]').type('SecurePass123!');
      cy.get('input[name="password2"]').type('SecurePass123!');
      
      // Select clothing business
      cy.get('[data-vertical="clothing"]').click();
      
      cy.get('button[type="submit"]').click();
      
      // Should land on clothing dashboard (NOT analytics)
      cy.url().should('include', 'clothing');
      cy.url().should('include', 'dashboard');
      cy.url().should('not.include', 'analytics');
    });

    it('should redirect to gym dashboard after signup for gym business', () => {
      cy.logout();
      
      cy.visit('/accounts/signup/');
      cy.get('input[name="email"]').type('gymuser@example.com');
      cy.get('input[name="username"]').type('gymuser');
      cy.get('input[name="password1"]').type('SecurePass123!');
      cy.get('input[name="password2"]').type('SecurePass123!');
      
      // Select gym business
      cy.get('[data-vertical="gym"]').click();
      
      cy.get('button[type="submit"]').click();
      
      // Should land on gym dashboard (NOT analytics)
      cy.url().should('include', 'gym');
      cy.url().should('include', 'dashboard');
      cy.url().should('not.include', 'analytics');
    });

  });

  describe('Mobile Bottom Nav (Vertical-Aware)', () => {
    
    beforeEach(() => {
      // Set mobile viewport
      cy.viewport('iphone-x');
    });

    it('should show mobile nav for phones business', () => {
      cy.switchToBusiness('phones');
      cy.visit('/inventory/dashboard/');
      
      // Mobile nav should be visible
      cy.get('.mobile-tabbar').should('be.visible');
      cy.get('[data-cy="mobile-nav-home"]').should('exist');
      cy.get('[data-cy="mobile-nav-scan"]').should('exist');
      cy.get('[data-cy="mobile-nav-sell"]').should('exist');
    });

    it('should navigate to phones dashboard when Home is tapped', () => {
      cy.switchToBusiness('phones');
      cy.visit('/inventory/scan-in/'); // Start on different page
      
      cy.get('[data-cy="mobile-nav-home"]').click();
      
      // Should navigate to phones dashboard
      cy.url().should('match', /phone.*dashboard|inventory.*dashboard/);
      cy.get('[data-cy="mobile-nav-home"]').should('have.class', 'active');
    });

    it('should navigate to clothing dashboard when Home is tapped', () => {
      cy.switchToBusiness('clothing');
      cy.visit('/verticals/clothing/sell/'); // Start on different page
      
      cy.get('[data-cy="mobile-nav-home"]').click();
      
      // Should navigate to clothing dashboard
      cy.url().should('include', 'clothing/dashboard');
      cy.get('[data-cy="mobile-nav-home"]').should('have.class', 'active');
    });

    it('should navigate to gym dashboard when Home is tapped', () => {
      cy.switchToBusiness('gym');
      cy.visit('/gym/members/'); // Start on different page
      
      cy.get('[data-cy="mobile-nav-home"]').click();
      
      // Should navigate to gym dashboard
      cy.url().should('include', 'gym/dashboard');
      cy.get('[data-cy="mobile-nav-home"]').should('have.class', 'active');
    });

    it('should never navigate to analytics when Home is tapped', () => {
      cy.switchToBusiness('phones');
      cy.visit('/app/analytics/'); // Start on analytics
      
      cy.get('[data-cy="mobile-nav-home"]').click();
      
      // Should NOT stay on analytics
      cy.url().should('not.include', 'analytics');
      cy.url().should('match', /dashboard/);
    });

  });

  describe('HQ Admin Sidebar (Sticky + Mobile-Friendly)', () => {
    
    it('should have sticky sidebar on desktop', () => {
      cy.viewport(1280, 720);
      cy.visit('/hq/dashboard/');
      
      // Sidebar should exist
      cy.get('.hq-sidebar').should('exist');
      
      // Scroll down
      cy.scrollTo(0, 500);
      
      // Sidebar should still be visible (sticky)
      cy.get('.hq-sidebar').should('be.visible');
      
      // Check CSS sticky property
      cy.get('.hq-sidebar').should('have.css', 'position', 'sticky');
    });

    it('should have mobile-friendly sidebar on mobile', () => {
      cy.viewport('iphone-x');
      cy.visit('/hq/dashboard/');
      
      // Sidebar should be collapsible on mobile
      cy.get('.hq-sidebar').should('not.be.visible');
      
      // Open sidebar
      cy.get('[data-cy="hq-sidebar-toggle"]').click();
      
      // Sidebar should be visible
      cy.get('.hq-sidebar').should('be.visible');
      
      // Close sidebar
      cy.get('[data-cy="hq-sidebar-close"]').click();
      
      // Sidebar should be hidden again
      cy.get('.hq-sidebar').should('not.be.visible');
    });

    it('should not break content width on mobile', () => {
      cy.viewport('iphone-x');
      cy.visit('/hq/dashboard/');
      
      // Open sidebar
      cy.get('[data-cy="hq-sidebar-toggle"]').click();
      
      // Content should not overflow viewport
      cy.get('.hq-content').then(($content) => {
        const contentWidth = $content[0].scrollWidth;
        const viewportWidth = Cypress.config('viewportWidth');
        
        expect(contentWidth).to.be.at.most(viewportWidth);
      });
    });

  });

  describe('Phones Stock Page (Full IMEI + Full Product)', () => {
    
    beforeEach(() => {
      cy.switchToBusiness('phones');
      cy.seedTestData('phones_stock', 10); // Seed test data
    });

    it('should show full IMEI on desktop (no ellipsis)', () => {
      cy.viewport(1280, 720);
      cy.visit('/inventory/list/');
      
      // Get first IMEI cell
      cy.get('table tbody tr:first td:first').then(($cell) => {
        const text = $cell.text();
        const hasEllipsis = $cell.css('text-overflow') === 'ellipsis';
        
        // IMEI should be 15 digits
        expect(text.replace(/\D/g, '').length).to.equal(15);
        
        // Should NOT have ellipsis
        expect(hasEllipsis).to.be.false;
        
        // Should not be truncated
        expect(text).not.to.include('...');
      });
    });

    it('should show full IMEI on mobile (no ellipsis)', () => {
      cy.viewport('iphone-x');
      cy.visit('/inventory/list/');
      
      // Get first mobile card IMEI
      cy.get('[data-cy="mobile-stock-imei"]').first().then(($imei) => {
        const text = $imei.text();
        const hasEllipsis = $imei.css('text-overflow') === 'ellipsis';
        
        // IMEI should be 15 digits
        expect(text.replace(/\D/g, '').length).to.equal(15);
        
        // Should NOT have ellipsis
        expect(hasEllipsis).to.be.false;
        
        // Should not be truncated
        expect(text).not.to.include('...');
      });
    });

    it('should show full product name on desktop (no ellipsis)', () => {
      cy.viewport(1280, 720);
      cy.visit('/inventory/list/');
      
      // Get first product cell
      cy.get('table tbody tr:first td:nth-child(2)').then(($cell) => {
        const text = $cell.text();
        const hasEllipsis = $cell.css('text-overflow') === 'ellipsis';
        
        // Should NOT have ellipsis
        expect(hasEllipsis).to.be.false;
        
        // Should not be truncated with dots
        expect(text).not.to.match(/…|\.{3}/);
      });
    });

    it('should show full product name on mobile (no ellipsis)', () => {
      cy.viewport('iphone-x');
      cy.visit('/inventory/list/');
      
      // Get first mobile card product
      cy.get('[data-cy="mobile-stock-product"]').first().then(($product) => {
        const text = $product.text();
        const hasEllipsis = $product.css('text-overflow') === 'ellipsis';
        
        // Should NOT have ellipsis
        expect(hasEllipsis).to.be.false;
        
        // Should not be truncated with dots
        expect(text).not.to.match(/…|\.{3}/);
        
        // Should wrap if needed (check for normal white-space)
        const whiteSpace = $product.css('white-space');
        expect(whiteSpace).to.equal('normal');
      });
    });

  });

  describe('Phones Wizard (Mobile Card Quality)', () => {
    
    beforeEach(() => {
      cy.viewport('iphone-x');
      cy.switchToBusiness('phones');
    });

    it('should have properly sized cards on mobile (not cramped)', () => {
      cy.visit('/inventory/phone-sale-wizard/');
      
      // Cards should have minimum comfortable height
      cy.get('.wizard-card').should('have.css', 'min-height').and('match', /\d{3,}/); // At least 100px
      
      // Cards should have proper padding
      cy.get('.wizard-card').should('have.css', 'padding').and('not.equal', '0px');
    });

    it('should not overflow horizontally on mobile', () => {
      cy.visit('/inventory/phone-sale-wizard/');
      
      // No element should cause horizontal scroll
      cy.get('body').then(($body) => {
        const bodyWidth = $body[0].scrollWidth;
        const viewportWidth = Cypress.config('viewportWidth');
        
        expect(bodyWidth).to.be.at.most(viewportWidth + 1); // +1 for rounding
      });
    });

    it('should wrap long IMEI input cleanly on mobile', () => {
      cy.visit('/inventory/phone-sale-wizard/');
      
      // Navigate to IMEI step
      cy.get('[data-step="imei"]').click();
      
      // Type long IMEI
      cy.get('input[name="imei"]').type('123456789012345');
      
      // Input should not overflow
      cy.get('input[name="imei"]').then(($input) => {
        const inputWidth = $input[0].scrollWidth;
        const containerWidth = $input.parent()[0].clientWidth;
        
        expect(inputWidth).to.be.at.most(containerWidth);
      });
    });

    it('should match clothing card quality (spacing + sizing)', () => {
      // Compare phones wizard cards to clothing cards
      cy.visit('/inventory/phone-sale-wizard/');
      cy.get('.wizard-card').first().then(($phoneCard) => {
        const phonePadding = $phoneCard.css('padding');
        const phoneRadius = $phoneCard.css('border-radius');
        
        cy.visit('/verticals/clothing/sell/');
        cy.get('.wizard-card, .cc-card').first().then(($clothingCard) => {
          const clothingPadding = $clothingCard.css('padding');
          const clothingRadius = $clothingCard.css('border-radius');
          
          // Padding should be similar (within 5px)
          const phonePaddingPx = parseInt(phonePadding);
          const clothingPaddingPx = parseInt(clothingPadding);
          expect(Math.abs(phonePaddingPx - clothingPaddingPx)).to.be.at.most(5);
          
          // Border radius should be similar (within 3px)
          const phoneRadiusPx = parseInt(phoneRadius);
          const clothingRadiusPx = parseInt(clothingRadius);
          expect(Math.abs(phoneRadiusPx - clothingRadiusPx)).to.be.at.most(3);
        });
      });
    });

  });

  describe('Dashboard Structure Standardization', () => {
    
    it('should use consistent dashboard structure across verticals', () => {
      const verticals = [
        { name: 'phones', url: '/inventory/dashboard/' },
        { name: 'clothing', url: '/verticals/clothing/dashboard/' },
        { name: 'gym', url: '/gym/dashboard/' },
        { name: 'cement', url: '/verticals/cement/dashboard/' },
      ];

      verticals.forEach(vertical => {
        cy.switchToBusiness(vertical.name);
        cy.visit(vertical.url);
        
        // All dashboards should have these elements
        cy.get('.vertical-hero').should('exist'); // Hero section
        cy.get('.hero-actions').should('exist'); // Action buttons
        cy.get('.metric-card, .cc-kpi-grid').should('exist'); // KPI cards
        
        // Hero should have proper gradient and spacing
        cy.get('.vertical-hero').should('have.css', 'background-image').and('include', 'gradient');
        cy.get('.vertical-hero').should('have.css', 'border-radius');
      });
    });

  });

});

// Custom Cypress commands (add to support/commands.js)
Cypress.Commands.add('login', (username, password) => {
  cy.session([username, password], () => {
    cy.visit('/accounts/login/');
    cy.get('input[name="identifier"]').type(username);
    cy.get('input[name="password"]').type(password);
    cy.get('button[type="submit"]').click();
    cy.url().should('not.include', '/accounts/login');
  });
});

Cypress.Commands.add('logout', () => {
  cy.visit('/accounts/logout/');
});

Cypress.Commands.add('switchToBusiness', (vertical) => {
  cy.window().then((win) => {
    win.localStorage.setItem('active_vertical', vertical);
  });
  cy.visit('/');
});

Cypress.Commands.add('seedTestData', (dataType, count) => {
  cy.request('POST', '/api/test/seed/', { type: dataType, count });
});

