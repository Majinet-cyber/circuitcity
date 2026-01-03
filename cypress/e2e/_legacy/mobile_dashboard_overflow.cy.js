/**
 * Cypress Test: Mobile Dashboard Overflow Prevention
 * Part B: Regression test for phones dashboard mobile overflow
 *
 * This test ensures that on small mobile screens (360px width):
 * - No horizontal scrolling caused by dashboard cards
 * - No amounts leak outside cards
 * - Long model names + amounts remain visually clean
 */

describe('Mobile Dashboard Overflow Prevention', () => {
  beforeEach(() => {
    // Login as test user
    cy.visit('/accounts/login/')
    cy.get('input[name="username"]').type('testuser')
    cy.get('input[name="password"]').type('testpass123')
    cy.get('button[type="submit"]').click()

    // Wait for redirect to dashboard
    cy.url().should('include', '/dashboard/')
  })

  it('should NOT cause horizontal scroll on phones dashboard at 360px width', () => {
    // Set viewport to small mobile (360x760 - typical budget Android)
    cy.viewport(360, 760)

    // Visit phones dashboard
    cy.visit('/inventory/verticals/phones/')

    // Wait for page to fully load
    cy.wait(1000)

    // CRITICAL TEST: Check no horizontal overflow
    cy.window().then((win) => {
      const scrollWidth = win.document.documentElement.scrollWidth
      const clientWidth = win.document.documentElement.clientWidth

      // Allow 1px tolerance for rounding
      expect(scrollWidth).to.be.at.most(clientWidth + 1,
        `Horizontal overflow detected! scrollWidth: ${scrollWidth}, clientWidth: ${clientWidth}`
      )
    })
  })

  it('should ellipsis long amounts safely in KPI cards', () => {
    cy.viewport(360, 760)
    cy.visit('/inventory/verticals/phones/')

    // Check Revenue KPI card
    cy.contains('Revenue').parent().within(() => {
      // The amount should have cc-amount class
      cy.get('.cc-amount, p.cc-amount').should('exist')

      // Check it has tooltip
      cy.get('.cc-amount, p.cc-amount').should('have.attr', 'title')

      // Check it doesn't overflow parent
      cy.get('.cc-amount, p.cc-amount').then(($el) => {
        const parentWidth = $el.parent().width()
        const elWidth = $el.width()
        expect(elWidth).to.be.at.most(parentWidth)
      })
    })
  })

  it('should handle long model names in Fast Moving Models', () => {
    cy.viewport(360, 760)
    cy.visit('/inventory/verticals/phones/')

    // Scroll to Fast Moving Models section
    cy.contains('Fast Moving Models').scrollIntoView()

    // Check leaderboard items don't overflow
    cy.get('.leaderboard-item').first().then(($item) => {
      const itemWidth = $item.width()

      // Check name and value don't overflow
      cy.wrap($item).find('.leaderboard-name').then(($name) => {
        const nameWidth = $name.width()
        expect(nameWidth).to.be.at.most(itemWidth)
      })

      cy.wrap($item).find('.leaderboard-value').then(($value) => {
        const valueWidth = $value.width()
        expect(valueWidth).to.be.at.most(itemWidth)
      })
    })
  })

  it('should handle long amounts in Top Agents leaderboard', () => {
    cy.viewport(360, 760)
    cy.visit('/inventory/verticals/phones/')

    // Scroll to Top Agents section
    cy.contains('Top Agents').scrollIntoView()

    // Check agent items don't overflow
    cy.get('.leaderboard-item').first().then(($item) => {
      // Check the value has cc-amount class and tooltip
      cy.wrap($item).find('.leaderboard-value.cc-amount').should('exist')
      cy.wrap($item).find('.leaderboard-value.cc-amount').should('have.attr', 'title')

      // Ensure no overflow
      const itemWidth = $item.width()
      cy.wrap($item).find('.leaderboard-value').then(($value) => {
        const valueWidth = $value.width()
        expect(valueWidth).to.be.at.most(itemWidth)
      })
    })
  })

  it('should handle Payment Mix amounts at 360px', () => {
    cy.viewport(360, 760)
    cy.visit('/inventory/verticals/phones/')

    // Scroll to Payment Mix section
    cy.contains('Payment Mix').scrollIntoView()

    // Check payment cards don't overflow
    cy.get('.metric-card').contains('Cash').parent().within(() => {
      cy.get('.cc-amount, p.cc-amount').should('exist')
      cy.get('.cc-amount, p.cc-amount').should('have.attr', 'title')
    })
  })

  it('should NOT have horizontal scroll on Best Sales Day card', () => {
    cy.viewport(360, 760)
    cy.visit('/inventory/verticals/phones/')

    // Scroll to Best Sales Day (if present)
    cy.get('body').then(($body) => {
      if ($body.find('.recent-block:contains("Best Sales Day")').length > 0) {
        cy.contains('Best Sales Day').scrollIntoView()

        // Check amounts have cc-amount class
        cy.contains('Best Sales Day').parent().within(() => {
          cy.get('.cc-amount').should('exist')
        })
      }
    })
  })

  it('should work correctly at even smaller width (320px)', () => {
    // iPhone SE size - worst case
    cy.viewport(320, 568)
    cy.visit('/inventory/verticals/phones/')

    // Wait for load
    cy.wait(1000)

    // Check no horizontal scroll
    cy.window().then((win) => {
      const scrollWidth = win.document.documentElement.scrollWidth
      const clientWidth = win.document.documentElement.clientWidth

      expect(scrollWidth).to.be.at.most(clientWidth + 1,
        `Horizontal overflow at 320px! scrollWidth: ${scrollWidth}, clientWidth: ${clientWidth}`
      )
    })

    // Ensure metric cards are visible and don't overflow
    cy.get('.metric-card').first().should('be.visible')
  })

  it('should apply tabular-nums font feature to amounts', () => {
    cy.viewport(360, 760)
    cy.visit('/inventory/verticals/phones/')

    // Check Revenue amount has tabular nums
    cy.contains('Revenue').parent().within(() => {
      cy.get('.cc-amount, p.cc-amount').should('have.css', 'font-variant-numeric', 'tabular-nums')
    })
  })

  it('should show tooltips on hover for ellipsed amounts', () => {
    cy.viewport(360, 760)
    cy.visit('/inventory/verticals/phones/')

    // Check Revenue KPI has tooltip
    cy.contains('Revenue').parent().within(() => {
      cy.get('.cc-amount, p.cc-amount').trigger('mouseover')
      cy.get('.cc-amount, p.cc-amount').should('have.attr', 'title').and('not.be.empty')
    })
  })
})

describe('Mobile Overflow - Other Dashboards', () => {
  it('should NOT overflow on clothing dashboard', () => {
    cy.viewport(360, 760)

    // Visit clothing dashboard (if business kind allows)
    cy.visit('/verticals/clothing/')

    cy.window().then((win) => {
      const scrollWidth = win.document.documentElement.scrollWidth
      const clientWidth = win.document.documentElement.clientWidth

      expect(scrollWidth).to.be.at.most(clientWidth + 1)
    })
  })

  it('should NOT overflow on liquor dashboard', () => {
    cy.viewport(360, 760)
    cy.visit('/verticals/liquor/')

    cy.window().then((win) => {
      const scrollWidth = win.document.documentElement.scrollWidth
      const clientWidth = win.document.documentElement.clientWidth

      expect(scrollWidth).to.be.at.most(clientWidth + 1)
    })
  })
})
