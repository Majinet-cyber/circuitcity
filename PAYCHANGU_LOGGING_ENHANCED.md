# PayChangu Logging Enhanced

## ✅ What Was Added

Enhanced logging in `billing/paychangu_service.py` to show:
1. **Exact URL being called** with masked secret key
2. **HTTP status code** in response
3. **Full error details** with status code + response body
4. **User-friendly error messages** based on status code

---

## 📊 Log Output Examples

### Success Flow

```
INFO: PayChangu create_checkout: POST https://api.paychangu.com/payment
  Headers: Authorization: Bearer sk_test_...xyz, Content-Type: application/json
  Payload: tx_ref=billing-abc-123, amount=20000.00, currency=MWK

INFO: PayChangu response: HTTP 200

INFO: PayChangu checkout created successfully: tx_ref=billing-abc-123, checkout_url=https://checkout.paychangu.com/pay/xyz123
```

### Error Flow (HTTP 405)

```
INFO: PayChangu create_checkout: POST https://api.paychangu.com/payment
  Headers: Authorization: Bearer sk_test_...xyz, Content-Type: application/json
  Payload: tx_ref=billing-abc-456, amount=15000.00, currency=MWK

ERROR: PayChangu checkout failed:
  URL: POST https://api.paychangu.com/payment
  Status Code: 405
  Error: POST not supported for route v1/payments
  Response Body: {"error": "POST not supported for route v1/payments", "message": "Method not allowed"}
```

### Error Flow (HTTP 401)

```
INFO: PayChangu create_checkout: POST https://api.paychangu.com/payment
  Headers: Authorization: Bearer sk_test_...xyz, Content-Type: application/json
  Payload: tx_ref=billing-def-789, amount=25000.00, currency=MWK

ERROR: PayChangu checkout failed:
  URL: POST https://api.paychangu.com/payment
  Status Code: 401
  Error: Invalid API credentials
  Response Body: {"error": "Unauthorized", "message": "Invalid API credentials"}
```

---

## 🔒 Security Features

1. **Secret Key Masking:** Only shows first 8 and last 4 characters
   - Example: `sk_test_1234567890abcdefghij` → `sk_test_...fghij`
   
2. **Response Body Truncation:** Limits to 500 characters in logs

3. **No Sensitive Data:** Customer email/phone not logged (only tx_ref)

---

## 🎯 User-Friendly Error Messages

The service now returns context-specific error messages based on HTTP status codes:

| Status Code | User Message |
|------------|--------------|
| 400 | "Invalid payment request: {error_detail}" |
| 401 | "Payment provider authentication failed. Please contact support." |
| 405 | "Payment provider endpoint error. Please contact support." |
| 500+ | "Payment provider is temporarily unavailable. Please try again later." |
| Other | "Payment provider error (HTTP {code}): {error_detail}" |

These messages are:
- ✅ Shown on checkout page via `messages.error()`
- ✅ Logged with full technical details
- ✅ Safe to show to end users (no technical jargon)

---

## 🔍 How to Verify

### 1. Check Logs During Payment

```bash
# Start server with visible logs
python manage.py runserver

# In another terminal, watch logs
tail -f logs/django.log | grep PayChangu
```

**When you click "Pay with Airtel Money":**

```
INFO: Initiating PayChangu payment: business=uuid-123, invoice=uuid-456, tx_ref=billing-abc-123, method=AIRTEL_MONEY, amount=20000
INFO: PayChangu create_checkout: POST https://api.paychangu.com/payment
  Headers: Authorization: Bearer sk_...xyz, Content-Type: application/json
  Payload: tx_ref=billing-abc-123, amount=20000, currency=MWK
INFO: PayChangu response: HTTP 200
INFO: PayChangu checkout created successfully: tx_ref=billing-abc-123, checkout_url=https://checkout.paychangu.com/...
```

### 2. Verify URL is Correct

The log should show:
```
POST https://api.paychangu.com/payment
```

**NOT:**
- ❌ `POST https://api.paychangu.com/v1/payments`
- ❌ `POST https://api.paychangu.com/payments`

### 3. Verify Headers Include Authorization

The log should show:
```
Headers: Authorization: Bearer sk_...xyz, Content-Type: application/json
```

### 4. Test Error Handling

Temporarily use invalid credentials:
```bash
export PAYCHANGU_SECRET_KEY="invalid-key-test"
python manage.py runserver
```

Click "Pay" and check:
1. **Logs show:**
   ```
   ERROR: PayChangu checkout failed:
     URL: POST https://api.paychangu.com/payment
     Status Code: 401
     Error: Invalid API credentials
   ```

2. **Checkout page shows:**
   ```
   ⚠️ Payment initiation failed: Payment provider authentication failed. Please contact support.
   ```

---

## 📋 Code Changes Summary

### File: `billing/paychangu_service.py`

#### Addition 1: Request Logging (before API call)
```python
# Log exact URL and headers (mask secret key for security)
masked_secret = f"{secret_key[:8]}...{secret_key[-4:]}" if len(secret_key) > 12 else "***"
logger.info(
    f"PayChangu create_checkout: POST {url}\n"
    f"  Headers: Authorization: Bearer {masked_secret}, Content-Type: application/json\n"
    f"  Payload: tx_ref={tx_ref}, amount={amount}, currency={currency}"
)
```

#### Addition 2: Response Status Logging (after API call)
```python
# Log response status
logger.info(f"PayChangu response: HTTP {response.status_code}")
```

#### Addition 3: Enhanced Error Logging
```python
# Log full error details
logger.error(
    f"PayChangu checkout failed:\n"
    f"  URL: POST {url}\n"
    f"  Status Code: {status_code}\n"
    f"  Error: {error_detail}\n"
    f"  Response Body: {response_body[:500]}"
)

# Return user-friendly error message
user_message = f"Payment provider error (HTTP {status_code}): {error_detail}"
if status_code == 401:
    user_message = "Payment provider authentication failed. Please contact support."
elif status_code == 400:
    user_message = f"Invalid payment request: {error_detail}"
elif status_code == 405:
    user_message = "Payment provider endpoint error. Please contact support."
elif status_code >= 500:
    user_message = "Payment provider is temporarily unavailable. Please try again later."
```

---

## 🧪 Quick Test

### Test 1: Verify Exact URL

```bash
python manage.py runserver
# Click "Pay with Airtel Money"
# Check logs for this line:
```

**Expected:**
```
INFO: PayChangu create_checkout: POST https://api.paychangu.com/payment
```

### Test 2: Verify Headers

**Expected in logs:**
```
Headers: Authorization: Bearer sk_test_...xyz, Content-Type: application/json
```

### Test 3: Verify Error Surface

```bash
# Use invalid key
export PAYCHANGU_SECRET_KEY="invalid"
python manage.py runserver

# Click "Pay"
# Check browser shows:
```

**Expected on page:**
```
⚠️ Payment initiation failed: Payment provider authentication failed. Please contact support.
```

**Expected in logs:**
```
ERROR: PayChangu checkout failed:
  URL: POST https://api.paychangu.com/payment
  Status Code: 401
  Error: ...
```

---

## ✅ Verification Checklist

After these changes:
- ✅ Logs show exact URL: `POST https://api.paychangu.com/payment`
- ✅ Logs show headers with masked secret key
- ✅ Logs show HTTP status code for every response
- ✅ Errors include full status code + response body
- ✅ User sees friendly error message on checkout page
- ✅ Secret key is masked in logs (security)
- ✅ Response body truncated to 500 chars (avoid log spam)

---

## 🎯 What You Get

### For Debugging:
```
INFO: PayChangu create_checkout: POST https://api.paychangu.com/payment
  Headers: Authorization: Bearer sk_test_...xyz, Content-Type: application/json
  Payload: tx_ref=billing-abc-123, amount=20000, currency=MWK
INFO: PayChangu response: HTTP 200
INFO: PayChangu checkout created successfully: tx_ref=billing-abc-123, checkout_url=...
```

### For Error Diagnosis:
```
ERROR: PayChangu checkout failed:
  URL: POST https://api.paychangu.com/payment
  Status Code: 405
  Error: POST not supported for route v1/payments
  Response Body: {"error": "POST not supported..."}
```

### For Users:
- Clear error message on checkout page
- No technical jargon
- Actionable instructions (e.g., "contact support")

---

## 📝 Summary

**Added:**
1. ✅ INFO log showing exact URL before API call
2. ✅ INFO log showing HTTP status code after API call
3. ✅ ERROR log with full details (URL, status, response body)
4. ✅ User-friendly error messages based on status code
5. ✅ Secret key masking for security

**Checkout view already:**
- ✅ Shows errors via `messages.error()` (line 462-464 in `views.py`)
- ✅ Re-renders checkout form with error message
- ✅ User sees red error banner at top of page

**Status:** ✅ Complete - Full observability + user-friendly errors

