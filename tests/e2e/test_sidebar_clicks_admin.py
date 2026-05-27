# tests/e2e/test_sidebar_clicks_admin.py
"""
Playwright E2E smoke tests for ADMIN sidebar clicks.

These tests simulate real user interactions:
- Login as admin
- Click every sidebar link
- Verify each page loads without errors
- Screenshot failures for debugging

NOTE: These tests require the Django development server to be running.
Run with: python manage.py runserver (in separate terminal)
Then: pytest tests/e2e/test_sidebar_clicks_admin.py
"""
import pytest
from playwright.sync_api import Page

from tests.e2e.helpers import PlaywrightHelper


# Mark all tests in this module as requiring the Django DB and being E2E tests
pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


class TestAdminSidebarClicksPhones:
    """Test admin sidebar clicks for Phones vertical."""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page, base_url: str):
        """Setup: Create test data and login."""
        # Note: In a real scenario, we'd use Django management commands
        # or API endpoints to set up test data before running Playwright tests.
        # For now, we'll document this requirement.
        
        # Login as admin (assumes test user exists)
        PlaywrightHelper.login(page, base_url, 'admin_phones', 'testpass123')
        
        # Navigate to Phones dashboard
        page.goto(f"{base_url}/inventory/verticals/phones/dashboard/")
        page.wait_for_load_state('networkidle')
        
        self.page = page
        self.base_url = base_url
    
    def test_phones_admin_clicks_all_sidebar_links(self):
        """Test clicking all Phones admin sidebar links."""
        # Find all sidebar links
        links = PlaywrightHelper.find_sidebar_links(self.page)
        
        assert len(links) > 0, "No sidebar links found"
        
        errors = []
        for link_text, link_href in links:
            success, error = PlaywrightHelper.click_link_and_verify(
                self.page, link_text, link_href
            )
            
            if not success:
                errors.append(f"{link_text} ({link_href}): {error}")
                # Take screenshot on error
                safe_filename = link_text.replace(' ', '_').replace('/', '_')
                PlaywrightHelper.take_screenshot_on_error(
                    self.page, f"phones_admin_{safe_filename}_error.png"
                )
            
            # Navigate back to dashboard for next test
            self.page.goto(f"{self.base_url}/inventory/verticals/phones/dashboard/")
            self.page.wait_for_load_state('networkidle')
        
        assert len(errors) == 0, f"Sidebar link errors:\n" + "\n".join(errors)


class TestAdminSidebarClicksPharmacy:
    """Test admin sidebar clicks for Pharmacy vertical."""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page, base_url: str):
        """Setup: Login and navigate to Pharmacy dashboard."""
        PlaywrightHelper.login(page, base_url, 'admin_pharmacy', 'testpass123')
        page.goto(f"{base_url}/dashboard/")  # Pharmacy uses main dashboard
        page.wait_for_load_state('networkidle')
        
        self.page = page
        self.base_url = base_url
    
    def test_pharmacy_admin_clicks_all_sidebar_links(self):
        """Test clicking all Pharmacy admin sidebar links."""
        links = PlaywrightHelper.find_sidebar_links(self.page)
        
        assert len(links) > 0, "No sidebar links found"
        
        errors = []
        for link_text, link_href in links:
            success, error = PlaywrightHelper.click_link_and_verify(
                self.page, link_text, link_href
            )
            
            if not success:
                errors.append(f"{link_text} ({link_href}): {error}")
                safe_filename = link_text.replace(' ', '_').replace('/', '_')
                PlaywrightHelper.take_screenshot_on_error(
                    self.page, f"pharmacy_admin_{safe_filename}_error.png"
                )
            
            self.page.goto(f"{self.base_url}/dashboard/")
            self.page.wait_for_load_state('networkidle')
        
        assert len(errors) == 0, f"Sidebar link errors:\n" + "\n".join(errors)


class TestAdminSidebarClicksClothing:
    """Test admin sidebar clicks for Clothing vertical."""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page, base_url: str):
        """Setup: Login and navigate to Clothing dashboard."""
        PlaywrightHelper.login(page, base_url, 'admin_clothing', 'testpass123')
        page.goto(f"{base_url}/verticals/clothing/dashboard/")
        page.wait_for_load_state('networkidle')
        
        self.page = page
        self.base_url = base_url
    
    def test_clothing_admin_clicks_all_sidebar_links(self):
        """Test clicking all Clothing admin sidebar links."""
        links = PlaywrightHelper.find_sidebar_links(self.page)
        
        assert len(links) > 0, "No sidebar links found"
        
        errors = []
        for link_text, link_href in links:
            success, error = PlaywrightHelper.click_link_and_verify(
                self.page, link_text, link_href
            )
            
            if not success:
                errors.append(f"{link_text} ({link_href}): {error}")
                safe_filename = link_text.replace(' ', '_').replace('/', '_')
                PlaywrightHelper.take_screenshot_on_error(
                    self.page, f"clothing_admin_{safe_filename}_error.png"
                )
            
            self.page.goto(f"{self.base_url}/verticals/clothing/dashboard/")
            self.page.wait_for_load_state('networkidle')
        
        assert len(errors) == 0, f"Sidebar link errors:\n" + "\n".join(errors)


class TestAdminSidebarClicksLiquor:
    """Test admin sidebar clicks for Liquor vertical."""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page, base_url: str):
        """Setup: Login and navigate to Liquor dashboard."""
        PlaywrightHelper.login(page, base_url, 'admin_liquor', 'testpass123')
        page.goto(f"{base_url}/verticals/liquor/dashboard/")
        page.wait_for_load_state('networkidle')
        
        self.page = page
        self.base_url = base_url
    
    def test_liquor_admin_clicks_all_sidebar_links(self):
        """Test clicking all Liquor admin sidebar links."""
        links = PlaywrightHelper.find_sidebar_links(self.page)
        
        assert len(links) > 0, "No sidebar links found"
        
        errors = []
        for link_text, link_href in links:
            success, error = PlaywrightHelper.click_link_and_verify(
                self.page, link_text, link_href
            )
            
            if not success:
                errors.append(f"{link_text} ({link_href}): {error}")
                safe_filename = link_text.replace(' ', '_').replace('/', '_')
                PlaywrightHelper.take_screenshot_on_error(
                    self.page, f"liquor_admin_{safe_filename}_error.png"
                )
            
            self.page.goto(f"{self.base_url}/verticals/liquor/dashboard/")
            self.page.wait_for_load_state('networkidle')
        
        assert len(errors) == 0, f"Sidebar link errors:\n" + "\n".join(errors)


class TestAdminSidebarClicksGym:
    """Test admin sidebar clicks for Gym vertical."""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page, base_url: str):
        """Setup: Login and navigate to Gym dashboard."""
        PlaywrightHelper.login(page, base_url, 'admin_gym', 'testpass123')
        page.goto(f"{base_url}/verticals/gym/dashboard/")
        page.wait_for_load_state('networkidle')
        
        self.page = page
        self.base_url = base_url
    
    def test_gym_admin_clicks_all_sidebar_links(self):
        """Test clicking all Gym admin sidebar links."""
        links = PlaywrightHelper.find_sidebar_links(self.page)
        
        assert len(links) > 0, "No sidebar links found"
        
        errors = []
        for link_text, link_href in links:
            success, error = PlaywrightHelper.click_link_and_verify(
                self.page, link_text, link_href
            )
            
            if not success:
                errors.append(f"{link_text} ({link_href}): {error}")
                safe_filename = link_text.replace(' ', '_').replace('/', '_')
                PlaywrightHelper.take_screenshot_on_error(
                    self.page, f"gym_admin_{safe_filename}_error.png"
                )
            
            self.page.goto(f"{self.base_url}/verticals/gym/dashboard/")
            self.page.wait_for_load_state('networkidle')
        
        assert len(errors) == 0, f"Sidebar link errors:\n" + "\n".join(errors)


class TestHQSidebarClicks:
    """Test HQ platform sidebar clicks."""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page, base_url: str):
        """Setup: Login as superuser and navigate to HQ."""
        PlaywrightHelper.login(page, base_url, 'superuser', 'testpass123')
        page.goto(f"{base_url}/hq/")
        page.wait_for_load_state('networkidle')
        
        self.page = page
        self.base_url = base_url
    
    def test_hq_clicks_all_sidebar_links(self):
        """Test clicking all HQ sidebar links."""
        links = PlaywrightHelper.find_sidebar_links(self.page)
        
        # HQ might have fewer links if modules aren't installed
        if len(links) == 0:
            pytest.skip("No HQ sidebar links found (HQ may not be fully configured)")
        
        errors = []
        for link_text, link_href in links:
            success, error = PlaywrightHelper.click_link_and_verify(
                self.page, link_text, link_href
            )
            
            if not success:
                # For HQ, we're more lenient (404s are okay)
                if '404' not in error:
                    errors.append(f"{link_text} ({link_href}): {error}")
                    safe_filename = link_text.replace(' ', '_').replace('/', '_')
                    PlaywrightHelper.take_screenshot_on_error(
                        self.page, f"hq_{safe_filename}_error.png"
                    )
            
            self.page.goto(f"{self.base_url}/hq/")
            self.page.wait_for_load_state('networkidle')
        
        assert len(errors) == 0, f"HQ sidebar link errors:\n" + "\n".join(errors)

