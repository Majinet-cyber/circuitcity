# inventory/tests/test_pharmacy_ux_upgrade.py
"""
Regression tests for Pharmacy & Cosmetics UX Upgrade (January 2026).

Tests cover:
- Enhanced dashboard with premium KPIs, sales trend, and attention panels
- Gamified stock-in flow (Pharmacy vs Cosmetics choice cards)
- Curated product catalog with quick stock-in
- Backend integration with existing stock-in service

CRITICAL: All tests must pass to ensure ZERO regressions across verticals.
"""
from __future__ import annotations

import json
from decimal import Decimal
from datetime import date, timedelta

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch, PharmacySale, PharmacyCategory

User = get_user_model()


# Helper function to create test fixtures
def create_test_pharmacy_fixtures():
    """Create reusable test fixtures for pharmacy tests."""
    from tenants.models import Location
    
    business = Business.objects.create(
        name="Test Pharmacy",
        slug="test-pharmacy",
        business_kind="pharmacy",
        status="ACTIVE"
    )
    
    location = Location.objects.create(
        business=business,
        name="Main Branch",
        is_default=True
    )
    
    user = User.objects.create_user(
        username="manager@test.com",
        email="manager@test.com",
        password="TestPass123!@#"
    )
    
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER"
    )
    
    return {
        "business": business,
        "location": location,
        "user": user,
    }


@pytest.mark.django_db
class TestPharmacyDashboardEnhancements(TestCase):
    """Test enhanced dashboard KPIs and features."""
    
    def setUp(self):
        """Create test business, user, and sample data."""
        fixtures = create_test_pharmacy_fixtures()
        self.business = fixtures["business"]
        self.location = fixtures["location"]
        self.user = fixtures["user"]
        
        self.client = Client()
        self.client.login(username="manager@test.com", password="TestPass123!@#")
        
        # Set active business and location in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()
    
    def test_pharmacy_dashboard_renders_200(self):
        """Dashboard should load without errors."""
        url = reverse("pharmacy:dashboard")
        response = self.client.get(url)
        
        assert response.status_code == 200, f"Dashboard should return 200, got {response.status_code}"
        
        content = response.content.decode()
        assert "Pharmacy &amp; Cosmetics" in content or "Pharmacy & Cosmetics" in content
        assert "Server Error" not in content
    
    def test_dashboard_shows_premium_kpis(self):
        """Dashboard should display all premium KPI cards."""
        url = reverse("pharmacy:dashboard")
        response = self.client.get(url)
        content = response.content.decode()
        
        # Check for KPI sections
        assert "Business Overview" in content or "Overview" in content
        assert "Total Products" in content
        assert "Active Batches" in content
        assert "Today" in content or "Sales" in content
        assert "Stock Value" in content
        assert "Potential Revenue" in content
    
    def test_dashboard_shows_operational_insights(self):
        """Dashboard should display operational insight KPIs."""
        url = reverse("pharmacy:dashboard")
        response = self.client.get(url)
        content = response.content.decode()
        
        # Check for operational insights
        assert "Expiring Soon" in content or "expiring" in content.lower()
        assert "Low Stock" in content or "low stock" in content.lower()
    
    def test_dashboard_includes_sales_trend_chart(self):
        """Dashboard should include Chart.js sales trend."""
        url = reverse("pharmacy:dashboard")
        response = self.client.get(url)
        content = response.content.decode()
        
        # Check for chart elements
        assert "salesTrendChart" in content
        assert "Chart.js" in content or "chart.js" in content
        assert "Sales Trend" in content
    
    def test_sales_trend_api_endpoint_works(self):
        """Sales trend JSON API should return valid data."""
        url = reverse("verticals:pharmacy_sales_trend_json")
        response = self.client.get(url + "?range=7d")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "labels" in data
        assert "revenue" in data
        assert "count" in data
        assert isinstance(data["labels"], list)
        assert isinstance(data["revenue"], list)
        assert isinstance(data["count"], list)


@pytest.mark.django_db
class TestStockInChoiceFlow(TestCase):
    """Test new stock-in landing page with Pharmacy/Cosmetics cards."""
    
    def setUp(self):
        """Create test business and user."""
        fixtures = create_test_pharmacy_fixtures()
        self.business = fixtures["business"]
        self.location = fixtures["location"]
        self.user = fixtures["user"]
        
        self.client = Client()
        self.client.login(username="manager@test.com", password="TestPass123!@#")
        
        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()
    
    def test_stock_in_landing_renders_200(self):
        """Stock-in landing page should load without errors."""
        url = reverse("pharmacy:stock_in_choice")
        response = self.client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        assert "Stock In" in content
    
    def test_stock_in_landing_shows_two_cards(self):
        """Landing page should show Pharmacy and Cosmetics cards."""
        url = reverse("pharmacy:stock_in_choice")
        response = self.client.get(url)
        content = response.content.decode()
        
        # Check for both cards
        assert "Pharmacy" in content
        assert "Cosmetics" in content
        assert "stock-in-pharmacy-card" in content or "pharmacy" in content.lower()
        assert "stock-in-cosmetics-card" in content or "cosmetics" in content.lower()
    
    def test_stock_in_landing_has_custom_option(self):
        """Landing page should have a custom product option."""
        url = reverse("pharmacy:stock_in_choice")
        response = self.client.get(url)
        content = response.content.decode()
        
        assert "Custom" in content or "custom" in content
        assert "stock-in-custom-btn" in content or "Custom Product" in content


@pytest.mark.django_db
class TestPharmacyCatalogPage(TestCase):
    """Test pharmacy product catalog page."""
    
    def setUp(self):
        """Create test business and user."""
        fixtures = create_test_pharmacy_fixtures()
        self.business = fixtures["business"]
        self.location = fixtures["location"]
        self.user = fixtures["user"]
        
        self.client = Client()
        self.client.login(username="manager@test.com", password="TestPass123!@#")
        
        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()
    
    def test_pharmacy_catalog_renders_200(self):
        """Pharmacy catalog page should load."""
        url = reverse("pharmacy:stock_in_catalog_pharmacy")
        response = self.client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        assert "Pharmacy" in content
        assert "Stock In" in content
    
    def test_cosmetics_catalog_renders_200(self):
        """Cosmetics catalog page should load."""
        url = reverse("pharmacy:stock_in_catalog_cosmetics")
        response = self.client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode()
        assert "Cosmetics" in content
        assert "Stock In" in content
    
    def test_pharmacy_catalog_shows_products(self):
        """Pharmacy catalog should display curated products."""
        url = reverse("pharmacy:stock_in_catalog_pharmacy")
        response = self.client.get(url)
        content = response.content.decode()
        
        # Check for common pharmacy products
        assert "Paracetamol" in content or "paracetamol" in content.lower()
        assert "product-card" in content
    
    def test_cosmetics_catalog_shows_products(self):
        """Cosmetics catalog should display curated products."""
        url = reverse("pharmacy:stock_in_catalog_cosmetics")
        response = self.client.get(url)
        content = response.content.decode()
        
        # Check for common cosmetics products
        assert "Lotion" in content or "lotion" in content.lower() or "Body" in content
        assert "product-card" in content


@pytest.mark.django_db
class TestCatalogStockInSave(TestCase):
    """Test stock-in save via catalog flow."""
    
    def setUp(self):
        """Create test business and user."""
        fixtures = create_test_pharmacy_fixtures()
        self.business = fixtures["business"]
        self.location = fixtures["location"]
        self.user = fixtures["user"]
        
        self.client = Client()
        self.client.login(username="manager@test.com", password="TestPass123!@#")
        
        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()
    
    def test_catalog_save_endpoint_creates_product(self):
        """Stock-in via catalog should create product and batch."""
        url = reverse("pharmacy:stock_in_catalog_save")
        print(f"Test URL: {url}")
        
        data = {
            "product_name": "Paracetamol 500mg",
            "category": "analgesic",
            "quantity": 100,
            "cost_price": 50.00,
            "selling_price": 75.00,
            "expiry_date": (date.today() + timedelta(days=365)).isoformat(),
            "batch_number": "TEST001",
        }
        
        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'  # Mark as AJAX request
        )
        
        # Debug output
        print(f"Response status: {response.status_code}")
        print(f"Response content-type: {response.get('Content-Type')}")
        print(f"Response content (first 500 chars): {response.content.decode()[:500]}")
        
        # The middleware might be redirecting - let's handle that
        if response.status_code == 302:
            print(f"Redirect to: {response.url}")
            assert False, f"Unexpected redirect to {response.url}"
        
        assert response.status_code == 200
        
        # Check if it's actually JSON
        if 'application/json' not in response.get('Content-Type', ''):
            assert False, f"Expected JSON response, got {response.get('Content-Type')}: {response.content.decode()[:500]}"
        
        result = response.json()
        assert result["ok"] is True
        assert "message" in result
        
        # Verify product was created
        product = MerchProduct.objects.filter(
            business=self.business,
            name="Paracetamol 500mg",
            kind="pharmacy"
        ).first()
        
        assert product is not None
        assert product.quantity_in_stock >= 100
        
        # Verify batch was created
        batch = PharmacyBatch.objects.filter(
            business=self.business,
            merch_product=product
        ).first()
        
        assert batch is not None
        assert batch.quantity >= 100
    
    def test_catalog_save_without_expiry_works(self):
        """Stock-in for cosmetics without expiry should work."""
        url = reverse("pharmacy:stock_in_catalog_save")
        
        data = {
            "product_name": "Body Lotion",
            "category": "skin_care",
            "quantity": 50,
            "cost_price": 100.00,
            "selling_price": 150.00,
            "expiry_date": None,
            "batch_number": None,
        }
        
        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type="application/json"
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["ok"] is True
        
        # Verify product was created
        product = MerchProduct.objects.filter(
            business=self.business,
            name="Body Lotion",
            kind="pharmacy"
        ).first()
        
        assert product is not None
    
    def test_catalog_save_validates_required_fields(self):
        """Catalog save should validate required fields."""
        url = reverse("pharmacy:stock_in_catalog_save")
        
        # Missing product_name
        data = {
            "category": "analgesic",
            "quantity": 10,
            "cost_price": 50.00,
            "selling_price": 75.00,
        }
        
        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type="application/json"
        )
        
        assert response.status_code == 400
        result = response.json()
        assert result["ok"] is False
        assert "error" in result


@pytest.mark.django_db
class TestPharmacyUXRegressions(TestCase):
    """Ensure no regressions in existing pharmacy functionality."""
    
    def setUp(self):
        """Create test business and user."""
        fixtures = create_test_pharmacy_fixtures()
        self.business = fixtures["business"]
        self.location = fixtures["location"]
        self.user = fixtures["user"]
        
        self.client = Client()
        self.client.login(username="manager@test.com", password="TestPass123!@#")
        
        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()
    
    def test_legacy_stock_in_form_still_works(self):
        """Legacy stock-in form should still be accessible."""
        url = reverse("pharmacy:stock_in")
        response = self.client.get(url)
        
        # Should load or redirect, but not error
        assert response.status_code in [200, 302]
    
    def test_batch_list_still_works(self):
        """Batch list page should still work."""
        url = reverse("pharmacy:batch_list")
        response = self.client.get(url)
        
        assert response.status_code == 200
    
    def test_fast_sell_still_works(self):
        """Fast sell page should still work."""
        url = reverse("pharmacy:fast_sell")
        response = self.client.get(url)
        
        assert response.status_code == 200
    
    def test_wizard_stock_in_still_works(self):
        """Wizard stock-in should still be accessible."""
        url = reverse("pharmacy:stock_in_wizard")
        response = self.client.get(url)
        
        assert response.status_code == 200


@pytest.mark.django_db
class TestPharmacyWorkflowIntegration(TestCase):
    """End-to-end workflow tests."""
    
    def setUp(self):
        """Create test business and user."""
        fixtures = create_test_pharmacy_fixtures()
        self.business = fixtures["business"]
        self.location = fixtures["location"]
        self.user = fixtures["user"]
        
        self.client = Client()
        self.client.login(username="manager@test.com", password="TestPass123!@#")
        
        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()
    
    def test_full_pharmacy_workflow(self):
        """Test complete workflow: dashboard → stock-in → product created."""
        # 1. Visit dashboard
        dashboard_url = reverse("pharmacy:dashboard")
        response = self.client.get(dashboard_url)
        assert response.status_code == 200
        
        # 2. Visit stock-in landing
        choice_url = reverse("pharmacy:stock_in_choice")
        response = self.client.get(choice_url)
        assert response.status_code == 200
        
        # 3. Visit pharmacy catalog
        catalog_url = reverse("pharmacy:stock_in_catalog_pharmacy")
        response = self.client.get(catalog_url)
        assert response.status_code == 200
        
        # 4. Stock in a product
        save_url = reverse("pharmacy:stock_in_catalog_save")
        data = {
            "product_name": "Test Medicine",
            "category": "analgesic",
            "quantity": 50,
            "cost_price": 100.00,
            "selling_price": 150.00,
        }
        
        response = self.client.post(
            save_url,
            data=json.dumps(data),
            content_type="application/json"
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["ok"] is True
        
        # 5. Verify product exists
        product = MerchProduct.objects.filter(
            business=self.business,
            name="Test Medicine"
        ).first()
        
        assert product is not None
        assert product.quantity_in_stock >= 50


# ============================================================================
# RUN INSTRUCTIONS
# ============================================================================
#
# To run these tests:
#   pytest inventory/tests/test_pharmacy_ux_upgrade.py -v
#
# To run with coverage:
#   pytest inventory/tests/test_pharmacy_ux_upgrade.py --cov=inventory.views_pharmacy --cov-report=term-missing
#
# ============================================================================

