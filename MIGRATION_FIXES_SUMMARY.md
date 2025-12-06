# Migration Dependency Fixes - Summary

**Date:** December 6, 2025  
**Issue:** NodeNotFoundError preventing migrations and server startup  
**Status:** ✅ RESOLVED

---

## Problem

The application was encountering `NodeNotFoundError` when attempting to run migrations or start the development server:

```
django.db.migrations.exceptions.NodeNotFoundError:
Migration tenants.0004_add_location_tracking dependencies reference
nonexistent parent node ('tenants', '0003_auto_20250101_0000')
```

Additionally, a similar issue existed in the `sales` app.

### Root Cause

**Duplicate Migration Numbers**: Multiple migrations were created with the same number in both the `tenants` and `sales` apps, with some referencing non-existent parent migrations.

#### Tenants App:
- ❌ `0004_add_location_tracking.py` → depended on `0003_auto_20250101_0000` (doesn't exist)
- ✅ `0004_agentinvite.py` → depended on `0003_alter_membership_role_and_more` (valid)

#### Sales App:
- ❌ `0003_update_default_commission_to_12pct.py` → depended on `0002_add_payment_method_and_penalties` (doesn't exist)
- ✅ `0003_backfill_sale_created_and_item_sold_at.py` → depended on `0002_alter_sale_options_sale_created_at_and_more` (valid)

---

## Solution

### 1. Fixed Tenants Migrations

**Action:** Renumbered and fixed dependencies

- **Deleted:** `tenants/migrations/0004_add_location_tracking.py`
- **Created:** `tenants/migrations/0013_add_location_tracking.py`
  - Updated dependency from `('tenants', '0003_auto_20250101_0000')` → `('tenants', '0012_add_business_logo')`
  - Added comment explaining the fix

### 2. Fixed Sales Migrations

**Action:** Renumbered and fixed dependencies

- **Deleted:** `sales/migrations/0003_update_default_commission_to_12pct.py`
- **Created:** `sales/migrations/0007_update_default_commission_to_12pct.py`
  - Updated dependency from `('sales', '0002_add_payment_method_and_penalties')` → `('sales', '0006_update_commission_default')`
  - Added comment explaining the fix

### 3. Applied Migrations

All pending migrations applied successfully:

```
✅ notifications.0003_add_category_and_business
✅ sales.0006_update_commission_default
✅ sales.0007_update_default_commission_to_12pct
✅ tenants.0013_add_location_tracking
```

### 4. Added Safety Tests

Created `tests/test_migrations_graph.py` with two protective tests:

1. **`test_migration_graph_is_consistent()`**
   - Validates Django can build the migration graph without errors
   - Catches invalid dependencies pointing to non-existent migrations
   - Will fail in CI if migration dependencies are broken

2. **`test_no_duplicate_migration_numbers()`**
   - Detects migrations with duplicate numbers in the same app
   - Prevents the root cause from happening again

---

## Verification

### ✅ Migrations Valid

```bash
python manage.py showmigrations
# Exit code: 0 (no errors)
```

### ✅ Migrations Applied

```bash
python manage.py migrate
# All migrations applied successfully
```

### ✅ Tests Pass

```bash
pytest tests/test_migrations_graph.py -v
# 2 passed
```

### ✅ System Check Clean

```bash
python manage.py check
# System check identified no issues (0 silenced)
```

### ✅ Smoke Tests Pass

```bash
pytest tests/test_smoke.py -v
# 3 passed
```

---

## Current Migration State

### Tenants (13 migrations)
```
[X] 0001_initial
[X] 0002_alter_business_options_alter_membership_options_and_more
[X] 0003_alter_membership_role_and_more
[X] 0004_agentinvite
[X] 0005_agentinvite_expires_at_agentinvite_invited_name_and_more
[X] 0006_agentinvite_location_membership_location
[X] 0007_alter_membership_unique_together_and_more
[X] 0008_membership_location_and_defaults
[X] 0009_remove_old_business_indexes
[X] 0010_business_business_kind
[X] 0011_agentinvite_temp_password_hash_and_more
[X] 0012_add_business_logo
[X] 0013_add_location_tracking  ← FIXED & APPLIED
```

### Sales (7 migrations)
```
[X] 0001_initial
[X] 0002_alter_sale_options_sale_created_at_and_more
[X] 0003_backfill_sale_created_and_item_sold_at
[X] 0004_commissionconfig_salecommission
[X] 0005_add_payment_method_and_penalties
[X] 0006_update_commission_default  ← APPLIED
[X] 0007_update_default_commission_to_12pct  ← FIXED & APPLIED
```

---

## Prevention Strategy

The new test suite (`tests/test_migrations_graph.py`) will catch these issues before they reach production:

1. **In Development:** Run `pytest tests/test_migrations_graph.py` before committing migrations
2. **In CI/CD:** The test will fail if anyone introduces broken migration dependencies
3. **Best Practice:** Always run `python manage.py showmigrations` after creating new migrations

---

## Files Changed

### Created
- ✅ `tenants/migrations/0013_add_location_tracking.py` (renumbered from 0004)
- ✅ `sales/migrations/0007_update_default_commission_to_12pct.py` (renumbered from 0003)
- ✅ `tests/test_migrations_graph.py` (new safety tests)
- ✅ `MIGRATION_FIXES_SUMMARY.md` (this document)

### Deleted
- ❌ `tenants/migrations/0004_add_location_tracking.py` (invalid dependency)
- ❌ `sales/migrations/0003_update_default_commission_to_12pct.py` (invalid dependency)

### Modified
- None (no existing migrations were altered - all fixes were surgical)

---

## Impact

### ✅ Zero Downtime
- No database reset required
- No data loss
- All existing migrations remain valid

### ✅ Backward Compatible
- Existing applied migrations unchanged
- New migrations build on top of existing chain
- Works with current database state

### ✅ Future-Proof
- Tests prevent recurrence
- Clear documentation of fix
- Proper migration numbering restored

---

## Next Steps

1. **Run the dev server** to verify everything works:
   ```bash
   python manage.py runserver
   ```

2. **Test key pages:**
   - `/inventory/list/`
   - `/dashboard/`
   - `/tenants/invites/` (uses new location tracking fields)
   - `/sales/` (uses commission config)

3. **Monitor for issues** with location tracking and commission calculations

4. **Keep the tests** - they're now part of the test suite and will run in CI

---

## Conclusion

The migration dependency issues have been **completely resolved** with:
- ✅ No database reset
- ✅ No data loss
- ✅ Surgical fixes only
- ✅ Future protection via tests
- ✅ Full backward compatibility

The application is now stable and migrations work cleanly.

