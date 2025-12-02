// ***********************************************
// Custom Cypress commands for CircuitCity
// ***********************************************

/**
 * Custom command to log in a user
 * @param {string} email - User email
 * @param {string} password - User password
 */
Cypress.Commands.add('login', (email, password) => {
  cy.visit('/accounts/login/');
  
  cy.get('input[name="username"], input[name="email"], [data-cy=login-email]')
    .clear()
    .type(email);
    
  cy.get('input[name="password"], [data-cy=login-password]')
    .clear()
    .type(password);
    
  cy.get('button[type="submit"], [data-cy=login-submit]').click();
  
  // Wait for redirect after successful login
  cy.url().should('not.include', '/accounts/login/');
});

/**
 * Custom command to select a business (if on business chooser page)
 * @param {string} businessName - Name of business to select
 */
Cypress.Commands.add('selectBusiness', (businessName) => {
  cy.url().then((url) => {
    if (url.includes('/choose') || url.includes('/select')) {
      cy.contains(businessName).click();
    }
  });
});

/**
 * Custom command to wait for element to be visible
 * @param {string} selector - CSS selector or data-cy attribute
 */
Cypress.Commands.add('waitForElement', (selector) => {
  cy.get(selector, { timeout: 10000 }).should('be.visible');
});

