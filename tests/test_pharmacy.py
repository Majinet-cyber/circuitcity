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

