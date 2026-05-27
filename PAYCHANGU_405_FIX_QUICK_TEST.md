# PayChangu 405 Fix - Quick Test Guide

## ✅ What Was Fixed

**Problem:** HTTP 405 error when clicking "Pay"

**Fix:** Changed endpoint from `/v1/payments` to `/payment`

---

## 🧪 Quick Test (2 minutes)

### Step 1: Verify Settings
```bash
python manage.py shell
```

```python
from django.conf import settings
print(f"Base URL: {settings.PAYCHANGU_API_BASE}")
# Should print: https://api.paychangu.com (NO /v1)
```

If it still shows `/v1/`, restart your server.

---

### Step 2: Test Payment Flow
```bash
# Ensure environment variable is NOT overriding with /v1
unset PAYCHANGU_API_BASE  # or set it correctly

# Start server
python manage.py runserver
```

**In Browser:**
1. Go to `http://localhost:8000/billing/subscribe/`
2. Login as manager
3. Select any plan
4. Click "Pay with Airtel Money"
5. Enter phone: `0991123456`
6. Click Submit

**Expected Result:**
- ✅ Redirects to `https://checkout.paychangu.com/pay/...`
- ✅ **NO 405 error**

**Check Logs:**
```bash
# Look for this in console/logs:
INFO: Initiating PayChangu payment: tx_ref=billing-...
INFO: PayChangu checkout created: tx_ref=billing-..., checkout_url=https://checkout.paychangu.com/...
```

---

### Step 3: Run Tests
```bash
pytest billing/tests/test_checkout_paychangu.py::TestPayChanguCorrectEndpoint -v
```

**Expected Output:**
```
test_create_checkout_calls_correct_endpoint PASSED
test_create_checkout_handles_405_error PASSED
```

---

## 🐛 If Still Getting 405

### Check 1: Base URL
```bash
python manage.py shell
```
```python
from django.conf import settings
print(settings.PAYCHANGU_API_BASE)
# MUST be: https://api.paychangu.com (no /v1)
```

### Check 2: Environment Variable
```bash
echo $PAYCHANGU_API_BASE
# Should be empty OR "https://api.paychangu.com"
# If it shows /v1, that's the problem!

# Fix:
export PAYCHANGU_API_BASE="https://api.paychangu.com"
```

### Check 3: Restart Server
After changing environment variables:
```bash
# Kill old server (Ctrl+C)
python manage.py runserver
```

---

## 📊 Verify Endpoint is Correct

Add temporary debug log to see exact URL being called:

```python
# In billing/paychangu_service.py, add this before line 127:
logger.info(f"DEBUG: Calling PayChangu endpoint: {url}")
```

Run payment flow and check logs:
```
INFO: DEBUG: Calling PayChangu endpoint: https://api.paychangu.com/payment
```

Should be `/payment` (singular), NOT `/payments` or `/v1/payments`.

---

## ✅ Success Indicators

1. **No 405 error in logs**
2. **Browser redirects to `checkout.paychangu.com`**
3. **Logs show:** `"PayChangu checkout created: tx_ref=..."`
4. **Database shows:**
   ```sql
   SELECT provider, status, checkout_url 
   FROM billing_paymenttransaction 
   ORDER BY created_at DESC LIMIT 1;
   
   -- Should show:
   -- provider: PAYCHANGU
   -- status: pending
   -- checkout_url: https://checkout.paychangu.com/pay/...
   ```

---

## 🔍 What Changed

| Before | After |
|--------|-------|
| `https://api.paychangu.com/v1/` + `/payments` | `https://api.paychangu.com` + `/payment` |
| = `https://api.paychangu.com/v1/payments` ❌ | = `https://api.paychangu.com/payment` ✅ |

---

## 📝 Files Modified

1. `cc/settings.py` - Removed `/v1/` from default
2. `billing/paychangu_service.py` - Changed `/payments` to `/payment`
3. `billing/tests/test_checkout_paychangu.py` - Updated test base URLs

---

**Status:** ✅ FIXED - Ready to test!

