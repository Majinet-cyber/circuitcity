# tests/smoke/test_sidebar_routes_admin.py
"""
Smoke tests for ADMIN/MANAGER sidebar navigation routes.

Tests that every sidebar link for admin/manager role:
- Can be reversed (no NoReverseMatch)
- Loads without 500 errors
- Does not contain error templates

This is a fast Django test client layer that catches URL resolution issues.
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from tests.smoke.fixtures import SmokeTestFixtures
from tests.smoke.helpers import SidebarLinkExtractor, SessionHelper


@pytest.mark.django_db
class TestSidebarRoutesAdminPhones(TestCase):
    """Test admin sidebar routes for Phones vertical."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setup_data = SmokeTestFixtures.create_complete_vertical_setup(
            BusinessKind.PHONES, "Phones Admin Test"
        )
    
    def setUp(self):
        self.client = Client()
        self.client.login(
            username=self.setup_data['admin_user'].username,
            password=self.setup_data['admin_password']
        )
        SessionHelper.set_active_business(self.client, self.setup_data['business'])
        SessionHelper.set_active_location(self.client, self.setup_data['location'])
    
    def test_phones_admin_sidebar_urls_resolve(self):
        """Test that all Phones admin sidebar URLs can be reversed."""
        items = SidebarLinkExtractor.get_sidebar_links_for_vertical("phones", "manager")
        resolved = SidebarLinkExtractor.resolve_sidebar_urls(items)
        
        errors = []
        for label, url, error in resolved:
            if error:
                errors.append(f"{label}: {error}")
        
        assert len(errors) == 0, f"URL resolution errors for Phones admin:\n" + "\n".join(errors)
    
    def test_phones_admin_sidebar_urls_load(self):
        """Test that all Phones admin sidebar URLs load without 500 errors."""
        items = SidebarLinkExtractor.get_sidebar_links_for_vertical("phones", "manager")
        resolved = SidebarLinkExtractor.resolve_sidebar_urls(items)
        
        errors = []
        for label, url, resolve_error in resolved:
            if resolve_error:
                errors.append(f"{label}: {resolve_error}")
                continue
            
            if not url:
                continue
            
            status, load_error = SidebarLinkExtractor.test_url_loads(self.client, url)
            
            if load_error:
                errors.append(f"{label} ({url}): {load_error}")
            elif status not in [200, 302]:
                errors.append(f"{label} ({url}): HTTP {status}")
        
        assert len(errors) == 0, f"URL loading errors for Phones admin:\n" + "\n".join(errors)


@pytest.mark.django_db
class TestSidebarRoutesAdminPharmacy(TestCase):
    """Test admin sidebar routes for Pharmacy vertical."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setup_data = SmokeTestFixtures.create_complete_vertical_setup(
            BusinessKind.PHARMACY, "Pharmacy Admin Test"
        )
    
    def setUp(self):
        self.client = Client()
        self.client.login(
            username=self.setup_data['admin_user'].username,
            password=self.setup_data['admin_password']
        )
        SessionHelper.set_active_business(self.client, self.setup_data['business'])
        SessionHelper.set_active_location(self.client, self.setup_data['location'])
    
    def test_pharmacy_admin_sidebar_urls_resolve(self):
        """Test that all Pharmacy admin sidebar URLs can be reversed."""
        items = SidebarLinkExtractor.get_sidebar_links_for_vertical("pharmacy", "manager")
        resolved = SidebarLinkExtractor.resolve_sidebar_urls(items)
        
        errors = []
        for label, url, error in resolved:
            if error:
                errors.append(f"{label}: {error}")
        
        assert len(errors) == 0, f"URL resolution errors for Pharmacy admin:\n" + "\n".join(errors)
    
    def test_pharmacy_admin_sidebar_urls_load(self):
        """Test that all Pharmacy admin sidebar URLs load without 500 errors."""
        items = SidebarLinkExtractor.get_sidebar_links_for_vertical("pharmacy", "manager")
        resolved = SidebarLinkExtractor.resolve_sidebar_urls(items)
        
        errors = []
        for label, url, resolve_error in resolved:
            if resolve_error:
                errors.append(f"{label}: {resolve_error}")
                continue
            
            if not url:
                continue
            
            status, load_error = SidebarLinkExtractor.test_url_loads(self.client, url)
            
            if load_error:
                errors.append(f"{label} ({url}): {load_error}")
            elif status not in [200, 302]:
                errors.append(f"{label} ({url}): HTTP {status}")
        
        assert len(errors) == 0, f"URL loading errors for Pharmacy admin:\n" + "\n".join(errors)


@pytest.mark.django_db
class TestSidebarRoutesAdminClothing(TestCase):
    """Test admin sidebar routes for Clothing vertical."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setup_data = SmokeTestFixtures.create_complete_vertical_setup(
            BusinessKind.CLOTHING, "Clothing Admin Test"
        )
    
    def setUp(self):
        self.client = Client()
        self.client.login(
            username=self.setup_data['admin_user'].username,
            password=self.setup_data['admin_password']
        )
        SessionHelper.set_active_business(self.client, self.setup_data['business'])
        SessionHelper.set_active_location(self.client, self.setup_data['location'])
    
    def test_clothing_admin_sidebar_urls_resolve(self):
        """Test that all Clothing admin sidebar URLs can be reversed."""
        items = SidebarLinkExtractor.get_sidebar_links_for_vertical("clothing", "manager")
        resolved = SidebarLinkExtractor.resolve_sidebar_urls(items)
        
        errors = []
        for label, url, error in resolved:
            if error:
                errors.append(f"{label}: {error}")
        
        assert len(errors) == 0, f"URL resolution errors for Clothing admin:\n" + "\n".join(errors)
    
    def test_clothing_admin_sidebar_urls_load(self):
        """Test that all Clothing admin sidebar URLs load without 500 errors."""
        items = SidebarLinkExtractor.get_sidebar_links_for_vertical("clothing", "manager")
        resolved = SidebarLinkExtractor.resolve_sidebar_urls(items)
        
        errors = []
        for label, url, resolve_error in resolved:
            if resolve_error:
                errors.append(f"{label}: {resolve_error}")
                continue
            
            if not url:
                continue
            
            status, load_error = SidebarLinkExtractor.test_url_loads(self.client, url)
            
            if load_error:
                errors.append(f"{label} ({url}): {load_error}")
            elif status not in [200, 302]:
                errors.append(f"{label} ({url}): HTTP {status}")
        
        assert len(errors) == 0, f"URL loading errors for Clothing admin:\n" + "\n".join(errors)


@pytest.mark.django_db
class TestSidebarRoutesAdminLiquor(TestCase):
    """Test admin sidebar routes for Liquor vertical."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setup_data = SmokeTestFixtures.create_complete_vertical_setup(
            BusinessKind.LIQUOR, "Liquor Admin Test"
        )
    
    def setUp(self):
        self.client = Client()
        self.client.login(
            username=self.setup_data['admin_user'].username,
            password=self.setup_data['admin_password']
        )
        SessionHelper.set_active_business(self.client, self.setup_data['business'])
        SessionHelper.set_active_location(self.client, self.setup_data['location'])
    
    def test_liquor_admin_sidebar_urls_resolve(self):
        """Test that all Liquor admin sidebar URLs can be reversed."""
        items = SidebarLinkExtractor.get_sidebar_links_for_vertical("liquor", "manager")
        resolved = SidebarLinkExtractor.resolve_sidebar_urls(items)
        
        errors = []
        for label, url, error in resolved:
            if error:
                errors.append(f"{label}: {error}")
        
        assert len(errors) == 0, f"URL resolution errors for Liquor admin:\n" + "\n".join(errors)
    
    def test_liquor_admin_sidebar_urls_load(self):
        """Test that all Liquor admin sidebar URLs load without 500 errors."""
        items = SidebarLinkExtractor.get_sidebar_links_for_vertical("liquor", "manager")
        resolved = SidebarLinkExtractor.resolve_sidebar_urls(items)
        
        errors = []
        for label, url, resolve_error in resolved:
            if resolve_error:
                errors.append(f"{label}: {resolve_error}")
                continue
            
            if not url:
                continue
            
            status, load_error = SidebarLinkExtractor.test_url_loads(self.client, url)
            
            if load_error:
                errors.append(f"{label} ({url}): {load_error}")
            elif status not in [200, 302]:
                errors.append(f"{label} ({url}): HTTP {status}")
        
        assert len(errors) == 0, f"URL loading errors for Liquor admin:\n" + "\n".join(errors)


@pytest.mark.django_db
class TestSidebarRoutesAdminGym(TestCase):
    """Test admin sidebar routes for Gym vertical."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setup_data = SmokeTestFixtures.create_complete_vertical_setup(
            BusinessKind.GYM, "Gym Admin Test"
        )
    
    def setUp(self):
        self.client = Client()
        self.client.login(
            username=self.setup_data['admin_user'].username,
            password=self.setup_data['admin_password']
        )
        SessionHelper.set_active_business(self.client, self.setup_data['business'])
        SessionHelper.set_active_location(self.client, self.setup_data['location'])
    
    def test_gym_admin_sidebar_urls_resolve(self):
        """Test that all Gym admin sidebar URLs can be reversed."""
        items = SidebarLinkExtractor.get_sidebar_links_for_vertical("gym", "manager")
        resolved = SidebarLinkExtractor.resolve_sidebar_urls(items)
        
        errors = []
        for label, url, error in resolved:
            if error:
                errors.append(f"{label}: {error}")
        
        assert len(errors) == 0, f"URL resolution errors for Gym admin:\n" + "\n".join(errors)
    
    def test_gym_admin_sidebar_urls_load(self):
        """Test that all Gym admin sidebar URLs load without 500 errors."""
        items = SidebarLinkExtractor.get_sidebar_links_for_vertical("gym", "manager")
        resolved = SidebarLinkExtractor.resolve_sidebar_urls(items)
        
        errors = []
        for label, url, resolve_error in resolved:
            if resolve_error:
                errors.append(f"{label}: {resolve_error}")
                continue
            
            if not url:
                continue
            
            status, load_error = SidebarLinkExtractor.test_url_loads(self.client, url)
            
            if load_error:
                errors.append(f"{label} ({url}): {load_error}")
            elif status not in [200, 302]:
                errors.append(f"{label} ({url}): HTTP {status}")
        
        assert len(errors) == 0, f"URL loading errors for Gym admin:\n" + "\n".join(errors)

