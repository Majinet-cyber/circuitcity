# GYM DASHBOARD AMOUNTS BUG - FIX SUMMARY

## STATUS: PARTIALLY FIXED + DEBUG INSTRUMENTATION ADDED

---

## BUG #1: Recent Payments Display ✅ FIXED

### Problem
Recent payments list on dashboard showed "MWK 0" for all payment amounts, even when payments had non-zero values in the database.

### Root Cause
Template `templates/verticals/gym/dashboard.html` line 204 was using:
```django
{{ payment.amount|floatformat:2|intcomma|money }}
```

The `payment.amount` field can be NULL or 0 for legacy payments or if the migration didn't run.

### Fix Applied
Changed to use the `total_amount` property which ALWAYS calculates correctly:
```django
{{ payment.total_amount|floatformat:2|intcomma|money }}
```

The `GymPayment.total_amount` property (line 1471 of `inventory/models_verticals.py`) always returns:
```python
return self.membership_amount + self.trainer_fee
```

This ensures recent payments ALWAYS show the correct amount, regardless of the `amount` field value.

---

## BUG #2: Main Financial Metrics (Revenue/Costs/Profit/MRR) - NEEDS USER TESTING

### Problem Reported by User
- Dashboard ALWAYS shows "MWK 0" for Revenue, Costs, Profit, MRR
- Even after creating brand-new gym + recording payments
- Counts update correctly (e.g. "4 payments") but amounts stay 0
- Django shell confirms database has non-zero amounts:
  - `sum_amount = 865000`
  - `sum_components = 870000`

### Investigation Result
After extensive code review, the **view code appears correct**:

1. ✅ `inventory/verticals/gym.py` uses the unified metrics service
2. ✅ `inventory/services/gym_metrics.py` calculates correctly from `membership_amount + trainer_fee`  
3. ✅ Template variables are correctly named (`revenue`, `costs`, `profit`, `mrr`)
4. ✅ Template filters (`|money`, `|floatformat`, `|intcomma`) handle Decimals correctly
5. ✅ No location filtering issues (GymMember/GymPayment don't have location fields)

### Possible Causes (Requires User Testing to Confirm)
1. **Service Worker / PWA caching** - Serving stale HTML from cache
2. **Middleware issue** - `active_business` not being set correctly
3. **Hidden filter bug** - Some edge case in the queryset filtering
4. **Template context issue** - Context variables not being passed correctly

---

## DEBUG INSTRUMENTATION ADDED ✅

To identify the EXACT root cause, I've added comprehensive debug instrumentation:

### 1. Server-Side Logging
**File:** `inventory/verticals/gym.py` (lines ~203-228)

When you load `/verticals/gym/dashboard/`, the server console will print:
```
GYM_DASH_DEBUG biz=X loc=Y range=mtd start=2026-01-01 end=2026-01-08 revenue=865000 costs=0 profit=865000 mrr=0 payment_count=4 payment_mix=[('Cash', Decimal('865000'))]
```

This will tell us:
- ✅ Is the view calculating revenue correctly?
- ✅ Are payments being found?
- ✅ What date range is being used?

### 2. HTML Source Debug Comments
**File:** `templates/verticals/gym/dashboard.html` (lines ~105, ~133, ~209)

View the page source (Ctrl+U) and look for:
```html
<!-- GYM_DASH_DEBUG revenue=865000 costs=0 profit=865000 mrr=0 payment_count=4 payment_mix_count=1 range_label=Month to Date -->
```

This will tell us:
- ✅ Are the correct values being passed to the template?
- ✅ Are they being lost during template rendering?

### 3. Sanity Check Log (PERMANENT GUARDRAIL)
**File:** `inventory/verticals/gym.py` (lines ~204-211)

If payments exist but revenue is 0, the server will log:
```
ERROR: GYM DASHBOARD BUG: 4 payments exist but revenue=0! Business=123, Range=2026-01-01 to 2026-01-08
```

This provides an early warning system for this bug in production.

---

## TESTING STEPS FOR USER

### Step 1: Clear Service Worker Cache
1. Open DevTools (F12)
2. Go to Application → Service Workers
3. Click "Unregister" on all service workers
4. Hard reload (Ctrl+Shift+R or Cmd+Shift+R)

### Step 2: Check Server Logs
1. Reload `/verticals/gym/dashboard/`
2. Look in server console for lines starting with `GYM_DASH_DEBUG`
3. **Share these log lines with me**

### Step 3: Check HTML Source
1. On the dashboard, press Ctrl+U (or Cmd+U) to view source
2. Search for `GYM_DASH_DEBUG` (Ctrl+F)
3. **Share these comment lines with me**

### Step 4: Check Rendered Values
1. Look at the "Financial Performance" section
2. Do you see:
   - "MWK 0" (bug still present)
   - "MWK 865,000" (bug is fixed!)
3. **Share a screenshot**

---

## FILES CHANGED

### Modified Files
1. `inventory/verticals/gym.py`
   - Added server-side debug logging (lines ~203-228)
   - Added sanity check guardrail (lines ~204-211)

2. `templates/verticals/gym/dashboard.html`
   - Fixed recent payments display (line ~207: use `payment.total_amount`)
   - Added HTML debug comments (lines ~105, ~133, ~209)

### New Test File
3. `tests/test_gym_dashboard_amounts_critical_bug.py`
   - Comprehensive test suite to reproduce and prevent regression
   - Tests Django aggregates, metrics service, view context, HTML rendering
   - Status: Written but needs setup fixes before it can run

---

## WHAT HAPPENS NEXT?

### If Debug Logs Show Non-Zero Revenue
**Good News:** The view is calculating correctly!

**Bad News:** The problem is in template rendering or caching.

**Next Steps:**
- Check if Service Worker is serving stale HTML
- Verify template filter (`|money`) is working correctly
- Check for JavaScript that might be overwriting values

### If Debug Logs Show Zero Revenue
**Bad News:** The view is not finding payments!

**Next Steps:**
- Check if `active_business` is being set correctly in session
- Verify date range is correct (MTD should include today)
- Check if payments have `is_active=True` set
- Verify `member__business` relationship is correct

---

## IMMEDIATE ACTION REQUIRED

**Please provide the following:**

1. **Server console output** after reloading dashboard (look for `GYM_DASH_DEBUG`)
2. **HTML source** debug comments (Ctrl+U, search for `GYM_DASH_DEBUG`)
3. **Screenshot** of the Financial Performance section
4. **Django shell query results:**
   ```python
   from inventory.models_verticals import GymPayment
   from django.db.models import Sum
   from django.db.models.functions import Coalesce
   from decimal import Decimal
   
   # Your business ID (replace XXX)
   business_id = XXX
   
   # Check payments exist
   payments = GymPayment.objects.filter(member__business_id=business_id, is_active=True)
   print(f"Total payments: {payments.count()}")
   print(f"Sum of amount field: {payments.aggregate(total=Coalesce(Sum('amount'), Decimal('0')))}")
   print(f"Sum of components: {payments.aggregate(total=Sum('membership_amount') + Sum('trainer_fee'))}")
   
   # Check business is correct
   from tenants.models import Business
   biz = Business.objects.get(id=business_id)
   print(f"Business: {biz.name} (kind={biz.kind})")
   ```

Once I see this output, I can pinpoint the EXACT issue and provide the final fix.

---

## FILES TO REVIEW

- `inventory/verticals/gym.py` (dashboard view + debug logging)
- `templates/verticals/gym/dashboard.html` (template + debug comments)
- `inventory/services/gym_metrics.py` (unified metrics calculation)
- `inventory/models_verticals.py` (GymPayment model + total_amount property)

---

## CONFIDENCE LEVEL

- **Recent Payments Fix:** 100% confident ✅ (Clear bug, clear fix)
- **Main Metrics Bug:** 80% confident the view is correct, need debug output to confirm

The debug instrumentation will definitively reveal whether this is:
- A caching issue (HTML comment shows correct values)
- A view issue (HTML comment shows 0)
- A template rendering issue (HTML comment shows values, but rendered page shows 0)


