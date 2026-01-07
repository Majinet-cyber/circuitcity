// cypress/e2e/verticals/nav_separation.cy.js
/**
 * E2E tests for vertical navigation separation
 * CRITICAL: Ensures phone-specific UI doesn't leak into non-phone verticals
 */

describe('Vertical Navigation Separation', () => {
  let managerId;
  let noneBusinessId;
  let cementBusinessId;
  const timestamp = Date.now();

  before(() => {
    // Create business with NO business_kind (None)
    cy.request({
      method: 'POST',
      url: '/accounts/e2e/create_business/',
      body: {
        name: `None Vertical Test ${timestamp}`,
        slug: `none-vert-${timestamp}`,
        business_kind: null,  // CRITICAL: No business_kind
        manager_username: `none_mgr_${timestamp}`,
        manager_password: 'test1234',
        manager_email: `none${timestamp}@test.local`,
      },
    }).then((response) => {
      expect(response.status).to.eq(200);
      managerId = response.body.manager_id;
      noneBusinessId = response.body.business_id;
      cy.log(`Created None business ${noneBusinessId}`);
    });

    // Create cement business
    cy.request({
      method: 'POST',
      url: '/accounts/e2e/create_business/',
      body: {
        name: `Cement Nav Test ${timestamp}`,
        slug: `cement-nav-${timestamp}`,
        business_kind: 'cement',
        manager_username: `cement_mgr_${timestamp}`,
        manager_password: 'test1234',
        manager_email: `cement_nav${timestamp}@test.local`,
      },
    }).then((response) => {
      expect(response.status).to.eq(200);
      cementBusinessId = response.body.business_id;
      cy.log(`Created Cement business ${cementBusinessId}`);
    });
  });

  describe('None/Unknown Business Navigation', () => {
    beforeEach(() => {
      // Login with None business
      cy.request({
        method: 'POST',
        url: '/accounts/e2e/login/',
        body: {
          user_id: managerId,
          business_id: noneBusinessId,
        },
      }).then((response) => {
        expect(response.status).to.eq(200);
        const cookies = response.headers['set-cookie'] || [];
        cookies.forEach(cookie => {
          const [nameValue] = cookie.split(';');
          const [name, value] = nameValue.split('=');
          if (name && value) {
            cy.setCookie(name.trim(), value.trim());
          }
        });
      });
    });

    it('should show minimal sidebar with NO phone terms', () => {
      cy.visit('/verticals/none/');
      
      // Verify page loads
      cy.contains(/Select your business type/i).should('be.visible');
      
      // Sidebar must NOT contain phone-specific items
      const phoneTerms = [
        'IMEI',
        'Scan IN',
        'Scan & Sell',
        'Accessories',
        'Scan IMEI',
        'Stock In Accessories',
        'Sell Accessories',
      ];
      
      phoneTerms.forEach(term => {
        cy.get('nav, aside, [class*="sidebar"]').should('not.contain.text', term);
      });
    });

    it('should show minimal mobile nav with NO phone terms', () => {
      cy.viewport('iphone-x');
      cy.visit('/verticals/none/');
      
      // Check mobile bottom nav
      const phoneTerms = ['IMEI', 'Scan', 'Accessories'];
      
      phoneTerms.forEach(term => {
        // Mobile nav should not contain these terms
        cy.get('[class*="mobile-nav"], [class*="bottom-nav"], nav').should('not.contain.text', term);
      });
      
      // Should have minimal items (Home, Settings, Menu)
      cy.get('[class*="mobile-nav"] a, [class*="bottom-nav"] a, nav a')
        .should('have.length.at.most', 5);  // Max 5 items for minimal nav
    });

    it('should have NO phone-specific links in page content', () => {
      cy.visit('/verticals/none/');
      
      // Check entire page content
      cy.get('body').then($body => {
        const bodyText = $body.text().toLowerCase();
        
        // Must NOT contain these terms
        const bannedTerms = ['imei', 'scan imei', 'accessories'];
        bannedTerms.forEach(term => {
          expect(bodyText).to.not.include(term, `Page must not contain "${term}"`);
        });
      });
    });
  });

  describe('Cement Business Navigation', () => {
    beforeEach(() => {
      // Login with Cement business
      cy.request({
        method: 'POST',
        url: '/accounts/e2e/login/',
        body: {
          user_id: managerId,  // Same manager
          business_id: cementBusinessId,
        },
      }).then((response) => {
        expect(response.status).to.eq(200);
        const cookies = response.headers['set-cookie'] || [];
        cookies.forEach(cookie => {
          const [nameValue] = cookie.split(';');
          const [name, value] = nameValue.split('=');
          if (name && value) {
            cy.setCookie(name.trim(), value.trim());
          }
        });
      });
    });

    it('should show cement sidebar with NO phone terms', () => {
      cy.visit('/verticals/cement/dashboard/');
      
      // Verify cement page loads
      cy.contains(/Cement/i).should('be.visible');
      
      // Sidebar must NOT contain phone-specific items
      const phoneTerms = [
        'IMEI',
        'Scan IMEI',
        'Accessories',
      ];
      
      phoneTerms.forEach(term => {
        cy.get('nav, aside, [class*="sidebar"]').should('not.contain.text', term);
      });
      
      // SHOULD contain cement-appropriate items
      const cementNavItems = ['Stock', 'Sell'];
      cementNavItems.forEach(item => {
        cy.get('nav, aside, [class*="sidebar"]').should('contain.text', item);
      });
    });

    it('should show cement mobile nav with NO phone terms', () => {
      cy.viewport('iphone-x');
      cy.visit('/verticals/cement/dashboard/');
      
      // Mobile nav should NOT contain phone-specific scan terms
      cy.get('[class*="mobile-nav"], [class*="bottom-nav"], nav')
        .should('not.contain.text', 'Scan IN')
        .and('not.contain.text', 'IMEI')
        .and('not.contain.text', 'Accessories');
    });

    it('should have cement-appropriate content with NO phone terms', () => {
      cy.visit('/verticals/cement/dashboard/');
      
      cy.get('body').then($body => {
        const bodyText = $body.text().toLowerCase();
        
        // Must NOT contain phone-specific terms
        expect(bodyText).to.not.include('imei');
        expect(bodyText).to.not.include('scan imei');
        
        // SHOULD contain cement terms
        const hasCementTerms = 
          bodyText.includes('cement') || 
          bodyText.includes('bag') || 
          bodyText.includes('brand');
        expect(hasCementTerms).to.be.true;
      });
    });

    it('should navigate through cement flows without seeing phone UI', () => {
      // Test full cement journey - no phone terms should appear
      
      // 1. Dashboard
      cy.visit('/verticals/cement/dashboard/');
      cy.get('body').should('not.contain.text', 'IMEI');
      
      // 2. Stock In
      cy.visit('/verticals/cement/stock-in/');
      cy.get('body').should('not.contain.text', 'IMEI');
      cy.get('body').should('not.contain.text', 'Accessories');
      
      // 3. Sell
      cy.visit('/verticals/cement/sell/');
      cy.get('body').should('not.contain.text', 'IMEI');
      cy.get('body').should('not.contain.text', 'Scan IMEI');
      
      // 4. Stock List
      cy.visit('/verticals/cement/stock/');
      cy.get('body').should('not.contain.text', 'IMEI');
    });
  });

  describe('Regression Prevention', () => {
    it('should NEVER default None business to phones navigation', () => {
      // Login with None business
      cy.request({
        method: 'POST',
        url: '/accounts/e2e/login/',
        body: {
          user_id: managerId,
          business_id: noneBusinessId,
        },
      }).then((response) => {
        const cookies = response.headers['set-cookie'] || [];
        cookies.forEach(cookie => {
          const [nameValue] = cookie.split(';');
          const [name, value] = nameValue.split('=');
          if (name && value) {
            cy.setCookie(name.trim(), value.trim());
          }
        });
      });

      cy.visit('/verticals/none/');
      
      // CRITICAL REGRESSION TEST:
      // This was the original bug - None businesses showed phones nav
      cy.get('nav, aside, [class*="sidebar"]')
        .should('not.contain.text', 'Scan IN')
        .and('not.contain.text', 'Scan & Sell')
        .and('not.contain.text', 'Accessories')
        .and('not.contain.text', 'IMEI');
      
      // Log success
      cy.log('✅ REGRESSION TEST PASSED: None business does NOT show phones nav');
    });
  });

  after(() => {
    cy.log(`Tests completed for None business ${noneBusinessId} and Cement business ${cementBusinessId}`);
  });
});

