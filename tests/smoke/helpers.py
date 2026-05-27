# tests/smoke/helpers.py
"""
Helper utilities for smoke tests.
"""
from typing import List, Dict, Tuple
from django.test import Client
from django.urls import reverse, NoReverseMatch

from inventory.utils_verticals import get_vertical_sidebar_items


class SidebarLinkExtractor:
    """Extract and validate sidebar links for testing."""
    
    @staticmethod
    def get_sidebar_links_for_vertical(business_kind: str, role: str = "manager") -> List[Dict]:
        """
        Get all sidebar links for a vertical and role.
        
        Args:
            business_kind: Vertical code (phones, pharmacy, clothing, liquor, gym)
            role: "manager" or "agent"
        
        Returns:
            List of sidebar items with URL, label, and metadata
        """
        all_items = get_vertical_sidebar_items(business_kind)
        
        # Filter by role
        if role == "agent":
            # Agents can only see items where require_manager is False
            items = [item for item in all_items if not item.get('require_manager', False)]
        else:
            # Managers see everything
            items = all_items
        
        return items
    
    @staticmethod
    def get_hq_sidebar_links() -> List[Dict]:
        """
        Get all HQ platform sidebar links.
        
        Returns:
            List of HQ sidebar items
        """
        # HQ sidebar links (manually defined since no function exists)
        return [
            {"key": "hq_home", "url": "hq:home", "label": "HQ Dashboard", "active_prefix": "/hq/"},
            {"key": "businesses", "url": "hq:businesses", "label": "Businesses", "active_prefix": "/hq/businesses"},
            {"key": "subscriptions", "url": "hq:subscriptions", "label": "Subscriptions", "active_prefix": "/hq/subscriptions"},
            {"key": "invoices", "url": "billing:invoices", "label": "Invoices", "active_prefix": "/billing/invoices"},
            {"key": "agents", "url": "hq:agents", "label": "Agents", "active_prefix": "/hq/agents"},
            {"key": "analytics", "url": "hq:hq_analytics", "label": "Analytics", "active_prefix": "/hq/analytics"},
            {"key": "tickets", "url": "support:hq_ticket_list", "label": "Tickets", "active_prefix": "/support/hq/"},
            {"key": "audit_logs", "url": "audit:log_list", "label": "Audit Logs", "active_prefix": "/audit/logs"},
            {"key": "django_admin", "url": "admin:index", "label": "Django Admin", "active_prefix": "/admin/"},
        ]
    
    @staticmethod
    def resolve_sidebar_urls(items: List[Dict]) -> List[Tuple[str, str, str]]:
        """
        Resolve sidebar item URLs to actual paths.
        
        Args:
            items: List of sidebar items with 'url' and 'label' keys
        
        Returns:
            List of tuples: (label, resolved_url, error_message)
            error_message is None if URL resolved successfully
        """
        resolved = []
        
        for item in items:
            label = item.get('label', 'Unknown')
            url = item.get('url', '')
            
            # Skip javascript: and # links
            if not url or url.startswith('#') or url.startswith('javascript:'):
                continue
            
            # If URL starts with /, it's already a path
            if url.startswith('/'):
                resolved.append((label, url, None))
                continue
            
            # Try to reverse named URL
            try:
                resolved_url = reverse(url)
                resolved.append((label, resolved_url, None))
            except NoReverseMatch as e:
                resolved.append((label, None, f"NoReverseMatch: {str(e)}"))
            except Exception as e:
                resolved.append((label, None, f"Error: {str(e)}"))
        
        return resolved
    
    @staticmethod
    def test_url_loads(client: Client, url: str) -> Tuple[int, str]:
        """
        Test if a URL loads successfully.
        
        Args:
            client: Django test client
            url: URL to test
        
        Returns:
            Tuple of (status_code, error_message)
            error_message is None if page loaded successfully
        """
        try:
            response = client.get(url, follow=True)
            status = response.status_code
            
            # Check for error pages
            if status == 500:
                return (status, "Server Error (500)")
            
            if status >= 400:
                return (status, f"HTTP {status} error")
            
            # Check response content for error indicators
            content = response.content.decode('utf-8', errors='ignore')
            
            if 'Server Error (500)' in content:
                return (status, "Page contains 'Server Error (500)' text")
            
            if 'NoReverseMatch' in content:
                return (status, "Page contains 'NoReverseMatch' error")
            
            if 'TemplateDoesNotExist' in content:
                return (status, "Template missing")
            
            return (status, None)
            
        except Exception as e:
            return (None, f"Exception: {str(e)}")


class SessionHelper:
    """Helper for managing test client sessions."""
    
    @staticmethod
    def set_active_business(client: Client, business):
        """Set active business in client session."""
        session = client.session
        session['active_business_id'] = business.id
        session['biz_id'] = business.id
        session['business_id'] = business.id
        session.save()
    
    @staticmethod
    def set_active_location(client: Client, location):
        """Set active location in client session."""
        session = client.session
        session['active_location_id'] = location.id
        session['location_id'] = location.id
        session.save()


__all__ = ['SidebarLinkExtractor', 'SessionHelper']

