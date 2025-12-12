# tests/test_wallet_phones_agent_fixes.py
"""
Tests for Phones Agent Wallet 4 Critical Fixes:
1. Units sold shows correct count (1 sale = 1 unit, not 2)
2. Commission rate is 3% (not 12%)
3. No duplicate commission transactions
4. Ranking works in wallet (not "unavailable")
5. Payslip updates immediately after sales
"""
from decimal import Decimal
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

User = get_user_model()


@pytest.mark.django_db
class TestPhonesAgentWalletFixes(TestCase):
    """Test suite for phones agent wallet critical fixes."""
    
    def setUp(self):
        """Set up test data."""
        # Create business
        from tenants.models import Business, Location, Membership
        self.business = Business.objects.create(
            name="Test Phones Shop",
            business_kind="phones",
        )
        
        self.location = Location.objects.create(
            name="Main Store",
            business=self.business,
            latitude=Decimal("-15.123"),
            longitude=Decimal("35.123"),
        )
        
        # Create agent user
        self.agent = User.objects.create_user(
            username="testagent",
            email="agent@test.com",
            password="testpass123",
            first_name="Test",
            last_name="Agent",
        )
        
        # Create agent membership
        self.membership = Membership.objects.create(
            user=self.agent,
            business=self.business,
            role="AGENT",
            status="ACTIVE",
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="testmanager",
            email="manager@test.com",
            password="testpass123",
            is_staff=True,
        )
        
        self.client = Client()
    
    def _create_phone_sale(self, price=Decimal("500000.00"), agent=None):
        """Helper to create a phone sale."""
        from inventory.models import InventoryItem
        from sales.models import Sale
        
        if agent is None:
            agent = self.agent
        
        # Create inventory item
        item = InventoryItem.objects.create(
            business=self.business,
            current_location=self.location,
            imei="123456789012345",
            brand="Samsung",
            model="Galaxy S21",
            variant="128GB Black",
            status="SOLD",
            selling_price=price,
            order_price=Decimal("400000.00"),
            assigned_agent=agent,
            sold_at=timezone.now(),
        )
        
        # Create sale (this triggers commission signal)
        sale = Sale.objects.create(
            item=item,
            agent=agent,
            location=self.location,
            sold_at=timezone.localdate(),
            price=price,
            commission_pct=Decimal("3.00"),  # 3%
            payment_method="CASH",
        )
        
        return sale, item
    
    def test_fix1_units_sold_correct_after_one_sale(self):
        """
        FIX 1: After 1 phone sale, wallet should show 1 unit sold (not 2).
        
        Root cause: Duplicate signals were creating 2 commission transactions per sale.
        Fix: Removed duplicate signal in wallet/signals.py, kept only sales/signals.py
        """
        # Create one sale
        sale, item = self._create_phone_sale(price=Decimal("500000.00"))
        
        # Get agent earnings
        from inventory.services.agent_earnings import get_agent_earnings
        
        earnings = get_agent_earnings(
            business=self.business,
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
            agent_id=self.agent.id,
        )
        
        # Should have exactly 1 agent in results
        self.assertEqual(len(earnings), 1)
        
        # Should show 1 unit sold (not 2)
        agent_data = earnings[0]
        self.assertEqual(agent_data.units_sold, 1, "Units sold should be 1 after 1 sale")
        
        # Verify commission transaction count
        from wallet.models import WalletTransaction, TxnType, Ledger
        
        commission_txns = WalletTransaction.objects.filter(
            business=self.business,
            agent=self.agent,
            type=TxnType.COMMISSION,
        )
        
        # Should have exactly 1 commission transaction (not 2)
        self.assertEqual(
            commission_txns.count(), 
            1, 
            "Should have exactly 1 commission transaction per sale (no duplicates)"
        )
    
    def test_fix2_commission_rate_is_3_percent(self):
        """
        FIX 2: Commission rate should be 3% (not 12%).
        
        Root cause: Default was hardcoded to 12% in tenants/utils_commission.py
        Fix: Changed default from 0.12 to 0.03
        """
        sale_price = Decimal("500000.00")
        expected_commission = sale_price * Decimal("0.03")  # 3% = MK 15,000
        
        # Create sale
        sale, item = self._create_phone_sale(price=sale_price)
        
        # Check commission percentage used
        from tenants.utils_commission import get_phone_commission_pct
        
        commission_pct = get_phone_commission_pct(self.business, is_agent_sale=True)
        self.assertEqual(
            commission_pct, 
            Decimal("0.03"), 
            "Commission rate should be 3% (0.03 fraction)"
        )
        
        # Verify actual commission amount in wallet
        from wallet.models import WalletTransaction, TxnType, Ledger
        
        commission_txn = WalletTransaction.objects.filter(
            business=self.business,
            agent=self.agent,
            type=TxnType.COMMISSION,
        ).first()
        
        self.assertIsNotNone(commission_txn, "Commission transaction should exist")
        self.assertEqual(
            commission_txn.amount,
            expected_commission,
            f"Commission should be {expected_commission} (3% of {sale_price})"
        )
        
        # Verify in earnings data
        from inventory.services.agent_earnings import get_agent_earnings
        
        earnings = get_agent_earnings(
            business=self.business,
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
            agent_id=self.agent.id,
        )
        
        agent_data = earnings[0]
        self.assertEqual(
            agent_data.total_commission,
            expected_commission,
            f"Total commission should be {expected_commission}"
        )
    
    def test_fix3_no_duplicate_commissions(self):
        """
        FIX 3: Ensure commission is created only once per sale (idempotent).
        
        Root cause: Two signals (sales/signals.py and wallet/signals.py) both creating commissions
        Fix: Removed duplicate wallet/signals.py handler, added idempotency check in sales/signals.py
        """
        # Create sale
        sale, item = self._create_phone_sale(price=Decimal("500000.00"))
        
        from wallet.models import WalletTransaction, TxnType, Ledger
        
        # Count commission transactions for this sale
        commission_txns = WalletTransaction.objects.filter(
            business=self.business,
            agent=self.agent,
            type=TxnType.COMMISSION,
            meta__sale_id=sale.id,
        )
        
        # Should have exactly 1 commission
        self.assertEqual(
            commission_txns.count(),
            1,
            "Should have exactly 1 commission transaction per sale"
        )
        
        # Try to manually trigger the signal again (simulate duplicate)
        from sales.signals import create_commission_on_sale
        
        # This should not create a duplicate (idempotency check)
        create_commission_on_sale(
            sender=type(sale),
            instance=sale,
            created=True,
        )
        
        # Count again
        commission_txns_after = WalletTransaction.objects.filter(
            business=self.business,
            agent=self.agent,
            type=TxnType.COMMISSION,
            meta__sale_id=sale.id,
        )
        
        # Should still be exactly 1 (idempotency worked)
        self.assertEqual(
            commission_txns_after.count(),
            1,
            "Idempotency check should prevent duplicate commissions"
        )
    
    def test_fix4_ranking_works_in_wallet(self):
        """
        FIX 4: Ranking should work in wallet (not show "Ranking unavailable").
        
        Root cause: api_ranking endpoint wasn't using the correct service
        Fix: Updated wallet/views.py api_ranking to use agent_earnings service
        """
        # Create sales for multiple agents
        sale1, _ = self._create_phone_sale(price=Decimal("500000.00"))
        
        # Create another agent
        agent2 = User.objects.create_user(
            username="agent2",
            email="agent2@test.com",
            password="test",
            first_name="Agent",
            last_name="Two",
        )
        
        membership2 = Membership.objects.create(
            user=agent2,
            business=self.business,
            role="AGENT",
            status="ACTIVE",
        )
        
        sale2, _ = self._create_phone_sale(price=Decimal("800000.00"), agent=agent2)
        
        # Test API endpoint
        self.client.login(username="testagent", password="testpass123")
        
        # Call ranking API
        response = self.client.get(
            reverse('wallet:api_ranking'),
            {'period': 'month'}
        )
        
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn('rows', data)
        self.assertIn('period', data)
        
        # Should have 2 agents in ranking
        rows = data['rows']
        self.assertEqual(len(rows), 2, "Ranking should show both agents")
        
        # Verify ranking is sorted by commission (descending)
        self.assertGreater(
            rows[0]['total'],
            rows[1]['total'],
            "Ranking should be sorted by total commission"
        )
        
        # Agent2 should be #1 (higher sale)
        self.assertEqual(rows[0]['agent__id'], agent2.id)
        
        # Agent1 should be #2
        self.assertEqual(rows[1]['agent__id'], self.agent.id)
    
    def test_fix5_payslip_updates_immediately(self):
        """
        FIX 5: Payslip widget should show earnings immediately after sale.
        
        Root cause: Payslip widget only showed formal Payslip records (manager-issued)
        Fix: Compute dynamic payslips from WalletTransaction commissions
        """
        # Create sale
        sale, item = self._create_phone_sale(price=Decimal("500000.00"))
        
        # Login as agent
        self.client.login(username="testagent", password="testpass123")
        
        # Access wallet page
        response = self.client.get(reverse('wallet:agent_wallet'))
        
        self.assertEqual(response.status_code, 200)
        
        # Check context for payslips
        payslips = response.context.get('payslips', [])
        
        # Should have at least 1 payslip entry (dynamic computed)
        self.assertGreater(
            len(payslips),
            0,
            "Payslips should show at least 1 entry after sale"
        )
        
        # Check that the current month appears
        current_year = timezone.now().year
        current_month = timezone.now().month
        
        current_month_payslip = None
        for p in payslips:
            if p.year == current_year and p.month == current_month:
                current_month_payslip = p
                break
        
        self.assertIsNotNone(
            current_month_payslip,
            "Current month should appear in payslips"
        )
        
        # Verify gross amount matches commission
        expected_commission = Decimal("500000.00") * Decimal("0.03")
        self.assertEqual(
            current_month_payslip.gross,
            expected_commission,
            f"Payslip gross should be {expected_commission}"
        )
    
    def test_integration_multiple_sales_correct_totals(self):
        """
        Integration test: Multiple sales should show correct totals.
        """
        # Create 3 sales
        prices = [Decimal("500000.00"), Decimal("750000.00"), Decimal("600000.00")]
        
        for price in prices:
            self._create_phone_sale(price=price)
        
        # Get earnings
        from inventory.services.agent_earnings import get_agent_earnings
        
        earnings = get_agent_earnings(
            business=self.business,
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
            agent_id=self.agent.id,
        )
        
        agent_data = earnings[0]
        
        # Should show 3 units sold
        self.assertEqual(agent_data.units_sold, 3, "Should show 3 units sold")
        
        # Total revenue
        expected_revenue = sum(prices)
        self.assertEqual(agent_data.total_revenue, expected_revenue)
        
        # Total commission (3% of total)
        expected_commission = sum(p * Decimal("0.03") for p in prices)
        self.assertEqual(agent_data.total_commission, expected_commission)
        
        # Verify transaction count
        from wallet.models import WalletTransaction, TxnType, Ledger
        
        commission_txns = WalletTransaction.objects.filter(
            business=self.business,
            agent=self.agent,
            type=TxnType.COMMISSION,
        )
        
        # Should have exactly 3 commission transactions
        self.assertEqual(commission_txns.count(), 3)
    
    def test_business_isolation(self):
        """
        Test that wallet queries are properly scoped to business (no leakage).
        """
        # Create another business
        from tenants.models import Business, Location, Membership
        
        business2 = Business.objects.create(
            name="Another Shop",
            business_kind="phones",
        )
        
        location2 = Location.objects.create(
            name="Other Store",
            business=business2,
            latitude=Decimal("-15.456"),
            longitude=Decimal("35.456"),
        )
        
        # Create agent in second business
        agent2 = User.objects.create_user(
            username="otheragent",
            email="other@test.com",
            password="test",
        )
        
        membership2 = Membership.objects.create(
            user=agent2,
            business=business2,
            role="AGENT",
            status="ACTIVE",
        )
        
        # Create sale in business1
        self._create_phone_sale(price=Decimal("500000.00"))
        
        # Create sale in business2
        from inventory.models import InventoryItem
        from sales.models import Sale
        
        item2 = InventoryItem.objects.create(
            business=business2,
            current_location=location2,
            imei="999888777666555",
            brand="iPhone",
            model="14 Pro",
            variant="256GB",
            status="SOLD",
            selling_price=Decimal("1000000.00"),
            order_price=Decimal("800000.00"),
            assigned_agent=agent2,
            sold_at=timezone.now(),
        )
        
        sale2 = Sale.objects.create(
            item=item2,
            agent=agent2,
            location=location2,
            sold_at=timezone.localdate(),
            price=Decimal("1000000.00"),
            commission_pct=Decimal("3.00"),
            payment_method="CASH",
        )
        
        # Query business1 earnings - should only see business1 sales
        from inventory.services.agent_earnings import get_agent_earnings
        
        earnings1 = get_agent_earnings(
            business=self.business,
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
        )
        
        # Should have exactly 1 agent from business1
        self.assertEqual(len(earnings1), 1)
        self.assertEqual(earnings1[0].agent_id, self.agent.id)
        self.assertEqual(earnings1[0].units_sold, 1)
        
        # Query business2 earnings - should only see business2 sales
        earnings2 = get_agent_earnings(
            business=business2,
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
        )
        
        # Should have exactly 1 agent from business2
        self.assertEqual(len(earnings2), 1)
        self.assertEqual(earnings2[0].agent_id, agent2.id)
        self.assertEqual(earnings2[0].units_sold, 1)


@pytest.mark.django_db
class TestCommissionRateConfiguration(TestCase):
    """Test commission rate configuration."""
    
    def setUp(self):
        """Set up test data."""
        from tenants.models import Business
        
        self.business = Business.objects.create(
            name="Test Shop",
            business_kind="phones",
        )
    
    def test_default_commission_rate_is_3_percent(self):
        """Default commission rate should be 3%."""
        from tenants.utils_commission import get_phone_commission_pct
        
        rate = get_phone_commission_pct(self.business, is_agent_sale=True)
        
        self.assertEqual(rate, Decimal("0.03"), "Default rate should be 3% (0.03)")
    
    def test_commission_config_override(self):
        """If CommissionConfig exists, it should override default."""
        try:
            from sales.models import CommissionConfig
            
            # Create config with 5% commission
            config = CommissionConfig.objects.create(
                business=self.business,
                base_commission_pct=Decimal("5.00"),
                is_active=True,
            )
            
            from tenants.utils_commission import get_phone_commission_pct
            
            rate = get_phone_commission_pct(self.business, is_agent_sale=True)
            
            self.assertEqual(rate, Decimal("0.05"), "Should use config rate of 5% (0.05)")
            
        except ImportError:
            # CommissionConfig not available, skip
            self.skipTest("CommissionConfig model not available")

