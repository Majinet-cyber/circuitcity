# tests/test_cement_vertical_fix.py
"""
Tests for cement vertical routing fix.

Ensures:
1. Cement businesses never land on /verticals/none/
2. Cement businesses have business_kind='cement' persisted
3. After login, cement businesses redirect to cement dashboard
4. /verticals/none/ redirects to settings (not a valid landing page)
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestCementVerticalFix:
    """Test cement vertical routing and business_kind persistence"""

    def test_cement_business_has_business_kind_set(self):
        """
        CRITICAL: Cement businesses MUST have business_kind='cement' (NOT NULL).
        """
        user = User.objects.create_user(username="cement_owner", password="test123")

        # Create cement business
        business = Business.objects.create(
            name="Test Cement Store",
            slug="test-cement",
            business_kind="cement",
            status="ACTIVE",
            created_by=user,
        )

        # Verify business_kind is set
        assert business.business_kind == "cement", "Cement business must have business_kind='cement'"
        assert business.business_kind is not None, "business_kind must NOT be NULL"

        # Refresh from DB to ensure it persisted
        business.refresh_from_db()
        assert business.business_kind == "cement", "business_kind must persist to database"

    def test_cement_dashboard_route_exists(self):
        """Verify cement dashboard route is registered and accessible"""
        user = User.objects.create_user(username="cement_user", password="test123")
        business = Business.objects.create(
            name="Cement Co",
            slug="cement-co",
            business_kind="cement",
            status="ACTIVE",
            created_by=user,
        )
        Membership.objects.create(user=user, business=business, role="MANAGER", status="ACTIVE")

        client = Client()
        client.force_login(user)

        # Set active business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()

        # Try to access cement dashboard
        url = reverse("verticals:cement_dashboard")
        response = client.get(url)

        # Should return 200 (not 404)
        assert response.status_code == 200, f"Cement dashboard should be accessible, got {response.status_code}"

    def test_verticals_none_redirects_to_settings(self):
        """
        CRITICAL: /verticals/none/ must NEVER be a valid landing page.
        It should redirect to settings with a helpful message.
        """
        user = User.objects.create_user(username="test_user", password="test123")
        business = Business.objects.create(
            name="Test Business",
            slug="test-biz",
            business_kind=None,  # No vertical set
            status="ACTIVE",
            created_by=user,
        )
        Membership.objects.create(user=user, business=business, role="MANAGER", status="ACTIVE")

        client = Client()
        client.force_login(user)

        # Set active business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()

        # Access /verticals/none/
        url = reverse("verticals:no_business")
        response = client.get(url)

        # Should redirect (302) to settings, NOT render a page (200)
        assert response.status_code == 302, f"/verticals/none/ should redirect, got {response.status_code}"

        # Follow redirect
        response = client.get(url, follow=True)

        # Should end up on settings page
        assert response.status_code == 200
        assert "settings" in response.request["PATH_INFO"].lower(), "Should redirect to settings page"

    def test_login_redirect_for_cement_business(self):
        """
        After login, cement business users should land on cement dashboard
        (NOT /verticals/none/).
        """
        user = User.objects.create_user(username="cement_manager", password="test123")
        business = Business.objects.create(
            name="Cement Store",
            slug="cement-store",
            business_kind="cement",
            status="ACTIVE",
            created_by=user,
        )
        Membership.objects.create(user=user, business=business, role="MANAGER", status="ACTIVE")

        client = Client()

        # Login
        response = client.post(
            reverse("accounts:login"),
            {"identifier": "cement_manager", "password": "test123"},
            follow=True,
        )

        # Should redirect to cement dashboard (not /verticals/none/)
        assert response.status_code == 200
        final_url = response.request["PATH_INFO"]

        # Should NOT contain "none"
        assert "none" not in final_url.lower(), f"Should NOT redirect to /verticals/none/, got {final_url}"

        # Should contain "cement" or "dashboard"
        assert (
            "cement" in final_url.lower() or "dashboard" in final_url.lower()
        ), f"Should redirect to cement dashboard, got {final_url}"

    def test_data_migration_fixes_null_business_kind(self):
        """
        Test that businesses with NULL business_kind can be fixed manually.
        (Migration would be run separately via manage.py migrate)
        """
        from django.db import models

        # Create a cement business with NULL business_kind (simulating the bug)
        business = Business.objects.create(
            name="Cement Hardware",
            slug="cement-hardware",
            business_kind=None,  # BUG: NULL vertical
            has_cement_section=True,  # But has cement flag
            status="ACTIVE",
        )

        # Verify it's NULL
        assert business.business_kind is None

        # Manually fix (simulating what the migration does)
        cement_flagged = Business.objects.filter(has_cement_section=True).filter(
            models.Q(business_kind__isnull=True) | models.Q(business_kind="")
        )
        cement_flagged.update(business_kind="cement")

        # Refresh from DB
        business.refresh_from_db()

        # Should now have business_kind='cement'
        assert business.business_kind == "cement", "Should fix NULL business_kind to 'cement'"

    def test_cement_business_name_detection(self):
        """
        Businesses with 'cement' or 'hardware' in name should be detected as cement vertical.
        """
        from django.db import models

        # Create business with "cement" in name but no business_kind
        business = Business.objects.create(
            name="ABC Cement Suppliers",
            slug="abc-cement",
            business_kind=None,
            status="ACTIVE",
        )

        # Manually fix (simulating what the migration does)
        cement_named = Business.objects.filter(
            models.Q(name__icontains="cement") | models.Q(name__icontains="hardware")
        ).filter(models.Q(business_kind__isnull=True) | models.Q(business_kind=""))
        cement_named.update(business_kind="cement", has_cement_section=True)

        # Refresh
        business.refresh_from_db()

        # Should be detected as cement
        assert business.business_kind == "cement"
        assert business.has_cement_section is True


@pytest.mark.django_db
class TestCementVerticalURLs:
    """Test cement vertical URL routing"""

    def test_cement_urls_are_registered(self):
        """Verify all cement URLs are properly registered"""
        cement_urls = [
            "verticals:cement_dashboard",
            "verticals:cement_stock_list",
            "verticals:cement_stock_in",
            "verticals:cement_sell",
            "verticals:cement_costs",
            "verticals:cement_analytics",
        ]

        for url_name in cement_urls:
            try:
                url = reverse(url_name)
                assert url is not None, f"{url_name} should resolve to a URL"
                assert "/cement/" in url, f"{url_name} should contain /cement/ in path"
            except Exception as e:
                pytest.fail(f"URL {url_name} is not registered: {e}")

    def test_cement_dashboard_requires_cement_business_kind(self):
        """Cement dashboard should only be accessible to cement businesses"""
        user = User.objects.create_user(username="phone_user", password="test123")

        # Create a PHONES business (not cement)
        business = Business.objects.create(
            name="Phone Store",
            slug="phone-store",
            business_kind="phones",  # NOT cement
            status="ACTIVE",
            created_by=user,
        )
        Membership.objects.create(user=user, business=business, role="MANAGER", status="ACTIVE")

        client = Client()
        client.force_login(user)

        # Set active business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()

        # Try to access cement dashboard (should be blocked)
        url = reverse("verticals:cement_dashboard")
        response = client.get(url)

        # Should redirect or return 403 (not 200)
        assert response.status_code in [
            302,
            403,
            404,
        ], f"Non-cement business should NOT access cement dashboard, got {response.status_code}"
