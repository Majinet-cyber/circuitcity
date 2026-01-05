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
    cy.contains('Cement Store Dashboard').should('be.visible');
    cy.contains('h1', /Cement Store Dashboard/i);
    
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

  it('should stock in Dangote cement successfully', () => {
    // Navigate to stock in
    cy.visit('/verticals/cement/stock-in/');
    
    // Step 1: Select brand (Dangote)
    cy.contains('.brand-name', 'Dangote')
      .closest('.premium-card')
      .click();
    cy.contains('button', 'Continue').should('not.be.disabled').click();
    
    // Step 2: Select or create product
    // If Dangote products exist, select one; otherwise enter new name
    cy.get('body').then($body => {
      if ($body.find('.product-card').length > 0) {
        // Select existing product
        cy.get('.product-card').first().click();
      } else {
        // Enter new product name
        cy.get('input[name="product_name"]').type('Dangote Cement 50kg');
      }
    });
    cy.contains('button', 'Continue').click();
    
    // Step 3: Enter quantity and pricing
    cy.get('input[name="quantity"]').type('100');
    cy.get('input[name="cost_price"]').type('50000');
    cy.get('input[name="selling_price"]').type('60000');
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

  it('should display seeded cement brands in stock-in', () => {
    // Visit stock-in
    cy.visit('/verticals/cement/stock-in/');
    
    // Verify all 9 seeded brands are present
    const expectedBrands = [
      'Dangote',
      'Akshar',
      'Nthanthwe',
      'Njati',
      'Njati Extra',
      'Khoma',
      'Nkope',
      'Lime',
      'Duracrete'
    ];
    
    expectedBrands.forEach(brand => {
      cy.contains('.brand-name', brand).should('be.visible');
    });
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

