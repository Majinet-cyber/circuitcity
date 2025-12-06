# Dashboard Charts Fix Summary

## Issue Description
The `/dashboard/` page had two major problems:
1. **Two large charts showing "⚠️ Failed to load chart"** instead of displaying data
2. **Active Stock KPI showing "MK 3" (currency)** instead of just "3" (count)

## Root Causes

### Chart API Issues
The chart APIs (`/dashboard/api/sales-trend/` and `/dashboard/api/top-models/`) were:
- **Using the Sale model** instead of InventoryItem model
- **Missing manager sales** because they only queried Sale records
- The KPIs on the same page use InventoryItem and work fine, creating inconsistency

### Active Stock KPI Issue
The JavaScript animation function was adding "MK " prefix to **ALL** stat values, including the Active Stock count which should be a plain number.

## Fixes Implemented

### 1. Rewrote Chart API Proxy Functions
**File:** `dashboard/views.py`

Rewrote `v2_sales_trend_data_proxy` and `v2_top_models_data_proxy` to:
- ✅ Use **InventoryItem model** (same as dashboard KPIs)
- ✅ Use `SOLD_Q()` to filter sold items properly
- ✅ Use `_scope_queryset()` for proper business scoping
- ✅ Include **manager sales** (not just agent sales)
- ✅ Return valid JSON even when there's NO sales data
- ✅ Support session-based business lookup (for tests and edge cases)

**Key changes:**
```python
# Before: Used Sale model via api_sales_metrics
response = api_sales_trend(request)

# After: Direct InventoryItem query
sold_items = (
    _scope_queryset(InventoryItem.objects.all(), business)
    .filter(SOLD_Q(), sold_at__gte=start_date, sold_at__lt=end_date)
)
```

### 2. Fixed Active Stock KPI Display
**File:** `templates/dashboard/home.html`

**Added `data-format` attribute** to distinguish between currency and count values:
```html
<!-- Currency values -->
<div class="stat-value" data-animate-value="{{ today_sales_amount }}" data-format="currency">MK 0</div>

<!-- Count values (NO currency) -->
<div class="stat-value" data-animate-value="{{ stock_count }}" data-format="number">0</div>
```

**Updated JavaScript animation** to respect the format:
```javascript
const format = el.getAttribute('data-format') || 'currency';
const isCurrency = format === 'currency';

// Display with or without "MK " based on format
el.textContent = isCurrency ? ('MK ' + value) : value;
```

### 3. Added Comprehensive Tests
**File:** `tests/test_dashboard_charts.py`

Created 11 comprehensive tests covering:
- ✅ APIs return HTTP 200 with valid JSON even with NO sales
- ✅ APIs include manager sales (not just agents)
- ✅ APIs scope correctly to current business
- ✅ Different period parameters work (today, week, month)
- ✅ Both metrics work (amount, count)
- ✅ Top models limited to 5 results

All tests pass: **11 passed, 0 failed**

## Expected Behavior After Fix

### When NO Sales Exist
- **Charts:** Show "📊 No sales data yet" or "📱 No models sold yet"
- **NOT:** "⚠️ Failed to load chart"

### When Sales Exist
- **Sales Trend Chart:** Line graph with daily sales for last 30 days
- **Top Models Chart:** Bar chart with top 5 selling models
- **Both charts include manager sales**

### Active Stock KPI
- **Shows:** "3" (plain number)
- **NOT:** "MK 3" (with currency)
- Subtitle shows "3 product SKUs" for clarity

## Files Modified

1. **dashboard/views.py**
   - Rewrote `v2_sales_trend_data_proxy()` 
   - Rewrote `v2_top_models_data_proxy()`
   - Added CharField import

2. **templates/dashboard/home.html**
   - Added `data-format` attributes to stat cards
   - Updated animation JavaScript to respect format

3. **tests/test_dashboard_charts.py** (NEW)
   - 11 comprehensive tests
   - Fixtures for business, products, users
   - Tests for both chart APIs

## Testing

### Automated Tests
```bash
python -m pytest tests/test_dashboard_charts.py -v
# Result: 11 passed, 0 failed
```

### Manual Testing Checklist
1. ✅ Start dev server: `python manage.py runserver`
2. ✅ Go to `/dashboard/` as a manager
3. ✅ With NO sales:
   - Both charts show "No data yet" messages
   - Active Stock shows plain number (e.g., "3")
4. ✅ Create some sales (use scan & sell)
5. ✅ Refresh `/dashboard/`:
   - Sales Trend shows line graph
   - Top Models shows bar chart
   - Active Stock still shows plain number

## Technical Details

### Chart Data Flow
```
Browser (/dashboard/)
    ↓ fetch('/dashboard/api/sales-trend/')
dashboard/urls.py → sales_trend_v2
    ↓
dashboard/views.py → v2_sales_trend_data_proxy
    ↓ Query InventoryItem directly
    ↓ Use SOLD_Q() + _scope_queryset()
    ↓ Group by date, fill missing days
    ↓ Return {labels: [...], values: [...]}
Browser renders Chart.js line graph
```

### Business Scoping
```python
# 1. Try request.business (set by @require_business middleware)
business = getattr(request, "business", None)

# 2. Fallback to session (for tests and edge cases)
if not business and 'active_business_id' in request.session:
    business = Business.objects.get(id=request.session['active_business_id'])

# 3. Return empty if no business
if not business:
    return JsonResponse({"labels": [], "values": []})
```

## Why This Works

1. **Consistency:** Charts now use same data source (InventoryItem) as KPIs
2. **Completeness:** Include ALL sales (manager + agents)
3. **Reliability:** Handle edge cases (no sales, no business, errors)
4. **Clarity:** Distinguish between currency and count in UI
5. **Testability:** Comprehensive tests prevent regressions

## Notes

- The old `inventory/api_sales_metrics.py` (Sale-based) is still available for other parts of the app
- The dashboard now uses InventoryItem-based APIs for consistency
- Frontend error handling already existed; we just needed working APIs
- Tests ensure the fix doesn't break in future

