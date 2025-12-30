# PayChangu Integration - Manual Testing Checklist

This document provides step-by-step instructions for manually testing the PayChangu payment integration in **TEST MODE**.

## Prerequisites

1. ✅ PayChangu account created at https://dashboard.paychangu.com/
2. ✅ TEST mode API keys obtained from dashboard
3. ✅ Local development server running or staging deployment available

---

## Step 1: Configure Environment Variables

Add the following to your `.env` file (never commit this file to Git):

```env
PAYCHANGU_MODE=test
PAYCHANGU_PUBLIC_KEY=pub-test-w2kyBmbgbr7m76yNjyTIh2oH71eM3VPQ
PAYCHANGU_SECRET_KEY=sec-test-npyGRLGM6VLkT6OAWUgqjAI9t7ZI2zWT
PAYCHANGU_WEBHOOK_SECRET=your-random-secret-string-here
PAYCHANGU_API_BASE=https://api.paychangu.com/v1/
```

**Important:**
- `PAYCHANGU_WEBHOOK_SECRET` should be a random string you generate (e.g., `openssl rand -hex 32`)
- Keep this secret safe - it's used to verify webhook authenticity

---

## Step 2: Run Database Migrations

Apply the new PayChangu migrations:

```bash
python manage.py migrate billing
```

This creates:
- `PaymentTransaction` model for tracking PayChangu transactions
- Adds `PAYCHANGU` to Payment provider choices

---

## Step 3: Expose Local Webhook URL (Development Only)

PayChangu needs a public HTTPS URL to send webhooks. Use **ngrok** or deploy to staging:

### Option A: ngrok (Local Development)

```bash
ngrok http 8000
```

You'll get a URL like: `https://abc123.ngrok-free.app`

Your webhook URL will be:
```
https://abc123.ngrok-free.app/billing/paychangu/webhook/
```

### Option B: Deploy to Staging

If using Render/Heroku/etc., your webhook URL will be:
```
https://your-staging-domain.onrender.com/billing/paychangu/webhook/
```

---

## Step 4: Configure PayChangu Dashboard

1. Go to https://dashboard.paychangu.com/
2. Navigate to **Settings** → **Webhooks** (TEST MODE)
3. Add webhook URL:
   ```
   https://your-public-url/billing/paychangu/webhook/
   ```
4. Set webhook secret to match your `PAYCHANGU_WEBHOOK_SECRET` from .env
5. Enable webhook events:
   - ✅ `payment.success`
   - ✅ `payment.failed`
   - ✅ `payment.pending`

---

## Step 5: Test Payment Flow

### 5.1. Initiate Checkout

**API Endpoint:**
```
POST /billing/paychangu/initiate/
```

**Required:**
- User must be logged in
- User must have active business/location

**POST Parameters:**
- `plan_code`: Subscription plan slug (e.g., "starter", "premium")
- `amount`: (optional) Payment amount, defaults to plan amount

**Example using curl:**

```bash
# Login first to get session cookie
curl -X POST http://localhost:8000/accounts/login/ \
  -d "username=manager@test.com&password=pass1234" \
  -c cookies.txt

# Initiate PayChangu checkout
curl -X POST http://localhost:8000/billing/paychangu/initiate/ \
  -b cookies.txt \
  -d "plan_code=starter" \
  -H "X-CSRFToken: YOUR_CSRF_TOKEN"
```

**Expected Response:**
```json
{
  "status": "success",
  "checkout_url": "https://checkout.paychangu.com/...",
  "tx_ref": "pc-1-abc123-1234567890",
  "message": "Checkout created successfully."
}
```

### 5.2. Complete Payment

1. Open the `checkout_url` in a browser
2. PayChangu will show payment options (Mobile Money, Card, etc.)
3. Use **TEST** payment credentials:
   - For Airtel Money TEST: Use test phone number from PayChangu docs
   - For TNM Mpamba TEST: Use test phone number from PayChangu docs
4. Complete the test payment

### 5.3. Verify Webhook Reception

**Check webhook was received:**

1. View webhook logs in PayChangu dashboard
2. Check your application logs for:
   ```
   PayChangu webhook received for tx_ref=pc-1-abc123-1234567890
   PayChangu transaction pc-1-abc123-1234567890 marked SUCCESS
   ```

**Check database:**

```python
from billing.models import PaymentTransaction, WebhookEvent

# Check transaction status
tx = PaymentTransaction.objects.get(tx_ref="pc-1-abc123-1234567890")
print(tx.status)  # Should be 'success'
print(tx.raw_webhook_payload)  # Webhook data
print(tx.raw_verify_payload)  # Verification data

# Check webhook event was logged
events = WebhookEvent.objects.filter(provider="paychangu")
print(events.latest("created_at").payload)
```

### 5.4. Test Return Page

After payment, PayChangu redirects to:
```
http://localhost:8000/billing/paychangu/return/?tx_ref=pc-1-abc123-1234567890&status=successful
```

**Expected:**
- ✅ Page shows "Payment successful!" message
- ✅ Transaction details displayed (amount, date, status)
- ✅ "Go to Dashboard" button works

---

## Step 6: Run Automated Tests

Run the PayChangu test suite:

```bash
# Run all PayChangu webhook tests
pytest billing/tests/test_paychangu_webhook.py -v

# Run specific test
pytest billing/tests/test_paychangu_webhook.py::TestPayChanguWebhookSignature::test_webhook_rejects_invalid_signature -v
```

**Expected:**
- ✅ All tests pass
- ✅ `test_webhook_rejects_invalid_signature` → 401 response
- ✅ `test_webhook_accepts_valid_signature_and_updates_transaction` → 200 + SUCCESS status

---

## Step 7: Test Edge Cases

### 7.1. Invalid Signature Attack

**Simulate malicious webhook:**

```bash
curl -X POST http://localhost:8000/billing/paychangu/webhook/ \
  -H "Content-Type: application/json" \
  -H "Signature: fake-signature-12345" \
  -d '{"tx_ref":"pc-1-abc123-1234567890","status":"successful"}'
```

**Expected:**
- ✅ Response: `401 Unauthorized`
- ✅ Transaction status unchanged (still PENDING)
- ✅ Log message: "PayChangu webhook signature verification failed"

### 7.2. Idempotency (Duplicate Webhook)

Send the same valid webhook twice:

**Expected:**
- ✅ First call: Updates transaction to SUCCESS
- ✅ Second call: Returns 200 but skips processing (already SUCCESS)
- ✅ Log message: "transaction already SUCCESS, skipping"

### 7.3. Unknown Transaction Reference

Send webhook for non-existent tx_ref:

**Expected:**
- ✅ Response: `200 OK` (to avoid provider retries)
- ✅ Log message: "transaction not found for tx_ref unknown-xyz"

### 7.4. Failed Payment

Complete a test payment but cancel/fail it:

**Expected:**
- ✅ Webhook received with `status=failed`
- ✅ Transaction marked as `FAILED`
- ✅ Return page shows "Payment failed. Please try again."

---

## Step 8: Multi-Tenant Isolation Check

**Goal:** Ensure no cross-business data leakage

1. Create two businesses: Business A and Business B
2. Create transaction for Business A with tx_ref="tx-a"
3. Send webhook for "tx-a"
4. **Verify:**
   - ✅ Only Business A's transaction updated
   - ✅ Business B's transactions unchanged
   - ✅ Webhook payload includes correct `business_id` and `location_id` in meta

---

## Step 9: Production Readiness Checks

Before going live:

### ✅ Security Checklist

- [ ] `PAYCHANGU_WEBHOOK_SECRET` is strong (32+ random characters)
- [ ] Webhook secret is NOT printed in logs
- [ ] API keys are NOT committed to Git
- [ ] Production guard active: DEBUG=False prevents PAYCHANGU_MODE=test

### ✅ Configuration Checklist

- [ ] PAYCHANGU_MODE=live in production .env
- [ ] PAYCHANGU_PUBLIC_KEY and SECRET_KEY using live keys (pub-live-..., sec-live-...)
- [ ] Webhook URL in PayChangu dashboard points to production domain (HTTPS)
- [ ] Webhook secret in dashboard matches production PAYCHANGU_WEBHOOK_SECRET

### ✅ Monitoring Checklist

- [ ] Application logs configured for production (e.g., Sentry, CloudWatch)
- [ ] Webhook failures trigger alerts
- [ ] Database backups enabled
- [ ] PaymentTransaction records monitored for stuck PENDING status

---

## Troubleshooting

### Webhook Not Received

1. Check ngrok is running: `curl https://your-ngrok-url/health`
2. Check PayChangu dashboard webhook logs for delivery attempts
3. Verify webhook URL is correct and accessible
4. Check firewall/security groups allow incoming HTTPS

### Invalid Signature Errors (But Should Be Valid)

1. Verify `PAYCHANGU_WEBHOOK_SECRET` matches dashboard exactly
2. Check for extra whitespace in .env file
3. Restart server after changing .env
4. Confirm webhook payload is raw bytes (not pre-parsed JSON)

### Transaction Stuck in PENDING

1. Check PayChangu dashboard for payment status
2. Manually trigger verification:
   ```python
   from billing import paychangu_service
   result = paychangu_service.verify_payment("tx_ref")
   print(result)
   ```
3. Check network connectivity to PayChangu API
4. Verify API keys are correct and active

---

## API Endpoints Summary

| Endpoint | Method | Purpose | Auth Required |
|----------|--------|---------|---------------|
| `/billing/paychangu/initiate/` | POST | Create checkout session | ✅ Yes |
| `/billing/paychangu/webhook/` | POST | Receive payment notifications | ❌ No (signature verified) |
| `/billing/paychangu/return/` | GET | Browser redirect after payment | ✅ Yes |
| `/billing/paychangu/callback/` | GET/POST | Alternative callback endpoint | ❌ No |

---

## Support

If you encounter issues:

1. Check PayChangu documentation: https://docs.paychangu.com/
2. Review application logs for error messages
3. Contact PayChangu support: support@paychangu.com
4. Report bugs to your development team

---

## Appendix: Test Credentials

PayChangu TEST mode credentials (from dashboard):

```
Public Key: pub-test-w2kyBmbgbr7m76yNjyTIh2oH71eM3VPQ
Secret Key: sec-test-npyGRLGM6VLkT6OAWUgqjAI9t7ZI2zWT
```

**Test Mobile Money Numbers:**
- Airtel Money: (Check PayChangu docs for latest test numbers)
- TNM Mpamba: (Check PayChangu docs for latest test numbers)

**Note:** Test transactions won't charge real money. Use live keys only in production.

