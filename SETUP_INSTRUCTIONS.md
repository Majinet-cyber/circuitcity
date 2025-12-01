# Quick Setup Instructions

## 1. Add New Apps to Settings

Add these apps to `INSTALLED_APPS` in `cc/settings.py`:

```python
INSTALLED_APPS = [
    # ... existing apps ...
    'support',           # NEW - Ticket system
    'audit',             # Already exists, but verify
    'notifications',     # Already exists, but verify
]
```

## 2. (Optional) Add Audit Middleware

Add to `MIDDLEWARE` in `cc/settings.py` (after `AuthenticationMiddleware`):

```python
MIDDLEWARE = [
    # ... existing middleware ...
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'audit.middleware.AuditLogMiddleware',  # NEW - Auto-log important accesses
    # ... rest of middleware ...
]
```

## 3. Create and Run Migrations

```bash
python manage.py makemigrations support
python manage.py migrate
```

## 4. Test the Installation

```bash
# Run new tests
pytest tests/test_tenant_isolation.py -v
pytest tests/test_support_tickets.py -v
pytest tests/test_notifications.py -v

# Run all tests
pytest -v
```

## 5. Access New Features

### Manager Features:
- **Tickets**: `/support/tickets/`
- **Notifications**: `/notifications/`
- **Notification Bell**: Appears in sidebar automatically

### HQ Features:
- **HQ Dashboard**: `/hq/` (unified sidebar)
- **All Tickets**: `/support/hq/tickets/`
- **Audit Logs**: `/audit/logs/`

## Troubleshooting

### If you see "app isn't in INSTALLED_APPS" error:
- Add `'support'` to `INSTALLED_APPS` in `settings.py`

### If migrations fail:
- Make sure `support` app is in `INSTALLED_APPS` first
- Run `python manage.py makemigrations` without app name to check all apps

### If HQ pages show double sidebar:
- Clear browser cache
- Hard refresh (Ctrl+F5)
- The `hq/base_hq.html` template now uses its own sidebar

### If tests fail:
- Ensure database is migrated: `python manage.py migrate`
- Check that all apps are in `INSTALLED_APPS`
- Run `python manage.py check` first

## Files Changed Summary

### New Files (52 files):
- `tenants/decorators.py`
- `support/` app (9 files)
- `audit/` enhancements (4 files)
- `notifications/` enhancements (3 files)
- `templates/hq/` (2 files)
- `templates/support/` (5 files)
- `templates/audit/` (1 file)
- `templates/notifications/` (1 file)
- `templates/partials/notification_bell.html`
- `tests/` (3 test files)
- `IMPLEMENTATION_SUMMARY.md`
- `SETUP_INSTRUCTIONS.md`

### Modified Files:
- `cc/urls.py` - Added support, audit, notifications URLs
- `templates/hq/dashboard.html` - Uses new HQ base template
- `notifications/apps.py` - Loads signals on startup

## Next Steps

1. Add apps to `INSTALLED_APPS`
2. Run migrations
3. Test the new features
4. Review `IMPLEMENTATION_SUMMARY.md` for detailed documentation

All features maintain:
✅ Multi-tenant isolation
✅ Existing flows unbroken
✅ Mobile-first design
✅ Glassmorphic styling
✅ Security best practices

