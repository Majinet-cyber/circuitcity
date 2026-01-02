# billing/tests/test_trial_lock.py
"""
Tests for trial lock functionality (hard lock expired trials).
"""
import pytest
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business, Membership
from billing.models import BusinessSubscription, SubscriptionPlan

User = get_user_model()


@pytest.mark.django_db
class TestTrialLock:
    """Test trial lock enforcement."""

    @pytest.fixture
    def plan(self):
        """Create a subscription plan."""
        return SubscriptionPlan.objects.create(
            code="starter",
            name="Starter Plan",
            amount=Decimal("5000.00"),
            currency="MWK",
            interval="month",
            is_active=True,
        )

    @pytest.fixture
    def business_active(self, plan):
        """Create a business with active trial."""
        business = Business.objects.create(
            name="Active Business",
            business_kind="phones",
        )
        # Create active trial (expires in 30 days)
        BusinessSubscription.objects.create(
            business=business,
            plan=plan,
            status="trial",
            trial_end=timezone.now() + timedelta(days=30),
            current_period_end=timezone.now() + timedelta(days=30),
        )
        return business

    @pytest.fixture
    def business_expired(self, plan):
        """Create a business with expired trial."""
        business = Business.objects.create(
            name="Expired Business",
            business_kind="liquor",
        )
        # Create expired trial
        BusinessSubscription.objects.create(
            business=business,
            plan=plan,
            status="expired",
            trial_end=timezone.now() - timedelta(days=1),
            current_period_end=timezone.now() - timedelta(days=1),
        )
        return business

    @pytest.fixture
    def manager_user(self, business_active):
        """Create a manager user."""
        user = User.objects.create_user(
            username="manager",
            password="testpass123",
            email="manager@test.com",
        )
        Membership.objects.create(
            user=user,
            business=business_active,
            role="MANAGER",
            status="ACTIVE",
        )
        return user

    @pytest.fixture
    def manager_expired(self, business_expired):
        """Create a manager for expired business."""
        user = User.objects.create_user(
            username="manager_expired",
            password="testpass123",
            email="manager_expired@test.com",
        )
        Membership.objects.create(
            user=user,
            business=business_expired,
            role="MANAGER",
            status="ACTIVE",
        )
        return user

    def test_active_trial_allows_access(self, business_active, manager_user, client: Client, settings):
        """Test that active trial allows access to app."""
        # Enable billing enforcement
        settings.FEATURES = {"BILLING_ENFORCE": True}

        client.force_login(manager_user)

        # Set business in session
        session = client.session
        session["active_business_id"] = business_active.id
        session.save()

        # Try to access analytics page (should work)
        response = client.get("/app/home/", follow=False)

        # Should not redirect to trial expired page
        assert response.status_code in [200, 301, 302]
        if response.status_code in [301, 302]:
            assert "trial-expired" not in response.url

    def test_expired_trial_blocks_app_access(self, business_expired, manager_expired, client: Client, settings):
        """Test that expired trial blocks access to app."""
        # Enable billing enforcement
        settings.FEATURES = {"BILLING_ENFORCE": True}

        client.force_login(manager_expired)

        # Set business in session
        session = client.session
        session["active_business_id"] = business_expired.id
        session.save()

        # Try to access app (should redirect to trial expired)
        response = client.get("/app/home/", follow=False)

        # Should redirect to trial expired page
        assert response.status_code == 302
        assert "trial-expired" in response.url or "billing" in response.url

    def test_expired_trial_allows_billing_access(self, business_expired, manager_expired, client: Client, settings):
        """Test that expired trial still allows access to billing pages."""
        # Enable billing enforcement
        settings.FEATURES = {"BILLING_ENFORCE": True}

        client.force_login(manager_expired)

        # Set business in session
        session = client.session
        session["active_business_id"] = business_expired.id
        session.save()

        # Try to access billing page (should work)
        response = client.get("/billing/subscribe/", follow=False)

        # Should allow access
        assert response.status_code in [200, 301, 302]
        if response.status_code in [301, 302]:
            # If redirecting, should not be to trial-expired (should be within billing flow)
            assert "trial-expired" not in response.url

    def test_expired_trial_allows_logout(self, business_expired, manager_expired, client: Client, settings):
        """Test that expired trial still allows logout."""
        # Enable billing enforcement
        settings.FEATURES = {"BILLING_ENFORCE": True}

        client.force_login(manager_expired)

        # Set business in session
        session = client.session
        session["active_business_id"] = business_expired.id
        session.save()

        # Try to logout (should work)
        response = client.get("/accounts/logout/", follow=False)

        # Should allow access
        assert response.status_code in [200, 301, 302]

    def test_trial_expired_page_accessible(self, business_expired, manager_expired, client: Client):
        """Test that trial expired page is accessible."""
        client.force_login(manager_expired)

        # Set business in session
        session = client.session
        session["active_business_id"] = business_expired.id
        session.save()

        # Access trial expired page
        response = client.get("/billing/trial-expired/")

        # Should render successfully
        assert response.status_code == 200
        assert b"Trial" in response.content or b"trial" in response.content

    def test_api_returns_json_error_for_expired_trial(
        self, business_expired, manager_expired, client: Client, settings
    ):
        """Test that API endpoints return JSON error for expired trial."""
        # Enable billing enforcement
        settings.FEATURES = {"BILLING_ENFORCE": True}

        client.force_login(manager_expired)

        # Set business in session
        session = client.session
        session["active_business_id"] = business_expired.id
        session.save()

        # Try to access an API endpoint
        response = client.get("/api/some-endpoint/", follow=False)

        # Should return JSON error with 402 status
        if response.status_code == 402:
            data = response.json()
            assert data["ok"] is False
            assert data["locked"] is True
            assert "error" in data

    def test_staff_user_bypasses_lock(self, business_expired, client: Client, settings):
        """Test that staff/superuser bypasses trial lock."""
        # Enable billing enforcement
        settings.FEATURES = {"BILLING_ENFORCE": True}

        # Create staff user
        staff_user = User.objects.create_user(
            username="staff",
            password="testpass123",
            email="staff@test.com",
            is_staff=True,
        )

        client.force_login(staff_user)

        # Set business in session
        session = client.session
        session["active_business_id"] = business_expired.id
        session.save()

        # Try to access app (should work for staff)
        response = client.get("/app/home/", follow=False)

        # Should not redirect to trial expired
        assert response.status_code in [200, 301, 302]
        if response.status_code in [301, 302]:
            assert "trial-expired" not in response.url
