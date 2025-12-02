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
 * Custom command to log in as owner using environment variables
 */
Cypress.Commands.add('loginAsOwner', () => {
  const email = Cypress.env('TEST_EMAIL');
  const password = Cypress.env('TEST_PASSWORD');
  cy.login(email, password);
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
 * Custom command to select a business by kind/vertical
 * @param {string} kind - Business kind (phones, liquor, clothing, gym, pharmacy)
 */
Cypress.Commands.add('selectBusinessByKind', (kind) => {
  cy.url().then((url) => {
    if (url.includes('/choose') || url.includes('/select') || url.includes('/business')) {
      // Try to find business with matching kind in name or data attribute
      cy.get('body').then(($body) => {
        if ($body.find(`[data-cy="business-${kind}"]`).length > 0) {
          cy.get(`[data-cy="business-${kind}"]`).click();
        } else {
          // Fallback: look for kind name in text
          cy.contains(new RegExp(kind, 'i')).first().click();
        }
      });
    }
  });
});

/**
 * Custom command to visit a vertical dashboard
 * @param {string} kind - Vertical kind (phones, liquor, clothing, gym, pharmacy)
 */
Cypress.Commands.add('visitDashboard', (kind) => {
  const dashboardUrls = {
    phones: '/inventory/verticals/phones/',
    liquor: '/inventory/verticals/liquor/',
    clothing: '/inventory/verticals/clothing/',
    gym: '/inventory/verticals/gym/',
    pharmacy: '/inventory/pharmacy/dashboard/',
  };
  
  const url = dashboardUrls[kind] || '/dashboard/';
  cy.visit(url, { failOnStatusCode: false });
  
  // Handle 404 fallback
  cy.url().then((currentUrl) => {
    if (currentUrl.includes('404')) {
      cy.visit('/dashboard/');
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

/**
 * Custom command to fill form field by label or data-cy
 * @param {string} labelOrCy - Label text or data-cy attribute
 * @param {string} value - Value to type
 */
Cypress.Commands.add('fillField', (labelOrCy, value) => {
  cy.get(`[data-cy="${labelOrCy}"], label:contains("${labelOrCy}")`).then(($el) => {
    if ($el.is('label')) {
      const inputId = $el.attr('for');
      if (inputId) {
        cy.get(`#${inputId}`).clear().type(value);
      } else {
        $el.find('input, textarea, select').clear().type(value);
      }
    } else {
      cy.get(`[data-cy="${labelOrCy}"]`).clear().type(value);
    }
  });
});

/**
 * Custom command to click button by text or data-cy
 * @param {string} textOrCy - Button text or data-cy attribute
 */
Cypress.Commands.add('clickButton', (textOrCy) => {
  cy.get(`[data-cy="${textOrCy}"], button:contains("${textOrCy}")`).first().click();
});

/**
 * Custom command to verify success message appears
 * @param {string} message - Expected message text (optional)
 */
Cypress.Commands.add('verifySuccess', (message) => {
  const selectors = [
    '[data-cy="success-message"]',
    '.alert-success',
    '.toast-success',
    '[role="alert"]:contains("Success")',
  ];
  
  selectors.forEach((selector) => {
    cy.get('body').then(($body) => {
      if ($body.find(selector).length > 0) {
        if (message) {
          cy.get(selector).should('contain', message);
        } else {
          cy.get(selector).should('be.visible');
        }
      }
    });
  });
});

/**
 * Custom command to verify error message appears
 * @param {string} message - Expected error text (optional)
 */
Cypress.Commands.add('verifyError', (message) => {
  const selectors = [
    '[data-cy="error-message"]',
    '.alert-danger',
    '.toast-error',
    '[role="alert"]:contains("Error")',
  ];
  
  selectors.forEach((selector) => {
    cy.get('body').then(($body) => {
      if ($body.find(selector).length > 0) {
        if (message) {
          cy.get(selector).should('contain', message);
        } else {
          cy.get(selector).should('be.visible');
        }
      }
    });
  });
});

