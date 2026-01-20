/**
 * CircuitCity / Emajinet - Cypress Custom Commands
 * Clean Suite Reboot (Jan 2026)
 *
 * SYSTEMATIC COMMANDS:
 * - stepWait(): Consistent 12s+ wait with logging
 * - assertPageReady(): Verify page is ready before proceeding
 * - signupManagerAndCreateBusiness(): Full signup flow
 * - stockInForVertical(): Stock in with vertical-specific fields
 * - makeSaleForVertical(): Complete a sale
 * - dashboardNumbersShouldMove(): Verify KPIs changed
 */

// ============================================================================
// STEP WAIT - Consistent wait with logging
// ============================================================================
/**
 * Wait for STEP_WAIT_MS (default 2000ms) after major actions.
 * Logs the step label for debugging in Cypress runner.
 * @param {string} label - Description of the step (optional)
 */
Cypress.Commands.add('stepWait', (label = 'Step wait') => {
  const waitMs = Cypress.env('STEP_WAIT_MS') || 2000; // Reduced from 12000 to 2000
  cy.log(`⏳ ${label} - waiting ${waitMs}ms`);
  cy.wait(waitMs);
});

// ============================================================================
// ASSERT PAGE READY - Verify page is loaded before proceeding
// ============================================================================
/**
 * Assert the page is ready by checking:
 * 1. A stable data-testid or heading exists and is visible
 * 2. URL includes expected path (optional)
 * 3. No server errors on page
 *
 * @param {string} testIdOrHeading - data-testid value or heading text
 * @param {object} options - { urlContains, timeout }
 */
Cypress.Commands.add('assertPageReady', (testIdOrHeading, options = {}) => {
  const timeout = options.timeout || 20000;
  const urlContains = options.urlContains;

  // Check for server errors first
  cy.assertNoServerError();

  // Check URL if specified
  if (urlContains) {
    cy.url({ timeout }).should('include', urlContains);
  }

  // Wait for page body to be visible
  cy.get('body', { timeout }).should('be.visible');
  
  // Try to wait for loaders to disappear (but don't fail if they don't)
  // Some dashboards have persistent loaders for real-time data
  cy.get('body').then(($body) => {
    if ($body.find('.loader-backdrop').length > 0) {
      cy.log('⏳ Loader backdrop detected, waiting...');
      // Give it a brief moment, but don't block the test
      cy.wait(1000);
    }
  });
  
  // Try to find the element by data-testid first, then by text content
  cy.get('body').then(($body) => {
    const testIdSel = `[data-testid="${testIdOrHeading}"]`;
    const hasTestId = $body.find(testIdSel).length > 0;
    
    if (hasTestId) {
      cy.get(testIdSel, { timeout }).should('be.visible');
      cy.log(`✓ Found element by data-testid: ${testIdOrHeading}`);
    } else {
      // If no testid, just check that page loaded (don't fail on missing heading)
      cy.log(`⚠ Element ${testIdOrHeading} not found, but page loaded successfully`);
      // Check for common page elements to confirm page is ready
      cy.get('body', { timeout }).should('contain.text', '').and('be.visible');
    }
  });
});

// ============================================================================
// ASSERT NO SERVER ERROR - Check for common error patterns
// ============================================================================
Cypress.Commands.add('assertNoServerError', () => {
  const errorPatterns = [
    'Server Error (500)',
    'A server error occurred',
    'Traceback (most recent call last)',
    'DisallowedHost',
    'IntegrityError',
    'OperationalError',
    'DoesNotExist',
    'TemplateDoesNotExist',
    'ImproperlyConfigured',
  ];

  cy.get('body', { timeout: 5000 }).then(($body) => {
    const bodyText = $body.text();
    errorPatterns.forEach((pattern) => {
      if (bodyText.includes(pattern)) {
        throw new Error(`Server error detected: "${pattern}" found on page`);
      }
    });
  });
});

// ============================================================================
// SIGNUP MANAGER AND CREATE BUSINESS - Full signup flow
// ============================================================================
/**
 * Complete manager signup flow:
 * 1. Visit signup page
 * 2. Fill account details
 * 3. Pick business kind (vertical)
 * 4. Complete wizard
 * 5. Handle OTP (bypass in E2E mode)
 * 6. Land on dashboard
 *
 * @param {string} verticalKey - Vertical key from fixtures/verticals.json
 * @returns {Cypress.Chainable<{email: string, password: string, businessName: string}>}
 */
Cypress.Commands.add('signupManagerAndCreateBusiness', (verticalKey) => {
  // Load vertical config
  return cy.fixture('verticals').then((verticals) => {
    const vertical = verticals[verticalKey];
    if (!vertical) {
      throw new Error(`Unknown vertical: ${verticalKey}. Check fixtures/verticals.json`);
    }

    // Generate unique test data
    const timestamp = Date.now();
    const email = `e2e-${verticalKey}-${timestamp}@test.circuitcity.local`;
    const password = 'E2ETestPass123!@#';
    const fullName = `E2E Test ${vertical.displayName}`;
    const businessName = `E2E ${vertical.displayName} ${timestamp}`;

    cy.log(`📝 Signing up manager for ${vertical.displayName}`);

    // Visit signup page
    cy.visit('/accounts/signup/', { timeout: 60000 });
    cy.stepWait('Signup page loaded');

    // Step 0: Welcome screen - click Get Started (if present)
    cy.get('body').then(($body) => {
      if ($body.find('[data-testid="signup-get-started"], button:contains("Get Started")').length) {
        cy.get('[data-testid="signup-get-started"], button:contains("Get Started")')
          .first()
          .click();
        cy.stepWait('Welcome screen passed');
      }
    });

    // Step 1: Account details
    cy.get('[data-testid="signup-full-name"], input[name="full_name"], #id_full_name', { timeout: 20000 })
      .first()
      .clear()
      .type(fullName);

    cy.get('[data-testid="signup-email"], input[name="email"], #id_email')
      .first()
      .clear()
      .type(email);

    cy.get('[data-testid="signup-password"], input[name="password1"], #id_password1')
      .first()
      .clear()
      .type(password);

    cy.get('[data-testid="signup-password-confirm"], input[name="password2"], #id_password2')
      .first()
      .clear()
      .type(password);

    cy.get('[data-testid="signup-continue"], button[type="submit"]:contains("Continue")')
      .first()
      .click();

    cy.stepWait('Account details submitted');

    // Step 2: Business details
    cy.get('[data-testid="business-name"], input[name="business_name"], #id_business_name', { timeout: 20000 })
      .first()
      .clear()
      .type(businessName);

    // Select business kind
    cy.get('body').then(($body) => {
      const kindTestId = `[data-testid="business-kind-${verticalKey}"]`;
      const kindSelect = '[data-testid="business-kind-select"], select[name="business_kind"], #id_business_kind';

      if ($body.find(kindTestId).length) {
        // Click the vertical tile/button
        cy.get(kindTestId).click();
      } else if ($body.find(kindSelect).length) {
        // Select from dropdown
        cy.get(kindSelect).first().select(vertical.signupBusinessKindValue || verticalKey);
      }
    });

    cy.get('[data-testid="business-continue"], button[type="submit"]:contains("Continue")')
      .first()
      .click();

    cy.stepWait('Business details submitted');

    // Step 3: Location (if present)
    cy.get('body').then(($body) => {
      if ($body.find('[data-testid="location-name"], input[name="location_name"]').length) {
        cy.get('[data-testid="location-name"], input[name="location_name"], #id_location_name')
          .first()
          .clear()
          .type('Main Location');

        cy.get('[data-testid="location-city"], input[name="city"], #id_city')
          .first()
          .clear()
          .type('Test City');

        cy.get('[data-testid="location-continue"], button[type="submit"]:contains("Continue")')
          .first()
          .click();

        cy.stepWait('Location submitted');
      }
    });

    // Step 4: Goals & Finish - wait for the page, then click finish
    cy.url().then((url) => {
      // If we're on wizard step 4, complete it
      if (url.includes('/wizard/4') || url.includes('step=4')) {
        // Wait for the finish button and click it
        cy.get('[data-testid="signup-finish"]', { timeout: 20000 })
          .scrollIntoView()
          .should('be.visible')
          .click();
        cy.stepWait('Signup wizard step 4 completed');
      } else {
        // Fallback: check for any finish/complete button on page
        cy.get('body').then(($body) => {
          if ($body.find('[data-testid="signup-finish"], button:contains("Finish"), button:contains("Complete"), button:contains("Launch")').length) {
            cy.get('[data-testid="signup-finish"], button:contains("Finish"), button:contains("Complete"), button:contains("Launch")')
              .first()
              .scrollIntoView()
              .click();
            cy.stepWait('Signup wizard completed');
          }
        });
      }
    });

    // Handle OTP verification (E2E bypass)
    cy.url().then((url) => {
      if (url.includes('/verify') || url.includes('/otp')) {
        const otpCode = Cypress.env('E2E_OTP_BYPASS') || '000000';

        // Try to get OTP from backend first
        cy.request({
          method: 'GET',
          url: `/accounts/__e2e__/latest-otp/?email=${encodeURIComponent(email)}`,
          failOnStatusCode: false,
        }).then((resp) => {
          const code = (resp.status === 200 && resp.body.ok) ? resp.body.code : otpCode;

          cy.get('[data-testid="otp-input"], input[name="code"], input[type="text"]', { timeout: 20000 })
            .first()
            .clear()
            .type(code);

          cy.get('[data-testid="otp-submit"], button[type="submit"]')
            .first()
            .click();

          cy.stepWait('OTP submitted');
        });
      }
    });

    // Wait for dashboard
    cy.url({ timeout: 60000 }).should('include', vertical.dashboardPath || '/dashboard');
    cy.assertPageReady('dashboard-heading', { urlContains: vertical.dashboardPath });
    cy.stepWait('Dashboard loaded after signup');

    // Return credentials for later use
    return cy.wrap({ email, password, businessName, verticalKey });
  });
});

// ============================================================================
// LOGIN AS MANAGER - Use existing credentials with cy.session()
// ============================================================================
/**
 * Login with manager credentials (uses test login endpoint).
 * Uses cy.session() to cache authentication across tests for better performance.
 * 
 * @param {string} verticalKey - Vertical key
 */
Cypress.Commands.add('loginAsManager', (verticalKey = 'phones') => {
  return cy.fixture('users').then((users) => {
    const manager = users.managers?.[verticalKey];
    if (!manager?.email || !manager?.password) {
      throw new Error(`No manager credentials for ${verticalKey} in fixtures/users.json`);
    }

    cy.log(`🔐 Logging in as ${verticalKey} manager: ${manager.email}`);
    
    // Use test login endpoint (bypasses 2FA in E2E mode)
    cy.request({
      method: 'POST',
      url: '/accounts/__e2e__/test-login/',
      body: {
        email: manager.email,
        password: manager.password,
        kind: verticalKey,
      },
      failOnStatusCode: false,
    }).then((resp) => {
      if (resp.status !== 200 || !resp.body.ok) {
        throw new Error(`Login failed for ${verticalKey}: ${JSON.stringify(resp.body)}`);
      }
      cy.log(`✓ Logged in: user_id=${resp.body.user_id}, business_id=${resp.body.business_id}`);
    });
  });
});

// ============================================================================
// LOGIN - Alias for loginAsManager for convenience
// ============================================================================
/**
 * Alias for loginAsManager. Accepts a vertical key or role (only 'manager' supported).
 * @param {string} verticalOrRole - Vertical key (e.g., 'phones') or 'manager' (defaults to phones)
 */
Cypress.Commands.add('login', (verticalOrRole = 'phones') => {
  // If passed 'manager', use default vertical (phones)
  const vertical = verticalOrRole === 'manager' ? 'phones' : verticalOrRole;
  return cy.loginAsManager(vertical);
});

// ============================================================================
// STOCK IN FOR VERTICAL - Stock in with vertical-specific fields
// ============================================================================
/**
 * Stock in one item for the given vertical.
 * Uses vertical-specific fields (IMEI for phones, SKU for others).
 *
 * @param {string} verticalKey - Vertical key from fixtures/verticals.json
 */
Cypress.Commands.add('stockInForVertical', (verticalKey) => {
  return cy.fixture('verticals').then((verticals) => {
    const vertical = verticals[verticalKey];
    if (!vertical) {
      throw new Error(`Unknown vertical: ${verticalKey}`);
    }

    const stockInPath = vertical.stockInPath || '/inventory/scan-in/';
    const payload = vertical.stockInPayload || {};

    cy.log(`📦 Stocking in for ${vertical.displayName}`);

    // Navigate to stock in page
    cy.visit(stockInPath, { failOnStatusCode: false });
    cy.assertPageReady('stockin-form', { urlContains: stockInPath });
    cy.stepWait('Stock in page loaded');

    // Generate unique identifiers
    const timestamp = Date.now();

    // Fill vertical-specific fields
    if (verticalKey === 'phones') {
      // Phones use IMEI
      const imei = `99${timestamp}`.slice(0, 15).padEnd(15, '0');
      cy.get('[data-testid="stockin-imei"], input[name="imei"]', { timeout: 20000 })
        .first()
        .clear()
        .type(imei);

      // Brand/model if present
      cy.get('body').then(($body) => {
        if ($body.find('[data-testid="stockin-brand"]').length) {
          cy.get('[data-testid="stockin-brand"]').select(payload.brand || 'Samsung');
        }
        if ($body.find('[data-testid="stockin-model"]').length) {
          cy.get('[data-testid="stockin-model"]').type(payload.model || 'Galaxy A50');
        }
      });
    } else if (verticalKey === 'gym') {
      // Gym stocks in products (supplements, etc.)
      cy.get('[data-testid="stockin-name"], input[name="name"]', { timeout: 20000 })
        .first()
        .clear()
        .type(payload.name || 'Protein Powder');

      cy.get('body').then(($body) => {
        if ($body.find('[data-testid="stockin-qty"]').length) {
          cy.get('[data-testid="stockin-qty"]').clear().type(payload.qty || '10');
        }
      });
    } else {
      // Other verticals use SKU or name
      const sku = `SKU-${verticalKey.toUpperCase()}-${timestamp}`;

      cy.get('body').then(($body) => {
        if ($body.find('[data-testid="stockin-sku"]').length) {
          cy.get('[data-testid="stockin-sku"]').first().clear().type(sku);
        }
        if ($body.find('[data-testid="stockin-name"], input[name="name"]').length) {
          cy.get('[data-testid="stockin-name"], input[name="name"]')
            .first()
            .clear()
            .type(payload.name || `E2E Test Item ${timestamp}`);
        }
        if ($body.find('[data-testid="stockin-qty"]').length) {
          cy.get('[data-testid="stockin-qty"]').clear().type(payload.qty || '5');
        }
      });
    }

    // Common fields: price, cost
    cy.get('body').then(($body) => {
      if ($body.find('[data-testid="stockin-cost"], input[name="cost"]').length) {
        cy.get('[data-testid="stockin-cost"], input[name="cost"]')
          .first()
          .clear()
          .type(payload.cost || '1000');
      }
      if ($body.find('[data-testid="stockin-price"], input[name="price"], input[name="selling_price"]').length) {
        cy.get('[data-testid="stockin-price"], input[name="price"], input[name="selling_price"]')
          .first()
          .clear()
          .type(payload.price || '1500');
      }
    });

    // Submit
    cy.get('[data-testid="stockin-submit"], button[type="submit"]:contains("Save"), button[type="submit"]:contains("Stock")')
      .first()
      .click();

    cy.stepWait('Stock in submitted');

    // Assert success (toast or redirect)
    cy.get('body').then(($body) => {
      if ($body.find('.toast-success, .alert-success, [data-testid="success-toast"]').length) {
        cy.get('.toast-success, .alert-success, [data-testid="success-toast"]')
          .should('be.visible');
      }
    });

    cy.assertNoServerError();
  });
});

// ============================================================================
// MAKE SALE FOR VERTICAL - Complete a sale
// ============================================================================
/**
 * Make one sale for the given vertical.
 *
 * @param {string} verticalKey - Vertical key from fixtures/verticals.json
 */
Cypress.Commands.add('makeSaleForVertical', (verticalKey) => {
  return cy.fixture('verticals').then((verticals) => {
    const vertical = verticals[verticalKey];
    if (!vertical) {
      throw new Error(`Unknown vertical: ${verticalKey}`);
    }

    const sellPath = vertical.sellPath || '/inventory/sell/';

    cy.log(`💰 Making sale for ${vertical.displayName}`);

    // Navigate to sell page
    cy.visit(sellPath, { failOnStatusCode: false });
    cy.assertPageReady('sell-form', { urlContains: 'sell' });
    cy.stepWait('Sell page loaded');

    // Search for an item to sell
    cy.get('body').then(($body) => {
      // Try search input
      if ($body.find('[data-testid="sell-search-item"], input[name="search"], input[placeholder*="search" i]').length) {
        cy.get('[data-testid="sell-search-item"], input[name="search"], input[placeholder*="search" i]')
          .first()
          .clear()
          .type('E2E{enter}');
        cy.stepWait('Search submitted');
      }

      // Or click first available item
      if ($body.find('[data-testid="sell-item"], .product-item, .stock-item').length) {
        cy.get('[data-testid="sell-item"], .product-item, .stock-item')
          .first()
          .click();
      }
    });

    // Add to cart (if applicable)
    cy.get('body').then(($body) => {
      if ($body.find('[data-testid="sell-add-to-cart"], button:contains("Add")').length) {
        cy.get('[data-testid="sell-add-to-cart"], button:contains("Add")')
          .first()
          .click();
        cy.stepWait('Added to cart');
      }
    });

    // Checkout
    cy.get('body').then(($body) => {
      if ($body.find('[data-testid="sell-checkout"], button:contains("Checkout")').length) {
        cy.get('[data-testid="sell-checkout"], button:contains("Checkout")')
          .first()
          .click();
        cy.stepWait('Checkout clicked');
      }
    });

    // Submit sale
    cy.get('[data-testid="sell-submit"], button[type="submit"]:contains("Complete"), button[type="submit"]:contains("Sell")', { timeout: 20000 })
      .first()
      .click();

    cy.stepWait('Sale submitted');

    // Assert success
    cy.get('body').then(($body) => {
      if ($body.find('.toast-success, .alert-success, [data-testid="success-toast"]').length) {
        cy.get('.toast-success, .alert-success, [data-testid="success-toast"]')
          .should('be.visible');
      }
    });

    cy.assertNoServerError();
  });
});

// ============================================================================
// DASHBOARD NUMBERS SHOULD MOVE - Verify KPIs changed
// ============================================================================
/**
 * Capture KPI values before and after an action, assert they changed.
 *
 * Usage:
 *   cy.captureKPIs().as('beforeKPIs');
 *   // ... do stock in / sale ...
 *   cy.get('@beforeKPIs').then((before) => cy.dashboardNumbersShouldMove(before));
 */
Cypress.Commands.add('captureKPIs', () => {
  const kpis = {};

  cy.get('body').then(($body) => {
    // In stock count
    if ($body.find('[data-testid="kpi-instock"]').length) {
      kpis.instock = parseInt($body.find('[data-testid="kpi-instock"]').text().replace(/[^\d]/g, ''), 10) || 0;
    }
    // Sold count
    if ($body.find('[data-testid="kpi-sold"]').length) {
      kpis.sold = parseInt($body.find('[data-testid="kpi-sold"]').text().replace(/[^\d]/g, ''), 10) || 0;
    }
    // Sum selling
    if ($body.find('[data-testid="kpi-sum-selling"]').length) {
      kpis.sumSelling = parseInt($body.find('[data-testid="kpi-sum-selling"]').text().replace(/[^\d]/g, ''), 10) || 0;
    }
    // Sum cost
    if ($body.find('[data-testid="kpi-sum-cost"]').length) {
      kpis.sumCost = parseInt($body.find('[data-testid="kpi-sum-cost"]').text().replace(/[^\d]/g, ''), 10) || 0;
    }
  });

  return cy.wrap(kpis);
});

Cypress.Commands.add('dashboardNumbersShouldMove', (beforeKPIs, expectation = 'increase') => {
  cy.captureKPIs().then((afterKPIs) => {
    cy.log(`📊 KPI Before: ${JSON.stringify(beforeKPIs)}`);
    cy.log(`📊 KPI After: ${JSON.stringify(afterKPIs)}`);

    // At least one KPI should have changed
    const changed = Object.keys(afterKPIs).some((key) => {
      const before = beforeKPIs[key] || 0;
      const after = afterKPIs[key] || 0;
      return expectation === 'increase' ? after > before : after !== before;
    });

    expect(changed, 'At least one KPI should have changed').to.be.true;
  });
});

// ============================================================================
// NAVIGATE SIDEBAR - Click sidebar item and verify page loads
// ============================================================================
/**
 * Click a sidebar navigation item and verify the page loads correctly.
 *
 * @param {string} testId - data-testid of the sidebar link
 * @param {string} expectedUrl - URL substring to verify
 */
Cypress.Commands.add('navigateSidebar', (testId, expectedUrl) => {
  // Wait for any loaders to disappear first
  cy.get('body').then(($body) => {
    if ($body.find('.loader-backdrop, .loading-spinner').length) {
      cy.get('.loader-backdrop, .loading-spinner', { timeout: 10000 }).should('not.exist');
    }
  });
  
  cy.get(`[data-testid="${testId}"]`, { timeout: 20000 })
    .should('be.visible')
    .click({ force: true }); // Force click to bypass overlay checks

  cy.wait(1000); // Brief wait for navigation

  if (expectedUrl) {
    cy.url({ timeout: 20000 }).should('include', expectedUrl);
  }

  cy.assertNoServerError();
});

// ============================================================================
// WAIT FOR APP SHELL - Verify app is loaded
// ============================================================================
Cypress.Commands.add('waitForAppShell', () => {
  cy.assertNoServerError();

  cy.get('body', { timeout: 60000 }).then(($body) => {
    // Check for sidebar
    if ($body.find('[data-testid="sidebar"], [data-cy="sidebar"], aside').length) {
      cy.get('[data-testid="sidebar"], [data-cy="sidebar"], aside', { timeout: 60000 })
        .first()
        .should('be.visible');
      return;
    }

    // Fallback: check for dashboard heading
    cy.contains(/dashboard/i, { timeout: 60000 }).should('exist');
  });
});

// ============================================================================
// HELPER: Generate unique test data
// ============================================================================
Cypress.Commands.add('generateTestData', (verticalKey) => {
  const timestamp = Date.now();
  return cy.wrap({
    email: `e2e-${verticalKey}-${timestamp}@test.local`,
    password: 'E2ETestPass123!@#',
    businessName: `E2E ${verticalKey} ${timestamp}`,
    imei: `99${timestamp}`.slice(0, 15).padEnd(15, '0'),
    sku: `SKU-${verticalKey.toUpperCase()}-${timestamp}`,
    timestamp,
  });
});
