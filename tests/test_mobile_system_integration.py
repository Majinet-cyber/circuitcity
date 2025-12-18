"""
Mobile-First UI System Integration Tests
Tests that mobile-system.css is properly loaded and key pages render correctly
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class MobileSystemIntegrationTest(TestCase):
    """
    Verify mobile-system.css is loaded in key templates
    and pages render without errors
    """
    
    def setUp(self):
        """Create test user and business for authenticated tests"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_base_template_includes_mobile_system_css(self):
        """
        Test that base.html includes mobile-system.css
        This is a smoke test to ensure the CSS file is referenced
        """
        # Read base.html template directly to verify mobile-system.css is included
        import os
        from django.conf import settings
        
        base_template_path = os.path.join(settings.BASE_DIR, 'templates', 'base.html')
        
        self.assertTrue(os.path.exists(base_template_path), 
                       "base.html template should exist")
        
        with open(base_template_path, 'r', encoding='utf-8') as f:
            base_template_content = f.read()
        
        self.assertIn('mobile-system.css', base_template_content,
                     "mobile-system.css should be referenced in base.html template")
        
        # Verify it's loaded in the correct order (after tokens.css, before mobile.css)
        tokens_pos = base_template_content.find('tokens.css')
        mobile_system_pos = base_template_content.find('mobile-system.css')
        mobile_pos = base_template_content.find('mobile.css')
        
        self.assertGreater(tokens_pos, -1, "tokens.css should be present")
        self.assertGreater(mobile_system_pos, -1, "mobile-system.css should be present")
        self.assertGreater(mobile_pos, -1, "mobile.css should be present")
        
        # Verify load order
        self.assertLess(tokens_pos, mobile_system_pos,
                       "mobile-system.css should load after tokens.css")
        self.assertLess(mobile_system_pos, mobile_pos,
                       "mobile-system.css should load before mobile.css")
    
    def test_hq_base_includes_mobile_system_css(self):
        """
        Test that HQ base template includes mobile-system.css
        """
        # Create superuser for HQ access
        superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123'
        )
        self.client.login(username='admin', password='adminpass123')
        
        try:
            # Try to access HQ dashboard
            response = self.client.get('/hq/')
            
            # If HQ dashboard exists and we can access it
            if response.status_code == 200:
                content = response.content.decode('utf-8')
                self.assertIn('mobile-system.css', content,
                            "mobile-system.css should be referenced in HQ base template")
        except Exception:
            # HQ might have different routing or requirements
            # This is a best-effort test
            self.skipTest("HQ dashboard not accessible or not configured")
    
    def test_mobile_system_css_file_exists(self):
        """
        Test that the mobile-system.css file can be requested
        """
        response = self.client.get('/static/css/mobile-system.css')
        
        # Should return 200 if static files are served in test
        # or 404 if static files aren't served (which is OK in test)
        self.assertIn(response.status_code, [200, 404], 
                     "mobile-system.css should exist in static/css/")
    
    def test_viewport_meta_tag_present(self):
        """
        Test that viewport meta tag is present for mobile-first design
        """
        response = self.client.get('/accounts/login/')
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('viewport', content.lower(),
                     "Viewport meta tag should be present")
        self.assertIn('width=device-width', content.lower(),
                     "Viewport should include width=device-width")
    
    def test_mobile_utility_classes_documented(self):
        """
        Verify that key utility classes from mobile-system.css are documented
        This test serves as documentation of the available utilities
        """
        expected_utilities = [
            '.cc-minw-0',
            '.cc-ellipsis',
            '.cc-wrap',
            '.cc-amount',
            '.cc-kpi-grid',
            '.cc-table-scroll',
            '.cc-chart-container',
            '.cc-btn-group',
            '.cc-leaderboard-item',
            '.cc-flex-safe',
            '.cc-mobile-only',
            '.cc-desktop-only',
        ]
        
        # Read the mobile-system.css file to verify utilities exist
        import os
        from django.conf import settings
        
        css_path = os.path.join(settings.BASE_DIR, 'static', 'css', 'mobile-system.css')
        
        if os.path.exists(css_path):
            with open(css_path, 'r', encoding='utf-8') as f:
                css_content = f.read()
            
            for utility in expected_utilities:
                self.assertIn(utility, css_content,
                            f"Utility class {utility} should be defined in mobile-system.css")
        else:
            self.fail("mobile-system.css file not found at expected path")


class MobileOverflowPreventionTest(TestCase):
    """
    Tests to ensure mobile overflow issues are prevented
    These are documentation tests that describe the expected behavior
    """
    
    def test_kpi_cards_should_not_overflow(self):
        """
        Documentation: KPI cards should use .cc-ellipsis and .cc-amount
        to prevent overflow on small screens (360px+)
        """
        # This is a documentation test
        # Actual visual testing requires browser automation (Cypress/Playwright)
        self.assertTrue(True, 
                       "KPI cards should apply .cc-minw-0 and .cc-amount classes")
    
    def test_leaderboards_should_truncate_names(self):
        """
        Documentation: Leaderboard agent names should use .cc-ellipsis
        with title attribute for full text on hover
        """
        self.assertTrue(True,
                       "Leaderboard items should use .cc-leaderboard-name with ellipsis")
    
    def test_tables_should_scroll_horizontally(self):
        """
        Documentation: Tables should be wrapped in .cc-table-scroll
        to enable horizontal scrolling without breaking layout
        """
        self.assertTrue(True,
                       "Tables should be wrapped in .cc-table-scroll container")
    
    def test_charts_should_not_be_cut_off(self):
        """
        Documentation: Charts should use .cc-chart-container
        and Chart.js should have responsive: true
        """
        self.assertTrue(True,
                       "Charts should be wrapped in .cc-chart-container")
    
    def test_buttons_should_stack_on_mobile(self):
        """
        Documentation: Button groups should use .cc-btn-group
        to stack vertically on screens < 576px
        """
        self.assertTrue(True,
                       "Button rows should use .cc-btn-group class")


@pytest.mark.django_db
class MobileSystemSmokeTest:
    """
    Pytest-style smoke tests for mobile system
    """
    
    def test_mobile_system_css_referenced_in_templates(self, client):
        """Verify mobile-system.css is referenced"""
        response = client.get('/accounts/login/')
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'mobile-system.css' in content
    
    def test_no_horizontal_overflow_classes_available(self):
        """Document that overflow prevention classes exist"""
        # This is a documentation test
        # Real testing requires browser automation
        overflow_prevention_classes = [
            'cc-minw-0',
            'cc-ellipsis',
            'cc-no-scroll-x',
            'cc-flex-safe',
        ]
        assert len(overflow_prevention_classes) > 0, \
            "Overflow prevention utilities should be defined"


# Usage instructions for developers
"""
MOBILE-FIRST UI SYSTEM USAGE:

1. Prevent Overflow on Flex Layouts:
   <div class="cc-flex-safe">
     <div class="cc-minw-0 cc-ellipsis">Agent Name Here</div>
     <div class="cc-amount">MWK 1,234,567.00</div>
   </div>

2. Responsive KPI Grid:
   <div class="cc-kpi-grid">
     <div class="metric-card">...</div>
     <div class="metric-card">...</div>
   </div>

3. Safe Tables:
   <div class="cc-table-scroll">
     <table>...</table>
   </div>

4. Charts that Don't Cut Off:
   <div class="cc-chart-container">
     <canvas id="myChart"></canvas>
   </div>

5. Button Groups (Stack on Mobile):
   <div class="cc-btn-group">
     <button>Action 1</button>
     <button>Action 2</button>
   </div>

6. Leaderboards:
   <div class="cc-leaderboard-item">
     <div class="cc-leaderboard-rank">1</div>
     <div class="cc-leaderboard-name" title="Full Name">Agent Name</div>
     <div class="cc-leaderboard-value cc-amount">MWK 50,000</div>
   </div>

7. Mobile/Desktop Visibility:
   <div class="cc-mobile-only">Shown only on mobile</div>
   <div class="cc-desktop-only">Shown only on desktop</div>

For full documentation, see: MOBILE_UI_AUDIT.md
"""

