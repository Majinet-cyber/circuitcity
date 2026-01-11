# tests/e2e/test_sidebar_clicks_agent.py
"""
Playwright E2E smoke tests for AGENT sidebar clicks.

These tests simulate real agent user interactions:
- Login as agent
- Click every visible sidebar link (agent can see)
- Verify each page loads without errors
- Verify agent cannot access manager-only pages
- Screenshot failures for debugging

NOTE: These tests require the Django development server to be running.
Run with: python manage.py runserver (in separate terminal)
Then: pytest tests/e2e/test_sidebar_clicks_agent.py
"""
import pytest
from playwright.sync_api import Page

from tests.e2e.helpers import PlaywrightHelper


# Mark all tests in this module as requiring the Django DB and being E2E tests
pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


class TestAgentSidebarClicksPhones:
    """Test agent sidebar clicks for Phones vertical."""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page, base_url: str):
        """Setup: Login as agent."""
        PlaywrightHelper.login(page, base_url, 'agent_phones', 'testpass123')
        page.goto(f"{base_url}/inventory/verticals/phones/dashboard/")
        page.wait_for_load_state('networkidle')
        
        self.page = page
        self.base_url = base_url
    
    def test_phones_agent_clicks_all_visible_sidebar_links(self):
        """Test clicking all Phones agent visible sidebar links."""
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
                    self.page, f"phones_agent_{safe_filename}_error.png"
                )
            
            self.page.goto(f"{self.base_url}/inventory/verticals/phones/dashboard/")
            self.page.wait_for_load_state('networkidle')
        
        assert len(errors) == 0, f"Agent sidebar link errors:\n" + "\n".join(errors)
    
    def test_phones_agent_cannot_access_manager_pages(self):
        """Test that agent cannot access manager-only pages."""
        manager_urls = [
            ('/reports/', 'Reports'),
            ('/wallet/admin/', 'Admin Wallet'),
            ('/tenants/manager/agents/', 'Agents'),
        ]
        
        for url, label in manager_urls:
            self.page.goto(f"{self.base_url}{url}")
            self.page.wait_for_load_state('networkidle')
            
            # Should not show the page content or should redirect
            content = self.page.content()
            
            # Check if redirected to login or access denied
            current_url = self.page.url
            assert '/login' in current_url or '403' in content or 'Access Denied' in content, \
                f"Agent should not access {label} ({url})"


class TestAgentSidebarClicksPharmacy:
    """Test agent sidebar clicks for Pharmacy vertical."""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page, base_url: str):
        """Setup: Login as agent."""
        PlaywrightHelper.login(page, base_url, 'agent_pharmacy', 'testpass123')
        page.goto(f"{base_url}/dashboard/")
        page.wait_for_load_state('networkidle')
        
        self.page = page
        self.base_url = base_url
    
    def test_pharmacy_agent_clicks_all_visible_sidebar_links(self):
        """Test clicking all Pharmacy agent visible sidebar links."""
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
                    self.page, f"pharmacy_agent_{safe_filename}_error.png"
                )
            
            self.page.goto(f"{self.base_url}/dashboard/")
            self.page.wait_for_load_state('networkidle')
        
        assert len(errors) == 0, f"Agent sidebar link errors:\n" + "\n".join(errors)


class TestAgentSidebarClicksClothing:
    """Test agent sidebar clicks for Clothing vertical."""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page, base_url: str):
        """Setup: Login as agent."""
        PlaywrightHelper.login(page, base_url, 'agent_clothing', 'testpass123')
        page.goto(f"{base_url}/verticals/clothing/dashboard/")
        page.wait_for_load_state('networkidle')
        
        self.page = page
        self.base_url = base_url
    
    def test_clothing_agent_clicks_all_visible_sidebar_links(self):
        """Test clicking all Clothing agent visible sidebar links."""
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
                    self.page, f"clothing_agent_{safe_filename}_error.png"
                )
            
            self.page.goto(f"{self.base_url}/verticals/clothing/dashboard/")
            self.page.wait_for_load_state('networkidle')
        
        assert len(errors) == 0, f"Agent sidebar link errors:\n" + "\n".join(errors)


class TestAgentSidebarClicksLiquor:
    """Test agent sidebar clicks for Liquor vertical."""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page, base_url: str):
        """Setup: Login as agent."""
        PlaywrightHelper.login(page, base_url, 'agent_liquor', 'testpass123')
        page.goto(f"{self.base_url}/verticals/liquor/dashboard/")
        page.wait_for_load_state('networkidle')
        
        self.page = page
        self.base_url = base_url
    
    def test_liquor_agent_clicks_all_visible_sidebar_links(self):
        """Test clicking all Liquor agent visible sidebar links."""
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
                    self.page, f"liquor_agent_{safe_filename}_error.png"
                )
            
            self.page.goto(f"{self.base_url}/verticals/liquor/dashboard/")
            self.page.wait_for_load_state('networkidle')
        
        assert len(errors) == 0, f"Agent sidebar link errors:\n" + "\n".join(errors)


class TestAgentSidebarClicksGym:
    """Test agent sidebar clicks for Gym vertical."""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page, base_url: str):
        """Setup: Login as agent (trainer)."""
        PlaywrightHelper.login(page, base_url, 'agent_gym', 'testpass123')
        page.goto(f"{base_url}/verticals/gym/dashboard/")
        page.wait_for_load_state('networkidle')
        
        self.page = page
        self.base_url = base_url
    
    def test_gym_agent_clicks_all_visible_sidebar_links(self):
        """Test clicking all Gym agent (trainer) visible sidebar links."""
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
                    self.page, f"gym_agent_{safe_filename}_error.png"
                )
            
            self.page.goto(f"{base_url}/verticals/gym/dashboard/")
            self.page.wait_for_load_state('networkidle')
        
        assert len(errors) == 0, f"Agent sidebar link errors:\n" + "\n".join(errors)

