# Gym Dashboard Costs Bug Fix - Implementation Summary

## Bug Description

**Issue:** Costs added in `/wallet/admin/costs/` (e.g., Rent MK 150,000) were not appearing on `/verticals/gym/dashboard/`. The costs card showed MK 0.00 even after adding costs through the admin wallet interface.

**Root Cause:** The verticals gym dashboard (`inventory/verticals/gym.py`) was querying the wrong data source:
- ❌ **Before:** Queried `GymWalletEntry` for costs (lines 98-103)
- ✅ **After:** Queries `WalletTransaction` with `ledger=COMPANY` and `type__in=[COST_ONCE_OFF, COST_RECURRING]` (same as admin wallet costs page)

## Implementation

### 1. Updated Verticals Gym Dashboard (`inventory/verticals/gym.py`)

**Changes Made:**
- Replaced `GymWalletEntry` cost queries with `get_business_costs_for_period()` helper
- Added period-specific cost calculations:
  - `costs_today`
  - `costs_yesterday`
  - `costs_this_month`
- Added period-specific revenue calculations:
  - `revenue_today`
  - `revenue_yesterday`
  - `revenue_this_month`
- Added period-specific profit calculations:
  - `profit_today = revenue_today - costs_today`
  - `profit_yesterday = revenue_yesterday - costs_yesterday`
  - `profit_this_month = revenue_this_month - costs_this_month`
- Maintained backward compatibility with legacy variables: `costs`, `revenue`, `profit`

**Key Code Section:**

```python
# ============================================================================
# COSTS: Use admin wallet costs (same source as /wallet/admin/costs/)
# This fixes the bug where costs added in admin wallet didn't show on dashboard
# ============================================================================
from inventory.utils_gym import get_business_costs_for_period

costs_today = get_business_costs_for_period(business, today, today)
costs_yesterday = get_business_costs_for_period(business, yesterday, yesterday)
costs_this_month = get_business_costs_for_period(business, month_start.date(), today)

# ============================================================================
# REVENUE: Calculate from GymPayment for today, yesterday, this month
# ============================================================================
revenue_today = GymPayment.objects.filter(
    member__business=business,
    is_active=True,
    paid_at__gte=today_start,
    paid_at__lte=today_end
).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

# ... similar for revenue_yesterday and revenue_this_month ...

# ============================================================================
# PROFIT: Calculate profit = revenue - costs for each period
# ============================================================================
profit_today = revenue_today - costs_today
profit_yesterday = revenue_yesterday - costs_yesterday
profit_this_month = revenue_this_month - costs_this_month
```

### 2. Helper Function (`inventory/utils_gym.py`)

**No changes needed** - The existing `get_business_costs_for_period()` function (lines 308-366) already implements the correct logic:

```python
def get_business_costs_for_period(business, start_date: date, end_date: date) -> Decimal:
    """
    Calculate total admin costs for a business in a given period.
    
    This uses the same logic as the admin wallet costs page to ensure consistency.
    Costs are pulled from WalletTransaction with:
    - ledger=COMPANY
    - type in [COST_ONCE_OFF, COST_RECURRING]
    - business scoping (no location scoping since WalletTransaction doesn't have location)
    """
    from wallet.models import WalletTransaction, Ledger, TxnType
    
    # Query admin costs for this business
    admin_costs_qs = WalletTransaction.objects.filter(
        business=business,
        ledger=Ledger.COMPANY,
        type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
    )
    
    # Filter by effective date range...
    # Sum costs (they're stored as negative, so we take absolute value)
    return abs(admin_costs_sum)
```

### 3. Cost Data Source (`wallet/services_costs.py` & `wallet/views_costs.py`)

**No changes needed** - The admin wallet costs page already creates costs correctly using `add_business_cost()`:

```python
def add_business_cost(
    business,
    name: str,
    amount: Decimal,
    cost_category: str = 'variable',
    is_recurring: bool = False,
    effective_date: Optional[date] = None,
    created_by=None,
    note: str = '',
) -> WalletTransaction:
    """Add a cost entry for a business."""
    txn = WalletTransaction.objects.create(
        business=business,
        ledger=Ledger.COMPANY,
        type=TxnType.COST_RECURRING if is_recurring else TxnType.COST_ONCE_OFF,
        amount=-abs(amount),  # Stored as negative
        note=full_note,
        effective_date=effective_date,
        is_recurring=is_recurring,
        created_by=created_by,
        meta={'cost_category': cost_category, 'cost_name': name}
    )
    return txn
```

### 4. Templates

**No changes needed** - Both templates already use the correct variables:

- `templates/verticals/gym/dashboard.html`: Uses `costs`, `revenue`, `profit` (legacy variables)
- `templates/inventory/gym/dashboard.html`: Uses `costs_this_month`, `revenue_this_month`, `profit_this_month`

Both templates now display identical cost data because they both pull from the same source.

## Testing

### Tests Added (`tests/test_verticals_gym_costs.py`)

Created comprehensive test suite with 7 tests:

1. **`test_verticals_gym_dashboard_shows_admin_wallet_costs`** ✅
   - Creates costs via admin wallet (Rent: 150k, Utilities: 25k)
   - Verifies costs appear on verticals dashboard (175k total)
   - PRIMARY test for the bug fix

2. **`test_verticals_gym_dashboard_profit_calculation`** ✅
   - Creates cost (50k) and revenue (100k)
   - Verifies profit = revenue - costs (50k)

3. **`test_verticals_gym_dashboard_costs_scoped_to_business`** ✅
   - Creates costs for two different businesses
   - Verifies business isolation (only shows costs for active business)

4. **`test_verticals_gym_dashboard_costs_by_period`** ✅
   - Creates costs for today, yesterday, and last month
   - Verifies period filtering (today: 10k, yesterday: 20k, this month: 30k+)

5. **`test_both_gym_dashboards_show_same_costs`** ✅
   - **REGRESSION TEST**: Ensures `/gym/dashboard/` and `/verticals/gym/dashboard/` show identical costs
   - Creates cost (75k) and checks both dashboards
   - Verifies consistency across both dashboards

6. **`test_admin_wallet_cost_creation`** ✅
   - Verifies costs are created correctly in `WalletTransaction`
   - Tests the data source

7. **`test_recurring_vs_once_off_costs`** ✅
   - Verifies both cost types are correctly identified
   - Tests COST_ONCE_OFF and COST_RECURRING

### Test Results

```
Ran 7 tests in 40.395s

OK
```

All tests passed! ✅

## Verification

### Manual Testing Checklist

1. ✅ Add cost in `/wallet/admin/costs/` (e.g., Rent MK 150,000)
2. ✅ Refresh `/verticals/gym/dashboard/`
   - Costs card shows MK 150,000
   - Profit decreases accordingly
3. ✅ Check `/gym/dashboard/` (inventory dashboard)
   - Shows same costs (MK 150,000)
4. ✅ Verify business isolation
   - Costs from other businesses don't appear
5. ✅ Verify period filtering
   - Today's costs only show today's transactions
   - This month's costs include all transactions this month

## Key Files Changed

1. **`inventory/verticals/gym.py`** - Updated to use admin wallet costs
2. **`tests/test_verticals_gym_costs.py`** - New comprehensive test suite

## No Regressions

- ✅ Inventory gym dashboard (`/gym/dashboard/`) still works correctly
- ✅ Admin wallet costs page (`/wallet/admin/costs/`) unchanged
- ✅ Template rendering unchanged
- ✅ Business isolation maintained
- ✅ Other verticals unaffected

## Impact

### Before Fix
- ❌ `/verticals/gym/dashboard/` showed MK 0.00 for costs
- ❌ Profit calculation incorrect
- ❌ Confusing discrepancy between admin wallet and dashboard

### After Fix
- ✅ `/verticals/gym/dashboard/` shows correct costs from admin wallet
- ✅ Profit calculated correctly (revenue - costs)
- ✅ Both gym dashboards show identical metrics
- ✅ Immediate reflection of costs added in admin wallet

## Acceptance Criteria Met

✅ Add cost MK 150,000 in `/wallet/admin/costs/`  
✅ Refresh `/verticals/gym/dashboard/` → Costs card shows MK 150,000  
✅ Profit decreases accordingly  
✅ `/gym/dashboard/` matches  
✅ Other verticals unaffected  
✅ Business scoping isolation verified  
✅ Tests pass (7/7)

## Technical Details

### Data Flow

```
Admin Wallet Costs Page (/wallet/admin/costs/)
    ↓
WalletTransaction.objects.create(
    ledger=Ledger.COMPANY,
    type=TxnType.COST_ONCE_OFF or TxnType.COST_RECURRING,
    business=business,
    amount=-abs(amount)  # Negative for expense
)
    ↓
get_business_costs_for_period(business, start_date, end_date)
    ↓
Both Gym Dashboards:
  - /gym/dashboard/ (inventory)
  - /verticals/gym/dashboard/ (verticals)
    ↓
Display: costs_this_month, profit = revenue - costs
```

### Single Source of Truth

**WalletTransaction** with:
- `ledger = Ledger.COMPANY`
- `type in [TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]`
- `business = <active_business>` (scoped to tenant)

### Business Scoping

All queries filter by `business=request.business` to ensure:
- ✅ Multi-tenant isolation
- ✅ No data leakage between businesses
- ✅ Correct costs for active business only

## Migration Path

No database migrations required. This is a pure logic fix updating how costs are queried.

## Performance Considerations

- Queries use indexed fields (`business`, `ledger`, `type`, `effective_date`)
- Aggregations use database-level `Sum()` (efficient)
- No N+1 queries introduced
- Same query pattern as admin wallet costs page (proven performant)

## Future Enhancements

Potential improvements (not required for this fix):

1. **Caching**: Cache cost totals for frequently accessed periods
2. **Dashboard Consolidation**: Consider merging `/gym/dashboard/` and `/verticals/gym/dashboard/` to avoid duplication
3. **Location Scoping**: If costs should be location-specific, update `WalletTransaction` model
4. **Cost Categories**: Add UI for filtering by fixed/variable costs
5. **Cost Trends**: Add cost trend charts (week-over-week, month-over-month)

## Conclusion

The bug has been successfully fixed. Both gym dashboards now correctly display costs from the admin wallet system, ensuring consistent financial reporting across the application.

**Status:** ✅ **COMPLETE**  
**Tests:** ✅ **7/7 PASSING**  
**Regressions:** ✅ **NONE**  
**Production Ready:** ✅ **YES**

