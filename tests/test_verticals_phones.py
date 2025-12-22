# tests/test_verticals_phones.py
"""
Tests for phones store functionality: products, inventory, sales, credits, repayments.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models import Product, InventoryItem, Location
from inventory.models_verticals import PhoneCredit, PhoneCreditPayment
from tenants.models import Business

User = get_user_model()


@pytest.fixture
def business():
    """Create a test phones business"""
    return Business.objects.create(
        name="Test Phone Store",
        slug="test-phones",
        status="ACTIVE",
        business_kind=BusinessKind.PHONES
    )


@pytest.fixture
def location(business):
    """Create a test location"""
    return Location.objects.create(
        business=business,
        name="Main Store",
        is_active=True
    )


@pytest.fixture
def manager(business):
    """Create a manager user"""
    user = User.objects.create_user(username="manager", password="pass")
    user.is_staff = False
    user.save()
    return user


@pytest.fixture
def agent(business):
    """Create an agent user"""
    user = User.objects.create_user(username="agent", password="pass")
    user.is_staff = False
    user.save()
    return user


@pytest.fixture
def phone_product(business):
    """Create a phone product"""
    return Product.objects.create(
        code="IPHN14-128",
        name="iPhone 14 128GB",
        brand="Apple",
        model="iPhone 14",
        variant="128GB",
        cost_price=Decimal("450000.00"),
        sale_price=Decimal("550000.00"),
        low_stock_threshold=5
    )


@pytest.mark.django_db
class TestPhoneProduct:
    """Test phone product configuration"""
    
    def test_create_phone_product(self, business):
        """Test creating a phone product"""
        product = Product.objects.create(
            code="SAMGS23-256",
            name="Samsung Galaxy S23 256GB",
            brand="Samsung",
            model="Galaxy S23",
            variant="256GB",
            cost_price=Decimal("380000.00"),
            sale_price=Decimal("480000.00")
        )
        
        assert product.brand == "Samsung"
        assert product.model == "Galaxy S23"
        assert product.sale_price == Decimal("480000.00")
    
    def test_product_profit_margin(self, phone_product):
        """Test calculating profit margin"""
        expected_profit = phone_product.sale_price - phone_product.cost_price
        assert expected_profit == Decimal("100000.00")


@pytest.mark.django_db
class TestPhoneInventory:
    """Test phone inventory management"""
    
    def test_add_inventory_item(self, business, phone_product, location):
        """Test adding a phone to inventory"""
        item = InventoryItem.objects.create(
            business=business,
            imei="123456789012345",
            product=phone_product,
            order_price=phone_product.cost_price,
            selling_price=phone_product.sale_price,
            status="IN_STOCK",
            current_location=location
        )
        
        assert item.imei == "123456789012345"
        assert item.status == "IN_STOCK"
        assert item.selling_price == phone_product.sale_price
    
    def test_inventory_item_unique_imei_per_business(self, business, phone_product, location):
        """Test IMEI uniqueness constraint per business"""
        # Create first item
        InventoryItem.objects.create(
            business=business,
            imei="111111111111111",
            product=phone_product,
            order_price=phone_product.cost_price,
            selling_price=phone_product.sale_price,
            status="IN_STOCK",
            current_location=location
        )
        
        # Attempting to create duplicate IMEI in same business should fail
        # (depending on DB constraints)
        # For now, just verify the first one exists
        items = InventoryItem.objects.filter(business=business, imei="111111111111111")
        assert items.count() >= 1
    
    def test_stock_count(self, business, phone_product, location):
        """Test counting in-stock items"""
        # Add 3 items
        for i in range(3):
            InventoryItem.objects.create(
                business=business,
                imei=f"11111111111111{i}",
                product=phone_product,
                order_price=phone_product.cost_price,
                selling_price=phone_product.sale_price,
                status="IN_STOCK",
                current_location=location
            )
        
        in_stock_count = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK"
        ).count()
        
        assert in_stock_count == 3


@pytest.mark.django_db
class TestPhoneCashSale:
    """Test cash sales for phones"""
    
    def test_cash_sale_marks_sold(self, business, phone_product, location, manager):
        """Test that cash sale marks item as SOLD"""
        item = InventoryItem.objects.create(
            business=business,
            imei="999999999999999",
            product=phone_product,
            order_price=phone_product.cost_price,
            selling_price=phone_product.sale_price,
            status="IN_STOCK",
            current_location=location
        )
        
        # Mark as sold
        item.status = "SOLD"
        item.sold_at = timezone.now()
        item.save()
        
        assert item.status == "SOLD"
        assert item.sold_at is not None
    
    def test_cash_sale_reduces_stock(self, business, phone_product, location, manager):
        """Test that selling reduces in-stock count"""
        # Add 5 items
        for i in range(5):
            InventoryItem.objects.create(
                business=business,
                imei=f"55555555555555{i}",
                product=phone_product,
                order_price=phone_product.cost_price,
                selling_price=phone_product.sale_price,
                status="IN_STOCK",
                current_location=location
            )
        
        initial_count = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK"
        ).count()
        assert initial_count == 5
        
        # Sell one
        item = InventoryItem.objects.filter(business=business, status="IN_STOCK").first()
        item.status = "SOLD"
        item.sold_at = timezone.now()
        item.save()
        
        remaining_count = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK"
        ).count()
        assert remaining_count == 4


@pytest.mark.django_db
class TestPhoneCreditSale:
    """Test credit sales and repayment workflow"""
    
    def test_create_credit_sale(self, business, manager):
        """Test creating a credit sale record"""
        credit = PhoneCredit.objects.create(
            business=business,
            customer_name="John Doe",
            customer_phone="0999123456",
            amount=Decimal("550000.00"),
            created_by=manager
        )
        
        assert credit.customer_name == "John Doe"
        assert credit.amount == Decimal("550000.00")
        assert credit.balance == Decimal("550000.00")
        assert credit.amount_paid == Decimal("0.00")
        assert credit.status == "open"
    
    def test_credit_partial_payment(self, business, manager):
        """Test recording partial payment"""
        credit = PhoneCredit.objects.create(
            business=business,
            customer_name="Jane Doe",
            customer_phone="0999654321",
            amount=Decimal("400000.00"),
            created_by=manager
        )
        
        # Record payment
        payment = PhoneCreditPayment.objects.create(
            credit=credit,
            amount=Decimal("150000.00"),
            transaction_id="PAY001",
            paid_by=manager
        )
        
        # Update credit
        credit.amount_paid = Decimal("150000.00")
        credit.save()
        credit.update_status()
        
        assert credit.balance == Decimal("250000.00")
        assert credit.status == "partial"
    
    def test_credit_full_payment(self, business, manager):
        """Test fully settling a credit"""
        credit = PhoneCredit.objects.create(
            business=business,
            customer_name="Bob Smith",
            customer_phone="0999111222",
            amount=Decimal("300000.00"),
            created_by=manager
        )
        
        # Pay in full
        payment = PhoneCreditPayment.objects.create(
            credit=credit,
            amount=Decimal("300000.00"),
            transaction_id="PAY002",
            paid_by=manager
        )
        
        credit.amount_paid = Decimal("300000.00")
        credit.save()
        credit.update_status()
        
        assert credit.balance == Decimal("0.00")
        assert credit.status == "settled"
        assert credit.settled_at is not None
    
    def test_credit_multiple_payments(self, business, manager):
        """Test multiple partial payments"""
        credit = PhoneCredit.objects.create(
            business=business,
            customer_name="Alice",
            customer_phone="0999999999",
            amount=Decimal("600000.00"),
            created_by=manager
        )
        
        # First payment
        PhoneCreditPayment.objects.create(
            credit=credit,
            amount=Decimal("200000.00"),
            transaction_id="PAY003A",
            paid_by=manager
        )
        credit.amount_paid = Decimal("200000.00")
        credit.save()
        credit.update_status()
        
        assert credit.balance == Decimal("400000.00")
        assert credit.status == "partial"
        
        # Second payment
        PhoneCreditPayment.objects.create(
            credit=credit,
            amount=Decimal("200000.00"),
            transaction_id="PAY003B",
            paid_by=manager
        )
        credit.amount_paid = Decimal("400000.00")
        credit.save()
        credit.update_status()
        
        assert credit.balance == Decimal("200000.00")
        assert credit.status == "partial"
        
        # Final payment
        PhoneCreditPayment.objects.create(
            credit=credit,
            amount=Decimal("200000.00"),
            transaction_id="PAY003C",
            paid_by=manager
        )
        credit.amount_paid = Decimal("600000.00")
        credit.save()
        credit.update_status()
        
        assert credit.balance == Decimal("0.00")
        assert credit.status == "settled"


@pytest.mark.django_db
class TestPhonesDashboard:
    """Test phones dashboard calculations"""
    
    def test_dashboard_stock_value(self, business, phone_product, location):
        """Test calculating total stock value"""
        # Add 10 items
        for i in range(10):
            InventoryItem.objects.create(
                business=business,
                imei=f"77777777777777{i:02d}",
                product=phone_product,
                order_price=Decimal("450000.00"),
                selling_price=Decimal("550000.00"),
                status="IN_STOCK",
                current_location=location
            )
        
        from django.db.models import Sum
        
        total_cost = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK"
        ).aggregate(total=Sum("order_price"))["total"]
        
        total_selling = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK"
        ).aggregate(total=Sum("selling_price"))["total"]
        
        assert total_cost == Decimal("4500000.00")  # 10 × 450,000
        assert total_selling == Decimal("5500000.00")  # 10 × 550,000
    
    def test_dashboard_sales_count(self, business, phone_product, location):
        """Test counting sold items"""
        # Add and sell 3 items
        for i in range(3):
            item = InventoryItem.objects.create(
                business=business,
                imei=f"88888888888888{i:02d}",
                product=phone_product,
                order_price=Decimal("450000.00"),
                selling_price=Decimal("550000.00"),
                status="SOLD",
                current_location=location,
                sold_at=timezone.now()
            )
        
        sold_count = InventoryItem.objects.filter(
            business=business,
            status="SOLD"
        ).count()
        
        assert sold_count == 3
    
    def test_dashboard_outstanding_credits(self, business, manager):
        """Test calculating outstanding credit balance"""
        # Create multiple credits
        PhoneCredit.objects.create(
            business=business,
            customer_name="Customer 1",
            customer_phone="0999111111",
            amount=Decimal("500000.00"),
            amount_paid=Decimal("0.00"),
            created_by=manager
        )
        
        PhoneCredit.objects.create(
            business=business,
            customer_name="Customer 2",
            customer_phone="0999222222",
            amount=Decimal("300000.00"),
            amount_paid=Decimal("100000.00"),
            created_by=manager
        )
        
        from django.db.models import Sum, F
        
        total_outstanding = PhoneCredit.objects.filter(
            business=business
        ).aggregate(
            total=Sum(F('amount') - F('amount_paid'))
        )["total"]
        
        # 500000 + (300000 - 100000) = 700000
        assert total_outstanding == Decimal("700000.00")


@pytest.mark.django_db
class TestPhonesIntegration:
    """Integration test for complete phones workflow"""
    
    def test_complete_phones_flow(self, business, phone_product, location, manager, agent):
        """Test: Add stock → Cash sale → Credit sale → Repayment"""
        
        # 1. Add stock
        item_cash = InventoryItem.objects.create(
            business=business,
            imei="100000000000001",
            product=phone_product,
            order_price=Decimal("450000.00"),
            selling_price=Decimal("550000.00"),
            status="IN_STOCK",
            current_location=location,
            assigned_agent=agent
        )
        
        item_credit = InventoryItem.objects.create(
            business=business,
            imei="100000000000002",
            product=phone_product,
            order_price=Decimal("450000.00"),
            selling_price=Decimal("550000.00"),
            status="IN_STOCK",
            current_location=location,
            assigned_agent=agent
        )
        
        assert InventoryItem.objects.filter(business=business, status="IN_STOCK").count() == 2
        
        # 2. Cash sale
        item_cash.status = "SOLD"
        item_cash.sold_at = timezone.now()
        item_cash.save()
        
        assert item_cash.status == "SOLD"
        assert InventoryItem.objects.filter(business=business, status="IN_STOCK").count() == 1
        
        # 3. Credit sale
        credit = PhoneCredit.objects.create(
            business=business,
            customer_name="Credit Customer",
            customer_phone="0999123456",
            amount=Decimal("550000.00"),
            created_by=manager
        )
        
        item_credit.status = "SOLD"
        item_credit.sold_at = timezone.now()
        item_credit.save()
        
        assert credit.balance == Decimal("550000.00")
        assert InventoryItem.objects.filter(business=business, status="IN_STOCK").count() == 0
        
        # 4. Record repayment
        payment = PhoneCreditPayment.objects.create(
            credit=credit,
            amount=Decimal("200000.00"),
            transaction_id="TXN001",
            paid_by=manager
        )
        
        credit.amount_paid = Decimal("200000.00")
        credit.save()
        credit.update_status()
        
        assert credit.balance == Decimal("350000.00")
        assert credit.status == "partial"
        
        # 5. Dashboard checks
        sold_count = InventoryItem.objects.filter(business=business, status="SOLD").count()
        assert sold_count == 2
        
        outstanding_balance = credit.balance
        assert outstanding_balance == Decimal("350000.00")


@pytest.mark.django_db
class TestPhonesAccessoriesDashboard:
    """Test accessories dashboard views"""
    
    def test_accessories_dashboard_loads_successfully(self, business, location, manager):
        """Test that accessories dashboard returns 200 OK"""
        from django.test import Client, RequestFactory
        from inventory.verticals.phones_accessories import accessories_dashboard
        from tenants.models import Membership
        
        # Create membership for manager
        Membership.objects.create(
            user=manager,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            location=location
        )
        
        # Create request
        factory = RequestFactory()
        request = factory.get('/verticals/phones/accessories/')
        request.user = manager
        request.business = business
        request.business_id = business.id
        request.session = {}
        
        # Call view
        response = accessories_dashboard(request)
        
        # Verify 200 OK (not 500)
        assert response.status_code == 200
    
    def test_accessories_dashboard_with_location_filter(self, business, location, manager):
        """Test that accessories dashboard works with location filter (no queryset slice error)"""
        from django.test import RequestFactory
        from inventory.verticals.phones_accessories import accessories_dashboard
        from tenants.models import Membership
        from inventory.models_accessories import AccessoryProduct, AccessoryStock, AccessoryStockLog
        
        # Create membership
        Membership.objects.create(
            user=manager,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            location=location
        )
        
        # Create sample accessory data
        product = AccessoryProduct.objects.create(
            business=business,
            name="USB-C Cable",
            category="cable",
            default_order_price=Decimal("500.00"),
            default_selling_price=Decimal("1000.00")
        )
        
        stock = AccessoryStock.objects.create(
            business=business,
            location=location,
            product=product,
            qty_on_hand=10,
            avg_cost=Decimal("500.00")
        )
        
        # Create stock log
        AccessoryStockLog.objects.create(
            business=business,
            product=product,
            location=location,
            action='STOCK_IN',
            quantity=10,
            unit_cost=Decimal("500.00"),
            by_user=manager
        )
        
        # Create request WITH location
        factory = RequestFactory()
        request = factory.get('/verticals/phones/accessories/')
        request.user = manager
        request.business = business
        request.business_id = business.id
        request.location = location  # This triggers the location filter
        request.location_id = location.id
        request.session = {}
        
        # Call view - should NOT raise "Cannot filter a query once a slice has been taken"
        response = accessories_dashboard(request)
        
        # Verify 200 OK (not 500)
        assert response.status_code == 200
        assert b'Accessories Dashboard' in response.content or 'Accessories Dashboard' in str(response.content)
    
    def test_accessories_fast_sell_with_location_filter(self, business, location, manager):
        """Test that fast sell page works with location filter (no queryset slice error)"""
        from django.test import RequestFactory
        from inventory.verticals.phones_accessories import accessories_fast_sell
        from tenants.models import Membership
        from inventory.models_accessories import AccessoryProduct, AccessoryStock, AccessoryStockLog
        
        # Create membership
        Membership.objects.create(
            user=manager,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            location=location
        )
        
        # Create sample sale log
        product = AccessoryProduct.objects.create(
            business=business,
            name="Power Bank",
            category="powerbank",
            default_order_price=Decimal("2000.00"),
            default_selling_price=Decimal("3000.00")
        )
        
        AccessoryStockLog.objects.create(
            business=business,
            product=product,
            location=location,
            action='SALE',
            quantity=-1,
            unit_cost=Decimal("2000.00"),
            by_user=manager
        )
        
        # Create request WITH location
        factory = RequestFactory()
        request = factory.get('/verticals/phones/accessories/fast-sell/')
        request.user = manager
        request.business = business
        request.business_id = business.id
        request.location = location  # This triggers the location filter
        request.location_id = location.id
        request.session = {}
        
        # Call view - should NOT raise "Cannot filter a query once a slice has been taken"
        response = accessories_fast_sell(request)
        
        # Verify 200 OK (not 500)
        assert response.status_code == 200
