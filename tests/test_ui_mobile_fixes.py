"""
Tests for UI mobile fixes - ensures no HTTP 500 and key sections render correctly.
Tests A) Global UI fixes across dashboards.
"""
from __future__ import annotations

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind
from inventory.models import Location

User = get_user_model()


class MobileUIRenderTest(TestCase):
    """
    Test that key dashboards render correctly (HTTP 200) with mobile-safe CSS.
    These tests don't pixel-test, just ensure safe rendering and presence of key sections.
    """
    
    def setUp(self):
        """Create test user, business, and location"""
        self.user = User.objects.create_user(
            username="testmanager",
            email="manager@test.com",
            password="testpass123",
            is_active=True
        )
        
        self.business = Business.objects.create(
            name="Test Business",
            kind=BusinessKind.PHONES,
            currency="MWK"
        )
        
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER"
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store"
        )
        
        self.client = Client()
        self.client.login(username="testmanager", password="testpass123")
        self.client.cookies['active_business'] = str(self.business.id)
    
    def test_phones_dashboard_renders(self):
        """Test phones dashboard renders with HTTP 200 and contains key sections"""
        response = self.client.get('/verticals/phones/dashboard/')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dashboard')
        # Check for chart-wrap class (mobile-safe chart container)
        self.assertContains(response, 'chart-wrap')
    
    def test_clothing_dashboard_renders(self):
        """Test clothing dashboard renders with HTTP 200"""
        # Update business kind
        self.business.kind = BusinessKind.CLOTHING
        self.business.save()
        
        response = self.client.get('/verticals/clothing/dashboard/')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dashboard')
        # Check for bar chart (changed from line to bar)
        self.assertContains(response, "type: 'bar'")
    
    def test_liquor_dashboard_renders(self):
        """Test liquor dashboard renders with HTTP 200 (no shift required)"""
        # Update business kind
        self.business.kind = BusinessKind.LIQUOR
        self.business.save()
        
        response = self.client.get('/verticals/liquor/dashboard/')
        
        # Should not 500 even without active shift
        self.assertIn(response.status_code, [200, 302])  # 302 if redirecting to start shift
    
    def test_phones_reports_exists(self):
        """Test phones reports route exists and returns 200 (not 404)"""
        self.business.kind = BusinessKind.PHONES
        self.business.save()
        
        response = self.client.get('/verticals/phones/reports/')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reports')
    
    def test_css_utilities_loaded(self):
        """Test that mobile CSS utilities are loaded in base CSS"""
        with open('static/css/polish.css', 'r') as f:
            css_content = f.read()
        
        # Check for key mobile-first utilities
        self.assertIn('.shrink-0', css_content)
        self.assertIn('.truncate-1', css_content)
        self.assertIn('.wrap-anywhere', css_content)
        self.assertIn('.chart-wrap', css_content)
        self.assertIn('-webkit-text-size-adjust', css_content)


class SettingsProductionSafetyTest(TestCase):
    """Test settings.py has Render PostgreSQL guard"""
    
    def test_render_postgres_guard_exists(self):
        """Ensure settings.py has guard against SQLite on Render"""
        with open('cc/settings.py', 'r') as f:
            settings_content = f.read()
        
        self.assertIn('RENDER', settings_content)
        self.assertIn('ImproperlyConfigured', settings_content)
        self.assertIn('SQLite is not allowed on Render', settings_content)


class ClothingCategoriesTest(TestCase):
    """Test clothing categories were expanded"""
    
    def test_clothing_categories_expanded(self):
        """Ensure new categories (Belts, Perfumes, Jeans, Shorts, Bags) exist"""
        from inventory.verticals.clothing import CLOTHING_CATEGORIES
        
        category_keys = [c[0] for c in CLOTHING_CATEGORIES]
        
        self.assertIn('belts', category_keys)
        self.assertIn('perfumes', category_keys)
        self.assertIn('jeans', category_keys)
        self.assertIn('shorts', category_keys)
        self.assertIn('handbags', category_keys)
        self.assertIn('schoolbags', category_keys)


class LiquorShiftAutoStartTest(TestCase):
    """Test liquor auto-shift functionality"""
    
    def setUp(self):
        """Create test user and business"""
        self.user = User.objects.create_user(
            username="barman",
            email="barman@test.com",
            password="testpass123",
            is_active=True
        )
        
        self.business = Business.objects.create(
            name="Bar Business",
            kind=BusinessKind.LIQUOR,
            currency="MWK"
        )
        
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role="AGENT"
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name="Main Bar"
        )
    
    def test_get_or_start_shift_function_exists(self):
        """Ensure get_or_start_active_shift function exists in liquor views"""
        from inventory.views_liquor import get_or_start_active_shift
        
        # Function exists and is callable
        self.assertTrue(callable(get_or_start_active_shift))
    
    def test_sell_liquor_doesnt_crash_without_shift(self):
        """Test that sell_liquor view doesn't crash when no shift exists"""
        from django.test import Client
        
        client = Client()
        client.login(username="barman", password="testpass123")
        client.cookies['active_business'] = str(self.business.id)
        
        # Should not 500 - either shows form or creates shift automatically
        response = client.get('/liquor/sell/')
        self.assertIn(response.status_code, [200, 302])


class PhonesSalesTrendTest(TestCase):
    """Test phones sales trend is a line chart and never empty"""
    
    def setUp(self):
        """Create test user and business"""
        self.user = User.objects.create_user(
            username="phonemanager",
            email="phone@test.com",
            password="testpass123",
            is_active=True
        )
        
        self.business = Business.objects.create(
            name="Phone Store",
            kind=BusinessKind.PHONES,
            currency="MWK"
        )
        
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER"
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store"
        )
        
        self.client = Client()
        self.client.login(username="phonemanager", password="testpass123")
        self.client.cookies['active_business'] = str(self.business.id)
    
    def test_phones_dashboard_has_line_chart(self):
        """Test phones dashboard uses line chart (not bar)"""
        response = self.client.get('/verticals/phones/dashboard/')
        
        self.assertEqual(response.status_code, 200)
        # Check for line chart type in JavaScript
        self.assertContains(response, "type: 'line'")
    
    def test_phones_dashboard_chart_never_empty(self):
        """Test phones dashboard chart always renders (even with no data)"""
        response = self.client.get('/verticals/phones/dashboard/')
        
        self.assertEqual(response.status_code, 200)
        # Chart should always render comment present
        self.assertContains(response, 'Sales Trend')
        self.assertContains(response, 'salesTrendChart')


class MoneyFormatterTest(TestCase):
    """Test currency formatting is consistent"""
    
    def test_money_filter_formats_correctly(self):
        """Test money template filter formats with proper separators"""
        from inventory.templatetags.money import money_filter
        from decimal import Decimal
        
        # Test thousands separator
        result = money_filter(Decimal('12345'), 'MWK')
        self.assertIn('12,345', result)
        self.assertIn('MWK', result)
        
        # Test decimal handling
        result = money_filter(Decimal('12345.00'), 'MWK')
        # Should drop .00 for cleaner display
        self.assertIn('12,345', result)
        self.assertNotIn('.00', result)
    
    def test_money_filter_handles_none(self):
        """Test money filter handles None gracefully"""
        from inventory.templatetags.money import money_filter
        
        result = money_filter(None, 'MWK')
        self.assertEqual(result, 'MWK 0')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

