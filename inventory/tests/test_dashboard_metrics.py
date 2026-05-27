# inventory/tests/test_dashboard_metrics.py
"""
Tests for dashboard metrics service - verifying admin wallet costs are included.
"""
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models import Product, InventoryItem, Location
from sales.models import Sale
from wallet.models import WalletTransaction, Ledger, TxnType
from inventory.services.dashboard_metrics import get_inventory_kpis

User = get_user_model()


class DashboardMetricsTestCase(TestCase):
    """Test that admin wallet costs are properly included in dashboard metrics."""

    def setUp(self):
        """Create test data: business, location, product, sale, and admin costs."""
        # Create business
        from inventory.business_kinds import BusinessKind

        self.business = Business.objects.create(
            name="Test Business", slug="test-business", business_kind=BusinessKind.PHONES, status="ACTIVE"
        )
        
        # Disable commissions for this business to isolate admin costs testing
        # (Commission tests should be separate; this tests admin costs specifically)
        self._disable_commissions()

        # Create location
        self.location = Location.objects.create(business=self.business, name="Main Store", city="Test City")

        # Create user/agent
        self.user = User.objects.create_user(username="testagent", email="agent@test.com", password="testpass123")

        # Create product
        self.product = Product.objects.create(
            business=self.business,
            brand="Test Brand",
            model="Test Model",
            variant="Test Variant",
            order_price=Decimal("100000.00"),  # MK 100,000 cost
            selling_price=Decimal("150000.00"),  # MK 150,000 selling
        )

        # Create inventory item
        self.item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            status="SOLD",
            imei="123456789012345",
            order_price=Decimal("100000.00"),
            selling_price=Decimal("150000.00"),
            assigned_agent=self.user,
            sold_at=timezone.now(),
        )

        # Create sale record
        self.sale = Sale.objects.create(
            item=self.item,
            agent=self.user,
            location=self.location,
            sold_at=timezone.now().date(),
            price=Decimal("150000.00"),
            payment_method="CASH",
        )

        # Date range for tests (today)
        now = timezone.now()
        self.start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.end_date = self.start_date + timedelta(days=1)

    def _disable_commissions(self):
        """Disable commissions for the test business to isolate admin costs testing."""
        try:
            from sales.models import CommissionConfig
            CommissionConfig.objects.update_or_create(
                business=self.business,
                defaults={
                    "commissions_enabled": False,
                    "commission_mode": "PERCENT",
                },
            )
        except ImportError:
            pass  # CommissionConfig may not exist

    def test_admin_wallet_costs_included_in_inventory_dashboard(self):
        """Test that admin wallet costs are included in dashboard metrics."""
        # Create an admin cost (e.g., rent)
        admin_cost = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),  # MK 50,000 cost (negative)
            note="Office rent",
            effective_date=timezone.now().date(),
            is_recurring=False,
        )

        # Build sales queryset
        sales_qs = Sale.objects.filter(
            item__business=self.business,
            created_at__gte=self.start_date,
            created_at__lt=self.end_date,
        )

        # Get KPIs from metrics service
        kpis = get_inventory_kpis(
            business=self.business,
            location=self.location,
            sales_qs=sales_qs,
            start_date=self.start_date,
            end_date=self.end_date,
        )

        # Assert metrics
        self.assertEqual(kpis["total_revenue"], Decimal("150000.00"))  # Revenue from sale
        self.assertEqual(kpis["total_cogs"], Decimal("100000.00"))  # COGS from item
        self.assertEqual(kpis["total_admin_costs"], Decimal("50000.00"))  # Admin cost (converted to positive)
        self.assertEqual(kpis["total_costs"], Decimal("150000.00"))  # COGS + Admin = 100k + 50k
        self.assertEqual(kpis["total_profit"], Decimal("0.00"))  # Revenue - Total Costs = 150k - 150k
        self.assertEqual(kpis["profit_margin"], 0.0)  # 0% margin

    def test_admin_wallet_costs_without_sales(self):
        """Test that admin costs are tracked even when there are no sales."""
        # Delete the sale
        self.sale.delete()
        self.item.status = "IN_STOCK"
        self.item.sold_at = None
        self.item.save()

        # Create admin cost
        admin_cost = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-30000.00"),  # MK 30,000 cost
            note="Utilities",
            effective_date=timezone.now().date(),
            is_recurring=False,
        )

        # Build sales queryset (empty)
        sales_qs = Sale.objects.filter(
            item__business=self.business,
            created_at__gte=self.start_date,
            created_at__lt=self.end_date,
        )

        # Get KPIs
        kpis = get_inventory_kpis(
            business=self.business,
            location=self.location,
            sales_qs=sales_qs,
            start_date=self.start_date,
            end_date=self.end_date,
        )

        # Assert
        self.assertEqual(kpis["total_revenue"], Decimal("0.00"))
        self.assertEqual(kpis["total_cogs"], Decimal("0.00"))
        self.assertEqual(kpis["total_admin_costs"], Decimal("30000.00"))
        self.assertEqual(kpis["total_costs"], Decimal("30000.00"))
        self.assertEqual(kpis["total_profit"], Decimal("-30000.00"))  # Negative profit (loss)

    def test_multiple_admin_costs_aggregated(self):
        """Test that multiple admin costs are properly aggregated."""
        # Create multiple admin costs
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-20000.00"),
            note="Rent",
            effective_date=timezone.now().date(),
            is_recurring=False,
        )

        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-15000.00"),
            note="Utilities",
            effective_date=timezone.now().date(),
            is_recurring=False,
        )

        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-10000.00"),
            note="Marketing",
            effective_date=timezone.now().date(),
            is_recurring=False,
        )

        # Build sales queryset
        sales_qs = Sale.objects.filter(
            item__business=self.business,
            created_at__gte=self.start_date,
            created_at__lt=self.end_date,
        )

        # Get KPIs
        kpis = get_inventory_kpis(
            business=self.business,
            location=self.location,
            sales_qs=sales_qs,
            start_date=self.start_date,
            end_date=self.end_date,
        )

        # Assert - total admin costs should be sum of all three
        self.assertEqual(kpis["total_admin_costs"], Decimal("45000.00"))  # 20k + 15k + 10k
        self.assertEqual(kpis["total_costs"], Decimal("145000.00"))  # COGS (100k) + Admin (45k)
        self.assertEqual(kpis["total_profit"], Decimal("5000.00"))  # Revenue (150k) - Costs (145k)
        self.assertAlmostEqual(kpis["profit_margin"], 3.33, places=1)  # ~3.33%

    def test_recurring_costs_included(self):
        """Test that recurring costs are included in metrics."""
        # Create a recurring cost that started before the period
        recurring_cost = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal("-25000.00"),  # Monthly rent
            note="Monthly rent",
            effective_date=timezone.now().date() - timedelta(days=30),
            effective_from=timezone.now().date() - timedelta(days=30),
            is_recurring=True,
            recurrence="monthly",
        )

        # Build sales queryset
        sales_qs = Sale.objects.filter(
            item__business=self.business,
            created_at__gte=self.start_date,
            created_at__lt=self.end_date,
        )

        # Get KPIs
        kpis = get_inventory_kpis(
            business=self.business,
            location=self.location,
            sales_qs=sales_qs,
            start_date=self.start_date,
            end_date=self.end_date,
        )

        # Assert - recurring cost should be included
        self.assertEqual(kpis["total_admin_costs"], Decimal("25000.00"))
        self.assertEqual(kpis["total_costs"], Decimal("125000.00"))  # COGS (100k) + Admin (25k)
        self.assertEqual(kpis["total_profit"], Decimal("25000.00"))  # Revenue (150k) - Costs (125k)
        self.assertAlmostEqual(kpis["profit_margin"], 16.67, places=1)  # ~16.67%

    def test_costs_from_different_business_excluded(self):
        """Test that costs from other businesses are not included."""
        # Create another business
        from inventory.business_kinds import BusinessKind

        other_business = Business.objects.create(
            name="Other Business", slug="other-business", business_kind=BusinessKind.PHONES, status="ACTIVE"
        )

        # Create admin cost for OTHER business
        other_cost = WalletTransaction.objects.create(
            business=other_business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-100000.00"),
            note="Other business cost",
            effective_date=timezone.now().date(),
            is_recurring=False,
        )

        # Create admin cost for OUR business
        our_cost = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-10000.00"),
            note="Our business cost",
            effective_date=timezone.now().date(),
            is_recurring=False,
        )

        # Build sales queryset
        sales_qs = Sale.objects.filter(
            item__business=self.business,
            created_at__gte=self.start_date,
            created_at__lt=self.end_date,
        )

        # Get KPIs
        kpis = get_inventory_kpis(
            business=self.business,
            location=self.location,
            sales_qs=sales_qs,
            start_date=self.start_date,
            end_date=self.end_date,
        )

        # Assert - only OUR business costs should be included
        self.assertEqual(kpis["total_admin_costs"], Decimal("10000.00"))  # Only our cost
        self.assertNotEqual(kpis["total_admin_costs"], Decimal("110000.00"))  # Should NOT include other

    def test_costs_outside_date_range_excluded(self):
        """Test that costs outside the selected date range are excluded."""
        # Create cost BEFORE the period
        old_cost = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-50000.00"),
            note="Old cost",
            effective_date=timezone.now().date() - timedelta(days=10),
            is_recurring=False,
        )

        # Create cost IN the period
        current_cost = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-30000.00"),
            note="Current cost",
            effective_date=timezone.now().date(),
            is_recurring=False,
        )

        # Build sales queryset
        sales_qs = Sale.objects.filter(
            item__business=self.business,
            created_at__gte=self.start_date,
            created_at__lt=self.end_date,
        )

        # Get KPIs
        kpis = get_inventory_kpis(
            business=self.business,
            location=self.location,
            sales_qs=sales_qs,
            start_date=self.start_date,
            end_date=self.end_date,
        )

        # Assert - only current cost should be included
        self.assertEqual(kpis["total_admin_costs"], Decimal("30000.00"))  # Only current cost
        self.assertNotEqual(kpis["total_admin_costs"], Decimal("80000.00"))  # Should NOT include old
