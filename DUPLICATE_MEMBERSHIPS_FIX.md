# Duplicate Active Memberships Fix

## Overview
Fixed duplicate ACTIVE membership issue that was causing 500 errors in production.

**Goal:** Never 500 if duplicates exist, clean existing duplicates, and prevent future duplicates.

## Implementation Summary

### 1. ✅ Hotfix: Made `get_membership()` Tolerant (Stops the 500)

**File:** `tenants/scope.py`

**Changes:**
- Replaced `.get()` with `.filter().order_by().first()`
- Added logging to warn when duplicates are detected
- Ordering logic: prefer memberships with location set (for agents), then most recent

**Impact:** App works immediately even if DB still has duplicates. No more crashes!

```python
def get_membership(user, business: Business | int) -> Optional[Membership]:
    """
    Get the active membership for a user in a business.
    Handles duplicate memberships gracefully by selecting the best one and logging a warning.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None
    biz_id = business.id if isinstance(business, Business) else business
    if not biz_id:
        return None
    
    # Use filter + order_by to handle duplicates gracefully
    # Prefer memberships with location set (for agents), then most recent
    qs = (
        Membership.objects
        .select_related("business", "location", "user")
        .filter(user_id=user.id, business_id=biz_id, status="ACTIVE")
        .order_by("-location_id", "-created_at", "-id")
    )
    
    m = qs.first()
    if not m:
        return None
    
    # Check if duplicates exist and warn (but don't crash)
    if qs.count() > 1:
        logger.warning(
            "Duplicate ACTIVE memberships detected user_id=%s business_id=%s; using membership_id=%s. "
            "Run 'python manage.py dedupe_memberships --apply' to clean up.",
            user.id, biz_id, m.id
        )
    
    return m
```

### 2. ✅ Management Command to Clean Existing Duplicates

**File:** `tenants/management/commands/dedupe_memberships.py`

**Usage:**
```bash
# Dry run (shows what would be changed)
python manage.py dedupe_memberships

# Actually apply changes
python manage.py dedupe_memberships --apply
```

**Behavior:**
- Finds all (user_id, business_id) pairs with multiple ACTIVE memberships
- Keeps the "best" one (prefers with location, most recent, highest ID)
- Sets the rest to status="REJECTED"
- Shows detailed output of what was kept and what was deactivated

**On Render:**
```bash
# SSH into render shell
python manage.py dedupe_memberships --apply
```

### 3. ✅ Database Constraint to Prevent Future Duplicates

**File:** `tenants/models.py`

**Changes:**
Added a conditional unique constraint to the `Membership` model:

```python
class Meta:
    constraints = [
        # Prevent duplicate ACTIVE memberships for the same (user, business) pair
        models.UniqueConstraint(
            fields=["user", "business"],
            condition=Q(status="ACTIVE"),
            name="uniq_active_membership_user_business",
        )
    ]
```

**Migration:** `tenants/migrations/0016_add_unique_active_membership_constraint.py`

**Important:** 
- This migration will fail if duplicates still exist in the database
- Must run step 2 (dedupe command) BEFORE applying this migration

### 4. ✅ Regression Tests

**File:** `tenants/tests/test_duplicate_memberships.py`

**Tests:**
1. `test_get_membership_handles_duplicates_gracefully` - Ensures no exception thrown
2. `test_constraint_prevents_new_duplicates` - Verifies DB constraint works
3. `test_non_active_memberships_allowed` - Confirms only ACTIVE ones are unique
4. `test_dedupe_command_dry_run` - Tests management command preview mode
5. `test_dedupe_command_apply` - Tests management command execution
6. `test_get_membership_with_no_duplicates` - Baseline test
7. `test_get_membership_unauthenticated` - Edge case handling
8. `test_get_membership_no_membership` - Edge case handling

**Run tests:**
```bash
python -m pytest tenants/tests/test_duplicate_memberships.py -v
```

## Deployment Steps

### For Staging/Production (Render):

1. **Deploy the hotfix** (this stops crashes immediately):
   ```bash
   git add tenants/scope.py
   git commit -m "Fix: handle duplicate active memberships gracefully"
   git push origin main
   ```
   ✅ App will now work even with duplicates present

2. **Clean existing duplicates** (after deployment):
   ```bash
   # SSH into Render shell
   python manage.py dedupe_memberships          # Preview what will change
   python manage.py dedupe_memberships --apply  # Actually clean up
   ```
   ✅ Database is now clean

3. **Apply the constraint migration** (prevents future duplicates):
   ```bash
   python manage.py migrate tenants
   ```
   ✅ Future duplicates are impossible

### Full Deployment (All Changes):

```bash
git add -A
git commit -m "Fix duplicate active membership crash and dedupe memberships

- Hotfix: Make get_membership() tolerant of duplicates (prevents 500)
- Add management command to clean existing duplicates
- Add DB constraint to prevent future duplicates
- Add comprehensive regression tests

Fixes #[issue-number]"
git push origin main
```

Then on Render:
```bash
# Wait for auto-deploy to complete, then:
python manage.py dedupe_memberships --apply
python manage.py migrate tenants
```

## Files Changed

### Modified:
- `tenants/scope.py` - Fixed `get_membership()` to handle duplicates
- `tenants/models.py` - Added unique constraint for ACTIVE memberships

### Created:
- `tenants/management/__init__.py` - Management commands package
- `tenants/management/commands/__init__.py` - Commands package
- `tenants/management/commands/dedupe_memberships.py` - Deduplication command
- `tenants/migrations/0016_add_unique_active_membership_constraint.py` - DB constraint
- `tenants/tests/test_duplicate_memberships.py` - Regression tests

## Testing Checklist

- [x] Unit tests pass for get_membership()
- [x] Management command works in dry-run mode
- [x] Management command works in apply mode
- [x] DB constraint prevents new duplicates
- [x] No linter errors
- [ ] Manual testing in staging environment
- [ ] Verify no 500 errors with existing duplicates
- [ ] Run dedupe command on staging
- [ ] Apply migration on staging
- [ ] Verify constraint works on staging

## Monitoring

After deployment, check logs for warnings like:
```
WARNING Duplicate ACTIVE memberships detected user_id=X business_id=Y; using membership_id=Z
```

If you see these warnings:
1. Note the user_id and business_id
2. Run `python manage.py dedupe_memberships --apply` to clean them up

## Rollback Plan

If issues occur:
1. The hotfix is safe and can remain (it only makes the code more tolerant)
2. The constraint can be removed with a migration if needed:
   ```python
   migrations.RemoveConstraint(
       model_name="membership",
       name="uniq_active_membership_user_business",
   )
   ```
3. The management command is idempotent and can be run multiple times safely

## Notes

- The constraint only applies to ACTIVE memberships
- Non-ACTIVE memberships (PENDING, REJECTED) can still have duplicates
- Agents require a location; managers do not
- The ordering logic prefers memberships with locations (for agents), then most recent

