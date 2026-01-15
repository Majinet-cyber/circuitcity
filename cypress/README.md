# CircuitCity / Emajinet - Cypress E2E Test Suite

**Clean Suite Reboot (Jan 2026)**

This is a systematic, vertical-aware E2E test suite designed for reliability on slow networks.

---

## 📁 Structure

```
cypress/
  e2e/
    journeys/          # Full user journeys (signup → stock-in → sale → verify KPIs)
      phones.journey.cy.js
      clothing.journey.cy.js
      liquor.journey.cy.js
      gym.journey.cy.js
      pharmacy.journey.cy.js
      grocery.journey.cy.js
      farm.journey.cy.js
      cement.journey.cy.js
      welding.journey.cy.js
      hardware.journey.cy.js

    smoke/             # Smoke tests (hit every sidebar button)
      phones.smoke.cy.js
      clothing.smoke.cy.js
      liquor.smoke.cy.js
      gym.smoke.cy.js
      pharmacy.smoke.cy.js
      grocery.smoke.cy.js
      farm.smoke.cy.js
      cement.smoke.cy.js
      welding.smoke.cy.js
      hardware.smoke.cy.js

  fixtures/
    verticals.json     # Single source of truth for vertical config
    users.json         # Test user credentials

  support/
    commands.js        # Custom Cypress commands
    e2e.js             # Global setup/teardown
```

---

## 🚀 Running Tests

### Prerequisites

1. Start the Django dev server (or point to staging):
   ```bash
   # Local development
   python manage.py runserver --settings=config.settings_e2e

   # Or set staging URL
   set CYPRESS_BASE_URL=https://staging.circuitcity.com
   ```

2. Ensure E2E mode is enabled in Django settings (`settings_e2e.py`):
   - OTP bypass enabled (code `000000` works)
   - Test login endpoint available at `/accounts/__e2e__/test-login/`

### NPM Scripts

```bash
# Open Cypress interactive runner
npm run cypress:open

# Run all tests headlessly
npm run cypress:run

# Run only smoke tests (quick, ~2 min)
npm run e2e:smoke

# Run only journey tests (full flows, ~10 min)
npm run e2e:journeys

# Run all E2E tests
npm run e2e:all

# Run tests for a specific vertical
npm run e2e:phones
npm run e2e:clothing
npm run e2e:liquor
npm run e2e:gym
npm run e2e:pharmacy
npm run e2e:grocery
npm run e2e:farm
npm run e2e:cement
npm run e2e:welding
npm run e2e:hardware
```

### Environment Variables

| Variable            | Default                  | Description                          |
|---------------------|--------------------------|--------------------------------------|
| `CYPRESS_BASE_URL`  | `http://127.0.0.1:8000`  | App base URL                         |
| `STEP_WAIT_MS`      | `12000`                  | Wait time after major steps (ms)     |

**Slow network mode (extra wait time):**

```bash
# PowerShell
$env:STEP_WAIT_MS=15000; npm run e2e:smoke

# CMD
set STEP_WAIT_MS=15000 && npm run e2e:smoke

# Bash
STEP_WAIT_MS=15000 npm run e2e:smoke
```

**Running against staging:**

```bash
# PowerShell
$env:CYPRESS_BASE_URL="https://staging.circuitcity.com"; npm run e2e:smoke

# CMD
set CYPRESS_BASE_URL=https://staging.circuitcity.com && npm run e2e:smoke

# Bash
CYPRESS_BASE_URL=https://staging.circuitcity.com npm run e2e:smoke
```

---

## 🧪 Test Types

### Journey Tests (`e2e/journeys/`)

Full user journey from signup to verified KPI changes:

1. **Signup** - Manager creates account and business
2. **Dashboard** - Verify dashboard loads correctly
3. **Stock In** - Add inventory item (vertical-specific)
4. **Verify KPIs** - Check dashboard numbers updated
5. **Make Sale** - Complete a sale
6. **Verify KPIs** - Check dashboard numbers updated again

Each step includes a 12-second wait for slow networks plus readiness assertions.

### Smoke Tests (`e2e/smoke/`)

Hit every sidebar button to ensure no 500 errors:

1. **Login** - Use pre-configured manager credentials
2. **Navigate** - Click each sidebar item
3. **Assert** - Verify page loads, URL correct, no server errors
4. **Return** - Go back to dashboard

---

## 🎯 Best Practices

### 1. Use `data-testid` Selectors

All tests use `data-testid` attributes, not CSS classes or text:

```javascript
// ✅ Good
cy.get('[data-testid="sidebar-dashboard"]').click();

// ❌ Bad (brittle)
cy.get('.nav-item.active').click();
cy.contains('Dashboard').click();
```

### 2. Wait + Assert (Not Just Wait)

Every major step has both a wait AND a readiness assertion:

```javascript
// ✅ Good
cy.stepWait('Dashboard loaded');
cy.assertPageReady('dashboard-heading', { urlContains: '/inventory' });

// ❌ Bad (only waiting)
cy.wait(12000);
```

### 3. Read from Fixtures

All vertical-specific config comes from `fixtures/verticals.json`:

```javascript
cy.fixture('verticals').then((verticals) => {
  const vertical = verticals['phones'];
  cy.visit(vertical.dashboardPath);
});
```

### 4. Use Custom Commands

The suite provides reusable commands:

- `cy.stepWait(label)` - Wait STEP_WAIT_MS with logging
- `cy.assertPageReady(testid, options)` - Verify page is ready
- `cy.assertNoServerError()` - Check for 500 errors
- `cy.signupManagerAndCreateBusiness(vertical)` - Full signup flow
- `cy.loginAsManager(vertical)` - Login with existing credentials
- `cy.stockInForVertical(vertical)` - Stock in with vertical-specific fields
- `cy.makeSaleForVertical(vertical)` - Complete a sale
- `cy.captureKPIs()` - Capture dashboard KPI values
- `cy.dashboardNumbersShouldMove(before)` - Assert KPIs changed

---

## 🏷️ Required `data-testid` Attributes

For tests to work, these `data-testid` attributes must exist in templates:

### Dashboard
- `dashboard-heading` - Main heading or page identifier
- `kpi-instock` - In stock count card
- `kpi-sold` - Sold count card
- `kpi-sum-selling` - Sum selling value card

### Sidebar
- `sidebar-dashboard`
- `sidebar-analytics`
- `sidebar-stock`
- `sidebar-scan-in`
- `sidebar-sell`
- `sidebar-sales-history`
- `sidebar-agents`
- `sidebar-reports`
- (plus vertical-specific: `sidebar-members`, `sidebar-checkin`, etc.)

### Forms
- `stockin-form` - Stock in form container
- `stockin-submit` - Submit button
- `stockin-imei` - IMEI input (phones)
- `stockin-sku` - SKU input (others)
- `stockin-name` - Item name input
- `stockin-price` - Selling price input
- `stockin-cost` - Cost price input
- `stockin-qty` - Quantity input

- `sell-form` - Sell form container
- `sell-search-item` - Search input
- `sell-add-to-cart` - Add to cart button
- `sell-checkout` - Checkout button
- `sell-submit` - Submit sale button

### Auth
- `signup-full-name`
- `signup-email`
- `signup-password`
- `signup-password-confirm`
- `signup-continue`
- `business-name`
- `business-kind-{vertical}` - e.g., `business-kind-phones`
- `business-continue`
- `login-email`
- `login-password`
- `login-submit`

---

## 🔧 Troubleshooting

### Tests failing on slow network

Increase the step wait time:

```bash
STEP_WAIT_MS=20000 npm run e2e:journeys
```

### "No manager credentials" error

Add credentials to `fixtures/users.json` for the vertical.

### Selector not found

Check that the required `data-testid` exists in the template.

### Server error detected

The test found a 500 error on the page. Check Django logs.

---

## 📊 Configuration

See `cypress.config.js` for all settings:

- `defaultCommandTimeout`: 20s
- `pageLoadTimeout`: 120s
- `requestTimeout`: 20s
- `responseTimeout`: 60s
- `retries.runMode`: 2 (retries in CI)
- `viewportWidth`: 375 (mobile-first)
- `viewportHeight`: 812

---

## 🔐 E2E Mode (Django)

For tests to work, Django must be running with E2E settings:

```python
# settings_e2e.py
E2E_MODE = True
E2E_OTP_BYPASS = '000000'  # OTP that always works in E2E mode
```

And these test-only endpoints should be available:
- `POST /accounts/__e2e__/test-login/` - Login without 2FA
- `GET /accounts/__e2e__/latest-otp/?email=...` - Get OTP for email (optional)

