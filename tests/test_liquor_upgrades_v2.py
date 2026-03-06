"""
Tests for Liquor Vertical Upgrade v2:
- Canonical pricing (stock-in updates product selling price)
- Sale uses latest canonical price
- Credit sale recording
- Email notification triggers (mocked)
- Stock alert triggers (mocked)
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind

User = get_user_model()


def make_business_and_user(kind=BusinessKind.LIQUOR):
    """Helper: create user, business, membership."""
    from tenants.models import Business, Membership
    user = User.objects.create_user(
        username=f"testliquor_{timezone.now().timestamp()}",
        password="testpass123",
        email=f"test_{timezone.now().timestamp()}@emajinet.africa",
    )
    business = Business.objects.create(
        name="Test Liquor Bar",
        kind=kind,
        owner=user,
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="manager",
        is_active=True,
    )
    return user, business


def make_liquor_product(business, name="Test Beer", category="beer", price=2500, cost=1500, qty=50):
    """Helper: create a liquor product."""
    return MerchProduct.objects.create(
        business=business,
        kind=BusinessKind.LIQUOR,
        name=name,
        category=category,
        price_per_bottle=Decimal(str(price)),
        cost_per_bottle=Decimal(str(cost)),
        quantity_in_stock=qty,
        track_inventory=True,
        is_active=True,
    )


class TestCanonicalPricing(TestCase):
    """Test that scan-in updates canonical selling price."""

    def setUp(self):
        self.user, self.business = make_business_and_user()
        self.product = make_liquor_product(self.business, price=2500)

    def test_scan_in_updates_price_per_bottle(self):
        """When scanning in with a new selling price, price_per_bottle must update."""
        self.client.force_login(self.user)
        # Simulate scan-in POST with new selling price
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.post(
            reverse("liquor:scan_in"),
            {
                "product_id": self.product.id,
                "quantity": 5,
                "unit_type": "bottle",
                "cost_per_unit": "1200",
                "selling_price": "3000",
            },
        )

        # Refresh product from DB
        self.product.refresh_from_db()
        self.assertEqual(self.product.price_per_bottle, Decimal("3000"))

    def test_stockin_transaction_records_selling_price(self):
        """LiquorStockInTransaction must store selling_price_at_time."""
        from inventory.models_verticals import LiquorStockInTransaction
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        self.client.post(
            reverse("liquor:scan_in"),
            {
                "product_id": self.product.id,
                "quantity": 3,
                "unit_type": "bottle",
                "cost_per_unit": "1400",
                "selling_price": "2800",
            },
        )

        txn = LiquorStockInTransaction.objects.filter(
            business=self.business, product=self.product
        ).order_by("-created_at").first()

        self.assertIsNotNone(txn)
        self.assertEqual(txn.selling_price_at_time, Decimal("2800"))

    def test_sale_uses_canonical_price(self):
        """Create a sale and verify unit_price equals product's price_per_bottle."""
        from inventory.services.liquor_sale import create_liquor_sale
        product = self.product
        product.price_per_bottle = Decimal("3500")
        product.save()

        result = create_liquor_sale(
            business=self.business,
            product_id=product.id,
            user=self.user,
            quantity=1,
            unit="bottle",
            unit_price=Decimal("3500"),
            sale_type="cash",
        )

        self.assertTrue(result["ok"])
        from inventory.models_verticals import LiquorSale
        sale = LiquorSale.objects.get(id=result["sale_id"])
        self.assertEqual(sale.unit_price, Decimal("3500"))


class TestCreditSaleRecording(TestCase):
    """Test dedicated credit sale recording view."""

    def setUp(self):
        self.user, self.business = make_business_and_user()
        self.product = make_liquor_product(self.business, qty=20)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_record_credit_sale_get(self):
        """GET record_credit_sale should render form successfully."""
        response = self.client.get(reverse("liquor:record_credit_sale"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Record Credit Sale")

    def test_record_credit_sale_post_creates_credit(self):
        """POST to record_credit_sale should create LiquorCredit and LiquorSale."""
        from inventory.models_verticals import LiquorCredit, LiquorSale

        response = self.client.post(
            reverse("liquor:record_credit_sale"),
            {
                "customer_name": "John Banda",
                "customer_phone": "+265999000111",
                "product_id": self.product.id,
                "quantity": 2,
                "unit": "bottle",
                "unit_price": "2500",
                "notes": "Regular customer",
            },
        )

        self.assertRedirects(response, reverse("liquor:credits_list"))
        credit = LiquorCredit.objects.filter(
            business=self.business, customer_name="John Banda"
        ).first()
        self.assertIsNotNone(credit)
        self.assertEqual(credit.amount, Decimal("5000"))  # 2 × 2500
        self.assertEqual(credit.status, "open")

    def test_record_credit_sale_decrements_stock(self):
        """Recording credit sale must decrement product stock."""
        initial_qty = self.product.quantity_in_stock

        self.client.post(
            reverse("liquor:record_credit_sale"),
            {
                "customer_name": "Jane Phiri",
                "product_id": self.product.id,
                "quantity": 3,
                "unit": "bottle",
                "unit_price": "2000",
            },
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, initial_qty - 3)

    def test_record_credit_sale_requires_customer_name(self):
        """Recording credit sale without customer name should fail."""
        from inventory.models_verticals import LiquorCredit

        before_count = LiquorCredit.objects.filter(business=self.business).count()

        self.client.post(
            reverse("liquor:record_credit_sale"),
            {
                "customer_name": "",  # missing
                "product_id": self.product.id,
                "quantity": 1,
                "unit_price": "2000",
            },
        )

        # No new credit should be created
        after_count = LiquorCredit.objects.filter(business=self.business).count()
        self.assertEqual(before_count, after_count)


class TestCreditListMetrics(TestCase):
    """Test credit list shows correct metrics."""

    def setUp(self):
        self.user, self.business = make_business_and_user()
        self.product = make_liquor_product(self.business)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Create some credits
        from inventory.models_verticals import LiquorCredit, LiquorCreditStatus
        LiquorCredit.objects.create(
            business=self.business,
            customer_name="Customer 1",
            amount=Decimal("5000"),
            status=LiquorCreditStatus.OPEN,
        )
        LiquorCredit.objects.create(
            business=self.business,
            customer_name="Customer 2",
            amount=Decimal("3000"),
            status=LiquorCreditStatus.OPEN,
        )
        LiquorCredit.objects.create(
            business=self.business,
            customer_name="Customer 3",
            amount=Decimal("2000"),
            amount_paid=Decimal("2000"),
            status=LiquorCreditStatus.SETTLED,
            settled_at=timezone.now(),
        )

    def test_credits_list_shows_metrics(self):
        """Credits list page should show outstanding count and totals."""
        response = self.client.get(reverse("liquor:credits_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["outstanding_count"], 2)

    def test_credits_list_search(self):
        """Credits list search by customer name."""
        response = self.client.get(
            reverse("liquor:credits_list") + "?search=Customer+1"
        )
        self.assertEqual(response.status_code, 200)
        credits = list(response.context["credits"])
        self.assertEqual(len(credits), 1)
        self.assertEqual(credits[0].customer_name, "Customer 1")


class TestEmailNotifications(TestCase):
    """Test email notifications are triggered on sale and stock alerts."""

    def setUp(self):
        self.user, self.business = make_business_and_user()
        self.product = make_liquor_product(self.business, qty=20)
        # Set manager email on user
        self.user.email = "manager@emajinet.africa"
        self.user.save()

    @patch("inventory.services.liquor_sale._send_sale_notification")
    def test_sale_triggers_email_notification(self, mock_send):
        """Every liquor sale should trigger _send_sale_notification."""
        from inventory.services.liquor_sale import create_liquor_sale

        result = create_liquor_sale(
            business=self.business,
            product_id=self.product.id,
            user=self.user,
            quantity=1,
            unit="bottle",
            unit_price=Decimal("2500"),
            sale_type="cash",
        )

        self.assertTrue(result["ok"])
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["business"], self.business)
        self.assertEqual(call_kwargs["quantity"], 1)

    @patch("inventory.views_liquor_inventory._send_stock_alert_if_needed")
    def test_stock_alert_called_after_scan_in(self, mock_alert):
        """Stock alert check must be called after every scan-in."""
        from django.test import Client
        client = Client()
        client.force_login(self.user)
        session = client.session
        session["active_business_id"] = self.business.id
        session.save()

        client.post(
            reverse("liquor:scan_in"),
            {
                "product_id": self.product.id,
                "quantity": 5,
                "unit_type": "bottle",
                "cost_per_unit": "1200",
                "selling_price": "2500",
            },
        )

        mock_alert.assert_called()

    @patch("inventory.views_liquor_inventory.send_event_email")
    def test_low_stock_alert_sends_email_when_below_threshold(self, mock_send):
        """_send_stock_alert_if_needed sends email when qty <= threshold."""
        from inventory.views_liquor_inventory import _send_stock_alert_if_needed

        # Set product to low stock
        self.product.quantity_in_stock = 5
        self.product.save()

        _send_stock_alert_if_needed(self.product, self.business)

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        self.assertIn("low_stock", kwargs["context"]["alert_type"])

    @patch("inventory.views_liquor_inventory.send_event_email")
    def test_out_of_stock_alert_sends_email(self, mock_send):
        """_send_stock_alert_if_needed sends out_of_stock email when qty == 0."""
        from inventory.views_liquor_inventory import _send_stock_alert_if_needed

        self.product.quantity_in_stock = 0
        self.product.save()

        _send_stock_alert_if_needed(self.product, self.business)

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        self.assertIn("out_of_stock", kwargs["context"]["alert_type"])

    @patch("inventory.views_liquor_inventory.send_event_email")
    def test_no_alert_when_stock_above_threshold(self, mock_send):
        """_send_stock_alert_if_needed does NOT send email when stock is fine."""
        from inventory.views_liquor_inventory import _send_stock_alert_if_needed

        self.product.quantity_in_stock = 50
        self.product.save()

        _send_stock_alert_if_needed(self.product, self.business)

        mock_send.assert_not_called()


class TestStockListView(TestCase):
    """Test the redesigned stock list view."""

    def setUp(self):
        self.user, self.business = make_business_and_user()
        self.product = make_liquor_product(self.business)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_stock_list_loads(self):
        """Stock list page should render without errors."""
        response = self.client.get(reverse("liquor:stock_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Liquor Inventory")

    def test_stock_list_contains_product(self):
        """Stock list should display the product name."""
        response = self.client.get(reverse("liquor:stock_list"))
        self.assertContains(response, self.product.name)

    def test_stock_list_search_filter(self):
        """Stock list search filter should work."""
        other = make_liquor_product(self.business, name="Heineken", category="beer")
        response = self.client.get(reverse("liquor:stock_list") + "?q=Heineken")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Heineken")


class TestSellPagePriceEditable(TestCase):
    """Test that sell page includes editable price input."""

    def setUp(self):
        self.user, self.business = make_business_and_user()
        self.product = make_liquor_product(self.business)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_sell_page_loads(self):
        """Sell page should load without errors."""
        response = self.client.get(reverse("liquor:sell"))
        self.assertEqual(response.status_code, 200)

    def test_sell_page_has_unit_price_input(self):
        """Sell page should include the editable unit price input."""
        response = self.client.get(reverse("liquor:sell"))
        self.assertContains(response, 'name="unit_price"')

    def test_sell_page_has_payment_cards(self):
        """Sell page should include payment type cards."""
        response = self.client.get(reverse("liquor:sell"))
        self.assertContains(response, "payment-type-card")
        self.assertContains(response, 'data-payment="cash"')
