# PayChangu Environment Variables

Add these environment variables to your `.env` file (create if it doesn't exist):

```env
# ============================================
# PayChangu Payment Provider (TEST MODE)
# ============================================

# Mode: "test" or "live" (default: test)
PAYCHANGU_MODE=test

# API Keys (from PayChangu Dashboard)
PAYCHANGU_PUBLIC_KEY=pub-test-w2kyBmbgbr7m76yNjyTIh2oH71eM3VPQ
PAYCHANGU_SECRET_KEY=sec-test-npyGRLGM6VLkT6OAWUgqjAI9t7ZI2zWT

# Webhook Secret (random string - must match PayChangu dashboard)
# Generate with: openssl rand -hex 32
PAYCHANGU_WEBHOOK_SECRET=your-random-webhook-secret-string-here

# API Base URL (default shown below)
PAYCHANGU_API_BASE=https://api.paychangu.com/v1/
```

## Production Configuration

When deploying to production, update to live keys:

```env
# PRODUCTION ONLY
PAYCHANGU_MODE=live
PAYCHANGU_PUBLIC_KEY=pub-live-your-live-public-key
PAYCHANGU_SECRET_KEY=sec-live-your-live-secret-key
PAYCHANGU_WEBHOOK_SECRET=your-strong-production-secret
```

**Important:** The production guard in `cc/settings.py` will prevent test mode when `DEBUG=False`:

```python
if not DEBUG and PAYCHANGU_MODE == "test":
    raise ImproperlyConfigured(
        "PAYCHANGU_MODE cannot be 'test' when DEBUG=False. "
        "Set PAYCHANGU_MODE=live in production or enable DEBUG for local testing."
    )
```

## Security Notes

1. ✅ **Never commit `.env` to Git** - it contains secrets
2. ✅ **Use different webhook secrets** for test and live environments
3. ✅ **Rotate secrets regularly** (every 90 days recommended)
4. ✅ **Webhook secret should be 32+ random characters**

## Where to Get Keys

1. Go to https://dashboard.paychangu.com/
2. Navigate to **Settings** → **API Keys**
3. Copy your TEST keys for local development
4. Copy your LIVE keys for production (keep separate and secure)

## Webhook Configuration

In PayChangu dashboard, configure webhook URL:

**Test Mode:**
```
https://your-ngrok-url.ngrok-free.app/billing/paychangu/webhook/
```

**Production:**
```
https://your-production-domain.com/billing/paychangu/webhook/
```

**Webhook Secret:**
- Must match the `PAYCHANGU_WEBHOOK_SECRET` in your `.env`
- Used to verify webhook authenticity via HMAC-SHA256

## Testing

Run tests with:

```bash
pytest billing/tests/test_paychangu_webhook.py -v
```

For manual testing, see: `PAYCHANGU_MANUAL_TEST_CHECKLIST.md`

