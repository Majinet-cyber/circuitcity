"""
Regression test for clothing fast sell page rendering.

Ensures that GET /verticals/clothing/fast-sell/ returns 200 and does not raise NoReverseMatch errors.
"""
import pytest
from django.test import Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from tenants.models import Business, BusinessUserMembership
from inventory.models import Location
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.mark.django_db
class TestClothingFastSellPageRendering:
    """Test that the clothing fast sell page renders without errors."""

    def test_fast_sell_page_loads_successfully(self):
        """
        Test that GET /verticals/clothing/fast-sell/ returns HTTP 200.
        
        This is a regression test for the NoReverseMatch error:
        "Reverse for 'clothing_fast_sell_resolve_product_api' not found"
        """
        # Setup user and business
        user = User.objects.create_user(
            username='clothinguser',
            email='clothing@test.com',
            password='testpass123'
        )
        
        business = Business.objects.create(
            name='Clothing Test Store',
            business_kind=BusinessKind.CLOTHING
        )
        
        BusinessUserMembership.objects.create(
            user=user,
            business=business,
            role='manager',
            is_active=True
        )
        
        Location.objects.create(
            business=business,
            name='Main Store',
            is_default=True
        )
        
        # Login and set active business
        client = Client()
        client.force_login(user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Request fast sell page
        url = reverse('verticals:clothing_fast_sell')
        response = client.get(url)
        
        # Assertions
        assert response.status_code == 200, (
            f"Expected HTTP 200, got {response.status_code}. "
            f"This indicates the page failed to render."
        )
        
        html = response.content.decode()
        
        # Verify expected content is present
        assert 'Fast Sell' in html, "Page should contain 'Fast Sell' text"
        assert 'barcodeInput' in html, "Page should contain barcode input field"
        
        # Verify no NoReverseMatch errors
        assert 'NoReverseMatch' not in html, (
            "Page should not contain NoReverseMatch errors"
        )
        assert 'Reverse for' not in html or 'not found' not in html, (
            "Page should not contain URL reversal errors"
        )
        
        # Verify the resolve product API URL is correctly rendered
        # The JavaScript should have the actual URL, not a template tag
        assert '/verticals/clothing/api/fast-sell/resolve-product/' in html, (
            "The resolve product API URL should be properly reversed in the template"
        )

    def test_all_fast_sell_template_urls_are_valid(self):
        """
        Test that all URL names used in fast_sell.html can be reversed.
        
        This ensures that the URL configuration is correct and all URL names
        referenced in the template are properly registered.
        """
        # All URL names used in the fast_sell.html template
        url_names_with_namespace = [
            'verticals:clothing_dashboard_v2',
            'inventory:clothing_wizard',
            'verticals:clothing_hub',
            'verticals:clothing_fast_sell_lookup_unified_api',
            'verticals:clothing_fast_sell_sell_unified_api',
            'verticals:clothing_fast_sell_resolve_product_api',  # The problematic one
        ]
        
        for url_name in url_names_with_namespace:
            # Should not raise NoReverseMatch
            url = reverse(url_name)
            assert url, f"URL name '{url_name}' should reverse to a valid path"
            assert url.startswith('/'), f"Reversed URL should start with '/': {url}"



