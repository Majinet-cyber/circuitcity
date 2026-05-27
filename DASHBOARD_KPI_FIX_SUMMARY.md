# Dashboard KPI + Admin Costs Fix Summary

**Date:** December 9, 2025  
**Status:** ✅ Complete

## Problem Statement

The inventory dashboard was showing **MK 0** for all KPIs even after recording sales and adding admin costs:

1. **Dead KPIs:** Revenue, Costs, Profit all showing MK 0
2. **Missing Admin Costs:** Costs from Admin Wallet → Costs not included
3. **Ratio Cards Not Wired:** New ratio cards showing 0% / MK 0
4. **Payment Mix Not Working:** Payment method breakdown stuck at 0%

## Root Cause

The dashboard was **only calculating COGS** (Cost of Goods Sold from `item__order_price`) and **NOT including admin costs** from `WalletTransaction` (rent, salaries, utilities, etc.).

## Solution Implemented

### 1. Created Centralized KPI Service

**File:** `inventory/services/dashboard_metrics.py`

```python
def get_inventory_kpis(
    business,
    location,
    sales_qs,
    start_date,
    end_date,
    model_filter
) -> dict
```

**What it does:**
- ✅ Computes **Revenue** from sales (`Sum("price")`)
- ✅ Computes **COGS** from items (`Sum("item__order_price")`)
- ✅ Computes **Admin Costs** from `WalletTransaction` (both once-off and recurring)
- ✅ Computes **Total Costs** = COGS + Admin Costs
- ✅ Computes **Profit** = Revenue - Total Costs
- ✅ Computes **Revenue vs Costs ratios** (percentages sum to 100%)
- ✅ Computes **Profit vs Costs ratios** with low-margin warning
- ✅ Computes **Payment Mix** (Cash / Bank / Mobile Money percentages)

**Key Features:**
- Single source of truth for all dashboard metrics
- Respects business/tenant scoping
- Respects period filters (This month, Last 7 days, All time)
- Respects model/product filters
- Handles edge cases (zero revenue, single payment method, etc.)
- Efficient queries (no N+1, uses aggregations)

### 2. Updated Dashboard View

**File:** `inventory/views.py` (lines 6966-7001)

**Changes:**
- Replaced inline COGS-only calculations with call to `get_inventory_kpis()`
- Extracts backward-compatible variables for existing template code
- Adds `kpis_detail` to context for detailed breakdown

**Before:**
```python
# Only COGS
cost=Coalesce(Sum(Coalesce(F("item__order_price"), Value(0))), Value(0))
```

**After:**
```python
# COGS + Admin Costs
kpis = get_inventory_kpis(
    business=biz,
    location=user_loc,
    sales_qs=sales_qs_period,
    start_date=period_start,
    end_date=period_end,
    model_filter=model_id,
)
```

### 3. Updated Template Labels

**File:** `templates/partials/profit_panel.html` (line 25)

**Change:**
- Updated cost card label from **"Cost of goods sold"** to **"COGS + Admin costs"**
- Clarifies that the displayed cost now includes both product costs and business overhead

### 4. Added Comprehensive Tests

**File:** `inventory/tests/test_dashboard_metrics.py`

**New Test Class:** `DashboardAdminCostsTestCase`

**Test Cases:**
1. `test_admin_costs_included_in_dashboard_costs`
   - Verifies admin costs (Rent MK 200k) are added to COGS (MK 400k)
   - Total costs should be MK 600k

2. `test_recurring_admin_costs_included`
   - Verifies recurring costs (Monthly salary) are included
   - Tests monthly recurring cost handling

3. `test_profit_vs_costs_warning_with_admin_costs`
   - Verifies low-margin warning considers admin costs
   - Tests that high admin costs trigger warning even if COGS margin is decent

## Admin Costs Logic

### WalletTransaction Model Fields Used:
- `business`: Business scoping
- `ledger`: Must be `COMPANY` (not agent)
- `type`: `COST_ONCE_OFF` or `COST_RECURRING`
- `amount`: Stored as **negative** (expenses)
- `effective_date`: Date cost applies (for once-off)
- `effective_from`: Start date (for recurring)
- `is_recurring`: Boolean flag

### Cost Calculation:
```python
# Once-off costs within period
Q(type=COST_ONCE_OFF, effective_date__gte=start, effective_date__lte=end)

# Recurring costs active during period
Q(type=COST_RECURRING, is_recurring=True, effective_from__lte=end)

# Sum and convert to positive (stored as negative)
total_admin_costs = abs(sum(amounts))
```

## Dashboard Template Structure

### Big KPI Cards (Top Row)
Already present in `templates/partials/profit_panel.html` lines 3-44:
- 💚 **Revenue** (green gradient) - MK amount + units sold
- 🧡 **Costs** (orange gradient) - MK amount + "COGS + Admin costs"
- 💙 **Profit** (blue gradient) - MK amount + profit margin %

### Ratio Battery Cards (Second Row)
Already present in `templates/partials/profit_panel.html` lines 46-263:

1. **Revenue vs Costs** (lines 49-108)
   - Horizontal battery bar (green + orange)
   - Revenue % + Costs % = 100%
   - Shows MK amounts

2. **Profit vs Costs** (lines 111-182)
   - Horizontal battery bar (blue + orange/red)
   - Profit % + Costs % = 100%
   - ⚠ **Low Margin Warning** if costs > 10% of revenue
   - Warning badge + red border when triggered

3. **Payment Mix** (lines 185-262)
   - **Single battery** with 3 segments (Cash, Bank, Mobile)
   - Green (Cash) + Blue (Bank) + Orange (Mobile) = 100%
   - Shows % and MK amounts for each

## Verification Steps

### 1. Test Zero State
```bash
python manage.py test inventory.tests.test_dashboard_metrics.DashboardMetricsTestCase.test_dashboard_metrics_zero_when_no_sales
```
**Expected:** All metrics = 0, no crashes

### 2. Test Sale Only (No Admin Costs)
- Record sale: ITEL A90, MK 600,000 (cost MK 400,000)
- **Expected:**
  - Revenue: MK 600,000
  - Costs: MK 400,000 (COGS only)
  - Profit: MK 200,000
  - Margin: 33%

### 3. Test Sale + Admin Cost
- Add admin cost: Rent, MK 200,000
- **Expected:**
  - Revenue: MK 600,000
  - Costs: MK 600,000 (MK 400k COGS + MK 200k Admin)
  - Profit: MK 0
  - Warning: ⚠ Costs > 10% of revenue

### 4. Test Payment Mix
- Record 3 sales: 1 Cash, 1 Bank, 1 Mobile Money
- **Expected:**
  - Cash ≈ 33%, Bank ≈ 33%, Mobile ≈ 33%
  - Battery segments visible
  - Percentages sum to 100%

### 5. Run All Tests
```bash
python manage.py test inventory.tests.test_dashboard_metrics
```

## What Changed vs What Stayed

### ✅ Changed (Fixed)
1. **Costs now include admin costs** from WalletTransaction
2. **Profit calculation** now accurate (Revenue - Total Costs)
3. **Low margin warning** considers total costs (not just COGS)
4. **Payment mix** now shows actual payment method breakdown
5. **All percentages** now based on real data

### ✅ Stayed the Same (No Breaking Changes)
1. **Template structure** (profit_panel.html already had everything)
2. **URL routes** (no new routes needed)
3. **Database schema** (no migrations needed)
4. **Existing views** (only internal calculations changed)
5. **Mobile layout** (responsive design already in place)

## Filter Behavior

All KPIs respect these filters (already implemented):

1. **Period Filter:**
   - "This month" (default)
   - "Last 7 days"
   - "All time"
   - Custom date range

2. **Model Filter:**
   - "All models"
   - Specific product/model

3. **Business Scoping:**
   - Multi-tenant safe
   - Only shows data for active business

4. **Agent Scoping:**
   - Managers see all agents
   - Agents see only their own sales

## Performance Considerations

1. **Query Efficiency:**
   - Uses Django ORM aggregations (single query per metric)
   - No N+1 queries
   - Indexes already exist on relevant fields

2. **Caching:**
   - Dashboard context cached for 60 seconds
   - Cache key includes business, user, period, model filter
   - Cache invalidated on sale (via `bump_dashboard_cache_version`)

3. **Decimal Safety:**
   - All money calculations use `DecimalField`
   - No float precision errors

## Known Edge Cases Handled

- ✅ Zero revenue (no sales) → no division by zero
- ✅ Zero costs → percentages handled gracefully
- ✅ Single payment method → 100% in one category
- ✅ Negative profit → profit% clamped at 0
- ✅ Rounding drift → last percentage takes remainder
- ✅ No admin costs → falls back to COGS only
- ✅ Multiple businesses → proper scoping

## Future Enhancements (Optional)

1. **Cost Categories:**
   - Break down admin costs by category (Rent, Salaries, Utilities, etc.)
   - Show cost category breakdown in a drill-down view

2. **Period Comparison:**
   - Show "vs last month" deltas
   - Trend indicators (↑↓)

3. **Cost Alerts:**
   - Alert when costs exceed budget
   - Alert when recurring cost payment due

4. **Export:**
   - Download dashboard data as CSV/Excel
   - Include cost breakdown

## Rollback Plan (If Needed)

If issues arise, revert these files:
1. `inventory/services/dashboard_metrics.py` (new file - can delete)
2. `inventory/views.py` lines 6966-7001
3. `templates/partials/profit_panel.html` line 25

The dashboard will fall back to COGS-only calculations (previous behavior).

## Related Files

- ✅ `inventory/services/dashboard_metrics.py` (new)
- ✅ `inventory/views.py` (modified)
- ✅ `templates/partials/profit_panel.html` (label updated)
- ✅ `inventory/tests/test_dashboard_metrics.py` (tests added)
- ✅ `wallet/models.py` (referenced, not modified)
- ✅ `sales/models.py` (referenced, not modified)

## Success Criteria

- [x] Revenue shows MK amount matching sales
- [x] Costs include COGS + admin costs from wallet
- [x] Profit = Revenue - Total Costs
- [x] Revenue vs Costs percentages sum to 100%
- [x] Profit vs Costs percentages sum to 100%
- [x] Low margin warning triggers when costs > 10% of revenue
- [x] Payment mix shows Cash / Bank / Mobile breakdown
- [x] Payment mix percentages sum to 100%
- [x] All filters (period, model, business) work correctly
- [x] All tests pass
- [x] No regressions in existing functionality

## Contact

For questions or issues, refer to:
- Implementation: `inventory/services/dashboard_metrics.py`
- Tests: `inventory/tests/test_dashboard_metrics.py`
- Documentation: This file

---

**Implementation Complete ✅**

