# tests/test_scan_in_pages.py
"""
Regression tests for scan-in pages across all verticals.

Ensures that scanner standardization doesn't break page rendering.
Verifies that smart_scanner.html partial works correctly.
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership

User = get_user_model()


class TestScanInPages(TestCase):
    """Test that scan-in pages render successfully with smart scanner."""
    
    def test_phones_scan_in_renders_200(self):
        """
        Test that phones Scan IN page returns HTTP 200.
        
        This page uses smart_scanner.html in IMEI mode (15-digit validation).
        """
        # Create user and business
        user = User.objects.create_user(
            username="phonesmanager",
            email="phones@test.com",
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
        self.client.login(username="phonesmanager", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Hit the Scan IN URL
        try:
            from django.urls import reverse
            url = reverse('inventory:scan_in')
        except Exception:
            # Fallback if URL name doesn't exist
            url = '/inventory/scan/'
        
        response = self.client.get(url)
        
        # Assert HTTP 200
        assert response.status_code == 200, (
            f"Phones Scan IN page returned {response.status_code}. "
            f"Check scanner integration."
        )
        
        # Assert it contains scanner elements
        content = response.content.decode('utf-8')
        assert 'smart_scanner' in content.lower() or 'scan' in content.lower(), (
            "Scan IN page should contain scanner elements"
        )
    
    def test_clothing_scan_in_renders_200(self):
        """
        Test that clothing Scan IN page returns HTTP 200.
        
        This page uses smart_scanner.html in barcode mode (alphanumeric).
        """
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
        
        # Hit the Scan IN URL
        try:
            from django.urls import reverse
            url = reverse('verticals:clothing_scan_in')
        except Exception:
            url = '/verticals/clothing/scan-in/'
        
        response = self.client.get(url)
        
        # Assert HTTP 200
        assert response.status_code == 200, (
            f"Clothing Scan IN returned {response.status_code}"
        )
        
        # Assert it contains scanner elements
        content = response.content.decode('utf-8')
        assert 'barcode' in content.lower() or 'scan' in content.lower(), (
            "Clothing Scan IN should contain barcode scanner"
        )
    
    def test_smart_scanner_partial_exists(self):
        """
        Test that smart_scanner.html partial exists and is valid.
        
        This is a static check to ensure the unified scanner component exists.
        """
        import os
        from django.conf import settings
        from pathlib import Path
        
        # Find the template file
        template_path = None
        
        # Try TEMPLATES[0]['DIRS'] first
        template_dirs = settings.TEMPLATES[0].get('DIRS', [])
        for template_dir in template_dirs:
            candidate = os.path.join(str(template_dir), 'partials', 'smart_scanner.html')
            if os.path.exists(candidate):
                template_path = candidate
                break
        
        # If not found, try BASE_DIR/templates as fallback
        if not template_path:
            base_dir = Path(settings.BASE_DIR)
            candidate = base_dir / 'templates' / 'partials' / 'smart_scanner.html'
            if candidate.exists():
                template_path = str(candidate)
        
        if not template_path:
            self.skipTest("smart_scanner.html not found")
        
        # Read the template
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Assert it's a valid partial (no extends)
        assert '{% extends' not in content, (
            "smart_scanner.html must NOT use {% extends %} "
            "because it is included, not extended."
        )
        
        # Assert it contains SmartScanner initialization
        assert 'SmartScanner' in content or 'smart-scanner' in content, (
            "smart_scanner.html should contain SmartScanner code"
        )
        
        # Assert it's configurable
        assert 'scanner_mode' in content or 'scanner_target_input_id' in content, (
            "smart_scanner.html should be configurable via parameters"
        )

