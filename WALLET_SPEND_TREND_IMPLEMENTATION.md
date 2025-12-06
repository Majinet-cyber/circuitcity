# Business Spend Trend Implementation Summary

## Overview
Implemented the "Business Spend Trend (recent)" chart on `/wallet/admin/` to display real data from admin costs and agent commissions.

## Changes Made

### 1. Backend: `wallet/views.py`

#### Added Imports
- `timedelta` for date calculations
- `DjangoJSONEncoder` for proper JSON serialization of date objects

#### Updated `AdminWalletHome.get_context_data()`
- Added call to `_compute_spend_trend(business)` to generate chart data
- Returns JSON-encoded trend data in context as `business_spend_trend`

#### New Method: `AdminWalletHome._compute_spend_trend(business)`
Computes spend trend data for the last 14 days:

**Data Sources:**
1. **Costs** - from `WalletTransaction` model:
   - Filters by `COST_ONCE_OFF` and `COST_RECURRING` types
   - Uses `effective_date` for date grouping
   - Converts negative amounts to positive for display
   - Scoped to business

2. **Commissions** - from `SaleCommission` model:
   - Uses `created_at` date for grouping
   - Aggregates `net_amount` (includes base + bonuses - penalties)
   - Scoped to business
   - Gracefully handles if model is unavailable

**Output Format:**
```json
[
  {
    "date": "2025-12-01",
    "costs": 1000.0,
    "commissions": 500.0
  },
  ...
]
```

### 2. Frontend: `templates/wallet/admin_home.html`

#### Updated Chart Card
- Changed badge from "Last X entries" to "Last 14 days"
- Added container ID `spendChartContainer` for graceful empty state handling
- Updated description to clarify data shown

#### Replaced Chart JavaScript
**Old Behavior:**
- Used `recent` WalletTransactions (last 30 entries)
- Showed raw transaction amounts (positive/negative bars)
- Single dataset

**New Behavior:**
- Uses `business_spend_trend` JSON data
- Shows two separate line series:
  - **Costs** (red): Daily admin costs
  - **Commissions** (blue): Daily commission payouts
- Line chart with filled areas and smooth curves
- **Empty State:** Shows friendly message when no data available:
  > "No spend data yet. Add costs or pay commissions to see trends here."

**Chart Configuration:**
- Type: Line chart (changed from bar)
- Two datasets with distinct colors
- Tension: 0.4 for smooth curves
- Fill: True for area under lines
- Interactive tooltips with formatted currency
- Legend enabled at top
- Y-axis shows "MWK" prefix
- X-axis shows dates

### 3. Tests: `tests/test_wallet_costs.py`

Added comprehensive test class `TestBusinessSpendTrend` with 3 test cases:

#### Test 1: `test_spend_trend_includes_costs_and_commissions`
- Creates business, manager, cost transaction, and commission
- Verifies `business_spend_trend` is in response context
- Parses JSON and validates:
  - At least one data entry exists
  - Today's costs are correctly displayed (1000.0)
  - Today's commissions are correctly displayed (500.0)

#### Test 2: `test_spend_trend_empty_data`
- Tests with business that has no costs or commissions
- Verifies response is 200
- Validates empty data is handled (empty array or all zeros)

#### Test 3: `test_spend_trend_multiple_days`
- Creates costs across 3 different days
- Verifies multiple entries in trend data
- Validates data is sorted by date (ascending)

**Test Coverage:**
- Business scoping (only shows data for active business)
- Multiple cost types (once-off and recurring)
- Date aggregation and sorting
- Empty state handling
- JSON serialization

## Data Flow

```
User visits /wallet/admin/
    ↓
AdminWalletHome.get_context_data()
    ↓
_compute_spend_trend(business)
    ↓
Query WalletTransaction (costs) ─┐
Query SaleCommission (commissions) ┘
    ↓
Aggregate by date
    ↓
Convert to JSON with DjangoJSONEncoder
    ↓
Template receives business_spend_trend
    ↓
JavaScript parses and renders Chart.js line chart
    ↓
User sees costs and commissions trend
```

## Key Features

### ✅ Real Data
- Pulls actual admin costs (fixed + variable, recurring + once-off)
- Pulls actual agent commissions from sales
- No mock/placeholder data

### ✅ No Errors
- Graceful handling when no data exists
- Try/catch for commission model availability
- No more "Failed to load chart" messages

### ✅ Auto-Updates
- Data is computed fresh on each page load
- New costs or commissions appear immediately
- No caching issues

### ✅ Business Scoping
- Respects multi-tenant architecture
- Managers see only their business data
- Superusers see all businesses (configurable)

### ✅ No Migrations
- Uses existing models and fields
- No database schema changes
- No data resets required

## Technical Notes

### Date Handling
- Uses Django's `localdate()` for timezone-aware dates
- 14-day window (configurable via `days_back` variable)
- Date range: `today - 14 days` to `today` (inclusive)

### Cost Amount Handling
- Costs stored as negative in DB (expenses)
- Converted to positive for display: `abs(amount)`
- Commissions already positive (earnings)

### Commission Query
- Uses `.extra(select={'date': 'DATE(created_at)'})` for date extraction
- Falls back gracefully if SaleCommission model unavailable
- Handles both dict key formats (`date` and `created_at__date`)

### JSON Serialization
- Uses `DjangoJSONEncoder` for proper date serialization
- Template uses `escapejs` filter for XSS protection
- JavaScript parses with `JSON.parse()`

## Browser Compatibility
- Chart.js 4.x (loaded from CDN)
- Modern browsers (ES6+ JavaScript)
- Responsive design (maintains aspect ratio)
- Accessible (ARIA labels on canvas)

## Future Enhancements (Optional)
1. Make date range configurable (7/14/30 days)
2. Add date range picker
3. Add export to CSV/Excel
4. Add drill-down to see individual transactions
5. Add stacked area chart option
6. Add percentage breakdown
7. Cache computed trends (with invalidation on new data)

## Testing

Run tests:
```bash
pytest tests/test_wallet_costs.py::TestBusinessSpendTrend -v
```

Expected output:
- ✅ test_spend_trend_includes_costs_and_commissions
- ✅ test_spend_trend_empty_data
- ✅ test_spend_trend_multiple_days

## Files Modified

1. `wallet/views.py` - Added spend trend computation logic
2. `templates/wallet/admin_home.html` - Updated chart rendering
3. `tests/test_wallet_costs.py` - Added comprehensive tests

## Zero Breaking Changes

- ✅ No migrations required
- ✅ No existing data affected
- ✅ No URL changes
- ✅ No API changes
- ✅ Backward compatible
- ✅ Works with existing Cost and Commission models
- ✅ Respects existing business scoping logic

---

**Implementation Date:** December 6, 2025  
**Status:** ✅ Complete and tested

