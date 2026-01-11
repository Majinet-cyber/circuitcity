# Phones Full Journey - Cypress E2E Test Plan

## Step 0 Audit: What Exists

### Config Review (`cypress.config.js`)
- **baseUrl**: `http://127.0.0.1:8000`
- **defaultCommandTimeout**: `20000` (20s) ✅ Already good
- **requestTimeout**: `20000` ✅ Good
- **responseTimeout**: `40000` ✅ Good  
- **pageLoadTimeout**: `90000` (90s) ✅ Excellent
- **Retries**: Not configured → will add `{ runMode: 1, openMode: 0 }`
- **Video**: disabled ✅
- **Screenshots on failure**: enabled ✅

### Existing Commands (`cypress/support/commands.js`)
| Command | Purpose | Reusable? |
|---------|---------|-----------|
| `loginAsManager(kind)` | Session-cached login via test API | ✅ Yes |
| `testLogin(email, pass)` | Direct API login (bypasses 2FA) | ✅ Yes |
| `loginAsOwner()` | Login using env TEST_EMAIL/TEST_PASSWORD | ✅ Yes |
| `assertNoServerError()` | Checks for 500/Traceback text | ✅ Yes - will extend |
| `waitForAppShell()` | Waits for sidebar/dashboard visible | ✅ Yes |
| `visitDashboard(kind)` | Visits vertical dashboard | ✅ Yes |
| `sidebarHrefs()` | Collects sidebar links as array | ✅ Yes |
| `fillField(labelOrCy, value)` | Fills by data-cy or label | ✅ Yes |
| `clickButton(textOrCy)` | Clicks by data-cy or button text | ✅ Yes |
| `createBusinessAndLocation(opts)` | Full signup wizard flow | ✅ Yes |
| `getAgentCreds/setAgentCreds` | Agent credential storage | N/A for this test |

### Existing Fixtures (`cypress/fixtures/`)
- `users.json`: Manager credentials per vertical (phones → `empire@gmai.com`)
- `products.json`: Sample product data (brand, model, prices)

### Existing Specs Related to Phones
| Spec | Location | Status |
|------|----------|--------|
| `phones_journey.cy.js` | `/cypress/e2e/verticals/` | Active but incomplete |
| `phones_full_journey.cy.js` | `/cypress/e2e/_legacy/` | Legacy, broken |
| `phones_scan_in_flow.cy.js` | `/cypress/e2e/_legacy/` | Legacy, has patterns to reuse |
| `phones_dashboard_wallet.cy.js` | `/cypress/e2e/_legacy/` | Legacy |
| `phone_manager_flow.cy.js` | `/cypress/e2e/_legacy/` | Legacy |
| `phone_reports_flow.cy.js` | `/cypress/e2e/_legacy/` | Legacy |

### Sidebar Selectors Available (`templates/includes/_sidebar_vertical.html`)
Phones section has these `data-cy` attributes:
- `data-cy="sidebar"` - main sidebar container
- `data-cy="nav-dashboard"` - Dashboard link
- `data-cy="nav-stock"` - Stock list
- `data-cy="nav-scan-in"` - Scan IN
- `data-cy="nav-scan-sell"` - Sell
- `data-cy="nav-sales"` - Sales history
- `data-cy="nav-reports"` - Reports
- `data-cy="nav-settings"` - Settings
- `data-cy="nav-team-agents"` - Agents (managers only)
- `data-cy="nav-team-locations"` - Locations (managers only)

### Template Selectors Status

| Page | Existing Selectors | Needed |
|------|-------------------|--------|
| **Scan IN** (`scan_in.html`) | `#id_imei`, `#id_product`, `#id_location`, `#id_order_price`, `#submitBtn` | Add: `data-testid="imei-input"`, `data-testid="scan-in-submit"` |
| **Scan Sold** (`scan_sold.html`) | `#id_imei`, `#id_price`, `#id_location`, `#submitBtn` | Add: `data-testid="sell-imei-input"`, `data-testid="sell-submit"` |
| **Signup Step 1** | Input names: `email`, `full_name`, `password1`, `password2` | Add: `data-testid="signup-*"` |
| **Signup Step 2** | `business_name`, `business_kind` | Add: `data-testid` for submit |
| **Dashboard** | Various KPI cards (no consistent selectors) | Add: `data-testid="kpi-*"` |

### API Endpoints Used
- `/accounts/__e2e__/test-login/` - Test login (bypasses 2FA)
- `/__whoami__/` - Session validation
- `/inventory/api/stock-models/` - Get products list
- `/inventory/api/stock-status/` - Check IMEI status
- `/inventory/api/mark-sold/` - Mark item as sold (POST)

---

## What Will Be Reused

1. **`cy.loginAsManager("phones")`** - Session-cached manager login
2. **`cy.assertNoServerError()`** - Will extend for more error patterns
3. **`cy.waitForAppShell()`** - Wait for sidebar/dashboard
4. **`cy.visitDashboard("phones")`** - Navigate to phones dashboard
5. **`cy.sidebarHrefs()`** - Collect sidebar links for navigation audit
6. **Fixtures** - `users.json` and `products.json`

## What Will Be Created

### New Commands (in `commands.js`)
1. **`cy.assertNoServerErrorPage()`** - Extended error detection
2. **`cy.safeClick(testid, options)`** - Visibility-checked click with timeout
3. **`cy.waitForAppIdle()`** - Wait for loader/spinner to disappear
4. **`cy.navAndAssert(testid, expectedUrl, interceptPattern?)`** - Navigate + verify no errors

### New Selectors (minimal additions)
- `data-testid="signup-email"`, `signup-password"`, etc.
- `data-testid="imei-input"` (scan-in)
- `data-testid="sell-imei-input"` (scan-sold)
- `data-testid="scan-in-submit"`, `sell-submit"`
- `data-testid="kpi-stock-count"`, `kpi-sales-today"`

### New Specs
1. **`phones_manager_full_journey.cy.js`** - Complete 10-stock + 10-sales journey
2. **`phones_manager_smoke.cy.js`** - Fast 1-stock + 1-sale smoke test

---

## Test Data Strategy

All test data uses timestamp-based uniqueness:

```javascript
const ts = Date.now();
const testData = {
  email: `manager+phones_${ts}@test.local`,
  password: 'TestPass123!',
  businessName: `TestPhones_${ts}`,
  // IMEIs: exactly 15 digits, unique per run
  imeis: Array.from({length: 10}, (_, i) => 
    `${ts}`.slice(-10).padStart(10, '0') + String(i).padStart(5, '0')
  ),
  // Products
  models: [
    { name: `Samsung A14 ${ts}`, price: 100000, cost: 80000 },
    { name: `iPhone 13 ${ts}`, price: 150000, cost: 120000 }
  ]
};
```

---

## Network Resilience Strategy

1. **No `cy.wait(ms)` for random delays** - Use explicit waits only
2. **Intercept + alias** for key requests:
   - Signup POST
   - Scan-in POST  
   - Mark-sold POST
3. **15s timeout** on `cy.wait('@alias', { timeout: 15000 })`
4. **Loader checks** via `cy.waitForAppIdle()`
5. **Element readiness** via `{ timeout: 15000 }` on `cy.get()`

---

## Environment Assumptions

- **baseUrl**: `http://127.0.0.1:8000`
- **Test login endpoint**: Available (not production)
- **OTP**: Bypassed via test login endpoint
- **Django DEBUG**: True (for error page detection)
- **Database**: Fresh or seeded with manager accounts

