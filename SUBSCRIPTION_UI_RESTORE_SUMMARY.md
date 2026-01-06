# Subscription Management UI Restore - January 6, 2026

## Problem
After recent fixes, the subscription management UI regressed:
- On `/billing/plans/` page, trial subscriptions showed "Trial" badge but NO "Manage Subscription" button
- Users couldn't access subscription management features during trial period
- This was a regression from commit e25dd8e where subscription management was fully functional

## Root Cause
In `templates/billing/subscribe.html`, the "Manage Subscription" button only appeared for `active` subscriptions (line 187-189), but NOT for `trial`/`trialing` subscriptions.

## Solution Implemented

### 1. Fixed `templates/billing/subscribe.html`
**Changed:** Trial subscription banner (lines 148-171)
- **Before:** Trial banner had no action button, just informational text
- **After:** Added "Manage Subscription" button to trial banner, matching the pattern used for active subscriptions

```html
<!-- BEFORE (lines 148-171) -->
{% elif sub.status == "trial" or sub.status == "trialing" %}
<div class="g" style="...">
  <div class="row-top">
    <div style="display: flex; align-items: center; gap: 12px; width: 100%;">
      <span style="font-size: 1.5rem;">🎯</span>
      <div style="flex: 1;">
        <p>You're on a free trial</p>
        <!-- ... trial info ... -->
      </div>
    </div>
  </div>
</div>

<!-- AFTER (lines 148-171) -->
{% elif sub.status == "trial" or sub.status == "trialing" %}
<div class="g" style="...">
  <div style="display: flex; align-items: center; gap: 12px; width: 100%; flex-wrap: wrap;">
    <span style="font-size: 1.5rem;">🎯</span>
    <div style="flex: 1; min-width: 200px;">
      <p>You're on a free trial</p>
      <!-- ... trial info ... -->
    </div>
    <a href="{% url 'billing:manage' %}" class="btn" style="background: linear-gradient(135deg, #6366f1, #8b5cf6); color: white; box-shadow: 0 6px 16px rgba(99, 102, 241, 0.3);">
      Manage Subscription
    </a>
  </div>
</div>
```

### 2. Added Tests in `billing/tests.py`
Added two new test methods to `BillingPlansViewTest` class:

```python
def test_plans_page_shows_manage_subscription_for_trial(self):
    """Trial subscriptions should show 'Manage Subscription' button"""
    sub = BusinessSubscription.start_trial(
        business=self.business,
        plan=self.plan,
        days=30
    )

    self.client.login(username="testuser", password="testpass123")
    response = self.client.get(reverse('billing:plans'))

    # Should show trial banner with Manage Subscription button
    self.assertContains(response, "You're on a free trial")
    self.assertContains(response, "Manage Subscription")
    self.assertContains(response, reverse('billing:manage'))

def test_plans_page_shows_manage_subscription_for_active(self):
    """Active subscriptions should show 'Manage Subscription' button"""
    sub = BusinessSubscription.objects.create(
        business=self.business,
        plan=self.plan,
        status=BusinessSubscription.Status.ACTIVE
    )

    self.client.login(username="testuser", password="testpass123")
    response = self.client.get(reverse('billing:plans'))

    # Should show active banner with Manage Subscription button
    self.assertContains(response, "You are subscribed")
    self.assertContains(response, "Manage Subscription")
    self.assertContains(response, reverse('billing:manage'))
```

## Files Changed
1. `templates/billing/subscribe.html` - Added "Manage Subscription" button to trial banner
2. `billing/tests.py` - Added 2 new tests to verify the fix

## Verification Steps

### Manual Testing
1. Start the development server:
   ```bash
   python manage.py runserver
   ```

2. Log in as a user with a trial subscription

3. Navigate to `/billing/plans/`

4. Verify:
   - Trial badge is displayed
   - "Manage Subscription" button is visible
   - Clicking button navigates to `/billing/manage/`
   - Manage page shows full subscription controls (cancel, billing phone, etc.)

### Automated Testing
Run the billing tests:
```bash
python manage.py test billing.tests.BillingPlansViewTest
```

Expected: All tests pass, including the 2 new tests.

## What Was NOT Changed (Preserved)
✅ Service worker fixes (`/sw.js` bypass constants, localhost SW disable)
✅ Notification overlay fixes (no layout shift/warped views)
✅ All dunning/cancellation/HQ notification features from e25dd8e
✅ `base.html` subscription badges and banners
✅ `templates/billing/manage.html` (already correct)

## Commit Message
```
Restore: subscription management UI for trial subscriptions

Fix regression where "Manage Subscription" button was missing for trial
subscriptions on /billing/plans/ page.

Changes:
- templates/billing/subscribe.html: Add "Manage Subscription" button to trial banner
- billing/tests.py: Add tests to verify trial+active subscriptions show manage button

This restores the full subscription management behavior from commit e25dd8e
while preserving recent SW fixes and notification overlay improvements.

Fixes: Trial users can now access subscription management features
Tests: 2 new tests verify manage button appears for trial and active states
```

## Next Steps
1. Commit the changes with the message above
2. Run full test suite to ensure no regressions
3. Test manually on local server
4. Push to branch `fix/cypress-pharmacy`

## Safety Tag Created
Before making changes, created safety tag:
```bash
git tag before-subscription-restore-20260106
```

To rollback if needed:
```bash
git reset --hard before-subscription-restore-20260106
```
