// cypress/e2e/smoke/period-filter.smoke.cy.js
/**
 * Period Filter E2E Tests
 * Tests the new Period filter (All time + Month picker) across all verticals
 */

describe('Period Filter - Dashboard Integration', () => {
  beforeEach(() => {
    // Login
    cy.login('manager@emajinet.net', 'testpass123');
    
    // Wait for dashboard to load
    cy.url().should('include', '/app/');
  });

  it('should display Filter button on dashboard', () => {
    // Check Filter button exists
    cy.get('[data-filter-trigger]').should('be.visible');
    cy.get('[data-filter-trigger]').should('contain.text', 'Filter');
  });

  it('should open filter panel when Filter button is clicked', () => {
    // Click Filter button
    cy.get('[data-filter-trigger]').click();
    
    // Filter panel should be visible
    cy.get('[data-filter-panel]').should('have.class', 'open');
    
    // Backdrop should be visible
    cy.get('[data-filter-backdrop]').should('have.class', 'open');
  });

  it('should show Period section with All time and Month options', () => {
    // Open filter
    cy.get('[data-filter-trigger]').click();
    
    // Check Period section exists
    cy.get('[data-filter-panel]').within(() => {
      cy.contains('Period').should('be.visible');
      
      // Check All time option
      cy.get('[data-period-option]').should('be.visible');
      cy.get('[data-period-option]').should('contain.text', 'All time');
      
      // Check Month option
      cy.get('[data-period-month-toggle]').should('be.visible');
      cy.get('[data-period-month-toggle]').should('contain.text', 'Month');
    });
  });

  it('should show month picker when Month option is clicked', () => {
    // Open filter
    cy.get('[data-filter-trigger]').click();
    
    // Click Month option
    cy.get('[data-period-month-toggle]').click();
    
    // Month form should be visible
    cy.get('[data-month-form]').should('be.visible');
    
    // Month select should exist with all 12 months
    cy.get('#filterMonth').should('be.visible');
    cy.get('#filterMonth option').should('have.length', 13); // 12 months + "Choose..."
    
    // Check for specific months
    cy.get('#filterMonth option').contains('January').should('exist');
    cy.get('#filterMonth option').contains('June').should('exist');
    cy.get('#filterMonth option').contains('December').should('exist');
  });

  it('should apply All time filter and update URL', () => {
    // Open filter
    cy.get('[data-filter-trigger]').click();
    
    // Click All time
    cy.get('[data-period-option]').click();
    
    // URL should contain period=all
    cy.url().should('include', 'period=all');
    
    // Dashboard should display "All time" label
    cy.contains('All time').should('be.visible');
  });

  it('should apply Month filter and update URL', () => {
    // Open filter
    cy.get('[data-filter-trigger]').click();
    
    // Click Month option
    cy.get('[data-period-month-toggle]').click();
    
    // Select March (month=3)
    cy.get('#filterMonth').select('3');
    
    // Click Apply
    cy.get('[data-cy="apply-month-filter"]').click();
    
    // URL should contain period=month&month=3
    cy.url().should('include', 'period=month');
    cy.url().should('include', 'month=3');
    
    // Dashboard should display "March" in the label
    cy.contains(/March \d{4}/).should('be.visible');
  });

  it('should close filter panel when backdrop is clicked', () => {
    // Open filter
    cy.get('[data-filter-trigger]').click();
    
    // Verify panel is open
    cy.get('[data-filter-panel]').should('have.class', 'open');
    
    // Click backdrop
    cy.get('[data-filter-backdrop]').click();
    
    // Panel should be closed
    cy.get('[data-filter-panel]').should('not.have.class', 'open');
  });

  it('should close filter panel when close button is clicked', () => {
    // Open filter
    cy.get('[data-filter-trigger]').click();
    
    // Verify panel is open
    cy.get('[data-filter-panel]').should('have.class', 'open');
    
    // Click close button
    cy.get('[data-filter-close]').click();
    
    // Panel should be closed
    cy.get('[data-filter-panel]').should('not.have.class', 'open');
  });

  it('should reset to All time when Clear All is clicked', () => {
    // First apply a month filter
    cy.get('[data-filter-trigger]').click();
    cy.get('[data-period-month-toggle]').click();
    cy.get('#filterMonth').select('6'); // June
    cy.get('[data-cy="apply-month-filter"]').click();
    
    // Verify month filter is applied
    cy.url().should('include', 'month=6');
    
    // Open filter again
    cy.get('[data-filter-trigger]').click();
    
    // Click Reset to All time
    cy.get('[data-filter-clear-all]').click();
    
    // URL should contain period=all
    cy.url().should('include', 'period=all');
  });

  it('should preserve period filter across page refreshes', () => {
    // Apply month filter
    cy.get('[data-filter-trigger]').click();
    cy.get('[data-period-month-toggle]').click();
    cy.get('#filterMonth').select('9'); // September
    cy.get('[data-cy="apply-month-filter"]').click();
    
    // Verify URL
    cy.url().should('include', 'period=month&month=9');
    
    // Refresh page
    cy.reload();
    
    // URL should still have the filter
    cy.url().should('include', 'period=month&month=9');
    
    // Dashboard should still show September
    cy.contains(/September \d{4}/).should('be.visible');
  });

  it('should work on mobile viewport', () => {
    // Set mobile viewport
    cy.viewport('iphone-x');
    
    // Filter button should be visible
    cy.get('[data-filter-trigger]').should('be.visible');
    
    // Click Filter
    cy.get('[data-filter-trigger]').click();
    
    // Panel should open as bottom sheet on mobile
    cy.get('[data-filter-panel]').should('have.class', 'open');
    
    // Period options should be visible
    cy.get('[data-period-option]').should('be.visible');
    cy.get('[data-period-month-toggle]').should('be.visible');
  });
});

describe('Period Filter - Phones Dashboard', () => {
  beforeEach(() => {
    cy.login('manager@emajinet.net', 'testpass123');
    
    // Navigate to Phones dashboard
    cy.visit('/verticals/phones/dashboard/');
  });

  it('should show period filter on Phones dashboard', () => {
    cy.get('[data-filter-trigger]').should('be.visible');
  });

  it('should filter Phones dashboard by month', () => {
    // Open filter
    cy.get('[data-filter-trigger]').click();
    
    // Select Month > January
    cy.get('[data-period-month-toggle]').click();
    cy.get('[data-cy="month-select"]').select('1');
    cy.get('[data-cy="apply-month-filter"]').click();
    
    // URL should be updated
    cy.url().should('include', 'period=month&month=1');
    
    // Check that dashboard shows filtered data (KPI values may change)
    cy.get('[data-cy="sales-revenue-card"]').should('be.visible');
  });
});

describe('Period Filter - Clothing Dashboard', () => {
  beforeEach(() => {
    cy.login('manager@emajinet.net', 'testpass123');
    
    // Navigate to Clothing dashboard
    cy.visit('/verticals/clothing/dashboard/');
  });

  it('should show period filter on Clothing dashboard', () => {
    cy.get('[data-filter-trigger]').should('be.visible');
  });

  it('should switch between All time and Month', () => {
    // Start with All time
    cy.get('[data-filter-trigger]').click();
    cy.get('[data-period-option]').click();
    cy.url().should('include', 'period=all');
    
    // Switch to Month
    cy.get('[data-filter-trigger]').click();
    cy.get('[data-period-month-toggle]').click();
    cy.get('[data-cy="month-select"]').select('5'); // May
    cy.get('[data-cy="apply-month-filter"]').click();
    cy.url().should('include', 'period=month&month=5');
    
    // Dashboard should update
    cy.contains(/May \d{4}/).should('be.visible');
  });
});

describe('Period Filter - Farm Dashboard', () => {
  beforeEach(() => {
    cy.login('manager@emajinet.net', 'testpass123');
    
    // Navigate to Farm dashboard (if exists in test env)
    cy.visit('/verticals/farm/dashboard/', { failOnStatusCode: false });
  });

  it('should show period filter if Farm dashboard is available', () => {
    // Check if page loaded successfully
    cy.url().then((url) => {
      if (url.includes('/verticals/farm/dashboard/')) {
        // Farm dashboard exists, test the filter
        cy.get('[data-filter-trigger]', { timeout: 10000 }).should('be.visible');
      } else {
        // Farm vertical not configured, skip test
        cy.log('Farm vertical not configured in test environment');
      }
    });
  });
});

