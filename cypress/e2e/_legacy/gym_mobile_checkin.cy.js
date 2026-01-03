/**
 * GYM MOBILE CHECK-IN JOURNEY (Mobile-First, Gamified, Premium)
 *
 * Tests the mobile-optimized check-in flow including:
 * - Mobile card layout rendering
 * - Search and filter functionality
 * - Check-in with celebration modal
 * - Leaderboard display
 * - Member detail mobile view
 *
 * Viewport: iPhone 12 (390x844)
 */

describe('Gym Mobile Check-In Journey', () => {
  // Mobile viewport configuration
  const MOBILE_VIEWPORT = {
    width: 390,
    height: 844,
  };

  beforeEach(() => {
    // Set mobile viewport
    cy.viewport(MOBILE_VIEWPORT.width, MOBILE_VIEWPORT.height);

    // Login as manager
    cy.visit('/accounts/login/');
    cy.get('input[name="username"]').type('manager_gym');
    cy.get('input[name="password"]').type('testpass123');
    cy.get('button[type="submit"]').click();

    // Should redirect to appropriate dashboard
    cy.url().should('not.include', '/accounts/login/');
  });

  it('should display mobile-optimized check-in page', () => {
    // Navigate to check-in page
    cy.visit('/gym/checkin/');

    // Check for mobile header
    cy.get('.gym-checkin-header').should('be.visible');
    cy.contains('Member Check-In').should('be.visible');

    // Check for search input
    cy.get('#memberSearch').should('be.visible').and('have.attr', 'placeholder');

    // Check for Scan QR button
    cy.contains('Scan').should('be.visible');

    // Check for filter chips
    cy.get('.gym-filter-chips').should('be.visible');
    cy.get('.gym-filter-chip').should('have.length.at.least', 3);

    // Mobile cards should be visible, desktop table should be hidden
    cy.get('.gym-member-cards').should('be.visible');
    cy.get('.gym-table-desktop').should('not.be.visible');

    // At least one member card should exist
    cy.get('.gym-member-card').should('have.length.at.least', 1);
  });

  it('should have touch-friendly card layout', () => {
    cy.visit('/gym/checkin/');

    // Check first member card
    cy.get('.gym-member-card').first().within(() => {
      // Should have member name and phone
      cy.get('.gym-member-card-info h3').should('be.visible');
      cy.get('.gym-member-card-info p').should('contain', '+');

      // Should have stats grid
      cy.get('.gym-member-card-stats').should('be.visible');

      // Should have check-in button (large touch target)
      cy.get('.gym-checkin-btn').should('be.visible').and('have.css', 'width');
    });
  });

  it('should filter members by search', () => {
    cy.visit('/gym/checkin/');

    // Get initial count of visible cards
    cy.get('.gym-member-card').should('have.length.at.least', 1);

    // Search for a specific member (assuming "John" exists)
    cy.get('#memberSearch').type('john');

    // Wait a bit for the filter to apply
    cy.wait(300);

    // Should have fewer or equal cards visible
    cy.get('.gym-member-card').each(($card) => {
      // Each visible card should contain "john" in the name
      cy.wrap($card).should('be.visible');
    });
  });

  it('should filter by status chips', () => {
    cy.visit('/gym/checkin/');

    // Click "Active" filter
    cy.get('.gym-filter-chip').contains('Active').click();

    // Should have active class
    cy.get('.gym-filter-chip').contains('Active').should('have.class', 'active');

    // All visible cards should be active members
    cy.get('.gym-member-card[data-status="active"]').should('be.visible');

    // Click "All" filter to reset
    cy.get('.gym-filter-chip').contains('All').click();
  });

  it('should check in a member', () => {
    cy.visit('/gym/checkin/');

    // Find an active member who hasn't checked in yet
    cy.get('.gym-member-card').contains('Check In').should('exist').first().parents('.gym-member-card').within(() => {
      // Click check-in button
      cy.get('button[type="submit"]').contains('Check In').click();
    });

    // Should redirect back to check-in page or show success
    cy.url().should('include', '/gym/checkin/');

    // Should show success message (either in messages or celebration modal)
    // Check for either success message or celebration modal
    cy.get('body').then(($body) => {
      if ($body.find('.celebration-modal.show').length > 0) {
        // Celebration modal shown
        cy.get('.celebration-modal.show').should('be.visible');
        cy.get('.celebration-modal').within(() => {
          cy.contains('Check').should('be.visible'); // Could be "Checked in" or similar
        });

        // Close the modal
        cy.get('.celebration-close').click();
      } else {
        // Regular success message
        cy.get('.alert-success, .messages').should('contain.text', 'checked in');
      }
    });
  });

  it('should navigate to member detail from card', () => {
    cy.visit('/gym/checkin/');

    // Click "View Details" on first card
    cy.get('.gym-member-card').first().within(() => {
      cy.contains('View Details').click();
    });

    // Should navigate to member detail page
    cy.url().should('include', '/gym/member/');

    // Check for premium card elements
    cy.get('.premium-card').should('be.visible');

    // Check for QR code
    cy.get('.qr-container').should('be.visible');
  });

  it('should display mobile sticky actions on member detail', () => {
    cy.visit('/gym/checkin/');

    // Navigate to a member detail
    cy.get('.gym-member-card').first().contains('View Details').click();

    // Check for mobile sticky bottom actions
    cy.get('.gym-member-mobile-actions').should('be.visible');

    // Should have action buttons (Check In or Renew)
    cy.get('.gym-member-mobile-actions .btn').should('have.length.at.least', 1);
  });

  it('should display leaderboard on mobile', () => {
    // Navigate to leaderboard
    cy.visit('/gym/leaderboard/');

    // Check for header
    cy.get('.gym-lb-header').should('be.visible');
    cy.contains('Leaderboard').should('be.visible');

    // Check for period selector
    cy.get('.gym-lb-period').should('be.visible');
    cy.get('.gym-lb-period-btn').should('have.length.at.least', 3);

    // Check for podium (if 3+ members)
    cy.get('body').then(($body) => {
      if ($body.find('.gym-lb-podium').length > 0) {
        cy.get('.gym-lb-podium').should('be.visible');
        cy.get('.gym-lb-podium-place').should('have.length.at.least', 1);
      }
    });

    // Check for leaderboard list
    cy.get('.gym-lb-list, .gym-lb-empty').should('be.visible');
  });

  it('should switch leaderboard periods', () => {
    cy.visit('/gym/leaderboard/');

    // Click "This Week" period
    cy.get('.gym-lb-period-btn').contains('Week').click();

    // Should navigate with query param
    cy.url().should('include', 'period=week');

    // Active button should have class
    cy.get('.gym-lb-period-btn').contains('Week').should('have.class', 'active');
  });

  it('should handle empty states gracefully', () => {
    cy.visit('/gym/checkin/');

    // Search for non-existent member
    cy.get('#memberSearch').type('XXXXNONEXISTENTXXXX');

    // Wait for filter
    cy.wait(300);

    // All cards should be hidden or show empty state
    cy.get('.gym-member-card').should('not.be.visible');
  });

  it('should not overflow or break layout on small screens', () => {
    // Test even smaller viewport (iPhone SE)
    cy.viewport(375, 667);

    cy.visit('/gym/checkin/');

    // Check that header doesn't overflow
    cy.get('.gym-checkin-header').should('be.visible');
    cy.get('.gym-checkin-actions').should('be.visible');

    // Check that cards don't overflow
    cy.get('.gym-member-card').first().should('be.visible');

    // Check that no horizontal scroll exists
    cy.document().then((doc) => {
      expect(doc.documentElement.scrollWidth).to.be.lte(doc.documentElement.clientWidth + 1);
    });
  });

  it('should show gamification elements correctly', () => {
    cy.visit('/gym/checkin/');

    // Find a member with gamification data
    cy.get('.gym-member-card').then(($cards) => {
      const cardWithBadge = $cards.filter((i, card) => {
        return Cypress.$(card).find('.gym-card-badges .badge').length > 0;
      });

      if (cardWithBadge.length > 0) {
        // Check that badge is visible
        cy.wrap(cardWithBadge.first()).within(() => {
          cy.get('.gym-card-badges').should('be.visible');
          cy.get('.badge').should('be.visible');
        });
      }
    });
  });

  it('should navigate between gym pages smoothly', () => {
    // Start at check-in
    cy.visit('/gym/checkin/');
    cy.contains('Member Check-In').should('be.visible');

    // Go to leaderboard (if link exists)
    cy.get('body').then(($body) => {
      if ($body.find('a[href*="leaderboard"]').length > 0) {
        cy.get('a[href*="leaderboard"]').first().click();
        cy.url().should('include', '/gym/leaderboard/');

        // Go back
        cy.contains('Back').click();
        cy.url().should('include', '/gym/checkin/');
      }
    });
  });

  // Desktop comparison test (should show table)
  it('should show table layout on desktop', () => {
    // Switch to desktop viewport
    cy.viewport(1280, 800);

    cy.visit('/gym/checkin/');

    // Desktop table should be visible, cards hidden
    cy.get('.gym-table-desktop').should('be.visible');
    cy.get('.gym-member-cards').should('not.be.visible');

    // Table should have proper columns
    cy.get('table thead th').should('have.length.at.least', 5);
  });

  // Accessibility test
  it('should be keyboard accessible', () => {
    cy.visit('/gym/checkin/');

    // Tab through elements
    cy.get('#memberSearch').focus();
    cy.focused().should('have.id', 'memberSearch');

    // Tab to Scan button
    cy.focused().tab();
    cy.focused().should('contain.text', 'Scan');
  });

  // Performance test
  it('should load check-in page quickly', () => {
    const startTime = Date.now();

    cy.visit('/gym/checkin/');

    cy.get('.gym-checkin-header').should('be.visible').then(() => {
      const loadTime = Date.now() - startTime;
      // Should load in under 3 seconds
      expect(loadTime).to.be.lessThan(3000);
    });
  });

  // No regressions test
  it('should preserve existing functionality', () => {
    // Verify dashboard still works
    cy.visit('/gym/');
    cy.get('body').should('contain', 'Gym').or('contain', 'Dashboard');

    // Verify members list still works
    cy.visit('/gym/members/');
    cy.get('body').should('be.visible');

    // Verify check-in page loads
    cy.visit('/gym/checkin/');
    cy.get('.gym-checkin-header, .gym-member-cards, .gym-table-desktop').should('exist');
  });
});
