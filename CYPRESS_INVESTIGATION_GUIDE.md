# Cypress Phones Tests - Investigation Guide

## Status: Ready for Investigation

Part A (Data Isolation) is **COMPLETE** ✅  
Part B (Cypress Tests) is **READY TO START**

---

## Quick Start

### 1. Start Development Server
```bash
python manage.py runserver 8000
```

**Wait for**: `Starting development server at http://127.0.0.1:8000/`

### 2. Run Cypress Tests (Choose One Approach)

#### Option A: Run All Phones Tests (Slowest)
```bash
npx cypress run --spec "cypress/e2e/*phone*.cy.js" --browser electron
```

#### Option B: Run Individual Tests (Recommended)
Start with the quickest/most critical tests:

```bash
# Quickest - Scan in flow
npx cypress run --spec "cypress/e2e/phones_scan_in_flow.cy.js" --browser electron

# Dashboard & wallet
npx cypress run --spec "cypress/e2e/phones_dashboard_wallet.cy.js" --browser electron

# Full user journey (slowest)
npx cypress run --spec "cypress/e2e/phones_full_journey.cy.js" --browser electron
```

#### Option C: Interactive Mode (Best for Debugging)
```bash
npx cypress open
# Then click on individual phones tests
```

---

## Test Files Overview

| File | Purpose | Est. Time |
|------|---------|-----------|
| `phones_scan_in_flow.cy.js` | Stock-in workflow | ~2 min |
| `phones_dashboard_wallet.cy.js` | Dashboard KPIs & wallet | ~3 min |
| `phone_manager_flow.cy.js` | Manager features | ~4 min |
| `phone_reports_flow.cy.js` | Reports/analytics | ~4 min |
| `phones_agent_invite_flow.cy.js` | Agent invitation | ~5 min |
| `phones_full_journey.cy.js` | End-to-end journey | ~8 min |

---

## Common Failure Patterns

### Backend Issues

#### 1. 500 Server Errors
**Symptoms**: Test fails with "Internal Server Error"  
**Check**:
- Django console for stack trace
- Look for missing business scope in queries
- Check for missing foreign keys

**Fix Pattern**:
```python
# Add business filter to queries
items = InventoryItem.objects.filter(business=request.business, ...)
```

#### 2. Redirect Loops
**Symptoms**: Test times out or shows wrong page  
**Check**:
- Missing `@require_business` decorator
- Incorrect URL reverse names
- Middleware conflicts

**Fix**: Add `@require_business` decorator to views

#### 3. Missing Data
**Symptoms**: Test expects data but finds none  
**Check**:
- Fixture setup in Cypress
- Database seeding  
- Business context in requests

### Frontend Issues

#### 1. Missing/Wrong Selectors
**Symptoms**: `cy.get('[data-cy="..."]')` fails  
**Check**:
- Template has `data-cy` attributes
- Selector matches current template structure

**Fix**: Add stable `data-cy` attributes:
```html
<button data-cy="scan-phone-submit" class="btn">Scan</button>
```

#### 2. Race Conditions
**Symptoms**: Flaky tests, sometimes pass/fail  
**Check**:
- AJAX calls completing before assertions
- Page redirects finishing  
- DOM elements rendering

**Fix**: Use proper waits:
```javascript
// BAD: Arbitrary wait
cy.wait(1000)

// GOOD: Wait for specific state
cy.get('[data-cy="success-message"]').should('be.visible')
cy.location('pathname').should('eq', '/expected/path/')
```

#### 3. Validation Mismatches
**Symptoms**: Form submission fails unexpectedly  
**Check**:
- Backend validation rules changed
- Required fields added
- Field format changed (IMEI, phone number)

**Fix**: Update Cypress fixtures or backend validation

---

## Investigation Workflow

### Step 1: Identify Failure
Run a single test and capture full output:
```bash
npx cypress run --spec "cypress/e2e/phones_scan_in_flow.cy.js" --browser electron > cypress_output.txt 2>&1
```

Look for:
- ❌ HTTP 500 errors → Backend issue
- ❌ Element not found → Selector issue  
- ❌ Timeout waiting → Race condition
- ❌ Assertion failed → Logic/validation issue

### Step 2: Diagnose Root Cause

#### For Backend Issues:
1. Check Django console output
2. Look for query errors, missing scoping
3. Check URL routing (`reverse()` calls)
4. Verify business context in requests

#### For Frontend Issues:
1. Check template file for selector
2. Verify element exists in current UI
3. Check if AJAX is completing  
4. Verify page redirects correctly

### Step 3: Fix Safely

**Principles**:
- ✅ Keep changes minimal
- ✅ Maintain business scoping (don't regress Part A fix!)
- ✅ Add `data-cy` selectors (preferred over class/ID selectors)
- ✅ Don't break other verticals

**Anti-Patterns to Avoid**:
- ❌ Don't use `set_current_business_id()` context switching
- ❌ Don't remove business filters
- ❌ Don't use arbitrary `cy.wait(1000)` for timing issues
- ❌ Don't create brittle selectors (nth-child, complex CSS)

### Step 4: Add Regression Guard

**For Backend Fixes**:
Add Django unit test in appropriate file:
```python
# Example: If you fix phones scan-in business scoping
def test_phone_scan_in_isolated_to_business():
    business_a = create_business("A")
    business_b = create_business("B")
    
    # Scan phone into business A
    response = scan_phone(request_with_business_a, ...)
    
    # Verify it's NOT visible in business B
    phones_b = InventoryItem.objects.filter(business=business_b)
    assert phones_b.count() == 0
```

**For Selector Fixes**:
Document in commit message which selectors were added/updated.

---

## Debugging Tips

### Enable Cypress Debug Mode
```bash
DEBUG=cypress:* npx cypress run --spec "cypress/e2e/phones_scan_in_flow.cy.js"
```

### Check Django Logs in Real-Time
```bash
# Terminal 1: Run server with verbose logging
python manage.py runserver --verbosity 2

# Terminal 2: Run Cypress
npx cypress run --spec "..."
```

### Interactive Debugging
```bash
# Open Cypress GUI for step-by-step debugging
npx cypress open

# Click on failing test
# Use Chrome DevTools to inspect elements
# Check Network tab for AJAX failures
```

### Check Browser Console
In Cypress GUI:
1. Click test to run
2. Open Chrome DevTools (F12)  
3. Check Console tab for JavaScript errors
4. Check Network tab for failed requests

---

## Expected Fixes Needed (Based on Common Patterns)

### Likely Issue 1: Missing `data-cy` Selectors
**Files to check**:
- `templates/inventory/scan_in.html`
- `templates/inventory/scan_sold.html`
- `templates/inventory/dashboard.html`

**Fix**: Add stable selectors:
```html
<!-- BEFORE -->
<button class="btn btn-primary">Submit</button>

<!-- AFTER -->
<button class="btn btn-primary" data-cy="scan-submit-btn">Submit</button>
```

### Likely Issue 2: Business Context in Scan Views
**Files to check**:
- `inventory/views_scan.py`
- `inventory/views_phones.py`

**Fix**: Ensure all queries scoped:
```python
@login_required
@require_business
def scan_in(request):
    business = request.business
    # ✅ All queries must include business filter
    items = InventoryItem.objects.filter(business=business, ...)
```

### Likely Issue 3: Redirect After Scan
**Files to check**:
- `inventory/views_scan.py` (redirect URLs)

**Fix**: Use correct URL names:
```python
# Ensure redirect goes to correct vertical dashboard
return redirect('verticals:phones_dashboard')  # or similar
```

---

## Success Criteria

### For Part B to be Complete:
- ✅ At least 1 key phones Cypress test passes (e.g., `phones_scan_in_flow.cy.js`)
- ✅ Fixes don't break data isolation from Part A
- ✅ Fixes don't break other verticals (clothing, liquor, gym)
- ✅ Django unit test added for any backend fixes
- ✅ Summary document explaining root cause and fix

---

## Time Estimates

- **Backend investigation**: 15-30 min
- **Frontend/selector fixes**: 10-20 min  
- **Testing & verification**: 10-15 min
- **Writing regression tests**: 15-20 min

**Total**: 50-85 minutes for complete Part B

---

## Quick Reference Commands

```bash
# 1. Start server
python manage.py runserver 8000

# 2. (New terminal) Run quickest test
npx cypress run --spec "cypress/e2e/phones_scan_in_flow.cy.js" --browser electron

# 3. If it fails, run in GUI mode for debugging
npx cypress open

# 4. After fixes, verify no regressions
python -m pytest tests/test_dashboard_data_isolation.py -v

# 5. Verify broader test suite
python -m pytest tests/ -k "dashboard" -v
```

---

**Status**: Part A Complete ✅ | Part B Ready to Start 🚀


