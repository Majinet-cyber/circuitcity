# PayChangu Webhook Testing Guide

## Quick Verification - Test the Fix Locally

This guide helps you verify the webhook signature fix works correctly in your environment.

---

## Step 1: Set Environment Variables

```bash
# Windows PowerShell
$env:PAYCHANGU_WEBHOOK_SECRET = "your-test-webhook-secret"
$env:PAYCHANGU_WEBHOOK_DEBUG = "true"

# Linux/Mac
export PAYCHANGU_WEBHOOK_SECRET="your-test-webhook-secret"
export PAYCHANGU_WEBHOOK_DEBUG=true
```

**Important**: Use your actual webhook secret from PayChangu dashboard.

---

## Step 2: Start Django Server

```bash
python manage.py runserver 8000
```

Keep this terminal open. You should see:
```
Starting development server at http://127.0.0.1:8000/
```

---

## Step 3: Create Test Payload

Create a JSON file named `payload.json`:

```json
{
  "event": "payment.success",
  "tx_ref": "pc-test-12345",
  "amount": "5000.00",
  "currency": "MWK",
  "status": "successful"
}
```

**Note**: Use a real `tx_ref` from your PaymentTransaction table if you want to test the full workflow.

---

## Step 4: Compute Signature (Python)

Run this Python script to compute the signature:

```python
# compute_signature.py
import hmac
import hashlib

# MUST match your environment variable
secret = "your-test-webhook-secret"

# Read payload as raw bytes (exactly as curl will send it)
with open("payload.json", "rb") as f:
    payload = f.read()

# Compute HMAC-SHA256
signature = hmac.new(
    secret.encode("utf-8"),
    payload,
    hashlib.sha256
).hexdigest()

print(f"Signature: {signature}")
print(f"Payload length: {len(payload)} bytes")
```

Run it:
```bash
python compute_signature.py
```

Example output:
```
Signature: a3b2c1d4e5f6789012345678901234567890abcdef1234567890abcdef123456
Payload length: 123 bytes
```

Copy the signature hex string.

---

## Step 5: Send Webhook Request

### Option A: Using curl (Windows PowerShell)

```powershell
curl.exe -i -X POST http://localhost:8000/billing/paychangu/webhook/ `
  -H "Content-Type: application/json" `
  -H "Signature: a3b2c1d4e5f6789012345678901234567890abcdef1234567890abcdef123456" `
  --data-binary "@payload.json"
```

### Option B: Using curl (Linux/Mac)

```bash
curl -i -X POST http://localhost:8000/billing/paychangu/webhook/ \
  -H "Content-Type: application/json" \
  -H "Signature: a3b2c1d4e5f6789012345678901234567890abcdef1234567890abcdef123456" \
  --data-binary "@payload.json"
```

### Option C: Using Python requests

```python
import requests
import hmac
import hashlib

url = "http://localhost:8000/billing/paychangu/webhook/"
secret = "your-test-webhook-secret"

with open("payload.json", "rb") as f:
    payload = f.read()

signature = hmac.new(
    secret.encode("utf-8"),
    payload,
    hashlib.sha256
).hexdigest()

response = requests.post(
    url,
    data=payload,
    headers={
        "Content-Type": "application/json",
        "Signature": signature
    }
)

print(f"Status: {response.status_code}")
print(f"Body: {response.text}")
```

---

## Step 6: Verify Response

### Expected: Success (200 OK)

If signature is correct:
```
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Content-Length: 2

OK
```

✅ **Success!** The signature was verified correctly.

### Expected: Failure (401 Unauthorized)

If signature is wrong:
```
HTTP/1.1 401 Unauthorized
Content-Type: text/html; charset=utf-8
Content-Length: 17

Invalid signature
```

❌ **Failure** - Check that:
1. Secret matches exactly (no extra quotes/newlines)
2. Payload file is identical to what you hashed
3. You're using `--data-binary` (not `--data`)

---

## Step 7: Check Debug Logs

With `PAYCHANGU_WEBHOOK_DEBUG=true`, check your Django console output:

### Success Case:
```
[DEBUG] PayChangu webhook signature verification:
  payload_len=123
  payload_sha256=def456...
  secret_sha256=abc123...
  received_sig=a3b2c1d4e5f6...
  computed_sig=a3b2c1d4e5f6...
[INFO] PayChangu webhook received for tx_ref=pc-test-12345
```

If `received_sig` == `computed_sig` → ✅ Signatures match!

### Failure Case:
```
[DEBUG] PayChangu webhook signature verification:
  payload_len=123
  payload_sha256=def456...
  secret_sha256=abc123...
  received_sig=111111...
  computed_sig=222222...
[WARNING] PayChangu webhook signature mismatch. Expected: 22222222..., Got: 11111111...
```

If `received_sig` ≠ `computed_sig` → ❌ Mismatch - check secret/payload

---

## Common Issues & Solutions

### Issue 1: "Missing signature"

**Cause**: Header not sent or misspelled.

**Solution**:
```bash
# Make sure header name is exactly "Signature" (capital S)
-H "Signature: abc123..."

# Alternative headers also work:
-H "X-Signature: abc123..."
-H "X-PayChangu-Signature: abc123..."
```

### Issue 2: Signature mismatch even with correct secret

**Cause**: Payload bytes don't match what you hashed.

**Solution**:
1. Use `--data-binary "@payload.json"` (NOT `--data`)
2. Ensure no BOM or encoding issues (save as UTF-8 no BOM)
3. Verify payload length matches: `len(payload) == file size`

### Issue 3: Secret has quotes in environment variable

**Cause**: Shell added quotes when setting env var.

**Bad**:
```bash
export PAYCHANGU_WEBHOOK_SECRET='"my-secret"'  # Has literal quotes
```

**Good**:
```bash
export PAYCHANGU_WEBHOOK_SECRET='my-secret'    # Clean
```

**But the fix handles this!** The code now strips quotes automatically:
```python
webhook_secret = webhook_secret.strip().strip('"').strip("'")
```

### Issue 4: Secret has trailing newline

**Cause**: Copied secret from file with newline, or echo added one.

**Bad**:
```bash
echo "my-secret" > secret.txt   # Adds newline!
export PAYCHANGU_WEBHOOK_SECRET=$(cat secret.txt)
```

**Good**:
```bash
export PAYCHANGU_WEBHOOK_SECRET="my-secret"  # No newline
```

**But the fix handles this!** The code now strips whitespace automatically.

---

## Production Testing with Cloudflare Tunnel

If you're testing with a real Cloudflare tunnel (as mentioned in your original issue):

```bash
# 1. Start cloudflared tunnel
cloudflared tunnel --url localhost:8000

# Output: https://random-name.trycloudflare.com

# 2. Send webhook through tunnel
curl.exe -i -X POST https://random-name.trycloudflare.com/billing/paychangu/webhook/ `
  -H "Content-Type: application/json" `
  -H "Signature: <computed-hex>" `
  --data-binary "@payload.json"
```

This tests:
- ✅ Real HTTPS request path
- ✅ Headers preserved through Cloudflare
- ✅ Binary payload preserved
- ✅ Django signature verification

---

## Unit Tests

Run the full test suite:

```bash
# All PayChangu webhook tests
python -m pytest billing/tests/test_paychangu_webhook.py -v

# Just signature verification tests
python -m pytest billing/tests/test_paychangu_webhook.py::TestPayChanguSignatureVerification -v

# Single test
python -m pytest billing/tests/test_paychangu_webhook.py::TestPayChanguWebhookSignature::test_webhook_accepts_valid_signature_and_updates_transaction -v
```

Expected: **15 passed**

---

## Debugging Checklist

If webhook still fails, check:

- [ ] Secret is set correctly: `echo $PAYCHANGU_WEBHOOK_SECRET`
- [ ] Secret has no quotes/newlines: `echo "$PAYCHANGU_WEBHOOK_SECRET" | xxd | head`
- [ ] Payload is valid JSON: `jq . payload.json`
- [ ] Signature is lowercase hex: `[a-f0-9]{64}`
- [ ] Header name is correct: `Signature` (capital S)
- [ ] Using `--data-binary` not `--data`
- [ ] Debug logging enabled: `PAYCHANGU_WEBHOOK_DEBUG=true`
- [ ] Django logs show the debug output
- [ ] `received_sig` matches your computed signature
- [ ] `payload_sha256` matches: `sha256sum payload.json` or `certutil -hashfile payload.json SHA256`

---

## Verify Fix Applied

Check that your code has the fixes:

### 1. Check paychangu_service.py has secret cleaning:
```bash
grep -A 1 "webhook_secret.strip()" billing/paychangu_service.py
```

Expected:
```python
webhook_secret = webhook_secret.strip().strip('"').strip("'")
```

### 2. Check views_paychangu.py prefers request.headers:
```bash
grep -A 1 "request.headers.get" billing/views_paychangu.py
```

Expected:
```python
request.headers.get("Signature", "")
```

### 3. Check settings.py has debug flag:
```bash
grep "PAYCHANGU_WEBHOOK_DEBUG" cc/settings.py
```

Expected:
```python
PAYCHANGU_WEBHOOK_DEBUG = env_bool("PAYCHANGU_WEBHOOK_DEBUG", False)
```

---

## Success Criteria

✅ **All these should work:**

1. Webhook with `Signature` header → 200 OK
2. Webhook with `X-Signature` header → 200 OK
3. Secret with trailing `\n` → Still verifies correctly
4. Secret with quotes `"secret"` → Still verifies correctly
5. Signature with whitespace → Still verifies correctly
6. Wrong signature → 401 Unauthorized
7. Missing signature → 401 Unauthorized
8. Unit tests pass → 15/15 passed

---

## Need Help?

If webhook still fails after following this guide:

1. **Enable debug logging** and share the output (mask your secret!)
2. **Run the unit tests** and share results: `pytest billing/tests/test_paychangu_webhook.py -v`
3. **Check payload hash**:
   ```python
   import hashlib
   payload = open("payload.json", "rb").read()
   print(hashlib.sha256(payload).hexdigest())
   ```
4. **Verify secret hash** (share this, not the raw secret):
   ```python
   import hashlib
   secret = "your-secret"
   print(hashlib.sha256(secret.encode("utf-8")).hexdigest())
   ```

This allows debugging without exposing your actual webhook secret.

