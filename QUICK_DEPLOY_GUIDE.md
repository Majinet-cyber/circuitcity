# Quick Deployment Guide - Duplicate Membership Fix

## ⚡ Fast Track (Staging/Production)

### Step 1: Deploy the Hotfix (stops crashes immediately)
```bash
git add tenants/scope.py
git commit -m "Hotfix: handle duplicate active memberships gracefully"
git push origin main
```
✅ **Result:** App works immediately, no more 500 errors

---

### Step 2: Clean Existing Duplicates (on Render shell)
```bash
# Preview what will change
python manage.py dedupe_memberships

# Apply the changes
python manage.py dedupe_memberships --apply
```
✅ **Result:** Database is clean, no duplicates remain

---

### Step 3: Apply the DB Constraint (prevent future duplicates)
```bash
python manage.py migrate tenants
```
✅ **Result:** Future duplicates are impossible

---

## 📦 Full Deployment (All at Once)

```bash
# Commit all changes
git add -A
git commit -m "Fix duplicate active membership crash and dedupe memberships

- Hotfix: Make get_membership() tolerant of duplicates (prevents 500)
- Add management command to clean existing duplicates
- Add DB constraint to prevent future duplicates
- Add comprehensive regression tests"

git push origin main
```

Then on Render:
```bash
# Wait for auto-deploy, then:
python manage.py dedupe_memberships --apply
python manage.py migrate tenants
```

---

## 🧪 Testing Locally

```bash
# Run the regression tests
python -m pytest tenants/tests/test_duplicate_memberships.py -v

# Test the management command (dry run)
python manage.py dedupe_memberships

# Test the management command (apply)
python manage.py dedupe_memberships --apply

# Run migrations
python manage.py migrate tenants
```

---

## 🔍 Monitoring

After deployment, check logs for warnings:
```
WARNING Duplicate ACTIVE memberships detected user_id=X business_id=Y; using membership_id=Z
```

If you see these:
1. Run `python manage.py dedupe_memberships --apply`
2. Verify the warning disappears

---

## ⚠️ Important Notes

- **Step 2 must be done BEFORE Step 3** (clean duplicates before adding constraint)
- The management command is **idempotent** (safe to run multiple times)
- The hotfix (Step 1) is **safe to deploy alone** and provides immediate relief
- Only ACTIVE memberships are constrained (PENDING, REJECTED can still have duplicates)

---

## 📁 Files Modified

- ✅ `tenants/scope.py` - Fixed get_membership()
- ✅ `tenants/models.py` - Added unique constraint
- ✅ `tenants/management/commands/dedupe_memberships.py` - New command
- ✅ `tenants/migrations/0016_add_unique_active_membership_constraint.py` - New migration
- ✅ `tenants/tests/test_duplicate_memberships.py` - New tests

---

## 🆘 Rollback

If issues occur:
```python
# Remove the constraint (create a new migration):
migrations.RemoveConstraint(
    model_name="membership",
    name="uniq_active_membership_user_business",
)
```

The hotfix in `tenants/scope.py` is safe and should remain.

