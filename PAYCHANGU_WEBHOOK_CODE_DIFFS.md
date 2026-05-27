# PayChangu Webhook Fix - Code Diffs

## Quick Reference - Exact Changes Made

---

## 1. billing/paychangu_service.py (Lines 266-321)

### Before:
```python
def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify PayChangu webhook signature using HMAC-SHA256.
    
    Args:
        payload: Raw request body (bytes)
        signature: Signature from request headers
    
    Returns:
        True if signature is valid, False otherwise
    """
    if not signature:
        logger.warning("PayChangu webhook missing signature")
        return False
    
    webhook_secret = getattr(settings, "PAYCHANGU_WEBHOOK_SECRET", "")
    if not webhook_secret:
        logger.error("PayChangu webhook secret not configured")
        return False
    
    # Compute HMAC-SHA256
    expected_signature = hmac.new(
        webhook_secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Compare using constant-time comparison
    is_valid = hmac.compare_digest(expected_signature, signature)
    
    if not is_valid:
        logger.warning(
            f"PayChangu webhook signature mismatch. "
            f"Expected: {expected_signature[:8]}..., Got: {signature[:8]}..."
        )
    
    return is_valid
```

### After:
```python
def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify PayChangu webhook signature using HMAC-SHA256.
    
    Args:
        payload: Raw request body (bytes)
        signature: Signature from request headers
    
    Returns:
        True if signature is valid, False otherwise
    """
    # Clean received signature
    signature = signature.strip()
    
    if not signature:
        logger.warning("PayChangu webhook missing signature")
        return False
    
    # Get and clean webhook secret (remove whitespace, quotes, newlines)
    webhook_secret = getattr(settings, "PAYCHANGU_WEBHOOK_SECRET", "")
    webhook_secret = webhook_secret.strip().strip('"').strip("'")
    
    if not webhook_secret:
        logger.error("PayChangu webhook secret not configured")
        return False
    
    # Compute HMAC-SHA256 signature over raw bytes
    expected_signature = hmac.new(
        webhook_secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Debug logging (safe - no raw secret)
    if getattr(settings, "DEBUG", False) or getattr(settings, "PAYCHANGU_WEBHOOK_DEBUG", False):
        secret_hash = hashlib.sha256(webhook_secret.encode("utf-8")).hexdigest()
        payload_hash = hashlib.sha256(payload).hexdigest()
        logger.debug(
            f"PayChangu webhook signature verification:\n"
            f"  payload_len={len(payload)}\n"
            f"  payload_sha256={payload_hash}\n"
            f"  secret_sha256={secret_hash}\n"
            f"  received_sig={signature}\n"
            f"  computed_sig={expected_signature}"
        )
    
    # Compare using constant-time comparison
    is_valid = hmac.compare_digest(expected_signature, signature)
    
    if not is_valid:
        logger.warning(
            f"PayChangu webhook signature mismatch. "
            f"Expected: {expected_signature[:8]}..., Got: {signature[:8]}..."
        )
    
    return is_valid
```

### Key Changes:
- ✅ Added `signature = signature.strip()` to clean received signature
- ✅ Added `webhook_secret = webhook_secret.strip().strip('"').strip("'")` to clean secret
- ✅ Added debug logging block (gated by DEBUG or PAYCHANGU_WEBHOOK_DEBUG flag)
- ✅ Added comments explaining each step

---

## 2. billing/views_paychangu.py (Lines 174-205)

### Before:
```python
@csrf_exempt
@require_POST
def paychangu_webhook(request: HttpRequest) -> HttpResponse:
    """
    Handle PayChangu webhook notifications.
    
    Verifies signature, extracts tx_ref, calls verify API, updates transaction.
    Must return 200 quickly to acknowledge receipt.
    """
    payload = request.body
    
    # Try multiple signature header names (Signature, X-Signature, X-PayChangu-Signature)
    signature = (
        request.META.get("HTTP_SIGNATURE", "")
        or request.META.get("HTTP_X_SIGNATURE", "")
        or request.META.get("HTTP_X_PAYCHANGU_SIGNATURE", "")
    )
    
    if not signature:
        logger.warning("PayChangu webhook missing signature header")
        return HttpResponse("Missing signature", status=401)
    
    # Verify signature
    is_valid = paychangu_service.verify_webhook_signature(payload, signature)
    if not is_valid:
        logger.warning("PayChangu webhook signature verification failed")
        return HttpResponse("Invalid signature", status=401)
```

### After:
```python
@csrf_exempt
@require_POST
def paychangu_webhook(request: HttpRequest) -> HttpResponse:
    """
    Handle PayChangu webhook notifications.
    
    Verifies signature, extracts tx_ref, calls verify API, updates transaction.
    Must return 200 quickly to acknowledge receipt.
    """
    # Get raw request body BEFORE any parsing
    payload = request.body
    
    # Read signature from header (try multiple names)
    # Prefer request.headers.get() first, then fall back to META
    signature = (
        request.headers.get("Signature", "")
        or request.META.get("HTTP_SIGNATURE", "")
        or request.headers.get("X-Signature", "")
        or request.META.get("HTTP_X_SIGNATURE", "")
        or request.headers.get("X-PayChangu-Signature", "")
        or request.META.get("HTTP_X_PAYCHANGU_SIGNATURE", "")
    ).strip()
    
    if not signature:
        logger.warning("PayChangu webhook missing signature header")
        return HttpResponse("Missing signature", status=401)
    
    # Verify signature using raw bytes (BEFORE any JSON parsing)
    is_valid = paychangu_service.verify_webhook_signature(payload, signature)
    if not is_valid:
        logger.warning("PayChangu webhook signature verification failed")
        return HttpResponse("Invalid signature", status=401)
```

### Key Changes:
- ✅ Added `request.headers.get("Signature")` as first option (preferred API)
- ✅ Added `request.headers.get("X-Signature")` and `request.headers.get("X-PayChangu-Signature")` variants
- ✅ Added `.strip()` to final signature value
- ✅ Added clarifying comments about raw bytes and parsing order

---

## 3. cc/settings.py (Line 843)

### Before:
```python
PAYCHANGU_MODE = os.environ.get("PAYCHANGU_MODE", "test").strip().lower()
PAYCHANGU_PUBLIC_KEY = os.environ.get("PAYCHANGU_PUBLIC_KEY", "")
PAYCHANGU_SECRET_KEY = os.environ.get("PAYCHANGU_SECRET_KEY", "")
PAYCHANGU_WEBHOOK_SECRET = os.environ.get("PAYCHANGU_WEBHOOK_SECRET", "")
PAYCHANGU_API_BASE = os.environ.get(
    "PAYCHANGU_API_BASE", "https://api.paychangu.com/v1/"
)
```

### After:
```python
PAYCHANGU_MODE = os.environ.get("PAYCHANGU_MODE", "test").strip().lower()
PAYCHANGU_PUBLIC_KEY = os.environ.get("PAYCHANGU_PUBLIC_KEY", "")
PAYCHANGU_SECRET_KEY = os.environ.get("PAYCHANGU_SECRET_KEY", "")
PAYCHANGU_WEBHOOK_SECRET = os.environ.get("PAYCHANGU_WEBHOOK_SECRET", "")
PAYCHANGU_WEBHOOK_DEBUG = env_bool("PAYCHANGU_WEBHOOK_DEBUG", False)
PAYCHANGU_API_BASE = os.environ.get(
    "PAYCHANGU_API_BASE", "https://api.paychangu.com/v1/"
)
```

### Key Changes:
- ✅ Added `PAYCHANGU_WEBHOOK_DEBUG` setting (defaults to False)
- ✅ Uses `env_bool()` helper to parse boolean from environment

---

## 4. billing/tests/test_paychangu_webhook.py

### Added Tests:

#### Test 1: Secret with whitespace and quotes
```python
@override_settings(PAYCHANGU_WEBHOOK_SECRET='  "my-secret-key"  \n')
def test_verify_webhook_signature_secret_with_whitespace_and_quotes(self):
    """Test signature verification when secret has whitespace/quotes/newlines."""
    payload = b'{"tx_ref":"test-123","amount":"1000"}'
    
    # Compute signature with CLEAN secret (after strip)
    expected_sig = hmac.new(
        b"my-secret-key",
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Should still verify correctly (service cleans the secret)
    is_valid = paychangu_service.verify_webhook_signature(payload, expected_sig)
    assert is_valid is True
```

#### Test 2: Secret with trailing newline
```python
@override_settings(PAYCHANGU_WEBHOOK_SECRET="  my-secret-key\n")
def test_verify_webhook_signature_secret_with_trailing_newline(self):
    """Test signature verification when secret has trailing newline."""
    payload = b'{"tx_ref":"test-123","amount":"1000"}'
    
    # Compute signature with clean secret
    expected_sig = hmac.new(
        b"my-secret-key",
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Should verify correctly after cleaning
    is_valid = paychangu_service.verify_webhook_signature(payload, expected_sig)
    assert is_valid is True
```

#### Test 3: Signature with whitespace
```python
@override_settings(PAYCHANGU_WEBHOOK_SECRET="my-secret-key")
def test_verify_webhook_signature_handles_signature_with_whitespace(self):
    """Test that signature with whitespace is cleaned before verification."""
    payload = b'{"tx_ref":"test-123","amount":"1000"}'
    
    expected_sig = hmac.new(
        b"my-secret-key",
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Add whitespace to signature
    signature_with_whitespace = f"  {expected_sig}  \n"
    
    # Should still verify correctly (service cleans the signature)
    is_valid = paychangu_service.verify_webhook_signature(payload, signature_with_whitespace)
    assert is_valid is True
```

#### Test 4: request.headers.get("Signature") support
```python
@override_settings(PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret-12345")
@patch('billing.paychangu_service.verify_payment')
def test_webhook_accepts_signature_header_via_request_headers(self, mock_verify, transaction):
    """Test that webhook accepts 'Signature' header via request.headers.get()."""
    # ... (full test in test file)
```

### Key Changes:
- ✅ Added 4 new comprehensive test cases
- ✅ All tests validate signature is computed over raw bytes
- ✅ All tests validate secret/signature cleaning works correctly
- ✅ Total: 15 tests, all passing

---

## Test Command

```bash
python -m pytest billing/tests/test_paychangu_webhook.py -v
```

**Result**: ✅ 15 passed in 23.30s

---

## Environment Variable Setup

### Development
```bash
# .env file or shell export
PAYCHANGU_WEBHOOK_SECRET="your-webhook-secret-here"
PAYCHANGU_WEBHOOK_DEBUG=true  # Enable debug logging
```

### Production
```bash
# Production environment
PAYCHANGU_WEBHOOK_SECRET="your-production-webhook-secret"
PAYCHANGU_WEBHOOK_DEBUG=false  # Disable debug logging
```

---

## Summary of Changes

| File | Lines Changed | Purpose |
|------|---------------|---------|
| `billing/paychangu_service.py` | 266-321 | Clean secret, add debug logging |
| `billing/views_paychangu.py` | 174-205 | Prefer request.headers.get(), add .strip() |
| `cc/settings.py` | 843 | Add PAYCHANGU_WEBHOOK_DEBUG flag |
| `billing/tests/test_paychangu_webhook.py` | +90 lines | Add 4 new edge case tests |

**Total impact**: ~130 lines changed/added across 4 files  
**Breaking changes**: None  
**Backwards compatible**: Yes  
**Database migrations**: None required

