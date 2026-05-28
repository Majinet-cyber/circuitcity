const { defineConfig } = require("cypress");

module.exports = defineConfig({
  e2e: {
    baseUrl: "http://localhost:8000",
    viewportWidth: 390,
    viewportHeight: 844,
    defaultCommandTimeout: 8000,
    requestTimeout: 10000,
    specPattern: "cypress/e2e/**/*.cy.{js,jsx,ts,tsx}",
    supportFile: "cypress/support/e2e.js",
    screenshotsFolder: "cypress/screenshots",
    videosFolder: "cypress/videos",
    video: false,
    env: {
      UNDERWRITER_USER: "underwriter1",
      UNDERWRITER_PASS: "testpass123",
      MERCHANT_USER: "merchant1",
      MERCHANT_PASS: "testpass123",
      HQ_USER: "hqadmin",
      HQ_PASS: "testpass123",
      DEMO_CONTRACT: "TS-MW-00000001",
      DEMO_PAYG: "TSG000001",
    },
  },
});
