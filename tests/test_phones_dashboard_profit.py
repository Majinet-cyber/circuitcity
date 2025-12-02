# tests/test_phones_dashboard_profit.py
"""
Tests for profit and payment mix on phones dashboard.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business, Location, Membership
from inventory.models import MerchProduct, InventoryItem
from sales.models import Sale, PaymentMethod
from wallet.models import WalletTransaction, Ledger, TxnType

User = get_user_model()


@pytest.mark.django_db
class TestPhonesDashboardProfit(TestCase):
    """Test profit and payment mix on phones dashboard."""

    def setUp(self):
        """Set up test fixtures."""
        # Create business
        self.business = Business.objects.create(
            name="Test Phone Shop",
            business_kind="PHONES",
            slug="test-phone-shop",
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123",
        )
        
        # Create manager membership
        self.manager_membership = Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )
        
        # Create product
        self.product = MerchProduct.objects.create(
            business=self.business,
            brand="Samsung",
            model="Galaxy S21",
            category="PHONE",
        )
        
        self.client = Client()
        
    def test_dashboard_shows_profit_with_sales(self):
        """Test dashboard shows profit when there are sales."""
        # Create some inventory items and sales
        for i in range(3):
            item = InventoryItem.objects.create(
                business=self.business,
                product=self.product,
                current_location=self.location,
                serial_number=f"SN{i:03d}",
                cost_price=Decimal("500.00"),
                selling_price=Decimal("750.00"),
                status="SOLD",
                sold_at=timezone.now().date(),
            )
            
            Sale.objects.create(
                item=item,
                agent=self.manager,
                location=self.location,
                sold_at=timezone.now().date(),
                price=Decimal("750.00"),
                payment_method=PaymentMethod.CASH,
            )
        
        # Add some costs
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-100.00"),
            description="Test cost",
            effective_date=timezone.now().date(),
        )
        
        # Login and access dashboard
        self.client.login(username="manager@test.com", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('inventory:inventory_verticals:phones_dashboard'))
        
        # Should return 200
        self.assertEqual(response.status_code, 200)
        
        # Check context has profit data
        self.assertIn('revenue', response.context)
        self.assertIn('costs', response.context)
        self.assertIn('profit', response.context)
        self.assertIn('profit_margin', response.context)
        
        # Revenue should be 3 * 750 = 2250
        self.assertEqual(response.context['revenue'], Decimal("2250.00"))
        
        # Costs should be 100
        self.assertEqual(response.context['costs'], Decimal("100.00"))
        
        # Profit should be 2250 - 100 = 2150
        self.assertEqual(response.context['profit'], Decimal("2150.00"))
        
    def test_dashboard_shows_payment_mix(self):
        """Test dashboard shows payment mix breakdown."""
        # Create sales with different payment methods
        payment_data = [
            (PaymentMethod.CASH, Decimal("500.00")),
            (PaymentMethod.CASH, Decimal("600.00")),
            (PaymentMethod.BANK, Decimal("700.00")),
            (PaymentMethod.MOBILE_MONEY, Decimal("800.00")),
        ]
        
        for i, (method, price) in enumerate(payment_data):
            item = InventoryItem.objects.create(
                business=self.business,
                product=self.product,
                current_location=self.location,
                serial_number=f"PAY{i:03d}",
                cost_price=Decimal("300.00"),
                selling_price=price,
                status="SOLD",
                sold_at=timezone.now().date(),
            )
            
            Sale.objects.create(
                item=item,
                agent=self.manager,
                location=self.location,
                sold_at=timezone.now().date(),
                price=price,
                payment_method=method,
            )
        
        # Login and access dashboard
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('inventory:inventory_verticals:phones_dashboard'))
        
        # Check context has payment_mix data
        self.assertIn('payment_mix', response.context)
        
        payment_mix = response.context['payment_mix']
        
        # Cash: 500 + 600 = 1100
        self.assertEqual(payment_mix['CASH'], Decimal("1100.00"))
        
        # Bank: 700
        self.assertEqual(payment_mix['BANK'], Decimal("700.00"))
        
        # Mobile Money: 800
        self.assertEqual(payment_mix['MOBILE_MONEY'], Decimal("800.00"))
        
        # Total: 2600
        self.assertEqual(payment_mix['total'], Decimal("2600.00"))
        
    def test_dashboard_works_with_no_sales(self):
        """Test dashboard still works when there are no sales."""
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('inventory:inventory_verticals:phones_dashboard'))
        
        # Should still return 200
        self.assertEqual(response.status_code, 200)
        
        # Profit should be 0 or negative (just costs)
        if 'profit' in response.context:
            self.assertLessEqual(response.context['profit'], Decimal("0.00"))
        
    def test_profit_calculation_accuracy(self):
        """Test that profit calculation is accurate."""
        # Create 5 sales
        for i in range(5):
            item = InventoryItem.objects.create(
                business=self.business,
                product=self.product,
                current_location=self.location,
                serial_number=f"PROFIT{i:03d}",
                cost_price=Decimal("400.00"),
                selling_price=Decimal("600.00"),
                status="SOLD",
                sold_at=timezone.now().date(),
            )
            
            Sale.objects.create(
                item=item,
                agent=self.manager,
                location=self.location,
                sold_at=timezone.now().date(),
                price=Decimal("600.00"),
                payment_method=PaymentMethod.CASH,
            )
        
        # Add recurring cost
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal("-200.00"),
            description="Monthly rent",
            effective_from=timezone.now().date().replace(day=1),
            is_recurring=True,
        )
        
        # Add once-off cost
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-150.00"),
            description="Equipment purchase",
            effective_date=timezone.now().date(),
            is_recurring=False,
        )
        
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('inventory:inventory_verticals:phones_dashboard'))
        
        # Revenue: 5 * 600 = 3000
        self.assertEqual(response.context['revenue'], Decimal("3000.00"))
        
        # Costs: 200 + 150 = 350
        self.assertEqual(response.context['costs'], Decimal("350.00"))
        
        # Profit: 3000 - 350 = 2650
        self.assertEqual(response.context['profit'], Decimal("2650.00"))
        
        # Profit margin: (2650 / 3000) * 100 = 88.33%
        expected_margin = Decimal("88.33")
        self.assertAlmostEqual(
            float(response.context['profit_margin']),
            float(expected_margin),
            places=1
        )

