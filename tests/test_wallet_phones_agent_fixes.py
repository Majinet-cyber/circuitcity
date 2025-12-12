# tests/test_wallet_phones_agent_fixes.py
"""
Tests for Phones Agent Wallet 4 Critical Fixes:
1. Units sold shows correct count (1 sale = 1 unit, not 2)
2. Commission rate is 3% (not 12%)
3. No duplicate commission transactions
4. Ranking works in wallet (not "unavailable")
5. Payslip updates immediately after sales
6. Base salary MWK 50,000 per month for Phones agents
"""
from decimal import Decimal
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from wallet.models import Ledger, TxnType

User = get_user_model()


def set_active_business_session(client, business_id, location_id=None):
    """
    Set session business/location context to match middleware expectations.
    
    This ensures views that depend on session['active_business_id'] work correctly.
    Uses 'biz_id' (legacy key) that get_active_business() actually reads from.
    """
    session = client.session
    # Match middleware expectations (keys seen in template context)
    session["active_business_id"] = business_id
    session["biz_id"] = business_id  # Legacy key that get_active_business() reads
    if location_id is not None:
        session["active_location_id"] = location_id
        session["location_id"] = location_id
    session.save()


@pytest.mark.django_db
class TestPhonesAgentWalletFixes(TestCase):
    """Test suite for phones agent wallet critical fixes."""
    
    def setUp(self):
        """Set up test data."""
        # Create business
        from tenants.models import Business, Membership
        from inventory.models import Location
        self.business = Business.objects.create(
            name="Test Phones Shop",
            business_kind="phones",
            status="ACTIVE",  # Required for middleware to auto-select this business
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
            location=self.location,
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
    
    def _create_phone_sale(self, price=Decimal("500000.00"), agent=None, imei=None, product=None):
        """Helper to create a phone sale."""
        from inventory.models import InventoryItem, Product
        from sales.models import Sale
        from uuid import uuid4
        
        if agent is None:
            agent = self.agent
        
        # Generate unique identifiers
        if imei is None:
            # Generate a unique 15-digit IMEI-like string
            imei = str(int(uuid4().int % 10**15)).zfill(15)
        
        # Create product if not provided (brand, model, variant live on Product, not InventoryItem)
        if product is None:
            product = Product.objects.create(
                code=f"SAM-S21-{uuid4().hex[:8]}",  # Unique code required
                name="Samsung Galaxy S21",
                brand="Samsung",
                model="Galaxy S21",
                variant="128GB Black",
                cost_price=Decimal("400000.00"),
                sale_price=price,
            )
        
        # Create inventory item with product FK
        item = InventoryItem.objects.create(
            business=self.business,
            current_location=self.location,
            product=product,
            imei=imei,
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
        from tenants.models import Membership
        from inventory.models import Product
        from uuid import uuid4
        
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
            location=self.location,
            role="AGENT",
            status="ACTIVE",
        )
        
        # Create unique product for agent2's sale
        product2 = Product.objects.create(
            code=f"PHONE-AGENT2-{uuid4().hex[:8]}",
            name="Test Phone Agent2",
            brand="Apple",
            model="iPhone 14",
            variant="256GB",
            cost_price=Decimal("700000.00"),
            sale_price=Decimal("800000.00"),
        )
        
        sale2, _ = self._create_phone_sale(price=Decimal("800000.00"), agent=agent2, product=product2)
        
        # Test API endpoint
        self.client.force_login(self.agent)
        set_active_business_session(self.client, self.business.id, self.location.id)
        
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
        self.client.force_login(self.agent)
        set_active_business_session(self.client, self.business.id, self.location.id)
        
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
        
        # Verify gross amount includes commission + base salary
        expected_commission = Decimal("500000.00") * Decimal("0.03")
        expected_base_salary = Decimal("50000.00")
        expected_total = expected_commission + expected_base_salary
        self.assertEqual(
            current_month_payslip.gross,
            expected_total,
            f"Payslip gross should be {expected_total} (commission {expected_commission} + base salary {expected_base_salary})"
        )
    
    def test_integration_multiple_sales_correct_totals(self):
        """
        Integration test: Multiple sales should show correct totals.
        """
        from inventory.models import Product
        from uuid import uuid4
        
        # Create 3 sales - create a shared product to avoid unique constraint violations
        prices = [Decimal("500000.00"), Decimal("750000.00"), Decimal("600000.00")]
        
        for i, price in enumerate(prices):
            # Create unique product for each sale
            product = Product.objects.create(
                code=f"PHONE-{uuid4().hex[:8]}",
                name=f"Test Phone {i}",
                brand="Samsung",
                model=f"Model {i}",
                variant="Test",
                cost_price=Decimal("400000.00"),
                sale_price=price,
            )
            self._create_phone_sale(price=price, product=product)
        
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
        from tenants.models import Business, Membership
        from inventory.models import Location
        from uuid import uuid4
        
        # Use timestamp or uuid to ensure unique business names/slugs
        unique_suffix = uuid4().hex[:8]
        business2 = Business.objects.create(
            name=f"Another Shop {unique_suffix}",
            slug=f"another-shop-{unique_suffix}",
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
            location=location2,
            role="AGENT",
            status="ACTIVE",
        )
        
        # Create sale in business1
        self._create_phone_sale(price=Decimal("500000.00"))
        
        # Create sale in business2
        from inventory.models import InventoryItem, Product
        from sales.models import Sale
        from uuid import uuid4
        
        # Create product for business2
        product2 = Product.objects.create(
            code=f"IPHONE-14-{uuid4().hex[:8]}",
            name="iPhone 14 Pro",
            brand="iPhone",
            model="14 Pro",
            variant="256GB",
            cost_price=Decimal("800000.00"),
            sale_price=Decimal("1000000.00"),
        )
        
        item2 = InventoryItem.objects.create(
            business=business2,
            current_location=location2,
            product=product2,
            imei="999888777666555",
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


@pytest.mark.django_db
class TestPhonesBaseSalary(TestCase):
    """Test base salary feature for Phones agents."""
    
    def setUp(self):
        """Set up test data."""
        from tenants.models import Business, Membership
        from inventory.models import Location
        import time
        
        # Use timestamp for unique business names
        ts = str(int(time.time() * 1000))[-8:]  # Last 8 digits of timestamp
        
        # Create Phones business
        self.phones_business = Business.objects.create(
            name=f"Phones Shop {ts}",
            slug=f"phones-shop-{ts}",
            business_kind="phones",
            status="ACTIVE",  # Required for middleware to auto-select this business
        )
        
        self.phones_location = Location.objects.create(
            name=f"Phones Store {ts}",
            business=self.phones_business,
            latitude=Decimal("-15.123"),
            longitude=Decimal("35.123"),
        )
        
        # Create agent user
        self.agent = User.objects.create_user(
            username=f"phoneagent{ts}",
            email=f"phoneagent{ts}@test.com",
            password="testpass123",
            first_name="Phone",
            last_name="Agent",
        )
        
        # Create agent membership
        self.membership = Membership.objects.create(
            user=self.agent,
            business=self.phones_business,
            location=self.phones_location,
            role="AGENT",
            status="ACTIVE",
        )
        
        # Create non-phones business for comparison
        self.other_business = Business.objects.create(
            name=f"Laptop Shop {ts}",
            slug=f"laptop-shop-{ts}",
            business_kind="laptops",
        )
        
        self.other_location = Location.objects.create(
            name=f"Laptop Store {ts}",
            business=self.other_business,
            latitude=Decimal("-15.456"),
            longitude=Decimal("35.456"),
        )
        
        self.client = Client()
    
    def test_phone_agent_base_salary_created_once_per_month(self):
        """
        Base salary should be created exactly once per month, even with multiple wallet visits.
        """
        from wallet.utils_salary import ensure_monthly_base_salary_for_agent
        from wallet.models import WalletTransaction, TxnType, Ledger
        
        today = timezone.localdate()
        month_key = today.strftime("%Y-%m")
        
        # First call - should create base salary
        txn1 = ensure_monthly_base_salary_for_agent(self.phones_business, self.agent, today)
        
        self.assertIsNotNone(txn1, "First call should create base salary transaction")
        self.assertEqual(txn1.amount, Decimal("50000.00"), "Base salary should be MWK 50,000")
        self.assertEqual(txn1.type, TxnType.BONUS)
        self.assertEqual(txn1.meta.get("kind"), "phones_base_salary")
        self.assertEqual(txn1.meta.get("month"), month_key)
        
        # Second call - should return None (idempotent)
        txn2 = ensure_monthly_base_salary_for_agent(self.phones_business, self.agent, today)
        
        self.assertIsNone(txn2, "Second call should return None (idempotent)")
        
        # Verify only one base salary transaction exists
        base_salary_txns = WalletTransaction.objects.filter(
            ledger=Ledger.AGENT,
            agent=self.agent,
            business=self.phones_business,
            type=TxnType.BONUS,
            meta__kind="phones_base_salary",
            meta__month=month_key,
        )
        
        self.assertEqual(
            base_salary_txns.count(),
            1,
            "Should have exactly one base salary transaction per month"
        )
    
    def test_phone_agent_base_salary_not_created_for_non_phone_vertical(self):
        """
        Base salary should NOT be created for non-Phones businesses.
        """
        from wallet.utils_salary import ensure_monthly_base_salary_for_agent
        from wallet.models import WalletTransaction
        
        # Create agent for non-phones business
        import time
        ts_agent = str(int(time.time() * 1000))[-8:]
        
        other_agent = User.objects.create_user(
            username=f"laptopagent{ts_agent}",
            email=f"laptopagent{ts_agent}@test.com",
            password="test",
        )
        
        from tenants.models import Membership
        Membership.objects.create(
            user=other_agent,
            business=self.other_business,
            location=self.other_location,
            role="AGENT",
            status="ACTIVE",
        )
        
        # Try to create base salary
        txn = ensure_monthly_base_salary_for_agent(self.other_business, other_agent)
        
        self.assertIsNone(txn, "Should not create base salary for non-Phones business")
        
        # Verify no base salary transactions exist
        base_salary_txns = WalletTransaction.objects.filter(
            agent=other_agent,
            meta__kind="phones_base_salary",
        )
        
        self.assertEqual(base_salary_txns.count(), 0)
    
    def test_phone_agent_new_month_creates_new_salary_txn(self):
        """
        A new month should create a new base salary transaction.
        """
        from wallet.utils_salary import ensure_monthly_base_salary_for_agent
        from wallet.models import WalletTransaction
        from datetime import timedelta
        
        # Current month
        today = timezone.localdate()
        txn1 = ensure_monthly_base_salary_for_agent(self.phones_business, self.agent, today)
        
        self.assertIsNotNone(txn1, "Should create base salary for current month")
        
        # Simulate next month (force "today" to be next month)
        if today.month == 12:
            next_month_date = date(today.year + 1, 1, 15)
        else:
            next_month_date = date(today.year, today.month + 1, 15)
        
        txn2 = ensure_monthly_base_salary_for_agent(self.phones_business, self.agent, next_month_date)
        
        self.assertIsNotNone(txn2, "Should create base salary for next month")
        self.assertNotEqual(txn1.id, txn2.id, "Should be different transactions")
        
        # Verify two different month keys
        self.assertNotEqual(txn1.meta.get("month"), txn2.meta.get("month"))
        
        # Verify total count is 2
        base_salary_txns = WalletTransaction.objects.filter(
            agent=self.agent,
            business=self.phones_business,
            meta__kind="phones_base_salary",
        )
        
        self.assertEqual(base_salary_txns.count(), 2, "Should have 2 base salary txns (one per month)")
    
    def test_phone_agent_payslip_includes_base_even_without_sales(self):
        """
        Payslip should show MWK 50,000 even if agent has made no sales.
        """
        from wallet.utils_salary import ensure_monthly_base_salary_for_agent
        
        # Ensure base salary exists
        ensure_monthly_base_salary_for_agent(self.phones_business, self.agent)
        
        # Login as agent
        self.client.force_login(self.agent)
        set_active_business_session(self.client, self.phones_business.id, self.phones_location.id)
        
        # Access wallet page
        response = self.client.get(reverse('wallet:agent_wallet'))
        
        self.assertEqual(response.status_code, 200)
        
        # Check context for payslips
        payslips = response.context.get('payslips', [])
        
        # Should have at least 1 payslip entry
        self.assertGreater(len(payslips), 0, "Should have at least one payslip")
        
        # Check current month payslip
        current_year = timezone.now().year
        current_month = timezone.now().month
        
        current_month_payslip = None
        for p in payslips:
            if p.year == current_year and p.month == current_month:
                current_month_payslip = p
                break
        
        self.assertIsNotNone(current_month_payslip, "Current month should appear in payslips")
        
        # Verify gross includes base salary (MWK 50,000)
        self.assertGreaterEqual(
            current_month_payslip.gross,
            Decimal("50000.00"),
            "Payslip gross should include base salary of MWK 50,000"
        )
    
    def test_commission_does_not_duplicate_salary(self):
        """
        Creating multiple sales should NOT duplicate base salary.
        Should have 2 commission txns + 1 salary txn (total 3).
        """
        from wallet.utils_salary import ensure_monthly_base_salary_for_agent
        from wallet.models import WalletTransaction, TxnType
        from inventory.models import InventoryItem
        from sales.models import Sale
        
        # Ensure base salary exists
        ensure_monthly_base_salary_for_agent(self.phones_business, self.agent)
        
        # Create product first
        from inventory.models import Product
        
        product = Product.objects.create(
            code="SAM-S21-128",
            name="Samsung Galaxy S21",
            brand="Samsung",
            model="Galaxy S21",
            variant="128GB Black",
        )
        
        # Create 2 sales
        for i in range(2):
            item = InventoryItem.objects.create(
                business=self.phones_business,
                current_location=self.phones_location,
                product=product,
                imei=f"12345678901234{i}",
                status="SOLD",
                selling_price=Decimal("500000.00"),
                order_price=Decimal("400000.00"),
                assigned_agent=self.agent,
                sold_at=timezone.now(),
            )
            
            Sale.objects.create(
                item=item,
                agent=self.agent,
                location=self.phones_location,
                sold_at=timezone.localdate(),
                price=Decimal("500000.00"),
                commission_pct=Decimal("3.00"),
                payment_method="CASH",
            )
        
        # Count commission transactions
        commission_txns = WalletTransaction.objects.filter(
            agent=self.agent,
            business=self.phones_business,
            type=TxnType.COMMISSION,
        )
        
        self.assertEqual(commission_txns.count(), 2, "Should have 2 commission transactions")
        
        # Count base salary transactions
        base_salary_txns = WalletTransaction.objects.filter(
            agent=self.agent,
            business=self.phones_business,
            type=TxnType.BONUS,
            meta__kind="phones_base_salary",
        )
        
        self.assertEqual(base_salary_txns.count(), 1, "Should still have only 1 base salary transaction")
        
        # Total positive transactions should be 3 (2 commissions + 1 salary)
        all_positive_txns = WalletTransaction.objects.filter(
            ledger=Ledger.AGENT,
            agent=self.agent,
            business=self.phones_business,
            amount__gt=0,
        )
        
        self.assertEqual(all_positive_txns.count(), 3, "Should have 3 positive transactions total")
    
    def test_agent_wallet_view_calls_ensure_salary(self):
        """
        Accessing the agent wallet view should automatically ensure base salary exists.
        """
        from unittest.mock import patch
        from wallet.models import WalletTransaction
        
        # Verify no base salary exists yet
        base_salary_txns = WalletTransaction.objects.filter(
            agent=self.agent,
            meta__kind="phones_base_salary",
        )
        
        self.assertEqual(base_salary_txns.count(), 0, "No base salary should exist initially")
        
        # Login and access wallet - patch at source (local import in method, not module-level)
        with patch("wallet.utils_salary.ensure_monthly_base_salary_for_agent") as mocked:
            # Configure mock to return None (default idempotent behavior)
            mocked.return_value = None
            
            self.client.force_login(self.agent)
            set_active_business_session(self.client, self.phones_business.id, self.phones_location.id)
            response = self.client.get(reverse('wallet:agent_wallet'))
            
            self.assertEqual(response.status_code, 200)
            
            # Verify the function was called (it's imported and called inside the view)
            mocked.assert_called()
        
        # Now call the real view without mocking to verify actual behavior
        self.client.force_login(self.agent)
        set_active_business_session(self.client, self.phones_business.id, self.phones_location.id)
        response = self.client.get(reverse('wallet:agent_wallet'))
        
        self.assertEqual(response.status_code, 200)
        
        # Now base salary should exist
        base_salary_txns = WalletTransaction.objects.filter(
            agent=self.agent,
            meta__kind="phones_base_salary",
        )
        
        self.assertEqual(
            base_salary_txns.count(),
            1,
            "Base salary should be created automatically on wallet visit"
        )
    
    def test_base_salary_transaction_fields(self):
        """
        Verify base salary transaction has correct fields.
        """
        from wallet.utils_salary import ensure_monthly_base_salary_for_agent
        
        today = timezone.localdate()
        month_key = today.strftime("%Y-%m")
        month_start = today.replace(day=1)
        
        txn = ensure_monthly_base_salary_for_agent(self.phones_business, self.agent, today)
        
        # Check all required fields
        self.assertEqual(txn.ledger, Ledger.AGENT)
        self.assertEqual(txn.agent, self.agent)
        self.assertEqual(txn.business, self.phones_business)
        self.assertEqual(txn.type, TxnType.BONUS)
        self.assertEqual(txn.amount, Decimal("50000.00"))
        self.assertEqual(txn.effective_date, month_start, "Should use month start as effective date")
        self.assertIn("Base salary", txn.note)
        self.assertIn("SALARY", txn.reference)
        
        # Check meta fields
        self.assertEqual(txn.meta.get("kind"), "phones_base_salary")
        self.assertEqual(txn.meta.get("month"), month_key)
        self.assertEqual(txn.meta.get("amount"), "50000.00")
    
    def test_business_isolation_for_base_salary(self):
        """
        Base salary should be properly scoped to business (no cross-business leakage).
        """
        from wallet.utils_salary import ensure_monthly_base_salary_for_agent
        from wallet.models import WalletTransaction
        
        # Create base salary for phones business
        txn1 = ensure_monthly_base_salary_for_agent(self.phones_business, self.agent)
        
        self.assertIsNotNone(txn1)
        self.assertEqual(txn1.business, self.phones_business)
        
        # Create another phones business
        from tenants.models import Business, Membership
        from inventory.models import Location
        import time
        
        ts2 = str(int(time.time() * 1000))[-8:]
        
        phones_business2 = Business.objects.create(
            name=f"Phones Shop 2 {ts2}",
            slug=f"phones-shop-2-{ts2}",
            business_kind="phones",
        )
        
        # Create location for second business
        phones_location2 = Location.objects.create(
            name="Phones Store 2",
            business=phones_business2,
            latitude=Decimal("-15.789"),
            longitude=Decimal("35.789"),
        )
        
        # Create membership for agent in second business
        Membership.objects.create(
            user=self.agent,
            business=phones_business2,
            location=phones_location2,
            role="AGENT",
            status="ACTIVE",
        )
        
        # Create base salary for second business
        txn2 = ensure_monthly_base_salary_for_agent(phones_business2, self.agent)
        
        self.assertIsNotNone(txn2)
        self.assertEqual(txn2.business, phones_business2)
        self.assertNotEqual(txn1.id, txn2.id)
        
        # Verify each business has exactly one base salary transaction
        biz1_txns = WalletTransaction.objects.filter(
            agent=self.agent,
            business=self.phones_business,
            meta__kind="phones_base_salary",
        )
        
        biz2_txns = WalletTransaction.objects.filter(
            agent=self.agent,
            business=phones_business2,
            meta__kind="phones_base_salary",
        )
        
        self.assertEqual(biz1_txns.count(), 1)
        self.assertEqual(biz2_txns.count(), 1)
