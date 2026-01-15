/**
 * CircuitCity / Emajinet - Cypress E2E Support
 * Clean Suite Reboot (Jan 2026)
 *
 * This file is loaded before every E2E test.
 * Import custom commands and configure global behavior.
 */

// Import custom commands
import './commands';

// ============================================================================
// GLOBAL CONFIGURATION
// ============================================================================

// Disable uncaught exception handling (prevents test failures from app errors)
Cypress.on('uncaught:exception', (err, runnable) => {
  // Log the error but don't fail the test
  console.warn('Uncaught exception:', err.message);

  // Return false to prevent Cypress from failing the test
  // We use assertNoServerError() explicitly in tests instead
  return false;
});

// ============================================================================
// BEFORE EACH TEST
// ============================================================================
beforeEach(() => {
  // Clear cookies and local storage between tests for isolation
  cy.clearCookies();
  cy.clearLocalStorage();

  // Log the test name for debugging
  cy.log(`🧪 Starting: ${Cypress.currentTest.title}`);
});

// ============================================================================
// AFTER EACH TEST
// ============================================================================
afterEach(() => {
  // Log test completion
  cy.log(`✅ Completed: ${Cypress.currentTest.title}`);
});
