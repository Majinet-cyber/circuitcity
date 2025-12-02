# Payment Providers, Pharmacy & WhatsApp Implementation Summary

## Overview
This document summarizes the complete implementation of:
1. **Payment Providers**: Stripe & Pesapal API v3 for SaaS subscriptions
2. **Pharmacy Vertical**: Business-aware features with batch tracking and expiry management
3. **WhatsApp Integration**: Real-time alerts for managers and agents

---

## 1. PAYMENT PROVIDERS (STRIPE & PESAPAL)

### Environment Variables Added (cc/settings.py)

**Stripe:**
```python
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
```

**Pesapal:**
```python
PESAPAL_CONSUMER_KEY = os.environ.get("PESAPAL_CONSUMER_KEY", "")
PESAPAL_CONSUMER_SECRET = os.environ.get("PESAPAL_CONSUMER_SECRET", "")
PESAPAL_BASE_URL = os.environ.get("PESAPAL_BASE_URL", "https://cybqa.pesapal.com/pesapalv3/api/")
PESAPAL_IPN_ID = os.environ.get("PESAPAL_IPN_ID", "")
```

### Models Extended (billing/models.py)

**BusinessSubscription** - Added provider fields:
- `stripe_subscription_id` (CharField)
- `stripe_customer_id` (CharField)
- `pesapal_order_tracking_id` (CharField)
- `pesapal_merchant_reference` (CharField)

**Payment.Provider** - Added choices:
- `STRIPE = "stripe", "Stripe"`
- `PESAPAL = "pesapal", "Pesapal"`

### New Service Files

**billing/stripe_service.py:**
- `create_checkout_session()` - Creates Stripe Checkout Session
- `construct_webhook_event()` - Verifies webhook signatures
- `handle_checkout_completed()` - Processes checkout.session.completed events
- `handle_invoice_payment_succeeded()` - Processes recurring payments
- `cancel_stripe_subscription()` - Cancels subscriptions
- `get_stripe_subscription()` - Retrieves subscription details

**billing/pesapal_service.py:**
- `get_access_token()` - Obtains and caches Pesapal auth token
- `submit_order_request()` - Submits payment orders to Pesapal
- `get_transaction_status()` - Checks payment status
- `parse_ipn_notification()` - Parses IPN callbacks
- `register_ipn_url()` - Registers IPN endpoints

### New Views & URLs (billing/views_providers.py)

**Stripe Views:**
- `stripe_checkout` - POST /billing/stripe/checkout/ - Creates checkout session
- `stripe_success` - GET /billing/stripe/success/ - Success page
- `stripe_webhook` - POST /billing/stripe/webhook/ - Webhook handler

**Pesapal Views:**
- `pesapal_checkout` - POST /billing/pesapal/checkout/ - Creates payment order
- `pesapal_callback` - GET /billing/pesapal/callback/ - Browser redirect
- `pesapal_ipn` - GET/POST /billing/pesapal/ipn/ - IPN handler

### Updated Billing Template (templates/billing/subscribe.html)

Each plan now shows three payment options:
1. **Pesapal** (Card/Mobile Money) - Always shown for Malawi
2. **Stripe** (Card) - Only shown if `STRIPE_SECRET_KEY` configured
3. **Other Payment Methods** (Airtel/Bank) - Existing flow

### Templates Created:
- `templates/billing/stripe_success.html` - Stripe payment confirmation
- `templates/billing/pesapal_callback.html` - Pesapal payment status

---

## 2. PHARMACY VERTICAL

### New Models (inventory/models_pharmacy.py)

**PharmacyProductInfo:**
- Extended product info (strength, form, category, prescription requirement)
- One-to-one with MerchProduct

**PharmacyBatch:**
- Batch-level tracking with expiry dates
- Fields: batch_number, expiry_date, quantity, reorder_level, cost_price, selling_price
- Properties: `is_expired`, `is_near_expiry`, `is_low_stock`, `days_to_expiry`
- Method: `decrement_stock()` - Decrements quantity and auto-archives when depleted

**PharmacySale:**
- Records individual sales with batch tracking
- Fields: quantity, unit_price, unit_cost, payment_method, customer info, prescription_number
- Property: `profit` - Calculates profit per sale

### Enums:
- `PharmacyProductForm` - Tablet, Capsule, Syrup, Injection, etc.
- `PharmacyCategory` - Analgesic, Antibiotic, Antiviral, etc.

### New Views (inventory/views_pharmacy.py)

**Dashboard:**
- `pharmacy_dashboard` - Main dashboard with metrics, alerts, and charts

**Batch Management:**
- `batch_list` - List all batches with filters
- `batch_create` - Create new batch
- `batch_edit` - Edit existing batch

**Sales:**
- `sale_create` - Record sale (validates expiry & stock)
- `sale_list` - View sales history

**Alerts:**
- `near_expiry_list` - Batches expiring in next 30 days
- `expired_list` - Expired batches
- `low_stock_list` - Batches below reorder level

**API:**
- `api_batch_info` - Get batch info as JSON

### URLs (inventory/urls_pharmacy.py)
All pharmacy routes under `inventory:pharmacy_*` namespace

### Dashboard Template (templates/verticals/pharmacy/dashboard.html)

Features:
- Key metrics cards (batches, stock value, revenue, profit)
- Three alert sections: Near Expiry, Expired, Low Stock
- Quick action buttons: Add Batch, Record Sale, View Batches
- Glassmorphic design matching Liquor/Gym verticals

### Business Logic:

**Sale Validation:**
- ❌ Blocks sales from expired batches
- ❌ Blocks sales exceeding available quantity
- ✅ FIFO ordering (oldest expiry first)
- ✅ Auto-decrements stock
- ✅ Triggers WhatsApp notifications

---

## 3. WHATSAPP INTEGRATION

### Environment Variables (cc/settings.py)

```python
WHATSAPP_API_BASE_URL = os.environ.get("WHATSAPP_API_BASE_URL", "https://graph.facebook.com/v21.0/")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_DEFAULT_COUNTRY_CODE = os.environ.get("WHATSAPP_DEFAULT_COUNTRY_CODE", "+265")
```

### New Model (notifications/models.py)

**WhatsAppPreference:**
- One-to-one with User
- Fields:
  - `phone_number` - International format
  - `is_enabled` - Master switch
  - `receive_sale_alerts` - For managers
  - `receive_profit_milestones` - For managers
  - `receive_low_stock_alerts` - For managers
  - `receive_commission_alerts` - For agents

### WhatsApp Service (notifications/whatsapp_service.py)

**Core Functions:**
- `normalize_phone_number()` - Converts local numbers to international format
- `send_whatsapp_message()` - Sends message via WhatsApp Cloud API

**Notification Helpers:**
- `notify_manager_sale()` - "🛒 Sale Alert! 5x Product sold..."
- `notify_manager_profit_milestone()` - "🎉 Milestone Reached! Profit hit MWK 1M..."
- `notify_manager_low_stock()` - "⚠️ Low Stock Alert! Product running low..."
- `notify_agent_commission()` - "💰 Commission Earned! You earned MWK 500..."
- `notify_near_expiry()` - "⚠️ Expiry Alert! Batch expires in 15 days..."

### Hooks (inventory/views_pharmacy.py)

**After Sale:**
1. `_send_sale_notifications()` - Notifies managers and agent
2. `_check_and_notify_low_stock()` - Checks if stock is now low

### Views & URLs (notifications/views_whatsapp.py)

- `whatsapp_settings` - GET/POST /notifications/whatsapp/settings/ - Manage preferences
- `whatsapp_test` - POST /notifications/whatsapp/test/ - Send test message

### Template (templates/notifications/whatsapp_settings.html)

Features:
- Phone number input with format help
- Master enable/disable toggle
- Individual notification type toggles
- Test message button
- Graceful handling when WhatsApp not configured

---

## 4. TESTS

### Test Files Created:

**tests/test_payment_providers.py:**
- Stripe service tests (checkout session, webhooks)
- Pesapal service tests (token, order submission, status check)
- Webhook integration tests

**tests/test_pharmacy.py:**
- PharmacyBatch model tests (expiry, stock, calculations)
- PharmacySale model tests (creation, profit calculation)
- Complete workflow integration test

**tests/test_whatsapp.py:**
- Phone normalization tests
- WhatsApp service tests (send message, error handling)
- Preference model tests
- Notification helper tests

All tests use mocks for external APIs (no real API calls in tests).

---

## 5. MIGRATIONS REQUIRED

Run the following commands to apply database changes:

```bash
# Create migrations for new models
python manage.py makemigrations billing
python manage.py makemigrations inventory
python manage.py makemigrations notifications

# Apply migrations
python manage.py migrate
```

---

## 6. SETUP INSTRUCTIONS

### Stripe Setup:

1. Create Stripe account: https://dashboard.stripe.com/
2. Get API keys from Dashboard → Developers → API keys
3. Create webhook endpoint: Dashboard → Developers → Webhooks
   - URL: `https://yourdomain.com/billing/stripe/webhook/`
   - Events: `checkout.session.completed`, `invoice.payment_succeeded`
4. Set environment variables:
   ```bash
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```

### Pesapal Setup:

1. Create Pesapal account: https://www.pesapal.com/
2. Get credentials from Pesapal dashboard
3. Register IPN URL in Pesapal dashboard:
   - URL: `https://yourdomain.com/billing/pesapal/ipn/`
   - Type: GET or POST
4. Set environment variables:
   ```bash
   PESAPAL_CONSUMER_KEY=your_consumer_key
   PESAPAL_CONSUMER_SECRET=your_consumer_secret
   PESAPAL_BASE_URL=https://pay.pesapal.com/v3/api/  # production
   PESAPAL_IPN_ID=your_ipn_id
   ```

### WhatsApp Setup:

1. Create Meta Developer account: https://developers.facebook.com/
2. Create app and add WhatsApp product
3. Get Phone Number ID and Access Token
4. Set environment variables:
   ```bash
   WHATSAPP_API_BASE_URL=https://graph.facebook.com/v21.0/
   WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
   WHATSAPP_ACCESS_TOKEN=your_long_lived_token
   WHATSAPP_DEFAULT_COUNTRY_CODE=+265
   ```

---

## 7. USAGE EXAMPLES

### Subscribing with Stripe:

1. User visits `/billing/subscribe/`
2. Selects plan and clicks "Pay with Card (Stripe)"
3. Redirected to Stripe Checkout
4. After payment, webhook activates subscription
5. User sees success page

### Recording Pharmacy Sale:

1. Manager visits pharmacy dashboard
2. Clicks "Record Sale"
3. Selects batch (non-expired, in-stock)
4. Enters quantity and customer details
5. Sale recorded, stock decremented
6. WhatsApp notifications sent to managers/agents

### Enabling WhatsApp Notifications:

1. User visits `/notifications/whatsapp/settings/`
2. Enters phone number (e.g. +265888123456)
3. Enables notifications and selects types
4. Clicks "Send Test Message" to verify
5. Receives real-time alerts on sales/stock

---

## 8. FILE SUMMARY

### New Files Created:

**Payment Providers:**
- billing/stripe_service.py (260 lines)
- billing/pesapal_service.py (365 lines)
- billing/views_providers.py (475 lines)
- templates/billing/stripe_success.html
- templates/billing/pesapal_callback.html

**Pharmacy:**
- inventory/models_pharmacy.py (445 lines)
- inventory/views_pharmacy.py (555 lines)
- inventory/urls_pharmacy.py (28 lines)
- templates/verticals/pharmacy/dashboard.html (170 lines)

**WhatsApp:**
- notifications/whatsapp_service.py (340 lines)
- notifications/views_whatsapp.py (90 lines)
- notifications/urls.py (8 lines)
- templates/notifications/whatsapp_settings.html (155 lines)

**Tests:**
- tests/test_payment_providers.py (210 lines)
- tests/test_pharmacy.py (255 lines)
- tests/test_whatsapp.py (215 lines)

### Modified Files:

- cc/settings.py (added environment variables)
- billing/models.py (added provider fields)
- billing/urls.py (added Stripe/Pesapal routes)
- billing/views.py (added stripe_configured flag)
- templates/billing/subscribe.html (added payment provider buttons)
- notifications/models.py (added WhatsAppPreference model)
- inventory/verticals/pharmacy.py (delegated to comprehensive dashboard)

---

## 9. SECURITY NOTES

✅ **No hardcoded credentials** - All sensitive data via environment variables
✅ **Webhook signature verification** - Stripe signatures validated
✅ **IPN transaction verification** - Pesapal status checked via API
✅ **Phone number normalization** - Prevents injection attacks
✅ **User authorization** - All views protected with `@login_required` and `@require_business`
✅ **Sale validation** - Expired batches and insufficient stock blocked

---

## 10. NEXT STEPS

1. **Run migrations** to create new database tables
2. **Set environment variables** for Stripe, Pesapal, and WhatsApp
3. **Test payment flows** in sandbox/test mode first
4. **Create Stripe products** and copy price IDs to SubscriptionPlan.meta
5. **Register Pesapal IPN** URL in their dashboard
6. **Verify WhatsApp** phone number in Meta Business Manager
7. **Add navigation links** to WhatsApp settings in user menu
8. **Seed pharmacy batches** for testing expiry alerts
9. **Monitor webhook logs** (WebhookEvent model) for debugging
10. **Set up profit milestones** tracking (optional enhancement)

---

## Support & Documentation

- **Stripe Docs**: https://stripe.com/docs/api
- **Pesapal API v3**: https://developer.pesapal.com/
- **WhatsApp Cloud API**: https://developers.facebook.com/docs/whatsapp/cloud-api/

For questions or issues, check the inline code comments or test files for examples.

---

**Implementation Complete** ✅

