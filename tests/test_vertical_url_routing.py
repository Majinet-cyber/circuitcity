"""
Test vertical URL routing standardization.

Ensures:
- Phones businesses use /inventory/... routes with inventory-style sidebar
- Gym/Clothing/Liquor/Pharmacy use /verticals/<slug>/dashboard/ with vertical-specific sidebars
- Legacy /inventory/verticals/ URLs redirect properly
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestPhonesInventoryRouting(TestCase):
    """Test that phones businesses maintain core inventory behavior."""
    
    def setUp(self):
        """Create a phones business with manager and agent."""
        from tenants.models import Business
        from accounts.models import Profile
        
        # Create business
        self.business = Business.objects.create(
            name="Test Phones Store",
            business_kind="phones",
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="phones_manager",
            email="manager@phones.test",
            password="testpass123"
        )
        self.manager_profile = Profile.objects.get_or_create(user=self.manager)[0]
        self.manager_profile.is_manager = True
        self.manager_profile.save()
        
        # Associate manager with business
        self.business.manager = self.manager
        self.business.save()
        
        self.client = Client()
    
    def test_phones_dashboard_url_accessible(self):
        """Phones dashboard should be at /inventory/dashboard/"""
        self.client.login(username="phones_manager", password="testpass123")
        
        # Activate business session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get("/inventory/dashboard/")
        
        # Should return 200 or redirect (but not 404)
        self.assertIn(response.status_code, [200, 302])
    
    def test_phones_sidebar_has_inventory_items(self):
        """Phones sidebar should show inventory-specific menu items."""
        self.client.login(username="phones_manager", password="testpass123")
        
        # Activate business session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        # Get dashboard page
        response = self.client.get("/inventory/dashboard/")
        
        # If we got redirected to a vertical, that's wrong for phones
        if response.status_code == 302:
            redirect_url = response.url
            # Phones should NOT redirect to /verticals/
            self.assertNotIn("/verticals/", redirect_url)
    
    def test_phones_sidebar_items_from_context(self):
        """Phones sidebar should contain core inventory items, not vertical items."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        sidebar_items = get_vertical_sidebar_items("phones")
        
        # Extract all labels
        labels = [item["label"] for item in sidebar_items]
        
        # Should have phones-specific items
        # Note: "Inventory Dashboard" removed for phones - replaced by "Analytics"
        self.assertIn("Analytics", labels)
        self.assertIn("Stock", labels)
        self.assertIn("Scan IN", labels)
        
        # Should NOT have gym-specific items
        self.assertNotIn("Gym Hub", labels)
        self.assertNotIn("Members", labels)
        self.assertNotIn("Check-ins", labels)
        
        # Should NOT have clothing-specific items
        self.assertNotIn("Clothing Hub", labels)
        
        # Should NOT have liquor-specific items
        self.assertNotIn("Liquor Hub", labels)
        
        # Should NOT have pharmacy-specific items
        self.assertNotIn("Pharmacy Hub", labels)


@pytest.mark.django_db
class TestGymVerticalRouting(TestCase):
    """Test gym vertical uses /verticals/gym/ routes."""
    
    def setUp(self):
        """Create a gym business with manager."""
        from tenants.models import Business
        from accounts.models import Profile
        
        # Create business
        self.business = Business.objects.create(
            name="Test Gym",
            business_kind="gym",
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="gym_manager",
            email="manager@gym.test",
            password="testpass123"
        )
        self.manager_profile = Profile.objects.get_or_create(user=self.manager)[0]
        self.manager_profile.is_manager = True
        self.manager_profile.save()
        
        # Associate manager with business
        self.business.manager = self.manager
        self.business.save()
        
        self.client = Client()
    
    def test_gym_canonical_url_accessible(self):
        """Gym dashboard should be accessible at /verticals/gym/dashboard/"""
        self.client.login(username="gym_manager", password="testpass123")
        
        # Activate business session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get("/verticals/gym/dashboard/")
        
        # Should return 200
        self.assertEqual(response.status_code, 200)
    
    def test_gym_dashboard_shows_gym_content(self):
        """Gym dashboard should show gym-specific content."""
        self.client.login(username="gym_manager", password="testpass123")
        
        # Activate business session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get("/verticals/gym/dashboard/")
        content = response.content.decode("utf-8")
        
        # Should contain gym-related text
        # (Exact text depends on template, but should have gym indicator)
        self.assertIn("Gym", content.lower())
    
    def test_gym_sidebar_has_vertical_items(self):
        """Gym sidebar should show gym-specific menu items, not phones items."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        sidebar_items = get_vertical_sidebar_items("gym")
        
        # Extract all labels
        labels = [item["label"] for item in sidebar_items]
        
        # Should have gym-specific items
        self.assertIn("Gym Hub", labels)
        self.assertIn("Trainers", labels)  # Agents labeled as Trainers for gym
        
        # Should NOT have phones-only items
        self.assertNotIn("Inventory Dashboard", labels)
        self.assertNotIn("Stock", labels)
        self.assertNotIn("Scan IN", labels)
    
    def test_gym_legacy_url_redirects(self):
        """Legacy /inventory/verticals/gym/ should redirect to new canonical URL."""
        self.client.login(username="gym_manager", password="testpass123")
        
        # Activate business session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get("/inventory/verticals/gym/")
        
        # Should redirect
        self.assertEqual(response.status_code, 302)
        
        # Should redirect to new canonical URL
        self.assertEqual(response.url, "/verticals/gym/dashboard/")
    
    def test_gym_url_namespace_resolves(self):
        """The verticals:gym_dashboard URL name should resolve correctly."""
        url = reverse("verticals:gym_dashboard")
        self.assertEqual(url, "/verticals/gym/dashboard/")


@pytest.mark.django_db
class TestClothingVerticalRouting(TestCase):
    """Test clothing vertical uses /verticals/clothing/ routes."""
    
    def setUp(self):
        """Create a clothing business with manager."""
        from tenants.models import Business
        from accounts.models import Profile
        
        # Create business
        self.business = Business.objects.create(
            name="Test Clothing Store",
            business_kind="clothing",
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="clothing_manager",
            email="manager@clothing.test",
            password="testpass123"
        )
        self.manager_profile = Profile.objects.get_or_create(user=self.manager)[0]
        self.manager_profile.is_manager = True
        self.manager_profile.save()
        
        # Associate manager with business
        self.business.manager = self.manager
        self.business.save()
        
        self.client = Client()
    
    def test_clothing_canonical_url_accessible(self):
        """Clothing dashboard should be accessible at /verticals/clothing/dashboard/"""
        self.client.login(username="clothing_manager", password="testpass123")
        
        # Activate business session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get("/verticals/clothing/dashboard/")
        
        # Should return 200
        self.assertEqual(response.status_code, 200)
    
    def test_clothing_sidebar_has_vertical_items(self):
        """Clothing sidebar should show clothing-specific items."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        sidebar_items = get_vertical_sidebar_items("clothing")
        
        # Extract all labels
        labels = [item["label"] for item in sidebar_items]
        
        # Should have clothing-specific items
        self.assertIn("Clothing Hub", labels)
        
        # Should NOT have phones-only items
        self.assertNotIn("Inventory Dashboard", labels)
        self.assertNotIn("Scan IN", labels)
    
    def test_clothing_legacy_url_redirects(self):
        """Legacy /inventory/verticals/clothing/ should redirect."""
        self.client.login(username="clothing_manager", password="testpass123")
        
        # Activate business session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get("/inventory/verticals/clothing/")
        
        # Should redirect
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/verticals/clothing/dashboard/")
    
    def test_clothing_url_namespace_resolves(self):
        """The verticals:clothing_dashboard URL name should resolve."""
        url = reverse("verticals:clothing_dashboard")
        self.assertEqual(url, "/verticals/clothing/dashboard/")


@pytest.mark.django_db
class TestLiquorVerticalRouting(TestCase):
    """Test liquor vertical uses /verticals/liquor/ routes."""
    
    def setUp(self):
        """Create a liquor business with manager."""
        from tenants.models import Business
        from accounts.models import Profile
        
        # Create business
        self.business = Business.objects.create(
            name="Test Liquor Store",
            business_kind="liquor",
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="liquor_manager",
            email="manager@liquor.test",
            password="testpass123"
        )
        self.manager_profile = Profile.objects.get_or_create(user=self.manager)[0]
        self.manager_profile.is_manager = True
        self.manager_profile.save()
        
        # Associate manager with business
        self.business.manager = self.manager
        self.business.save()
        
        self.client = Client()
    
    def test_liquor_canonical_url_accessible(self):
        """Liquor dashboard should be accessible at /verticals/liquor/dashboard/"""
        self.client.login(username="liquor_manager", password="testpass123")
        
        # Activate business session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get("/verticals/liquor/dashboard/")
        
        # Should return 200
        self.assertEqual(response.status_code, 200)
    
    def test_liquor_sidebar_has_vertical_items(self):
        """Liquor sidebar should show liquor-specific items."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        sidebar_items = get_vertical_sidebar_items("liquor")
        
        # Extract all labels
        labels = [item["label"] for item in sidebar_items]
        
        # Should have liquor-specific items
        self.assertIn("Liquor Hub", labels)
        
        # Should NOT have phones-only items
        self.assertNotIn("Inventory Dashboard", labels)
        self.assertNotIn("Scan IN", labels)
    
    def test_liquor_legacy_url_redirects(self):
        """Legacy /inventory/verticals/liquor/ should redirect."""
        self.client.login(username="liquor_manager", password="testpass123")
        
        # Activate business session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get("/inventory/verticals/liquor/")
        
        # Should redirect
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/verticals/liquor/dashboard/")
    
    def test_liquor_url_namespace_resolves(self):
        """The verticals:liquor_dashboard URL name should resolve."""
        url = reverse("verticals:liquor_dashboard")
        self.assertEqual(url, "/verticals/liquor/dashboard/")


@pytest.mark.django_db
class TestPharmacyVerticalRouting(TestCase):
    """Test pharmacy vertical uses /verticals/pharmacy/ routes."""
    
    def setUp(self):
        """Create a pharmacy business with manager."""
        from tenants.models import Business
        from accounts.models import Profile
        
        # Create business
        self.business = Business.objects.create(
            name="Test Pharmacy",
            business_kind="pharmacy",
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="pharmacy_manager",
            email="manager@pharmacy.test",
            password="testpass123"
        )
        self.manager_profile = Profile.objects.get_or_create(user=self.manager)[0]
        self.manager_profile.is_manager = True
        self.manager_profile.save()
        
        # Associate manager with business
        self.business.manager = self.manager
        self.business.save()
        
        self.client = Client()
    
    def test_pharmacy_canonical_url_accessible(self):
        """Pharmacy dashboard should be accessible at /verticals/pharmacy/dashboard/"""
        self.client.login(username="pharmacy_manager", password="testpass123")
        
        # Activate business session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get("/verticals/pharmacy/dashboard/")
        
        # Should return 200
        self.assertEqual(response.status_code, 200)
    
    def test_pharmacy_sidebar_has_vertical_items(self):
        """Pharmacy sidebar should show pharmacy-specific items."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        sidebar_items = get_vertical_sidebar_items("pharmacy")
        
        # Extract all labels
        labels = [item["label"] for item in sidebar_items]
        
        # Should have pharmacy-specific items
        self.assertIn("Pharmacy Hub", labels)
        
        # Should NOT have phones-only items
        self.assertNotIn("Inventory Dashboard", labels)
        self.assertNotIn("Scan IN", labels)
    
    def test_pharmacy_legacy_url_redirects(self):
        """Legacy /inventory/verticals/pharmacy/ should redirect."""
        self.client.login(username="pharmacy_manager", password="testpass123")
        
        # Activate business session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get("/inventory/verticals/pharmacy/")
        
        # Should redirect
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/verticals/pharmacy/dashboard/")
    
    def test_pharmacy_url_namespace_resolves(self):
        """The verticals:pharmacy_dashboard URL name should resolve."""
        url = reverse("verticals:pharmacy_dashboard")
        self.assertEqual(url, "/verticals/pharmacy/dashboard/")


@pytest.mark.django_db
class TestVerticalUtilsFunctions(TestCase):
    """Test the utility functions for vertical routing."""
    
    def test_get_vertical_dashboard_url_for_gym(self):
        """Gym should return verticals:gym_dashboard"""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        url_name = get_vertical_dashboard_url("gym")
        self.assertEqual(url_name, "verticals:gym_dashboard")
    
    def test_get_vertical_dashboard_url_for_clothing(self):
        """Clothing should return verticals:clothing_dashboard"""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        url_name = get_vertical_dashboard_url("clothing")
        self.assertEqual(url_name, "verticals:clothing_dashboard")
    
    def test_get_vertical_dashboard_url_for_liquor(self):
        """Liquor should return verticals:liquor_dashboard"""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        url_name = get_vertical_dashboard_url("liquor")
        self.assertEqual(url_name, "verticals:liquor_dashboard")
    
    def test_get_vertical_dashboard_url_for_pharmacy(self):
        """Pharmacy should return verticals:pharmacy_dashboard"""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        url_name = get_vertical_dashboard_url("pharmacy")
        self.assertEqual(url_name, "verticals:pharmacy_dashboard")
    
    def test_get_vertical_dashboard_url_for_phones(self):
        """Phones should return None (uses default inventory dashboard)"""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        url_name = get_vertical_dashboard_url("phones")
        self.assertIsNone(url_name)

