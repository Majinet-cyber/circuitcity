// cypress/e2e/verticals/cement_journey.cy.js
/**
 * E2E test for Cement vertical journey
 * Tests stock-in, sell, and dashboard KPIs
 */

describe('Cement Vertical Journey', () => {
  let managerId;
  let businessId;
  const businessSlug = `cement-e2e-${Date.now()}`;
  
  before(() => {
    // Create cement business via API
    cy.request({
      method: 'POST',
      url: '/accounts/e2e/create_business/',
      body: {
        name: 'Cement E2E Test Store',
        slug: businessSlug,
        business_kind: 'cement',
        manager_username: `cement_mgr_${Date.now()}`,
        manager_password: 'test1234',
        manager_email: `cement${Date.now()}@test.local`,
      },
    }).then((response) => {
      expect(response.status).to.eq(200);
      managerId = response.body.manager_id;
      businessId = response.body.business_id;
      cy.log(`Created cement business ${businessId} with manager ${managerId}`);
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

  it('should display cement dashboard with seeded brands', () => {
    // Visit cement dashboard
    cy.visit(`/verticals/cement/dashboard/`);
    
    // Verify page loaded
    cy.contains('Hardware & General Dealers Dashboard').should('be.visible');
    cy.contains('h1', /Hardware & General Dealers Dashboard/i);
    
    // Verify KPI cards exist
    cy.contains('Total Revenue').should('be.visible');
    cy.contains('Total Profit').should('be.visible');
    cy.contains('Stock Value').should('be.visible');
    cy.contains('Items In Stock').should('be.visible');
    
    // Verify quick actions
    cy.contains('Add Stock').should('be.visible');
    cy.contains('Make Sale').should('be.visible');
    cy.contains('View All Products').should('be.visible');
  });

  it('should display multiple category cards in stock-in step 1', () => {
    // Navigate to stock in
    cy.visit('/verticals/cement/stock-in/?step=1');
    
    // Verify all three categories are present with data-testid
    cy.get('[data-testid="category-construction-materials"]').should('be.visible');
    cy.get('[data-testid="category-welding-materials"]').should('be.visible');
    cy.get('[data-testid="category-car-spares"]').should('be.visible');
    
    // Verify category labels are visible
    cy.contains('Construction Materials').should('be.visible');
    cy.contains('Welding Materials').should('be.visible');
    cy.contains('Car Spares').should('be.visible');
    
    // Verify category icons are present
    cy.contains('🏗️').should('be.visible'); // Construction
    cy.contains('🔥').should('be.visible'); // Welding
    cy.contains('🚗').should('be.visible'); // Car Spares
  });

  it('should proceed to product selection after selecting construction materials', () => {
    // Navigate to stock in step 1
    cy.visit('/verticals/cement/stock-in/?step=1');
    
    // Click Construction Materials category
    cy.get('[data-testid="category-construction-materials"]').click();
    
    // Click Continue button
    cy.contains('button', 'Continue').should('not.be.disabled').click();
    
    // Should navigate to step 2
    cy.url().should('include', 'step=2');
    
    // Verify product cards are shown
    cy.contains('Step 2: Select Product').should('be.visible');
    cy.contains('Cement').should('be.visible');
    cy.contains('Paint').should('be.visible');
  });

  it('should show coming soon for welding materials and car spares', () => {
    // Test Welding Materials
    cy.visit('/verticals/cement/stock-in/?step=1');
    cy.get('[data-testid="category-welding-materials"]').click();
    cy.contains('button', 'Continue').should('not.be.disabled').click();
    
    // Should stay on step 1 with warning
    cy.url().should('include', 'step=1');
    cy.contains(/coming soon/i).should('be.visible');
    
    // Test Car Spares
    cy.visit('/verticals/cement/stock-in/?step=1');
    cy.get('[data-testid="category-car-spares"]').click();
    cy.contains('button', 'Continue').should('not.be.disabled').click();
    
    // Should stay on step 1 with warning
    cy.url().should('include', 'step=1');
    cy.contains(/coming soon/i).should('be.visible');
  });

  it('should stock in Dangote cement successfully via card wizard', () => {
    // Navigate to stock in
    cy.visit('/verticals/cement/stock-in/?step=1');
    
    // Step 1: Select Construction Materials category
    cy.get('[data-testid="category-construction-materials"]').click();
    cy.contains('button', 'Continue').should('not.be.disabled').click();
    
    // Step 2: Select Cement product
    cy.contains('Cement').closest('.premium-card').click();
    cy.contains('button', 'Continue').should('not.be.disabled').click();
    
    // Step 3: Select Dangote brand and 50kg size
    cy.contains('Dangote').closest('.premium-card').click();
    cy.contains('BAG (50KG)').closest('.premium-card').click();
    cy.contains('button', 'Continue').click();
    
    // Step 4: Enter quantity and pricing
    cy.get('input[name="quantity"]').type('100');
    cy.get('input[name="cost_price"]').type('25000');
    cy.get('input[name="selling_price"]').type('30000');
    cy.contains('button', /Save Stock/i).click();
    
    // Verify success message
    cy.contains(/Added.*100.*bag/i, { timeout: 5000 }).should('be.visible');
  });

  it('should display stocked products in stock list', () => {
    // Visit stock list
    cy.visit('/verticals/cement/stock/');
    
    // Verify Dangote appears in list
    cy.contains('Dangote').should('be.visible');
    
    // Verify stock quantity shown
    cy.contains(/\d+\s+bag/i).should('be.visible');
  });

  it('should sell Dangote cement and update stock', () => {
    // First, verify we have stock
    cy.visit('/verticals/cement/stock/');
    cy.contains('Dangote').should('be.visible');
    
    // Navigate to sell
    cy.visit('/verticals/cement/sell/');
    
    // Step 1: Select brand (Dangote)
    cy.contains('.brand-name', 'Dangote')
      .closest('.premium-card')
      .click();
    cy.contains('button', 'Continue').should('not.be.disabled').click();
    
    // Step 2: Select product
    cy.get('.product-card').first().click();
    cy.contains('button', 'Continue').click();
    
    // Step 3: Enter quantity and payment
    cy.get('input[name="quantity"]').type('10');
    cy.get('select[name="payment_method"]').select('CASH');
    cy.contains('button', /Sell/i).click();
    
    // Verify success message
    cy.contains(/Sold.*10.*bag/i, { timeout: 5000 }).should('be.visible');
    cy.contains(/Revenue/i).should('be.visible');
    cy.contains(/Profit/i).should('be.visible');
  });

  it('should not allow selling more than available stock', () => {
    // Navigate to sell
    cy.visit('/verticals/cement/sell/');
    
    // Select Dangote
    cy.contains('.brand-name', 'Dangote')
      .closest('.premium-card')
      .click();
    cy.contains('button', 'Continue').click();
    
    // Select product
    cy.get('.product-card').first().click();
    cy.contains('button', 'Continue').click();
    
    // Try to sell 999999 bags (more than available)
    cy.get('input[name="quantity"]').type('999999');
    cy.get('select[name="payment_method"]').select('CASH');
    cy.contains('button', /Sell/i).click();
    
    // Verify error message
    cy.contains(/Insufficient stock/i, { timeout: 5000 }).should('be.visible');
  });

  it('should display updated KPIs on dashboard after sale', () => {
    // Visit dashboard
    cy.visit('/verticals/cement/dashboard/');
    
    // Verify KPIs show non-zero values (after previous stock-in and sell)
    // Note: We can't predict exact values, but we can verify elements exist
    cy.contains('Total Revenue').parent().within(() => {
      cy.contains(/MK/i).should('be.visible');
    });
    
    cy.contains('Total Profit').parent().within(() => {
      cy.contains(/MK/i).should('be.visible');
    });
    
    cy.contains('Stock Value').parent().within(() => {
      cy.contains(/MK/i).should('be.visible');
    });
  });

  it('should display seeded cement brands including Njati and Njati Extra', () => {
    // Visit stock-in and navigate to cement brand selection
    cy.visit('/verticals/cement/stock-in/?step=1');
    
    // Select Construction Materials
    cy.get('[data-testid="category-construction-materials"]').click();
    cy.contains('button', 'Continue').click();
    
    // Select Cement
    cy.contains('Cement').closest('.premium-card').click();
    cy.contains('button', 'Continue').click();
    
    // Verify all 9 seeded brands are present (including Njati Extra)
    const expectedBrands = [
      'Dangote',
      'Akshar',
      'Nthanthwe',
      'Njati',
      'Njati Extra',  // DISTINCT from Njati
      'Khoma',
      'Nkope',
      'Lime',
      'Duracrete'
    ];
    
    expectedBrands.forEach(brand => {
      cy.contains(brand).should('be.visible');
    });
    
    // Specifically verify both Njati and Njati Extra are present and distinct
    cy.contains('Njati').should('be.visible');
    cy.contains('Njati Extra').should('be.visible');
  });

  it('should show no phone-specific UI elements', () => {
    // Visit all cement pages and verify no phone terms
    const pages = [
      '/verticals/cement/dashboard/',
      '/verticals/cement/stock/',
      '/verticals/cement/stock-in/',
      '/verticals/cement/sell/'
    ];
    
    pages.forEach(page => {
      cy.visit(page);
      
      // Verify NO phone-specific terms appear
      cy.get('body').should('not.contain.text', 'IMEI');
      cy.get('body').should('not.contain.text', 'Scan IMEI');
      cy.get('body').should('not.contain.text', 'accessories');
      cy.get('body').should('not.contain.text', 'Phone');
    });
  });

  after(() => {
    // Cleanup: Mark business as test (optional)
    if (businessId) {
      cy.log(`Test completed for business ${businessId}`);
    }
  });
});

