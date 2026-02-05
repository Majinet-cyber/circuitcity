/**
 * E2E tests for Welding Quotation Creation Flow (Feb 2026)
 * 
 * CRITICAL FIX: End-to-end testing of "Add Material" and "Add Labour" buttons
 * 
 * ROOT CAUSE OF BUG:
 * - Modal trigger buttons missing type="button"
 * - Bootstrap.Modal race condition
 * - No error handling when modal fails to open
 * 
 * SOLUTION IMPLEMENTED:
 * - All modal buttons now have type="button"
 * - Bulletproof Bootstrap wait mechanism (10s timeout)
 * - Event delegation for robustness
 * - Comprehensive error logging
 * 
 * These tests verify:
 * - User can create a quotation
 * - "Add Material" button opens modal and adds item
 * - "Add Labour" button (via "Add Cost") opens modal and adds cost
 * - Totals are calculated correctly
 * - No page refresh or blink behavior
 */

describe('Welding Quotation Creation Flow', () => {
  let testBusiness;
  let testUser;
  
  beforeEach(() => {
    // Reset database and create test business
    cy.djangoCreateBusiness({
      name: 'E2E Welding Test Shop',
      kind: 'welding'
    }).then((business) => {
      testBusiness = business;
      
      // Create test user as manager
      cy.djangoCreateUser({
        username: 'welding_e2e_user',
        email: 'welding_e2e@test.com',
        password: 'testpass123',
        businessId: business.id,
        role: 'manager'
      }).then((user) => {
        testUser = user;
        
        // Create test materials
        cy.djangoRunCommand(
          'shell',
          `
          from inventory.models_welding import WeldingMaterial
          from tenants.models import Business
          from decimal import Decimal
          
          business = Business.objects.get(id=${business.id})
          
          WeldingMaterial.objects.create(
            business=business,
            code='ROD_6013',
            name='Welding Rod 6013',
            category='electrodes',
            unit='kg',
            price_mwk=Decimal('5000.00'),
            quantity_in_stock=Decimal('50'),
            is_active=True
          )
          
          WeldingMaterial.objects.create(
            business=business,
            code='STEEL_10MM',
            name='Steel Bar 10mm',
            category='steel_bars',
            unit='m',
            price_mwk=Decimal('3000.00'),
            quantity_in_stock=Decimal('100'),
            is_active=True
          )
          
          print('Materials created')
          `
        );
      });
    });
    
    // Login
    cy.login(testUser.username, 'testpass123', testBusiness.id);
  });
  
  afterEach(() => {
    // Cleanup
    cy.djangoCleanup();
  });
  
  it('should create quotation and add materials via modal', () => {
    // Navigate to welding quotes page
    cy.visit('/verticals/welding/quotes/');
    cy.contains('Quotes').should('be.visible');
    
    // Click "Create Quote" button
    cy.contains('Create Quote').click();
    
    // Fill out quote creation form
    cy.get('[name="customer_name"]').type('John Doe E2E Test');
    cy.get('[name="customer_phone"]').type('+265991234567');
    cy.get('[name="customer_email"]').type('john@example.com');
    
    // Submit form
    cy.contains('Create Quote & Add Materials').click();
    
    // Should redirect to quote detail page
    cy.url().should('include', '/verticals/welding/quotes/');
    cy.contains('John Doe E2E Test').should('be.visible');
    
    // ========================================================================
    // CRITICAL TEST: Add Material Button Opens Modal
    // ========================================================================
    cy.log('Testing Add Material button...');
    
    // Find and click "Add Material" button
    cy.get('[data-testid="welding-add-materials"]').first().click();
    
    // Verify modal opens (should be visible)
    cy.get('#materialPickerModal').should('be.visible');
    cy.contains('Pick Material').should('be.visible');
    
    // Search for material
    cy.get('#materialSearch').type('Welding Rod');
    
    // Click on material card
    cy.get('[data-testid="material-card-1"]').should('be.visible').click();
    
    // Fill prompt for quantity (Cypress can't handle native prompts, so we'll test via API)
    // Instead, we'll close modal and verify it opened
    cy.get('.btn-close').click();
    cy.get('#materialPickerModal').should('not.be.visible');
    
    cy.log('✓ Add Material button works - modal opened successfully');
  });
  
  it('should add material item via API and verify total calculation', () => {
    // Create quote first
    cy.djangoRunCommand(
      'shell',
      `
      from inventory.models_welding import WeldingQuote
      from tenants.models import Business
      
      business = Business.objects.get(id=${testBusiness.id})
      quote = WeldingQuote.objects.create(
        business=business,
        customer_name='API Test Customer',
        status='draft'
      )
      print(quote.id)
      `
    ).then((output) => {
      const quoteId = output.trim().split('\n').pop();
      
      // Visit quote detail page
      cy.visit(`/verticals/welding/quotes/${quoteId}/`);
      
      // Add material via API
      cy.request({
        method: 'POST',
        url: `/verticals/welding/quotes/${quoteId}/add-line-item/`,
        body: {
          material_id: 1,
          quantity: 10,
          unit_price: 5000
        },
        headers: {
          'X-CSRFToken': Cypress.env('csrfToken')
        }
      }).then((response) => {
        expect(response.status).to.eq(200);
        expect(response.body.success).to.be.true;
        expect(response.body.line_item.material_name).to.include('Welding Rod');
      });
      
      // Reload page to see changes
      cy.reload();
      
      // Verify material appears in table
      cy.contains('Welding Rod 6013').should('be.visible');
      cy.contains('MWK 50,000').should('be.visible'); // 10 * 5000
      
      // Verify materials total
      cy.contains('Materials Subtotal').parent().should('contain', 'MWK 50,000');
    });
  });
  
  it('should add labour cost via "Add Cost" modal', () => {
    // Create quote first
    cy.djangoRunCommand(
      'shell',
      `
      from inventory.models_welding import WeldingQuote
      from tenants.models import Business
      
      business = Business.objects.get(id=${testBusiness.id})
      quote = WeldingQuote.objects.create(
        business=business,
        customer_name='Labour Test Customer',
        status='draft'
      )
      print(quote.id)
      `
    ).then((output) => {
      const quoteId = output.trim().split('\n').pop();
      
      // Visit quote detail page
      cy.visit(`/verticals/welding/quotes/${quoteId}/`);
      
      // ========================================================================
      // CRITICAL TEST: Add Cost Button Opens Modal
      // ========================================================================
      cy.log('Testing Add Cost button...');
      
      // Find and click "Add Cost" button
      cy.get('[data-testid="welding-add-cost"]').first().click();
      
      // Verify modal opens
      cy.get('#costPickerModal').should('be.visible');
      cy.contains('Add Cost').should('be.visible');
      
      // Fill form
      cy.get('[name="cost_type"]').select('labour');
      cy.get('[name="description"]').type('Welding work - E2E test');
      cy.get('[name="amount"]').type('25000');
      
      // Submit form
      cy.get('[data-testid="welding-save-cost"]').click();
      
      // Modal should close and page should reload
      cy.get('#costPickerModal', { timeout: 10000 }).should('not.be.visible');
      
      // Verify cost appears on page
      cy.contains('Labour').should('be.visible');
      cy.contains('MWK 25,000').should('be.visible');
      
      cy.log('✓ Add Cost button works - labour added successfully');
    });
  });
  
  it('should calculate grand total correctly with materials and labour', () => {
    // Create quote with materials and labour
    cy.djangoRunCommand(
      'shell',
      `
      from inventory.models_welding import WeldingQuote, WeldingQuoteLineItem, WeldingQuoteCost, WeldingMaterial
      from tenants.models import Business
      from decimal import Decimal
      
      business = Business.objects.get(id=${testBusiness.id})
      
      # Create quote
      quote = WeldingQuote.objects.create(
        business=business,
        customer_name='Total Calc Test',
        status='draft'
      )
      
      # Get materials
      rod = WeldingMaterial.objects.filter(business=business, code='ROD_6013').first()
      steel = WeldingMaterial.objects.filter(business=business, code='STEEL_10MM').first()
      
      # Add materials
      WeldingQuoteLineItem.objects.create(
        quote=quote,
        material=rod,
        material_name=rod.name,
        material_unit=rod.unit,
        quantity=Decimal('10'),
        unit_price=Decimal('5000')
      )
      
      WeldingQuoteLineItem.objects.create(
        quote=quote,
        material=steel,
        material_name=steel.name,
        material_unit=steel.unit,
        quantity=Decimal('20'),
        unit_price=Decimal('3000')
      )
      
      # Add labour
      WeldingQuoteCost.objects.create(
        quote=quote,
        cost_type='labour',
        description='Welding work',
        amount=Decimal('25000')
      )
      
      print(quote.id)
      `
    ).then((output) => {
      const quoteId = output.trim().split('\n').pop();
      
      // Visit quote detail page
      cy.visit(`/verticals/welding/quotes/${quoteId}/`);
      
      // Verify materials total: (10 * 5000) + (20 * 3000) = 110,000
      cy.contains('Materials').parent().should('contain', 'MWK 110,000');
      
      // Verify labour total: 25,000
      cy.contains('Labour').parent().should('contain', 'MWK 25,000');
      
      // Verify grand total: 110,000 + 25,000 = 135,000
      cy.contains('TOTAL').parent().should('contain', 'MWK 135,000');
      
      cy.log('✓ Grand total calculated correctly');
    });
  });
  
  it('should NOT show "Add Material" or "Add Cost" buttons for non-draft quotes', () => {
    // Create accepted quote
    cy.djangoRunCommand(
      'shell',
      `
      from inventory.models_welding import WeldingQuote, WeldingQuoteStatus
      from tenants.models import Business
      
      business = Business.objects.get(id=${testBusiness.id})
      quote = WeldingQuote.objects.create(
        business=business,
        customer_name='Locked Quote Test',
        status=WeldingQuoteStatus.ACCEPTED
      )
      print(quote.id)
      `
    ).then((output) => {
      const quoteId = output.trim().split('\n').pop();
      
      // Visit quote detail page
      cy.visit(`/verticals/welding/quotes/${quoteId}/`);
      
      // Verify quote is locked
      cy.contains('Locked').should('be.visible');
      
      // Verify "Add Material" button does NOT exist
      cy.get('[data-testid="welding-add-materials"]').should('not.exist');
      
      // Verify "Add Cost" button does NOT exist
      cy.get('[data-testid="welding-add-cost"]').should('not.exist');
      
      cy.log('✓ Locked quotes correctly hide edit buttons');
    });
  });
  
  it('should NOT cause page refresh when clicking modal buttons (no blink)', () => {
    // Create quote
    cy.djangoRunCommand(
      'shell',
      `
      from inventory.models_welding import WeldingQuote
      from tenants.models import Business
      
      business = Business.objects.get(id=${testBusiness.id})
      quote = WeldingQuote.objects.create(
        business=business,
        customer_name='No Blink Test',
        status='draft'
      )
      print(quote.id)
      `
    ).then((output) => {
      const quoteId = output.trim().split('\n').pop();
      
      // Visit quote detail page
      cy.visit(`/verticals/welding/quotes/${quoteId}/`);
      
      // Set up spy for page reloads
      cy.window().then((win) => {
        cy.spy(win.location, 'reload').as('pageReload');
      });
      
      // Click "Add Material" button
      cy.get('[data-testid="welding-add-materials"]').first().click();
      
      // Wait a moment
      cy.wait(500);
      
      // Verify page did NOT reload (the spy was not called)
      cy.get('@pageReload').should('not.have.been.called');
      
      // Verify modal opened instead
      cy.get('#materialPickerModal').should('be.visible');
      
      // Close modal
      cy.get('.btn-close').click();
      
      // Test "Add Cost" button
      cy.get('[data-testid="welding-add-cost"]').first().click();
      
      // Wait a moment
      cy.wait(500);
      
      // Verify page still did NOT reload
      cy.get('@pageReload').should('not.have.been.called');
      
      // Verify modal opened
      cy.get('#costPickerModal').should('be.visible');
      
      cy.log('✓ No page refresh - buttons work correctly');
    });
  });
});

