"""
Test suite for liquor stock list vertical isolation.

CRITICAL BUG FIX: Ensure liquor businesses NEVER access phone stock list UI.

This test suite ensures:
1. Liquor "View Stock" links route to liquor:stock_list (not inventory:stock_list)
2. Liquor businesses accessing inventory:stock_list are redirected/blocked
3. Phone businesses can still access inventory:stock_list normally
4. No IMEI UI appears on liquor stock pages
5. Category filtering works correctly for liquor
"""

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal

from tenants.models import Business, Membership
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.mark.django_db
class TestLiquorStockListVerticalIsolation(TestCase):
    """Test vertical isolation between liquor and phone stock lists."""
    
    def setUp(self):
        """Set up test data with liquor and phone businesses."""
        # Create liquor business
        self.liquor_business = Business.objects.create(
            name="Test Liquor Store",
            slug="test-liquor-store",
            status="ACTIVE",
            business_kind=BusinessKind.LIQUOR
        )
        
        # Create phone business
        self.phone_business = Business.objects.create(
            name="Test Phone Store",
            slug="test-phone-store",
            status="ACTIVE",
            business_kind="phones"
        )
        
        # Create users
        self.liquor_user = User.objects.create_user(
            username="liquor_manager",
            email="liquor@test.com",
            password="TestPass123!"
        )
        self.phone_user = User.objects.create_user(
            username="phone_manager",
            email="phone@test.com",
            password="TestPass123!"
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.liquor_user,
            business=self.liquor_business,
            role="MANAGER",
            status="ACTIVE"
        )
        Membership.objects.create(
            user=self.phone_user,
            business=self.phone_business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Create liquor products
        self.beer = MerchProduct.objects.create(
            business=self.liquor_business,
            name="Castle Lite",
            kind=BusinessKind.LIQUOR,
            category="beer",
            quantity_in_stock=50,
            cost_per_bottle=Decimal("500.00"),
            price_per_bottle=Decimal("1000.00"),
            is_active=True
        )
        self.cider = MerchProduct.objects.create(
            business=self.liquor_business,
            name="Savanna Dry",
            kind=BusinessKind.LIQUOR,
            category="cider",
            quantity_in_stock=30,
            cost_per_bottle=Decimal("600.00"),
            price_per_bottle=Decimal("1200.00"),
            is_active=True
        )
        
        self.client = Client()
    
    def test_liquor_stock_list_url_exists(self):
        """Test that liquor:stock_list URL route exists."""
        url = reverse("liquor:stock_list")
        self.assertIsNotNone(url)
        self.assertEqual(url, "/liquor/stock/list/")
    
    def test_liquor_user_can_access_liquor_stock_list(self):
        """Test that liquor users can access liquor stock list."""
        self.client.login(username="liquor_manager", password="TestPass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.liquor_business.id
        session.save()
        
        url = reverse("liquor:stock_list")
        response = self.client.get(url)
        
        # Should return 200
        self.assertEqual(response.status_code, 200)
        
        # Should use liquor template (not phone template)
        self.assertTemplateUsed(response, "verticals/liquor/stock_list.html")
    
    def test_liquor_user_accessing_phone_stock_list_gets_redirected(self):
        """
        CRITICAL: Liquor user accessing inventory:stock_list (phone route)
        should be redirected to liquor:stock_list.
        """
        self.client.login(username="liquor_manager", password="TestPass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.liquor_business.id
        session.save()
        
        # Try to access phone stock list
        phone_stock_url = reverse("inventory:stock_list")
        response = self.client.get(phone_stock_url)
        
        # Should NOT return 200 (should redirect or 404)
        self.assertNotEqual(response.status_code, 200, 
                          "Liquor business MUST NOT get 200 from phone stock list")
        
        # Should redirect to liquor stock list
        if response.status_code == 302:
            self.assertIn("liquor/stock/list", response.url)
    
    def test_phone_user_can_access_phone_stock_list(self):
        """Test that phone users can still access inventory:stock_list normally."""
        self.client.login(username="phone_manager", password="TestPass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.phone_business.id
        session.save()
        
        url = reverse("inventory:stock_list")
        response = self.client.get(url)
        
        # Should return 200 (phones can access their own stock list)
        self.assertEqual(response.status_code, 200)
    
    def test_liquor_stock_list_shows_liquor_products_only(self):
        """Test that liquor stock list shows only liquor products."""
        self.client.login(username="liquor_manager", password="TestPass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.liquor_business.id
        session.save()
        
        url = reverse("liquor:stock_list")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check context
        products = response.context["products"]
        self.assertEqual(len(products), 2)
        
        # All products should be from liquor business
        for product in products:
            self.assertEqual(product.business_id, self.liquor_business.id)
            self.assertEqual(product.kind, BusinessKind.LIQUOR)
    
    def test_liquor_stock_list_category_filter(self):
        """Test category filtering on liquor stock list."""
        self.client.login(username="liquor_manager", password="TestPass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.liquor_business.id
        session.save()
        
        # Filter by beer category
        url = reverse("liquor:stock_list") + "?category=beer"
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        products = response.context["products"]
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].category, "beer")
        self.assertEqual(products[0].name, "Castle Lite")
    
    def test_liquor_stock_list_has_no_imei_ui(self):
        """
        CRITICAL: Ensure liquor stock list does NOT show IMEI scanner or phone UI.
        """
        self.client.login(username="liquor_manager", password="TestPass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.liquor_business.id
        session.save()
        
        url = reverse("liquor:stock_list")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that response does NOT contain phone-specific terms
        content = response.content.decode('utf-8').lower()
        
        # Should NOT have IMEI references
        self.assertNotIn("imei", content, 
                        "Liquor stock list must NOT show IMEI UI")
        self.assertNotIn("scan imei", content)
        
        # Should NOT have phone/warranty references
        self.assertNotIn("warranty", content)
        self.assertNotIn("phone scanner", content)
    
    def test_liquor_stock_list_shows_liquor_appropriate_ui(self):
        """Test that liquor stock list shows liquor-appropriate UI elements."""
        self.client.login(username="liquor_manager", password="TestPass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.liquor_business.id
        session.save()
        
        url = reverse("liquor:stock_list")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8').lower()
        
        # Should have liquor-specific terms
        self.assertIn("bottle", content)
        self.assertIn("liquor", content)
        
        # Should show product names
        self.assertIn("castle lite", content)
        self.assertIn("savanna dry", content)
    
    def test_liquor_stock_list_search_filter(self):
        """Test search functionality on liquor stock list."""
        self.client.login(username="liquor_manager", password="TestPass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.liquor_business.id
        session.save()
        
        # Search for "castle"
        url = reverse("liquor:stock_list") + "?q=castle"
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        products = response.context["products"]
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].name, "Castle Lite")
    
    def test_liquor_stock_list_displays_correct_metrics(self):
        """Test that liquor stock list displays correct business metrics."""
        self.client.login(username="liquor_manager", password="TestPass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.liquor_business.id
        session.save()
        
        url = reverse("liquor:stock_list")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check context metrics
        self.assertEqual(response.context["total_products"], 2)
        self.assertEqual(response.context["total_quantity"], 80)  # 50 + 30
        
        # Check cost and retail values
        expected_cost = (50 * Decimal("500.00")) + (30 * Decimal("600.00"))  # 43000
        expected_retail = (50 * Decimal("1000.00")) + (30 * Decimal("1200.00"))  # 86000
        expected_profit = expected_retail - expected_cost  # 43000
        
        self.assertEqual(response.context["total_cost_value"], expected_cost)
        self.assertEqual(response.context["total_retail_value"], expected_retail)
        self.assertEqual(response.context["expected_profit"], expected_profit)
    
    def test_routing_helper_returns_liquor_stock_list_for_liquor_business(self):
        """Test that _get_vertical_stock_url returns correct URL for liquor."""
        from inventory.views_router import _get_vertical_stock_url
        from inventory.helpers_core import LIQUOR
        
        url = _get_vertical_stock_url(LIQUOR)
        
        # Should return liquor stock list URL, not phone stock list
        self.assertEqual(url, reverse("liquor:stock_list"))
        self.assertNotEqual(url, reverse("inventory:stock_list"))
    
    def test_no_cross_business_data_leakage(self):
        """
        CRITICAL: Ensure liquor business A cannot see liquor business B's data.
        """
        # Create another liquor business
        other_liquor_business = Business.objects.create(
            name="Other Liquor Store",
            slug="other-liquor-store",
            status="ACTIVE",
            business_kind=BusinessKind.LIQUOR
        )
        
        # Create product for other business
        other_product = MerchProduct.objects.create(
            business=other_liquor_business,
            name="Other Business Product",
            kind=BusinessKind.LIQUOR,
            category="beer",
            quantity_in_stock=100,
            cost_per_bottle=Decimal("500.00"),
            price_per_bottle=Decimal("1000.00"),
            is_active=True
        )
        
        # Login as liquor_user (belongs to liquor_business)
        self.client.login(username="liquor_manager", password="TestPass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.liquor_business.id
        session.save()
        
        url = reverse("liquor:stock_list")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        products = response.context["products"]
        
        # Should only see own business products (2)
        self.assertEqual(len(products), 2)
        
        # Should NOT see other business's product
        product_names = [p.name for p in products]
        self.assertNotIn("Other Business Product", product_names)


@pytest.mark.django_db
class TestLiquorHubLinks(TestCase):
    """Test that liquor hub "View Stock" links route correctly."""
    
    def setUp(self):
        """Set up liquor business and user."""
        self.liquor_business = Business.objects.create(
            name="Test Liquor Store",
            slug="test-liquor-store",
            status="ACTIVE",
            business_kind=BusinessKind.LIQUOR
        )
        
        self.liquor_user = User.objects.create_user(
            username="liquor_manager",
            email="liquor@test.com",
            password="TestPass123!"
        )
        
        Membership.objects.create(
            user=self.liquor_user,
            business=self.liquor_business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client = Client()
    
    def test_liquor_hub_uses_liquor_stock_list_url(self):
        """Test that liquor hub template uses liquor:stock_list not inventory:stock_list."""
        self.client.login(username="liquor_manager", password="TestPass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.liquor_business.id
        session.save()
        
        # Get liquor hub page
        hub_url = reverse("liquor:inventory_dashboard")
        response = self.client.get(hub_url)
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        
        # Should link to liquor:stock_list
        self.assertIn("liquor/stock/list", content, 
                     "Liquor hub must link to liquor stock list")
        
        # Should NOT link to inventory:stock_list (phone route)
        # Note: This is a bit tricky to test without parsing HTML properly,
        # but we can check that if inventory/list/ appears, it's not in a href
        if "inventory/list/" in content:
            # Make sure it's not in an <a href="">
            import re
            phone_links = re.findall(r'<a[^>]*href=["\']/inventory/list/[^"\']*["\'][^>]*>', content)
            self.assertEqual(len(phone_links), 0, 
                           "Liquor hub must NOT link to phone stock list")


# Run with: pytest tests/test_liquor_stock_vertical_leakage.py -v

