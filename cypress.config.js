/**
 * Cypress E2E Configuration
 * CircuitCity / Emajinet - Clean Suite Reboot (Jan 2026)
 *
 * SLOW NETWORK FRIENDLY:
 * - High timeouts for slow connections
 * - Step waits via STEP_WAIT_MS env (default 12000ms)
 * - Retries enabled for stability
 */
const { defineConfig } = require('cypress');

module.exports = defineConfig({
  e2e: {
    // Base URL from env or default to local
    baseUrl: process.env.CYPRESS_BASE_URL || 'http://127.0.0.1:8000',
    supportFile: 'cypress/support/e2e.js',
    specPattern: 'cypress/e2e/**/*.cy.js',

    // Viewport: mobile-first by default, desktop tests can override
    viewportWidth: 375,
    viewportHeight: 812,

    // ============================================
    // SLOW NETWORK RESILIENT TIMEOUTS
    // ============================================
    defaultCommandTimeout: 20000,   // 20s per command
    requestTimeout: 20000,          // 20s for XHR/fetch
    responseTimeout: 60000,         // 60s for responses
    pageLoadTimeout: 120000,        // 120s for full page loads
    taskTimeout: 60000,             // 60s for cy.task

    // ============================================
    // RETRY SETTINGS FOR STABILITY
    // ============================================
    retries: {
      runMode: 2,      // Retry twice in CI (npx cypress run)
      openMode: 0,     // No retries in interactive mode
    },

    // ============================================
    // VIDEO & SCREENSHOTS
    // ============================================
    video: false,                   // Disable video for faster runs
    screenshotOnRunFailure: true,   // Capture on failure for debugging

    // ============================================
    // ENV VARIABLES
    // ============================================
    env: {
      // Step wait duration (ms) - 12 seconds default for slow networks
      STEP_WAIT_MS: 12000,

      // E2E Mode flag - enables test-only endpoints
      E2E_MODE: true,

      // E2E OTP bypass code
      E2E_OTP_BYPASS: '000000',
    },

    setupNodeEvents(on, config) {
      // Allow overriding STEP_WAIT_MS from environment
      if (process.env.STEP_WAIT_MS) {
        config.env.STEP_WAIT_MS = parseInt(process.env.STEP_WAIT_MS, 10);
      }

      // Allow overriding base URL from environment
      if (process.env.CYPRESS_BASE_URL) {
        config.baseUrl = process.env.CYPRESS_BASE_URL;
      }

      // Task for creating test users via Django management command
      on('task', {
        seedE2EUser({ vertical }) {
          return new Promise((resolve, reject) => {
            const { execSync } = require('child_process');
            try {
              const result = execSync(
                `python manage.py seed_e2e_user --vertical=${vertical} --json`,
                { encoding: 'utf8', timeout: 30000 }
              );
              // Parse JSON output from management command
              const data = JSON.parse(result.trim());
              resolve(data);
            } catch (err) {
              // Return null if seeding fails (tests can handle this)
              console.warn(`[seed_e2e_user] Failed for ${vertical}:`, err.message);
              resolve(null);
            }
          });
        },

        log(message) {
          console.log(message);
          return null;
        },
      });

      return config;
    },
  },
});
