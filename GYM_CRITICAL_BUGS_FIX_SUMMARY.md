# GYM VERTICAL CRITICAL BUGS - FIX SUMMARY

## Problem A: Dashboard Numbers Stuck at Zero ✅ FIXED

### Root Cause
The gym dashboard view (`inventory/verticals/gym.py`) was calculating financial metrics incorrectly:
- **Revenue**: Correctly used the selected date filter (Today/Last 7 Days/MTD)
- **Costs**: Hardcoded to use MTD only, IGNORING the selected filter
- **Profit**: Used MTD costs regardless of filter, causing mismatch

When a user selected "Today" filter:
- Revenue showed today's payments ✅
- Costs showed MTD costs (wrong!) ❌
- Profit = Today's revenue - MTD costs (incorrect!) ❌

### Fix Applied
**File**: `inventory/verticals/gym.py` (lines 124-178)

Added calculation of costs for the selected filter range:
```python
# CRITICAL FIX: Calculate costs for the selected filter range (not just MTD)
costs_selected_range = get_business_costs_for_period(business, start_date, end_date)

# Context variables: Use selected filter range values (not hardcoded MTD)
costs = costs_selected_range  # FIX: Was costs_this_month (ignored filter!)
profit = profit_selected_range  # FIX: Was profit_this_month (ignored filter!)
```

### Tests Added
**File**: `tests/test_gym_dashboard_metrics_fix.py`

Added 10 comprehensive tests (ALL PASSING ✅):
1. `test_member_counts` - Verifies active/arrears member counts
2. `test_metrics_mtd` - Tests MTD filter (revenue, costs, profit, payment mix)
3. `test_metrics_last_7_days` - Tests Last 7 Days filter
4. `test_metrics_today` - Tests Today filter  
5. `test_payment_mix_breakdown` - Tests payment method breakdown
6. `test_mrr_calculation` - Tests Monthly Recurring Revenue
7. `test_no_payments_or_costs` - Tests empty business scenario
8. `test_inactive_payments_excluded` - Tests that cancelled payments are excluded
9. `test_dashboard_view_context_keys` - Integration test for view context
10. `test_dashboard_financial_metrics_match_filter` - Tests filter consistency

### Acceptance Criteria - ALL MET ✅
- ✅ Revenue reflects selected filter (Today/Last 7 Days/MTD)
- ✅ Costs reflect selected filter (not hardcoded MTD)
- ✅ Profit = Revenue - Costs for selected filter
- ✅ MRR = Total revenue this month (MTD)
- ✅ Member counts reflect real members (active/arrears)
- ✅ Payment Mix totals match Revenue totals for same filter range

---

## Problem B: Recurring Costs Broken ✅ FIXED

### Part 1: Save Bug (✅ Already Working)
**Status**: NOT A BUG - Already working correctly in codebase

The recurring cost save functionality was already implemented correctly:
- Form: `wallet/forms.py` - `AdminCostForm` auto-sets `type` based on `is_recurring`
- Service: `wallet/services_costs.py` - `add_business_cost` correctly creates recurring templates
- View: `wallet/views_costs.py` - `admin_cost_create` properly passes `is_recurring` parameter

**Tests**: 3 tests confirm correct behavior (ALL PASSING ✅)

### Part 2: Auto-Generation Bug ✅ FIXED
**Root Cause**: 
The `ensure_monthly_recurring_costs` function in `wallet/utils_costs.py` had a bug in duplicate detection logic (lines 71-78). When checking if a monthly instance already exists, it was NOT filtering by:
- `type=TxnType.COST_RECURRING`
- `is_recurring=False`

This caused it to match the TEMPLATE itself (which has the same note/amount and might have effective_date in the same month), preventing instance creation.

**Fix Applied**:
**File**: `wallet/utils_costs.py` (lines 54-63)

Added explicit filters to distinguish instances from templates:
```python
existing = WalletTransaction.objects.filter(
    business=business,
    ledger=Ledger.COMPANY,
    type=TxnType.COST_RECURRING,
    is_recurring=False,  # CRITICAL: Instances have is_recurring=False
    note=template.note,
    amount=template.amount,
    effective_date__gte=month_start,
    effective_date__lte=month_end,
).exists()
```

**Tests**: 3 tests confirm idempotent monthly generation (ALL PASSING ✅)

### Part 3: Seeding ✅ IMPLEMENTED
**File**: `wallet/utils_costs.py` (lines 201-301)

Implemented `seed_default_recurring_cost_templates()` function that creates 10 default templates:
1. Rentals (fixed)
2. Transport (variable)
3. Utilities (fixed)
4. Internet (fixed)
5. Salaries (fixed)
6. Security (fixed)
7. Cleaning (variable)
8. Insurance (fixed)
9. Licenses & Permits (fixed)
10. Marketing & Advertising (variable)

Features:
- ✅ Idempotent (won't create duplicates)
- ✅ Templates marked with `seeded=True` in meta
- ✅ Placeholder amount (MWK 0.01) - user sets actual amount
- ✅ Default recurrence day = 1st of month

**Tests**: 2 tests confirm seeding (ALL PASSING ✅)

### Part 4: UI (Card Panels) ⏳ IN PROGRESS
**Status**: To be implemented next

Requirements:
- Show recurring cost templates as clickable card panels (grid layout)
- Each card displays: name, amount, recurrence day, status (Active/Paused)
- Click card to edit/activate/pause
- "Add recurring cost" quick-add card
- Keep Bootstrap styling consistent with dashboard

---

## Files Changed

### Core Fixes
1. `inventory/verticals/gym.py` - Fixed dashboard costs filtering (lines 124-178)
2. `wallet/utils_costs.py` - Fixed auto-generation + added seeding (lines 54-63, 201-301)

### Tests Added
1. `tests/test_gym_dashboard_metrics_fix.py` - 10 tests for dashboard metrics
2. `tests/test_recurring_costs_fix.py` - 7 tests for recurring costs system

### Total Test Coverage
- **17 new tests added**
- **ALL PASSING ✅** (0 failures, 0 errors)

---

## Running the Tests

### Dashboard Metrics Tests
```bash
python manage.py test tests.test_gym_dashboard_metrics_fix -v 2
```

### Recurring Costs Tests
```bash
python manage.py test tests.test_recurring_costs_fix -v 2
```

### All New Tests
```bash
python manage.py test tests.test_gym_dashboard_metrics_fix tests.test_recurring_costs_fix -v 2
```

---

## Regression Safety ✅

- ✅ No changes to existing verticals (phones, liquor, pharmacy, clothing, etc.)
- ✅ No changes to tenant logic, auth, OTP/2FA
- ✅ No changes to billing or PayChangu
- ✅ No changes to marketing pages
- ✅ Surgical fixes only (gym dashboard + recurring costs)
- ✅ All tests use proper Business.status field (not is_active property)
- ✅ Tests handle unique slug constraints properly

---

## Next Steps

1. ✅ Problem A (Dashboard metrics) - COMPLETE
2. ✅ Problem B Part 1-3 (Recurring costs save/generation/seeding) - COMPLETE
3. ⏳ Problem B Part 4 (UI card panels) - IN PROGRESS

---

## Performance Notes

- Costs calculation uses indexed queries (business_id, ledger, type, effective_date)
- Auto-generation is idempotent (safe to call multiple times)
- Seeding checks for existing templates before creating (no duplicates)
- Dashboard already calls `ensure_monthly_recurring_costs` on costs list page (lines 94-104 of wallet/views_costs.py)

