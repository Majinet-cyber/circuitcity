# Legacy Cypress Tests

This directory contains old/outdated Cypress E2E tests that have been replaced by the new test suite.

## New Test Structure

The new test suite is organized as follows:

- `00_smoke_auth.cy.js` - Authentication smoke test across all verticals
- `verticals/phones_journey.cy.js` - Full phones vertical journey
- `verticals/clothing_journey.cy.js` - Full clothing vertical journey
- `verticals/liquor_journey.cy.js` - Full liquor vertical journey
- `verticals/pharmacy_journey.cy.js` - Full pharmacy vertical journey
- `verticals/groceries_journey.cy.js` - Full groceries vertical journey
- `verticals/gym_journey.cy.js` - Full gym vertical journey

## Why These Tests Were Moved

These tests were moved to `_legacy/` because:

1. **Replaced by new journey tests**: The new vertical journey tests provide comprehensive coverage of the full user workflows
2. **Outdated selectors**: Many tests relied on brittle CSS selectors or text-based selectors
3. **Inconsistent structure**: Old tests had varying patterns and approaches
4. **Maintenance burden**: Keeping old tests alongside new ones creates confusion

## When to Reference Legacy Tests

You may want to reference these tests if:

- You need to understand how a specific feature was tested before
- You're debugging a regression and need historical context
- You want to extract specific test cases that weren't covered in the new suite

## Migration Notes

The new test suite:

- Uses `cy.session()` for faster test runs
- Implements test-only login endpoint (gated by `ALLOW_TEST_LOGIN=true`)
- Uses `data-cy` selectors with graceful fallbacks
- Follows consistent patterns across all verticals
- Includes comprehensive error handling and assertions

## Files Moved

- `clothing_full_journey.cy.js` → Replaced by `verticals/clothing_journey.cy.js`
- `liquor_full_journey.cy.js` → Replaced by `verticals/liquor_journey.cy.js`
- `pharmacy_full_journey.cy.js` → Replaced by `verticals/pharmacy_journey.cy.js`
- `gym_full_journey.cy.js` → Replaced by `verticals/gym_journey.cy.js`
- `phones_full_journey.cy.js` → Replaced by `verticals/phones_journey.cy.js`
- `journeys/manager_full_journey.cy.js` → Functionality merged into vertical journey tests
- Various smoke tests and specific feature tests → Functionality integrated into new journey tests

## Running Legacy Tests

If you need to run legacy tests for reference:

```bash
# Run a specific legacy test
npx cypress run --spec "cypress/e2e/_legacy/clothing_full_journey.cy.js"

# Run all legacy tests (not recommended)
npx cypress run --spec "cypress/e2e/_legacy/**/*.cy.js"
```

**Note**: Legacy tests may not work with the new test infrastructure (test login endpoint, session caching, etc.). They are kept for reference only.
