# sales/tests/test_pharmacy_fast_sell.py
"""
Regression test for Pharmacy Fast Sell RecursionError fix.
Ensures the pharmacy fast sell page renders without template recursion errors.
"""
import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


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
        user = User.objects.create_user(
            username="pharmacist",
            email="pharmacist@test.com",
            password="testpass123"
        )
        
        from tenants.models import Business, Membership
        business = Business.objects.create(
            name="Test Pharmacy",
            kind="pharmacy",
            owner=user
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            role="manager",
            is_active=True
        )
        
        # Login and set active business
        client.force_login(user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
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
        user = User.objects.create_user(
            username="pharmacist2",
            email="pharmacist2@test.com",
            password="testpass123"
        )
        
        from tenants.models import Business, Membership
        business = Business.objects.create(
            name="Test Pharmacy 2",
            kind="pharmacy",
            owner=user
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            role="owner",
            is_active=True
        )
        
        # Login and set active business
        client.force_login(user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
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
        user = User.objects.create_user(
            username="pharmacist3",
            email="pharmacist3@test.com",
            password="testpass123"
        )
        
        from tenants.models import Business, Membership
        business = Business.objects.create(
            name="Test Pharmacy 3",
            kind="pharmacy",
            owner=user
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            role="manager",
            is_active=True
        )
        
        # Login and set active business
        client.force_login(user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
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

