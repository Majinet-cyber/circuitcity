# Fix for: django.db.utils.OperationalError: no such column: inventory_merchproduct.size

## Problem
The clothing dashboard at `/verticals/clothing/dashboard/` was failing with:
```
django.db.utils.OperationalError: no such column: inventory_merchproduct.size
```

This occurred when `merch_metrics(business, BusinessKind.CLOTHING)` tried to query the `MerchProduct` table.

## Root Cause
The `MerchProduct` model defines a `size` field (line 249 in `inventory/models.py`), but the database table `inventory_merchproduct` doesn't have this column because migration `0045_clothing_cost_tracking.py` hasn't been applied yet.

## Solution
Migration `0045_clothing_cost_tracking.py` already exists and includes the necessary schema changes:
- Adds `size` field: `CharField(max_length=20, blank=True, default='')`
- Adds `color` field: `CharField(max_length=50, blank=True, default='')`
- Adds `quantity_in_stock` field: `PositiveIntegerField(default=0)`
- Adds `cost_price` field: `DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)`
- Adds `selling_price` field: `DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)`

All fields use safe defaults (`blank=True`, `default=''` or `default=0`) ensuring backward compatibility.

## Required Action
Run the following commands from the project root:

```bash
cd "C:\Users\CHRIS PAUL MWALE\PycharmProjects\circuitcity_clean"
python manage.py migrate inventory
```

This will apply migration `0045_clothing_cost_tracking.py` and add the missing columns to the database.

## Verification Steps
After running the migration:

1. **Verify migration applied successfully:**
   ```bash
   python manage.py showmigrations inventory
   ```
   You should see `[X] 0045_clothing_cost_tracking`

2. **Test the clothing dashboard:**
   - Start the server: `python manage.py runserver`
   - Navigate to: `http://localhost:8000/verticals/clothing/dashboard/`
   - The page should load without database errors

3. **Run the test suite:**
   ```bash
   python manage.py test inventory.tests.test_clothing_premium
   ```

## Impact Assessment
- **Phones vertical:** ✅ No impact (uses separate `Product` model)
- **Liquor vertical:** ✅ No impact (fields are optional, default='')
- **Grocery/Pharmacy:** ✅ No impact (fields are optional, default='')
- **Clothing vertical:** ✅ Fixed - can now properly store size/color data

## What Changed
- ✅ Migration already exists: `inventory/migrations/0045_clothing_cost_tracking.py`
- ✅ Model fields already defined: `inventory/models.py` lines 249-254
- ✅ Test added: `inventory/tests/test_merch_product_size.py`
- ✅ Documentation created: This file

## Safety Notes
- All new fields are **nullable** or have **safe defaults**
- No existing data is modified or deleted
- Migration is **additive only** (no drops, no renames)
- Backward compatible with all existing verticals
- No code changes required - pure schema alignment

## Next Steps
1. Run `python manage.py migrate inventory`
2. Test the clothing dashboard
3. If successful, delete this summary file

