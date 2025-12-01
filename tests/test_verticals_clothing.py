# tests/test_verticals_clothing.py
"""
Tests for clothing store functionality: products, sales, archive, dashboard.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_verticals import ClothingSale, ClothingProductLog, ClothingProductAction
from tenants.models import Business

User = get_user_model()


@pytest.fixture
def business():
    """Create a test clothing business"""
    return Business.objects.create(
        name="Test Clothing Store",
        slug="test-clothing",
        status="ACTIVE",
        business_kind=BusinessKind.CLOTHING
    )


@pytest.fixture
def manager(business):
    """Create a manager user"""
    user = User.objects.create_user(username="clothing_manager", password="pass")
    user.is_staff = False
    user.save()
    return user


@pytest.fixture
def staff(business):
    """Create a staff user"""
    user = User.objects.create_user(username="staff", password="pass")
    user.is_staff = False
    user.save()
    return user


@pytest.fixture
def clothing_product(business):
    """Create a clothing product"""
    return MerchProduct.objects.create(
        business=business,
        name="Denim Jacket",
        kind=BusinessKind.CLOTHING,
        price_per_bottle=Decimal("25000.00"),  # Using price_per_bottle as generic price
        is_active=True,
        is_archived=False
    )


@pytest.mark.django_db
class TestClothingProduct:
    """Test clothing product management"""
    
    def test_create_product(self, business):
        """Test creating a clothing product"""
        product = MerchProduct.objects.create(
            business=business,
            name="T-Shirt",
            kind=BusinessKind.CLOTHING,
            price_per_bottle=Decimal("5000.00"),
            is_active=True
        )
        
        assert product.is_active is True
        assert product.is_archived is False
    
    def test_archive_product(self, clothing_product, manager):
        """Test archiving a product"""
        clothing_product.is_archived = True
        clothing_product.is_active = False
        clothing_product.archived_at = timezone.now()
        clothing_product.archived_by = manager
        clothing_product.save()
        
        assert clothing_product.is_archived is True
        assert clothing_product.is_active is False
        assert clothing_product.archived_by == manager
    
    def test_restore_archived_product(self, clothing_product, manager):
        """Test restoring an archived product"""
        # Archive first
        clothing_product.is_archived = True
        clothing_product.is_active = False
        clothing_product.archived_at = timezone.now()
        clothing_product.archived_by = manager
        clothing_product.save()
        
        # Restore
        clothing_product.is_archived = False
        clothing_product.is_active = True
        clothing_product.archived_at = None
        clothing_product.archived_by = None
        clothing_product.save()
        
        assert clothing_product.is_archived is False
        assert clothing_product.is_active is True


@pytest.mark.django_db
class TestClothingProductLog:
    """Test clothing product audit logging"""
    
    def test_log_product_creation(self, clothing_product, manager):
        """Test logging product creation"""
        log = ClothingProductLog.objects.create(
            product=clothing_product,
            action=ClothingProductAction.CREATED,
            changes={"name": clothing_product.name, "price": str(clothing_product.price_per_bottle)},
            performed_by=manager
        )
        
        assert log.action == ClothingProductAction.CREATED
        assert log.product == clothing_product
        assert log.performed_by == manager
    
    def test_log_product_update(self, clothing_product, manager):
        """Test logging product update"""
        old_price = clothing_product.price_per_bottle
        new_price = Decimal("30000.00")
        
        clothing_product.price_per_bottle = new_price
        clothing_product.save()
        
        log = ClothingProductLog.objects.create(
            product=clothing_product,
            action=ClothingProductAction.UPDATED,
            changes={"price": {"old": str(old_price), "new": str(new_price)}},
            performed_by=manager
        )
        
        assert log.action == ClothingProductAction.UPDATED
        assert "price" in log.changes
    
    def test_log_product_archive(self, clothing_product, manager):
        """Test logging product archival"""
        clothing_product.is_archived = True
        clothing_product.archived_at = timezone.now()
        clothing_product.archived_by = manager
        clothing_product.save()
        
        log = ClothingProductLog.objects.create(
            product=clothing_product,
            action=ClothingProductAction.ARCHIVED,
            changes={"archived_at": str(clothing_product.archived_at)},
            performed_by=manager
        )
        
        assert log.action == ClothingProductAction.ARCHIVED


@pytest.mark.django_db
class TestClothingSale:
    """Test clothing sales"""
    
    def test_create_sale(self, business, clothing_product, staff):
        """Test creating a clothing sale"""
        sale = ClothingSale.objects.create(
            business=business,
            product=clothing_product,
            quantity=2,
            unit_price=Decimal("25000.00"),
            sold_by=staff
        )
        
        assert sale.total_price == Decimal("50000.00")  # 2 × 25000
        assert sale.sold_by == staff
    
    def test_sale_auto_calculates_total(self, business, clothing_product, staff):
        """Test that sale auto-calculates total price"""
        sale = ClothingSale.objects.create(
            business=business,
            product=clothing_product,
            quantity=3,
            unit_price=Decimal("10000.00"),
            sold_by=staff
        )
        
        assert sale.total_price == Decimal("30000.00")


@pytest.mark.django_db
class TestClothingDashboard:
    """Test clothing dashboard metrics"""
    
    def test_dashboard_counts_products(self, business, clothing_product):
        """Test dashboard counts active products"""
        # Create more products
        MerchProduct.objects.create(
            business=business,
            name="Jeans",
            kind=BusinessKind.CLOTHING,
            price_per_bottle=Decimal("30000.00"),
            is_active=True
        )
        
        active_products = MerchProduct.objects.filter(
            business=business,
            kind=BusinessKind.CLOTHING,
            is_active=True,
            is_archived=False
        )
        
        assert active_products.count() == 2
    
    def test_dashboard_calculates_sales_totals(self, business, clothing_product, staff):
        """Test dashboard calculates sales totals"""
        # Create sales
        ClothingSale.objects.create(
            business=business,
            product=clothing_product,
            quantity=2,
            unit_price=Decimal("25000.00"),
            sold_by=staff
        )
        ClothingSale.objects.create(
            business=business,
            product=clothing_product,
            quantity=1,
            unit_price=Decimal("25000.00"),
            sold_by=staff
        )
        
        total_sales = ClothingSale.objects.filter(business=business).count()
        assert total_sales == 2
    
    def test_dashboard_excludes_archived(self, business, clothing_product, manager):
        """Test dashboard excludes archived products"""
        # Create another product and archive it
        archived_product = MerchProduct.objects.create(
            business=business,
            name="Old Style Shirt",
            kind=BusinessKind.CLOTHING,
            price_per_bottle=Decimal("15000.00"),
            is_active=True
        )
        archived_product.is_archived = True
        archived_product.archived_by = manager
        archived_product.archived_at = timezone.now()
        archived_product.save()
        
        active_products = MerchProduct.objects.filter(
            business=business,
            kind=BusinessKind.CLOTHING,
            is_active=True,
            is_archived=False
        )
        
        assert active_products.count() == 1
        assert archived_product not in active_products

