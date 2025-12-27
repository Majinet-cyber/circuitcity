# Production Email System - Final Checklist

## Files Changed

### 1. Settings Hardening (`cc/settings.py`)
- ✅ Added production guard: `USE_CONSOLE_EMAIL=True` raises `RuntimeError` when `DEBUG=False`
- ✅ Added SendGrid config validation: Raises `ImproperlyConfigured` if `USE_CONSOLE_EMAIL=0` but `SENDGRID_API_KEY` missing
- ✅ Added `DEFAULT_FROM_EMAIL` validation with fallback and warning
- ✅ Added startup warning if from-email domain is not `emajinet.africa`
- ✅ Confirmed `TIME_ZONE="Africa/Blantyre"` and `CELERY_TIMEZONE="Africa/Blantyre"`

### 2. Email Deliverability (`notifications/emailer.py`)
- ✅ Added `CANONICAL_HOST` to email template context for correct domain links
- ✅ Ensures consistent from name via `DEFAULT_FROM_EMAIL` setting

### 3. Idempotency & Transaction Safety (`notifications/services.py`, `notifications/signals.py`)
- ✅ Verified `NotificationEvent` unique constraint exists: `(event_type, recipient_email, dedupe_key)`
- ✅ All emitters use stable dedupe_key:
  - OTP: `OTP:{email}:{otp_id}`
  - Welcome manager: `WELCOME_MANAGER:{user_id}`
  - Welcome agent: `WELCOME_AGENT:{user_id}`
  - Sale instant: `SALE:{sale_id}`
  - Sale batch: `SALE_BATCH:{business_id}:{time_bucket}`
  - Daily summary: `DAILY_SUMMARY:{business_id}:{YYYY-MM-DD}`
  - High sales: `HIGH_SALES:{business_id}:{product_id}:{YYYY-MM-DD}:{threshold}`
  - Important: `IMPORTANT:{business_id}:{subject}:{YYYY-MM-DD}` (or passed-in dedupe)
- ✅ All email sending occurs after DB commit via `transaction.on_commit()`
- ✅ Sale completion hook uses `transaction.on_commit()` in signal handler

### 4. Performance & Spam Control (`notifications/services.py`)
- ✅ Documented batching thresholds:
  - If >10 sales in last 5 minutes: Use 2-minute buckets (SALE_BATCH)
  - Otherwise: Send instant notification (SALE_INSTANT)
- ✅ Added rate limiting: Max 30 SALE_* emails per recipient per hour
- ✅ Recipients filtered by `NotificationPreference` toggles (via `get_business_manager_emails`)

### 5. Error Handling & Admin UX (`notifications/admin.py`, `notifications/services.py`)
- ✅ Failures set `NotificationEvent.status=FAILED` and store `last_error`
- ✅ Added admin filters/search for:
  - `status` (PENDING, SENT, FAILED)
  - `event_type`
  - `business`
  - `recipient_email`
  - `created_at` (date hierarchy)
- ✅ Created `retry_failed_emails` management command

### 6. Production Operations (`notifications/management/commands/send_yesterday_sales_summary.py`)
- ✅ Command exits with code 0 on success (required for cron)
- ✅ Logs useful output for monitoring

---

## PRODUCTION CHECKLIST FOR RENDER

### Step 1: Environment Variables

Set these in Render Dashboard → Environment:

```bash
# Required for production
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DEFAULT_FROM_EMAIL=Emajinet <no-reply@emajinet.africa>
USE_CONSOLE_EMAIL=0

# Optional (for monitoring)
ADMIN_EMAIL=ops@emajinet.africa
```

**CRITICAL:** 
- `USE_CONSOLE_EMAIL=0` is REQUIRED in production
- `SENDGRID_API_KEY` must be set when `USE_CONSOLE_EMAIL=0`
- System will raise `RuntimeError` on startup if misconfigured

### Step 2: Verify Configuration

After setting env vars, restart the service and check logs:

```bash
# On Render shell or via SSH
python manage.py check
```

Expected output: No errors. If you see:
- `RuntimeError: CRITICAL: USE_CONSOLE_EMAIL=True is not allowed in production` → Set `USE_CONSOLE_EMAIL=0`
- `ImproperlyConfigured: USE_CONSOLE_EMAIL=0 requires SENDGRID_API_KEY` → Set `SENDGRID_API_KEY`

### Step 3: Test Email Sending

Run email debug command:

```bash
python manage.py email_debug
```

Expected output:
- Backend: `anymail.backends.sendgrid.EmailBackend`
- From email: `Emajinet <no-reply@emajinet.africa>`
- No warnings about console backend

Then send a test email:

```bash
python manage.py test_email your-email@example.com
```

**Verify:**
- Email arrives in inbox (check spam folder)
- From address is `no-reply@emajinet.africa`
- Subject is "Test Email from Emajinet"

### Step 4: Set Up Daily Summary Cron

In Render Dashboard → Cron Jobs:

**Schedule:** `0 23 * * *` (23:00 UTC = 01:00 Africa/Blantyre)

**Command:**
```bash
python manage.py send_yesterday_sales_summary
```

**Notes:**
- Runs daily at 01:00 Africa/Blantyre time (23:00 UTC)
- Exits with code 0 on success
- Logs output to Render logs
- Respects `NotificationPreference.daily_summary_email` toggles
- Uses dedupe key to prevent duplicates

### Step 5: Monitor Email Events

Check email notification events in Django Admin:

1. Go to `/admin/notifications/notificationevent/`
2. Filter by:
   - Status: `FAILED` (to see errors)
   - Event type: `DAILY_SUMMARY`, `SALE_INSTANT`, etc.
   - Business: Filter by specific business
3. Search by recipient email or dedupe_key

### Step 6: Retry Failed Emails (if needed)

If you see FAILED events:

```bash
python manage.py retry_failed_emails --limit 100
```

Or dry-run first:
```bash
python manage.py retry_failed_emails --limit 100 --dry-run
```

---

## Risky Areas Found & Mitigations

### 1. Console Backend in Production
**Risk:** Emails could silently fail to send if console backend is used in production.

**Mitigation:**
- Added hard guard: `RuntimeError` if `DEBUG=False` and `USE_CONSOLE_EMAIL=True`
- System will not start if misconfigured

### 2. Missing SendGrid API Key
**Risk:** Emails would fail silently if API key is missing.

**Mitigation:**
- Startup validation raises `ImproperlyConfigured` if `USE_CONSOLE_EMAIL=0` but key missing
- Clear error message guides operator to fix

### 3. Duplicate Emails
**Risk:** Multiple sends of the same email due to retries or race conditions.

**Mitigation:**
- Unique constraint on `(event_type, recipient_email, dedupe_key)`
- All emitters use stable, predictable dedupe keys
- `get_or_create` prevents duplicates

### 4. Email Spam
**Risk:** High-volume sales could flood recipients with emails.

**Mitigation:**
- Batching: >10 sales in 5 minutes → batch into 2-minute buckets
- Rate limiting: Max 30 SALE_* emails per recipient per hour
- Preference filtering: Respects user notification preferences

### 5. Transaction Safety
**Risk:** Emails sent before DB commit could reference non-existent data.

**Mitigation:**
- All email sending wrapped in `transaction.on_commit()`
- Sale completion hook uses `transaction.on_commit()` in signal

### 6. Unverified From Domain
**Risk:** Emails from unverified domain may be marked as spam.

**Mitigation:**
- Startup warning if `DEFAULT_FROM_EMAIL` domain is not `emajinet.africa`
- Operator can verify domain in SendGrid dashboard

### 7. Failed Emails Not Retried
**Risk:** Transient failures could leave emails unsent.

**Mitigation:**
- `retry_failed_emails` command allows safe retry
- Respects dedupe keys to prevent duplicates
- Admin interface shows failed events with error messages

---

## Testing Checklist

Before going live, verify:

- [ ] `USE_CONSOLE_EMAIL=0` set in production
- [ ] `SENDGRID_API_KEY` set and valid
- [ ] `DEFAULT_FROM_EMAIL` domain verified in SendGrid
- [ ] Test email received successfully
- [ ] Daily summary cron scheduled
- [ ] Admin can view/filter NotificationEvent records
- [ ] Failed emails can be retried via command
- [ ] Sale completion triggers email (check logs)
- [ ] Rate limiting prevents spam (test with >30 sales/hour)

---

## Support

If emails are not sending:

1. Check Render logs for errors
2. Run `python manage.py email_debug` to verify config
3. Check `/admin/notifications/notificationevent/` for FAILED events
4. Verify SendGrid API key is valid in SendGrid dashboard
5. Check SendGrid activity logs for delivery status

