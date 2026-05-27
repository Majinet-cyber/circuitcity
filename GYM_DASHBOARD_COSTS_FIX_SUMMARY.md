# Gym Dashboard Costs Fix - Summary

## Problem
**Bug Report:** Gym dashboard "Costs" showed MK 0.00 even after adding costs in `/wallet/admin/costs/`. The dashboard was not pulling admin wallet costs at all.

## Root Cause
The `gym_dashboard` view in `inventory/views_gym.py` was missing any cost calculation logic. While the templates expected `costs`, `revenue`, and `profit` variables, the view was not computing or passing them to the context.

## Solution

### 1. Added Cost Calculation Helper Function
**File:** `inventory/utils_gym.py`

Created `get_business_costs_for_period()` function that:
- Queries `WalletTransaction` with `ledger=COMPANY` and cost types
- Handles both once-off costs (filtered by `effective_date`) and recurring costs (filtered by `effective_from`)
- Returns costs as positive Decimal (stored as negative in DB)
- Properly scopes by business (no location scoping since `WalletTransaction` doesn't have location FK)

```python
def get_business_costs_for_period(business, start_date: date, end_date: date) -> Decimal:
    """
    Calculate total admin costs for a business in a given period.
    Uses the same logic as the admin wallet costs page for consistency.
    """
    ...
```

### 2. Updated Gym Dashboard View
**File:** `inventory/views_gym.py`

Added financial metrics calculation section that computes:
- `costs_today`, `costs_yesterday`, `costs_this_month`
- `revenue_today`, `revenue_yesterday`, `revenue_this_month` (from GymPayment)
- `profit_today`, `profit_yesterday`, `profit_this_month` (revenue - costs)
- `payment_count_month`
- `mrr` (Monthly Recurring Revenue estimate)

All values are passed to both dashboard templates:
- Detailed template: `templates/inventory/gym/dashboard.html`
- Simplified template: `templates/verticals/gym/dashboard.html`

### 3. Updated Templates
**File:** `templates/inventory/gym/dashboard.html`

Added "Financial Performance (This Month)" section displaying:
- **Revenue**: MWK amount with payment count
- **Costs**: MWK amount (from admin wallet)
- **Profit**: MWK amount with color-coding (green if positive, red if negative)
- **MRR**: Monthly Recurring Revenue

The simplified template (`templates/verticals/gym/dashboard.html`) already had the structure and now receives the correct values.

### 4. Added Regression Tests
**File:** `tests/test_gym_dashboard_enhancements.py`

Added two test cases:
1. `test_gym_dashboard_includes_admin_costs`: Verifies costs from admin wallet appear correctly
2. `test_gym_dashboard_costs_scoped_to_business`: Ensures costs from other businesses don't leak

## Technical Details

### Cost Query Logic
- **Once-off costs**: Include if `effective_date` is within the date range
- **Recurring costs**: Include if `effective_from <= end_date` (assumes they continue indefinitely)
- **Business scoping**: Filters by `business` FK
- **No location scoping**: `WalletTransaction` model doesn't have a location field

### Data Flow
```
/wallet/admin/costs/ (Cost Creation)
    ↓
WalletTransaction (Model)
    ↓
get_business_costs_for_period() (Helper)
    ↓
gym_dashboard (View)
    ↓
dashboard.html (Template)
```

## Testing Results
✅ Both tests pass
✅ Costs display correctly: `'costs_this_month': Decimal('50000')`
✅ Revenue calculation works: `'revenue_this_month': Decimal('160000')`
✅ Profit calculation correct: `'profit_this_month': Decimal('110000')` (160k - 50k)
✅ Business scoping verified

## Files Changed
1. `inventory/utils_gym.py` - Added `get_business_costs_for_period()` helper
2. `inventory/views_gym.py` - Added financial metrics calculation section
3. `templates/inventory/gym/dashboard.html` - Added financial performance section
4. `tests/test_gym_dashboard_enhancements.py` - Added 2 regression tests

## Verification Steps
1. Navigate to `/wallet/admin/costs/`
2. Add a cost (e.g., MK 150,000 for "Office Rent")
3. Navigate to gym dashboard (`/gym/`)
4. Verify "Costs (This Month)" shows MK 150,000
5. Verify "Profit" decreases by MK 150,000

## Impact
- ✅ Gym vertical now correctly shows admin wallet costs
- ✅ Profit calculation is now accurate (revenue - costs)
- ✅ No impact on other verticals (scoped to gym dashboard only)
- ✅ Consistent with admin wallet cost tracking
- ✅ Proper date/time awareness and business scoping

## Notes
- `WalletTransaction` model does NOT have a `location` field, so costs are business-scoped only
- If location-specific cost tracking is needed in the future, `location` FK would need to be added to `WalletTransaction` model
- The fix uses the same cost query logic as `inventory/services/dashboard_metrics.py` for consistency

