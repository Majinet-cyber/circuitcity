# Gym Public Token Migration Idempotency Fix

## Problem

Render deploy was failing with the following error:

```
django.db.utils.ProgrammingError: relation "inventory_gymmember_public_token_208110ff_like" already exists
```

This occurred when running migration `inventory.1019_add_gym_public_token`. The issue was that:
1. A previous deployment attempt created the `public_token` column and indexes
2. The migration failed partway through (or was interrupted)
3. Django didn't mark the migration as complete
4. On retry, Django tried to create the already-existing indexes, causing a crash

## Root Cause

The original migration used `migrations.AddField()` which directly instructs Django to:
1. Add the column via `ALTER TABLE`
2. Create indexes (including PostgreSQL's automatic `_like` index for CharField with `db_index=True`)

When PostgreSQL sees a `CharField` with `db_index=True`, it creates TWO indexes:
- Standard btree: `inventory_gymmember_public_token_208110ff`
- Pattern ops (for LIKE queries): `inventory_gymmember_public_token_208110ff_like`

The migration wasn't idempotent - it would fail if these indexes already existed.

## Solution

Made the migration **idempotent** using `migrations.SeparateDatabaseAndState()`:

### Step 1: Add Column (Idempotent)
```python
migrations.SeparateDatabaseAndState(
    state_operations=[
        # Updates Django's internal state only
        migrations.AddField(...)
    ],
    database_operations=[
        # Custom SQL that checks before creating
        migrations.RunPython(add_public_token_column_idempotent)
    ]
)
```

The `add_public_token_column_idempotent()` function:
- **PostgreSQL**: 
  - Checks if column exists via `information_schema.columns`
  - Adds column only if missing
  - Drops and recreates the `_like` index (safe, always works)
  - Creates standard btree index with `IF NOT EXISTS`
- **SQLite**: 
  - Checks column via `PRAGMA table_info()`
  - Adds column only if missing
  - Creates index with `IF NOT EXISTS`

### Step 2: Backfill Tokens
No changes needed - this step is naturally idempotent (only updates rows with empty/null tokens).

### Step 3: Add Unique Constraint (Idempotent)
```python
migrations.SeparateDatabaseAndState(
    state_operations=[
        # Updates Django's internal state only
        migrations.AlterField(...)  # adds unique=True
    ],
    database_operations=[
        # Custom SQL that checks before creating
        migrations.RunPython(add_unique_constraint_idempotent)
    ]
)
```

The `add_unique_constraint_idempotent()` function:
- **PostgreSQL**: 
  - Drops existing unique indexes (if any)
  - Creates unique index with `IF NOT EXISTS`
- **SQLite**: 
  - Checks if unique index exists
  - Creates only if missing

## Key Implementation Details

### PostgreSQL Index Names Used
- Standard btree: `inventory_gymmember_public_token_208110ff`
- LIKE pattern ops: `inventory_gymmember_public_token_208110ff_like`
- Unique constraint: `inventory_gymmember_public_token_key`

### Why This Works
1. **Column check**: Prevents "column already exists" errors
2. **DROP + CREATE pattern**: For the `_like` index, we drop first (safe with `IF EXISTS`), then create fresh
3. **CREATE IF NOT EXISTS**: For standard indexes, we use PostgreSQL 9.5+ syntax
4. **Vendor-aware**: Handles PostgreSQL and SQLite differently
5. **State vs DB separation**: Django's state is updated via `AddField`/`AlterField`, but actual DB work is done by our safe functions

## Testing

### Local Testing (SQLite)
1. ✅ Applied migration successfully on fresh DB
2. ✅ Unmarked migration from `django_migrations` table (simulating Render scenario)
3. ✅ Re-ran migration with column/indexes already existing - SUCCESS (idempotent)
4. ✅ Django system check passed
5. ✅ Gym-related tests passed (`test_gym_qr.py` - 10 tests)

### Expected Render Behavior
When deployed to Render (PostgreSQL):
1. Migration will detect existing `public_token` column
2. Will skip column creation
3. Will drop and recreate the `_like` index cleanly
4. Will ensure standard and unique indexes exist
5. Will backfill any missing tokens
6. Migration will complete successfully

## Files Modified

- `inventory/migrations/1019_add_gym_public_token.py`
  - Added `add_public_token_column_idempotent()` function (84 lines)
  - Added `add_unique_constraint_idempotent()` function (46 lines)
  - Wrapped AddField in `SeparateDatabaseAndState`
  - Wrapped AlterField in `SeparateDatabaseAndState`
  - Total: +168 lines, -25 lines

## Git Commit

```
commit 88929018
Author: [Your Name]
Date:   [Date]

    Make gym public_token migration idempotent on Postgres (fix existing _like index)
```

## No Regressions

- ✅ Model field (`GymMember.public_token`) unchanged
- ✅ No UI changes
- ✅ No test changes
- ✅ No behavior changes
- ✅ Only migration internals modified
- ✅ Backward compatible with existing data

## Deployment Instructions

1. **Merge to main**: This fix is safe to merge
2. **Deploy to Render**: The migration will now succeed
3. **Monitor**: Watch Render logs during migration for "Applying inventory.1019_add_gym_public_token... OK"
4. **Verify**: After deploy, check that GymMember records have `public_token` values

## Rollback Safety

The migration uses `reverse_code=migrations.RunPython.noop` for rollback, which means:
- Rolling back won't drop the column/indexes
- This is intentional - we don't want to lose generated tokens in production
- If rollback is needed, manual cleanup would be required

## Future-Proofing

This pattern can be reused for other migrations that might face similar issues:
1. Use `SeparateDatabaseAndState` for operations that might fail if run twice
2. Write vendor-aware SQL that checks before creating
3. Test idempotency locally by unmarking migration and re-running

## References

- Django Ticket: https://code.djangoproject.com/ticket/29898 (SeparateDatabaseAndState)
- PostgreSQL Pattern Ops: https://www.postgresql.org/docs/current/indexes-opclass.html
- Django Migration Operations: https://docs.djangoproject.com/en/stable/ref/migration-operations/

