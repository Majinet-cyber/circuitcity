# tests/test_verticals_liquor.py
"""
Tests for liquor store functionality: products, sales, credits, payments.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_verticals import (
    LiquorSale, LiquorCredit, LiquorCreditPayment, LiquorStockEditRequest,
    LiquorWalletEntry, LiquorUnitType, LiquorSaleType, LiquorCreditStatus,
    LiquorCreditPaymentStatus
)
from tenants.models import Business

User = get_user_model()


@pytest.fixture
def business():
    """Create a test liquor business"""
    return Business.objects.create(
        name="Test Liquor Store",
        slug="test-liquor",
        status="ACTIVE",
        business_kind=BusinessKind.LIQUOR
    )


@pytest.fixture
def manager(business):
    """Create a manager user"""
    user = User.objects.create_user(username="manager", password="pass")
    user.is_staff = False
    user.save()
    return user


@pytest.fixture
def bartender(business):
    """Create a bartender user"""
    user = User.objects.create_user(username="bartender", password="pass")
    user.is_staff = False
    user.save()
    return user


@pytest.fixture
def liquor_product(business):
    """Create a liquor product with shots"""
    return MerchProduct.objects.create(
        business=business,
        name="Test Whiskey",
        kind=BusinessKind.LIQUOR,
        category="spirits",
        has_shots=True,
        shots_per_bottle=25,
        barman_shots_reserved=2,
        price_per_bottle=Decimal("15000.00"),
        price_per_shot=Decimal("750.00"),
        is_active=True
    )


@pytest.mark.django_db
class TestLiquorProduct:
    """Test liquor product configuration"""
    
    def test_sellable_shots_calculation(self, liquor_product):
        """Test that sellable shots = total - reserved"""
        assert liquor_product.sellable_shots_per_bottle == 23
    
    def test_product_with_no_shots(self, business):
        """Test product without shots"""
        product = MerchProduct.objects.create(
            business=business,
            name="Beer",
            kind=BusinessKind.LIQUOR,
            category="beer",
            has_shots=False,
            price_per_bottle=Decimal("2000.00"),
            is_active=True
        )
        assert product.sellable_shots_per_bottle == 0


@pytest.mark.django_db
class TestLiquorSales:
    """Test liquor sales (bottle vs shot)"""
    
    def test_bottle_sale(self, business, liquor_product, bartender):
        """Test selling a bottle"""
        sale = LiquorSale.objects.create(
            business=business,
            product=liquor_product,
            unit=LiquorUnitType.BOTTLE,
            quantity=2,
            unit_price=liquor_product.price_per_bottle,
            sold_by=bartender
        )
        
        assert sale.total_price == Decimal("30000.00")  # 2 × 15000
        assert sale.is_credit is False
        assert sale.sale_type == LiquorSaleType.SALE
    
    def test_shot_sale(self, business, liquor_product, bartender):
        """Test selling shots"""
        sale = LiquorSale.objects.create(
            business=business,
            product=liquor_product,
            unit=LiquorUnitType.SHOT,
            quantity=10,
            unit_price=liquor_product.price_per_shot,
            sold_by=bartender
        )
        
        assert sale.total_price == Decimal("7500.00")  # 10 × 750
        assert sale.unit == LiquorUnitType.SHOT
    
    def test_credit_sale(self, business, liquor_product, bartender):
        """Test credit sale creates credit record"""
        sale = LiquorSale.objects.create(
            business=business,
            product=liquor_product,
            unit=LiquorUnitType.BOTTLE,
            quantity=1,
            unit_price=liquor_product.price_per_bottle,
            sale_type=LiquorSaleType.CREDIT,
            sold_by=bartender
        )
        
        assert sale.is_credit is True
        assert sale.sale_type == LiquorSaleType.CREDIT


@pytest.mark.django_db
class TestLiquorCredit:
    """Test credit system"""
    
    def test_create_credit(self, business, manager):
        """Test creating a credit record"""
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name="John Doe",
            customer_phone="0999123456",
            amount=Decimal("10000.00"),
            created_by=manager
        )
        
        assert credit.status == LiquorCreditStatus.OPEN
        assert credit.balance == Decimal("10000.00")
        assert credit.amount_paid == Decimal("0.00")
    
    def test_credit_payment_updates_balance(self, business, manager):
        """Test that payment updates credit balance"""
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name="Jane Doe",
            customer_phone="0999654321",
            amount=Decimal("5000.00"),
            created_by=manager
        )
        
        # Simulate payment
        credit.amount_paid = Decimal("2000.00")
        credit.save()
        credit.update_status()
        
        assert credit.balance == Decimal("3000.00")
        assert credit.status == LiquorCreditStatus.PARTIAL
    
    def test_credit_fully_settled(self, business, manager):
        """Test credit marked as settled when fully paid"""
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name="Bob Smith",
            customer_phone="0999111222",
            amount=Decimal("8000.00"),
            created_by=manager
        )
        
        credit.amount_paid = Decimal("8000.00")
        credit.save()
        credit.update_status()
        
        assert credit.status == LiquorCreditStatus.SETTLED
        assert credit.balance == Decimal("0.00")
        assert credit.settled_at is not None


@pytest.mark.django_db
class TestLiquorCreditPayment:
    """Test credit payment approval workflow"""
    
    def test_bartender_submits_payment(self, business, manager, bartender):
        """Test bartender submits payment with proof"""
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name="Alice",
            customer_phone="0999999999",
            amount=Decimal("5000.00"),
            created_by=manager
        )
        
        payment = LiquorCreditPayment.objects.create(
            credit=credit,
            amount=Decimal("2000.00"),
            transaction_id="TXN12345",
            paid_by=bartender
        )
        
        assert payment.status == LiquorCreditPaymentStatus.PENDING
        assert payment.reviewed_by is None
    
    def test_manager_approves_payment(self, business, manager, bartender):
        """Test manager approves payment"""
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name="Charlie",
            customer_phone="0999888777",
            amount=Decimal("10000.00"),
            created_by=manager
        )
        
        payment = LiquorCreditPayment.objects.create(
            credit=credit,
            amount=Decimal("5000.00"),
            transaction_id="TXN67890",
            paid_by=bartender
        )
        
        # Manager approves
        payment.approve(manager)
        
        assert payment.status == LiquorCreditPaymentStatus.APPROVED
        assert payment.reviewed_by == manager
        assert payment.reviewed_at is not None
        
        # Check credit updated
        credit.refresh_from_db()
        assert credit.amount_paid == Decimal("5000.00")
        assert credit.status == LiquorCreditStatus.PARTIAL
    
    def test_manager_rejects_payment(self, business, manager, bartender):
        """Test manager rejects payment"""
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name="David",
            customer_phone="0999777666",
            amount=Decimal("3000.00"),
            created_by=manager
        )
        
        payment = LiquorCreditPayment.objects.create(
            credit=credit,
            amount=Decimal("1000.00"),
            transaction_id="TXN11111",
            paid_by=bartender
        )
        
        # Manager rejects
        payment.reject(manager, reason="Invalid proof")
        
        assert payment.status == LiquorCreditPaymentStatus.REJECTED
        assert payment.review_reason == "Invalid proof"
        
        # Credit should not be updated
        credit.refresh_from_db()
        assert credit.amount_paid == Decimal("0.00")


@pytest.mark.django_db
class TestLiquorStockEditRequest:
    """Test stock edit request workflow"""
    
    def test_bartender_requests_edit(self, business, liquor_product, bartender):
        """Test bartender creates stock edit request"""
        request = LiquorStockEditRequest.objects.create(
            business=business,
            product=liquor_product,
            requested_changes={"quantity": 50},
            reason="Received new stock",
            requested_by=bartender
        )
        
        assert request.status == "pending"
        assert request.reviewed_by is None


@pytest.mark.django_db
class TestLiquorWalletEntry:
    """Test wallet entries for liquor business"""
    
    def test_create_income_entry(self, business, liquor_product, bartender):
        """Test creating income wallet entry from sale"""
        sale = LiquorSale.objects.create(
            business=business,
            product=liquor_product,
            unit=LiquorUnitType.BOTTLE,
            quantity=1,
            unit_price=Decimal("15000.00"),
            sold_by=bartender
        )
        
        entry = LiquorWalletEntry.objects.create(
            business=business,
            amount=sale.total_price,
            description=f"Sale of {liquor_product.name}",
            entry_type="income",
            related_sale=sale,
            created_by=bartender
        )
        
        assert entry.entry_type == "income"
        assert entry.amount == Decimal("15000.00")

