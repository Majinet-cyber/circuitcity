# Fix for OperationalError: no such column: inventory_merchproduct.size

**Date:** December 6, 2025  
**Issue:** Clothing dashboard fails with `django.db.utils.OperationalError: no such column: inventory_merchproduct.size`  
**Root Cause:** Migration `0045_clothing_cost_tracking.py` exists but hasn't been applied to the database yet.

---

## Problem Analysis

### Error Traceback
```
File "circuitcity_clean\inventory\verticals\clothing.py", line 31, in dashboard
    metrics = base.merch_metrics(business, BusinessKind.CLOTHING)

File "circuitcity_clean\inventory\verticals\base.py", line 96, in merch_metrics
    recent = list(qs.order_by("-id")[:recent_limit])

django.db.utils.OperationalError: no such column: inventory_merchproduct.size
```

### Case Determination: **CASE A**

The `MerchProduct` model **DOES** have a `size` field defined:
- Location: `inventory/models.py`, line 249
- Definition: `size = models.CharField(max_length=20, blank=True, default='', help_text="Size for clothing items")`

The database schema is **behind** the code because the migration hasn't been applied yet.

---

## Solution

### Migration Already Exists ✅

Migration `inventory/migrations/0045_clothing_cost_tracking.py` already exists and includes:

1. **`size` field** (lines 53-62) - CharField(max_length=20, blank=True, default='')
2. **`color` field** (lines 64-72) - CharField(max_length=50, blank=True, default='')
3. **`quantity_in_stock` field** (lines 75-82) - PositiveIntegerField(default=0)
4. **`cost_price` field** (lines 85-95) - DecimalField (nullable)
5. **`selling_price` field** (lines 96-106) - DecimalField (nullable)

All fields use **safe defaults** ensuring backward compatibility with existing liquor, grocery, and pharmacy products.

### Migration Dependencies ✅

- Depends on: `0044_gym_membership_enhancements`
- Depended on by: `0046_rename_gymcheckin_biz_ts_idx_inventory_g_busines_72ef0c_idx_and_more`
- Migration chain is **intact** and **correct**

---

## Action Required

You must apply the existing migration to your database:

```powershell
cd "C:\Users\CHRIS PAUL MWALE\PycharmProjects\circuitcity_clean"
python manage.py migrate inventory
```

This will add the missing columns to the `inventory_merchproduct` table.

---

## Expected Outcome

After running the migration:

1. ✅ The `inventory_merchproduct` table will have the `size` column
2. ✅ The clothing dashboard at `/verticals/clothing/dashboard/` will load successfully
3. ✅ The `base.merch_metrics()` function will execute without errors
4. ✅ All existing data remains intact (backward compatible)

---

## Files Involved

### No Changes Needed
All necessary changes are already in place:

- ✅ **Model:** `inventory/models.py` - `size` field already defined (line 249)
- ✅ **Migration:** `inventory/migrations/0045_clothing_cost_tracking.py` - already exists
- ✅ **Views:** `inventory/verticals/clothing.py` - uses the size field correctly (line 333)
- ✅ **Base utilities:** `inventory/verticals/base.py` - queries work fine once migration applied

### No Code Changes Required
The code is already correct and ready. Only the database schema needs to be updated by running the migration.

---

## Verification Steps

After running `python manage.py migrate`:

1. Start the development server:
   ```powershell
   python manage.py runserver
   ```

2. Visit the clothing dashboard:
   ```
   http://127.0.0.1:8000/verticals/clothing/dashboard/
   ```

3. Verify no `OperationalError` occurs

4. Check that metrics display correctly (total products, active products, recent products, etc.)

---

## Notes

- **No database reset needed** ✅
- **No migration deletion needed** ✅
- **Backward compatible** ✅ (all new fields have safe defaults)
- **Other verticals unaffected** ✅ (liquor, phones, gym remain unchanged)
- **Existing tests remain passing** ✅ (no test modifications needed)

The migration uses `blank=True` and `default=''` for the `size` field, ensuring it applies safely to existing `MerchProduct` records for other verticals (liquor, grocery, etc.) without requiring data migration.
