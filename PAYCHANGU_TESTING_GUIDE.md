# PayChangu Checkout - Quick Testing Guide

## 🚀 Quick Start

### 1. Set Environment Variables

```bash
# Add to .env or export in terminal
export PAYCHANGU_MODE=test
export PAYCHANGU_PUBLIC_KEY=your_test_public_key
export PAYCHANGU_SECRET_KEY=your_test_secret_key
export PAYCHANGU_WEBHOOK_SECRET=your_webhook_secret
export PAYCHANGU_API_BASE=https://api.paychangu.com
```

### 2. Run Migrations

```bash
python manage.py migrate billing
```

### 3. Start Server

```bash
python manage.py runserver
```

---

## 📱 Test Scenarios

### Scenario 1: Airtel Money (Mobile Money Direct Charge) - SUCCESS

1. Navigate to: `http://localhost:8000/billing/subscribe/`
2. Select any plan
3. Click "Continue to Checkout"
4. Select "Airtel Money" tab
5. Enter test number: `0990000000` or `990000000` (PayChangu sandbox - success)
6. Click "Pay with Airtel Money"
7. **Expected:** Waiting page with polling animation, then success
8. **Note:** Numbers are 9 digits (without country code or leading 0)

### Scenario 1b: Airtel Money - FAILURE

1. Same steps as above
2. Enter test number: `0990000001` or `990000001` (PayChangu sandbox - fail)
3. **Expected:** Waiting page, then failure message

### Scenario 2: TNM Mpamba (Mobile Money Direct Charge) - SUCCESS

1. Same steps as Airtel Money
2. Select "TNM Mpamba" tab
3. Enter test number: `0899817565` or `899817565` (PayChangu sandbox - success)
4. Click "Pay with TNM Mpamba"
5. **Expected:** Waiting page with polling animation, then success

### Scenario 2b: TNM Mpamba - FAILURE

1. Same steps as above
2. Enter test number: `0899817566` or `899817566` (PayChangu sandbox - fail)
3. **Expected:** Waiting page, then failure message

### Scenario 3: Card (Hosted Checkout)

1. Navigate to checkout
2. Select "Card" tab
3. Enter test card: `4242 4242 4242 4242`
4. Expiry: `12/2025`, CVV: `123`
5. Click "Pay with Card"
6. **Expected:** Redirect to PayChangu hosted checkout page

### Scenario 4: Test Mode Validation (Blocks Real Numbers)

1. Navigate to checkout
2. Select "Airtel Money" tab
3. Enter real number: `0991234567`
4. Click "Pay with Airtel Money"
5. **Expected:** Warning message: "⚠️ Test mode: Please use PayChangu sandbox numbers only. For AIRTEL, use: 990000000, 990000001. Switch to LIVE mode to use real phone numbers."
6. **Behavior:** Payment will NOT proceed - user must use sandbox numbers or switch to LIVE mode

---

## 🔍 What to Check

### UI/UX Checks

- [ ] Checkout page is light mode (white background)
- [ ] Font is Inter (not system-ui)
- [ ] Three tabs visible: Airtel Money, TNM Mpamba, Card
- [ ] Test mode warning shows (yellow badge)
- [ ] Invoice preview shows on right side
- [ ] Send/Download buttons work
- [ ] Form validation works (empty phone shows error)
- [ ] Waiting page shows after submitting mobile money
- [ ] Polling animation works (spinner rotates)
- [ ] Status updates in real-time

### Backend Checks

1. **Transaction Created:**
   ```bash
   python manage.py shell
   >>> from billing.models import PaymentTransaction
   >>> PaymentTransaction.objects.latest('created_at')
   # Should show charge_id, payment_method, status=PENDING
   ```

2. **Logs Are Clean:**
   - Check terminal for no massive dict dumps
   - Should see structured log messages only
   - Secrets should be masked (e.g., `sec-****LAST4`)

3. **Database State:**
   ```bash
   python manage.py shell
   >>> from billing.models import Invoice, BusinessSubscription
   >>> inv = Invoice.objects.latest('created_at')
   >>> inv.status  # Should be 'draft' or 'sent'
   >>> sub = BusinessSubscription.objects.first()
   >>> sub.status  # Should be 'trial' or 'active' after payment
   ```

---

## 🧪 API Testing

### Test Payment Status Endpoint

```bash
# Get charge_id from database or logs
curl "http://localhost:8000/billing/api/payment-status/?charge_id=charge-abc123" \
  -H "Cookie: sessionid=YOUR_SESSION_ID"

# Expected response:
{
  "status": "pending",  # or "success" or "failed"
  "message": "Payment is being processed...",
  "redirect_url": "/billing/success/"  # only if success
}
```

### Test Webhook (Manual Trigger)

```bash
# Create test webhook payload
curl -X POST http://localhost:8000/billing/paychangu/webhook/ \
  -H "Content-Type: application/json" \
  -H "Signature: test_signature" \
  -d '{
    "tx_ref": "billing-123-abc456",
    "status": "successful",
    "amount": "20000",
    "currency": "MWK"
  }'

# Expected: 200 OK (even if signature fails - webhook logs error)
```

---

## 🐛 Troubleshooting

### Issue: "Payment system is not configured"

**Solution:** Check environment variables are set:
```bash
echo $PAYCHANGU_SECRET_KEY  # Should not be empty
```

### Issue: "Phone number must start with 0 or +265" or "Invalid phone number format"

**Solution:** Enter Malawi format (PayChangu accepts 9 digits normalized):
- Valid: `0990000000`, `990000000`, `+265990000000`
- Invalid (wrong length): `99000000` (8 digits), `9900000000` (10 digits)

**Test Mode Sandbox Numbers (9 digits WITHOUT leading 0):**
- Airtel Success: `990000000` (or with leading 0: `0990000000`)
- Airtel Fail: `990000001` (or with leading 0: `0990000001`)
- TNM Success: `899817565` (or with leading 0: `0899817565`)
- TNM Fail: `899817566` (or with leading 0: `0899817566`)

**Note:** Real phone numbers only work in LIVE mode (not TEST mode).

### Issue: Waiting page shows "Failed"

**Possible Causes:**
1. Test mode with real number (use sandbox numbers)
2. PayChangu API error (check logs)
3. Invalid operator ID (check `paychangu_service.py` operator_map)

**Debug:**
```bash
# Check logs
tail -f logs/django.log  # or check terminal output

# Check transaction status
python manage.py shell
>>> from billing.models import PaymentTransaction
>>> tx = PaymentTransaction.objects.latest('created_at')
>>> tx.status
>>> tx.raw_init_payload  # Check for errors
```

### Issue: Polling never completes

**Expected Behavior:**
- In TEST mode, sandbox may not send push prompts
- Polling will timeout after 90 seconds
- This is normal for sandbox testing

**Solution:**
- Test with LIVE mode + real numbers for full flow
- Or mock the verify endpoint in tests

### Issue: Webhook not called

**Possible Causes:**
1. Webhook URL not configured in PayChangu dashboard
2. Signature mismatch
3. Webhook secret incorrect

**Debug:**
```bash
# Check webhook events
python manage.py shell
>>> from billing.models import WebhookEvent
>>> WebhookEvent.objects.latest('created_at')
# Should show payload if webhook was received
```

---

## 📊 Success Criteria

After testing, verify:

- [x] Checkout page loads without errors
- [x] Light mode everywhere (no dark backgrounds)
- [x] Inter font used consistently
- [x] Mobile money creates PaymentTransaction with charge_id
- [x] Waiting page shows and polls
- [x] Card payment redirects to hosted checkout
- [x] Invoice send/download buttons work
- [x] No print() statements in logs
- [x] Secrets masked in logs
- [x] Payment status API returns JSON
- [x] Webhook processes successfully (200 OK)

---

## 🚀 Production Testing

### ⚠️ IMPORTANT: Real Push Prompts Only Work in LIVE Mode

**TEST Mode:** Sandbox numbers only, no real push prompts
**LIVE Mode:** Real numbers trigger push prompts to actual phones (like Premier Bet)

### Before Production

1. **Switch to Live Mode:**
   ```bash
   export PAYCHANGU_MODE=live
   export PAYCHANGU_SECRET_KEY=sec_live_xxxxxxxx
   export PAYCHANGU_PUBLIC_KEY=pub_live_xxxxxxxx
   ```

2. **Test with Real Numbers (LIVE Mode Only):**
   - Use your own Airtel/TNM number (e.g., `0991234567`)
   - Test with small amount (e.g., MWK 100)
   - **Expected:** Push prompt arrives on your phone within seconds
   - Approve payment on phone
   - Verify subscription activates automatically
   - Check database: transaction status should be SUCCESS

3. **Test Webhook:**
   - Configure webhook URL in PayChangu dashboard
   - Make a payment
   - Check webhook is called (check WebhookEvent table)
   - Verify subscription activates

4. **Monitor Logs:**
   ```bash
   tail -f logs/django.log | grep -i paychangu
   ```

---

## 📞 Support

### PayChangu Support
- **Docs:** https://docs.paychangu.com/
- **Email:** support@paychangu.com
- **Dashboard:** https://dashboard.paychangu.com/

### Internal Support
- **Code:** `billing/paychangu_service.py`
- **Views:** `billing/views.py`, `billing/views_paychangu.py`
- **Models:** `billing/models.py` (PaymentTransaction)
- **Templates:** `templates/billing/checkout.html`, `templates/billing/payment_waiting.html`

---

**Last Updated:** January 3, 2026
**Version:** 1.0
**Status:** Production Ready ✅
