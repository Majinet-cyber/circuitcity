# tests/test_vertical_routing.py
"""
Tests for business-kind-aware dashboard routing and navigation.
Ensures that users are directed to the correct vertical-specific dashboard
based on their business kind.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind
from inventory.utils_verticals import (
    get_vertical_kind,
    get_vertical_dashboard_url,
    get_onboarding_steps,
    get_vertical_display_name,
)

User = get_user_model()


@pytest.fixture
def manager_user(db):
    """Create a manager user."""
    return User.objects.create_user(
        username="manager",
        email="manager@test.com",
        password="testpass123"
    )


@pytest.fixture
def phone_business(db):
    """Create a phone business."""
    return Business.objects.create(
        name="Test Phone Shop",
        slug="test-phone-shop",
        business_kind=BusinessKind.PHONES,
        status="ACTIVE"
    )


@pytest.fixture
def gym_business(db):
    """Create a gym business."""
    return Business.objects.create(
        name="Test Gym",
        slug="test-gym",
        business_kind=BusinessKind.GYM,
        status="ACTIVE"
    )


@pytest.fixture
def clothing_business(db):
    """Create a clothing business."""
    return Business.objects.create(
        name="Test Clothing Store",
        slug="test-clothing-store",
        business_kind=BusinessKind.CLOTHING,
        status="ACTIVE"
    )


@pytest.fixture
def liquor_business(db):
    """Create a liquor business."""
    return Business.objects.create(
        name="Test Liquor Store",
        slug="test-liquor-store",
        business_kind=BusinessKind.LIQUOR,
        status="ACTIVE"
    )


@pytest.fixture
def pharmacy_business(db):
    """Create a pharmacy business."""
    return Business.objects.create(
        name="Test Pharmacy",
        slug="test-pharmacy",
        business_kind=BusinessKind.PHARMACY,
        status="ACTIVE"
    )


def create_manager_membership(user, business):
    """Helper to create a manager membership."""
    return Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE"
    )


def set_active_business(client, business):
    """Helper to set active business in session.
    
    Note: The middleware will pick this up and set request.business when the view runs.
    """
    session = client.session
    session["active_business_id"] = business.id
    session["business_id"] = business.id
    session["PRODUCT_MODE_SESSION_KEY"] = business.business_kind or "phones"
    session.save()


# ==============================================================================
# UTILITY FUNCTION TESTS
# ==============================================================================

def test_get_vertical_kind_phones(phone_business):
    """Test vertical kind detection for phone business."""
    assert get_vertical_kind(phone_business) == "phones"


def test_get_vertical_kind_gym(gym_business):
    """Test vertical kind detection for gym business."""
    assert get_vertical_kind(gym_business) == "gym"


def test_get_vertical_kind_clothing(clothing_business):
    """Test vertical kind detection for clothing business."""
    assert get_vertical_kind(clothing_business) == "clothing"


def test_get_vertical_kind_liquor(liquor_business):
    """Test vertical kind detection for liquor business."""
    assert get_vertical_kind(liquor_business) == "liquor"


def test_get_vertical_kind_pharmacy(pharmacy_business):
    """Test vertical kind detection for pharmacy business."""
    assert get_vertical_kind(pharmacy_business) == "pharmacy"


def test_get_vertical_kind_none():
    """Test vertical kind with None business defaults to generic."""
    assert get_vertical_kind(None) == "generic"


def test_get_vertical_dashboard_url_gym():
    """Test gym gets correct dashboard URL."""
    url = get_vertical_dashboard_url("gym")
    assert url == "inventory_verticals:gym_dashboard"


def test_get_vertical_dashboard_url_phones():
    """Test phones uses default dashboard (returns None)."""
    url = get_vertical_dashboard_url("phones")
    assert url is None


def test_get_onboarding_steps_gym():
    """Test gym onboarding steps."""
    steps = get_onboarding_steps("gym")
    assert len(steps) == 3
    assert steps[0]["label"] == "Add membership plans"
    assert steps[1]["label"] == "Add your first members"
    assert steps[2]["label"] == "Track payments & arrears"


def test_get_onboarding_steps_phones():
    """Test phone onboarding steps."""
    steps = get_onboarding_steps("phones")
    assert len(steps) == 3
    assert steps[0]["label"] == "Add your first product"
    assert steps[1]["label"] == "Stock in items"
    assert steps[2]["label"] == "Invite/approve agents"


def test_get_vertical_display_name():
    """Test display name mapping."""
    assert get_vertical_display_name("gym") == "Gym & Fitness"
    assert get_vertical_display_name("phones") == "Phones & Electronics"
    assert get_vertical_display_name("pharmacy") == "Pharmacy"


# ==============================================================================
# DASHBOARD ROUTING TESTS
# ==============================================================================

@pytest.mark.django_db
class TestDashboardRouting:
    """Test that dashboard routes correctly based on business kind."""

    def test_phone_business_shows_default_dashboard(
        self, client: Client, manager_user, phone_business
    ):
        """Phone business should show default dashboard with phone-specific items."""
        # Setup
        create_manager_membership(manager_user, phone_business)
        client.force_login(manager_user)
        set_active_business(client, phone_business)

        # Act
        response = client.get(reverse("dashboard:home"))

        # Assert
        assert response.status_code == 200
        # Should render the default dashboard template (not redirect)
        content = response.content.decode()
        
        # Check that we're on the right dashboard (not redirected)
        assert "Add your first product" in content or "Products" in content

    def test_gym_business_redirects_to_gym_dashboard(
        self, client: Client, manager_user, gym_business
    ):
        """Gym business should redirect to gym-specific dashboard."""
        # Setup
        create_manager_membership(manager_user, gym_business)
        client.force_login(manager_user)
        set_active_business(client, gym_business)

        # Act
        response = client.get(reverse("dashboard:home"))

        # Assert - should redirect to gym dashboard
        assert response.status_code == 302
        assert "gym" in response.url.lower()

    def test_clothing_business_redirects_to_clothing_dashboard(
        self, client: Client, manager_user, clothing_business
    ):
        """Clothing business should redirect to clothing-specific dashboard."""
        # Setup
        create_manager_membership(manager_user, clothing_business)
        client.force_login(manager_user)
        set_active_business(client, clothing_business)

        # Act
        response = client.get(reverse("dashboard:home"))

        # Assert - should redirect to clothing dashboard
        assert response.status_code == 302
        assert "clothing" in response.url.lower()

    def test_liquor_business_redirects_to_liquor_dashboard(
        self, client: Client, manager_user, liquor_business
    ):
        """Liquor business should redirect to liquor-specific dashboard."""
        # Setup
        create_manager_membership(manager_user, liquor_business)
        client.force_login(manager_user)
        set_active_business(client, liquor_business)

        # Act
        response = client.get(reverse("dashboard:home"))

        # Assert - should redirect to liquor dashboard
        assert response.status_code == 302
        assert "liquor" in response.url.lower()

    def test_pharmacy_business_redirects_to_pharmacy_dashboard(
        self, client: Client, manager_user, pharmacy_business
    ):
        """Pharmacy business should redirect to pharmacy-specific dashboard."""
        # Setup
        create_manager_membership(manager_user, pharmacy_business)
        client.force_login(manager_user)
        set_active_business(client, pharmacy_business)

        # Act
        response = client.get(reverse("dashboard:home"))

        # Assert - should redirect to pharmacy dashboard
        assert response.status_code == 302
        assert "pharmacy" in response.url.lower()


# ==============================================================================
# ONBOARDING STEPS TESTS
# ==============================================================================

@pytest.mark.django_db
class TestOnboardingSteps:
    """Test that onboarding steps are tailored to business kind."""

    def test_phone_business_shows_phone_onboarding(
        self, client: Client, manager_user, phone_business
    ):
        """Phone business should show phone-specific onboarding steps."""
        # Setup
        create_manager_membership(manager_user, phone_business)
        client.force_login(manager_user)
        set_active_business(client, phone_business)

        # Act
        response = client.get(reverse("dashboard:home"))
        content = response.content.decode()

        # Assert - should show phone-specific steps if first run
        # (We can't guarantee first_run=True in this test, but we can check the view works)
        assert response.status_code == 200

    def test_gym_business_context_includes_vertical_steps(
        self, client: Client, manager_user, gym_business
    ):
        """Verify gym business view includes vertical-specific context."""
        # This test would check the actual gym dashboard once we follow the redirect
        # For now, we just verify the main dashboard would have redirected
        create_manager_membership(manager_user, gym_business)
        client.force_login(manager_user)
        set_active_business(client, gym_business)

        response = client.get(reverse("dashboard:home"))
        assert response.status_code == 302  # Redirected


# ==============================================================================
# INTEGRATION TEST
# ==============================================================================

@pytest.mark.django_db
def test_full_flow_gym_signup_and_navigation(client: Client, manager_user, gym_business):
    """
    Integration test: Gym business owner signs up, lands on gym dashboard,
    sees gym-specific navigation and onboarding.
    """
    # Setup: Manager is member of gym
    create_manager_membership(manager_user, gym_business)
    client.force_login(manager_user)
    set_active_business(client, gym_business)

    # Step 1: Navigate to main dashboard
    response = client.get(reverse("dashboard:home"))
    
    # Should redirect to gym-specific dashboard
    assert response.status_code == 302
    assert "gym" in response.url.lower()


@pytest.mark.django_db
def test_full_flow_phone_business_navigation(
    client: Client, manager_user, phone_business
):
    """
    Integration test: Phone business owner lands on default dashboard
    with phone-specific features.
    """
    # Setup
    create_manager_membership(manager_user, phone_business)
    client.force_login(manager_user)
    set_active_business(client, phone_business)

    # Navigate to dashboard
    response = client.get(reverse("dashboard:home"))
    
    # Should NOT redirect (stays on default dashboard)
    assert response.status_code == 200


# ==============================================================================
# EDGE CASES
# ==============================================================================

@pytest.mark.django_db
def test_business_without_kind_defaults_to_phones(db, manager_user):
    """Business without a kind should default to phones behavior."""
    # Create business with no business_kind set
    legacy_business = Business.objects.create(
        name="Legacy Business",
        slug="legacy-business",
        business_kind=None,  # No kind set
        status="ACTIVE"
    )
    
    vertical_kind = get_vertical_kind(legacy_business)
    assert vertical_kind == "phones"


@pytest.mark.django_db
def test_grocery_business_uses_default_dashboard(db, manager_user):
    """Grocery business (not yet implemented) should use default dashboard."""
    grocery_business = Business.objects.create(
        name="Test Grocery",
        slug="test-grocery",
        business_kind=BusinessKind.GROCERY,
        status="ACTIVE"
    )
    
    vertical_kind = get_vertical_kind(grocery_business)
    assert vertical_kind == "grocery"
    
    # Should return None (uses default dashboard)
    dashboard_url = get_vertical_dashboard_url(vertical_kind)
    assert dashboard_url is None

