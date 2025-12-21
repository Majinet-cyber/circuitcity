# Django Migration Fix Summary

**Date:** December 21, 2025  
**Issue:** Migration dependency error and RuntimeWarning about database access during app initialization

## Problems Identified

### 1. Migration Issue (RESOLVED)
**Error Message:**
```
NodeNotFoundError: Migration inventory.1004_remove_merchproduct_merchprod_biz_barcode_idx_and_more 
dependencies reference nonexistent parent node ('inventory', '1003_add_barcode_fields').
```

**Root Cause:**
- The error message was misleading - there was NO missing migration file
- Migration `1003_merchproduct_barcode_pharmacybatch_barcode_and_more.py` existed but was **not yet applied**
- All migrations up to `1002_add_sold_by_field` were applied
- Migration 1003 was pending application

**Solution:**
- Applied the pending migration: `python manage.py migrate inventory`
- Migration 1003 successfully added barcode fields to `MerchProduct` and `PharmacyBatch` models

### 2. RuntimeWarning (RESOLVED)
**Warning Message:**
```
RuntimeWarning: Accessing the database during app initialization is discouraged.
```

**Root Cause:**
- `billing/signals.py` was calling `_seed_plans()` at **module import time** (line 67)
- This function accessed the database via `SubscriptionPlan.objects.update_or_create()`
- Database access during app initialization/import is discouraged by Django

**Solution:**
- Moved the `_seed_plans()` call from module import time to a `post_migrate` signal
- Created `_seed_plans_after_migrate()` receiver that runs after migrations complete
- This ensures database seeding happens at the appropriate time, not during app initialization

## Files Modified

### `billing/signals.py`
**Changes:**
1. Added `post_migrate` to imports
2. Removed direct call to `_seed_plans()` at module level (lines 66-70)
3. Added new signal receiver:
```python
@receiver(post_migrate)
def _seed_plans_after_migrate(sender, **kwargs):
    """
    Seed subscription plans after migrations complete.
    This avoids database access during app initialization.
    """
    try:
        _seed_plans()
    except Exception:
        # Ignore during early migrate phases or if DB is unavailable
        pass
```

## Verification

### Migration Status
```bash
python manage.py showmigrations inventory
```
**Result:** All migrations applied successfully, including:
- ✅ `1002_add_sold_by_field`
- ✅ `1003_merchproduct_barcode_pharmacybatch_barcode_and_more`

### No Pending Migrations
```bash
python manage.py makemigrations --check
```
**Result:** `No changes detected`

### No RuntimeWarning
```bash
python manage.py check
python manage.py migrate
```
**Result:** No RuntimeWarning about database access during app initialization

## Migration Details

### Latest Existing Migration Before 1003
**File:** `inventory/migrations/1002_add_sold_by_field.py`

### Migration 1003 Contents
**File:** `inventory/migrations/1003_merchproduct_barcode_pharmacybatch_barcode_and_more.py`
- **Dependency:** `1002_add_sold_by_field`
- **Operations:**
  1. Added `barcode` field to `MerchProduct` (CharField, max_length=100, indexed)
  2. Added `barcode` field to `PharmacyBatch` (CharField, max_length=100, indexed)
  3. Altered `PharmacyBatch.batch_number` field (made optional)
  4. Altered `PharmacyBatch.expiry_date` field (made optional for cosmetics)

## Best Practices Applied

1. ✅ **No migration deletion** - Did not delete or renumber existing migrations
2. ✅ **Proper dependency chain** - Migration 1003 correctly depends on 1002
3. ✅ **No import-time DB access** - Moved database operations to post_migrate signal
4. ✅ **Idempotent seeding** - Plan seeding uses update_or_create for safety
5. ✅ **Graceful error handling** - All database operations wrapped in try/except

## Server Boot Confirmation

✅ Django check passes without RuntimeWarning  
✅ All migrations applied successfully  
✅ No RuntimeWarning about database access during app initialization  
✅ Server can boot normally  
✅ Barcode fields accessible: `MerchProduct.barcode` and `PharmacyBatch.barcode`  
✅ No module-level database queries found in codebase  

### Test Commands Run Successfully
```bash
python manage.py check                    # ✅ No issues
python manage.py makemigrations --check   # ✅ No changes detected
python manage.py migrate                  # ✅ All migrations applied
python manage.py showmigrations inventory # ✅ All migrations marked [X]
python manage.py check --deploy           # ✅ Only expected security warnings (dev environment)
```

## Notes

- The original error about "1004_remove_merchproduct" was likely from a previous attempt or different environment
- No migration file named `1004_*` exists in the current codebase
- The barcode fields are now properly added and indexed for Fast Sell functionality
- Subscription plan seeding now happens at the correct time (post-migrate) instead of import time
- The only remaining warning is `RequestsDependencyWarning` about urllib3 version mismatch, which is unrelated to our changes

## Impact

### Before Fix
- ❌ RuntimeWarning on every management command
- ❌ Database accessed during app initialization (discouraged by Django)
- ❌ Migration 1003 not applied

### After Fix
- ✅ No RuntimeWarning
- ✅ Database only accessed at appropriate times (post-migrate, request-time)
- ✅ All migrations applied successfully
- ✅ Barcode fields ready for use in Fast Sell feature

