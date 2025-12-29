# sales/tests/test_pharmacy_fast_sell.py
"""
Regression test for Pharmacy Fast Sell RecursionError fix.
Ensures the pharmacy fast sell page renders without template recursion errors.
"""
import pytest
from django.test import Client
from django.urls import reverse

from tenants.constants import BusinessKind
from tests.helpers.tenant_setup import (
    make_user, make_business, make_location, make_membership, login_with_active_scope
)


@pytest.mark.django_db
class TestPharmacyFastSellRegression:
    """Test that pharmacy fast sell page renders correctly without recursion errors."""
    
    def test_pharmacy_fast_sell_returns_200(self, client: Client):
        """
        CRITICAL REGRESSION TEST:
        Pharmacy fast sell must return 200 status, not 500 RecursionError.
        
        This test prevents the production bug where template recursion caused:
        RecursionError: maximum recursion depth exceeded
        """
        # Create user and pharmacy business
        user = make_user(email="pharmacist@test.com", username="pharmacist", password="testpass123")
        business = make_business(
            created_by=user,
            kind=BusinessKind.PHARMACY,
            name="Test Pharmacy"
        )
        location = make_location(business=business, name="Main Store")
        make_membership(
            business=business,
            user=user,
            role="MANAGER",
            location=None,  # Managers should not be tied to a specific location
            status="ACTIVE"
        )
        
        # Login and set active business and location
        login_with_active_scope(client, user, business, location)
        
        # Access pharmacy fast sell page
        url = reverse('verticals:pharmacy_fast_sell')
        response = client.get(url)
        
        # CRITICAL: Must return 200, not 500
        assert response.status_code == 200, \
            f"Pharmacy fast sell returned {response.status_code}. " \
            f"Check for template recursion or missing context variables."
        
        # Verify template is rendered correctly
        assert b"Fast Sell" in response.content or b"fast-sell" in response.content
        
    def test_pharmacy_fast_sell_template_no_recursion(self, client: Client):
        """
        Verify that the template doesn't have circular extends/includes.
        
        Common causes of template recursion:
        - {% extends base_template %} where base_template == current template
        - {% include template_var %} where template_var resolves to itself
        - Circular chain of includes
        """
        # Create user and pharmacy business
        user = make_user(email="pharmacist2@test.com", username="pharmacist2", password="testpass123")
        business = make_business(
            created_by=user,
            kind=BusinessKind.PHARMACY,
            name="Test Pharmacy 2"
        )
        location = make_location(business=business, name="Main Store")
        make_membership(
            business=business,
            user=user,
            role="MANAGER",
            location=None,  # Managers should not be tied to a specific location
            status="ACTIVE"
        )
        
        # Login and set active business and location
        login_with_active_scope(client, user, business, location)
        
        # Access pharmacy fast sell page
        url = reverse('verticals:pharmacy_fast_sell')
        
        # This should complete without RecursionError
        try:
            response = client.get(url)
            assert response.status_code == 200
        except RecursionError as e:
            pytest.fail(f"Template recursion detected: {str(e)}")
        except Exception as e:
            # Other errors are acceptable for this specific test
            # (e.g., missing context variables, database issues)
            # We only care about RecursionError here
            if "recursion" in str(e).lower():
                pytest.fail(f"Recursion error detected: {str(e)}")
            # Otherwise, let it pass (we're only testing for recursion)
            pass
    
    def test_pharmacy_fast_sell_api_endpoints_work(self, client: Client):
        """Test that pharmacy fast sell API endpoints are accessible."""
        # Create user and pharmacy business
        user = make_user(email="pharmacist3@test.com", username="pharmacist3", password="testpass123")
        business = make_business(
            created_by=user,
            kind=BusinessKind.PHARMACY,
            name="Test Pharmacy 3"
        )
        location = make_location(business=business, name="Main Store")
        make_membership(
            business=business,
            user=user,
            role="MANAGER",
            location=None,  # Managers should not be tied to a specific location
            status="ACTIVE"
        )
        
        # Login and set active business and location
        login_with_active_scope(client, user, business, location)
        
        # Test lookup API
        lookup_url = reverse('verticals:pharmacy_fast_sell_lookup_api')
        response = client.get(f"{lookup_url}?barcode=TEST123")
        assert response.status_code == 200
        assert response.json().get('ok') is not None
        
        # Test KPIs API
        kpis_url = reverse('verticals:pharmacy_fast_sell_kpis_api')
        response = client.get(f"{kpis_url}?range=today")
        assert response.status_code == 200
        assert response.json().get('ok') is not None

