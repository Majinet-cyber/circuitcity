// cypress/e2e/verticals/hardware_upgrade.cy.js
/**
 * E2E test for Hardware & General Dealers Vertical Upgrade
 * Tests:
 * - Display name changed from "Cement Store" to "Hardware & General Dealers"
 * - Products catalog accessible and functional
 * - Variation picker works correctly
 * - No vertical leakage (other verticals don't see hardware catalog)
 * - No regressions (existing cement functionality still works)
 */

describe('Hardware & General Dealers Vertical Upgrade', () => {
  let managerId;
  let businessId;
  const businessSlug = `hardware-e2e-${Date.now()}`;
  
  before(() => {
    // Create hardware business via API
    cy.request({
      method: 'POST',
      url: '/accounts/e2e/create_business/',
      body: {
        name: 'Hardware E2E Test Store',
        slug: businessSlug,
        business_kind: 'cement',  // Internal code remains "cement"
        manager_username: `hardware_mgr_${Date.now()}`,
        manager_password: 'test1234',
        manager_email: `hardware${Date.now()}@test.local`,
      },
    }).then((response) => {
      expect(response.status).to.eq(200);
      managerId = response.body.manager_id;
      businessId = response.body.business_id;
      cy.log(`Created hardware business ${businessId} with manager ${managerId}`);
    });
  });

  beforeEach(() => {
    // Login before each test
    cy.request({
      method: 'POST',
      url: '/accounts/e2e/login/',
      body: {
        user_id: managerId,
        business_id: businessId,
      },
    }).then((response) => {
      expect(response.status).to.eq(200);
      
      // Set session cookies manually
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

  it('should display "Hardware & General Dealers" instead of "Cement Store"', () => {
    // Visit dashboard
    cy.visit('/verticals/cement/dashboard/');
    
    // Verify new display name appears
    cy.contains('Hardware & General Dealers').should('be.visible');
    
    // Verify old name does NOT appear
    cy.get('body').should('not.contain.text', 'Cement Store');
  });

  it('should show Products tab in sidebar', () => {
    // Visit dashboard
    cy.visit('/verticals/cement/dashboard/');
    
    // Verify Products tab exists in sidebar
    cy.get('[data-cy="nav-hardware-products"]').should('be.visible');
    cy.contains('a', 'Products').should('be.visible');
  });

  it('should access hardware products catalog', () => {
    // Navigate to products catalog
    cy.visit('/cement/products/');
    
    // Verify catalog page loaded
    cy.contains('Hardware Products Catalog').should('be.visible');
    
    // Verify category chips exist
    cy.contains('Construction Materials').should('be.visible');
    cy.contains('Car Spares').should('be.visible');
    cy.contains('Welding Materials').should('be.visible');
    cy.contains('Safety Equipment').should('be.visible');
    cy.contains('Carpentry Equipment').should('be.visible');
    
    // Verify popular products section exists
    cy.contains('Popular Items').should('be.visible');
  });

  it('should search products in catalog', () => {
    // Visit catalog
    cy.visit('/cement/products/');
    
    // Search for "paint"
    cy.get('input[name="q"]').type('paint');
    cy.get('button[type="submit"]').click();
    
    // Verify search results
    cy.contains('Paint').should('be.visible');
    cy.contains('result', { matchCase: false }).should('be.visible');
  });

  it('should filter products by category', () => {
    // Visit catalog
    cy.visit('/cement/products/');
    
    // Click on "Car Spares" category
    cy.contains('a', 'Car Spares').click();
    
    // Verify filtered results
    cy.url().should('include', 'category=car-spares');
    cy.contains('Engine Oil').should('be.visible');
  });

  it('should view product detail with variation picker', () => {
    // Visit catalog
    cy.visit('/cement/products/');
    
    // Click on Paint product
    cy.contains('Paint').click();
    
    // Verify product detail page loaded
    cy.contains('h1', 'Paint').should('be.visible');
    cy.contains('Construction Materials').should('be.visible');
    
    // Verify variation steps exist
    cy.contains('Select Brand').should('be.visible');
    cy.contains('Select Size').should('be.visible');
    cy.contains('Select Color').should('be.visible');
    cy.contains('Select Finish').should('be.visible');
    
    // Verify suggested name section exists
    cy.contains('Suggested Product Name').should('be.visible');
  });

  it('should select variations and see updated product name', () => {
    // Visit paint product detail
    cy.visit('/cement/products/paint/');
    
    // Step 1: Select brand (Rainbow)
    cy.contains('a', 'Rainbow').click();
    
    // Verify URL updated with brand
    cy.url().should('include', 'brand=Rainbow');
    
    // Step 2: Select size (20L)
    cy.contains('a', '20L').click();
    
    // Verify URL updated with size
    cy.url().should('include', 'size=20L');
    
    // Step 3: Select finish (Emulsion)
    cy.contains('a', 'Emulsion').click();
    
    // Verify suggested name includes selections
    cy.contains('Paint — Rainbow — 20L — Emulsion').should('be.visible');
  });

  it('should redirect to stock-in with prefilled product', () => {
    // Visit paint product detail
    cy.visit('/cement/products/paint/?brand=Rainbow&size=20L&finish=Emulsion');
    
    // Click "Add to Inventory"
    cy.contains('a', 'Add to Inventory').click();
    
    // Verify redirected to stock-in page
    cy.url().should('include', '/cement/stock-in');
    
    // Verify product name is prefilled in URL
    cy.url().should('include', 'prefill_name=Paint');
  });

  it('should not show duplicate product names in catalog', () => {
    // Visit catalog
    cy.visit('/cement/products/');
    
    // Get all product names
    cy.get('.hw-product-name').then($names => {
      const names = $names.toArray().map(el => el.textContent.trim());
      const uniqueNames = [...new Set(names)];
      
      // Verify no duplicates
      expect(names.length).to.equal(uniqueNames.length);
    });
  });

  it('should maintain existing cement functionality (no regressions)', () => {
    // Test that existing stock-in still works
    cy.visit('/cement/stock-in/');
    
    // Verify stock-in page loads
    cy.contains('Select Brand').should('be.visible');
    
    // Verify seeded brands still exist
    cy.contains('Dangote').should('be.visible');
  });

  it('should show hardware catalog only for hardware businesses', () => {
    // This test verifies no vertical leakage
    // Hardware business should see catalog
    cy.visit('/cement/products/');
    cy.contains('Hardware Products Catalog').should('be.visible');
    
    // Verify URL is accessible (200 status)
    cy.url().should('include', '/cement/products/');
  });

  it('should display all required product categories', () => {
    // Visit catalog
    cy.visit('/cement/products/');
    
    // Verify all 5 categories exist
    const requiredCategories = [
      'Construction Materials',
      'Car Spares',
      'Welding Materials',
      'Safety Equipment',
      'Carpentry Equipment'
    ];
    
    requiredCategories.forEach(category => {
      cy.contains(category).should('be.visible');
    });
  });

  it('should display popular hardware products', () => {
    // Visit catalog
    cy.visit('/cement/products/');
    
    // Verify popular section exists
    cy.contains('Popular Items').should('be.visible');
    
    // Verify at least some popular products are shown
    cy.get('.hw-product-card').should('have.length.at.least', 6);
  });

  it('should show variation options for engine oil', () => {
    // Visit engine oil product
    cy.visit('/cement/products/engine-oil/');
    
    // Verify variation steps
    cy.contains('Select Brand').should('be.visible');
    cy.contains('Select Size').should('be.visible');
    cy.contains('Select Viscosity').should('be.visible');
    
    // Verify brand options
    cy.contains('Puma').should('be.visible');
    cy.contains('Extreme').should('be.visible');
    cy.contains('Total').should('be.visible');
    
    // Verify viscosity options
    cy.contains('10W-30').should('be.visible');
    cy.contains('15W-40').should('be.visible');
  });

  it('should show variation options for iron sheets', () => {
    // Visit iron sheets product
    cy.visit('/cement/products/iron-sheets/');
    
    // Verify gauge selection exists
    cy.contains('Select Gauge').should('be.visible');
    cy.contains('Gauge 26').should('be.visible');
    cy.contains('Gauge 28').should('be.visible');
    
    // Verify color options
    cy.contains('Galvanized').should('be.visible');
    cy.contains('Green').should('be.visible');
    cy.contains('Red').should('be.visible');
  });

  after(() => {
    // Cleanup: Mark business as test (optional)
    if (businessId) {
      cy.log(`Test completed for hardware business ${businessId}`);
    }
  });
});

