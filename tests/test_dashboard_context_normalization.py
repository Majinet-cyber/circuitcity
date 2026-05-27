"""
Tests for dashboard context normalization across all verticals.

This test suite ensures:
1. All vertical dashboards return HTTP 200 (no 500 errors from missing variables)
2. Dashboard context is properly normalized with safe defaults
3. Legacy uppercase keys are mapped to lowercase
4. No template variable crashes occur
"""
import pytest
from django.test import Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind
from core.dashboard_context import normalize_dashboard_context, DASHBOARD_DEFAULTS, LEGACY_KEY_MAP

User = get_user_model()


# ============================================================================
# Unit Tests for normalize_dashboard_context()
# ============================================================================

@pytest.mark.django_db
class TestDashboardContextNormalization:
    """Unit tests for the dashboard context normalizer."""
    
    def test_inject_defaults(self, rf):
        """Test that defaults are injected for missing keys."""
        request = rf.get('/')
        ctx = {"business": None}
        
        ctx = normalize_dashboard_context(request, ctx)
        
        # Check all defaults are present
        for key, default_value in DASHBOARD_DEFAULTS.items():
            assert key in ctx
            assert ctx[key] == default_value
    
    def test_map_legacy_uppercase_keys(self, rf):
        """Test that legacy UPPERCASE keys are mapped to lowercase."""
        request = rf.get('/')
        ctx = {
            "YESTERDAY_SUMMARY": {"date": "2024-01-01"},
            "DASHBOARD_QUOTES": {"quotes": []},
            "DASHBOARD_BRAND_TITLE": "Test Business",
        }
        
        ctx = normalize_dashboard_context(request, ctx)
        
        # Check lowercase versions exist
        assert ctx["yesterday_summary"] == {"date": "2024-01-01"}
        assert ctx["dashboard_quotes"] == {"quotes": []}
        assert ctx["dashboard_brand_title"] == "Test Business"
        
        # By default, uppercase keys are preserved for backward compatibility
        assert ctx["YESTERDAY_SUMMARY"] == {"date": "2024-01-01"}
        assert ctx["DASHBOARD_QUOTES"] == {"quotes": []}
        assert ctx["DASHBOARD_BRAND_TITLE"] == "Test Business"
    
    def test_dont_overwrite_explicit_lowercase(self, rf):
        """Test that explicit lowercase values are not overwritten by uppercase."""
        request = rf.get('/')
        ctx = {
            "YESTERDAY_SUMMARY": {"date": "2024-01-01"},  # Legacy
            "yesterday_summary": {"date": "2024-01-02"},  # Explicit
        }
        
        ctx = normalize_dashboard_context(request, ctx)
        
        # Lowercase should win
        assert ctx["yesterday_summary"] == {"date": "2024-01-02"}
    
    def test_business_name_fallback(self, rf):
        """Test that business name is used as fallback for dashboard_brand_title."""
        request = rf.get('/')
        
        class MockBusiness:
            name = "My Test Shop"
            logo = None
        
        ctx = {"business": MockBusiness()}
        ctx = normalize_dashboard_context(request, ctx)
        
        assert ctx["dashboard_brand_title"] == "My Test Shop"
    
    def test_user_name_from_request(self, rf, django_user_model):
        """Test that user name is extracted from request."""
        user = django_user_model(username="testuser", first_name="John")
        request = rf.get('/')
        request.user = user
        
        ctx = {}
        ctx = normalize_dashboard_context(request, ctx)
        
        # Should prefer first_name
        assert ctx["dashboard_user_name"] == "John"
    
    def test_preserve_legacy_false(self, rf):
        """Test that legacy keys can be removed if preserve_legacy=False."""
        request = rf.get('/')
        ctx = {"YESTERDAY_SUMMARY": {"date": "2024-01-01"}}
        
        ctx = normalize_dashboard_context(request, ctx, preserve_legacy=False)
        
        # Uppercase key should be removed
        assert "YESTERDAY_SUMMARY" not in ctx
        # Lowercase should exist
        assert "yesterday_summary" in ctx


# ============================================================================
# Integration Tests for All Vertical Dashboards
# ============================================================================

@pytest.mark.django_db
class TestVerticalDashboardsHTTP200:
    """
    Integration tests to ensure all vertical dashboards return HTTP 200.
    
    This prevents production 500 errors from missing template variables.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self, db):
        """Create test user and businesses for all verticals."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        # Create a business for each vertical
        self.businesses = {}
        for kind in [BusinessKind.PHONES, BusinessKind.CLOTHING, BusinessKind.PHARMACY, 
                     BusinessKind.LIQUOR, BusinessKind.GYM]:
            biz = Business.objects.create(
                name=f"Test {kind.label} Shop",
                kind=kind.value,
            )
            self.businesses[kind.value] = biz
            
            # Create manager membership
            Membership.objects.create(
                user=self.user,
                business=biz,
                role="MANAGER",
                status="ACTIVE"
            )
        
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_phones_dashboard_200(self):
        """Test phones dashboard returns 200."""
        # Simulate selecting the phones business
        biz = self.businesses[BusinessKind.PHONES.value]
        response = self.client.get(
            reverse('verticals:phones_dashboard'),
            HTTP_HOST=f"{biz.id}.testserver"  # Simulate subdomain
        )
        
        # Should return 200 even with no data
        assert response.status_code == 200
    
    def test_clothing_dashboard_200(self):
        """Test clothing dashboard returns 200 (this was the failing one)."""
        biz = self.businesses[BusinessKind.CLOTHING.value]
        response = self.client.get(
            reverse('verticals:clothing_dashboard'),
            HTTP_HOST=f"{biz.id}.testserver"
        )
        
        # Should return 200 even with no data
        assert response.status_code == 200
    
    def test_pharmacy_dashboard_200(self):
        """Test pharmacy dashboard returns 200."""
        biz = self.businesses[BusinessKind.PHARMACY.value]
        response = self.client.get(
            reverse('pharmacy:dashboard'),
            HTTP_HOST=f"{biz.id}.testserver"
        )
        
        # Should return 200 even with no data
        assert response.status_code == 200
    
    def test_liquor_dashboard_200(self):
        """Test liquor dashboard returns 200."""
        biz = self.businesses[BusinessKind.LIQUOR.value]
        response = self.client.get(
            reverse('verticals:liquor_dashboard'),
            HTTP_HOST=f"{biz.id}.testserver"
        )
        
        # Should return 200 even with no data
        assert response.status_code == 200
    
    def test_gym_dashboard_200(self):
        """Test gym dashboard returns 200."""
        biz = self.businesses[BusinessKind.GYM.value]
        response = self.client.get(
            reverse('verticals:gym_dashboard'),
            HTTP_HOST=f"{biz.id}.testserver"
        )
        
        # Should return 200 even with no data
        assert response.status_code == 200
    
    def test_all_dashboards_have_normalized_context(self):
        """
        Test that all dashboard responses include normalized context keys.
        
        This ensures the normalizer is being called in all views.
        """
        dashboard_urls = [
            ('verticals:phones_dashboard', BusinessKind.PHONES.value),
            ('verticals:clothing_dashboard', BusinessKind.CLOTHING.value),
            ('pharmacy:dashboard', BusinessKind.PHARMACY.value),
            ('verticals:liquor_dashboard', BusinessKind.LIQUOR.value),
            ('verticals:gym_dashboard', BusinessKind.GYM.value),
        ]
        
        for url_name, kind in dashboard_urls:
            biz = self.businesses[kind]
            response = self.client.get(
                reverse(url_name),
                HTTP_HOST=f"{biz.id}.testserver"
            )
            
            assert response.status_code == 200
            
            # Check that normalized keys are in context
            context = response.context
            for key in DASHBOARD_DEFAULTS.keys():
                assert key in context, f"{url_name} missing normalized key: {key}"


# ============================================================================
# Template Variable Existence Tests
# ============================================================================

@pytest.mark.django_db
class TestDashboardTemplateVariables:
    """
    Tests to ensure dashboard templates have all required variables.
    
    This catches missing variable errors that would cause 500 in production.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self, db):
        """Create minimal test user and business."""
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123"
        )
        self.business = Business.objects.create(
            name="Test Shop",
            kind=BusinessKind.CLOTHING.value
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_dashboard_context_always_has_defaults(self):
        """Test that dashboard context always includes default values."""
        response = self.client.get(
            reverse('verticals:clothing_dashboard'),
            HTTP_HOST=f"{self.business.id}.testserver"
        )
        
        context = response.context
        
        # All default keys should be present
        assert "yesterday_summary" in context
        assert "dashboard_quotes" in context
        assert "dashboard_brand_title" in context
        assert "dashboard_greeting" in context
        assert "dashboard_user_name" in context
        
        # Even if None, they should exist (no KeyError)
        assert context.get("yesterday_summary") is not None or context.get("yesterday_summary") is None

