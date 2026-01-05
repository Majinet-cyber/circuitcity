# Migration Fix + Production Commands

## ✅ Issue Fixed

**Problem:** `django.db.utils.OperationalError: no such column: tenants_business.hq_notified_signup_at`

**Root Cause:** Model field added but migrations not applied to local SQLite database.

**Solution:**
1. Added column directly to database
2. Marked migration as applied
3. Generated and applied billing migrations
4. Added migration safety checks

---

## 🚀 PowerShell Commands

### 1. Check Migration Status

```powershell
# Check if all migrations are applied
python manage.py check_migrations

# Show migration status
python manage.py showmigrations
```

### 2. Generate Migrations (if needed)

```powershell
# Generate migrations for all apps
python manage.py makemigrations

# Generate migrations for specific app
python manage.py makemigrations billing
python manage.py makemigrations tenants
```

### 3. Apply Migrations

```powershell
# Apply all pending migrations
python manage.py migrate

# Apply specific app migrations
python manage.py migrate billing
python manage.py migrate tenants
```

### 4. Run Tests

```powershell
# Run all tests
python manage.py test

# Run specific test modules
python manage.py test core.tests.test_migrations
python manage.py test billing.tests.test_hq_notifications
python manage.py test billing.tests.test_subscription_cancellation_dunning

# Run with verbose output
python manage.py test billing.tests --verbosity=2
```

### 5. Start Development Server

```powershell
# Start Django development server
python manage.py runserver

# Access at: http://localhost:8000
```

### 6. Start Celery Workers (for Dunning)

```powershell
# Terminal 1: Start Celery worker
celery -A cc worker -l info --pool=solo

# Terminal 2: Start Celery beat (scheduler)
celery -A cc beat -l info
```

### 7. Git Commands

```powershell
# Check status
git status

# Stage all changes
git add .

# Commit with message
git commit -m "feat: Production-grade subscription cancellation + dunning + HQ notifications

- Implement cancel at period end (SaaS best practice)
- Add auto-billing dunning (6 retries over 2 days)
- Add grace periods (2 days before suspension)
- Implement subscription lockout (suspended/canceled)
- Add HQ/admin notifications (idempotent, all events)
- Add comprehensive tests + migration safety checks
- Fix migration dependency issues

All notifications sent to:
- info@imajinet.com
- jadepaulchris@gmail.com
- Admin email from settings

Includes migration safety checks and regression tests."

# Push to GitHub
git push origin main
```

---

## 🛡️ Safety Guards Added

### 1. Migration Consistency Check

**Command:** `python manage.py check_migrations`

**Purpose:** Ensures all migrations are applied and no missing migrations exist.

**Usage in CI:**
```yaml
# .github/workflows/ci.yml
- name: Check migrations
  run: python manage.py check_migrations --fail-on-pending
```

### 2. Regression Tests

**File:** `core/tests/test_migrations.py`

**Tests:**
- ✅ No missing migrations
- ✅ Business.hq_notified_signup_at exists
- ✅ BusinessSubscription HQ fields exist
- ✅ Invoice.hq_notified_paid_at exists

**Run:** `python manage.py test core.tests.test_migrations`

---

## 📋 Files Created/Modified

### New Files

1. `fix_migration_column.py` — One-time script to fix database (can delete after use)
2. `core/management/commands/check_migrations.py` — Migration check command
3. `core/tests/test_migrations.py` — Migration regression tests
4. `billing/services/notify_hq.py` — HQ notification service
5. `billing/tests/test_hq_notifications.py` — HQ notification tests
6. `MIGRATION_FIX_AND_COMMANDS.md` — This file

### Modified Files

1. `tenants/models.py` — Added `hq_notified_signup_at` field
2. `billing/models.py` — Added HQ notification fields
3. `billing/tasks.py` — Integrated HQ notifications
4. `billing/views.py` — Added HQ notifications to cancel/undo
5. `billing/tests/test_subscription_cancellation_dunning.py` — Added HQ notification tests

### Migrations Generated

1. `tenants/migrations/0022_business_hq_notified_signup_at.py` — Business HQ tracking
2. `billing/migrations/0013_businesssubscription_cancel_requested_at_and_more.py` — Subscription + Invoice HQ tracking

---

## ✅ Verification Steps

### 1. Check Database Columns Exist

```powershell
python manage.py shell
```

```python
from tenants.models import Business
from billing.models import BusinessSubscription, Invoice

# Check Business
print(hasattr(Business, 'hq_notified_signup_at'))  # Should be True

# Check BusinessSubscription
print(hasattr(BusinessSubscription, 'cancel_requested_at'))  # Should be True
print(hasattr(BusinessSubscription, 'hq_notified_cancel_requested_at'))  # Should be True

# Check Invoice
print(hasattr(Invoice, 'hq_notified_paid_at'))  # Should be True
```

### 2. Test Server Starts Without Errors

```powershell
python manage.py runserver
```

Visit: http://localhost:8000/sw.js (should return 200, not 500)

### 3. Run All Tests

```powershell
python manage.py test billing.tests core.tests.test_migrations
```

All tests should pass.

---

## 🔧 Troubleshooting

### Issue: "no such column" Error

**Solution:**
```powershell
# Run the fix script (if not already run)
python fix_migration_column.py

# Then apply migrations
python manage.py migrate
```

### Issue: "InconsistentMigrationHistory" Error

**Solution:**
```powershell
# The fix script handles this automatically
# If you still see it, the column was added but migration not marked
python fix_migration_column.py
```

### Issue: Tests Failing with UNIQUE Constraint

**Solution:** Tests use `get_or_create` for shared fixtures. If you see this error, clear test database:

```powershell
# Delete test database (if exists)
Remove-Item -Path "test_*.db" -ErrorAction SilentlyContinue

# Run tests again
python manage.py test
```

---

## 📝 Deploy Process (Production)

### Render Deploy Steps

1. **Update Environment Variables:**
   ```bash
   SENDGRID_API_KEY=your_key
   DEFAULT_FROM_EMAIL=Emajinet <no-reply@emajinet.africa>
   ADMIN_EMAIL=ops@emajinet.africa
   ```

2. **Update Build Command (if needed):**
   ```bash
   pip install -r requirements.txt && python manage.py collectstatic --no-input
   ```

3. **Update Release Command:**
   ```bash
   python manage.py migrate && python manage.py check_migrations
   ```

4. **Start Command:**
   ```bash
   gunicorn cc.wsgi:application
   ```

5. **Celery Worker (separate service):**
   ```bash
   celery -A cc worker -l info
   ```

6. **Celery Beat (separate service):**
   ```bash
   celery -A cc beat -l info
   ```

---

## 🎉 Summary

✅ **Migration issue fixed** — Column added, migrations applied
✅ **Safety guards added** — Migration check command + regression tests
✅ **Tests passing** — All migration and HQ notification tests pass
✅ **Production-ready** — Deploy process documented

**Next Steps:**
1. Run tests: `python manage.py test`
2. Start server: `python manage.py runserver`
3. Verify /sw.js loads without errors
4. Commit and push changes

---

**Date:** January 5, 2026
**Status:** ✅ COMPLETE
