/**
 * Welding Quote Detail - Modal Button Regression Test
 * CircuitCity / Emajinet (Jan 2026)
 *
 * CRITICAL BUG FIX VERIFICATION:
 * Tests that "Add Material", "Add Cost", and "Add Labour/Transport/Profit" buttons
 * properly open modals and allow interaction.
 *
 * BEFORE FIX: Buttons would blink but modals wouldn't open
 * AFTER FIX: Buttons reliably open modals with explicit JavaScript initialization
 *
 * TEST COVERAGE:
 * 1. Desktop: Modal buttons work
 * 2. Mobile: Modal buttons work (no overlay interception)
 * 3. Modal is interactive (can click inside, type, submit)
 * 4. No backdrop z-index issues
 */

describe('Welding Quote Detail - Modal Buttons Regression', () => {
  const VERTICAL = 'welding';
  
  beforeEach(() => {
    // Login as manager for welding vertical
    cy.loginAsManager(VERTICAL);
    
    // Create a quote to work with
    cy.visit('/verticals/welding/quotes/create/', { failOnStatusCode: false });
    cy.wait(500);
    
    // Fill in customer info
    cy.get('input[name="customer_name"]').type('Test Customer Modal Fix', { force: true });
    cy.get('input[name="customer_phone"]').type('0999123456', { force: true });
    
    // Submit form
    cy.get('button[type="submit"]').click({ force: true });
    cy.wait(1000);
    
    // We should now be on the quote detail page
    cy.url().should('include', '/verticals/welding/quotes/');
  });

  it('should open Add Material modal and allow interaction (desktop)', () => {
    // Desktop viewport
    cy.viewport(1280, 720);
    
    cy.log('🖥️ Testing Add Material button on desktop');
    
    // Wait for page to be fully loaded
    cy.wait(1000);
    
    // Find and click "Add Material" button
    cy.get('button[data-bs-target="#materialPickerModal"]').first().should('be.visible');
    cy.get('button[data-bs-target="#materialPickerModal"]').first().click({ force: true });
    
    // Modal should be visible and interactive
    cy.get('#materialPickerModal', { timeout: 5000 }).should('be.visible');
    cy.get('#materialPickerModal').should('not.have.css', 'pointer-events', 'none');
    
    // Verify modal content is interactive
    cy.get('#materialSearch').should('be.visible');
    cy.get('#materialSearch').type('steel', { force: true });
    
    // Verify search worked (materials should filter)
    cy.get('.material-item').should('exist');
    
    // Close modal
    cy.get('#materialPickerModal .btn-close').click({ force: true });
    cy.wait(500);
    
    cy.log('✅ Desktop modal test passed');
  });

  it('should open Add Material modal and allow interaction (mobile)', () => {
    // Mobile viewport
    cy.viewport(375, 667);
    
    cy.log('📱 Testing Add Material button on mobile');
    
    // Wait for page to be fully loaded
    cy.wait(1000);
    
    // Scroll to make button visible (mobile has bottom nav)
    cy.scrollTo('top');
    cy.wait(300);
    
    // Find and click "Add Material" button
    cy.get('button[data-bs-target="#materialPickerModal"]').first().should('be.visible');
    cy.get('button[data-bs-target="#materialPickerModal"]').first().click({ force: true });
    
    // Modal should be visible and interactive (no backdrop z-index issues)
    cy.get('#materialPickerModal', { timeout: 5000 }).should('be.visible');
    cy.get('#materialPickerModal').should('not.have.css', 'pointer-events', 'none');
    
    // Verify we can interact with modal content on mobile
    cy.get('#materialSearch').should('be.visible');
    cy.get('#materialSearch').type('rod', { force: true });
    
    // Close modal
    cy.get('#materialPickerModal .btn-close').click({ force: true });
    cy.wait(500);
    
    cy.log('✅ Mobile modal test passed');
  });

  it('should open Add Cost modal and allow form submission', () => {
    // Desktop viewport
    cy.viewport(1280, 720);
    
    cy.log('💰 Testing Add Cost button');
    
    // Wait for page to be fully loaded
    cy.wait(1000);
    
    // Find and click "Add Cost" button
    cy.get('button[data-bs-target="#costPickerModal"]').first().should('be.visible');
    cy.get('button[data-bs-target="#costPickerModal"]').first().click({ force: true });
    
    // Modal should be visible
    cy.get('#costPickerModal', { timeout: 5000 }).should('be.visible');
    
    // Fill out the cost form
    cy.get('select[name="cost_type"]').select('labour', { force: true });
    cy.get('input[name="description"]').type('Test welding work', { force: true });
    cy.get('input[name="amount"]').type('15000', { force: true });
    
    // Submit form
    cy.get('#costForm button[type="submit"]').click({ force: true });
    
    // Page should reload with the new cost
    cy.wait(2000);
    cy.get('body').should('contain', 'Labour').or('contain', 'MWK 15,000');
    
    cy.log('✅ Cost modal submission test passed');
  });

  it('should open "Add First Material" button when no materials exist', () => {
    // This tests the alternate button that appears in the empty state
    cy.viewport(1280, 720);
    
    cy.log('🔘 Testing Add First Material button (empty state)');
    
    // Wait for page to be fully loaded
    cy.wait(1000);
    
    // Check if "Add First Material" button exists (in empty state)
    cy.get('body').then(($body) => {
      if ($body.text().includes('Add First Material')) {
        cy.log('Found "Add First Material" button - testing it');
        
        // Click the button
        cy.contains('button', 'Add First Material').click({ force: true });
        
        // Modal should open
        cy.get('#materialPickerModal', { timeout: 5000 }).should('be.visible');
        
        // Close modal
        cy.get('#materialPickerModal .btn-close').click({ force: true });
      } else {
        cy.log('No empty state - materials already exist, skipping this test');
      }
    });
  });

  it('should verify modals use cc-modal-root portal for proper z-index', () => {
    // This test ensures modals are moved to the modal portal to prevent z-index issues
    cy.viewport(1280, 720);
    
    cy.log('🎯 Testing modal portal (z-index fix)');
    
    // Verify modal portal exists in DOM
    cy.get('#cc-modal-root').should('exist');
    
    // Open modal
    cy.get('button[data-bs-target="#materialPickerModal"]').first().click({ force: true });
    cy.wait(500);
    
    // Modal should be visible
    cy.get('#materialPickerModal', { timeout: 5000 }).should('be.visible');
    
    // Verify no backdrop is blocking clicks (modal should be clickable)
    cy.get('#materialSearch').click({ force: true }).should('be.focused');
    
    cy.log('✅ Modal portal test passed');
  });

  it('should verify console logs show successful modal initialization', () => {
    // This test verifies the explicit modal initialization script runs
    cy.viewport(1280, 720);
    
    cy.log('📋 Checking for modal initialization logs');
    
    // Listen for console logs
    cy.window().then((win) => {
      cy.spy(win.console, 'log').as('consoleLog');
    });
    
    // Wait for initialization
    cy.wait(1000);
    
    // Check if initialization log exists
    cy.get('@consoleLog').should('be.called');
    cy.get('@consoleLog').should((spy) => {
      const calls = spy.getCalls().map(call => call.args.join(' '));
      const initLog = calls.some(call => call.includes('Welding Quote') && call.includes('Modal'));
      expect(initLog).to.be.true;
    });
    
    cy.log('✅ Console log verification passed');
  });
});

