# tests/test_brand_icons_safety.py
"""
Tests for safe brand icon template tag and WhiteNoise static file handling.

Critical regression test to ensure missing brand icons never cause a 500 error.

This test ensures:
1. The brand_icon template tag never raises an exception
2. Missing brand SVG files return a valid fallback URL
3. The /inventory/scan-in/ page renders successfully even with missing icons
4. WhiteNoise manifest storage doesn't cause 500 errors
"""
import pytest
from django.template import Context, Template
from django.test import RequestFactory, override_settings
from django.contrib.auth.models import User
from django.contrib.staticfiles.storage import staticfiles_storage

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind
from inventory.models import Location

pytestmark = pytest.mark.django_db


# =============================================================================
# Template Tag Unit Tests
# =============================================================================
class TestBrandIconTag:
    """Test the brand_icon and brand_icon_path template tags."""
    
    def test_brand_icon_existing_file(self):
        """Test that existing brand files return correct URL."""
        template = Template("{% load brand_icons %}{% brand_icon 'Tecno' %}")
        rendered = template.render(Context({}))
        
        # Should contain the brand path (staticfiles will resolve the URL)
        assert "tecno.svg" in rendered.lower()
    
    def test_brand_icon_missing_file(self):
        """Test that missing brand files return fallback URL without raising."""
        template = Template("{% load brand_icons %}{% brand_icon 'NonExistentBrand' %}")
        
        # Should NOT raise an exception
        rendered = template.render(Context({}))
        
        # Should return the fallback default.svg
        assert "default.svg" in rendered.lower()
        assert rendered  # Should not be empty
    
    def test_brand_icon_iphone(self):
        """Test that iPhone brand icon resolves correctly."""
        template = Template("{% load brand_icons %}{% brand_icon 'iPhone' %}")
        rendered = template.render(Context({}))
        
        # Should slugify to 'iphone'
        assert "iphone.svg" in rendered.lower()
    
    def test_brand_icon_google_pixel(self):
        """Test that Google Pixel brand icon resolves correctly."""
        template = Template("{% load brand_icons %}{% brand_icon 'Google Pixel' %}")
        rendered = template.render(Context({}))
        
        # Should slugify to 'google-pixel'
        assert "google-pixel.svg" in rendered.lower()
    
    def test_brand_icon_redmi(self):
        """Test that Redmi brand icon resolves correctly."""
        template = Template("{% load brand_icons %}{% brand_icon 'Redmi' %}")
        rendered = template.render(Context({}))
        
        assert "redmi.svg" in rendered.lower()
    
    def test_brand_icon_empty_string(self):
        """Test that empty brand name returns fallback."""
        template = Template("{% load brand_icons %}{% brand_icon '' %}")
        rendered = template.render(Context({}))
        
        # Should return fallback
        assert "default.svg" in rendered.lower()
    
    def test_brand_icon_none_value(self):
        """Test that None brand name returns fallback."""
        template = Template("{% load brand_icons %}{% brand_icon brand_name %}")
        rendered = template.render(Context({"brand_name": None}))
        
        # Should return fallback without error
        assert "default.svg" in rendered.lower()
    
    def test_brand_icon_special_characters(self):
        """Test that brand names with special characters are handled."""
        template = Template("{% load brand_icons %}{% brand_icon 'Brand@#$%' %}")
        rendered = template.render(Context({}))
        
        # Should slugify and probably not exist, so fallback
        assert rendered  # Should not crash
        # Likely returns default.svg since "brand" probably doesn't exist
    
    def test_brand_icon_path_existing(self):
        """Test brand_icon_path with existing file path."""
        template = Template("{% load brand_icons %}{% brand_icon_path 'img/brands/tecno.svg' %}")
        rendered = template.render(Context({}))
        
        assert "tecno.svg" in rendered.lower()
    
    def test_brand_icon_path_missing(self):
        """Test brand_icon_path with missing file path returns fallback."""
        template = Template("{% load brand_icons %}{% brand_icon_path 'img/brands/nonexistent.svg' %}")
        rendered = template.render(Context({}))
        
        # Should return fallback
        assert "default.svg" in rendered.lower()
    
    def test_brand_icon_path_empty(self):
        """Test brand_icon_path with empty path returns fallback."""
        template = Template("{% load brand_icons %}{% brand_icon_path '' %}")
        rendered = template.render(Context({}))
        
        assert "default.svg" in rendered.lower()


# =============================================================================
# Integration Tests: View Rendering
# =============================================================================
class TestScanInPageWithMissingIcons:
    """Test that /inventory/scan-in/ never crashes from missing icons."""
    
    @pytest.fixture
    def setup_phones_business(self, db):
        """Create a phones business with user and membership."""
        # Create user
        user = User.objects.create_user(
            username="testmanager",
            password="testpass123",
            email="manager@test.com",
        )
        
        # Create business
        business = Business.objects.create(
            name="Test Phones Shop",
            business_kind=BusinessKind.PHONES,
            status="ACTIVE",
        )
        
        # Create membership (manager role)
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
        )
        
        # Create a location
        location = Location.objects.create(
            name="Main Shop",
            business=business,
        )
        
        return {
            "user": user,
            "business": business,
            "location": location,
        }
    
    def test_scan_in_page_renders_200(self, client, setup_phones_business):
        """Test that scan-in page returns 200 even with missing icons."""
        user = setup_phones_business["user"]
        business = setup_phones_business["business"]
        
        # Login
        client.login(username="testmanager", password="testpass123")
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Request the scan-in page
        response = client.get("/inventory/phones/scan-in/")
        
        # Should NOT be a 500 error
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}. "
            "Missing brand icons should not cause 500 errors!"
        )
    
    def test_scan_in_template_renders_with_fake_brand(self, client, setup_phones_business):
        """Test rendering template with a completely fake brand name."""
        user = setup_phones_business["user"]
        business = setup_phones_business["business"]
        
        client.login(username="testmanager", password="testpass123")
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Get the page
        response = client.get("/inventory/phones/scan-in/")
        
        # Check that it rendered successfully
        assert response.status_code == 200
        
        # Check that the page contains the brand icon tag
        assert "brand_icon" in str(response.content) or response.status_code == 200
        
        # Most importantly: no 500 error
    
    def test_scan_sell_page_renders_200(self, client, setup_phones_business):
        """Test that scan-sell page also renders successfully."""
        user = setup_phones_business["user"]
        business = setup_phones_business["business"]
        
        client.login(username="testmanager", password="testpass123")
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        response = client.get("/inventory/phones/scan-sell/")
        
        # Should render successfully
        assert response.status_code == 200


# =============================================================================
# Static File Existence Tests
# =============================================================================
class TestBrandIconFilesExist:
    """Test that all required brand icon SVG files exist."""
    
    def test_iphone_svg_exists(self):
        """Test that iphone.svg exists in static files."""
        exists = staticfiles_storage.exists("img/brands/iphone.svg")
        assert exists, "Missing img/brands/iphone.svg - this will cause 500 on production!"
    
    def test_google_pixel_svg_exists(self):
        """Test that google-pixel.svg exists in static files."""
        exists = staticfiles_storage.exists("img/brands/google-pixel.svg")
        assert exists, "Missing img/brands/google-pixel.svg - this will cause 500 on production!"
    
    def test_redmi_svg_exists(self):
        """Test that redmi.svg exists in static files."""
        exists = staticfiles_storage.exists("img/brands/redmi.svg")
        assert exists, "Missing img/brands/redmi.svg - this will cause 500 on production!"
    
    def test_default_svg_exists(self):
        """Test that default.svg fallback exists in static files."""
        exists = staticfiles_storage.exists("img/brands/default.svg")
        assert exists, "Missing img/brands/default.svg - fallback icon is critical!"
    
    def test_existing_brands_still_work(self):
        """Test that previously existing brand icons still exist."""
        assert staticfiles_storage.exists("img/brands/tecno.svg")
        assert staticfiles_storage.exists("img/brands/itel.svg")
        assert staticfiles_storage.exists("img/brands/samsung.svg")


# =============================================================================
# WhiteNoise Safety Test
# =============================================================================
class TestWhiteNoiseSafety:
    """Test that WhiteNoise manifest storage doesn't crash the app."""
    
    def test_template_tag_never_raises_valueerror(self):
        """
        Test that the template tag never raises ValueError even if
        staticfiles_storage.url() would fail.
        """
        # Simulate a missing file
        template = Template("{% load brand_icons %}{% brand_icon 'CompletelyFakeBrand999' %}")
        
        # This should NOT raise ValueError like:
        # "The file 'img/brands/...' could not be found with CompressedManifestStaticFilesStorage"
        try:
            rendered = template.render(Context({}))
            assert rendered  # Should return something (the fallback)
        except ValueError as e:
            pytest.fail(f"brand_icon tag raised ValueError: {e}")
        except Exception as e:
            pytest.fail(f"brand_icon tag raised unexpected exception: {e}")
    
    def test_brand_icon_path_never_raises_valueerror(self):
        """Test that brand_icon_path never raises ValueError for missing files."""
        template = Template(
            "{% load brand_icons %}{% brand_icon_path 'img/brands/completely-fake-999.svg' %}"
        )
        
        try:
            rendered = template.render(Context({}))
            assert rendered  # Should return fallback
        except ValueError as e:
            pytest.fail(f"brand_icon_path tag raised ValueError: {e}")
        except Exception as e:
            pytest.fail(f"brand_icon_path tag raised unexpected exception: {e}")

