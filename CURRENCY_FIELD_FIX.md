# Currency Field Migration Fix

## Root Cause

The production-blocking error `django.db.utils.OperationalError: no such column: tenants_business.currency` occurred because:

1. The `Business` model in `tenants/models.py` has a `currency` field defined (line 107-111)
2. A migration to add this field existed (`tenants/migrations/0023_add_currency_field.py`) but was **not applied** to the SQLite database
3. The migration dependency conflict prevented it from being applied: `notifications.0008_backfill_preferences_and_set_defaults` was already applied but depended on `tenants.__latest__`, which created an inconsistent migration history when the new `0023_add_currency_field` migration was added

## Fix Applied

### 1. Fixed Migration Dependency Conflict
**File**: `notifications/migrations/0008_backfill_preferences_and_set_defaults.py`

Changed the dependency from the problematic `__latest__` to a specific migration:

```python
dependencies = [
    ("notifications", "0007_add_sale_emails_enabled_field"),
    ("tenants", "0022_business_hq_notified_signup_at"),  # Changed from "__latest__"
]
```

### 2. Applied the Currency Field Migration
Ran:
```bash
python manage.py migrate tenants
```

This successfully applied `tenants.0023_add_currency_field`, which:
- Adds `currency = models.CharField(max_length=3, default="MWK")` to the `tenants_business` table
- Sets default value "MWK" (Malawian Kwacha) for all existing rows
- Safe for production: no data loss, backward compatible

### 3. Applied Additional Pending Migrations
Also applied:
- `billing.0015_rename_billing_pen_busines_idx_...` (index renames)
- `inventory.1018_clothingbarcodeunit` (new model)

### 4. Added Regression Test
**File**: `tenants/tests/test_business_currency.py`

Created comprehensive smoke tests to ensure:
- Business objects can be created with default currency (MWK)
- Business objects can be created with custom currency codes
- Existing Business rows can be queried without `OperationalError`
- All 3 tests pass ✅

## Files Changed

1. `notifications/migrations/0008_backfill_preferences_and_set_defaults.py` - Fixed dependency
2. `tenants/tests/test_business_currency.py` - Added regression tests (new file)
3. Database: Applied `tenants.0023_add_currency_field` migration

## Verification

✅ `python manage.py check` - No issues  
✅ `python manage.py test tenants.tests.test_business_currency` - All 3 tests pass  
✅ `python manage.py migrate` - All migrations applied successfully  
✅ Business model can now be queried without `OperationalError`

## Impact on /billing/manage/

The `/billing/manage/` page (and all other pages) will no longer crash with the `OperationalError` because:
- The `currency` column now exists in the `tenants_business` table
- All Business queries (which happen in middleware and throughout the app) will succeed
- No code changes were needed - the schema now matches the model definition

## No Regressions

✅ No changes to PayChangu live payment flow  
✅ No changes to dunning logic  
✅ No changes to cancellation flow  
✅ No changes to HQ notifications  
✅ No changes to `/sw.js` or service worker stability  
✅ Migration is backward compatible with default value

## Deployment Notes

For production deployment:
1. Run `python manage.py migrate` to apply the currency field migration
2. Existing businesses will automatically get `currency="MWK"` as default
3. No downtime required - migration is additive with safe defaults

