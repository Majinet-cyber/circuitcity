const { defineConfig } = require('cypress');

module.exports = defineConfig({
  e2e: {
    baseUrl: 'http://127.0.0.1:8000',
    supportFile: 'cypress/support/e2e.js',
    specPattern: 'cypress/e2e/**/*.cy.{js,jsx,ts,tsx}',
    viewportWidth: 1280,
    viewportHeight: 720,

    // ✅ More tolerant settings for slow network / slow server
    video: false,
    screenshotOnRunFailure: true,
    defaultCommandTimeout: 20000,   // was 10s → now 20s per command
    requestTimeout: 20000,          // allow slower API calls
    responseTimeout: 40000,         // wait longer for responses
    pageLoadTimeout: 90000,         // up to 90s for full page load

    env: {
      // Test user credentials (fixed email)
      TEST_EMAIL: 'empire@gmai.com',
      TEST_PASSWORD: '@Lincoln1863?',
    },

    setupNodeEvents(on, config) {
      // implement node event listeners here if needed
    },
  },
});
