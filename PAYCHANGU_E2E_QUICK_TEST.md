# PayChangu End-to-End - Quick Test Guide

## 🧪 Quick Test (5 Minutes)

### Step 1: Run Automated Tests
```bash
pytest billing/tests/test_checkout_paychangu.py -v
```

**Expected:** 17 tests pass ✅
- 8 original tests (checkout + basic webhook)
- 6 new tests (return page + polling API)
- 3 new tests (webhook hardening)

---

### Step 2: Manual Flow Test

```bash
# Terminal 1: Start server
python manage.py runserver

# Terminal 2: Start cloudflared (for webhooks)
cloudflared tunnel --url http://localhost:8000
# Note the public URL (e.g., https://xxx.trycloudflare.com)
```

**In Browser:**
1. Go to `http://localhost:8000/billing/subscribe/`
2. Login as manager
3. Select any plan
4. Click "Pay with Airtel Money"
5. Enter phone: `0991123456`
6. Click Submit

**Expected:**
- ✅ Redirects to PayChangu checkout page
- ✅ URL is `https://checkout.paychangu.com/pay/...`

---

### Step 3: Test Return Page Polling

**After completing payment on PayChangu:**
1. Browser returns to your site
2. **Watch the return page:**
   - ✅ Shows spinner
   - ✅ Message: "Payment is being processed..."
   - ✅ Status updates every 2 seconds
   - ✅ Reference shows: `billing-xxx-123`

**Wait for webhook or test status API:**

---

### Step 4: Test Status API

```bash
python manage.py shell
```

```python
from billing.models import PaymentTransaction
from django.test import Client

# Get latest transaction
tx = PaymentTransaction.objects.latest('created_at')
print(f"Status: {tx.status}, tx_ref: {tx.tx_ref}")

# Test status API
user = tx.created_by
client = Client()
client.force_login(user)

response = client.get(f'/billing/api/payment-status/?tx_ref={tx.tx_ref}')
print(response.json())
# Expected: {"status": "pending" or "success", ...}
```

---

### Step 5: Simulate Webhook

```bash
python manage.py shell
```

```python
import json, hmac, hashlib, os
from django.test import Client
from billing.models import PaymentTransaction

tx = PaymentTransaction.objects.filter(status='pending').latest('created_at')

# Build payload with alternate field name
payload = {
    "event": "payment.success",
    "reference": tx.tx_ref,  # Using 'reference' not 'tx_ref'
    "status": "successful",
}
payload_bytes = json.dumps(payload).encode('utf-8')

# Sign payload
secret = os.environ.get('PAYCHANGU_WEBHOOK_SECRET')
sig = hmac.new(secret.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()

# Send webhook
client = Client()
response = client.post(
    '/billing/paychangu/webhook/',
    data=payload_bytes,
    content_type='application/json',
    HTTP_SIGNATURE=sig
)

print(f"Webhook: {response.status_code}")  # Should be 200

# Check transaction status
tx.refresh_from_db()
print(f"Transaction: {tx.status}")  # Should be 'success'

# Check subscription
sub = tx.business.subscription
print(f"Subscription: {sub.status}")  # Should be 'active'
```

---

### Step 6: Verify Polling Success

**After webhook (or status check):**

**In Browser:**
- ✅ Page detects success
- ✅ Shows: "Payment Confirmed! ✓"
- ✅ Auto-redirects to dashboard after 2 seconds

---

## ✅ Success Indicators

### 1. Tests Pass
```
test_checkout_airtel_creates_paychangu_transaction PASSED
test_return_page_renders_with_tx_ref PASSED
test_payment_status_api_success PASSED
test_webhook_accepts_reference_field PASSED
test_webhook_idempotent_on_repeated_calls PASSED
... (17 tests total)
```

### 2. Logs Show Complete Flow
```
INFO: Initiating PayChangu payment: tx_ref=billing-abc-123
INFO: PayChangu create_checkout: POST https://api.paychangu.com/payment
INFO: PayChangu response: HTTP 200
INFO: PayChangu return: tx_ref=billing-abc-123
INFO: PayChangu webhook received for tx_ref=billing-abc-123
INFO: PayChangu transaction billing-abc-123 marked SUCCESS
INFO: Invoice INV-... marked PAID
INFO: Subscription activated
```

### 3. Return Page Behaves Correctly
- Shows spinner while pending
- Polls every 2 seconds
- Auto-redirects on success
- Shows error if failed

### 4. Database Shows Results
```sql
-- Check transaction
SELECT provider, status, checkout_url 
FROM billing_paymenttransaction 
ORDER BY created_at DESC LIMIT 1;
-- Expected: provider=PAYCHANGU, status=success

-- Check subscription
SELECT status, last_payment_at 
FROM billing_businesssubscription 
ORDER BY updated_at DESC LIMIT 1;
-- Expected: status=active, last_payment_at=<recent timestamp>
```

---

## 🐛 Quick Troubleshooting

### Issue: Polling Doesn't Detect Success

**Check:**
1. Webhook was sent: `grep "webhook received" logs/django.log`
2. Transaction is SUCCESS: `PaymentTransaction.objects.latest('created_at').status`
3. Status API returns success: Test in shell (see Step 4)

**Fix:** Simulate webhook manually (see Step 5)

---

### Issue: Return Page Shows Error

**Check:**
1. tx_ref in URL: `...paychangu/return/?tx_ref=billing-xxx`
2. Transaction exists: `PaymentTransaction.objects.filter(tx_ref='...')`
3. User belongs to correct business

**Fix:** Ensure correct tx_ref is passed

---

### Issue: Status API Returns 404

**Cause:** Transaction not found for current business (multi-tenant isolation working!)

**Check:**
```python
tx = PaymentTransaction.objects.get(tx_ref='billing-xxx-123')
print(f"Business: {tx.business.id}")

user = User.objects.get(email='manager@test.com')
print(f"User's business: {user.memberships.first().business.id}")

# Should match!
```

---

### Issue: Webhook Not Received

**Check:**
1. Cloudflared running: `ps aux | grep cloudflared`
2. Public URL configured in PayChangu dashboard
3. Webhook secret matches: `echo $PAYCHANGU_WEBHOOK_SECRET`

**Fix:** 
- Restart cloudflared
- Update webhook URL in PayChangu dashboard
- Simulate webhook manually (see Step 5)

---

## 📊 Quick Verification Commands

### Check Latest Transaction
```bash
python manage.py shell -c "
from billing.models import PaymentTransaction
tx = PaymentTransaction.objects.latest('created_at')
print(f'Status: {tx.status}')
print(f'URL: {tx.checkout_url}')
print(f'Provider: {tx.provider}')
"
```

### Check Status API
```bash
# Get tx_ref first
TX_REF=$(python manage.py shell -c "from billing.models import PaymentTransaction; print(PaymentTransaction.objects.latest('created_at').tx_ref)")

# Test API (must login first in browser, get session cookie)
curl -H "Cookie: sessionid=<your-session>" \
  "http://localhost:8000/billing/api/payment-status/?tx_ref=$TX_REF"
```

### Check Subscription
```bash
python manage.py shell -c "
from billing.models import BusinessSubscription
sub = BusinessSubscription.objects.latest('updated_at')
print(f'Status: {sub.status}')
print(f'Last payment: {sub.last_payment_at}')
"
```

---

## ✅ Final Checklist

- [ ] All 17 tests pass
- [ ] Return page shows spinner and polls
- [ ] Status API returns correct status
- [ ] Status API is business-scoped (404 for other businesses)
- [ ] Webhook accepts `reference` field
- [ ] Webhook is idempotent (no double-activation)
- [ ] Polling detects success and auto-redirects
- [ ] Subscription activates after webhook
- [ ] Logs show complete flow

**If all checked:** ✅ End-to-end flow is working!

---

## 🎯 Expected Test Time

- **Automated tests:** 30 seconds
- **Manual flow:** 2-3 minutes
- **Status API test:** 1 minute
- **Webhook simulation:** 1 minute

**Total:** ~5 minutes for complete verification ✅

