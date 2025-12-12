# Test Fixes Summary - All 17/17 Tests Passing

## Status: ✅ COMPLETE - All tests in `tests/test_wallet_phones_agent_fixes.py` now pass (17/17)

## Failing Tests Fixed

### 1. `test_fix4_ranking_works_in_wallet` ✅
**Problem:** API returned 0 agents instead of expected 2  
**Root Cause:** Test was creating Business objects with default `status="PENDING"`, but middleware only auto-selects ACTIVE businesses  
**Solution:** Added `status="ACTIVE"` when creating test businesses

### 2. `test_agent_wallet_view_calls_ensure_salary` ✅
**Problem:** Salary ensure function not being called / salary not created  
**Root Cause:** Same as above - Business with PENDING status wasn't being resolved by middleware, so wallet view received `business=None` and skipped salary creation  
**Solution:** Added `status="ACTIVE"` when creating test businesses

## Changes Made

### Test-Side Fixes (Primary)

#### 1. `tests/test_wallet_phones_agent_fixes.py`

**Session Helper Fix:**
- Changed `session["business_id"]` to `session["biz_id"]` in `set_active_business_session()`
- Reason: The `get_active_business()` utility looks for `"biz_id"` (legacy key), not `"business_id"`

**Business Status Fix:**
- Added `status="ACTIVE"` to both test class setUp methods:
  - `TestPhonesAgentWalletFixes.setUp()` - line ~53
  - `TestPhonesBaseSalary.setUp()` - line ~649
- Reason: Business model defaults to `status="PENDING"`, but middleware skips PENDING businesses

**Test Expectation Update:**
- Updated `test_fix5_payslip_updates_immediately` to expect base salary + commission
- Changed from expecting just commission (15000) to commission + base salary (65000)
- Reason: With ACTIVE business, the wallet view now correctly creates base salary for Phones agents

### Production-Side Fixes (Minimal)

#### 2. `cc/settings.py`

**ALLOWED_HOSTS for Testing:**
- Added `'testserver'` to `ALLOWED_HOSTS` when `TESTING=True`
- Reason: Django test client uses `'testserver'` as hostname; without this, all test requests fail with `DisallowedHost` error before reaching any middleware

## Root Cause Analysis

Both failing tests had the same underlying issue:

1. **Business Status:** Tests created businesses without setting `status="ACTIVE"`
2. **Defaults to PENDING:** Business model has `default="PENDING"` for the status field
3. **Middleware Filtering:** `TenantResolutionMiddleware` filters out non-ACTIVE businesses when auto-selecting based on membership
4. **Null Business Context:** Views received `business=None` from `get_active_business(request)`
5. **Skipped Logic:** 
   - Wallet view skips base salary creation when `business=None`
   - Ranking API returns empty list when `business=None`

## Why This Looked Like Production Bugs

The symptoms appeared to be production issues:
- "Salary function not being called" → Actually was being called with `(None, user)` 
- "API returns 0 agents" → Actually middleware couldn't resolve business context

But the real issue was **test data setup** - missing `status="ACTIVE"` on Business objects.

## Verification

### Target Test File
```bash
pytest tests/test_wallet_phones_agent_fixes.py -q
# Result: 17 passed, 20 warnings ✅
```

### Regression Check
```bash
pytest tests/test_tenants.py tests/test_agent_wallet.py tests/test_smoke.py -q
# Result: 16 passed, 1 skipped, 12 warnings ✅ (no regressions)
```

## No Production Behavior Changes

All fixes were test-side except for adding `'testserver'` to ALLOWED_HOSTS, which only affects testing and has no impact on production behavior.

✅ Phones vertical base salary feature works correctly  
✅ Ranking API works correctly  
✅ All business isolation tests pass  
✅ No cross-vertical impact (laptops, liquor, etc. unaffected)

