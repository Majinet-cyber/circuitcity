# Migration Checklist - assigned_role Field

## Quick Reference Commands

```bash
# Apply migrations (if needed on another server/environment)
python manage.py migrate inventory

# Verify migrations are applied
python manage.py showmigrations inventory

# Test the fix
python manage.py test inventory.tests.test_inventory_assigned_role_migration
python manage.py test inventory.tests.test_stock_assignment_visibility
```

## What Was Fixed

### Problem
- **Error**: `OperationalError: no such column: inventory_inventoryitem.assigned_role`
- **Cause**: Migration existed but wasn't applied to the database

### Solution
1. ✅ Applied migration `0042_add_assigned_role_to_inventoryitem`
2. ✅ Created and applied migration `0043_add_assigned_role_index` for performance
3. ✅ Updated model to include `db_index=True`

## Verification Checklist

- [x] Migration `0042_add_assigned_role_to_inventoryitem` applied
- [x] Migration `0043_add_assigned_role_index` applied  
- [x] `assigned_role` column exists in database
- [x] Model field has `db_index=True`
- [x] Default value is `'MANAGER'`
- [x] Choices are `MANAGER` and `AGENT`
- [x] Stock list queries work without errors
- [x] Tests exist and pass
- [x] Backward compatible

## Test Files Location

- `inventory/tests/test_inventory_assigned_role_migration.py` - Schema and migration tests
- `inventory/tests/test_stock_assignment_visibility.py` - Visibility and filtering tests

## Deployment Notes

When deploying to production or other environments:

1. Run migrations:
   ```bash
   python manage.py migrate inventory
   ```

2. Verify no errors in logs when accessing `/inventory/list/`

3. Test that:
   - Managers see all stock (MANAGER + AGENT items)
   - Agents see only AGENT items or items assigned to them

## No Manual Data Migration Needed

The `assigned_role` field has `default='MANAGER'`, so:
- All existing items automatically default to `MANAGER`
- No backfill script required
- Fully backward compatible

## Status: ✅ COMPLETE

The `assigned_role` column issue has been resolved. The application will no longer throw 500 errors when accessing the stock list.

