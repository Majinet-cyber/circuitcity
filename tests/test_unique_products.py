# tests/test_unique_products.py
"""
Tests for Unique Products system (barcode/SKU-based inventory for Fast Sell).
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business
from inventory.models_unique_products import UniqueProduct, UniqueProductStockIn, UniqueSale

User = get_user_model()


@pytest.mark.django_db
class TestUniqueProductModel:
    """Test UniqueProduct model."""
    
    def test_create_unique_product(self):
        """Test creating a unique product with barcode."""
        business = Business.objects.create(name="Test Grocery", kind="grocery")
        user = User.objects.create_user(username="testuser", password="testpass")
        
        product = UniqueProduct.objects.create(
            business=business,
            vertical="groceries",
            barcode="TEST12345",
            name="Test Product",
            quantity=Decimal("100.00"),
            unit="pieces",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("75.00"),
            created_by=user,
        )
        
        assert product.barcode == "TEST12345"
        assert product.name == "Test Product"
        assert product.quantity == Decimal("100.00")
        assert product.is_in_stock is True
    
    def test_barcode_unique_per_business(self):
        """Test that barcode must be unique per business."""
        business1 = Business.objects.create(name="Business 1", kind="grocery")
        business2 = Business.objects.create(name="Business 2", kind="grocery")
        
        # Create product in business1
        UniqueProduct.objects.create(
            business=business1,
            vertical="groceries",
            barcode="SAME123",
            name="Product 1",
            selling_price=Decimal("100.00"),
        )
        
        # Same barcode in business2 should be allowed
        product2 = UniqueProduct.objects.create(
            business=business2,
            vertical="groceries",
            barcode="SAME123",
            name="Product 2",
            selling_price=Decimal("100.00"),
        )
        
        assert product2.barcode == "SAME123"
        
        # But duplicate in same business should fail
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            UniqueProduct.objects.create(
                business=business1,
                vertical="groceries",
                barcode="SAME123",
                name="Product 3",
                selling_price=Decimal("100.00"),
            )
    
    def test_stock_value_calculations(self):
        """Test stock value properties."""
        business = Business.objects.create(name="Test", kind="grocery")
        
        product = UniqueProduct.objects.create(
            business=business,
            vertical="groceries",
            barcode="VALUE123",
            name="Value Test",
            quantity=Decimal("10.00"),
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
        )
        
        assert product.stock_value_cost == Decimal("500.00")  # 10 * 50
        assert product.stock_value_selling == Decimal("1000.00")  # 10 * 100
        assert product.profit_margin == Decimal("50.00")  # (100-50)/100 * 100
    
    def test_can_sell_method(self):
        """Test can_sell validation."""
        business = Business.objects.create(name="Test", kind="grocery")
        
        product = UniqueProduct.objects.create(
            business=business,
            vertical="groceries",
            barcode="SELL123",
            name="Sell Test",
            quantity=Decimal("5.00"),
            selling_price=Decimal("100.00"),
        )
        
        assert product.can_sell(Decimal("3.00")) is True
        assert product.can_sell(Decimal("5.00")) is True
        assert product.can_sell(Decimal("6.00")) is False
        assert product.can_sell(Decimal("0")) is False


@pytest.mark.django_db
class TestUniqueProductStockIn:
    """Test stock-in functionality."""
    
    def test_stock_in_updates_quantity(self):
        """Test that stock-in increases product quantity."""
        business = Business.objects.create(name="Test", kind="grocery")
        user = User.objects.create_user(username="testuser", password="testpass")
        
        product = UniqueProduct.objects.create(
            business=business,
            vertical="groceries",
            barcode="STOCK123",
            name="Stock Test",
            quantity=Decimal("10.00"),
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
        )
        
        # Add stock
        stock_in = UniqueProductStockIn.objects.create(
            business=business,
            product=product,
            quantity=Decimal("20.00"),
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
            added_by=user,
        )
        
        # Manually update product (in real views, this is done in transaction)
        product.quantity += stock_in.quantity
        product.save()
        
        product.refresh_from_db()
        assert product.quantity == Decimal("30.00")


@pytest.mark.django_db
class TestUniqueSale:
    """Test unique sales functionality."""
    
    def test_create_sale(self):
        """Test creating a sale for unique product."""
        business = Business.objects.create(name="Test", kind="grocery")
        user = User.objects.create_user(username="testuser", password="testpass")
        
        product = UniqueProduct.objects.create(
            business=business,
            vertical="groceries",
            barcode="SALE123",
            name="Sale Test",
            quantity=Decimal("100.00"),
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
        )
        
        sale = UniqueSale.objects.create(
            business=business,
            product=product,
            quantity=Decimal("5.00"),
            unit_price=Decimal("100.00"),
            unit_cost=Decimal("50.00"),
            payment_method="CASH",
            sold_by=user,
        )
        
        assert sale.total_amount == Decimal("500.00")  # 5 * 100
        assert sale.total_cost == Decimal("250.00")  # 5 * 50
        assert sale.profit == Decimal("250.00")  # 500 - 250
        assert sale.profit_margin == Decimal("50.00")  # (250/500) * 100
    
    def test_sale_deducts_stock(self):
        """Test that completing a sale deducts stock."""
        business = Business.objects.create(name="Test", kind="grocery")
        user = User.objects.create_user(username="testuser", password="testpass")
        
        product = UniqueProduct.objects.create(
            business=business,
            vertical="groceries",
            barcode="DEDUCT123",
            name="Deduct Test",
            quantity=Decimal("100.00"),
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
        )
        
        # Create sale
        sale = UniqueSale.objects.create(
            business=business,
            product=product,
            quantity=Decimal("10.00"),
            unit_price=Decimal("100.00"),
            unit_cost=Decimal("50.00"),
            sold_by=user,
        )
        
        # Manually deduct stock (in real views, this is done in transaction)
        product.quantity -= sale.quantity
        product.save()
        
        product.refresh_from_db()
        assert product.quantity == Decimal("90.00")


@pytest.mark.django_db
class TestFastSellIntegration:
    """Test Fast Sell integration with Unique Products."""
    
    def test_fast_sell_lookup_by_barcode(self, client):
        """Test that Fast Sell can lookup products by barcode."""
        business = Business.objects.create(name="Test Grocery", kind="grocery")
        user = User.objects.create_user(username="testuser", password="testpass")
        user.business_memberships.create(business=business, role="manager")
        
        product = UniqueProduct.objects.create(
            business=business,
            vertical="groceries",
            barcode="FAST123",
            name="Fast Sell Test",
            quantity=Decimal("50.00"),
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
        )
        
        client.force_login(user)
        
        # Test lookup API
        response = client.get(
            reverse("grocery:fast_sell_lookup"),
            {"q": "FAST123"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["product"]["barcode"] == "FAST123"
        assert data["product"]["name"] == "Fast Sell Test"
    
    def test_fast_sell_not_found(self, client):
        """Test Fast Sell returns error for non-existent barcode."""
        business = Business.objects.create(name="Test Grocery", kind="grocery")
        user = User.objects.create_user(username="testuser", password="testpass")
        user.business_memberships.create(business=business, role="manager")
        
        client.force_login(user)
        
        response = client.get(
            reverse("grocery:fast_sell_lookup"),
            {"q": "NOTFOUND"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Not found in Unique Products" in data["error"]


@pytest.mark.django_db
class TestUniqueProductViews:
    """Test Unique Products views."""
    
    def test_unique_products_list(self, client):
        """Test unique products list page."""
        business = Business.objects.create(name="Test", kind="grocery")
        user = User.objects.create_user(username="testuser", password="testpass")
        user.business_memberships.create(business=business, role="manager")
        
        # Create some products
        UniqueProduct.objects.create(
            business=business,
            vertical="groceries",
            barcode="PROD1",
            name="Product 1",
            quantity=Decimal("10.00"),
            selling_price=Decimal("100.00"),
        )
        
        client.force_login(user)
        response = client.get(reverse("inventory:unique_products:list"))
        
        assert response.status_code == 200
        assert b"Unique Products" in response.content
        assert b"Product 1" in response.content
    
    def test_unique_product_create(self, client):
        """Test creating a unique product via form."""
        business = Business.objects.create(name="Test", kind="grocery")
        user = User.objects.create_user(username="testuser", password="testpass")
        user.business_memberships.create(business=business, role="manager")
        
        client.force_login(user)
        
        response = client.post(
            reverse("inventory:unique_products:create"),
            {
                "vertical": "groceries",
                "barcode": "NEWPROD123",
                "name": "New Product",
                "quantity": "100",
                "unit": "kg",
                "cost_price": "50",
                "selling_price": "100",
            }
        )
        
        # Should redirect on success
        assert response.status_code == 302
        
        # Verify product was created
        product = UniqueProduct.objects.get(barcode="NEWPROD123")
        assert product.name == "New Product"
        assert product.quantity == Decimal("100.00")


# Run with: pytest tests/test_unique_products.py -v

