# PayChangu Quick Reference Card

## 🎯 Goal Achieved
✅ **ALL billing payments now use PayChangu** (Airtel, Bank, Card)  
✅ **No more "fake success"** - payments go through PayChangu  
✅ **Subscriptions activate only after webhook confirms payment**

---

## 📋 Files Changed

| File | What Changed |
|------|-------------|
| `billing/models.py` | Added `tax_total` property to Invoice |
| `billing/views.py` | Rewrote `checkout()` to use PayChangu |
| `billing/views_paychangu.py` | Enhanced webhook to activate subscriptions |
| `templates/billing/success.html` | Updated to show "processing" state |
| `billing/tests/test_checkout_paychangu.py` | **NEW** - Comprehensive tests |

---

## 🔍 How to Verify

### 1. Check Database
```sql
SELECT provider, status FROM billing_paymenttransaction ORDER BY created_at DESC LIMIT 1;
```
**Expected:** `provider = PAYCHANGU`, `status = PENDING` or `SUCCESS`

### 2. Check Logs
```bash
grep "Initiating PayChangu payment" logs/app.log
grep "Webhook confirmed" logs/app.log
```

### 3. Check Browser
After clicking "Pay", URL should be:
```
https://checkout.paychangu.com/pay/...
```

NOT `/billing/success/`

---

## 🧪 Run Tests
```bash
# All PayChangu tests
pytest billing/tests/test_checkout_paychangu.py -v
pytest billing/tests/test_paychangu_webhook.py -v

# Expected: 8 new tests pass ✅
```

---

## 🚀 Manual Test (5 min)

1. **Setup:**
   ```bash
   export PAYCHANGU_SECRET_KEY="your-key"
   export PAYCHANGU_WEBHOOK_SECRET="your-secret"
   python manage.py runserver
   ```

2. **Click Pay:**
   - Go to `/billing/subscribe/`
   - Select plan
   - Click "Pay with Airtel Money"
   - Enter phone: `0991123456`
   - Submit

3. **Verify:**
   - Browser redirects to `checkout.paychangu.com`
   - Database: `SELECT * FROM billing_paymenttransaction ORDER BY created_at DESC LIMIT 1;`
   - Should show `provider = 'PAYCHANGU'`

4. **Simulate Webhook:**
   ```python
   python manage.py shell
   
   import json, hmac, hashlib, os
   from django.test import Client
   from billing.models import PaymentTransaction
   
   tx = PaymentTransaction.objects.filter(status='pending').latest('created_at')
   payload = {"tx_ref": tx.tx_ref, "status": "successful"}
   payload_bytes = json.dumps(payload).encode('utf-8')
   
   secret = os.environ.get('PAYCHANGU_WEBHOOK_SECRET')
   sig = hmac.new(secret.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()
   
   client = Client()
   response = client.post('/billing/paychangu/webhook/', 
                          data=payload_bytes, 
                          content_type='application/json',
                          HTTP_SIGNATURE=sig)
   
   print(f"Webhook: {response.status_code}")  # Should be 200
   tx.refresh_from_db()
   print(f"Transaction: {tx.status}")  # Should be 'success'
   print(f"Subscription: {tx.business.subscription.status}")  # Should be 'active'
   ```

---

## 📊 What Happens Now

### OLD FLOW (Before):
```
User clicks "Pay" 
  → Creates stub Payment record
  → Redirects to /billing/success/
  → Shows "Payment Received" (FAKE!)
  → Subscription NOT activated
```

### NEW FLOW (After):
```
User clicks "Pay"
  → Creates PaymentTransaction (provider=PAYCHANGU, status=PENDING)
  → Calls paychangu_service.create_checkout()
  → Logs: "Initiating PayChangu payment: tx_ref=..."
  → Redirects to https://checkout.paychangu.com/pay/...
  → User completes payment on PayChangu
  → PayChangu sends webhook to /billing/paychangu/webhook/
  → Webhook verifies signature
  → Marks transaction SUCCESS
  → Marks invoice PAID
  → Activates subscription (status=ACTIVE)
  → Logs: "Webhook confirmed: tx_ref=..., invoice marked PAID"
```

---

## 🔐 Environment Variables

```bash
# Required for PayChangu
export PAYCHANGU_PUBLIC_KEY="pk_live_..."
export PAYCHANGU_SECRET_KEY="sk_live_..."
export PAYCHANGU_WEBHOOK_SECRET="whsec_..."
export PAYCHANGU_API_BASE="https://api.paychangu.com/v1/"
```

---

## 📝 Key Logs to Watch

### Successful Payment Flow:
```
INFO: Initiating PayChangu payment: business=uuid-123, tx_ref=billing-abc-456, method=AIRTEL_MONEY, amount=20000
INFO: PayChangu checkout created: tx_ref=billing-abc-456, checkout_url=https://checkout.paychangu.com/pay/...
INFO: PayChangu webhook received for tx_ref=billing-abc-456
INFO: PayChangu transaction billing-abc-456 marked SUCCESS
INFO: Invoice INV-20231225-XYZ marked PAID for tx_ref billing-abc-456
INFO: Subscription activated for business uuid-123, tx_ref billing-abc-456
INFO: Webhook confirmed: tx_ref=billing-abc-456, status=SUCCESS, invoice marked PAID
```

---

## ❌ Common Issues

### Issue: "Payment system is not configured"
**Cause:** PayChangu env vars not set  
**Fix:** Set `PAYCHANGU_SECRET_KEY`, `PAYCHANGU_WEBHOOK_SECRET`, `PAYCHANGU_API_BASE`

### Issue: Webhook returns 401 "Invalid signature"
**Cause:** Webhook secret mismatch  
**Fix:** Ensure `PAYCHANGU_WEBHOOK_SECRET` matches PayChangu dashboard

### Issue: Subscription not activating after payment
**Cause:** Webhook not reaching server  
**Fix:** 
1. Check webhook URL in PayChangu dashboard
2. Use cloudflared tunnel for local testing
3. Check logs for "PayChangu webhook received"

---

## 🎯 Success Criteria

✅ Database shows `provider="PAYCHANGU"` for all transactions  
✅ Logs show "Initiating PayChangu payment" before redirect  
✅ Browser redirects to `checkout.paychangu.com`  
✅ Webhook logs show "invoice marked PAID"  
✅ Subscription activates ONLY after webhook  
✅ Tests pass: `pytest billing/tests/test_checkout_paychangu.py -v`  

---

## 📚 Full Documentation

- **Complete Implementation:** `PAYCHANGU_IMPLEMENTATION_COMPLETE.md`
- **Changes Summary:** `PAYCHANGU_CHANGES_SUMMARY.md`
- **This Card:** `PAYCHANGU_QUICK_REFERENCE.md`

---

**Status:** ✅ PRODUCTION READY  
**Date:** 2023-12-30  
**Version:** 1.0
