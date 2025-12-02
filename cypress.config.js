const { defineConfig } = require('cypress');

module.exports = defineConfig({
  e2e: {
    baseUrl: 'http://127.0.0.1:8000',
    supportFile: 'cypress/support/e2e.js',
    specPattern: 'cypress/e2e/**/*.cy.{js,jsx,ts,tsx}',
    viewportWidth: 1280,
    viewportHeight: 720,
    video: false,
    screenshotOnRunFailure: true,
    defaultCommandTimeout: 10000,
    requestTimeout: 10000,
    responseTimeout: 10000,
    env: {
      // Test user credentials
      TEST_EMAIL: 'cindymahon@gmail.com',
      TEST_PASSWORD: '@Lincoln1863?',
    },
    setupNodeEvents(on, config) {
      // implement node event listeners here if needed
    },
  },
});

