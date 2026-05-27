# SMS 2FA Inventory Settings UI Implementation

## Summary

Successfully wired the SMS OTP 2FA backend to the inventory settings UI. The hard-coded "Unavailable" button has been replaced with a dynamic SMS 2FA card that respects `TWILIO_VERIFY_ENABLED` and shows the correct status.

## Changes Made

### 1. Created Reusable Template Partial
**File:** `templates/accounts/_twofa_sms_card.html`

A reusable template component that displays SMS 2FA status with three states:
- **Unavailable** (when `TWILIO_VERIFY_ENABLED=False`): Shows badge + help text
- **Disabled** (when Twilio enabled but user hasn't enabled 2FA): Shows "Enable 2FA" button
- **Enabled** (when user has SMS 2FA active): Shows masked phone + "Disable 2FA" button

**Context variables required:**
- `twofa_available` (bool) - Whether Twilio Verify is configured
- `twofa_sms_enabled` (bool) - Whether user has SMS 2FA enabled
- `twofa_phone_masked` (str) - Masked phone number like `+265******456`

**URLs used:**
- `accounts:twofa_sms_enable_start` - Start enable flow
- `accounts:twofa_sms_disable_start` - Start disable flow

### 2. Updated Inventory Settings Template
**File:** `templates/inventory/settings.html`

**Before (line 44-61):**
```html
<!-- Two-Factor Authentication -->
<div class="panel-soft pad-sm round" style="margin-left:auto; min-width:min(420px, 100%);">
  <div class="hstack" style="justify-content:space-between;">
    <div>
      <div style="font-weight:900; font-size:var(--fs-18);">Two-Factor Authentication</div>
      <div class="text-muted">Status: {{ twofa_status }}</div>
    </div>
    <div class="hstack" style="gap:8px;">
      {% if twofa_manage_url %}
        <a href="{{ twofa_manage_url }}" class="btn {% if not twofa_enabled %}btn-primary{% endif %}">
          {% if twofa_enabled %}Manage 2FA{% else %}Set up 2FA{% endif %}
        </a>
      {% else %}
        <button class="btn" disabled title="Two-factor app not installed">Unavailable</button>
      {% endif %}
    </div>
  </div>
</div>
```

**After (line 44-45):**
```html
<!-- Two-Factor Authentication (SMS OTP) -->
{% include "accounts/_twofa_sms_card.html" %}
```

### 3. Updated Inventory Settings View
**File:** `inventory/views.py` (line 5758-5785)

**Key changes:**
- Imported `UserTwoFactor` and `mask_phone` from `circuitcity.accounts.models`
- Added logic to check `TWILIO_VERIFY_ENABLED` setting
- Get or create `UserTwoFactor` record for current user
- Pass three new context variables to template:
  - `twofa_available`: `bool(getattr(settings, "TWILIO_VERIFY_ENABLED", False))`
  - `twofa_sms_enabled`: `bool(tf.sms_enabled)`
  - `twofa_phone_masked`: `mask_phone(tf.phone_e164)` if phone exists
- Also fixed missing context variables: `avatar_img_url`, `upload_avatar_url`, `change_password_url`

**Note:** Commented out duplicate `settings_home` function at line 4737 to avoid confusion.

## Security Considerations

✅ **No OTP codes rendered or logged**
✅ **Phone numbers are masked** using existing `mask_phone()` helper
✅ **No tenant scoping touched** - this is UI wiring only
✅ **Reuses existing enable/disable endpoints** - no new security surface

## Manual Verification Steps

### Test Case 1: Twilio Not Configured
**Setup:** `TWILIO_VERIFY_ENABLED=False` or not set

**Expected Result:**
1. Navigate to inventory settings page
2. SMS 2FA section shows:
   - Status: **Unavailable** badge (gray)
   - Help text: "Configure Twilio to enable SMS OTP 2FA."
   - Button: **Unavailable** (disabled)

### Test Case 2: Twilio Enabled, User Has Not Enabled 2FA
**Setup:** `TWILIO_VERIFY_ENABLED=True`, user's `UserTwoFactor.sms_enabled=False`

**Expected Result:**
1. Navigate to inventory settings page
2. SMS 2FA section shows:
   - Status: **Disabled** badge (yellow/warning)
   - Help text: "Add an extra layer of security to your account."
   - Button: **Enable 2FA** (primary/blue, clickable)
3. Clicking "Enable 2FA" redirects to `/accounts/2fa/sms/enable/start/`

### Test Case 3: Twilio Enabled, User Has Enabled 2FA
**Setup:** `TWILIO_VERIFY_ENABLED=True`, user's `UserTwoFactor.sms_enabled=True`, `phone_e164="+265991234567"`

**Expected Result:**
1. Navigate to inventory settings page
2. SMS 2FA section shows:
   - Status: **Enabled** badge (green)
   - Phone: **+265******567** (masked)
   - Button: **Disable 2FA** (muted/gray, clickable)
3. Clicking "Disable 2FA" redirects to `/accounts/2fa/sms/disable/start/`

## Files Modified

1. ✅ `templates/accounts/_twofa_sms_card.html` (NEW)
2. ✅ `templates/inventory/settings.html` (MODIFIED)
3. ✅ `inventory/views.py` (MODIFIED)

## Dependencies

- Existing `circuitcity.accounts.models.UserTwoFactor` model
- Existing `circuitcity.accounts.models.mask_phone()` helper
- Existing URL patterns in `circuitcity/accounts/urls.py`:
  - `accounts:twofa_sms_enable_start`
  - `accounts:twofa_sms_disable_start`
- Django setting: `TWILIO_VERIFY_ENABLED`

## No Breaking Changes

- Old context variables (`twofa`, `twofa_status`, `twofa_manage_url`, `twofa_enabled`) are no longer used but their removal doesn't break anything
- The new partial is self-contained and doesn't affect other pages
- All existing 2FA enable/disable flows remain unchanged

## Commit Message Suggestion

```
feat(2fa): Wire SMS OTP 2FA to inventory settings UI

- Create reusable _twofa_sms_card.html partial
- Replace hard-coded "Unavailable" button in inventory/settings.html
- Update settings_home view to pass SMS 2FA context
- Show correct status: Unavailable/Disabled/Enabled
- Link to existing enable/disable flows
- Mask phone numbers for security

Fixes hard-coded "Two-factor app not installed" message.
Now respects TWILIO_VERIFY_ENABLED and user's SMS 2FA status.
```

