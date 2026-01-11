# Migration Fix Deployment Guide

## Summary of Changes

This deployment fixes critical migration issues that were preventing successful deploys on Render:

### Issues Fixed
1. **InconsistentMigrationHistory in tenants app**: Migration dependency order issue with 0019/0020/0021
2. **DuplicateColumn error in inventory app**: Migration 1012 tried to add columns that already existed

### Solution Approach
- **Tenants**: Renamed `0019_fix_cement_business_kind.py` → `0019a_fix_cement_business_kind.py` to establish correct dependency order
- **Inventory**: Made migration 1012 idempotent using `SeparateDatabaseAndState` and `ADD COLUMN IF NOT EXISTS`
- **Safety**: All changes are safe for both fresh databases and existing production/staging databases

---

## Pre-Deployment Checklist

Run these commands locally BEFORE pushing to Render:

```bash
# 1. Verify no unapplied model changes
python manage.py makemigrations --check --dry-run

# 2. Check migration plan
python manage.py migrate --plan

# 3. Run comprehensive migration checks
python bin/check_migrations.py
```

---

## Deployment Steps

### For Existing Databases (Production/Staging)

**IMPORTANT**: If deploying to an existing database that already has migrations applied, you MUST run the migration rename fix first.

#### Step 1: Run the Migration Rename Fix

Before deploying, run this one-time script to update the migration history:

```bash
python bin/fix_migration_rename.py
```

This script:
- Updates the `django_migrations` table to rename `0019_fix_cement_business_kind` → `0019a_fix_cement_business_kind`
- Is idempotent (safe to run multiple times)
- Does NOT modify any data or schema
- Only updates migration tracking records

**On Render**: You can run this via the Shell tab:
1. Open your Render service → Shell tab
2. Run: `python bin/fix_migration_rename.py`
3. Wait for "[OK] Successfully updated migration record!"

#### Step 2: Deploy the Code

Push the code to your repository:

```bash
git add .
git commit -m "Fix migration issues: InconsistentMigrationHistory and DuplicateColumn"
git push origin main
```

#### Step 3: Verify Migrations Run Successfully

After Render deploys:
- Check build logs for `python manage.py migrate --noinput`
- Should see: "Operations to perform: Apply all migrations..."
- Should complete with no errors

---

### For Fresh Databases (New Environments)

No special steps needed! The migrations are now idempotent and will work correctly:

```bash
python manage.py migrate --noinput
```

---

## What Changed - Technical Details

### Files Modified

#### Tenants App
- **Renamed**: `0019_fix_cement_business_kind.py` → `0019a_fix_cement_business_kind.py`
  - Fixed dependency order (now depends on 0019_add_section_flags_with_defaults)
- **Modified**: `0020_merge_20250105_1200.py`
  - Updated dependency to reference `0019a_fix_cement_business_kind`
- **Added**: `0024_reconcile_0019a_rename.py`
  - Reconciliation migration (runs automatically on existing DBs)

#### Inventory App
- **Modified**: `1012_add_cementsale_total_price_and_cost.py`
  - Now uses idempotent SQL (`ADD COLUMN IF NOT EXISTS`)
  - Uses `SeparateDatabaseAndState` to handle existing columns
  - Safe to run on DBs where columns already exist

#### New Tools
- **bin/fix_migration_rename.py**: One-time script for existing databases
- **bin/check_migrations.py**: Pre-deployment verification script
- **tenants/management/commands/verify_migrations.py**: Django command for migration checks
- **tests/test_migrations.py**: Automated migration consistency tests

---

## Troubleshooting

### Error: "InconsistentMigrationHistory: tenants.0020_merge_20250105_1200 is applied before its dependency"

**Solution**: Run the migration rename fix script:
```bash
python bin/fix_migration_rename.py
```

### Error: "DuplicateColumn: column 'total_price' of relation 'inventory_cementsale' already exists"

**Solution**: This should be fixed by the idempotent migration. If you still see this:
1. Check that you've deployed the latest code
2. The migration should handle existing columns automatically

### Error: "Migration X is unapplied but depends on Y which is applied"

**Solution**: Check migration order:
```bash
python manage.py showmigrations
python manage.py migrate --plan
```

---

## Verification Commands

After deployment, verify everything is working:

```bash
# Check no pending migrations
python manage.py showmigrations | grep "[ ]"

# Verify migration history
python manage.py migrate --plan

# Run migration tests
python manage.py test tests.test_migrations -v 2

# Run full verification
python bin/check_migrations.py
```

---

## Render Build Command

The build command should remain:
```bash
python manage.py migrate --noinput
```

No changes needed to the build script!

---

## Rollback Plan

If you need to rollback:

### Option 1: Rollback Code (Safe)
```bash
git revert <commit-hash>
git push origin main
```

### Option 2: Rollback Specific Migration (Advanced)
```bash
# Rollback tenants to before reconciliation
python manage.py migrate tenants 0023_add_currency_field

# Rollback inventory to before 1012
python manage.py migrate inventory 1011_pharmacy_packaging_fields
```

**Note**: Rolling back migrations may require manual intervention. Contact the development team before rolling back.

---

## Contact

If you encounter issues during deployment:
1. Check build logs on Render
2. Run verification commands above
3. Contact the development team with:
   - Error messages from build logs
   - Output of `python manage.py showmigrations`
   - Output of `python bin/check_migrations.py`

---

## Known Safe to Ignore

The verification script may report these pre-existing issues (safe to ignore):
- Duplicate migration numbers in inventory app (0040, 0042, 0054) - these have merge migrations
- Duplicate payment_method field additions in GymPayment - handled by merge migrations

These don't affect deployment and were present before this fix.

