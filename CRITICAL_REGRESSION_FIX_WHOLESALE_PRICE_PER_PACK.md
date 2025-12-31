# CRITICAL REGRESSION FIX — "no such column: inventory_merchproduct.wholesale_price_per_pack"

**Date:** December 31, 2025  
**Status:** ✅ RESOLVED  
**Impact:** Pharmacy dashboard crash, Groceries V2 features broken

---

## Problem Summary

The Django model `MerchProduct` included fields for Groceries V2 functionality:
- `wholesale_price_per_pack` (DecimalField, nullable)
- `track_expiry` (BooleanField)
- `category_group` (CharField)

However, the database table `inventory_merchproduct` was **missing these columns** because:
1. Migration `0101_add_groceries_v2_fields.py` was **corrupted** (file contained only null bytes)
2. This caused ANY query touching MerchProduct to crash with: `OperationalError: no such column: inventory_merchproduct.wholesale_price_per_pack`
3. Affected multiple verticals, not just Groceries (e.g., Pharmacy dashboard)

---

## Root Cause

- Migration file `inventory/migrations/0101_add_groceries_v2_fields.py` was corrupted (all null bytes)
- Migration was never applied, so database schema was out of sync with model definitions
- Any code accessing these fields would crash with "no such column" errors

---

## Solution Implemented

### Step 1: Delete Corrupted Migration
- Removed corrupted `0101_add_groceries_v2_fields.py` file

### Step 2: Create Fresh Migrations
Created two new migrations with proper field definitions:

**Migration 0101** (`inventory/migrations/0101_add_groceries_v2_fields.py`):
```python
operations = [
    migrations.AddField(
        model_name='merchproduct',
        name='wholesale_price_per_pack',
        field=models.DecimalField(
            blank=True,
            decimal_places=2,
            help_text='Wholesale price per pack (carton/bale/bundle). If null, derived from retail price * pack_size',
            max_digits=10,
            null=True
        ),
    ),
    migrations.AddField(
        model_name='merchproduct',
        name='track_expiry',
        field=models.BooleanField(
            default=False,
            help_text='Track expiry dates for this product (optional for groceries)'
        ),
    ),
]
```

**Migration 0102** (`inventory/migrations/0102_add_category_group.py`):
```python
operations = [
    migrations.AddField(
        model_name='merchproduct',
        name='category_group',
        field=models.CharField(
            blank=True,
            default='',
            help_text='Category group for groceries UI tiles (drinks, water, snacks, etc.)',
            max_length=30
        ),
    ),
]
```

### Step 3: Apply Migrations
```bash
python manage.py migrate inventory
```

**Result:**
```
Applying inventory.0100_clothing_premium_upgrade... OK
Applying inventory.0101_add_groceries_v2_fields... OK
Applying inventory.0102_add_category_group... OK
```

---

## Verification

### ✅ Database Columns Created
```python
# Verified all columns exist in inventory_merchproduct table
wholesale_price_per_pack: True
category_group: True
track_expiry: True
```

### ✅ Pharmacy Dashboard Loads
```
Status code: 200
✅ SUCCESS: Pharmacy dashboard loads without errors
```

### ✅ Groceries V2 Fields Accessible
```
1. Checking model fields...
  ✅ wholesale_price_per_pack exists
  ✅ category_group exists
  ✅ track_expiry exists

2. Testing field access on model instance...
  ✅ All fields accessible on model instance

3. Verifying database columns...
  ✅ wholesale_price_per_pack column exists in database
  ✅ category_group column exists in database
  ✅ track_expiry column exists in database

✅ SUCCESS: All Groceries V2 fields are properly migrated and accessible
```

---

## Migration Safety

### Backward Compatibility
- All fields are **nullable** or have **defaults**
- Old database rows remain valid after migration
- No data loss or corruption risk
- Safe to apply in production

### Field Specifications
1. **wholesale_price_per_pack**: `DecimalField(null=True, blank=True)` — optional wholesale pricing
2. **track_expiry**: `BooleanField(default=False)` — opt-in expiry tracking
3. **category_group**: `CharField(blank=True, default='')` — optional UI grouping

---

## Impact Assessment

### Affected Verticals
- ✅ **Pharmacy**: Dashboard now loads (was returning 500)
- ✅ **Groceries**: V2 features now functional
- ✅ **Liquor**: Unaffected
- ✅ **Clothing**: Unaffected
- ✅ **Gym**: Unaffected

### No Regressions
- All existing functionality preserved
- No changes to business logic
- No data modifications

---

## Deployment Checklist

### Local Development
- [x] Delete corrupted migration
- [x] Create new migrations (0101, 0102)
- [x] Apply migrations locally
- [x] Verify pharmacy dashboard loads
- [x] Verify groceries V2 fields accessible
- [x] Test no regressions in other verticals

### Production Deployment
- [ ] Pull latest code with new migrations
- [ ] Run `python manage.py migrate inventory` **before** starting web server
- [ ] Verify pharmacy dashboard loads (no 500 errors)
- [ ] Monitor logs for any "no such column" errors
- [ ] Confirm groceries V2 features work

---

## Prevention

### For Future Deployments
1. **Always run migrations after pull/deploy** before starting the web server
2. **Check migration file integrity** before committing (ensure not corrupted/binary)
3. **Test migrations in staging** before production
4. **Monitor for "no such column" errors** in production logs

### Deployment Script Template
```bash
#!/bin/bash
# Safe deployment script
git pull origin main
python manage.py migrate  # Run BEFORE starting server
python manage.py collectstatic --noinput
# Restart web server
```

---

## Files Changed

### New Migrations
- `inventory/migrations/0101_add_groceries_v2_fields.py` (recreated)
- `inventory/migrations/0102_add_category_group.py` (new)

### No Model Changes
- `inventory/models.py` — unchanged (fields already existed)

---

## Done Criteria

✅ `python manage.py migrate inventory` succeeds  
✅ Pharmacy dashboard loads (no 500)  
✅ Groceries V2 still works  
✅ Liquor/Pharmacy/Clothing unaffected  
✅ No regressions introduced  

---

## Conclusion

**Critical regression fixed successfully.** The missing database columns for Groceries V2 fields have been added via proper migrations. All verticals now function correctly, with zero regressions.

**Action Required:** Deploy these migrations to production **immediately** to restore pharmacy dashboard functionality.

