"""
Regression test for phones products page URL fixes.

Ensures that the products page renders without NoReverseMatch errors
for dashboard links.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.models import Location
from tenants.models import Business

User = get_user_model()


class PhonesProductsRouteTestCase(TestCase):
    """
    Test that phones products page renders correctly with fixed dashboard URLs.
    """

    def setUp(self):
        """Create test business and user."""
        # Create business
        self.business = Business.objects.create(
            name="Test Phones Store",
            business_kind="phones",
            slug="test-phones-products",
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True,
        )
        
        # Create user and log in
        self.user = User.objects.create_user(
            username="testmanager",
            password="testpass123",
            email="manager@test.com",
        )
        # Make user manager
        self.user.is_staff = False
        self.user.is_superuser = False
        self.user.save()
        
        # Add user to business
        from tenants.models import Membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client = Client()
        self.client.login(username="testmanager", password="testpass123")

    def test_phones_products_page_renders_without_reverse_match_error(self):
        """
        Test that phones products page renders successfully.
        
        This guards against the error:
        django.urls.exceptions.NoReverseMatch: Reverse for 'phones_dashboard' not found.
        """
        # Activate business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        # Call products view
        url = reverse("inventory:phone_products")
        response = self.client.get(url)
        
        # Should return 200, not 500
        self.assertEqual(
            response.status_code,
            200,
            f"phone_products should return 200, got {response.status_code}",
        )
        
    def test_products_page_contains_correct_dashboard_link(self):
        """
        Test that the rendered HTML contains the correct dashboard URL.
        """
        # Activate business
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        # Get products page
        url = reverse("inventory:phone_products")
        response = self.client.get(url)
        
        # Should contain link to inventory_dashboard (the correct route)
        self.assertContains(response, 'href="/inventory/dashboard/"')
        
        # Should NOT contain broken verticals:phones_dashboard reference
        # (We can't directly test template tags, but we verify the rendered output is correct)
        self.assertEqual(response.status_code, 200)


@pytest.mark.django_db
def test_phones_products_route_pytest(client, django_user_model):
    """
    Pytest version: Ensure products page doesn't crash with bad dashboard URL.
    """
    # Create business
    business = Business.objects.create(
        name="Pytest Products Test",
        business_kind="phones",
        slug="pytest-products-test",
    )
    
    # Create location
    Location.objects.create(
        business=business,
        name="Pytest Store",
        is_default=True,
    )
    
    # Create user
    user = django_user_model.objects.create_user(
        username="pytest_products",
        password="pytest_pass",
        email="pytest.products@test.com",
    )
    from tenants.models import Membership
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE"
    )
    
    # Login and activate business
    client.login(username="pytest_products", password="pytest_pass")
    session = client.session
    session["active_business_id"] = business.id
    session.save()
    
    # Hit products page
    response = client.get(reverse("inventory:phone_products"))
    
    # Should return 200
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

