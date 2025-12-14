# Email OTP Smoke Test Guide

This document provides step-by-step instructions for manually testing the Email OTP functionality.

## Prerequisites

1. **Environment Variables Set:**
   ```bash
   export SENDGRID_API_KEY="your-sendgrid-api-key"
   export DEFAULT_FROM_EMAIL="Emajinet <noreply@emajinet.africa>"
   export ENABLE_EMAIL_OTP=true  # Optional: enable OTP for signup
   ```

2. **Dependencies Installed:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Database Migrations Applied:**
   ```bash
   python manage.py migrate
   ```

## Local Testing

### Step 1: Test Email Backend

1. **Send a test email:**
   ```bash
   python manage.py send_test_email your-email@gmail.com
   ```
   
   **Expected:** 
   - Command completes successfully
   - Email arrives in your inbox
   - Subject: "Test Email from Emajinet"

2. **Check SendGrid Activity Dashboard:**
   - Log into SendGrid
   - Navigate to Activity
   - Verify the email send event appears

### Step 2: Test OTP Request Endpoint

1. **Request an OTP via API:**
   ```bash
   curl -X POST http://localhost:8000/accounts/auth/otp/request/ \
     -H "Content-Type: application/json" \
     -H "X-CSRFToken: <your-csrf-token>" \
     -d '{"email": "test@example.com", "purpose": "signup"}'
   ```
   
   **Expected Response:**
   ```json
   {"ok": true}
   ```
   
   **Check:**
   - Email arrives with 6-digit code
   - Subject contains "Verify your email address"
   - Code is clearly displayed in email body

2. **Test Rate Limiting:**
   - Send 4+ requests in quick succession
   - 4th request should return HTTP 429 or error message
   ```json
   {"ok": false, "error": "Too many requests. Please try again later."}
   ```

### Step 3: Test OTP Verify Endpoint

1. **Verify with correct code:**
   ```bash
   curl -X POST http://localhost:8000/accounts/auth/otp/verify/ \
     -H "Content-Type: application/json" \
     -H "X-CSRFToken: <your-csrf-token>" \
     -d '{"email": "test@example.com", "purpose": "signup", "code": "123456"}'
   ```
   
   **Expected Response (if code is correct):**
   ```json
   {"ok": true}
   ```
   
   **Expected Response (if code is wrong):**
   ```json
   {"ok": false, "error": "Invalid or expired code"}
   ```

2. **Test Invalid Code:**
   - Use wrong code → Should return error
   - Try same wrong code 5+ times → Should still fail (attempt limit)

3. **Test Expired Code:**
   - Wait 10+ minutes (OTP_TTL_MINUTES)
   - Try to verify → Should return "Invalid or expired code"

### Step 4: Test Signup Flow with OTP

1. **Enable OTP for Signup:**
   ```bash
   export ENABLE_EMAIL_OTP=true
   ```

2. **Complete Signup Wizard:**
   - Navigate to `/accounts/signup/`
   - Complete all wizard steps (0-4)
   - After step 4, you should be redirected to `/accounts/signup/verify-email/`

3. **Verify Email:**
   - Check your email for the verification code
   - Enter the 6-digit code on the verification page
   - Click "Verify"
   
   **Expected:**
   - Success message: "Email verified! Welcome to Emajinet!"
   - Redirected to dashboard
   - User is logged in
   - Profile.email_verified = True

4. **Test Resend:**
   - On verification page, click "Resend Code"
   - New email should arrive
   - Old code should no longer work

## Production/Staging Testing

### Step 1: Verify Environment Variables

1. **Check Render Environment:**
   - Navigate to Render dashboard
   - Verify `SENDGRID_API_KEY` is set
   - Verify `DEFAULT_FROM_EMAIL` is set
   - Optionally set `ENABLE_EMAIL_OTP=true`

### Step 2: Test Email Sending

1. **Send Test Email:**
   ```bash
   # On Render shell or via management command
   python manage.py send_test_email your-email@gmail.com
   ```

2. **Check SendGrid Activity:**
   - Log into SendGrid
   - Navigate to Activity
   - Filter by your email address
   - Verify send event appears with status "Delivered"

### Step 3: Test Endpoints

1. **Test OTP Request:**
   ```bash
   curl -X POST https://your-domain.com/accounts/auth/otp/request/ \
     -H "Content-Type: application/json" \
     -H "X-CSRFToken: <csrf-token>" \
     -d '{"email": "test@example.com", "purpose": "signup"}'
   ```

2. **Test OTP Verify:**
   ```bash
   curl -X POST https://your-domain.com/accounts/auth/otp/verify/ \
     -H "Content-Type: application/json" \
     -H "X-CSRFToken: <csrf-token>" \
     -d '{"email": "test@example.com", "purpose": "signup", "code": "123456"}'
   ```

### Step 4: Test Full Signup Flow

1. **Complete Signup:**
   - Navigate to signup page
   - Complete wizard
   - Verify email arrives
   - Enter code and verify
   - Confirm redirect to dashboard

## Troubleshooting

### Email Not Sending

1. **Check SendGrid API Key:**
   ```bash
   echo $SENDGRID_API_KEY
   ```

2. **Check Email Backend:**
   ```python
   # In Django shell
   from django.conf import settings
   print(settings.EMAIL_BACKEND)
   print(settings.ANYMAIL)
   ```

3. **Check Logs:**
   - Look for errors in application logs
   - Check SendGrid Activity for bounces/rejections

### OTP Not Working

1. **Check Database:**
   ```python
   # In Django shell
   from circuitcity.accounts.models import EmailOTP
   EmailOTP.objects.filter(email="test@example.com").order_by("-created_at")
   ```

2. **Check Cache:**
   ```python
   # In Django shell
   from django.core.cache import cache
   cache.clear()  # Clear rate limit cache
   ```

3. **Check Settings:**
   ```python
   # In Django shell
   from django.conf import settings
   print(getattr(settings, "OTP_TTL_MINUTES", 10))
   print(getattr(settings, "OTP_MAX_ATTEMPTS", 5))
   ```

### Signup Not Redirecting to Verification

1. **Check ENABLE_EMAIL_OTP:**
   ```bash
   echo $ENABLE_EMAIL_OTP
   ```

2. **Check User Creation:**
   - Verify user was created in database
   - Check Profile.email_verified is False

## Acceptance Criteria Checklist

- [ ] `python manage.py check` passes
- [ ] Migrations apply cleanly
- [ ] Tests pass: `python manage.py test circuitcity.accounts.tests_email_otp`
- [ ] Local send test works (with SendGrid key set)
- [ ] OTP request endpoint works end-to-end
- [ ] OTP verify endpoint works end-to-end
- [ ] Signup verification flow works without breaking existing logins
- [ ] Rate limiting works (429 after 3 requests/minute)
- [ ] Expired OTPs are rejected
- [ ] Attempt limit works (5 attempts max)
- [ ] Existing users can still log in (no regressions)

## Notes

- OTP codes expire after 10 minutes (configurable via `OTP_TTL_MINUTES`)
- Rate limit: 3 requests per minute per email/purpose (configurable via `OTP_RATE_LIMIT_PER_MINUTE`)
- Max attempts: 5 per OTP (configurable via `OTP_MAX_ATTEMPTS`)
- OTPs are hashed at rest (never stored in plaintext)
- Email verification is optional (controlled by `ENABLE_EMAIL_OTP` env var)
- Existing users are not forced to verify (only new signups when enabled)

