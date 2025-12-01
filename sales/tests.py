# sales/tests.py
"""
Tests for sales commission and bonus/penalty calculations.
"""
from datetime import time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from sales.models import Sale, SaleCommission, CommissionConfig
from timelogs.models import AgentWorkLog, WorkingHours
from tenants.models import Business
from inventory.models import Location, InventoryItem, Product

User = get_user_model()


class SaleCommissionTest(TestCase):
    """Tests for SaleCommission creation and bonus/penalty calculations."""
    
    def setUp(self):
        """Create test data."""
        self.agent = User.objects.create_user(
            username="agent1",
            email="agent1@test.com",
            password="test123",
        )
        
        self.business = Business.objects.create(
            name="Test Business",
            business_kind="phones",
        )
        
        self.location = Location.objects.create(
            name="Main Store",
            business=self.business,
            latitude=Decimal("-15.123456"),
            longitude=Decimal("35.123456"),
            geofence_radius_m=100,
        )
        
        # Create commission config with bonuses/penalties enabled
        self.config = CommissionConfig.objects.create(
            business=self.business,
            base_commission_pct=Decimal("3.00"),  # 3%
            early_bonus_per_30min=Decimal("5000.00"),
            late_penalty_per_30min=Decimal("7000.00"),
            early_bonus_enabled=True,
            lateness_penalties_enabled=True,
            is_active=True,
        )
        
        # Create working hours: 8:00 AM - 5:00 PM
        WorkingHours.objects.create(
            business=self.business,
            scheduled_start=time(8, 0),
            scheduled_end=time(17, 0),
        )
        
        # Create a product and item
        self.product = Product.objects.create(
            business=self.business,
            name="iPhone 13",
            category="phones",
        )
        
        self.today = timezone.localdate()
    
    def _create_sale(self, price=100000):
        """Helper to create a sale."""
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei="123456789012345",
            status="in_stock",
        )
        
        sale = Sale.objects.create(
            item=item,
            agent=self.agent,
            location=self.location,
            sold_at=self.today,
            price=Decimal(str(price)),
            commission_pct=Decimal("3.00"),
        )
        return sale
    
    def test_commission_without_timelogs(self):
        """Test commission creation when agent has no time logs."""
        sale = self._create_sale(price=100000)
        commission = SaleCommission.create_for_sale(sale)
        
        self.assertIsNotNone(commission)
        self.assertEqual(commission.agent, self.agent)
        self.assertEqual(commission.business, self.business)
        
        # Base commission: 3% of 100000 = 3000
        self.assertEqual(commission.base_commission, Decimal("3000.00"))
        
        # No bonuses/penalties without time logs
        self.assertEqual(commission.early_bonus, Decimal("0.00"))
        self.assertEqual(commission.late_penalty, Decimal("0.00"))
        self.assertEqual(commission.early_blocks, 0)
        self.assertEqual(commission.late_blocks, 0)
        
        # Net should equal base
        self.assertEqual(commission.net_amount, commission.base_commission)
    
    def test_commission_with_early_arrival(self):
        """Test commission with early arrival bonus."""
        # Create work log with early arrival (60 minutes early = 2 blocks)
        work_log = AgentWorkLog.objects.create(
            agent=self.agent,
            business=self.business,
            work_date=self.today,
            first_seen_at=timezone.make_aware(
                timezone.datetime.combine(self.today, time(7, 0))  # 1 hour early
            ),
        )
        
        sale = self._create_sale(price=100000)
        commission = SaleCommission.create_for_sale(sale)
        
        # Base commission: 3000
        self.assertEqual(commission.base_commission, Decimal("3000.00"))
        
        # Early bonus: 2 blocks × 5000 = 10000
        self.assertEqual(commission.early_blocks, 2)
        self.assertEqual(commission.early_bonus, Decimal("10000.00"))
        
        # No penalty
        self.assertEqual(commission.late_penalty, Decimal("0.00"))
        
        # Net: 3000 + 10000 = 13000
        self.assertEqual(commission.net_amount, Decimal("13000.00"))
    
    def test_commission_with_late_arrival(self):
        """Test commission with late arrival penalty."""
        # Enable late penalties
        self.config.lateness_penalties_enabled = True
        self.config.save()
        
        # Create work log with late arrival (90 minutes late = 3 blocks)
        work_log = AgentWorkLog.objects.create(
            agent=self.agent,
            business=self.business,
            work_date=self.today,
            first_seen_at=timezone.make_aware(
                timezone.datetime.combine(self.today, time(9, 30))  # 1.5 hours late
            ),
        )
        
        sale = self._create_sale(price=100000)
        commission = SaleCommission.create_for_sale(sale)
        
        # Base commission: 3000
        self.assertEqual(commission.base_commission, Decimal("3000.00"))
        
        # No bonus
        self.assertEqual(commission.early_bonus, Decimal("0.00"))
        
        # Late penalty: 3 blocks × 7000 = 21000
        self.assertEqual(commission.late_blocks, 3)
        self.assertEqual(commission.late_penalty, Decimal("21000.00"))
        
        # Net: 3000 - 21000 = -18000 (can go negative!)
        self.assertEqual(commission.net_amount, Decimal("-18000.00"))
    
    def test_commission_with_bonus_disabled(self):
        """Test that bonuses are not applied when disabled."""
        # Disable early bonuses
        self.config.early_bonus_enabled = False
        self.config.save()
        
        # Create work log with early arrival
        work_log = AgentWorkLog.objects.create(
            agent=self.agent,
            business=self.business,
            work_date=self.today,
            first_seen_at=timezone.make_aware(
                timezone.datetime.combine(self.today, time(7, 0))
            ),
        )
        
        sale = self._create_sale(price=100000)
        commission = SaleCommission.create_for_sale(sale)
        
        # Should have no bonus despite early arrival
        self.assertEqual(commission.early_bonus, Decimal("0.00"))
        self.assertEqual(commission.net_amount, commission.base_commission)
    
    def test_commission_with_penalty_disabled(self):
        """Test that penalties are not applied when disabled."""
        # Disable late penalties
        self.config.lateness_penalties_enabled = False
        self.config.save()
        
        # Create work log with late arrival
        work_log = AgentWorkLog.objects.create(
            agent=self.agent,
            business=self.business,
            work_date=self.today,
            first_seen_at=timezone.make_aware(
                timezone.datetime.combine(self.today, time(9, 30))
            ),
        )
        
        sale = self._create_sale(price=100000)
        commission = SaleCommission.create_for_sale(sale)
        
        # Should have no penalty despite late arrival
        self.assertEqual(commission.late_penalty, Decimal("0.00"))
        self.assertEqual(commission.net_amount, commission.base_commission)
    
    def test_commission_with_fixed_amount(self):
        """Test commission with fixed amount instead of percentage."""
        # Set fixed commission amount
        self.config.fixed_commission_amount = Decimal("5000.00")
        self.config.save()
        
        sale = self._create_sale(price=100000)
        commission = SaleCommission.create_for_sale(sale)
        
        # Should use fixed amount, not percentage
        self.assertEqual(commission.base_commission, Decimal("5000.00"))
    
    def test_multiple_sales_same_day(self):
        """Test that multiple sales on the same day use the same work log."""
        # Create work log with early arrival
        work_log = AgentWorkLog.objects.create(
            agent=self.agent,
            business=self.business,
            work_date=self.today,
            first_seen_at=timezone.make_aware(
                timezone.datetime.combine(self.today, time(7, 0))
            ),
        )
        
        # Create two sales
        sale1 = self._create_sale(price=100000)
        sale2 = self._create_sale(price=150000)
        
        commission1 = SaleCommission.create_for_sale(sale1)
        commission2 = SaleCommission.create_for_sale(sale2)
        
        # Both should reference the same work log
        self.assertEqual(commission1.work_log, work_log)
        self.assertEqual(commission2.work_log, work_log)
        
        # Both should have the same early bonus blocks
        self.assertEqual(commission1.early_blocks, 2)
        self.assertEqual(commission2.early_blocks, 2)
        
        # But different commission amounts based on sale price
        self.assertEqual(commission1.base_commission, Decimal("3000.00"))
        self.assertEqual(commission2.base_commission, Decimal("4500.00"))
    
    def test_commission_config_get_active(self):
        """Test getting active commission config."""
        config = CommissionConfig.get_active(self.business)
        self.assertIsNotNone(config)
        self.assertEqual(config, self.config)
    
    def test_commission_config_ensure_config(self):
        """Test ensure_config creates config if none exists."""
        business2 = Business.objects.create(
            name="Test Business 2",
            business_kind="gym",
        )
        
        config = CommissionConfig.ensure_config(business2)
        self.assertIsNotNone(config)
        self.assertEqual(config.business, business2)
        self.assertTrue(config.is_active)
