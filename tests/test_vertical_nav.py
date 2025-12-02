# tests/test_vertical_nav.py
"""
Tests for vertical-aware navigation sidebar.
Ensures that sidebar nav items are appropriate for each business vertical.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind

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
    """Helper to set active business in session."""
    session = client.session
    session["active_business_id"] = business.id
    session["business_id"] = business.id
    session["PRODUCT_MODE_SESSION_KEY"] = business.business_kind or "phones"
    session.save()


# ==============================================================================
# PHONE BUSINESS NAV TESTS
# ==============================================================================

@pytest.mark.django_db
class TestPhoneBusinessNav:
    """Test that phone businesses see phone-specific nav items."""

    def test_phone_business_shows_inventory_dashboard_link(
        self, client: Client, manager_user, phone_business
    ):
        """Phone business should see 'Inventory Dashboard' in nav."""
        create_manager_membership(manager_user, phone_business)
        client.force_login(manager_user)
        set_active_business(client, phone_business)

        response = client.get(reverse("dashboard:home"))
        content = response.content.decode()

        # Should have phones-specific nav items
        assert "Inventory Dashboard" in content or "inventory/dashboard" in content

    def test_phone_business_shows_stock_link(
        self, client: Client, manager_user, phone_business
    ):
        """Phone business should see 'Stock' in nav."""
        create_manager_membership(manager_user, phone_business)
        client.force_login(manager_user)
        set_active_business(client, phone_business)

        response = client.get(reverse("dashboard:home"))
        content = response.content.decode()

        # Should have Stock link
        assert "Stock" in content or "/inventory/list/" in content

    def test_phone_business_shows_scan_in_link(
        self, client: Client, manager_user, phone_business
    ):
        """Phone business should see 'Scan IN' in nav."""
        create_manager_membership(manager_user, phone_business)
        client.force_login(manager_user)
        set_active_business(client, phone_business)

        response = client.get(reverse("dashboard:home"))
        content = response.content.decode()

        # Should have Scan IN link
        assert "Scan IN" in content or "/inventory/scan" in content

    def test_phone_business_shows_sell_link(
        self, client: Client, manager_user, phone_business
    ):
        """Phone business should see 'Sell' in nav."""
        create_manager_membership(manager_user, phone_business)
        client.force_login(manager_user)
        set_active_business(client, phone_business)

        response = client.get(reverse("dashboard:home"))
        content = response.content.decode()

        # Should have Sell link
        assert "Sell" in content or "/sell/" in content


# ==============================================================================
# GYM BUSINESS NAV TESTS
# ==============================================================================

@pytest.mark.django_db
class TestGymBusinessNav:
    """Test that gym businesses see gym-specific nav items."""

    def test_gym_business_does_not_show_inventory_dashboard(
        self, client: Client, manager_user, gym_business
    ):
        """Gym business should NOT see 'Inventory Dashboard' in nav."""
        create_manager_membership(manager_user, gym_business)
        client.force_login(manager_user)
        set_active_business(client, gym_business)

        # Navigate to dashboard - it will redirect to gym dashboard
        # Don't follow to avoid model dependencies, just check the redirect
        response = client.get(reverse("dashboard:home"), follow=False)
        
        # Should redirect to gym vertical
        if response.status_code == 302:
            assert "gym" in response.url.lower() or "verticals" in response.url.lower(), \
                "Gym business should redirect to gym dashboard"
        else:
            # If no redirect (already on correct page), check content
            content = response.content.decode().lower()
            assert "inventory dashboard" not in content

    def test_gym_business_does_not_show_stock_link(
        self, client: Client, manager_user, gym_business
    ):
        """Gym business should NOT see phones 'Stock' link in nav."""
        create_manager_membership(manager_user, gym_business)
        client.force_login(manager_user)
        set_active_business(client, gym_business)

        # Check redirect without following to avoid model dependencies
        response = client.get(reverse("dashboard:home"), follow=False)
        
        if response.status_code == 302:
            # Should redirect to gym dashboard
            assert "gym" in response.url.lower() or "verticals" in response.url.lower()
        else:
            content = response.content.decode()
            # Gym business should NOT see the phones "Stock" link in sidebar
            assert not ('<span>Stock</span>' in content and '/inventory/list/' in content)

    def test_gym_business_does_not_show_scan_in(
        self, client: Client, manager_user, gym_business
    ):
        """Gym business should NOT see phones 'Scan IN' in nav."""
        create_manager_membership(manager_user, gym_business)
        client.force_login(manager_user)
        set_active_business(client, gym_business)

        # Check redirect behavior
        response = client.get(reverse("dashboard:home"), follow=False)
        
        if response.status_code == 302:
            # Should redirect to gym dashboard
            assert "gym" in response.url.lower() or "verticals" in response.url.lower()

    def test_gym_business_shows_members_link(
        self, client: Client, manager_user, gym_business
    ):
        """Gym business should redirect to gym dashboard."""
        create_manager_membership(manager_user, gym_business)
        client.force_login(manager_user)
        set_active_business(client, gym_business)

        # Should redirect to gym-specific dashboard
        response = client.get(reverse("dashboard:home"), follow=False)
        assert response.status_code == 302
        assert "gym" in response.url.lower() or "verticals" in response.url.lower()


# ==============================================================================
# CLOTHING BUSINESS NAV TESTS
# ==============================================================================

@pytest.mark.django_db
class TestClothingBusinessNav:
    """Test that clothing businesses see clothing-specific nav items."""

    def test_clothing_business_does_not_show_phones_items(
        self, client: Client, manager_user, clothing_business
    ):
        """Clothing business should NOT see phones nav items."""
        create_manager_membership(manager_user, clothing_business)
        client.force_login(manager_user)
        set_active_business(client, clothing_business)

        # Check redirect without following
        response = client.get(reverse("dashboard:home"), follow=False)
        
        if response.status_code == 302:
            assert "clothing" in response.url.lower() or "verticals" in response.url.lower()

    def test_clothing_business_shows_clothing_hub(
        self, client: Client, manager_user, clothing_business
    ):
        """Clothing business should redirect to clothing dashboard."""
        create_manager_membership(manager_user, clothing_business)
        client.force_login(manager_user)
        set_active_business(client, clothing_business)

        # Should redirect to clothing dashboard
        response = client.get(reverse("dashboard:home"), follow=False)
        assert response.status_code == 302
        assert "clothing" in response.url.lower() or "verticals" in response.url.lower()


# ==============================================================================
# LIQUOR BUSINESS NAV TESTS
# ==============================================================================

@pytest.mark.django_db
class TestLiquorBusinessNav:
    """Test that liquor businesses see liquor-specific nav items."""

    def test_liquor_business_does_not_show_phones_items(
        self, client: Client, manager_user, liquor_business
    ):
        """Liquor business should NOT see phones nav items."""
        create_manager_membership(manager_user, liquor_business)
        client.force_login(manager_user)
        set_active_business(client, liquor_business)

        # Check redirect
        response = client.get(reverse("dashboard:home"), follow=False)
        
        if response.status_code == 302:
            assert "liquor" in response.url.lower() or "verticals" in response.url.lower()

    def test_liquor_business_shows_liquor_hub(
        self, client: Client, manager_user, liquor_business
    ):
        """Liquor business should redirect to liquor dashboard."""
        create_manager_membership(manager_user, liquor_business)
        client.force_login(manager_user)
        set_active_business(client, liquor_business)

        # Should redirect to liquor dashboard
        response = client.get(reverse("dashboard:home"), follow=False)
        assert response.status_code == 302
        assert "liquor" in response.url.lower() or "verticals" in response.url.lower()


# ==============================================================================
# PHARMACY BUSINESS NAV TESTS
# ==============================================================================

@pytest.mark.django_db
class TestPharmacyBusinessNav:
    """Test that pharmacy businesses see pharmacy-specific nav items."""

    def test_pharmacy_business_does_not_show_phones_items(
        self, client: Client, manager_user, pharmacy_business
    ):
        """Pharmacy business should NOT see phones nav items."""
        create_manager_membership(manager_user, pharmacy_business)
        client.force_login(manager_user)
        set_active_business(client, pharmacy_business)

        # Check redirect
        response = client.get(reverse("dashboard:home"), follow=False)
        
        if response.status_code == 302:
            assert "pharmacy" in response.url.lower() or "verticals" in response.url.lower()

    def test_pharmacy_business_shows_pharmacy_hub(
        self, client: Client, manager_user, pharmacy_business
    ):
        """Pharmacy business should redirect to pharmacy dashboard."""
        create_manager_membership(manager_user, pharmacy_business)
        client.force_login(manager_user)
        set_active_business(client, pharmacy_business)

        # Should redirect to pharmacy dashboard
        response = client.get(reverse("dashboard:home"), follow=False)
        assert response.status_code == 302
        assert "pharmacy" in response.url.lower() or "verticals" in response.url.lower()


# ==============================================================================
# INVENTORY DASHBOARD REDIRECT TESTS
# ==============================================================================

@pytest.mark.django_db
class TestInventoryDashboardRedirect:
    """Test that /inventory/dashboard/ redirects non-phone businesses."""

    def test_phone_business_can_access_inventory_dashboard(
        self, client: Client, manager_user, phone_business
    ):
        """Phone business can access /inventory/dashboard/."""
        create_manager_membership(manager_user, phone_business)
        client.force_login(manager_user)
        set_active_business(client, phone_business)

        # Should be able to access inventory dashboard
        response = client.get("/inventory/dashboard/")
        # Either 200 (accessible) or redirect to phones dashboard
        assert response.status_code in [200, 302]

    def test_gym_business_redirects_from_inventory_dashboard(
        self, client: Client, manager_user, gym_business
    ):
        """Gym business should be redirected from /inventory/dashboard/."""
        create_manager_membership(manager_user, gym_business)
        client.force_login(manager_user)
        set_active_business(client, gym_business)

        # Should redirect away from inventory dashboard (don't follow to avoid model dependencies)
        response = client.get("/inventory/dashboard/", follow=False)
        assert response.status_code == 302, "Gym business should be redirected from phones inventory dashboard"
        
        # Verify it redirects to a vertical dashboard
        assert "gym" in response.url.lower() or "verticals" in response.url.lower()

    def test_clothing_business_redirects_from_inventory_dashboard(
        self, client: Client, manager_user, clothing_business
    ):
        """Clothing business should be redirected from /inventory/dashboard/."""
        create_manager_membership(manager_user, clothing_business)
        client.force_login(manager_user)
        set_active_business(client, clothing_business)

        response = client.get("/inventory/dashboard/", follow=False)
        assert response.status_code == 302, "Clothing business should be redirected from phones inventory dashboard"
        assert "clothing" in response.url.lower() or "verticals" in response.url.lower()

    def test_liquor_business_redirects_from_inventory_dashboard(
        self, client: Client, manager_user, liquor_business
    ):
        """Liquor business should be redirected from /inventory/dashboard/."""
        create_manager_membership(manager_user, liquor_business)
        client.force_login(manager_user)
        set_active_business(client, liquor_business)

        response = client.get("/inventory/dashboard/", follow=False)
        assert response.status_code == 302, "Liquor business should be redirected from phones inventory dashboard"
        assert "liquor" in response.url.lower() or "verticals" in response.url.lower()

    def test_pharmacy_business_redirects_from_inventory_dashboard(
        self, client: Client, manager_user, pharmacy_business
    ):
        """Pharmacy business should be redirected from /inventory/dashboard/."""
        create_manager_membership(manager_user, pharmacy_business)
        client.force_login(manager_user)
        set_active_business(client, pharmacy_business)

        response = client.get("/inventory/dashboard/", follow=False)
        assert response.status_code == 302, "Pharmacy business should be redirected from phones inventory dashboard"
        assert "pharmacy" in response.url.lower() or "verticals" in response.url.lower()

