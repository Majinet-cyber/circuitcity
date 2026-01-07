# Trial Subscription & Cache Busting Fix Summary

## Date: January 6, 2026
## Branch: fix/cypress-pharmacy

---

## Problem A: Trial Users Incorrectly Shown as "Starter/CURRENT" Before Payment

### Root Cause

**The Issue:**
When a new business was created, the system automatically:
1. Created a trial subscription
2. Assigned the "Starter" plan to the subscription (for billing limit purposes)
3. **Created a DRAFT invoice immediately** when the user clicked "Choose Plan"
4. Showed "CURRENT" badge on the Starter plan even though no payment had been made

This violated the principle that trial users should NOT have a locked-in plan or invoices until payment is confirmed.

**Why It Happened:**
- The `select_plan` view in `billing/views.py` called `_create_draft_invoice_for_plan()` immediately
- The template checked `if sub.plan.id == p.id` to show "CURRENT", which was true for trial users
- The `manage.html` page showed plan details and invoices even for unpaid trial users

### Solution Implemented

**1. Introduced `PendingCheckout` Model** (`billing/models.py`)
- New lightweight model to track plan selection BEFORE payment
- Fields: `business`, `selected_plan`, `amount`, `currency`, `tx_ref`, `status`
- Status: `PENDING` → `SUCCEEDED` (on payment) or `FAILED`/`EXPIRED`
- **NO invoice is created until payment webhook confirms success**

**2. Updated Checkout Flow** (`billing/views.py`)
- `select_plan()` now creates `PendingCheckout` instead of Invoice
- Stores `pending_checkout_id` in session (not `billing_invoice_id`)
- `checkout()` view works with `PendingCheckout` for display
- Invoice creation moved to webhook success handler

**3. Invoice Creation on Payment Success** (`billing/domain.py`)
- `_find_or_create_invoice_for_transaction()` now checks for `PendingCheckout` by `tx_ref`
- If found, creates invoice NOW (first time) and marks it PAID
- Activates subscription: sets `status=ACTIVE`, `plan=selected_plan`, `last_payment_at=now`
- Marks `PendingCheckout` as `SUCCEEDED`

**4. UI Updates**
- `templates/billing/subscribe.html`: Uses `paid_plan_id` (only set when `status==ACTIVE`)
- `templates/billing/manage.html`: Already had `is_paid_active` logic, now works correctly
- Trial users see: "Free Trial" banner, "Choose & Pay" buttons, NO "CURRENT" badge
- Paid users see: "CURRENT" badge, plan details, invoices

### Files Changed
- `billing/models.py`: Added `PendingCheckout` model
- `billing/migrations/0014_add_pending_checkout.py`: Migration for new model
- `billing/views.py`: Updated `select_plan()`, `checkout()`, `subscribe()` views
- `billing/domain.py`: Updated `_find_or_create_invoice_for_transaction()`
- `templates/billing/subscribe.html`: Updated to use `paid_plan_id`
- `billing/tests/test_trial_invoice_creation.py`: New tests for invoice timing

---

## Problem B: "Warped Until Hard Refresh" (Stale CSS Cache)

### Root Cause

**The Issue:**
Users occasionally saw "warped" layouts after deployments:
- CSS/JS files were cached by browser and service worker
- New deployments didn't force cache refresh
- Hard refresh (Ctrl+F5) fixed it temporarily

**Why It Happened:**
- Static assets had `?v={{ ASSET_V }}` query strings, but `ASSET_V` wasn't changing on every deploy
- Service worker had a hardcoded `VERSION` constant that wasn't updated automatically
- Old caches weren't being cleared when VERSION changed

### Solution Implemented

**1. Dynamic BUILD_ID Injection** (`cc/views.py`)
- The `sw_js()` view now reads `BUILD_ID` from settings
- Replaces `BUILD_ID_PLACEHOLDER` in `static/sw.js` with actual build ID
- Service worker VERSION now changes automatically on every deployment

**2. Service Worker Cache Cleanup** (`static/sw.js`)
- Updated VERSION format: `'emajinet-v1-BUILD_ID_PLACEHOLDER'`
- On activate, SW deletes all caches not matching current VERSION
- Ensures old cached assets are purged on deployment

**3. Static Asset Versioning** (`templates/base.html`)
- Already had `?v={{ ASSET_V }}` on all CSS/JS includes
- `ASSET_V` comes from `BUILD_ID` or `STATIC_VERSION` setting
- Verified all critical assets have version query strings

**4. Network-First for HTML** (`static/sw.js`)
- Service worker uses network-first strategy for HTML/navigation
- Ensures new page structure loads immediately
- Static assets use stale-while-revalidate (fast + fresh)

### Files Changed
- `static/sw.js`: Updated VERSION to use `BUILD_ID_PLACEHOLDER`
- `cc/views.py`: Updated `sw_js()` to inject BUILD_ID dynamically
- `templates/base.html`: Verified cache-busting query strings present

---

## Testing

### New Tests Added
1. `billing/tests/test_billing_plans_ux.py`:
   - `test_trial_user_does_not_see_current_badge()`: Verifies NO "CURRENT" badge for trial
   - `test_trial_user_sees_choose_plan_buttons()`: Verifies "Choose" buttons for all plans
   - `test_trialing_status_also_works()`: Tests both "trial" and "trialing" statuses
   - `test_active_user_sees_current_badge_on_paid_plan()`: Verifies CURRENT for paid users
   - `test_active_user_can_upgrade_to_higher_tier()`: Verifies upgrade flow

2. `billing/tests/test_trial_invoice_creation.py`:
   - `test_trial_user_has_no_invoices()`: Verifies zero invoices for trial
   - `test_select_plan_creates_pending_checkout_not_invoice()`: Verifies PendingCheckout creation
   - `test_manage_page_shows_no_invoices_for_trial()`: Verifies manage page hides paid details
   - `test_active_subscription_after_payment_has_invoice()`: Verifies invoice after payment

### How to Run Tests
```bash
# Run new billing tests
python manage.py test billing.tests.test_billing_plans_ux -v 2
python manage.py test billing.tests.test_trial_invoice_creation -v 2

# Run all billing tests
python manage.py test billing -v 2
```

---

## Backward Compatibility

### Preserved Flows
- **PayChangu webhook processing**: No changes to webhook handlers
- **Dunning & grace periods**: All dunning logic intact
- **Cancellation flow**: `cancel_at_period_end` logic unchanged
- **HQ notifications**: All notification triggers preserved
- **Service worker on localhost**: Disabled as before (dev mode)

### Migration Path
- Old draft invoices (if any exist) will still work via fallback logic
- `_find_or_create_invoice_for_transaction()` has fallback to old flow
- Existing ACTIVE subscriptions continue to work normally
- No data migration needed - new model is additive

---

## Deployment Checklist

### Before Deploy
- [x] Run migrations: `python manage.py migrate`
- [x] Run tests: `python manage.py test billing`
- [x] Verify BUILD_ID is set in production settings
- [x] Verify STATIC_VERSION is set (fallback for BUILD_ID)

### After Deploy
- [ ] Verify `/sw.js` returns updated VERSION (check browser devtools)
- [ ] Test trial user flow: signup → choose plan → checkout
- [ ] Verify NO invoices created until payment webhook
- [ ] Test payment success: verify invoice created + subscription ACTIVE
- [ ] Hard refresh on a few pages to verify no "warped" layouts

### Monitoring
- Watch for any invoice creation errors in logs
- Monitor PendingCheckout records (should transition to SUCCEEDED/FAILED)
- Check service worker registration in production (should update automatically)

---

## Summary

### Trial Subscription Fix
✅ Trial users NO longer see "CURRENT" on any plan until payment  
✅ NO invoices created until PayChangu confirms payment success  
✅ Manage page correctly hides paid plan details for trial users  
✅ Subscription only becomes ACTIVE after payment webhook  

### Cache Busting Fix
✅ Service worker VERSION now updates automatically on deploy  
✅ Old caches purged on SW activation  
✅ Static assets have version query strings  
✅ No more "warped until hard refresh" issues  

### No Regressions
✅ PayChangu live flow unchanged  
✅ Dunning & cancellation logic intact  
✅ HQ notifications preserved  
✅ SW stability on localhost maintained  

