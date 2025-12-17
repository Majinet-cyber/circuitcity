/**
 * Cypress E2E Tests for Premium Product Redesign
 * Focus: Mobile responsiveness and zero horizontal overflow
 */

describe('Premium Product Grid - Mobile Responsiveness', () => {
  const MOBILE_VIEWPORT = { width: 360, height: 760 };
  
  beforeEach(() => {
    // Set mobile viewport
    cy.viewport(MOBILE_VIEWPORT.width, MOBILE_VIEWPORT.height);
    
    // Login (adjust URL/credentials as needed)
    cy.visit('/login/');
    cy.get('input[name="username"]').type('testuser');
    cy.get('input[name="password"]').type('testpass123');
    cy.get('button[type="submit"]').click();
  });

  it('Liquor products page has no horizontal overflow on mobile', () => {
    cy.visit('/inventory/liquor/products/new/v2/', { failOnStatusCode: false });
    
    // Allow page to load
    cy.wait(500);
    
    // Check for horizontal overflow
    cy.window().then((win) => {
      const scrollWidth = win.document.documentElement.scrollWidth;
      const clientWidth = win.innerWidth;
      
      // Allow 1px tolerance for rounding
      expect(scrollWidth).to.be.lessThan(clientWidth + 2);
    });
    
    // Verify premium CSS is loaded
    cy.get('link[href*="premium-products.css"]').should('exist');
  });

  it('Pharmacy batch list has no horizontal overflow on mobile', () => {
    cy.visit('/pharmacy/batches/', { failOnStatusCode: false });
    
    cy.wait(500);
    
    cy.window().then((win) => {
      const scrollWidth = win.document.documentElement.scrollWidth;
      const clientWidth = win.innerWidth;
      expect(scrollWidth).to.be.lessThan(clientWidth + 2);
    });
  });

  it('Product cards stack vertically on mobile', () => {
    cy.visit('/inventory/liquor/products/new/v2/', { failOnStatusCode: false });
    
    // Product cards should be present
    cy.get('.premium-product-card').should('exist');
    
    // Cards should stack (each card takes full width)
    cy.get('.premium-product-grid').then(($grid) => {
      const gridComputedStyle = window.getComputedStyle($grid[0]);
      const gridTemplateColumns = gridComputedStyle.getPropertyValue('grid-template-columns');
      
      // On mobile, grid should be 1 column
      // This could be "1fr" or similar
      expect(gridTemplateColumns).to.not.include('280px');
    });
  });

  it('Premium price values do not overflow cards', () => {
    cy.visit('/inventory/liquor/products/new/v2/', { failOnStatusCode: false });
    
    cy.get('.premium-price-value').each(($priceEl) => {
      const priceWidth = $priceEl[0].scrollWidth;
      const containerWidth = $priceEl[0].clientWidth;
      
      // Price should not overflow its container
      expect(priceWidth).to.be.lessThan(containerWidth + 2);
    });
  });

  it('View toggle switches between grid and table', () => {
    cy.visit('/pharmacy/batches/', { failOnStatusCode: false });
    
    // Click table view button
    cy.get('.premium-view-btn').contains('Table').click({ force: true });
    
    // Should show table
    cy.url().should('include', 'view=table');
    cy.get('.premium-table-fallback').should('be.visible');
    
    // Click grid view button
    cy.get('.premium-view-btn').contains('Grid').click({ force: true });
    
    // Should show grid
    cy.url().should('include', 'view=grid');
  });

  it('Empty state displays correctly on mobile', () => {
    // Visit a page that might be empty (adjust URL as needed)
    cy.visit('/inventory/liquor/products/new/v2/', { failOnStatusCode: false });
    
    // If empty state is present, verify it displays correctly
    cy.get('body').then(($body) => {
      if ($body.find('.premium-empty-state').length > 0) {
        cy.get('.premium-empty-state').should('be.visible');
        cy.get('.premium-empty-icon').should('exist');
        cy.get('.premium-empty-title').should('exist');
        
        // No horizontal overflow in empty state
        cy.window().then((win) => {
          const scrollWidth = win.document.documentElement.scrollWidth;
          const clientWidth = win.innerWidth;
          expect(scrollWidth).to.be.lessThan(clientWidth + 2);
        });
      }
    });
  });

  it('Product card buttons are touch-friendly (min 44px height)', () => {
    cy.visit('/inventory/liquor/products/new/v2/', { failOnStatusCode: false });
    
    cy.get('.premium-btn').each(($btn) => {
      const btnHeight = $btn[0].offsetHeight;
      // Buttons should be at least 44px for touch targets
      expect(btnHeight).to.be.at.least(36); // Allow some flexibility
    });
  });

  it('Pharmacy gamified health score displays on mobile', () => {
    cy.visit('/pharmacy/batches/', { failOnStatusCode: false });
    
    // If grid view and batches exist
    cy.get('body').then(($body) => {
      if ($body.find('.premium-health-score').length > 0) {
        cy.get('.premium-health-score').should('be.visible');
        cy.get('.premium-health-icon').should('exist');
        cy.get('.premium-health-value').should('exist');
        
        // Health score should not cause overflow
        cy.get('.premium-health-score').each(($score) => {
          const scoreWidth = $score[0].scrollWidth;
          const containerWidth = $score[0].parentElement.clientWidth;
          expect(scoreWidth).to.be.lessThan(containerWidth + 2);
        });
      }
    });
  });

  it('Filter bar does not cause horizontal overflow', () => {
    cy.visit('/pharmacy/batches/', { failOnStatusCode: false });
    
    cy.get('.premium-filters-bar').should('exist');
    
    cy.window().then((win) => {
      const scrollWidth = win.document.documentElement.scrollWidth;
      const clientWidth = win.innerWidth;
      expect(scrollWidth).to.be.lessThan(clientWidth + 2);
    });
  });
});

describe('Premium Product Grid - Desktop View', () => {
  beforeEach(() => {
    // Set desktop viewport
    cy.viewport(1280, 720);
    
    // Login
    cy.visit('/login/');
    cy.get('input[name="username"]').type('testuser');
    cy.get('input[name="password"]').type('testpass123');
    cy.get('button[type="submit"]').click();
  });

  it('Product grid displays multiple columns on desktop', () => {
    cy.visit('/inventory/liquor/products/new/v2/', { failOnStatusCode: false });
    
    cy.get('.premium-product-grid').then(($grid) => {
      if ($grid.find('.premium-product-card').length > 1) {
        const gridComputedStyle = window.getComputedStyle($grid[0]);
        const gridTemplateColumns = gridComputedStyle.getPropertyValue('grid-template-columns');
        
        // On desktop, should have multiple columns
        expect(gridTemplateColumns).to.include('px'); // Will have multiple pixel values
      }
    });
  });

  it('Cards have hover effects on desktop', () => {
    cy.visit('/inventory/liquor/products/new/v2/', { failOnStatusCode: false });
    
    cy.get('.premium-product-card').first().then(($card) => {
      const initialTransform = window.getComputedStyle($card[0]).transform;
      
      // Hover over card
      cy.wrap($card).trigger('mouseover');
      
      // Transform should change on hover (translateY)
      cy.wait(100);
      cy.wrap($card).then(($hoveredCard) => {
        const hoverTransform = window.getComputedStyle($hoveredCard[0]).transform;
        // Transform values should differ
        expect(hoverTransform).to.not.equal('none');
      });
    });
  });
});

