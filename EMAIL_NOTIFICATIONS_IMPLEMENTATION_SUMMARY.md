# Email Notifications System Implementation Summary

## Overview
Complete email notification system using SendGrid has been implemented for the Emajinet/Circuit City SaaS platform. All emails send after DB commit and are idempotent to prevent duplicates.

## ✅ Completed Features

### 1. ✅ NEW MANAGER Signup → Welcome Email
- **Location**: `circuitcity/accounts/views.py` - `_complete_manager_wizard_signup()`
- **Template**: `notifications/templates/notifications/emails/welcome_manager.html`
- **Subject**: "Congratulations for joining Emajinet"

### 2. ✅ OTP System (Request + Verify)
- **Model**: `circuitcity/accounts/models.py` - `EmailOTP`
- **Endpoints**: 
  - `POST /accounts/auth/otp/request/` - Request OTP
  - `POST /accounts/auth/otp/verify/` - Verify OTP
- **Template**: `notifications/templates/notifications/emails/otp_code.html`
- **Features**: Rate limiting (3 per 10 min), 10-minute expiry, max 5 attempts

### 3. ✅ Sale Completion Notifications
- **Location**: `inventory/signals.py` - Sale post_save signal
- **Service**: `notifications/services.py` - `notify_sale_completion()`
- **Features**:
  - Instant emails for normal volume
  - Batching for high volume (>10 sales in 5 min)
  - Templates: `sale_instant.html`, `sale_batch.html`

### 4. ✅ Daily Summary Email (1AM Africa/Blantyre)
- **Command**: `notifications/management/commands/send_yesterday_sales_summary.py`
- **Template**: `notifications/templates/notifications/emails/sales_daily_summary.html`
- **Content**: Total sales, revenue, profit, top 5 products
- **Scheduling**: See "Scheduling" section below

### 5. ✅ NEW AGENT Signup → Welcome Emails
- **Location**: `tenants/services/invites.py` - `accept_invite_by_token()`
- **Templates**: 
  - `welcome_agent.html` - Sent to agent
  - `important_alert.html` - Optional notification to managers
- **Subject**: "Welcome to {business_name}"

### 6. ✅ Important Alerts Framework
- **Service**: `notifications/services.py` - `send_important_alert()`
- **Triggers**: 
  - Big sale threshold (default: 500000 MWK) - auto-triggered
  - Can be called programmatically
- **Template**: `notifications/templates/notifications/emails/important_alert.html`

### 7. ✅ High-Sales Day Detection
- **Service**: `notifications/services.py` - `_check_high_sales_alert()`
- **Template**: `notifications/templates/notifications/emails/high_sales_alert.html`
- **Features**: 
  - Threshold: 10 sales per product per day
  - Trending detection (compares with 7-day average)
  - Deduplicated per day

## 📁 Files Created

### Models
- `notifications/models.py` - Added `NotificationPreference`, `NotificationEvent`
- `circuitcity/accounts/models.py` - Added `EmailOTP` model

### Services
- `notifications/emailer.py` - Email sending utilities
- `notifications/selectors.py` - Recipient resolution helpers
- `notifications/services.py` - Updated with email notification functions
- `notifications/tasks.py` - Celery tasks for email dispatch

### Templates
- `notifications/templates/notifications/emails/welcome_manager.html/txt`
- `notifications/templates/notifications/emails/welcome_agent.html/txt`
- `notifications/templates/notifications/emails/otp_code.html/txt`
- `notifications/templates/notifications/emails/sale_instant.html/txt`
- `notifications/templates/notifications/emails/sale_batch.html/txt`
- `notifications/templates/notifications/emails/sales_daily_summary.html/txt`
- `notifications/templates/notifications/emails/high_sales_alert.html/txt`
- `notifications/templates/notifications/emails/important_alert.html/txt`

### Management Commands
- `notifications/management/commands/send_yesterday_sales_summary.py`
- `core/management/commands/test_email.py`

### Admin
- `notifications/admin.py` - Registered all models

### Signals
- `notifications/signals.py` - Added signal to auto-create `NotificationPreference`

## 📝 Files Modified

1. **cc/settings.py**
   - Added `anymail` to INSTALLED_APPS (optional, added if installed)
   - Added `CELERY_TIMEZONE = "Africa/Blantyre"`
   - Email configuration already existed

2. **circuitcity/accounts/views.py**
   - Added welcome email emission in `_complete_manager_wizard_signup()`

3. **circuitcity/accounts/services/email_otp.py**
   - Updated to use notification system instead of direct send_mail

4. **tenants/services/invites.py**
   - Added welcome email emission for agents

5. **inventory/signals.py**
   - Added sale completion notification in Sale post_save signal
   - Added important sale threshold check

## 🔧 Migrations Required

Run these commands to create migrations:

```bash
python manage.py makemigrations notifications
python manage.py makemigrations accounts
python manage.py migrate
```

## ⚙️ Configuration

### Environment Variables (Already Set on Render)
- `SENDGRID_API_KEY` - Your SendGrid API key
- `DEFAULT_FROM_EMAIL` - Default: "Emajinet <noreply@emajinet.africa>"
- `IMPORTANT_SALE_THRESHOLD` - Optional, default: 500000

### Dependencies
Already in `requirements.txt`:
- `django-anymail==11.1`
- `sendgrid==6.11.0`

Install if needed:
```bash
pip install django-anymail[sendgrid]
```

## 📅 Scheduling

### Daily Summary Email

**Option 1: Render Cron Job (Recommended)**
Create a Cron Job in Render:
- **Schedule**: `0 1 * * *` (1:00 AM UTC = 3:00 AM Blantyre) - Adjust timezone offset
- **Command**: `python manage.py send_yesterday_sales_summary`
- **Timezone**: Africa/Blantyre (UTC+2)

**Option 2: Celery Beat**
Add to Celery Beat schedule (if using django-celery-beat):

```python
# In settings.py or celery config
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'send-daily-sales-summary': {
        'task': 'notifications.tasks.send_daily_sales_summary',
        'schedule': crontab(hour=1, minute=0, timezone='Africa/Blantyre'),
    },
}
```

**Note**: 1:00 AM Blantyre = 23:00 UTC (previous day), so schedule at `23:00 UTC` or adjust accordingly.

## 🧪 Testing

### Test Email Sending
```bash
python manage.py test_email your@email.com
```

### Test OTP
```bash
# Request OTP
curl -X POST http://localhost:8000/accounts/auth/otp/request/ \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "purpose": "login"}'

# Verify OTP
curl -X POST http://localhost:8000/accounts/auth/otp/verify/ \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "purpose": "login", "code": "123456"}'
```

### Test Sale Notification
1. Create a sale (mark item as sold)
2. Check `NotificationEvent` in admin - should see `SALE_INSTANT` event
3. Check email delivery status

### Test Daily Summary
```bash
python manage.py send_yesterday_sales_summary
```

## 🔍 Admin Interface

Access Django admin to:
- View/edit `NotificationPreference` for users
- View `NotificationEvent` audit trail (status, errors, etc.)
- Debug failed emails

## 🚨 Important Notes

1. **Transaction Safety**: All emails are sent after DB commit using `transaction.on_commit()`

2. **Idempotency**: `NotificationEvent` has unique constraint on `(event_type, recipient_email, dedupe_key)` to prevent duplicates

3. **Batching**: Sale notifications automatically batch when >10 sales occur in 5 minutes

4. **Rate Limiting**: OTP requests limited to 3 per email per 10 minutes

5. **Preferences**: Users can opt-out of specific email types via `NotificationPreference` model

6. **Fallback**: If Celery is unavailable, emails send synchronously (still after commit)

## 📊 Database Models

### NotificationPreference
- Auto-created on user creation (via signal)
- Controls which emails user receives

### NotificationEvent
- Audit trail of all email events
- Prevents duplicates via unique constraint
- Tracks status (PENDING/SENT/FAILED)

### EmailOTP
- Stores OTP codes (hashed)
- Tracks attempts and expiry
- Rate limiting support

## 🔗 API Endpoints

- `POST /accounts/auth/otp/request/` - Request OTP
- `POST /accounts/auth/otp/verify/` - Verify OTP

## ✅ Next Steps

1. **Install dependencies** (if not already):
   ```bash
   pip install django-anymail[sendgrid]
   ```

2. **Run migrations**:
   ```bash
   python manage.py makemigrations notifications accounts
   python manage.py migrate
   ```

3. **Test email sending**:
   ```bash
   python manage.py test_email your@email.com
   ```

4. **Set up Render Cron Job** for daily summaries (see Scheduling section)

5. **Verify SendGrid credentials** are set in Render environment

6. **Test end-to-end**:
   - Create a test manager account → check welcome email
   - Create a test sale → check notification email
   - Request OTP → check OTP email

## 🐛 Troubleshooting

### Emails not sending
1. Check `SENDGRID_API_KEY` is set
2. Check `NotificationEvent` in admin for errors
3. Check Celery worker logs if using Celery
4. Verify SendGrid account is active

### Migrations fail
- Ensure `anymail` is installed OR remove from INSTALLED_APPS temporarily
- Check for model conflicts

### OTP not working
- Check email rate limiting (3 per 10 min)
- Verify OTP hasn't expired (10 minutes)
- Check attempt count (< 5 attempts)

## 📝 Summary

All required features have been implemented:
- ✅ Manager welcome emails
- ✅ Agent welcome emails  
- ✅ OTP system (request + verify)
- ✅ Sale completion notifications (with batching)
- ✅ Daily sales summary
- ✅ Important alerts framework
- ✅ High-sales day detection
- ✅ Idempotent email sending
- ✅ Transaction-safe (on_commit)
- ✅ Admin interface
- ✅ Test command

The system is production-ready once migrations are run and SendGrid is configured.

