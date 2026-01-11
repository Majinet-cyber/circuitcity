const { defineConfig } = require('cypress');

module.exports = defineConfig({
  e2e: {
    baseUrl: 'http://127.0.0.1:8000',
    supportFile: 'cypress/support/e2e.js',
    specPattern: 'cypress/e2e/**/*.cy.{js,jsx,ts,tsx}',
    viewportWidth: 1280,
    viewportHeight: 720,

    // ✅ Slow-network resilient settings (15s+ tolerance)
    video: false,
    screenshotOnRunFailure: true,
    defaultCommandTimeout: 15000,   // 15s per command (matches intercept waits)
    requestTimeout: 15000,          // 15s for XHR/fetch
    responseTimeout: 15000,         // 15s for responses
    pageLoadTimeout: 60000,         // 60s for full page loads

    // ✅ Light retry for CI stability (not excessive)
    retries: {
      runMode: 1,      // Retry once in CI (npx cypress run)
      openMode: 0,     // No retries in interactive mode
    },

    env: {
      // Test user credentials (fixed email)
      TEST_EMAIL: 'empire@gmai.com',
      TEST_PASSWORD: '@Lincoln1863?',
    },

    setupNodeEvents(on, config) {
      // ✅ Run PyTests BEFORE Cypress starts (unless already ran in wrapper)
      on('before:run', async () => {
        // Skip pytest if wrapper already ran it (prevents double execution)
        if (process.env.CC_SKIP_PYTEST === '1') {
          console.log('[test-system] Skipping pytest in Cypress (already ran in wrapper).');
          return;
        }
        
        console.log('\n🔄 Running PyTests before Cypress...\n');
        
        try {
          const { execSync } = require('child_process');
          execSync('node scripts/run_pytests_and_summarize.mjs', {
            stdio: 'inherit',
            shell: true,
          });
          console.log('\n✅ PyTest execution complete. Starting Cypress...\n');
        } catch (err) {
          // Script always exits 0, so this shouldn't happen
          // But if it does, log and continue
          console.error('⚠️  PyTest script error (continuing anyway):', err.message);
        }
      });
    },
  },
});
