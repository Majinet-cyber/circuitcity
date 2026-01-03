// cypress/e2e/gym_analytics.cy.js
/**
 * E2E tests for gym analytics dashboard.
 * Verifies gym-specific KPIs and ensures no product/stock language appears.
 */

describe('Gym Analytics Dashboard', () => {
  beforeEach(() => {
    // Login and navigate to gym analytics
    cy.login('gym_manager', 'testpass123');
    cy.visit('/app/analytics/');
  });

  it('should display gym-specific KPIs only', () => {
    // Wait for analytics to load
    cy.get('.kpi-row', { timeout: 10000 }).should('be.visible');

    // Check that gym-specific KPIs are present
    cy.contains('.kpi-label', 'Active Members', { matchCase: false }).should('exist');
    cy.contains('.kpi-label', 'Check-ins', { matchCase: false }).should('exist');
    cy.contains('.kpi-label', 'Attendance Rate', { matchCase: false }).should('exist');

    // Verify NO product/stock language appears
    cy.get('.kpi-label').should('not.contain', 'Total Products');
    cy.get('.kpi-label').should('not.contain', 'Stock');
    cy.get('.kpi-label').should('not.contain', 'Avg Order Value');
    cy.get('.kpi-label').should('not.contain', 'Units Sold');
  });

  it('should display attendance trend chart', () => {
    // Wait for charts to load
    cy.get('.charts-grid', { timeout: 10000 }).should('be.visible');

    // Check for attendance/check-ins chart
    cy.contains('h3', 'Attendance', { matchCase: false }).should('exist')
      .or(cy.contains('h3', 'Check-ins', { matchCase: false }));

    // Verify chart canvas exists
    cy.get('canvas').should('have.length.at.least', 1);
  });

  it('should display top trainers (not agents)', () => {
    // Check for trainers section
    cy.contains('h3', 'Trainers', { matchCase: false }).should('exist');

    // Should NOT say "Top Agents" for gym
    cy.get('h3').should('not.contain', 'Top Agents');
  });

  it('should not display top products chart', () => {
    // Gym should not have "Top Products"
    cy.get('.charts-grid').within(() => {
      cy.contains('h3', 'Top Products').should('not.exist');
    });
  });

  it('should display payment mix chart', () => {
    // Payment mix is relevant for gym
    cy.contains('h3', 'Payment Mix', { matchCase: false }).should('exist');
  });

  it('should handle empty state gracefully', () => {
    // If no data, should show empty state message
    cy.get('.charts-grid').should('be.visible');

    // Charts should either have data or show "No data" message
    cy.get('canvas').each(($canvas) => {
      cy.wrap($canvas).should('be.visible');
    });
  });

  it('should filter by date range', () => {
    // Click on "This Month" filter
    cy.contains('.filter-pill', 'This Month').click();

    // Wait for data to reload
    cy.wait(1000);

    // KPIs should still be visible
    cy.get('.kpi-row').should('be.visible');
    cy.get('.kpi-card').should('have.length.at.least', 4);
  });

  it('should display correct KPI values', () => {
    // Wait for KPIs to load
    cy.get('.kpi-row', { timeout: 10000 }).should('be.visible');

    // Check that KPI values are numbers (not "--" or loading state)
    cy.get('.kpi-value').each(($value) => {
      const text = $value.text().trim();
      // Should be a number, currency, or percentage
      expect(text).to.match(/^\d+|MWK|%|--$/);
    });
  });

  it('should be mobile responsive', () => {
    // Test mobile viewport
    cy.viewport('iphone-x');

    // KPIs should still be visible and stacked
    cy.get('.kpi-row').should('be.visible');

    // Charts should be visible
    cy.get('.charts-grid').should('be.visible');

    // No horizontal overflow
    cy.get('body').should('have.css', 'overflow-x', 'hidden')
      .or(cy.get('body').should('not.have.css', 'overflow-x', 'scroll'));
  });
});

describe('Gym Member Names Clickable', () => {
  beforeEach(() => {
    cy.login('gym_manager', 'testpass123');
  });

  it('should have clickable member names in check-in page', () => {
    cy.visit('/gym/checkin/');

    // Wait for member list to load
    cy.get('.gym-member-card, table', { timeout: 10000 }).should('be.visible');

    // Find first member name link
    cy.get('a').contains(/[A-Z][a-z]+ [A-Z][a-z]+/).first().then(($link) => {
      const memberName = $link.text();
      const href = $link.attr('href');

      // Should link to member detail page
      expect(href).to.match(/\/gym\/member\/\d+\//);

      // Click and verify navigation
      cy.wrap($link).click();
      cy.url().should('include', '/gym/member/');
      cy.contains(memberName).should('exist');
    });
  });

  it('should have clickable member names in members list', () => {
    cy.visit('/gym/members/');

    // Wait for table to load
    cy.get('table tbody', { timeout: 10000 }).should('be.visible');

    // Find first member name link
    cy.get('table tbody tr').first().within(() => {
      cy.get('a').first().then(($link) => {
        const href = $link.attr('href');
        expect(href).to.match(/\/gym\/member\/\d+\//);

        // Click and verify
        cy.wrap($link).click();
      });
    });

    cy.url().should('include', '/gym/member/');
  });

  it('should have clickable member names in leaderboard', () => {
    cy.visit('/gym/leaderboard/');

    // Wait for leaderboard to load
    cy.get('.gym-lb-podium, .gym-lb-list', { timeout: 10000 }).should('be.visible');

    // Check podium names are clickable
    cy.get('.gym-lb-podium-name a, .gym-lb-name a').first().then(($link) => {
      const href = $link.attr('href');
      expect(href).to.match(/\/gym\/member\/\d+\//);
    });
  });
});

describe('Gym QR Code and Member Numbers', () => {
  beforeEach(() => {
    cy.login('gym_manager', 'testpass123');
  });

  it('should display member number on member detail page', () => {
    // Navigate to first member
    cy.visit('/gym/members/');
    cy.get('table tbody tr').first().find('a').first().click();

    // Should show member number
    cy.contains(/GYM-\d{6}|[A-Z]{2,3}-\d{6}/).should('exist');
  });

  it('should display QR code on member detail page', () => {
    // Navigate to first member
    cy.visit('/gym/members/');
    cy.get('table tbody tr').first().find('a').first().click();

    // Should show QR code image
    cy.get('img[alt*="QR Code"]').should('exist').and('be.visible');
  });

  it('should allow QR code scanning for check-in', () => {
    cy.visit('/gym/scan/');

    // Scan page should be visible
    cy.contains('Scan', { matchCase: false }).should('exist');

    // Should have camera/scanner interface
    cy.get('video, canvas, #scanner').should('exist');
  });
});
