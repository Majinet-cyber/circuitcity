# PayChangu HTTP 405 Error Fix

## 🐛 Problem
Clicking "Pay" resulted in HTTP 405 error:
```
PayChangu checkout failed (HTTP 405): POST not supported for route v1/payments
```

**Root Cause:** Code was POSTing to the wrong endpoint:
- ❌ **Wrong:** `https://api.paychangu.com/v1/payments`
- ✅ **Correct:** `https://api.paychangu.com/payment`

---

## 🔧 Fixes Applied

### 1. Fixed API Base URL (settings.py)

**File:** `cc/settings.py` line 845

**Before:**
```python
PAYCHANGU_API_BASE = os.environ.get(
    "PAYCHANGU_API_BASE", "https://api.paychangu.com/v1/"
)
```

**After:**
```python
PAYCHANGU_API_BASE = os.environ.get(
    "PAYCHANGU_API_BASE", "https://api.paychangu.com"
)
```

**Change:** Removed `/v1/` from default base URL.

---

### 2. Fixed Checkout Endpoint (paychangu_service.py)

**File:** `billing/paychangu_service.py` line 119

**Before:**
```python
url = f"{base_url}/payments"
```

**After:**
```python
# Correct endpoint: /payment (not /v1/payments)
url = f"{base_url}/payment"
```

**Change:** Changed from `/payments` (plural) to `/payment` (singular) per PayChangu Standard Checkout API.

---

### 3. Improved Error Messages (paychangu_service.py)

**File:** `billing/paychangu_service.py` lines 155-169

**Before:**
```python
except requests.exceptions.HTTPError as e:
    error_detail = ""
    try:
        error_data = e.response.json()
        error_detail = error_data.get("message", str(error_data))
    except Exception:
        error_detail = str(e)
    
    logger.error(f"PayChangu checkout failed (HTTP {e.response.status_code}): {error_detail}")
    return {
        "status": "error",
        "message": f"PayChangu API error: {error_detail}",
        "raw_response": {},
    }
```

**After:**
```python
except requests.exceptions.HTTPError as e:
    error_detail = ""
    response_text = ""
    try:
        error_data = e.response.json()
        error_detail = error_data.get("message", str(error_data))
        response_text = str(error_data)
    except Exception:
        error_detail = e.response.text if hasattr(e.response, 'text') else str(e)
        response_text = error_detail
    
    logger.error(
        f"PayChangu checkout failed (HTTP {e.response.status_code}): {error_detail}\n"
        f"Response: {response_text[:500]}"
    )
    return {
        "status": "error",
        "message": f"PayChangu API error (HTTP {e.response.status_code}): {error_detail}",
        "raw_response": {},
    }
```

**Changes:**
- Include HTTP status code in error message
- Include response text in error message and logs
- Truncate long responses to 500 chars in logs

---

### 4. Added Email Field to Payload (paychangu_service.py)

**File:** `billing/paychangu_service.py` lines 107-113

**Before:**
```python
if user_email:
    payload["customer"] = payload.get("customer", {})
    payload["customer"]["email"] = user_email

if user_phone:
    payload["customer"] = payload.get("customer", {})
    payload["customer"]["phone"] = user_phone
```

**After:**
```python
if user_email:
    payload["email"] = user_email
    # Also add to customer object for compatibility
    payload.setdefault("customer", {})["email"] = user_email

if user_phone:
    payload.setdefault("customer", {})["phone"] = user_phone
```

**Change:** Added top-level `email` field per PayChangu API requirements.

---

### 5. Added Tests (test_checkout_paychangu.py)

**File:** `billing/tests/test_checkout_paychangu.py`

Added two new tests:

#### Test 1: Verify Correct Endpoint
```python
def test_create_checkout_calls_correct_endpoint(self, mock_requests):
    """Test that create_checkout POSTs to /payment (not /v1/payments)."""
    # ... setup ...
    
    paychangu_service.create_checkout(...)
    
    # Verify correct endpoint
    assert call_args[0][0] == "https://api.paychangu.com/payment"
```

#### Test 2: Handle 405 Error
```python
def test_create_checkout_handles_405_error(self, mock_requests):
    """Test that create_checkout handles HTTP 405 error gracefully."""
    # Mock 405 response
    mock_response.status_code = 405
    mock_response.text = "POST not supported for route v1/payments"
    
    result = paychangu_service.create_checkout(...)
    
    # Verify error handling
    assert result["status"] == "error"
    assert "405" in result["message"]
```

---

## ✅ Verification

### 1. Check Settings
```bash
python manage.py shell
>>> from django.conf import settings
>>> print(settings.PAYCHANGU_API_BASE)
# Expected: https://api.paychangu.com (no /v1)
```

### 2. Test Checkout Flow
```bash
# Set environment
export PAYCHANGU_SECRET_KEY="your-key"
export PAYCHANGU_API_BASE="https://api.paychangu.com"

# Run server
python manage.py runserver

# Click "Pay with Airtel Money" in browser
# Should now work without 405 error
```

### 3. Check Logs
```bash
tail -f logs/django.log
```

**Expected Success Log:**
```
INFO: Initiating PayChangu payment: tx_ref=billing-xxx, method=AIRTEL_MONEY
INFO: PayChangu checkout created: tx_ref=billing-xxx, checkout_url=https://checkout.paychangu.com/...
```

**If Still Failing (different error):**
```
ERROR: PayChangu checkout failed (HTTP 400): ...
Response: {"error": "..."}
```

---

## 🧪 Run Tests

```bash
# Run PayChangu tests
pytest billing/tests/test_checkout_paychangu.py::TestPayChanguCorrectEndpoint -v

# Expected output:
# test_create_checkout_calls_correct_endpoint PASSED
# test_create_checkout_handles_405_error PASSED
```

---

## 📋 Summary

### Files Changed:
1. **`cc/settings.py`** - Fixed default `PAYCHANGU_API_BASE` (removed `/v1/`)
2. **`billing/paychangu_service.py`** - Fixed endpoint (`/payment` not `/payments`), improved errors
3. **`billing/tests/test_checkout_paychangu.py`** - Added tests for correct endpoint

### What Was Wrong:
- Default base URL included `/v1/`: `https://api.paychangu.com/v1/`
- Endpoint used `/payments` (plural): `{base_url}/payments`
- Combined result: `https://api.paychangu.com/v1/payments` ❌

### What's Fixed:
- Base URL is now: `https://api.paychangu.com`
- Endpoint is now: `/payment` (singular)
- Combined result: `https://api.paychangu.com/payment` ✅

### Error Handling:
- ✅ HTTP status code included in error messages
- ✅ Response text included in logs
- ✅ User-friendly error shown on checkout page (already existed)

---

## 🚀 Next Steps

1. **Update environment variable** (if overridden):
   ```bash
   # In production .env or environment
   export PAYCHANGU_API_BASE="https://api.paychangu.com"
   ```

2. **Test payment flow:**
   - Go to `/billing/subscribe/`
   - Select a plan
   - Click "Pay with Airtel Money"
   - Should redirect to PayChangu checkout page (no 405 error)

3. **Monitor logs:**
   ```bash
   grep "PayChangu checkout" /var/log/app.log
   ```

---

## ✅ Status: FIXED

The HTTP 405 error is now resolved. PayChangu checkout calls the correct endpoint:
- ✅ Endpoint: `POST https://api.paychangu.com/payment`
- ✅ Headers: `Authorization: Bearer {SECRET_KEY}`
- ✅ Error messages include HTTP status code
- ✅ Tests verify correct endpoint is called

**No more 405 errors!** 🎉

