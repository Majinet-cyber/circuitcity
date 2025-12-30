# PayChangu Webhook Signature Verification Fix

## Problem Summary
The PayChangu webhook endpoint was **always returning HTTP 401 "Invalid signature"** even when the signature was computed correctly on the client side using:
```bash
hex(hmac_sha256(secret, raw_bytes_of_payload_json_file))
```

## Root Cause Identified

The webhook secret from `settings.PAYCHANGU_WEBHOOK_SECRET` was **not being cleaned** before use. When reading environment variables, especially from `.env` files or shell exports, secrets often contain:
- Trailing newlines (`\n`)
- Leading/trailing whitespace
- Accidental quotes (`"secret"` or `'secret'`)

The signature verification was comparing:
- **Client**: `hmac_sha256("clean-secret", payload)`
- **Server**: `hmac_sha256("clean-secret\n", payload)` or `hmac_sha256('"clean-secret"', payload)`

These produce **completely different** HMAC hashes, causing signature mismatch.

## Secondary Issues Fixed

1. **Header reading order**: The view only tried `request.META.get("HTTP_SIGNATURE")` variants, missing the cleaner `request.headers.get("Signature")` API
2. **No debug logging**: Made troubleshooting impossible without exposing secrets
3. **Insufficient test coverage**: Tests didn't cover secrets with whitespace/quotes

---

## Files Changed

### 1. `billing/paychangu_service.py`
**Lines 266-321** - Enhanced `verify_webhook_signature()` function

#### Changes:
```python
# OLD: No cleaning
webhook_secret = getattr(settings, "PAYCHANGU_WEBHOOK_SECRET", "")

# NEW: Clean whitespace and quotes
webhook_secret = getattr(settings, "PAYCHANGU_WEBHOOK_SECRET", "")
webhook_secret = webhook_secret.strip().strip('"').strip("'")
```

#### Added:
- **Signature cleaning**: `signature = signature.strip()`
- **Secret cleaning**: Strip whitespace, quotes, newlines from both ends
- **Debug logging** (gated by `DEBUG` or `PAYCHANGU_WEBHOOK_DEBUG`):
  - `payload_len` - Length of raw request body
  - `payload_sha256` - SHA256 hash of payload
  - `secret_sha256` - SHA256 hash of secret (NOT the secret itself)
  - `received_sig` - Signature from header
  - `computed_sig` - Expected signature
- Logs are **safe** - never expose the raw secret

---

### 2. `billing/views_paychangu.py`
**Lines 174-205** - Updated webhook view header reading

#### Changes:
```python
# OLD: Only tried META variants
signature = (
    request.META.get("HTTP_SIGNATURE", "")
    or request.META.get("HTTP_X_SIGNATURE", "")
    or request.META.get("HTTP_X_PAYCHANGU_SIGNATURE", "")
)

# NEW: Prefer request.headers.get() first, with fallbacks
signature = (
    request.headers.get("Signature", "")
    or request.META.get("HTTP_SIGNATURE", "")
    or request.headers.get("X-Signature", "")
    or request.META.get("HTTP_X_SIGNATURE", "")
    or request.headers.get("X-PayChangu-Signature", "")
    or request.META.get("HTTP_X_PAYCHANGU_SIGNATURE", "")
).strip()
```

#### Added:
- **Robust header reading**: Try `request.headers.get()` variants first
- **Explicit comment**: "Get raw request body BEFORE any parsing"
- **Strip whitespace**: Call `.strip()` on final signature value

---

### 3. `cc/settings.py`
**Line 843** - Added debug flag

```python
PAYCHANGU_WEBHOOK_DEBUG = env_bool("PAYCHANGU_WEBHOOK_DEBUG", False)
```

This allows enabling debug logging without setting `DEBUG=True` globally:
```bash
export PAYCHANGU_WEBHOOK_DEBUG=true
```

---

### 4. `billing/tests/test_paychangu_webhook.py`
**Lines 184-261, 445-491** - Enhanced test coverage

#### Added Tests:
1. **`test_webhook_accepts_signature_header_via_request_headers`**
   - Ensures `Signature` header (via `request.headers.get()`) is read correctly

2. **`test_verify_webhook_signature_secret_with_whitespace_and_quotes`**
   - Tests secret like `  "my-secret"  \n` is cleaned to `my-secret`

3. **`test_verify_webhook_signature_secret_with_trailing_newline`**
   - Tests secret like `my-secret\n` is cleaned to `my-secret`

4. **`test_verify_webhook_signature_handles_signature_with_whitespace`**
   - Tests signature like `  abcd1234  \n` is cleaned to `abcd1234`

All tests validate that:
- Signature is computed over **raw bytes** (`request.body`)
- Secret is **cleaned** before use
- Comparison uses `hmac.compare_digest()` (constant-time)
- Returns **200 OK** when signature matches
- Returns **401 Unauthorized** when signature doesn't match

---

## Test Results

All 15 tests passed:
```bash
$ python -m pytest billing/tests/test_paychangu_webhook.py -v
============================= test session starts =============================
billing\tests\test_paychangu_webhook.py ...............                  [100%]
====================== 15 passed in 23.30s =======================
```

---

## How to Test Locally

### 1. Set webhook secret (clean, no quotes/newlines)
```bash
export PAYCHANGU_WEBHOOK_SECRET="your-actual-secret"
```

### 2. Enable debug logging (optional)
```bash
export PAYCHANGU_WEBHOOK_DEBUG=true
```

### 3. Send test webhook
```bash
# Create payload file
echo '{"event":"payment.success","tx_ref":"test-123","amount":"5000","currency":"MWK"}' > payload.json

# Compute signature (Python)
python -c "
import hmac, hashlib
secret = 'your-actual-secret'
payload = open('payload.json', 'rb').read()
sig = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
print(sig)
"

# Send webhook (Windows PowerShell)
curl.exe -i -X POST http://localhost:8000/billing/paychangu/webhook/ `
  -H "Content-Type: application/json" `
  -H "Signature: <computed-hex-from-above>" `
  --data-binary "@payload.json"
```

### 4. Check logs
With `PAYCHANGU_WEBHOOK_DEBUG=true`, you'll see:
```
[DEBUG] PayChangu webhook signature verification:
  payload_len=89
  payload_sha256=abc123...
  secret_sha256=def456...
  received_sig=789012...
  computed_sig=789012...
```

If they **match** → 200 OK  
If they **don't match** → 401 Invalid signature (with first 8 chars logged)

---

## Security Considerations

✅ **Safe Practices Implemented:**
- Signature verified **before** parsing JSON (prevents injection attacks)
- Uses `hmac.compare_digest()` (constant-time comparison, prevents timing attacks)
- Debug logging **never** logs raw secret (only SHA256 hash)
- Webhook remains unauthenticated (external endpoint, no session/tenant checks)
- Returns generic error messages (no info leakage)

⚠️ **Ensure:**
- `PAYCHANGU_WEBHOOK_SECRET` is stored securely (environment variable, not in code)
- HTTPS is used in production (prevents MITM attacks)
- Debug logging is disabled in production (set `PAYCHANGU_WEBHOOK_DEBUG=false`)

---

## Migration Notes

**No database migrations required** - this is a pure logic fix.

**No breaking changes** - existing working webhooks will continue to work, and previously failing ones (due to secret whitespace) will now succeed.

**Backwards compatible** - still reads all the same header names as before, just added more options.

---

## Summary

| Issue | Root Cause | Fix |
|-------|------------|-----|
| Invalid signature | Secret had trailing newline/quotes | Clean secret with `.strip().strip('"').strip("'")` |
| Header not found | Only checked META variants | Try `request.headers.get()` first |
| Hard to debug | No logging | Add safe debug logging (gated by flag) |
| Insufficient tests | Missing edge cases | Added 4 new test cases |

**Status**: ✅ Fixed and tested (all 15 tests passing)

