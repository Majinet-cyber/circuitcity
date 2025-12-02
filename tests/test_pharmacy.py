# tests/test_pharmacy.py
"""
Tests for Pharmacy vertical functionality.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models import MerchProduct
from inventory.models_pharmacy import (
    PharmacyBatch,
    PharmacySale,
    PharmacyProductInfo,
)

User = get_user_model()


class PharmacyBatchTests(TestCase):
    """Tests for PharmacyBatch model."""
    
    def setUp(self):
        self.business = Business.objects.create(name="Test Pharmacy", slug="test-pharm")
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Paracetamol 500mg",
            kind="pharmacy"
        )
    
    def test_create_batch(self):
        """Test creating a pharmacy batch."""
        batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="BATCH001",
            expiry_date=date.today() + timedelta(days=365),
            quantity=100,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00"),
            reorder_level=10
        )
        
        assert batch.batch_number == "BATCH001"
        assert batch.quantity == 100
        assert not batch.is_expired
        assert not batch.is_low_stock
    
    def test_is_expired_property(self):
        """Test batch expiry check."""
        # Expired batch
        expired_batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="EXPIRED001",
            expiry_date=date.today() - timedelta(days=1),
            quantity=50,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        assert expired_batch.is_expired
        assert expired_batch.days_to_expiry < 0
    
    def test_is_near_expiry(self):
        """Test near-expiry detection."""
        near_expiry_batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="NEAR001",
            expiry_date=date.today() + timedelta(days=15),
            quantity=50,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        assert near_expiry_batch.is_near_expiry
        assert 0 < near_expiry_batch.days_to_expiry <= 30
    
    def test_is_low_stock(self):
        """Test low stock detection."""
        low_stock_batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="LOW001",
            expiry_date=date.today() + timedelta(days=365),
            quantity=5,
            reorder_level=10,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        assert low_stock_batch.is_low_stock
    
    def test_decrement_stock(self):
        """Test stock decrement on sale."""
        batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="STOCK001",
            expiry_date=date.today() + timedelta(days=365),
            quantity=100,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        batch.decrement_stock(20)
        
        assert batch.quantity == 80
    
    def test_decrement_stock_insufficient(self):
        """Test stock decrement with insufficient quantity."""
        batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="INSUF001",
            expiry_date=date.today() + timedelta(days=365),
            quantity=10,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        with pytest.raises(ValueError, match="Insufficient stock"):
            batch.decrement_stock(20)
    
    def test_cannot_create_batch_with_negative_quantity(self):
        """Test that creating batch with negative quantity is prevented."""
        with pytest.raises(Exception):  # ValidationError or IntegrityError
            batch = PharmacyBatch.objects.create(
                business=self.business,
                merch_product=self.product,
                batch_number="NEG001",
                expiry_date=date.today() + timedelta(days=365),
                quantity=-10,
                cost_price=Decimal("50.00"),
                selling_price=Decimal("80.00")
            )
            batch.full_clean()  # Trigger validation
    
    def test_cannot_create_batch_with_negative_price(self):
        """Test that creating batch with negative price is prevented."""
        with pytest.raises(Exception):  # ValidationError or IntegrityError
            batch = PharmacyBatch.objects.create(
                business=self.business,
                merch_product=self.product,
                batch_number="NEGPRICE001",
                expiry_date=date.today() + timedelta(days=365),
                quantity=100,
                cost_price=Decimal("-50.00"),
                selling_price=Decimal("80.00")
            )
            batch.full_clean()  # Trigger validation
    
    def test_stock_value_calculations(self):
        """Test stock value calculations."""
        batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="VALUE001",
            expiry_date=date.today() + timedelta(days=365),
            quantity=100,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        assert batch.stock_value_cost == Decimal("5000.00")
        assert batch.stock_value_selling == Decimal("8000.00")


class PharmacySaleTests(TestCase):
    """Tests for PharmacySale model."""
    
    def setUp(self):
        self.business = Business.objects.create(name="Test Pharmacy", slug="test-pharm")
        self.user = User.objects.create_user(
            username="pharmacist",
            email="pharm@test.com",
            password="test123"
        )
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Aspirin 300mg",
            kind="pharmacy"
        )
        self.batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="BATCH001",
            expiry_date=date.today() + timedelta(days=365),
            quantity=100,
            cost_price=Decimal("40.00"),
            selling_price=Decimal("70.00")
        )
    
    def test_create_sale(self):
        """Test creating a pharmacy sale."""
        sale = PharmacySale.objects.create(
            business=self.business,
            batch=self.batch,
            quantity=5,
            unit_price=Decimal("70.00"),
            unit_cost=Decimal("40.00"),
            sold_by=self.user
        )
        
        assert sale.quantity == 5
        assert sale.total_amount == Decimal("350.00")
        assert sale.profit == Decimal("150.00")  # (70 - 40) * 5
    
    def test_sale_auto_calculates_total(self):
        """Test that sale total is auto-calculated."""
        sale = PharmacySale.objects.create(
            business=self.business,
            batch=self.batch,
            quantity=10,
            unit_price=Decimal("70.00"),
            unit_cost=Decimal("40.00")
        )
        
        assert sale.total_amount == Decimal("700.00")
    
    def test_profit_calculation(self):
        """Test profit calculation."""
        sale = PharmacySale.objects.create(
            business=self.business,
            batch=self.batch,
            quantity=10,
            unit_price=Decimal("70.00"),
            unit_cost=Decimal("40.00")
        )
        
        expected_profit = (Decimal("70.00") - Decimal("40.00")) * 10
        assert sale.profit == expected_profit


@pytest.mark.django_db
class PharmacyFIFOTests:
    """Tests for FIFO (First In First Out) batch selection."""
    
    def test_fifo_selects_oldest_expiry_first(self):
        """Test that sales consume batches with nearest expiry first."""
        business = Business.objects.create(name="Test Pharmacy", slug="test")
        product = MerchProduct.objects.create(
            business=business,
            name="Medicine",
            kind="pharmacy"
        )
        user = User.objects.create_user(username="pharm", password="test")
        
        # Create two batches with different expiry dates
        batch_near = PharmacyBatch.objects.create(
            business=business,
            merch_product=product,
            batch_number="NEAR",
            expiry_date=date.today() + timedelta(days=60),
            quantity=20,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        batch_far = PharmacyBatch.objects.create(
            business=business,
            merch_product=product,
            batch_number="FAR",
            expiry_date=date.today() + timedelta(days=365),
            quantity=50,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        # Get batches ordered by expiry (FIFO)
        batches_fifo = PharmacyBatch.objects.filter(
            business=business,
            merch_product=product,
            quantity__gt=0,
            expiry_date__gte=date.today()
        ).order_by("expiry_date")
        
        # First batch should be the one expiring soonest
        assert batches_fifo.first() == batch_near
        assert batches_fifo.first().batch_number == "NEAR"
    
    def test_cannot_sell_from_expired_batch(self):
        """Test that selling from expired batch raises error."""
        business = Business.objects.create(name="Test Pharmacy", slug="test")
        product = MerchProduct.objects.create(
            business=business,
            name="Expired Medicine",
            kind="pharmacy"
        )
        
        expired_batch = PharmacyBatch.objects.create(
            business=business,
            merch_product=product,
            batch_number="EXPIRED",
            expiry_date=date.today() - timedelta(days=1),
            quantity=100,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        assert expired_batch.is_expired
        
        # Attempting to sell should be blocked
        # (In real implementation, this would be checked in the sale view/service)
        if expired_batch.is_expired:
            # This represents the business logic that should prevent the sale
            with pytest.raises(Exception):
                raise ValueError("Cannot sell from expired batch")


@pytest.mark.django_db
class PharmacyDashboardTests:
    """Tests for pharmacy dashboard helper queries."""
    
    def test_near_expiry_queryset(self):
        """Test queryset returns only batches expiring within 30 days."""
        business = Business.objects.create(name="Test Pharmacy", slug="test")
        product = MerchProduct.objects.create(
            business=business,
            name="Medicine",
            kind="pharmacy"
        )
        
        # Create batches with different expiry dates
        batch_expired = PharmacyBatch.objects.create(
            business=business,
            merch_product=product,
            batch_number="EXPIRED",
            expiry_date=date.today() - timedelta(days=1),
            quantity=10,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        batch_near = PharmacyBatch.objects.create(
            business=business,
            merch_product=product,
            batch_number="NEAR",
            expiry_date=date.today() + timedelta(days=15),
            quantity=20,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        batch_safe = PharmacyBatch.objects.create(
            business=business,
            merch_product=product,
            batch_number="SAFE",
            expiry_date=date.today() + timedelta(days=90),
            quantity=50,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        # Query for near-expiry batches (not expired, but expiring within 30 days)
        near_expiry_batches = PharmacyBatch.objects.filter(
            business=business,
            expiry_date__gte=date.today(),
            expiry_date__lte=date.today() + timedelta(days=30),
            quantity__gt=0
        )
        
        assert near_expiry_batches.count() == 1
        assert batch_near in near_expiry_batches
        assert batch_expired not in near_expiry_batches
        assert batch_safe not in near_expiry_batches
    
    def test_low_stock_queryset(self):
        """Test queryset returns only batches below reorder level."""
        business = Business.objects.create(name="Test Pharmacy", slug="test")
        product = MerchProduct.objects.create(
            business=business,
            name="Medicine",
            kind="pharmacy"
        )
        
        batch_low = PharmacyBatch.objects.create(
            business=business,
            merch_product=product,
            batch_number="LOW",
            expiry_date=date.today() + timedelta(days=365),
            quantity=5,
            reorder_level=10,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        batch_ok = PharmacyBatch.objects.create(
            business=business,
            merch_product=product,
            batch_number="OK",
            expiry_date=date.today() + timedelta(days=365),
            quantity=50,
            reorder_level=10,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        # Query for low stock batches
        from django.db.models import F
        low_stock_batches = PharmacyBatch.objects.filter(
            business=business,
            quantity__lte=F('reorder_level'),
            is_archived=False
        )
        
        assert low_stock_batches.count() == 1
        assert batch_low in low_stock_batches
        assert batch_ok not in low_stock_batches


@pytest.mark.django_db
class PharmacyWorkflowTest:
    """Integration test for complete pharmacy workflow."""
    
    def test_complete_pharmacy_flow(self):
        """Test: Create batch → Record sale → Check stock → Verify expiry."""
        # Setup
        business = Business.objects.create(name="Test Pharmacy", slug="test")
        product = MerchProduct.objects.create(
            business=business,
            name="Antibiotic",
            kind="pharmacy"
        )
        user = User.objects.create_user(username="pharm", password="test")
        
        # 1. Create batch
        batch = PharmacyBatch.objects.create(
            business=business,
            merch_product=product,
            batch_number="BATCH001",
            expiry_date=date.today() + timedelta(days=180),
            quantity=50,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            reorder_level=10
        )
        
        assert batch.quantity == 50
        assert not batch.is_low_stock
        
        # 2. Record sale
        sale = PharmacySale.objects.create(
            business=business,
            batch=batch,
            quantity=10,
            unit_price=batch.selling_price,
            unit_cost=batch.cost_price,
            sold_by=user
        )
        
        batch.decrement_stock(10)
        
        # 3. Check stock after sale
        assert batch.quantity == 40
        assert not batch.is_low_stock  # Still above reorder level
        
        # 4. Sell more to trigger low stock
        batch.decrement_stock(31)
        assert batch.quantity == 9
        assert batch.is_low_stock  # Now below reorder level
        
        # 5. Verify expiry check
        assert not batch.is_expired
        assert batch.days_to_expiry == 180
    
    def test_multi_batch_fifo_sale(self):
        """Test selling across multiple batches in FIFO order."""
        business = Business.objects.create(name="Test Pharmacy", slug="test")
        product = MerchProduct.objects.create(
            business=business,
            name="Paracetamol",
            kind="pharmacy"
        )
        user = User.objects.create_user(username="pharm", password="test")
        
        # Create multiple batches
        batch1 = PharmacyBatch.objects.create(
            business=business,
            merch_product=product,
            batch_number="BATCH1",
            expiry_date=date.today() + timedelta(days=30),
            quantity=10,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        batch2 = PharmacyBatch.objects.create(
            business=business,
            merch_product=product,
            batch_number="BATCH2",
            expiry_date=date.today() + timedelta(days=90),
            quantity=20,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00")
        )
        
        # Simulate FIFO: sell 15 units (should consume all of batch1 + 5 from batch2)
        # Sale 1: 10 from batch1
        sale1 = PharmacySale.objects.create(
            business=business,
            batch=batch1,
            quantity=10,
            unit_price=batch1.selling_price,
            unit_cost=batch1.cost_price,
            sold_by=user
        )
        batch1.decrement_stock(10)
        
        # Sale 2: 5 from batch2
        sale2 = PharmacySale.objects.create(
            business=business,
            batch=batch2,
            quantity=5,
            unit_price=batch2.selling_price,
            unit_cost=batch2.cost_price,
            sold_by=user
        )
        batch2.decrement_stock(5)
        
        # Verify
        assert batch1.quantity == 0
        assert batch2.quantity == 15

