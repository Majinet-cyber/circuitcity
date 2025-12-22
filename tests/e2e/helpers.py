# tests/e2e/helpers.py
"""
Helper utilities for Playwright E2E tests.
"""
from typing import List, Tuple
from playwright.sync_api import Page, Locator


class PlaywrightHelper:
    """Helper class for common Playwright operations."""
    
    @staticmethod
    def login(page: Page, base_url: str, username: str, password: str):
        """
        Login to the application.
        
        Args:
            page: Playwright page object
            base_url: Base URL of the application
            username: Username to login with
            password: Password for the user
        """
        # Navigate to login page
        page.goto(f"{base_url}/login/")
        
        # Fill login form
        page.fill('input[name="username"]', username)
        page.fill('input[name="password"]', password)
        
        # Click login button
        page.click('button[type="submit"]')
        
        # Wait for navigation after login
        page.wait_for_load_state('networkidle', timeout=10000)
    
    @staticmethod
    def find_sidebar_links(page: Page) -> List[Tuple[str, str]]:
        """
        Find all sidebar navigation links.
        
        Args:
            page: Playwright page object
        
        Returns:
            List of tuples: (link_text, link_href)
        """
        # Wait for sidebar to be visible
        page.wait_for_selector('.cc-sidebar, #hqSidebar, aside', timeout=5000)
        
        # Find all sidebar links
        sidebar_links = page.locator('.cc-sidebar a, #hqSidebar a, aside a').all()
        
        links = []
        for link in sidebar_links:
            try:
                href = link.get_attribute('href')
                text = link.inner_text().strip()
                
                # Skip empty links, javascript:, and # links
                if not href or href.startswith('#') or href.startswith('javascript:'):
                    continue
                
                # Skip logout link (we'll handle it separately)
                if 'logout' in href.lower() or 'logout' in text.lower():
                    continue
                
                links.append((text, href))
            except:
                # Skip links that can't be accessed
                continue
        
        return links
    
    @staticmethod
    def click_link_and_verify(page: Page, link_text: str, link_href: str) -> Tuple[bool, str]:
        """
        Click a link and verify the page loads without errors.
        
        Args:
            page: Playwright page object
            link_text: Text of the link to click
            link_href: Href of the link
        
        Returns:
            Tuple of (success: bool, error_message: str)
        """
        try:
            # Click the link
            page.click(f'a[href="{link_href}"]', timeout=5000)
            
            # Wait for navigation
            page.wait_for_load_state('networkidle', timeout=10000)
            
            # Check for error indicators
            page_content = page.content()
            
            if 'Server Error (500)' in page_content:
                return (False, "Page contains 'Server Error (500)'")
            
            if 'NoReverseMatch' in page_content:
                return (False, "Page contains 'NoReverseMatch' error")
            
            if 'TemplateDoesNotExist' in page_content:
                return (False, "Template missing")
            
            # Check HTTP status (if available)
            # Note: We can't directly get HTTP status in Playwright after navigation,
            # but we can check for error pages
            
            return (True, None)
            
        except Exception as e:
            return (False, f"Exception: {str(e)}")
    
    @staticmethod
    def take_screenshot_on_error(page: Page, filename: str):
        """
        Take a screenshot for debugging.
        
        Args:
            page: Playwright page object
            filename: Filename to save screenshot (will be saved in screenshots/ folder)
        """
        import os
        os.makedirs('screenshots', exist_ok=True)
        page.screenshot(path=f'screenshots/{filename}')
    
    @staticmethod
    def set_active_business(page: Page, base_url: str, business_id: int):
        """
        Set active business in session via JavaScript (if needed).
        
        Args:
            page: Playwright page object
            base_url: Base URL
            business_id: Business ID to set
        """
        # This might not be necessary if login handles it,
        # but we can set it via a session endpoint if available
        pass


__all__ = ['PlaywrightHelper']

