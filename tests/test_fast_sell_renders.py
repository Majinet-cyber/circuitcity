# tests/test_fast_sell_renders.py
"""
Regression test to ensure Fast Sell pages render without recursion errors.

This test prevents the template recursion bug where _fast_sell_universal.html
was incorrectly using {% extends %} when it should only be included.
"""
import os
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings

from tenants.models import Business, Membership

User = get_user_model()


class TestFastSellRendering(TestCase):
    """Test that Fast Sell pages render successfully without recursion."""
    
    def test_phones_fast_sell_renders_200(self):
        """
        Test that phones Fast Sell page returns HTTP 200.
        
        This is a critical regression test for the template recursion bug
        where _fast_sell_universal.html had {% extends "base.html" %} 
        causing infinite recursion when included by phones/fast_sell.html.
        """
        # Create user and business
        user = User.objects.create_user(
            username="testmanager",
            email="manager@test.com",
            password="testpass123"
        )
        
        business = Business.objects.create(
            name="Test Phone Shop",
            slug="test-phone-shop",
            business_kind="phones"
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Login
        self.client.login(username="testmanager", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Hit the Fast Sell URL
        try:
            url = reverse('inventory:phones_fast_sell')
        except Exception:
            # Fallback if URL name doesn't exist
            url = '/inventory/phones/fast-sell/'
        
        response = self.client.get(url)
        
        # Assert HTTP 200 (not 500 from recursion)
        assert response.status_code == 200, (
            f"Fast Sell page returned {response.status_code}. "
            f"Check for template recursion in _fast_sell_universal.html"
        )
        
        # Assert it contains expected content
        content = response.content.decode('utf-8')
        assert "Fast Sell" in content or "fast-sell" in content.lower()
    
    def test_clothing_fast_sell_renders_200(self):
        """Test that clothing Fast Sell page returns HTTP 200."""
        # Create user and business
        user = User.objects.create_user(
            username="clothingmgr",
            email="clothing@test.com",
            password="testpass123"
        )
        
        business = Business.objects.create(
            name="Test Clothing Store",
            slug="test-clothing-store",
            business_kind="clothing"
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Login
        self.client.login(username="clothingmgr", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Hit the Fast Sell URL
        try:
            url = reverse('verticals:clothing_fast_sell')
        except Exception:
            url = '/verticals/clothing/fast-sell/'
        
        response = self.client.get(url)
        
        # Assert HTTP 200
        assert response.status_code == 200, (
            f"Clothing Fast Sell returned {response.status_code}"
        )
        
        # Assert it contains expected content
        content = response.content.decode('utf-8')
        assert "Fast Sell" in content
    
    def test_pharmacy_fast_sell_renders_200(self):
        """Test that pharmacy Fast Sell page returns HTTP 200."""
        # Create user and business
        user = User.objects.create_user(
            username="pharmacymgr",
            email="pharmacy@test.com",
            password="testpass123"
        )
        
        business = Business.objects.create(
            name="Test Pharmacy",
            slug="test-pharmacy",
            business_kind="pharmacy"
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Login
        self.client.login(username="pharmacymgr", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Hit the Fast Sell URL
        try:
            url = reverse('verticals:pharmacy_fast_sell')
        except Exception:
            url = '/verticals/pharmacy/fast-sell/'
        
        response = self.client.get(url)
        
        # Assert HTTP 200
        assert response.status_code == 200, (
            f"Pharmacy Fast Sell returned {response.status_code}"
        )
        
        # Assert it contains expected content
        content = response.content.decode('utf-8')
        assert "Fast Sell" in content
    
    def test_template_no_recursion_pattern(self):
        """
        Test that _fast_sell_universal.html does not contain {% extends %}.
        
        This is a static check to prevent the recursion bug from returning.
        Partials that are included must NOT extend base templates.
        """
        # Find the template file
        template_path = None
        
        # Try TEMPLATES[0]['DIRS'] first
        template_dirs = settings.TEMPLATES[0].get('DIRS', [])
        for template_dir in template_dirs:
            candidate = os.path.join(str(template_dir), 'verticals', '_fast_sell_universal.html')
            if os.path.exists(candidate):
                template_path = candidate
                break
        
        # If not found, try BASE_DIR/templates as fallback
        if not template_path:
            from pathlib import Path
            base_dir = Path(settings.BASE_DIR)
            candidate = base_dir / 'templates' / 'verticals' / '_fast_sell_universal.html'
            if candidate.exists():
                template_path = str(candidate)
        
        if not template_path:
            self.skipTest("_fast_sell_universal.html not found")
        
        # Read the template
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remove comments before checking for {% extends %}
        import re
        # Remove {# ... #} comments
        content_no_comments = re.sub(r'\{#.*?#\}', '', content, flags=re.DOTALL)
        
        # Assert it does NOT contain {% extends %} (outside of comments)
        assert '{% extends' not in content_no_comments, (
            "_fast_sell_universal.html must NOT use {% extends %} "
            "because it is included, not extended. This causes recursion."
        )
        
        # Assert it contains the warning comment
        assert 'DO NOT add {% extends %}' in content or 'meant to be included' in content, (
            "_fast_sell_universal.html should have a comment warning against {% extends %}"
        )

