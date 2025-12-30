# PayChangu - Verify Logs & URL

## ✅ What to Look For

When you click "Pay with Airtel Money", you should see these logs:

---

## 📊 Expected Log Sequence

```
INFO: Initiating PayChangu payment: business=<uuid>, invoice=<uuid>, tx_ref=billing-abc-123, method=AIRTEL_MONEY, amount=20000

INFO: PayChangu create_checkout: POST https://api.paychangu.com/payment
  Headers: Authorization: Bearer sk_test_...xyz, Content-Type: application/json
  Payload: tx_ref=billing-abc-123, amount=20000, currency=MWK

INFO: PayChangu response: HTTP 200

INFO: PayChangu checkout created successfully: tx_ref=billing-abc-123, checkout_url=https://checkout.paychangu.com/pay/xyz123
```

---

## ✅ Verify These Details

### 1. URL Must Be Correct
```
POST https://api.paychangu.com/payment
```

**✅ Correct:**
- `https://api.paychangu.com/payment`

**❌ Wrong:**
- `https://api.paychangu.com/v1/payments`
- `https://api.paychangu.com/payments`
- `https://api.paychangu.com/v1/payment`

---

### 2. Headers Must Include Authorization
```
Headers: Authorization: Bearer sk_test_...xyz, Content-Type: application/json
```

**Check:**
- ✅ Starts with `Bearer`
- ✅ Secret key is masked (shows only first 8 + last 4 chars)
- ✅ Includes `Content-Type: application/json`

---

### 3. HTTP Status Should Be 200
```
INFO: PayChangu response: HTTP 200
```

**If not 200:**
- Check error logs below for full details

---

## 🔴 Error Scenario Examples

### Example 1: Wrong Endpoint (405)
```
INFO: PayChangu create_checkout: POST https://api.paychangu.com/payment
  Headers: Authorization: Bearer sk_test_...xyz, Content-Type: application/json
  Payload: tx_ref=billing-abc-123, amount=20000, currency=MWK

ERROR: PayChangu checkout failed:
  URL: POST https://api.paychangu.com/payment
  Status Code: 405
  Error: POST not supported for route v1/payments
  Response Body: {"error": "Method not allowed"}
```

**What User Sees:**
```
⚠️ Payment initiation failed: Payment provider endpoint error. Please contact support.
```

---

### Example 2: Invalid Credentials (401)
```
INFO: PayChangu create_checkout: POST https://api.paychangu.com/payment
  Headers: Authorization: Bearer sk_test_...xyz, Content-Type: application/json
  Payload: tx_ref=billing-def-456, amount=15000, currency=MWK

ERROR: PayChangu checkout failed:
  URL: POST https://api.paychangu.com/payment
  Status Code: 401
  Error: Invalid API credentials
  Response Body: {"error": "Unauthorized", "message": "Invalid API credentials"}
```

**What User Sees:**
```
⚠️ Payment initiation failed: Payment provider authentication failed. Please contact support.
```

---

### Example 3: Invalid Request (400)
```
INFO: PayChangu create_checkout: POST https://api.paychangu.com/payment
  Headers: Authorization: Bearer sk_test_...xyz, Content-Type: application/json
  Payload: tx_ref=billing-ghi-789, amount=5000, currency=MWK

ERROR: PayChangu checkout failed:
  URL: POST https://api.paychangu.com/payment
  Status Code: 400
  Error: Amount must be at least 100
  Response Body: {"error": "Bad Request", "message": "Amount must be at least 100"}
```

**What User Sees:**
```
⚠️ Payment initiation failed: Invalid payment request: Amount must be at least 100. Please try again or contact support.
```

---

## 🧪 Quick Test Steps

### Step 1: Watch Logs
```bash
# Terminal 1: Start server
python manage.py runserver

# Terminal 2: Watch PayChangu logs
tail -f logs/django.log | grep -A 3 "PayChangu"
```

### Step 2: Trigger Payment
1. Go to `http://localhost:8000/billing/subscribe/`
2. Login as manager
3. Select a plan
4. Click "Pay with Airtel Money"
5. Enter phone: `0991123456`
6. Click Submit

### Step 3: Check Logs
Look for these lines in order:

1. ✅ **Initiation:** `Initiating PayChangu payment`
2. ✅ **URL:** `POST https://api.paychangu.com/payment`
3. ✅ **Headers:** `Authorization: Bearer sk_...`
4. ✅ **Status:** `PayChangu response: HTTP 200`
5. ✅ **Success:** `PayChangu checkout created successfully`

### Step 4: Check Browser
- ✅ Should redirect to `checkout.paychangu.com`
- ✅ OR show error message at top of page (if failed)

---

## 🔍 Debugging Checklist

If you see HTTP 405:
- [ ] Check URL in logs - should be `/payment` not `/payments`
- [ ] Check base URL - should be `https://api.paychangu.com` (no `/v1`)
- [ ] Restart server after changing env vars

If you see HTTP 401:
- [ ] Check `PAYCHANGU_SECRET_KEY` env var
- [ ] Verify key starts with `sk_test_` or `sk_live_`
- [ ] Check PayChangu dashboard for correct key

If you see HTTP 400:
- [ ] Check error message in logs for specific issue
- [ ] Common issues: amount too low, invalid currency, missing fields

If no redirect happens:
- [ ] Check browser console for errors
- [ ] Check if `checkout_url` is in response
- [ ] Look for error message on checkout page

---

## ✅ Success Indicators

**In Logs:**
```
✅ URL is POST https://api.paychangu.com/payment
✅ Headers include Authorization: Bearer
✅ Response is HTTP 200
✅ checkout_url is present
```

**In Browser:**
```
✅ Redirects to checkout.paychangu.com
✅ No error messages shown
```

**In Database:**
```sql
SELECT provider, status, checkout_url 
FROM billing_paymenttransaction 
ORDER BY created_at DESC LIMIT 1;

-- Should show:
-- provider: PAYCHANGU
-- status: pending
-- checkout_url: https://checkout.paychangu.com/...
```

---

## 📝 Quick Copy-Paste Commands

### Watch Logs
```bash
tail -f logs/django.log | grep -E "(PayChangu|Initiating)"
```

### Check Last Transaction
```bash
python manage.py shell -c "
from billing.models import PaymentTransaction
tx = PaymentTransaction.objects.latest('created_at')
print(f'URL: {tx.checkout_url}')
print(f'Status: {tx.status}')
print(f'Provider: {tx.provider}')
"
```

### Check Settings
```bash
python manage.py shell -c "
from django.conf import settings
print(f'Base: {settings.PAYCHANGU_API_BASE}')
print(f'Key: {settings.PAYCHANGU_SECRET_KEY[:10]}...')
"
```

---

## 🎯 Summary

**New logs show:**
1. ✅ Exact URL: `POST https://api.paychangu.com/payment`
2. ✅ Headers with masked secret
3. ✅ HTTP status code for every request
4. ✅ Full error details when failing
5. ✅ User-friendly error on checkout page

**All you need to verify:**
- Logs show correct URL
- HTTP 200 response
- Browser redirects to PayChangu

**That's it!** 🚀

