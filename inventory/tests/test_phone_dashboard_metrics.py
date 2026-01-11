"""
Tests for Phones Dashboard specific metrics.

Ensures that:
1. Phone dashboard metrics update correctly after sales
2. Date range filtering works correctly
3. Business costs from wallet are included
4. Stock counts update properly
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, timedelta

from tenants.models import Business, Membership
from inventory.models import Location, InventoryItem, Product
from sales.models import Sale, PaymentMethod
from inventory.business_kinds import BusinessKind

User = get_user_model()


class PhoneDashboardMetricsTestCase(TestCase):
    """Test phone dashboard metrics calculations."""

    def setUp(self):
        """Set up test data."""
        # Create user
        self.user = User.objects.create_user(
            username="phonemanager", email="manager@phones.com", password="testpass123"
        )

        # Create phone business
        self.business = Business.objects.create(
            name="Phone Business", slug="phone-business", business_kind=BusinessKind.PHONES
        )

        # Add user to business with manager role
        Membership.objects.create(business=self.business, user=self.user, role="MANAGER", status="ACTIVE")

        # Get or create location
        self.location = Location.objects.filter(business=self.business).first()
        if not self.location:
            self.location = Location.objects.create(business=self.business, name="Main Store", is_default=True)

        # Create phone product
        self.product = Product.objects.create(
            code="TECNO-SPARK40-4128",
            brand="TECNO",
            model="Spark 40",
            variant="4+128",
            cost_price=Decimal("400000.00"),
            sale_price=Decimal("600000.00"),
        )

        self.client = Client()
        self.client.login(username="phonemanager", password="testpass123")

    def test_phones_dashboard_accessible(self):
        """Test that phones dashboard is accessible for phone businesses."""
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("dashboard_kpis", response.context)

    def test_phones_dashboard_metrics_zero_when_no_sales(self):
        """Test that metrics are zero when there are no sales."""
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)

        kpis = response.context["dashboard_kpis"]
        self.assertEqual(float(kpis["revenue"]), 0.0)
        self.assertEqual(float(kpis["cost_of_goods"]), 0.0)
        self.assertEqual(float(kpis["total_costs"]), 0.0)
        self.assertEqual(float(kpis["profit"]), 0.0)
        self.assertEqual(kpis["units_sold"], 0)
        self.assertEqual(float(kpis["profit_margin"]), 0.0)

    def test_phones_dashboard_metrics_update_after_sale(self):
        """Test that metrics update correctly after a phone sale."""
        # Create inventory item
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="123456789012345",
            order_price=Decimal("400000.00"),
            selling_price=Decimal("600000.00"),
            status="IN_STOCK",
            current_location=self.location,
        )

        # Create sale
        sale = Sale.objects.create(
            item=item,
            agent=self.user,
            location=self.location,
            sold_at=timezone.now(),
            price=Decimal("600000.00"),
            commission_pct=Decimal("12.00"),
            payment_method=PaymentMethod.MOBILE_MONEY,
        )

        # Update item status (including payment method for dashboard payment mix)
        item.status = "SOLD"
        item.sold_at = timezone.now()
        item.payment_method = "MOBILE_MONEY"  # Must match Sale.payment_method for dashboard
        item.save()

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)

        kpis = response.context["dashboard_kpis"]

        # Check metrics
        self.assertEqual(float(kpis["revenue"]), 600000.0)
        self.assertEqual(float(kpis["cost_of_goods"]), 400000.0)
        self.assertEqual(float(kpis["total_costs"]), 400000.0)  # No business costs yet
        self.assertEqual(float(kpis["profit"]), 200000.0)
        self.assertEqual(kpis["units_sold"], 1)

        # Check profit margin (33.33%)
        self.assertAlmostEqual(float(kpis["profit_margin"]), 33.33, places=1)

        # Check payment mix
        payment_mix = kpis["payment_mix"]
        mobile_payment = next((pm for pm in payment_mix if pm["method"] == "Mobile Money"), None)
        self.assertIsNotNone(mobile_payment)
        self.assertEqual(float(mobile_payment["amount"]), 600000.0)
        self.assertEqual(mobile_payment["percentage"], 100)

    def test_phones_dashboard_stock_decreases_after_sale(self):
        """Test that stock count decreases after a sale."""
        # Create two inventory items
        item1 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="111111111111111",
            order_price=Decimal("400000.00"),
            selling_price=Decimal("600000.00"),
            status="IN_STOCK",
            current_location=self.location,
        )

        item2 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="222222222222222",
            order_price=Decimal("400000.00"),
            selling_price=Decimal("600000.00"),
            status="IN_STOCK",
            current_location=self.location,
        )

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Check stock before sale
        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)
        kpis = response.context["dashboard_kpis"]
        self.assertEqual(kpis["stock_on_hand"], 2)

        # Sell one item
        Sale.objects.create(
            item=item1,
            agent=self.user,
            location=self.location,
            sold_at=timezone.now(),
            price=Decimal("600000.00"),
            payment_method=PaymentMethod.CASH,
        )

        item1.status = "SOLD"
        item1.sold_at = timezone.now()
        item1.save()

        # Check stock after sale
        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)
        kpis = response.context["dashboard_kpis"]
        self.assertEqual(kpis["stock_on_hand"], 1)
        self.assertEqual(kpis["units_sold"], 1)

    def test_phones_dashboard_date_filter_today(self):
        """Test that 'today' date filter works correctly."""
        # Create sale today
        item_today = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="333333333333333",
            order_price=Decimal("400000.00"),
            selling_price=Decimal("600000.00"),
            status="SOLD",
            current_location=self.location,
            sold_at=timezone.now(),
        )

        Sale.objects.create(
            item=item_today,
            agent=self.user,
            location=self.location,
            sold_at=timezone.now(),
            price=Decimal("600000.00"),
            payment_method=PaymentMethod.CASH,
        )

        # Create sale yesterday
        yesterday = timezone.now() - timedelta(days=1)
        item_yesterday = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="444444444444444",
            order_price=Decimal("400000.00"),
            selling_price=Decimal("600000.00"),
            status="SOLD",
            current_location=self.location,
            sold_at=yesterday,
        )

        Sale.objects.create(
            item=item_yesterday,
            agent=self.user,
            location=self.location,
            sold_at=yesterday,
            price=Decimal("600000.00"),
            payment_method=PaymentMethod.BANK,
        )

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Filter for today only
        response = self.client.get("/inventory/verticals/phones/?range=today")
        self.assertEqual(response.status_code, 200)

        kpis = response.context["dashboard_kpis"]

        # Should only count today's sale
        self.assertEqual(kpis["units_sold"], 1)
        self.assertEqual(float(kpis["revenue"]), 600000.0)

    def test_phones_dashboard_date_filter_7d(self):
        """Test that 'last 7 days' date filter works correctly."""
        # Create sales at different times
        today = timezone.now()
        five_days_ago = today - timedelta(days=5)
        ten_days_ago = today - timedelta(days=10)

        # Sale from 5 days ago (should be included)
        item_5d = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="555555555555555",
            order_price=Decimal("400000.00"),
            selling_price=Decimal("600000.00"),
            status="SOLD",
            current_location=self.location,
            sold_at=five_days_ago,
        )

        Sale.objects.create(
            item=item_5d,
            agent=self.user,
            location=self.location,
            sold_at=five_days_ago,
            price=Decimal("600000.00"),
            payment_method=PaymentMethod.CASH,
        )

        # Sale from 10 days ago (should NOT be included)
        item_10d = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="666666666666666",
            order_price=Decimal("400000.00"),
            selling_price=Decimal("600000.00"),
            status="SOLD",
            current_location=self.location,
            sold_at=ten_days_ago,
        )

        Sale.objects.create(
            item=item_10d,
            agent=self.user,
            location=self.location,
            sold_at=ten_days_ago,
            price=Decimal("600000.00"),
            payment_method=PaymentMethod.BANK,
        )

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Filter for last 7 days
        response = self.client.get("/inventory/verticals/phones/?range=7d")
        self.assertEqual(response.status_code, 200)

        kpis = response.context["dashboard_kpis"]

        # Should only count the sale from 5 days ago
        self.assertEqual(kpis["units_sold"], 1)
        self.assertEqual(float(kpis["revenue"]), 600000.0)

    def test_phones_dashboard_includes_business_costs(self):
        """Test that business costs from wallet are included in phone dashboard."""
        from wallet.models import WalletTransaction, Ledger, TxnType

        # Create a phone sale
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="777777777777777",
            order_price=Decimal("400000.00"),
            selling_price=Decimal("600000.00"),
            status="SOLD",
            current_location=self.location,
            sold_at=timezone.now(),
        )

        Sale.objects.create(
            item=item,
            agent=self.user,
            location=self.location,
            sold_at=timezone.now(),
            price=Decimal("600000.00"),
            payment_method=PaymentMethod.CASH,
        )

        # Add business cost (rent)
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-100000.00"),  # Negative = expense
            note="Rent",
            effective_date=date.today(),
            created_by=self.user,
        )

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)

        kpis = response.context["dashboard_kpis"]

        # Revenue: 600k
        self.assertEqual(float(kpis["revenue"]), 600000.0)

        # Cost of goods: 400k
        self.assertEqual(float(kpis["cost_of_goods"]), 400000.0)

        # Business costs: 100k (rent)
        self.assertEqual(float(kpis["business_costs"]), 100000.0)

        # Total costs: 400k (COGS) + 100k (rent) = 500k
        self.assertEqual(float(kpis["total_costs"]), 500000.0)

        # Profit: 600k - 500k = 100k
        self.assertEqual(float(kpis["profit"]), 100000.0)

        # Profit margin: 100k / 600k = 16.67%
        self.assertAlmostEqual(float(kpis["profit_margin"]), 16.67, places=1)

    def test_phones_dashboard_zero_margin_when_revenue_is_zero(self):
        """Test that profit margin is 0% when revenue is zero."""
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)

        kpis = response.context["dashboard_kpis"]

        # No sales, so margin should be 0%
        self.assertEqual(float(kpis["profit_margin"]), 0.0)

    def test_phones_dashboard_payment_mix(self):
        """Test that payment mix breaks down correctly by payment method."""
        # Create three sales with different payment methods
        # Cash sale: 600k
        item_cash = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="888888888888888",
            order_price=Decimal("400000.00"),
            selling_price=Decimal("600000.00"),
            status="SOLD",
            current_location=self.location,
            sold_at=timezone.now(),
            payment_method="CASH",
        )

        # Bank sale: 900k
        item_bank = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="999999999999999",
            order_price=Decimal("400000.00"),
            selling_price=Decimal("900000.00"),
            status="SOLD",
            current_location=self.location,
            sold_at=timezone.now(),
            payment_method="BANK",
        )

        # Mobile Money sale: 500k
        item_mobile = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="101010101010101",
            order_price=Decimal("400000.00"),
            selling_price=Decimal("500000.00"),
            status="SOLD",
            current_location=self.location,
            sold_at=timezone.now(),
            payment_method="MOBILE_MONEY",
        )

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)

        kpis = response.context["dashboard_kpis"]

        # Total revenue: 600k + 900k + 500k = 2,000k
        self.assertEqual(float(kpis["revenue"]), 2000000.0)

        # Check payment mix breakdown
        payment_mix = kpis["payment_mix"]
        self.assertEqual(len(payment_mix), 3)

        # Cash: 600k / 2,000k = 30%
        cash_payment = next((pm for pm in payment_mix if pm["method"] == "Cash"), None)
        self.assertIsNotNone(cash_payment)
        self.assertEqual(float(cash_payment["amount"]), 600000.0)
        self.assertEqual(cash_payment["percentage"], 30)

        # Bank: 900k / 2,000k = 45%
        bank_payment = next((pm for pm in payment_mix if pm["method"] == "Bank"), None)
        self.assertIsNotNone(bank_payment)
        self.assertEqual(float(bank_payment["amount"]), 900000.0)
        self.assertEqual(bank_payment["percentage"], 45)

        # Mobile: 500k / 2,000k = 25%
        mobile_payment = next((pm for pm in payment_mix if pm["method"] == "Mobile Money"), None)
        self.assertIsNotNone(mobile_payment)
        self.assertEqual(float(mobile_payment["amount"]), 500000.0)
        self.assertEqual(mobile_payment["percentage"], 25)

        # Verify percentages sum to 100%
        total_pct = sum(pm["percentage"] for pm in payment_mix)
        self.assertEqual(total_pct, 100)


class PhoneDashboardLandingPageTestCase(TestCase):
    """Test that phone businesses land on the phones dashboard after login."""

    def setUp(self):
        """Set up test data."""
        # Create user
        self.user = User.objects.create_user(username="phoneuser", email="user@phones.com", password="testpass123")

        # Create phone business
        self.business = Business.objects.create(name="Phone Shop", slug="phone-shop", business_kind=BusinessKind.PHONES)

        # Add user to business
        Membership.objects.create(business=self.business, user=self.user, role="MANAGER", status="ACTIVE")

        self.client = Client()

    def test_phone_business_redirects_to_phones_dashboard_after_login(self):
        """Test that logging in with a phone business redirects to phones dashboard."""
        # Login
        response = self.client.post(
            "/accounts/login/",
            {
                "identifier": "phoneuser",
                "password": "testpass123",
            },
            follow=True,
        )

        # Should redirect to phones dashboard
        self.assertEqual(response.status_code, 200)

        # Check that we ended up on the phones dashboard
        # (The redirect chain should lead to /inventory/verticals/phones/)
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.wsgi_request.path
        self.assertIn("/inventory/verticals/phones", final_url)
