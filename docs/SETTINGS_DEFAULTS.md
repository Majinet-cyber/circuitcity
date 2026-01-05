# Settings Defaults System

## Overview

The Settings Defaults system ensures that all users have sensible, premium default values for their profile settings and notification preferences. This system is designed to provide a clean, professional user experience without any "masked" or placeholder feel.

## Default Values

### Profile Defaults (Malawi Context)

All new users and users with blank fields automatically receive these defaults:

- **Language**: English
- **Country**: Malawi
- **Time Zone**: Africa/Blantyre
- **City**: Lilongwe (Malawi capital)

### Notification Defaults

All notification preferences are **enabled by default** for new users:

- ✅ Welcome emails
- ✅ Instant sale notifications
- ✅ Daily summary emails
- ✅ Important alerts
- ✅ High sales alerts
- ✅ Weekly digest
- ❌ Commission emails (disabled by default, for agents only)

## How It Works

### 1. Service Functions

The defaults system is implemented in `circuitcity/accounts/services/settings_defaults.py`:

```python
from circuitcity.accounts.services import (
    ensure_user_profile_defaults,
    ensure_notification_defaults,
    ensure_all_settings_defaults,
)
```

#### `ensure_user_profile_defaults(user)`

Fills in blank profile fields with Malawi defaults. **Never overwrites existing user choices.**

**Returns**: `True` if changes were made, `False` otherwise.

#### `ensure_notification_defaults(user)`

Creates notification preferences with all toggles enabled. **Never re-enables notifications that users have explicitly disabled.**

**Returns**: `True` if preferences were created or updated, `False` otherwise.

#### `ensure_all_settings_defaults(user)`

Convenience function that calls both profile and notification defaults.

**Returns**: Dict with `profile_changed` and `notifications_changed` keys.

### 2. When Defaults Are Applied

Defaults are automatically applied in these scenarios:

1. **Settings Page Visit**: When users visit `/accounts/settings/profile/`, the view calls `ensure_all_settings_defaults()` to ensure defaults are set.

2. **User Creation**: Profile and LoginSecurity are auto-created via Django signals when a user is created.

3. **Onboarding**: During business onboarding, defaults can be applied by calling the service functions.

### 3. Important Guarantees

#### ✅ User Choices Are Preserved

The system **NEVER** overwrites values that users have explicitly set:

- If a user changes their country to "France", it stays "France"
- If a user disables a notification, it stays disabled
- Only empty/blank fields get defaults filled in

#### ✅ No Data Loss

The service functions use `update_fields` to only save changed fields, preventing race conditions and data loss.

#### ✅ Idempotent

All functions can be called multiple times safely. They only make changes when needed.

## Model Changes

### Profile Model

The `Profile` model (`circuitcity/accounts/models.py`) includes these fields:

```python
class Profile(models.Model):
    display_name = models.CharField(max_length=120, blank=True, default="")
    country = models.CharField(max_length=80, blank=True, default="Malawi")
    language = models.CharField(max_length=80, blank=True, default="English")
    timezone = models.CharField(max_length=80, blank=True, default="Africa/Blantyre")
    city = models.CharField(max_length=100, blank=True, default="Lilongwe")
    display_currency = models.CharField(max_length=3, default="MWK", ...)
```

**Migration**: `0016_add_city_field_to_profile.py` adds the `city` field.

### NotificationPreference Model

The `NotificationPreference` model (`notifications/models.py`) includes these fields:

```python
class NotificationPreference(models.Model):
    welcome_emails = models.BooleanField(default=True)
    instant_sale_email = models.BooleanField(default=True)
    sale_emails_enabled = models.BooleanField(default=True)
    daily_summary_email = models.BooleanField(default=True)
    important_alerts_email = models.BooleanField(default=True)
    high_sales_alerts = models.BooleanField(default=True)
    weekly_digest_enabled = models.BooleanField(default=True)
    commission_emails_enabled = models.BooleanField(default=False)
```

**Note**: All fields default to `True` except `commission_emails_enabled` (for agents).

## Form Changes

### ProfileForm

The `ProfileForm` (`circuitcity/accounts/forms.py`) includes the `city` field and sets initial values from defaults:

```python
class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["display_name", "country", "language", "timezone", "city", "display_currency", "avatar"]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial defaults if instance doesn't already have values
        self.fields["country"].initial = getattr(self.instance, "country", None) or DEFAULT_COUNTRY
        self.fields["language"].initial = getattr(self.instance, "language", None) or DEFAULT_LANGUAGE
        self.fields["timezone"].initial = getattr(self.instance, "timezone", None) or DEFAULT_TIMEZONE
        self.fields["city"].initial = getattr(self.instance, "city", None) or DEFAULT_CITY
```

## View Changes

### settings_profile View

The `settings_profile` view (`circuitcity/accounts/views.py`) calls the defaults service:

```python
@login_required
@require_http_methods(["GET", "POST"])
def settings_profile(request):
    from .services.settings_defaults import ensure_all_settings_defaults

    profile = getattr(request.user, "profile", None)
    if profile is None:
        profile, _ = Profile.objects.get_or_create(user=request.user)

    # Apply defaults for new users or users with blank fields
    ensure_all_settings_defaults(request.user)
    
    # Refresh profile from DB after defaults are applied
    profile.refresh_from_db()

    # ... rest of view logic
```

## Template Changes

### settings_profile.html

The template (`templates/accounts/settings_profile.html`) now includes the city field:

```html
<div class="row g-3 mt-2">
  <div class="col-md-6">
    <label for="{{ form.city.id_for_label }}" class="form-label fw-semibold">City</label>
    {{ form.city }}
  </div>
  <div class="col-md-6">
    <label for="{{ form.display_currency.id_for_label }}" class="form-label fw-semibold">Display Currency</label>
    {{ form.display_currency }}
  </div>
</div>
```

## Testing

Comprehensive tests are in `circuitcity/accounts/tests/test_settings_defaults.py`.

### Test Coverage

- ✅ New users get proper defaults
- ✅ Existing values are preserved
- ✅ Mixed blank/set fields are handled correctly
- ✅ Notification preferences are created with all toggles enabled
- ✅ User-disabled notifications stay disabled
- ✅ Settings page applies defaults on visit
- ✅ Form submission persists changes
- ✅ Revisiting settings preserves user choices

### Running Tests

```bash
python manage.py test circuitcity.accounts.tests.test_settings_defaults
```

All 17 tests should pass.

## Usage Examples

### In a View

```python
from circuitcity.accounts.services import ensure_all_settings_defaults

def my_view(request):
    # Ensure user has defaults
    ensure_all_settings_defaults(request.user)
    
    # Continue with view logic
    ...
```

### In Onboarding

```python
from circuitcity.accounts.services import ensure_user_profile_defaults

def onboarding_complete(request):
    # Apply profile defaults after user creation
    ensure_user_profile_defaults(request.user)
    
    # Redirect to dashboard
    return redirect("dashboard")
```

### In a Management Command

```python
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from circuitcity.accounts.services import ensure_all_settings_defaults

User = get_user_model()

class Command(BaseCommand):
    help = "Backfill defaults for existing users"
    
    def handle(self, *args, **options):
        for user in User.objects.all():
            result = ensure_all_settings_defaults(user)
            if result["profile_changed"] or result["notifications_changed"]:
                self.stdout.write(f"Applied defaults for {user.username}")
```

## Troubleshooting

### User Not Seeing Defaults

1. Check if profile exists: `user.profile`
2. Check if defaults are blank: `user.profile.country == ""`
3. Call `ensure_user_profile_defaults(user)` manually
4. Refresh profile: `user.profile.refresh_from_db()`

### Notifications Not Enabled

1. Check if preferences exist: `NotificationPreference.objects.filter(user=user).exists()`
2. Call `ensure_notification_defaults(user)` manually
3. Check if user explicitly disabled them (False vs None)

### Defaults Not Persisting

1. Ensure migrations are run: `python manage.py migrate accounts`
2. Check for validation errors in forms
3. Verify `update_fields` is working correctly

## Future Enhancements

Possible improvements:

1. **Admin Interface**: Add a Django admin action to bulk-apply defaults
2. **Localization**: Support multiple language defaults based on user's region
3. **Business Context**: Apply business-specific defaults (e.g., timezone from business location)
4. **Analytics**: Track how many users keep defaults vs. customize them

## Related Files

- `circuitcity/accounts/models.py` - Profile model
- `circuitcity/accounts/forms.py` - ProfileForm with defaults
- `circuitcity/accounts/views.py` - settings_profile view
- `circuitcity/accounts/services/settings_defaults.py` - Service functions
- `notifications/models.py` - NotificationPreference model
- `templates/accounts/settings_profile.html` - Settings template
- `circuitcity/accounts/tests/test_settings_defaults.py` - Tests
- `circuitcity/accounts/migrations/0016_add_city_field_to_profile.py` - Migration

## Changelog

### 2026-01-05: Initial Implementation

- Added `city` field to Profile model
- Updated Profile model defaults (country=Malawi, language=English, timezone=Africa/Blantyre)
- Created `settings_defaults.py` service with ensure functions
- Updated ProfileForm to include city field
- Updated settings_profile view to call ensure_defaults
- Updated settings_profile.html template to include city
- Created comprehensive tests (17 tests, all passing)
- Added this documentation

