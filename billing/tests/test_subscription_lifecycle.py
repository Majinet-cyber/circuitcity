# billing/tests/test_subscription_lifecycle.py
"""
Tests for subscription lifecycle management and automatic status transitions.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.utils import timezone

from billing import domain
from billing.models import BusinessSubscription, SubscriptionPlan
from tests.helpers.tenant_setup import make_business, make_user


@pytest.mark.django_db
class TestSubscriptionLifecycle:
    """Test subscription lifecycle state transitions."""

    @pytest.fixture
    def setup_data(self):
        """Create test user, business, and subscription."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test Biz", slug="test-biz")

        plan = SubscriptionPlan.objects.create(
            code="test-plan",
            name="Test Plan",
            amount=Decimal("10000.00"),
            currency="MWK",
        )

        subscription = BusinessSubscription.start_trial(
            business=business,
            plan=plan,
            days=7,  # 7-day trial for testing
        )

        return {
            "user": user,
            "business": business,
            "plan": plan,
            "subscription": subscription,
        }

    def test_activate_subscription(self, setup_data):
        """Test activating subscription."""
        sub = setup_data["subscription"]

        # Activate subscription
        domain.activate_subscription(sub, payment_method="airtel")

        sub.refresh_from_db()
        assert sub.status == BusinessSubscription.Status.ACTIVE
        assert sub.payment_method == BusinessSubscription.Method.AIRTEL
        assert sub.last_payment_at is not None
        assert sub.current_period_start is not None
        assert sub.current_period_end is not None
        assert sub.next_billing_date is not None

    def test_mark_past_due(self, setup_data):
        """Test marking subscription as past due."""
        sub = setup_data["subscription"]

        domain.mark_past_due(sub)

        sub.refresh_from_db()
        assert sub.status == BusinessSubscription.Status.PAST_DUE

    def test_suspend_subscription(self, setup_data):
        """Test suspending subscription."""
        sub = setup_data["subscription"]

        reason = "Payment failed after grace period"
        domain.suspend_subscription(sub, reason=reason)

        sub.refresh_from_db()
        assert sub.status == BusinessSubscription.Status.SUSPENDED
        assert sub.meta.get("suspended_reason") == reason
        assert "suspended_at" in sub.meta

    def test_refresh_status_trial_expired(self, setup_data):
        """Test that refresh_status transitions TRIAL → PAST_DUE when trial expires."""
        sub = setup_data["subscription"]

        # Set trial_end to past
        sub.trial_end = timezone.now() - timedelta(hours=1)
        sub.save()

        domain.refresh_subscription_status(sub)

        sub.refresh_from_db()
        assert sub.status == BusinessSubscription.Status.PAST_DUE

    def test_refresh_status_period_expired(self, setup_data):
        """Test that refresh_status transitions ACTIVE → PAST_DUE when period expires."""
        sub = setup_data["subscription"]

        # Activate subscription
        sub.status = BusinessSubscription.Status.ACTIVE
        sub.current_period_start = timezone.now() - timedelta(days=30)
        sub.current_period_end = timezone.now() - timedelta(hours=1)
        sub.save()

        domain.refresh_subscription_status(sub)

        sub.refresh_from_db()
        assert sub.status == BusinessSubscription.Status.PAST_DUE

    def test_refresh_status_grace_expired(self, setup_data, settings):
        """Test that refresh_status transitions PAST_DUE → SUSPENDED after grace period."""
        settings.BILLING_GRACE_DAYS = 7

        sub = setup_data["subscription"]

        # Set subscription to PAST_DUE with grace period expired
        sub.status = BusinessSubscription.Status.PAST_DUE
        sub.current_period_end = timezone.now() - timedelta(days=10)  # 10 days ago
        sub.next_billing_date = sub.current_period_end
        sub.save()

        domain.refresh_subscription_status(sub)

        sub.refresh_from_db()
        assert sub.status == BusinessSubscription.Status.SUSPENDED

    def test_refresh_status_within_grace(self, setup_data, settings):
        """Test that refresh_status does NOT suspend if within grace period."""
        settings.BILLING_GRACE_DAYS = 7

        sub = setup_data["subscription"]

        # Set subscription to PAST_DUE but within grace
        sub.status = BusinessSubscription.Status.PAST_DUE
        sub.current_period_end = timezone.now() - timedelta(days=3)  # 3 days ago
        sub.next_billing_date = sub.current_period_end
        sub.save()

        domain.refresh_subscription_status(sub)

        sub.refresh_from_db()
        assert sub.status == BusinessSubscription.Status.PAST_DUE  # Still past due

    def test_refresh_status_skips_terminal_states(self, setup_data):
        """Test that refresh_status skips already-terminal states."""
        sub = setup_data["subscription"]

        # Set to SUSPENDED
        sub.status = BusinessSubscription.Status.SUSPENDED
        sub.trial_end = timezone.now() - timedelta(days=1)
        sub.save()

        domain.refresh_subscription_status(sub)

        sub.refresh_from_db()
        assert sub.status == BusinessSubscription.Status.SUSPENDED  # Unchanged


@pytest.mark.django_db
class TestProcessSubscriptionRenewals:
    """Test bulk subscription renewal processing."""

    @pytest.fixture
    def setup_multiple_subs(self):
        """Create multiple subscriptions in different states."""
        user = make_user(email="admin@test.com", password="pass")

        plan = SubscriptionPlan.objects.create(
            code="test-plan",
            name="Test Plan",
            amount=Decimal("10000.00"),
            currency="MWK",
        )

        # Create 3 businesses with different subscription states
        subs = []

        # 1. Trial expired (should → PAST_DUE)
        biz1 = make_business(created_by=user, name="Biz 1", slug="biz-1")
        sub1 = BusinessSubscription.start_trial(business=biz1, plan=plan, days=7)
        sub1.trial_end = timezone.now() - timedelta(hours=1)
        sub1.save()
        subs.append(sub1)

        # 2. Active period expired (should → PAST_DUE)
        biz2 = make_business(created_by=user, name="Biz 2", slug="biz-2")
        sub2 = BusinessSubscription.start_trial(business=biz2, plan=plan, days=7)
        sub2.status = BusinessSubscription.Status.ACTIVE
        sub2.current_period_end = timezone.now() - timedelta(hours=1)
        sub2.save()
        subs.append(sub2)

        # 3. Past due with grace expired (should → SUSPENDED)
        biz3 = make_business(created_by=user, name="Biz 3", slug="biz-3")
        sub3 = BusinessSubscription.start_trial(business=biz3, plan=plan, days=7)
        sub3.status = BusinessSubscription.Status.PAST_DUE
        sub3.current_period_end = timezone.now() - timedelta(days=10)
        sub3.next_billing_date = sub3.current_period_end
        sub3.save()
        subs.append(sub3)

        # 4. Active and current (should not change)
        biz4 = make_business(created_by=user, name="Biz 4", slug="biz-4")
        sub4 = BusinessSubscription.start_trial(business=biz4, plan=plan, days=7)
        sub4.status = BusinessSubscription.Status.ACTIVE
        sub4.current_period_end = timezone.now() + timedelta(days=15)
        sub4.save()
        subs.append(sub4)

        return {
            "subscriptions": subs,
            "sub1": sub1,
            "sub2": sub2,
            "sub3": sub3,
            "sub4": sub4,
        }

    def test_process_subscription_renewals(self, setup_multiple_subs, settings):
        """Test that process_subscription_renewals transitions all subscriptions correctly."""
        settings.BILLING_GRACE_DAYS = 7

        stats = domain.process_subscription_renewals()

        # Refresh subscriptions
        sub1 = setup_multiple_subs["sub1"]
        sub2 = setup_multiple_subs["sub2"]
        sub3 = setup_multiple_subs["sub3"]
        sub4 = setup_multiple_subs["sub4"]

        sub1.refresh_from_db()
        sub2.refresh_from_db()
        sub3.refresh_from_db()
        sub4.refresh_from_db()

        # Check transitions
        assert sub1.status == BusinessSubscription.Status.PAST_DUE  # Trial expired
        assert sub2.status == BusinessSubscription.Status.PAST_DUE  # Period expired
        assert sub3.status == BusinessSubscription.Status.SUSPENDED  # Grace expired
        assert sub4.status == BusinessSubscription.Status.ACTIVE  # Unchanged

        # Check stats
        assert stats["total_checked"] >= 4
        assert stats["expired_trials"] >= 1
        assert stats["expired_periods"] >= 1
        assert stats["suspended"] >= 1
        assert stats["errors"] == 0

    def test_process_subscription_renewals_empty(self):
        """Test that process_subscription_renewals handles no subscriptions gracefully."""
        stats = domain.process_subscription_renewals()

        assert stats["total_checked"] >= 0
        assert stats["errors"] == 0


@pytest.mark.django_db
class TestActivateSubscriptionWithPaymentMethod:
    """Test subscription activation with different payment methods."""

    @pytest.fixture
    def setup_data(self):
        """Create test subscription."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test Biz", slug="test-biz")

        plan = SubscriptionPlan.objects.create(
            code="test-plan",
            name="Test Plan",
            amount=Decimal("10000.00"),
            currency="MWK",
        )

        subscription = BusinessSubscription.start_trial(
            business=business,
            plan=plan,
            days=7,
        )

        return {"subscription": subscription}

    def test_activate_with_airtel(self, setup_data):
        """Test activation with Airtel Money."""
        sub = setup_data["subscription"]
        domain.activate_subscription(sub, payment_method="airtel")

        sub.refresh_from_db()
        assert sub.payment_method == BusinessSubscription.Method.AIRTEL

    def test_activate_with_tnm(self, setup_data):
        """Test activation with TNM Mpamba."""
        sub = setup_data["subscription"]
        domain.activate_subscription(sub, payment_method="tnm")

        sub.refresh_from_db()
        assert sub.payment_method == BusinessSubscription.Method.AIRTEL  # Maps to same enum

    def test_activate_with_card(self, setup_data):
        """Test activation with card."""
        sub = setup_data["subscription"]
        domain.activate_subscription(sub, payment_method="card")

        sub.refresh_from_db()
        assert sub.payment_method == BusinessSubscription.Method.CARD

    def test_activate_with_unknown_method(self, setup_data):
        """Test activation with unknown payment method defaults to NONE."""
        sub = setup_data["subscription"]
        domain.activate_subscription(sub, payment_method="unknown_method")

        sub.refresh_from_db()
        assert sub.payment_method == BusinessSubscription.Method.NONE
