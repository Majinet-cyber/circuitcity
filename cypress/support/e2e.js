// TengaSale Cypress support file

// Custom commands
Cypress.Commands.add("loginAs", (username, password) => {
  cy.session([username, password], () => {
    cy.visit("/accounts/login/");
    cy.get('input[name="username"]').type(username);
    cy.get('input[name="password"]').type(password);
    cy.get('button[type="submit"]').click();
    cy.url().should("not.include", "/login/");
  });
});

Cypress.Commands.add("loginAsUnderwriter", () => {
  cy.loginAs(
    Cypress.env("UNDERWRITER_USER"),
    Cypress.env("UNDERWRITER_PASS")
  );
});

Cypress.Commands.add("loginAsMerchant", () => {
  cy.loginAs(Cypress.env("MERCHANT_USER"), Cypress.env("MERCHANT_PASS"));
});

Cypress.Commands.add("loginAsHQ", () => {
  cy.loginAs(Cypress.env("HQ_USER"), Cypress.env("HQ_PASS"));
});

// Alias for backwards compatibility
Cypress.Commands.add("loginHQ", () => {
  cy.loginAs(Cypress.env("HQ_USER"), Cypress.env("HQ_PASS"));
});

// Prevent uncaught errors failing tests in dev mode
Cypress.on("uncaught:exception", (err) => {
  if (err.message.includes("ResizeObserver") || err.message.includes("Script error")) {
    return false;
  }
});
