"""
Regression test for warranty_expiration field issue.

Ensures that /inventory/list/ (stock_list view) works correctly
after warranty field migrations are applied.

This test will fail in dev if migrations haven't been applied, but will
pass on the test DB where migrations are always applied.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.models import InventoryItem, Location, Product
from tenants.models import Business, Membership

User = get_user_model()


class StockListWarrantyTestCase(TestCase):
    """
    Test that stock_list view works with warranty_expiration field.
    Ensures the field exists in the DB and queries work correctly.
    """

    def setUp(self):
        """Create test business, location, product, and inventory item."""
        # Create business
        self.business = Business.objects.create(
            name="Test Phones Store",
            business_kind="phones",
            slug="test-phones-store",
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True,
        )
        
        # Create product
        self.product = Product.objects.create(
            code="TEST-001",
            brand="TECNO",
            model="Spark 40",
            variant="4+128",
            cost_price=50000,
            sale_price=75000,
        )
        
        # Create inventory item with warranty fields
        self.item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei="123456789012345",
            order_price=50000,
            selling_price=75000,
            status="IN_STOCK",
            warranty_status="unknown",
            # warranty_expiration is nullable, so it's OK to omit
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
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client = Client()
        self.client.login(username="testmanager", password="testpass123")

    def test_stock_list_renders_without_warranty_column_error(self):
        """
        Test that stock_list view renders successfully.
        
        This guards against the error:
        django.db.utils.OperationalError: no such column: inventory_inventoryitem.warranty_expiration
        """
        # Activate business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        # Call stock_list view
        url = reverse("inventory:stock_list")
        response = self.client.get(url)
        
        # Should return 200, not 500
        self.assertEqual(
            response.status_code,
            200,
            f"stock_list should return 200, got {response.status_code}",
        )
        
        # Should contain the item IMEI
        self.assertContains(response, "123456789012345")

    def test_warranty_expiration_field_exists(self):
        """
        Direct test that warranty_expiration field exists on InventoryItem.
        """
        # This will fail if the field doesn't exist in DB
        item = InventoryItem.objects.filter(
            warranty_expiration__isnull=True
        ).first()
        
        # Should not raise OperationalError
        self.assertIsNotNone(item)
        
    def test_warranty_fields_are_queryable(self):
        """
        Test that we can filter/annotate on warranty fields without errors.
        """
        from django.utils import timezone
        from datetime import timedelta
        
        # Set warranty expiration on item
        future_date = timezone.now().date() + timedelta(days=365)
        self.item.warranty_expiration = future_date
        self.item.warranty_status = "in_warranty"
        self.item.save()
        
        # Query with warranty_expiration filter (should not crash)
        items = InventoryItem.objects.filter(
            warranty_expiration__gte=timezone.now().date()
        )
        
        self.assertEqual(items.count(), 1)
        self.assertEqual(items.first().imei, "123456789012345")


@pytest.mark.django_db
def test_stock_list_warranty_regression_pytest(client, django_user_model):
    """
    Pytest version: Ensure stock_list doesn't crash with warranty_expiration query.
    """
    # Create business
    business = Business.objects.create(
        name="Pytest Phones Store",
        business_kind="phones",
        slug="pytest-phones-store",
    )
    
    # Create location
    location = Location.objects.create(
        business=business,
        name="Pytest Store",
        is_default=True,
    )
    
    # Create product
    product = Product.objects.create(
        code="PYTEST-001",
        brand="ITEL",
        model="A70",
        variant="3+32",
        cost_price=30000,
        sale_price=45000,
    )
    
    # Create item
    InventoryItem.objects.create(
        business=business,
        product=product,
        current_location=location,
        imei="999888777666555",
        order_price=30000,
        status="IN_STOCK",
    )
    
    # Create user
    user = django_user_model.objects.create_user(
        username="pytest_user",
        password="pytest_pass",
        email="pytest@test.com",
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE"
    )
    
    # Login and activate business
    client.login(username="pytest_user", password="pytest_pass")
    session = client.session
    session["active_business_id"] = business.id
    session.save()
    
    # Hit stock_list
    response = client.get(reverse("inventory:stock_list"))
    
    # Should return 200
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

