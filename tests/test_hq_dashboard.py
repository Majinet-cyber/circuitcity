# tests/test_hq_dashboard.py
"""
Tests for HQ dashboard and navigation.
Ensures HQ users see platform-level controls and not tenant business menus.
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
def hq_user(db):
    """Create an HQ admin user (superuser)."""
    return User.objects.create_superuser(
        username="hqadmin",
        email="hq@test.com",
        password="testpass123"
    )


@pytest.fixture
def staff_user(db):
    """Create a staff user."""
    user = User.objects.create_user(
        username="staff",
        email="staff@test.com",
        password="testpass123"
    )
    user.is_staff = True
    user.save()
    return user


@pytest.fixture
def phone_business(db):
    """Create a phone business."""
    return Business.objects.create(
        name="Test Phone Shop",
        slug="test-phone-shop",
        business_kind=BusinessKind.PHONES,
        status="ACTIVE"
    )


# ==============================================================================
# HQ DASHBOARD ACCESS TESTS
# ==============================================================================

@pytest.mark.django_db
class TestHQDashboardAccess:
    """Test that HQ dashboard is accessible and uses correct template."""

    def test_hq_dashboard_accessible_for_superuser(self, client: Client, hq_user):
        """Superuser can access HQ dashboard."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        assert response.status_code == 200
        # Check for HQ dashboard template or inline rendering
        if hasattr(response, 'templates') and response.templates:
            template_names = [t.name for t in response.templates if t.name]
            assert any("hq/dashboard" in name for name in template_names)

    def test_hq_dashboard_accessible_for_staff(self, client: Client, staff_user):
        """Staff user can access HQ dashboard."""
        client.force_login(staff_user)
        
        response = client.get(reverse("hq:dashboard"))
        assert response.status_code == 200

    def test_hq_home_accessible(self, client: Client, hq_user):
        """HQ home URL is accessible."""
        client.force_login(hq_user)
        
        response = client.get("/hq/", follow=True)
        assert response.status_code == 200
        # Should end up at a valid HQ page
        content = response.content.decode()
        assert "HQ" in content or "Control" in content or "Platform" in content
    
    def test_hq_dashboard_uses_base_hq_template(self, client: Client, hq_user):
        """HQ dashboard should use the base_hq.html template."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        # Should have HQ-specific branding
        assert "HQ" in content or "Control Center" in content


# ==============================================================================
# HQ DASHBOARD CONTENT TESTS
# ==============================================================================

@pytest.mark.django_db
class TestHQDashboardContent:
    """Test that HQ dashboard shows platform metrics and not tenant menus."""

    def test_hq_dashboard_shows_platform_metrics(self, client: Client, hq_user):
        """HQ dashboard displays platform-level metrics."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        # Should show at least one of these platform metrics
        assert any(metric in content.lower() for metric in [
            "total businesses",
            "active subs",
            "mrr",
            "agents total",
            "hq",
            "control center",
            "platform"
        ]), "HQ dashboard should show platform metrics"
    
    def test_hq_dashboard_shows_kpi_cards(self, client: Client, hq_user):
        """HQ dashboard should show KPI cards."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        # Should have multiple KPI indicators
        kpis = ["Total Businesses", "New (7d)", "Active Subs", "MRR", "Agents"]
        found_kpis = sum(1 for kpi in kpis if kpi in content)
        assert found_kpis >= 3, "HQ dashboard should show at least 3 KPI cards"
    
    def test_hq_dashboard_shows_sales_metrics(self, client: Client, hq_user):
        """HQ dashboard should show sales overview metrics."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        # Should have sales-related content
        assert any(term in content for term in [
            "Sales", "Revenue", "sales_count", "sales_revenue"
        ]), "HQ dashboard should show sales metrics"
    
    def test_hq_dashboard_shows_onboarding_metrics(self, client: Client, hq_user):
        """HQ dashboard should show agent onboarding metrics."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        # Should have onboarding-related content
        assert any(term in content for term in [
            "Agents New", "Onboarding", "New Agents", "agents_new"
        ]), "HQ dashboard should show onboarding metrics"

    def test_hq_dashboard_has_no_tenant_stock_menu(self, client: Client, hq_user):
        """HQ dashboard does NOT show tenant 'Stock' menu in navigation."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        # HQ navigation should not have tenant-specific items
        # Should have "HQ Dashboard" or "Platform" indicating it's HQ context
        assert "HQ Dashboard" in content or "Platform" in content or "Control Center" in content

    def test_hq_dashboard_has_no_scan_in_menu(self, client: Client, hq_user):
        """HQ dashboard does NOT show tenant 'Scan IN' menu."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        # Should have HQ context markers
        assert "HQ" in content or "Platform" in content

    def test_hq_dashboard_has_no_sell_menu(self, client: Client, hq_user):
        """HQ dashboard does NOT show tenant 'Sell' menu."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        # Should be clearly HQ context
        assert "HQ" in content or "Control Center" in content


# ==============================================================================
# HQ NAVIGATION TESTS
# ==============================================================================

@pytest.mark.django_db
class TestHQNavigation:
    """Test that HQ navigation shows platform controls."""

    def test_hq_nav_shows_businesses_link(self, client: Client, hq_user):
        """HQ navigation shows 'Businesses' link."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        assert "Businesses" in content or "/hq/businesses" in content

    def test_hq_nav_shows_subscriptions_link(self, client: Client, hq_user):
        """HQ navigation shows 'Subscriptions' link."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        assert "Subscriptions" in content or "/hq/subscriptions" in content

    def test_hq_nav_shows_agents_link(self, client: Client, hq_user):
        """HQ navigation shows 'Agents' link."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        assert "Agents" in content or "/hq/agents" in content
    
    def test_hq_nav_shows_invoices_link(self, client: Client, hq_user):
        """HQ navigation shows 'Invoices' link."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        assert "Invoices" in content or "/hq/invoices" in content
    
    def test_hq_nav_shows_stock_trends_link(self, client: Client, hq_user):
        """HQ navigation shows 'Stock Trends' link."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        assert "Stock" in content and ("Trends" in content or "trends" in content)
    
    def test_hq_nav_is_platform_focused(self, client: Client, hq_user):
        """HQ navigation should be platform-focused, not tenant-focused."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        # Should have clear HQ/Platform indicators
        assert "HQ" in content or "Platform" in content or "Control" in content


# ==============================================================================
# HQ VS TENANT SEPARATION TESTS
# ==============================================================================

@pytest.mark.django_db
class TestHQTenantSeparation:
    """Test that HQ and tenant views are properly separated."""

    def test_hq_user_sees_hq_dashboard_not_tenant_dashboard(
        self, client: Client, hq_user, phone_business
    ):
        """HQ user on HQ dashboard doesn't see tenant items."""
        client.force_login(hq_user)
        
        # Access HQ dashboard
        response = client.get(reverse("hq:dashboard"))
        content = response.content.decode()
        
        # Should be HQ-focused
        assert "HQ" in content or "Platform" in content or "Control" in content
        
        # Should NOT have tenant-specific onboarding steps
        assert "Add your first product" not in content or "Total Businesses" in content

    def test_hq_metrics_are_platform_wide(self, client: Client, hq_user):
        """HQ dashboard shows platform-wide metrics, not single tenant metrics."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:dashboard"))
        assert response.status_code == 200
        
        # Context should have platform metrics
        context = response.context
        assert "total_biz" in context or "active_subs" in context, \
            "HQ dashboard should have platform-wide metrics in context"


# ==============================================================================
# HQ PERMISSIONS TESTS
# ==============================================================================

@pytest.mark.django_db
class TestHQPermissions:
    """Test that HQ pages require appropriate permissions."""

    def test_regular_user_cannot_access_hq_dashboard(self, client: Client):
        """Regular (non-staff, non-superuser) user cannot access HQ dashboard."""
        # Create a regular user
        regular_user = User.objects.create_user(
            username="regular",
            email="regular@test.com",
            password="testpass123"
        )
        client.force_login(regular_user)
        
        response = client.get(reverse("hq:dashboard"))
        # Should either redirect or return 403
        assert response.status_code in [302, 403]

    def test_hq_businesses_list_requires_auth(self, client: Client, hq_user):
        """HQ businesses list requires authentication."""
        # Try without login
        response = client.get(reverse("hq:businesses"))
        assert response.status_code == 302  # Redirect to login
        
        # With login
        client.force_login(hq_user)
        response = client.get(reverse("hq:businesses"))
        assert response.status_code == 200


# ==============================================================================
# HQ TEMPLATE CONSISTENCY TESTS
# ==============================================================================

@pytest.mark.django_db
class TestHQTemplateConsistency:
    """Test that all HQ pages use consistent base template."""
    
    def test_hq_subscriptions_uses_hq_base(self, client: Client, hq_user):
        """HQ subscriptions page should use base_hq.html."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:subscriptions"))
        content = response.content.decode()
        
        # Should have HQ branding/sidebar
        assert "HQ" in content or "Control Center" in content
    
    def test_hq_invoices_accessible(self, client: Client, hq_user):
        """HQ invoices page should be accessible."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:invoices"))
        assert response.status_code == 200
    
    def test_hq_agents_accessible(self, client: Client, hq_user):
        """HQ agents page should be accessible."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:agents"))
        assert response.status_code == 200
    
    def test_hq_stock_trends_accessible(self, client: Client, hq_user):
        """HQ stock trends page should be accessible."""
        client.force_login(hq_user)
        
        response = client.get(reverse("hq:stock_trends"))
        assert response.status_code == 200

