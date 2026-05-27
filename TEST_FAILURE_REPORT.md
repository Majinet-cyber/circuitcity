# TEST FAILURE REPORT
**Branch:** `fix/cypress-pharmacy`  
**Date:** January 6, 2026  
**Working Tree:** DIRTY (staged changes + 1 unstaged file)

---

## 1. EXECUTIVE SUMMARY

### Test Suite Results

| Suite | Total | Passed | Failed | Errors | Skipped | Duration |
|-------|-------|--------|--------|--------|---------|----------|
| **Django manage.py test** | N/A | N/A | N/A | Collection Error | - | - |
| **pytest** | 2,321 | 1,338 | 815 | 156 | 17 | 21m 44s |
| **TOTAL** | **2,321** | **1,338** | **815** | **156** | **17** | **21m 44s** |

### Suite Status
- ❌ **Django manage.py test**: FAILED TO RUN - ImportError during test discovery (billing/tests.py vs billing/tests/ conflict)
- ⚠️ **pytest**: 35.1% failure rate (815 failed + 156 errors out of 2,321 tests)

### Critical Issues Preventing Test Runs
1. **Django test runner cannot collect tests** - `billing/tests.py` file conflicts with Python's expectation of a package structure
2. **3 test files fail to import** before any tests run:
   - `inventory/tests/test_gym_analytics_kpis.py`
   - `inventory/tests/test_gym_email_tasks.py`
   - `tests/test_payslip_notifications.py`

---

## 2. FAILURE TABLE

| # | Suite | Test File/Module | Error Type | Root Cause | Scope | Regression Risk |
|---|-------|------------------|------------|------------|-------|----------------|
| 1 | pytest | 800+ tests across all verticals | `TypeError` | Tests use `Business(kind=...)` but model field is `business_kind` | **DB Schema/Model** | 🔴 **HIGH** |
| 2 | pytest | 36+ tests (wallet, clothing, cement, etc.) | `TypeError` | Tests use `Business(currency=...)` but field doesn't exist in model | **DB Schema/Model** | 🔴 **HIGH** |
| 3 | pytest | inventory/services/fast_sell.py | `FieldError` | Code queries `Location.objects.filter(is_active=True)` but Location has no `is_active` field (only `is_default`) | **Business Logic/Query** | 🔴 **HIGH** |
| 4 | pytest | inventory/tests/test_gym_analytics_kpis.py | `ImportError` | `from circuitcity.accounts.models import User` - should use Django's `get_user_model()` | **Import/Auth** | 🟡 **MED** |
| 5 | pytest | inventory/tests/test_gym_email_tasks.py | `ImportError` | `from circuitcity.accounts.models import User` - should use Django's `get_user_model()` | **Import/Auth** | 🟡 **MED** |
| 6 | pytest | tests/test_payslip_notifications.py | `ModuleNotFoundError` | `from freezegun import freeze_time` - freezegun not installed | **Dependencies** | 🟢 **LOW** |
| 7 | pytest | Multiple vertical tests | `ERROR` | Tests create `business_kind='hardware'` and `'cement'` but not in BusinessKind registry | **Vertical Registry** | 🟡 **MED** |
| 8 | Django | billing/tests.py | `ImportError` | Test discovery fails: `billing/tests` incorrectly imported as module instead of package | **Test Structure** | 🟡 **MED** |
| 9 | pytest | 150+ E2E/smoke/integration tests | `ERROR` | Playwright/browser fixtures failing (likely config/dependency issue) | **E2E Infrastructure** | 🟢 **LOW** |
| 10 | pytest | /tenants/choose/ endpoint (6 occurrences) | `500 Internal Server Error` | Unhandled exception in tenant selection flow | **Middleware/Auth** | 🟡 **MED** |
| 11 | pytest | /hq/stock-trends/, /hq/invoices/create/ | `500 Internal Server Error` | HQ endpoints crashing | **HQ Module** | 🟡 **MED** |
| 12 | pytest | /inventory/api/scan-in/ | `500 Internal Server Error` | Scan-in API endpoint failing | **Inventory API** | 🟡 **MED** |
| 13 | pytest | /gym/qr/.../print/ | `500 Internal Server Error` | Gym QR code print functionality broken | **Gym Vertical** | 🟢 **LOW** |
| 14 | pytest | /dashboard/api/profit-data/ | `500 Internal Server Error` | Dashboard profit API endpoint failing | **Dashboard/Analytics** | 🟡 **MED** |

---

## 3. GROUPED ROOT CAUSES

### 🔴 **CRITICAL - Model/Schema Mismatches (Blocks ~70% of failures)**

#### A) Business Model Field Name Mismatch
**Count:** ~800+ test failures  
**Cause:** Tests create Business objects with `kind=` parameter, but the actual model field is `business_kind=`  
**Example:**
```python
# ❌ Tests currently do this:
Business.objects.create(name="Test Business", kind="clothing")

# ✅ Should be:
Business.objects.create(name="Test Business", business_kind="clothing")
```
**Files affected:** Virtually all tests that create Business instances across:
- `inventory/tests/test_clothing_barcode_service.py:37`
- `tests/test_*.py` (100+ files)
- `inventory/tests/test_*.py` (50+ files)
- `tenants/tests/test_*.py` (20+ files)

**Model location:** `tenants/models.py:97-104` - Field is `business_kind`, not `kind`

---

#### B) Business Model Missing `currency` Field
**Count:** ~36+ test failures  
**Cause:** Tests try to create Business objects with `currency=` parameter, but this field doesn't exist in the Business model  
**Example:**
```python
# ❌ Tests currently do this:
Business.objects.create(name="Shop", currency="MWK")

# ✅ Currency field doesn't exist - needs to be added or removed from tests
```
**Files affected:**
- `tests/test_wallet_costs.py`
- `tests/test_clothing_*.py`
- `tests/test_cement_*.py`
- `tests/test_well_known_currency.py`

**Investigation needed:** Determine if currency was removed in a recent refactor, or if tests are from a feature branch that was never merged.

---

#### C) Location Model Field Name Mismatch
**Count:** Multiple runtime errors in fast_sell service  
**Cause:** Code queries `Location.objects.filter(is_active=True)` but Location model has no `is_active` field (it has `is_default`)  
**Error message:**
```
Cannot resolve keyword 'is_active' into field. Choices are: accessory_stock_logs, accessory_stocks, [...], is_default, [...]
```
**Source file:** `inventory/services/fast_sell.py:318`  
**Model location:** `inventory/models.py:125-173` - Has `is_default` (line 149), NOT `is_active`

**Impact:** Fast-sell functionality crashes at runtime for accessories/clothing/pharmacy

---

### 🟡 **HIGH PRIORITY - Import & Dependency Issues**

#### D) Incorrect User Model Import
**Count:** 3 test files fail to import  
**Cause:** Using direct import instead of Django's `get_user_model()`  
**Files:**
- `inventory/tests/test_gym_analytics_kpis.py:11`
- `inventory/tests/test_gym_email_tasks.py:13`

**Fix pattern:**
```python
# ❌ Wrong:
from circuitcity.accounts.models import User

# ✅ Correct:
from django.contrib.auth import get_user_model
User = get_user_model()
```

---

#### E) Missing Test Dependency
**Count:** 1 test file fails to import  
**Cause:** `freezegun` package not installed  
**File:** `tests/test_payslip_notifications.py:9`  
**Fix:** Add `freezegun` to `requirements.txt` or `requirements-dev.txt`

---

#### F) Unregistered Business Kinds
**Count:** Multiple test failures creating hardware/cement businesses  
**Cause:** Tests create businesses with `business_kind='hardware'` and `'cement'` but these are not in the `BusinessKind` enum  
**Error logs:**
```
ERROR inventory.verticals.fallback:fallback.py:69 Unrecognized business_kind 'hardware' for business Hardware Store
ERROR inventory.verticals.fallback:fallback.py:69 Unrecognized business_kind 'cement' for business Cement Store
```

**Current BusinessKind enum** (`tenants/constants.py` or `inventory/business_kinds.py`):
- phones
- liquor
- grocery
- pharmacy
- clothing
- gym

**Missing:** hardware, cement

**Decision needed:** Add these to the enum, or update tests to use existing verticals?

---

### 🟡 **MEDIUM PRIORITY - Test Infrastructure**

#### G) Django Test Runner Import Error
**Cause:** `billing/tests.py` file exists alongside tests expecting `billing/tests/` to be a package  
**Error:**
```
ImportError: 'tests' module incorrectly imported from 'C:\...\billing\tests'. Expected 'C:\...\billing'.
Is this module globally installed?
```
**Impact:** Cannot run `python manage.py test` at all

**Fix options:**
1. Rename `billing/tests.py` → `billing/test_billing.py`
2. Convert to package: `billing/tests/__init__.py` + move content into separate files
3. Move all tests to top-level `tests/` directory

---

#### H) E2E/Smoke Test Infrastructure Failures
**Count:** 156 ERRORs (not failures, but errors during setup/teardown)  
**Cause:** Playwright browser tests failing to initialize properly  
**Files affected:**
- `tests/e2e/test_sidebar_clicks_*.py` (12 errors)
- `tests/smoke/test_core_workflows.py` (15 errors)
- `tests/smoke/test_sidebar_routes_*.py` (21 errors)
- Integration tests using browser fixtures (100+ errors)

**Likely causes:**
- Playwright not installed/configured properly
- Browser fixtures not properly scoped
- Missing browser binaries

**Note:** These are infrastructure issues, not functional test failures. Can be addressed separately.

---

### 🟢 **LOW PRIORITY - Endpoint Failures (Functional Bugs)**

#### I) Internal Server Errors (500s)
**Count:** ~30 logged errors across multiple endpoints  
**Endpoints failing:**
- `/tenants/choose/` (6 occurrences) - Tenant selection
- `/hq/stock-trends/` (3 occurrences) - HQ analytics
- `/hq/invoices/create/` (1 occurrence) - HQ invoicing
- `/inventory/api/scan-in/` (3 occurrences) - Scan-in API
- `/gym/qr/.../print/` (1 occurrence) - Gym QR printing
- `/dashboard/api/profit-data/` (1 occurrence) - Profit analytics

**Cause:** Likely cascading from the model field mismatches above (tests set up bad data → endpoints crash)

**Recommendation:** Re-test these after fixing critical model issues. Many may self-resolve.

---

## 4. IMPACT ASSESSMENT

### By Category

| Category | Failures | Impact | Can Fix Without Code Changes? |
|----------|----------|--------|-------------------------------|
| **Model field mismatches** | ~836 | Blocks majority of test suite | ❌ No - requires test updates |
| **Import errors** | 3 | Blocks specific test files | ❌ No - requires import fixes |
| **Missing dependency** | 1 | Blocks 1 test file | ❌ No - requires package install |
| **Vertical registry** | ~10 | Blocks hardware/cement tests | ⚠️ Maybe - config or test change |
| **Test structure** | 1 suite | Blocks Django test runner | ❌ No - requires file restructure |
| **E2E infrastructure** | 156 | Blocks browser tests | ⚠️ Maybe - tooling setup |
| **Endpoint crashes** | ~30 | Functional bugs | ⚠️ Maybe - may resolve after fixes |

### Blast Radius by Module

| Module | Test Failures | Primary Cause |
|--------|---------------|---------------|
| **Phones vertical** | ~200 | Business.kind field mismatch |
| **Clothing vertical** | ~150 | Business.kind + currency fields |
| **Pharmacy vertical** | ~100 | Business.kind + Location.is_active |
| **Gym vertical** | ~80 | Business.kind + User import |
| **Liquor vertical** | ~80 | Business.kind field mismatch |
| **Cement vertical** | ~50 | Business.kind + unregistered vertical |
| **Hardware vertical** | ~30 | Unregistered vertical |
| **Wallet/Billing** | ~40 | Business.currency field |
| **HQ/Admin** | ~25 | Multiple (cascading from above) |
| **E2E/Smoke** | ~156 | Infrastructure setup |

---

## 5. RECOMMENDED FIX SEQUENCE

### Phase 1: Stop the Bleeding (Critical Blockers)
1. ✅ **Fix Business.kind → business_kind** (~800 tests)
   - Search/replace: `Business.objects.create(.*kind=` → `business_kind=`
   - Scope: All test files
   - Risk: Low (mechanical change)

2. ✅ **Decide on Business.currency field** (~36 tests)
   - **Option A:** Add `currency` field to Business model + migration
   - **Option B:** Remove currency from tests (use business-level settings instead)
   - Risk: Medium (data model decision)

3. ✅ **Fix Location.is_active → is_default** (multiple runtime errors)
   - Update `inventory/services/fast_sell.py:318`
   - Search codebase for other `is_active` on Location
   - Risk: Medium (logic change - verify semantics match)

### Phase 2: Restore Test Infrastructure
4. ✅ **Fix billing/tests.py import issue**
   - Rename or restructure billing tests
   - Risk: Low (file structure)

5. ✅ **Fix User import errors**
   - Update 2 test files to use `get_user_model()`
   - Risk: Low (standard Django pattern)

6. ✅ **Install freezegun**
   - Add to requirements-dev.txt
   - Run `pip install freezegun`
   - Risk: Low (dependency add)

### Phase 3: Vertical Registry (Optional)
7. ⚠️ **Handle hardware/cement verticals**
   - **Option A:** Add to BusinessKind enum if feature exists
   - **Option B:** Update tests to use existing verticals
   - Risk: Low-Medium (depends on product roadmap)

### Phase 4: E2E Infrastructure (Defer)
8. ⚠️ **Fix Playwright/E2E tests** (156 errors)
   - Install Playwright properly: `playwright install`
   - Fix fixture scoping issues
   - Risk: Low (tooling setup, doesn't block unit tests)

---

## 6. FILES REQUIRING CHANGES (Estimate)

### Test Files
- **~150 test files** in `tests/` directory (Business.kind fixes)
- **~50 test files** in `inventory/tests/` (Business.kind fixes)
- **~20 test files** in `tenants/tests/` (Business.kind fixes)
- **~30 test files** with Business.currency references
- **2 test files** with User import issues
- **1 test file** with freezegun import

### Source Files
- `inventory/services/fast_sell.py` (Location.is_active → is_default)
- Possibly more source files using Location.is_active (needs search)
- `billing/tests.py` (rename/restructure)

### Configuration
- `requirements.txt` or `requirements-dev.txt` (add freezegun)
- Possibly `tenants/constants.py` or `inventory/business_kinds.py` (add hardware/cement)

---

## 7. NOTES FOR BRAINSTORMING

### Questions to Answer Before Fixing
1. **Currency field:** Was this intentionally removed? Check git history for `Business.currency` removal
2. **Location.is_active:** Was this renamed to `is_default`? Check semantics - do they mean the same thing?
3. **hardware/cement verticals:** Are these planned features or test artifacts? Check product roadmap
4. **billing/tests.py:** Why does this file exist? Recent addition? Can it be safely moved?

### Potential Hidden Issues
- After fixing field names, **many endpoint 500 errors may disappear** (they're caused by bad test data setup)
- **E2E tests may have unrelated issues** - they weren't run successfully even before recent changes
- **Migration state:** If currency/is_active fields were recently removed, old migrations may conflict

### Git Investigation Recommended
```bash
# Check when Business.kind vs business_kind changed
git log -p --all -S "kind=" -- tenants/models.py

# Check if currency field was removed
git log -p --all -S "currency" -- tenants/models.py business/models.py

# Check when Location.is_active was changed
git log -p --all -S "is_active" -- inventory/models.py
```

---

## 8. PASTE INTO CHATGPT

```
TEST FAILURE ANALYSIS - CircuitCity Django/Pytest Suite
Branch: fix/cypress-pharmacy | Date: 2026-01-06

SUMMARY: 815 failed + 156 errors out of 2,321 tests (35% failure rate)

═══════════════════════════════════════════════════════════════════
TOP 3 CRITICAL BLOCKERS (Fix These First)
═══════════════════════════════════════════════════════════════════

1. ❌ Business.kind Parameter Mismatch (~800 failures)
   • Tests use: Business(kind="phones")
   • Model has: business_kind (not kind)
   • Impact: Blocks 70% of test suite across ALL verticals
   • Fix: Search/replace kind= → business_kind= in all test files

2. ❌ Business.currency Field Missing (~36 failures)
   • Tests use: Business(currency="MWK")
   • Model has: NO currency field
   • Impact: Wallet, clothing, cement test failures
   • Decision: Add field OR remove from tests?

3. ❌ Location.is_active Query Error (Runtime crashes)
   • Code queries: Location.objects.filter(is_active=True)
   • Model has: is_default (not is_active)
   • Impact: Fast-sell crashes for accessories/clothing/pharmacy
   • File: inventory/services/fast_sell.py:318

═══════════════════════════════════════════════════════════════════
OTHER BLOCKERS
═══════════════════════════════════════════════════════════════════

4. Import Errors (3 test files won't load)
   • inventory/tests/test_gym_analytics_kpis.py
   • inventory/tests/test_gym_email_tasks.py
   • Issue: from circuitcity.accounts.models import User
   • Fix: Use get_user_model() instead

5. Missing Dependency
   • tests/test_payslip_notifications.py
   • Missing: freezegun package
   • Fix: pip install freezegun

6. Unregistered Business Kinds
   • Tests create: business_kind='hardware' and 'cement'
   • Registry has: phones, liquor, grocery, pharmacy, clothing, gym
   • Fix: Add to enum OR update tests to use existing kinds

7. Django Test Runner Broken
   • billing/tests.py file conflicts with package structure
   • Impact: Cannot run python manage.py test
   • Fix: Rename/restructure billing/tests.py

8. E2E Infrastructure (156 errors)
   • Playwright browser tests failing to initialize
   • Lower priority - doesn't block unit tests

═══════════════════════════════════════════════════════════════════
BLAST RADIUS BY VERTICAL
═══════════════════════════════════════════════════════════════════

Phones:    ~200 failures (Business.kind)
Clothing:  ~150 failures (Business.kind + currency)
Pharmacy:  ~100 failures (Business.kind + Location.is_active)
Gym:       ~80 failures  (Business.kind + User import)
Liquor:    ~80 failures  (Business.kind)
Cement:    ~50 failures  (Business.kind + unregistered)
Hardware:  ~30 failures  (Unregistered vertical)
Wallet:    ~40 failures  (Business.currency)
E2E/Smoke: ~156 errors   (Infrastructure setup)

═══════════════════════════════════════════════════════════════════
QUESTIONS FOR MANUAL REVIEW
═══════════════════════════════════════════════════════════════════

1. Was Business.currency field recently removed? Check git history.
2. Was Location.is_active renamed to is_default? Check semantics.
3. Are hardware/cement official verticals or test artifacts?
4. Why does billing/tests.py exist as file (not package)?
5. Should E2E tests be fixed now or deferred?

═══════════════════════════════════════════════════════════════════
RECOMMENDED FIX ORDER
═══════════════════════════════════════════════════════════════════

Phase 1 (Critical - Must Fix):
  1. Business.kind → business_kind (800 tests) - MECHANICAL
  2. Decide on Business.currency strategy (36 tests) - NEEDS DECISION
  3. Location.is_active → is_default (source code) - VERIFY SEMANTICS

Phase 2 (Infrastructure):
  4. Fix billing/tests.py structure
  5. Fix User imports (2 files)
  6. Install freezegun

Phase 3 (Optional):
  7. Add hardware/cement to BusinessKind enum (if needed)
  8. Fix E2E/Playwright setup (defer if needed)

═══════════════════════════════════════════════════════════════════
KEY FILES TO INVESTIGATE
═══════════════════════════════════════════════════════════════════

Models:
  • tenants/models.py:97-104 (Business.business_kind definition)
  • inventory/models.py:125-173 (Location model - has is_default)

Source Code Issues:
  • inventory/services/fast_sell.py:318 (Location.is_active query)

Test Examples:
  • inventory/tests/test_clothing_barcode_service.py:37 (kind usage)

═══════════════════════════════════════════════════════════════════
```

---


