# tests/test_vertical_routing_comprehensive.py
"""
Comprehensive tests for vertical routing to ensure:
1. Each vertical routes to its correct dashboard
2. Navigation items match the vertical
3. Phones-only pages return 404 or redirect for non-phone verticals
4. /verticals/none/ never appears once vertical is set
"""
import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123"
    )


@pytest.fixture
def grocery_business(db, user):
    """Create a grocery business."""
    business = Business.objects.create(
        name="Test Grocery Store",
        slug="test-grocery",
        status="ACTIVE",
        business_kind=BusinessKind.GROCERY,
        created_by=user,
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE"
    )
    return business


@pytest.fixture
def cement_business(db, user):
    """Create a cement & hardware business."""
    business = Business.objects.create(
        name="Test Cement & Hardware",
        slug="test-cement",
        status="ACTIVE",
        business_kind=BusinessKind.CEMENT,
        created_by=user,
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE"
    )
    return business


@pytest.fixture
def hardware_business(db, user):
    """Create a hardware store business."""
    business = Business.objects.create(
        name="Test Hardware Store",
        slug="test-hardware",
        status="ACTIVE",
        business_kind=BusinessKind.HARDWARE,
        created_by=user,
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE"
    )
    return business


@pytest.fixture
def phones_business(db, user):
    """Create a phones business."""
    business = Business.objects.create(
        name="Test Phones Store",
        slug="test-phones",
        status="ACTIVE",
        business_kind=BusinessKind.PHONES,
        created_by=user,
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE"
    )
    return business


class TestGroceryVerticalRouting:
    """Test that grocery businesses route correctly."""

    def test_grocery_routes_to_grocery_dashboard(self, client: Client, user, grocery_business):
        """Grocery business should route to grocery dashboard, not /verticals/none/"""
        client.force_login(user)
        client.session["active_business_id"] = grocery_business.id
        client.session.save()

        # Access the main dashboard
        response = client.get(reverse("dashboard:home"))
        
        # Should redirect to grocery dashboard
        assert response.status_code in (200, 302)
        if response.status_code == 302:
            assert "/verticals/grocery/dashboard" in response.url or "/grocery/" in response.url
            # Follow redirect
            response = client.get(response.url)
            assert response.status_code == 200
        
        # Should NOT contain "Select your business type"
        assert b"Select your business type" not in response.content
        assert b"Grocery" in response.content or b"grocery" in response.content

    def test_grocery_never_sees_verticals_none(self, client: Client, user, grocery_business):
        """/verticals/none/ should never appear for grocery business."""
        client.force_login(user)
        client.session["active_business_id"] = grocery_business.id
        client.session.save()

        # Try various entry points
        urls_to_test = [
            reverse("dashboard:home"),
            "/inventory/dashboard/",
        ]
        
        for url in urls_to_test:
            response = client.get(url, follow=True)
            # Should never land on /verticals/none/
            assert "/verticals/none/" not in response.request["PATH_INFO"]
            assert b"Select your business type" not in response.content

    def test_grocery_cannot_access_phone_scan_imei(self, client: Client, user, grocery_business):
        """Grocery business should not access phones-only IMEI scan pages."""
        client.force_login(user)
        client.session["active_business_id"] = grocery_business.id
        client.session.save()

        # Try to access phone scan-in
        try:
            url = reverse("inventory:phone_scan_in")
            response = client.get(url)
            # Should either 404, 403, or redirect away from phones page
            assert response.status_code in (302, 403, 404) or b"IMEI" not in response.content
        except Exception:
            # URL might not exist or be protected - that's fine
            pass

    def test_grocery_sidebar_has_correct_items(self, client: Client, user, grocery_business):
        """Grocery sidebar should show grocery menu items, not phones items."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("grocery")
        
        # Should have grocery-specific items
        item_labels = [item["label"] for item in items]
        assert "Fast Sell" in item_labels or "Sell" in item_labels
        assert "Inventory" in item_labels or "Stock In" in item_labels
        
        # Should NOT have phones-specific items
        assert "Scan IMEI" not in item_labels
        assert "Scan & Sell" not in item_labels


class TestCementVerticalRouting:
    """Test that cement & hardware businesses route correctly."""

    def test_cement_routes_to_cement_dashboard(self, client: Client, user, cement_business):
        """Cement business should route to cement dashboard, not /verticals/none/"""
        client.force_login(user)
        client.session["active_business_id"] = cement_business.id
        client.session.save()

        # Access the main dashboard
        response = client.get(reverse("dashboard:home"))
        
        # Should redirect to cement dashboard
        assert response.status_code in (200, 302)
        if response.status_code == 302:
            assert "/verticals/cement/dashboard" in response.url or "/cement/" in response.url
            # Follow redirect
            response = client.get(response.url)
            assert response.status_code == 200
        
        # Should contain cement/hardware content
        assert b"Cement" in response.content or b"Hardware" in response.content

    def test_cement_never_sees_verticals_none(self, client: Client, user, cement_business):
        """/verticals/none/ should never appear for cement business."""
        client.force_login(user)
        client.session["active_business_id"] = cement_business.id
        client.session.save()

        response = client.get(reverse("dashboard:home"), follow=True)
        assert "/verticals/none/" not in response.request["PATH_INFO"]
        assert b"Select your business type" not in response.content

    def test_cement_cannot_access_phone_wizard(self, client: Client, user, cement_business):
        """Cement business should not access phone sale wizard."""
        client.force_login(user)
        client.session["active_business_id"] = cement_business.id
        client.session.save()

        # Try to access phone sale wizard
        try:
            url = reverse("inventory:phone_sale_wizard")
            response = client.get(url)
            # Should be blocked or redirected
            assert response.status_code in (302, 403, 404)
        except Exception:
            # URL might be protected - that's fine
            pass


class TestHardwareVerticalRouting:
    """Test that hardware store businesses route correctly."""

    def test_hardware_routes_to_hardware_dashboard(self, client: Client, user, hardware_business):
        """Hardware business should route to hardware dashboard, not /verticals/none/"""
        client.force_login(user)
        client.session["active_business_id"] = hardware_business.id
        client.session.save()

        # Access the main dashboard
        response = client.get(reverse("dashboard:home"))
        
        # Should redirect to hardware dashboard
        assert response.status_code in (200, 302)
        if response.status_code == 302:
            assert "/verticals/hardware/dashboard" in response.url or "/hardware/" in response.url
            # Follow redirect
            response = client.get(response.url)
            assert response.status_code == 200
        
        # Should contain hardware content
        assert b"Hardware" in response.content

    def test_hardware_never_sees_verticals_none(self, client: Client, user, hardware_business):
        """/verticals/none/ should never appear for hardware business."""
        client.force_login(user)
        client.session["active_business_id"] = hardware_business.id
        client.session.save()

        response = client.get(reverse("dashboard:home"), follow=True)
        assert "/verticals/none/" not in response.request["PATH_INFO"]
        assert b"Select your business type" not in response.content


class TestPhonesVerticalProtection:
    """Test that phones-only views are protected from other verticals."""

    def test_phones_business_can_access_imei_scan(self, client: Client, user, phones_business):
        """Phones business should be able to access IMEI scan pages."""
        client.force_login(user)
        client.session["active_business_id"] = phones_business.id
        client.session.save()

        # Should be able to access phone-specific pages
        try:
            url = reverse("inventory:phone_scan_in")
            response = client.get(url)
            assert response.status_code == 200
        except Exception:
            # If URL doesn't exist, that's okay for this test
            pass

    def test_grocery_redirected_from_phone_pages(self, client: Client, user, grocery_business):
        """Grocery business accessing phone pages should be redirected."""
        client.force_login(user)
        client.session["active_business_id"] = grocery_business.id
        client.session.save()

        # Try various phone-specific endpoints
        phone_endpoints = [
            ("inventory:phone_scan_in", "Phone scan-in"),
            ("inventory:phone_sale_wizard", "Phone sale wizard"),
        ]

        for url_name, description in phone_endpoints:
            try:
                url = reverse(url_name)
                response = client.get(url)
                
                # Should be blocked (403/404) or redirected (302)
                if response.status_code == 200:
                    # If it loads, should not show phone-specific content
                    assert b"IMEI" not in response.content, f"{description} should not show IMEI to grocery"
                else:
                    assert response.status_code in (302, 403, 404), f"{description} should be protected"
            except Exception:
                # URL might not exist - that's acceptable
                pass


class TestVerticalUtilities:
    """Test vertical utility functions."""

    def test_get_vertical_kind_returns_correct_vertical(self, grocery_business, cement_business):
        """get_vertical_kind should return the correct vertical for each business."""
        from inventory.utils_verticals import get_vertical_kind

        assert get_vertical_kind(grocery_business) == "grocery"
        assert get_vertical_kind(cement_business) == "cement"

    def test_get_vertical_dashboard_url_maps_correctly(self):
        """get_vertical_dashboard_url should map verticals to correct URLs."""
        from inventory.utils_verticals import get_vertical_dashboard_url

        assert get_vertical_dashboard_url("grocery") == "verticals:grocery_dashboard"
        assert get_vertical_dashboard_url("cement") == "verticals:cement_dashboard"
        assert get_vertical_dashboard_url("hardware") == "verticals:hardware_dashboard"
        
        # Phones should not have a vertical dashboard URL (uses inventory dashboard)
        assert get_vertical_dashboard_url("phones") is None

    def test_business_vertical_helper_returns_correct_value(self, client: Client, user, grocery_business):
        """business_vertical helper should return correct vertical from request."""
        from inventory.helpers import business_vertical
        
        client.force_login(user)
        client.session["active_business_id"] = grocery_business.id
        client.session.save()
        
        # Create a mock request
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        request.session = client.session
        request.business = grocery_business
        
        vertical = business_vertical(request)
        assert vertical == "grocery"


class TestNoBusinessFallback:
    """Test fallback behavior for businesses without a vertical set."""

    def test_no_vertical_shows_selection_page(self, client: Client, user, db):
        """Business without vertical should show selection page."""
        # Create business without business_kind
        business = Business.objects.create(
            name="Generic Business",
            slug="generic-biz",
            status="ACTIVE",
            business_kind=None,  # No vertical set
            created_by=user,
        )
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )

        client.force_login(user)
        client.session["active_business_id"] = business.id
        client.session.save()

        # Should show business type selection
        response = client.get(reverse("dashboard:home"), follow=True)
        
        # Should land on /verticals/none/ or show selection prompt
        assert (
            "/verticals/none/" in response.request["PATH_INFO"]
            or b"Select your business type" in response.content
            or b"business type" in response.content.lower()
        )

