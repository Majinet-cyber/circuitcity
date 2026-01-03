# PayChangu Billing Flow Map — Baseline Audit

**Date:** 2026-01-03
**Status:** STEP 0 — Baseline Audit Complete

---

## Current Implementation Summary

### 1. Checkout Initiation

**File:** `billing/views_paychangu.py` (lines 44-163)

**Endpoint:** `POST /billing/paychangu/initiate/`

**Flow:**
1. User selects a plan (plan_code) and amount
2. System generates unique `tx_ref` = `pc-{business.id}-{uuid}-{timestamp}`
3. Creates `PaymentTransaction` record (PENDING status)
4. Calls `paychangu_service.create_checkout()` to get hosted checkout URL
5. Returns JSON with `checkout_url` for redirect

**Reference IDs stored:**
- `PaymentTransaction.tx_ref` (unique, indexed)
- `PaymentTransaction.checkout_url`
- `PaymentTransaction.raw_init_payload` (full API response)

**Tenant Isolation:**
- ✅ `PaymentTransaction.business` (FK, indexed)
- ✅ `PaymentTransaction.location` (FK, indexed)
- ✅ `PaymentTransaction.created_by` (FK)

---

### 2. Webhook Handler

**File:** `billing/views_paychangu.py` (lines 170-381)

**Endpoint:** `POST /billing/paychangu/webhook/` (CSRF exempt)

**Current Security:**
- ✅ Signature verification via `paychangu_service.verify_webhook_signature()`
- ✅ HMAC-SHA256 with `PAYCHANGU_WEBHOOK_SECRET`
- ✅ Returns 401 if signature invalid or missing
- ✅ Stores all events in `WebhookEvent` model

**Current Idempotency:**
- ✅ Checks if `transaction.status == SUCCESS` before processing
- ✅ Returns 200 immediately if already processed
- ⚠️ **GAP:** No explicit idempotency key or event deduplication beyond tx_ref

**Current Processing:**
1. Parse webhook payload (extract `tx_ref`)
2. Find `PaymentTransaction` by `tx_ref`
3. Store webhook payload in `transaction.raw_webhook_payload`
4. Call `paychangu_service.verify_payment(tx_ref)` to confirm with API
5. If verified SUCCESS:
   - Mark transaction SUCCESS
   - Find matching Invoice (by business + amount + currency)
   - Mark Invoice PAID
   - Activate BusinessSubscription (ACTIVE status)
   - Advance billing period
6. Return 200 OK

**Gaps Identified:**
- ⚠️ No `select_for_update()` locking (race condition risk)
- ⚠️ No explicit `transaction.atomic()` wrapper
- ⚠️ Invoice matching is heuristic (amount + currency) — could mismatch
- ⚠️ No PaymentEvent audit table (only WebhookEvent)
- ⚠️ No explicit idempotency_key beyond tx_ref

---

### 3. Success/Return Handler

**File:** `billing/views_paychangu.py` (lines 388-434)

**Endpoint:** `GET /billing/paychangu/return/`

**Current Behavior:**
- Accepts `tx_ref` from query params
- Stores `tx_ref` in session
- Renders `billing/paychangu_return.html` with "Processing..." message
- JavaScript polls `/api/payment-status/` for confirmation

**Polling API:** `billing/views.py` → `payment_status_api()` (lines 444-561)
- Returns transaction status (pending/success/failed)
- If still pending, calls `verify_payment()` to check latest status
- Returns `next_url` for redirect on success

**Gap:**
- ⚠️ No explicit "don't trust redirect" messaging (but webhook is source of truth)

---

### 4. Current Models

#### BusinessSubscription (`billing/models.py` lines 69-418)

**Status Choices:**
- TRIAL, ACTIVE, GRACE, PAST_DUE, CANCELED, EXPIRED

**Key Fields:**
- `plan` (FK to SubscriptionPlan)
- `status` (CharField)
- `trial_end`, `current_period_start`, `current_period_end`, `next_billing_date`
- `last_payment_at`
- `payment_method` (NONE, AIRTEL, STANDARD_BANK, CARD, STRIPE, PESAPAL)
- `stripe_subscription_id`, `pesapal_order_tracking_id`

**State Transitions:**
- `activate_now()` — sets ACTIVE, advances period
- `mark_past_due()` — sets PAST_DUE
- `enter_grace()` — sets GRACE
- `expire()` — sets EXPIRED
- `refresh_status()` — normalizes status based on dates

**Gap:**
- ⚠️ No `provider_customer_ref` or `provider_subscription_ref` for PayChangu
- ⚠️ State transitions not centralized in domain service

---

#### Invoice (`billing/models.py` lines 428-541)

**Status Choices:**
- DRAFT, SENT, PAID, OVERDUE, CANCELLED

**Key Fields:**
- `number` (unique, auto-generated `INV-YYYYMMDD-XXXXXX`)
- `business` (FK)
- `period_start`, `period_end` (DateField, nullable)
- `issue_date`, `due_date`, `sent_at`, `paid_at`
- `currency`, `subtotal`, `tax_amount`, `total`
- `status`
- `meta` (JSONField)

**Methods:**
- `mark_sent()` — sets SENT status
- `mark_paid()` — sets PAID status, records `paid_at`
- `recalc_totals()` — sums InvoiceItems

**Gaps:**
- ⚠️ No `pdf_file` field (PDF generation not implemented)
- ⚠️ No `provider_reference` field (PayChangu tx_ref)
- ⚠️ No `billing_period_start/end` (uses `period_start/end` but nullable)

---

#### InvoiceItem (`billing/models.py` lines 543-564)

**Fields:**
- `invoice` (FK)
- `description`, `qty`, `unit`, `unit_price`

**Auto-recalc:** Signal triggers `invoice.recalc_totals()` on save/delete

---

#### Payment (`billing/models.py` lines 569-636)

**Provider Choices:**
- AIRTEL, STANDARD_BANK, CARD, STRIPE, PESAPAL, PAYCHANGU

**Status Choices:**
- PENDING, SUCCEEDED, FAILED, REFUNDED

**Key Fields:**
- `business` (FK)
- `invoice` (FK, nullable)
- `provider`, `amount`, `currency`, `status`
- `reference`, `external_id`
- `raw_payload` (JSONField)
- `created_at`, `processed_at`

**Methods:**
- `mark_succeeded()` — marks SUCCEEDED, cascades to Invoice + Subscription

**Gap:**
- ⚠️ Not currently used by PayChangu webhook (uses PaymentTransaction instead)
- ⚠️ Duplicate payment tracking models (Payment vs PaymentTransaction)

---

#### PaymentTransaction (`billing/models.py` lines 733-820)

**Status Choices:**
- PENDING, SUCCESS, FAILED

**Key Fields:**
- `business`, `location`, `created_by` (tenant isolation)
- `provider` (default "paychangu")
- `tx_ref` (unique, indexed)
- `charge_id` (for mobile money direct charge)
- `payment_method` (airtel, tnm, card, etc.)
- `amount`, `currency`, `status`
- `checkout_url`
- `raw_init_payload`, `raw_webhook_payload`, `raw_verify_payload`

**Methods:**
- `mark_success()` — idempotent, only updates if not already SUCCESS
- `mark_failed()` — won't downgrade SUCCESS to FAILED

**Current Usage:**
- ✅ Primary model for PayChangu transactions
- ✅ Tenant-isolated
- ✅ Idempotent status updates

**Gap:**
- ⚠️ No link to Invoice (webhook matches by heuristic)
- ⚠️ No link to Payment model

---

#### WebhookEvent (`billing/models.py` lines 666-687)

**Fields:**
- `provider` (CharField)
- `event_type`, `external_id`
- `payload` (JSONField)
- `received_at`
- `processed` (BooleanField)

**Gap:**
- ⚠️ No `signature_valid` field
- ⚠️ No `status` (RECEIVED/PROCESSED/IGNORED/FAILED)
- ⚠️ No `error_message` field
- ⚠️ No `processed_at` timestamp
- ⚠️ No unique constraint on event_id/idempotency_key

---

### 5. Access Gating

**File:** `billing/middleware.py` (lines 50-180)

**Class:** `SubscriptionGateMiddleware`

**Enforcement Logic:**
- Enabled when `settings.FEATURES['BILLING_ENFORCE'] == True`
- Allows: TRIAL (if not expired), ACTIVE, GRACE period
- Blocks: EXPIRED, PAST_DUE (after grace)
- Redirects to `/billing/trial-expired/`

**Safe Prefixes (never blocked):**
- `/admin/`, `/billing/`, `/accounts/`, `/tenants/`, `/static/`, `/media/`
- `/hq/` (HQ paths bypass entirely)

**Bootstrap:**
- Auto-creates TRIAL subscription for new businesses (30 days default)

**Gap:**
- ⚠️ No explicit SUSPENDED status handling
- ⚠️ Grace logic uses `in_grace()` and `is_expired()` methods (works but not centralized)

---

### 6. Subscription Lifecycle Management

**Current State Transitions:**

```
TRIAL (30 days)
  ↓ (trial_end passes)
GRACE (30 days)
  ↓ (grace expires OR payment succeeds)
ACTIVE (if paid) OR EXPIRED (if not paid)
  ↓ (period ends without payment)
GRACE (30 days)
  ↓ (grace expires)
EXPIRED
```

**Methods:**
- `BusinessSubscription.activate_now()` — immediate activation
- `BusinessSubscription.mark_past_due()` — manual PAST_DUE
- `BusinessSubscription.enter_grace()` — manual GRACE
- `BusinessSubscription.expire()` — manual EXPIRED
- `BusinessSubscription.refresh_status()` — normalize based on dates

**Gap:**
- ⚠️ No scheduled task to auto-transition subscriptions daily
- ⚠️ No centralized domain service for state transitions
- ⚠️ PAST_DUE status exists but not actively used in flow

---

### 7. PayChangu Service Module

**File:** `billing/paychangu_service.py`

**Functions:**
- `is_paychangu_configured()` — checks env vars
- `create_checkout()` — POST to `/payment` endpoint
- `verify_payment(tx_ref)` — GET `/verify/{tx_ref}`
- `verify_webhook_signature(payload, signature)` — HMAC-SHA256 verification
- `get_mobile_money_operators()` — fetch operator list
- `get_operator_ref_id(method)` — resolve operator ref_id for airtel/tnm
- `momo_initialize_payment()` — direct charge initialization
- `momo_verify_payment(charge_id)` — verify direct charge

**Security:**
- ✅ Signature verification implemented
- ✅ Secret cleaning (strips quotes/whitespace)
- ✅ Constant-time comparison

**Gap:**
- ⚠️ No explicit retry logic
- ⚠️ No rate limiting

---

## Test Coverage

**Existing Tests:** `billing/tests/test_paychangu_webhook.py` (15 tests, all passing)

**Coverage:**
- ✅ Signature verification (valid/invalid/missing)
- ✅ Idempotency (duplicate webhook calls)
- ✅ Transaction status updates (SUCCESS/FAILED)
- ✅ Cross-tenant isolation
- ✅ Multiple signature header formats
- ✅ Webhook payload variations

**Gap:**
- ⚠️ No concurrency tests (race conditions)
- ⚠️ No invoice generation tests
- ⚠️ No PDF generation tests (not implemented)
- ⚠️ No email notification tests
- ⚠️ No reconciliation tests

---

## Critical Gaps for Production

### HIGH PRIORITY (STEP 1-2)

1. **No PaymentEvent audit table** — Need explicit event store with idempotency_key
2. **No PDF generation** — Invoices cannot be downloaded
3. **No atomic webhook processing** — Race conditions possible
4. **No select_for_update locking** — Concurrent webhooks could duplicate
5. **Invoice matching is heuristic** — Should use explicit link

### MEDIUM PRIORITY (STEP 3-4)

6. **No scheduled status transitions** — Subscriptions don't auto-expire
7. **No centralized domain service** — State transitions scattered
8. **No email notifications** — Managers don't get receipts
9. **No reconciliation tooling** — Hard to debug mismatches

### LOW PRIORITY (STEP 5-7)

10. **Success page could be clearer** — "Don't trust redirect" messaging
11. **No refund/chargeback handling** — Not implemented
12. **No partial payment support** — All-or-nothing

---

## File Paths Summary

### Core Billing Files
- `billing/models.py` — All models (BusinessSubscription, Invoice, Payment, PaymentTransaction, WebhookEvent)
- `billing/views_paychangu.py` — PayChangu checkout, webhook, return handlers
- `billing/paychangu_service.py` — PayChangu API client
- `billing/middleware.py` — Subscription gate enforcement
- `billing/urls.py` — URL routing

### Tests
- `billing/tests/test_paychangu_webhook.py` — Webhook tests (15 passing)
- `billing/tests/test_checkout_paychangu.py` — Checkout flow tests (passing)

### Templates (referenced but not audited)
- `templates/billing/paychangu_return.html` — Return/processing page
- `templates/billing/invoice.html` — Invoice display template

---

## Next Steps (STEP 1)

1. Create `PaymentEvent` model with idempotency_key
2. Add `Invoice.pdf_file` field
3. Add `Invoice.provider_reference` field
4. Add `InvoiceLineItem` model (or reuse InvoiceItem)
5. Add `BusinessSubscription.provider_customer_ref` and `provider_subscription_ref`
6. Create migration with safe defaults
7. Add model tests

---

**Audit Complete:** Ready to proceed to STEP 1 (Data Model Hardening)
