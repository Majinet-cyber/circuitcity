# Accounts Settings SMS 2FA Fix

## Problem
The `/accounts/settings/` page was showing "Unavailable" for SMS 2FA even though `TWILIO_VERIFY_ENABLED=True`. The issue was that the `settings_unified` and `settings_security` views were not passing the required context variables for the `_twofa_sms_card.html` partial.

## Solution

### 1. Created Helper Function
**File:** `circuitcity/accounts/views.py` (line 1082-1125)

Added `_inject_sms_twofa_context(request, context)` helper that:
- Safely injects SMS 2FA context variables
- Handles import failures gracefully (falls back to `twofa_available=False`)
- Tries multiple import paths for `mask_phone()` function
- Includes inline fallback implementation of `mask_phone` if needed

**Context variables injected:**
- `twofa_available` (bool): Checks `TWILIO_VERIFY_ENABLED` setting
- `twofa_sms_enabled` (bool): User's SMS 2FA status from `UserTwoFactor` model
- `twofa_phone_masked` (str): Masked phone number (e.g., `+265******567`)

**Safety features:**
- Try/except wrapper catches all import and execution errors
- Logs warnings on failure but doesn't crash
- Falls back to "Unavailable" state on any error
- Multiple fallback paths for `mask_phone()` function

### 2. Updated settings_unified View
**File:** `circuitcity/accounts/views.py` (line 1346)

Added before `render()`:
```python
# Inject SMS 2FA context for _twofa_sms_card.html partial
ctx = _inject_sms_twofa_context(request, ctx)
```

This view renders to `inventory/settings.html` and is accessed via `/accounts/settings/`.

### 3. Updated settings_security View
**File:** `circuitcity/accounts/views.py` (line 1176)

Added before `render()`:
```python
# Inject SMS 2FA context for _twofa_sms_card.html partial
context = _inject_sms_twofa_context(request, context)
```

This view renders to `accounts/settings_security.html` and is accessed via `/accounts/settings/security/`.

## Changes Made

### Modified Files
1. ✅ `circuitcity/accounts/views.py`:
   - Added `_inject_sms_twofa_context()` helper function (47 lines)
   - Updated `settings_unified()` view (1 line added)
   - Updated `settings_security()` view (1 line added)

### No Template Changes Required
The templates already include `{% include "accounts/_twofa_sms_card.html" %}` from the previous implementation, so they automatically pick up the new context variables.

## Manual Verification Steps

### Before Fix
1. Set `TWILIO_VERIFY_ENABLED=True` in settings
2. Navigate to `/accounts/settings/`
3. ❌ SMS 2FA section shows: **"Unavailable"** (incorrect)

### After Fix
1. Restart Django server (to pick up new view code)
2. Hard refresh `/accounts/settings/` (Ctrl+Shift+R)
3. ✅ Expected behavior based on user state:

**Case A: User has NOT enabled SMS 2FA**
- Status: **Disabled** badge (yellow/warning)
- Help text: "Add an extra layer of security to your account."
- Button: **Enable 2FA** (blue/primary, clickable)

**Case B: User HAS enabled SMS 2FA**
- Status: **Enabled** badge (green)
- Phone: **+265******567** (masked, last 3 digits visible)
- Button: **Disable 2FA** (gray/muted, clickable)

**Case C: Twilio not configured (TWILIO_VERIFY_ENABLED=False)**
- Status: **Unavailable** badge (gray)
- Help text: "Configure Twilio to enable SMS OTP 2FA."
- Button: **Unavailable** (disabled)

## Security Considerations

✅ **No security changes** - This is UI wiring only
✅ **Phone numbers masked** - Uses existing `mask_phone()` helper
✅ **Fail-safe defaults** - Errors result in "Unavailable" state, not crashes
✅ **No OTP codes exposed** - Only status and masked phone displayed
✅ **Reuses existing flows** - Links to existing enable/disable endpoints

## Testing Recommendations

### Manual Testing
```bash
# 1. Start server with Twilio enabled
export TWILIO_VERIFY_ENABLED=True
export TWILIO_ACCOUNT_SID=ACxxxx
export TWILIO_AUTH_TOKEN=xxxx
export TWILIO_VERIFY_SERVICE_SID=VAxxxx
python manage.py runserver

# 2. Test each user state:
# - User without 2FA: Should see "Disabled" + Enable button
# - User with 2FA: Should see "Enabled" + masked phone + Disable button

# 3. Test fail-safe:
# - Set TWILIO_VERIFY_ENABLED=False
# - Should see "Unavailable" + disabled button
```

### Automated Testing (Optional)
Consider adding a test in `circuitcity/accounts/tests/test_twofa_sms.py`:

```python
def test_settings_unified_shows_sms_2fa_status(client, user, twilio_enabled_settings):
    """Test that /accounts/settings/ shows correct SMS 2FA status."""
    client.force_login(user)
    response = client.get(reverse("accounts:settings_unified"))
    
    assert response.status_code == 200
    assert "twofa_available" in response.context
    assert response.context["twofa_available"] is True
    assert response.context["twofa_sms_enabled"] is False
```

## Related Files

### Previously Modified (in earlier task)
- `templates/accounts/_twofa_sms_card.html` (NEW - reusable partial)
- `templates/inventory/settings.html` (MODIFIED - includes the partial)
- `inventory/views.py` (MODIFIED - `settings_home` view)

### Newly Modified (this task)
- `circuitcity/accounts/views.py` (MODIFIED - added helper + updated 2 views)

## No Breaking Changes

- ✅ Old context variables still work (backwards compatible)
- ✅ No auth/tenant logic modified
- ✅ Helper is defensive and fail-safe
- ✅ No database migrations required

## Commit Message Suggestion

```
fix(2fa): Wire SMS OTP context to accounts settings views

- Add _inject_sms_twofa_context() helper in accounts/views.py
- Call helper in settings_unified and settings_security views
- Fix "Unavailable" showing when TWILIO_VERIFY_ENABLED=True
- Fail-safe: errors default to Unavailable state
- Multi-path imports for mask_phone with inline fallback

Fixes /accounts/settings/ showing incorrect SMS 2FA status.
Now respects TWILIO_VERIFY_ENABLED and user's actual 2FA state.
```

## Files Modified Summary

1. ✅ `circuitcity/accounts/views.py`:
   - Lines 1082-1125: New `_inject_sms_twofa_context()` helper
   - Line 1176: Call helper in `settings_security()`
   - Line 1346: Call helper in `settings_unified()`

Total: **1 file modified, 3 logical changes, ~50 lines added**

## Deployment Checklist

- [x] Python syntax validated (`python -m py_compile`)
- [x] No linter errors
- [x] Backwards compatible (no breaking changes)
- [x] Fail-safe error handling
- [ ] Manual testing in development environment
- [ ] Verify with TWILIO_VERIFY_ENABLED=True
- [ ] Verify with TWILIO_VERIFY_ENABLED=False
- [ ] Test both /accounts/settings/ and /accounts/settings/security/

