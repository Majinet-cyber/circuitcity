# SMS OTP 2FA - Quick Reference Guide

## 🚀 Quick Start

### For Developers - Apply to Sensitive Views

```python
from circuitcity.accounts.decorators import require_recent_2fa

@login_required
@require_recent_2fa(max_age_seconds=1800)  # 30 min default
def sensitive_view(request):
    # Password change, payouts, wallet withdrawals, etc.
    pass
```

### For Developers - Check if User Has 2FA

```python
from circuitcity.accounts.models import is_twofa_enabled

if is_twofa_enabled(request.user):
    # User has 2FA enabled
    pass
```

---

## 🔑 Environment Variables

```bash
# Required for 2FA to work
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_VERIFY_SERVICE_SID=VAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Get Credentials**: https://console.twilio.com/us1/develop/verify/services

---

## 📍 Key URLs

- `/accounts/settings/` → Enable/Disable 2FA
- `/accounts/2fa/challenge/` → Post-login OTP challenge
- `/accounts/2fa/sms/enable/start/` → Start enable flow
- `/accounts/2fa/sms/enable/verify/` → Verify enable code
- `/accounts/2fa/sms/disable/start/` → Start disable flow
- `/accounts/2fa/sms/disable/verify/` → Verify disable code

---

## 🔒 Rate Limits

| Action | Cooldown | Max Attempts | Window |
|--------|----------|--------------|--------|
| Send OTP | 60 sec | 3 | 10 min |
| Verify OTP | - | 8 | 10 min |

**Error**: "Too many attempts. Contact your admin."

---

## 🆘 Admin Rescue

**Emergency disable 2FA**:
1. Go to `/admin/accounts/usertwofa/`
2. Find user
3. Actions → "Disable 2FA for selected users"

---

## 🧪 Testing

**Mock Twilio in tests**:
```python
from unittest.mock import patch

@patch('circuitcity.accounts.services.twilio_verify.Client')
def test_2fa(mock_client):
    mock_client.return_value.verify.v2.services...
```

**Run tests**:
```bash
pytest circuitcity/accounts/tests/test_twofa_sms.py -v
```

---

## 📝 Session Keys

- `twofa_required` → User needs to pass challenge
- `twofa_passed` → User passed challenge
- `twofa_passed_at` → Timestamp of challenge pass
- `twofa_pending_phone` → Phone during enable flow
- `twofa_enable_flow` → Enable flow in progress
- `twofa_disable_flow` → Disable flow in progress
- `twofa_challenge_otp_sent` → OTP sent on challenge page

---

## 🎯 Apply Decorator To

**Recommended views**:
- Password change ✅ (already applied)
- Profile/email updates
- Payout requests
- Wallet withdrawals
- Destructive deletes
- Data exports

**Example**:
```python
@login_required
@require_recent_2fa()  # 30 min default
def delete_business(request, pk):
    # Destructive operation
    pass
```

---

## 🔍 Troubleshooting

### User can't receive SMS
- Verify phone format: E.164 (+265991234567)
- Check Twilio dashboard for delivery logs
- Verify Twilio Verify service is active

### "Too many attempts"
- Wait 10 minutes for counters to reset
- Admin disables 2FA via Django admin
- Clear cache: `cache.clear()`

### Stuck on challenge page
- Admin disables 2FA for user
- Check session: `request.session.get('twofa_passed')`

### Twilio outage
- Shows friendly error: "Unable to send verification code"
- Admin can disable 2FA temporarily
- Users can't enable/disable during outage

---

## 📊 Helper Functions

```python
from circuitcity.accounts.models import (
    get_or_create_twofactor,  # Get UserTwoFactor object
    is_twofa_enabled,         # Check if enabled (bool)
    mask_phone,               # Mask for display
    is_twofa_recent,          # Check if recent (bool)
)

# Examples
tf = get_or_create_twofactor(user)
enabled = is_twofa_enabled(user)
masked = mask_phone("+265991234567")  # "+2659******567"
recent = is_twofa_recent(request, max_age_seconds=1800)
```

---

## 🎨 Template Usage

```django
{% load account_extras %}

{# Check if enabled #}
{% if twofactor.sms_enabled %}
  <span class="badge bg-success">Enabled</span>
  <code>{{ twofactor.phone_e164|mask_phone }}</code>
{% else %}
  <span class="badge bg-secondary">Disabled</span>
{% endif %}
```

---

## 🚦 User Flow

### Enable Flow
1. Settings → Security → Enter phone → Send Code
2. Receive SMS with 6-digit code
3. Enter code → Verify & Enable
4. ✅ 2FA Enabled

### Login Flow (2FA Enabled)
1. Enter username/password
2. Redirected to challenge page
3. Receive SMS automatically
4. Enter 6-digit code
5. ✅ Access granted

### Disable Flow
1. Settings → Security → Disable 2FA
2. Receive SMS with code
3. Enter code → Verify & Disable
4. ✅ 2FA Disabled

---

## 📦 Files Structure

```
circuitcity/accounts/
├── models.py                 # UserTwoFactor model + helpers
├── views.py                  # 5 new views + updated login
├── urls.py                   # 5 new URL patterns
├── admin.py                  # UserTwoFactor admin
├── decorators.py             # @require_recent_2fa
├── services/
│   └── twilio_verify.py     # Twilio API integration
├── tests/
│   └── test_twofa_sms.py    # Comprehensive tests
└── templatetags/
    └── account_extras.py     # mask_phone filter

cc/
├── settings.py               # Twilio config
└── middleware_twofa.py      # Enforcement middleware

templates/accounts/
├── settings_security.html    # Updated with 2FA UI
└── 2fa_challenge.html       # Challenge page
```

---

## 🎯 Deployment Steps

1. **Migration**:
   ```bash
   python manage.py migrate accounts
   ```

2. **Environment Variables** (production):
   ```bash
   export TWILIO_ACCOUNT_SID=ACxxx...
   export TWILIO_AUTH_TOKEN=xxx...
   export TWILIO_VERIFY_SERVICE_SID=VAxxx...
   ```

3. **Verify**:
   - Check: `TWILIO_VERIFY_ENABLED = True` in logs
   - Test enable flow in staging
   - Test login flow
   - Verify rate limits work

4. **Monitor**:
   - Twilio usage dashboard
   - Cache hit rates
   - User feedback

---

## 💰 Twilio Pricing

**Verify API** (as of 2024):
- SMS Verification: ~$0.05 per attempt
- Voice Verification: ~$0.15 per attempt

**Cost Calculation**:
- 1000 users × 2 logins/day × 30 days = 60,000 SMS/month
- 60,000 × $0.05 = **$3,000/month**

**Optimization**:
- Session timeout: Increase to reduce re-challenges
- Remember device: Consider adding in future
- Rate limiting: Already implemented

---

## 🔐 Security Best Practices

✅ **Implemented**:
- No OTP logging
- Phone masking in UI
- Rate limiting (60s + 3/10min + 8/10min)
- CSRF protection
- Session security
- Step-up authentication
- Admin rescue path
- Graceful error handling

⚠️ **Consider Adding** (Future):
- Remember device (30 days)
- Backup codes (if phone lost)
- TOTP app support (Google Authenticator)
- SMS fallback to email

---

## 📞 Support

**For Users**:
- "Too many attempts" → Wait 10 minutes or contact admin
- Can't receive SMS → Check phone number format
- Lost phone → Contact admin to disable 2FA

**For Admins**:
- Emergency disable: Django admin → UserTwoFactor
- Monitor: Twilio dashboard for delivery issues
- Costs: Check Twilio usage logs

---

**Last Updated**: December 31, 2025  
**Version**: 1.0.0  
**Status**: ✅ Production Ready

