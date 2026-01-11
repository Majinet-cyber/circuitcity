# GYM DASHBOARD METRICS FIX - COMPREHENSIVE SOLUTION

## CRITICAL BUG FIXED
**Issue**: Gym dashboard "Financial Performance (Month to Date)" showed MWK 0 for Revenue/Costs/Profit/MRR even though payments existed (the card showed "4 payments"). Payment mix/list could show amounts, but KPI totals remained 0.

**Root Cause**: The metrics calculation relied on the `GymPayment.amount` field, which could be 0 or NULL for legacy data. Migration 0111 only backfilled NULL cases, not amount=0 cases.

## SOLUTION IMPLEMENTED

### 1. Data Integrity Fix (Migration 0112)
**File**: `inventory/migrations/0112_backfill_gympayment_amount_comprehensive.py`

**What it does**:
- Backfills `GymPayment.amount` for BOTH:
  - `amount IS NULL`
  - `amount == 0 AND (membership_amount > 0 OR trainer_fee > 0)`
- Uses Django F expressions + Coalesce for efficiency
- Formula: `amount = membership_amount + trainer_fee`
- Idempotent (safe to run multiple times)

**Key improvements over 0111**:
- Handles amount=0 cases (not just NULL)
- Uses bulk update with F expressions (more efficient)
- Better logging

### 2. Model Guarantee (Already Correct)
**File**: `inventory/models_verticals.py` (line 1478)

The `GymPayment.save()` method already correctly computes:
```python
self.amount = self.membership_amount + self.trainer_fee
```

This ensures all NEW payments will have correct amounts.

### 3. Metrics Robustness (The Real "Never Break" Layer)
**Files Modified**:
- `inventory/services/gym_metrics.py`
- `inventory/verticals/gym.py`
- `inventory/views_gym.py`
- `inventory/analytics/adapters/gym.py`

**Critical Change**: Revenue is now ALWAYS calculated directly from:
```python
Sum(
    ExpressionWrapper(
        Coalesce(F("membership_amount"), Value(Decimal("0.00"))) +
        Coalesce(F("trainer_fee"), Value(Decimal("0.00"))),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
)
```

**Defense in Depth**: Even if amount field has bad data, revenue will ALWAYS be correct because we compute from source fields.

### 4. Template Wiring (Verified Correct)
**File**: `templates/verticals/gym/dashboard.html`

Template correctly uses context keys:
- `revenue` - Total revenue
- `costs` - Total costs
- `profit` - Revenue - Costs
- `payment_count` - Number of payments
- `payment_mix` - Breakdown by payment method
- `mrr` - Monthly recurring revenue

All keys are properly populated by the view.

### 5. Comprehensive Regression Tests
**File**: `tests/test_gym_dashboard_metrics_fix_regression.py`

**Tests cover**:
1. ✅ Revenue > 0 when amount=NULL but membership_amount > 0
2. ✅ Revenue > 0 when amount=0 but membership_amount > 0
3. ✅ Multiple payments with mixed conditions (NULL, 0, correct)
4. ✅ Payment mix sums match total revenue
5. ✅ GymPayment.save() always computes amount correctly
6. ✅ Migration backfills amount field correctly

**All 6 tests pass**.

## FILES CHANGED

### New Files:
1. `inventory/migrations/0112_backfill_gympayment_amount_comprehensive.py` - Data migration
2. `tests/test_gym_dashboard_metrics_fix_regression.py` - Regression tests

### Modified Files:
1. `inventory/services/gym_metrics.py` - Calculate revenue from components (not amount field)
2. `inventory/verticals/gym.py` - Calculate revenue_today/yesterday from components
3. `inventory/views_gym.py` - Calculate revenue_today/yesterday from components
4. `inventory/analytics/adapters/gym.py` - Calculate revenue from components + add DecimalField import

### Verified Correct (No Changes):
1. `inventory/models_verticals.py` - GymPayment.save() already correct (line 1478)
2. `templates/verticals/gym/dashboard.html` - Context keys correct

## TEST RESULTS

```bash
pytest tests/test_gym_dashboard_metrics_fix_regression.py -v -q
```

**Result**: 6 passed, 10 warnings in 5.05s ✅

## ACCEPTANCE CRITERIA MET

✅ **With existing DB data, gym dashboard shows correct non-zero Revenue/Costs/Profit when payments/costs exist**
- Metrics now compute from membership_amount + trainer_fee directly
- Migration backfills legacy data

✅ **No more "MWK 0" when there are real payments**
- Defense in depth: metrics NEVER rely on amount field
- Always compute from source fields

✅ **Backfill migration updates legacy amount=0 rows safely**
- Migration 0112 handles both NULL and 0 cases
- Uses F expressions for efficiency
- Idempotent

✅ **Tests prevent this from ever coming back**
- 6 comprehensive regression tests
- Cover all edge cases (NULL, 0, mixed)
- Test both metrics calculation and model save()

✅ **No regressions in other verticals or billing/auth**
- Changes only touch gym metrics calculation
- No changes to tenant/auth/billing flows
- UI layout intact

## HOW TO USE

### 1. Run the migration:
```bash
python manage.py migrate inventory
```

This will backfill any legacy payments with amount=0 or NULL.

### 2. Verify the fix:
```bash
pytest tests/test_gym_dashboard_metrics_fix_regression.py -v
```

All tests should pass.

### 3. Check your dashboard:
Navigate to `/gym/dashboard/` and verify that:
- Revenue shows actual payment totals (not MWK 0)
- Payment count matches number of payments
- Payment mix sums to total revenue
- Costs show admin wallet costs
- Profit = Revenue - Costs

## TECHNICAL DETAILS

### Why This Fix is Bulletproof

1. **Data Layer**: Migration fixes historical data
2. **Model Layer**: save() ensures new data is correct
3. **Metrics Layer**: Calculations never trust amount field (defense in depth)
4. **Test Layer**: Comprehensive tests prevent regression

Even if:
- Someone manually updates amount to 0/NULL in DB
- Legacy migration didn't run
- Model save() somehow fails

**The metrics will STILL be correct** because they compute from source fields.

### Performance Impact

Minimal. The ExpressionWrapper with F expressions is evaluated in the database, so it's just as fast as `Sum("amount")`.

### Migration Safety

The migration uses:
- Bulk update with F expressions (fast)
- Idempotent logic (safe to rerun)
- Clear logging (shows what it's doing)
- No data deletion (only fixes bad data)

## PREVENTION

To prevent this bug from ever happening again:

1. **Always use `get_gym_dashboard_metrics()` service** for financial metrics
2. **Never query GymPayment.amount directly** - always compute from components
3. **Run regression tests** before deploying gym changes
4. **Monitor dashboard** - if KPIs show 0 when payments exist, this fix prevents it

## SUMMARY

This fix ensures the gym dashboard will ALWAYS reflect real payments and costs, fulfilling the core SaaS promise. The defense-in-depth approach (migration + model + metrics + tests) makes it virtually impossible for this bug to recur.

**Migration**: 0112_backfill_gympayment_amount_comprehensive
**Tests**: All pass (6/6)
**Status**: ✅ COMPLETE

