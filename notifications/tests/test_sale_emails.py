# notifications/tests/test_sale_emails.py
"""
Tests for sale notification emails.
Verifies that emails are sent with correct content, friendly tone, and detailed information.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from inventory.models import InventoryItem, Product
from notifications.models import NotificationEvent
from notifications.services import notify_sale_completion
from sales.models import Sale
from tenants.models import Business, Location, Membership

User = get_user_model()


@pytest.mark.django_db
class SaleEmailNotificationTests(TestCase):
    """Test sale email notification functionality."""

    def setUp(self):
        """Create test data."""
        self.business = Business.objects.create(
            name="Test Business", slug="test-business", status="ACTIVE", business_kind="phones"
        )
        self.location = Location.objects.create(business=self.business, name="Test Location", city="Test City")
        self.manager = User.objects.create_user(username="manager", email="manager@test.com", password="password123")
        self.agent = User.objects.create_user(username="agent", email="agent@test.com", password="password123")
        Membership.objects.create(business=self.business, user=self.manager, role="MANAGER", status="ACTIVE")
        Membership.objects.create(business=self.business, user=self.agent, role="AGENT", status="ACTIVE")
        self.product = Product.objects.create(
            business=self.business, brand="Test Brand", model="Test Model", selling_price=Decimal("100000")
        )
        self.item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="123456789012345",
            order_price=Decimal("80000"),
            selling_price=Decimal("100000"),
            status="IN_STOCK",
            current_location=self.location,
        )

    @patch("notifications.services.emit_event")
    def test_sale_email_sent_on_sale_completion(self, mock_emit_event):
        """Test that email is sent when sale is completed."""
        sale = Sale.objects.create(
            item=self.item,
            agent=self.agent,
            location=self.location,
            price=Decimal("100000"),
            sold_at=timezone.now().date(),
        )

        # Call notify_sale_completion
        notify_sale_completion(sale)

        # Verify emit_event was called
        self.assertTrue(mock_emit_event.called)
        call_args = mock_emit_event.call_args
        self.assertEqual(call_args[1]["event_type"], "SALE_INSTANT")

    @patch("notifications.services.emit_event")
    def test_sale_email_has_friendly_subject(self, mock_emit_event):
        """Test that email subject is friendly and does not contain ALERT/WARNING."""
        sale = Sale.objects.create(
            item=self.item,
            agent=self.agent,
            location=self.location,
            price=Decimal("100000"),
            sold_at=timezone.now().date(),
        )

        notify_sale_completion(sale)

        # Check that subject template is friendly
        from notifications.services import _get_template_config

        config = _get_template_config("SALE_INSTANT")
        self.assertIsNotNone(config)
        subject = config["subject"]
        self.assertNotIn("ALERT", subject.upper())
        self.assertNotIn("WARNING", subject.upper())
        self.assertIn("Sale", subject)

    @patch("notifications.services.emit_event")
    def test_sale_email_includes_product_details(self, mock_emit_event):
        """Test that email includes product name and details."""
        sale = Sale.objects.create(
            item=self.item,
            agent=self.agent,
            location=self.location,
            price=Decimal("100000"),
            sold_at=timezone.now().date(),
        )

        notify_sale_completion(sale)

        # Verify payload includes product information
        call_args = mock_emit_event.call_args
        payload = call_args[1]["payload"]

        self.assertIn("product_name", payload)
        self.assertIn("revenue", payload)
        self.assertIn("quantity", payload)
        self.assertIsNotNone(payload["product_name"])

    @patch("notifications.services.emit_event")
    def test_sale_email_includes_revenue_and_profit(self, mock_emit_event):
        """Test that email includes revenue, cost, and profit."""
        sale = Sale.objects.create(
            item=self.item,
            agent=self.agent,
            location=self.location,
            price=Decimal("100000"),
            sold_at=timezone.now().date(),
        )

        notify_sale_completion(sale)

        # Verify payload includes financial information
        call_args = mock_emit_event.call_args
        payload = call_args[1]["payload"]

        self.assertIn("revenue", payload)
        self.assertIn("cost", payload)
        self.assertIn("profit", payload)
        self.assertEqual(payload["revenue"], "100000")
        # Cost should be present (from order_price)
        self.assertIsNotNone(payload.get("cost"))
        # Profit should be calculated
        self.assertIsNotNone(payload.get("profit"))

    @patch("notifications.services.emit_event")
    def test_sale_email_includes_metadata(self, mock_emit_event):
        """Test that email includes sale metadata (date, location, agent, payment method)."""
        sale = Sale.objects.create(
            item=self.item,
            agent=self.agent,
            location=self.location,
            price=Decimal("100000"),
            sold_at=timezone.now().date(),
            payment_method="CASH",
        )

        notify_sale_completion(sale)

        # Verify payload includes metadata
        call_args = mock_emit_event.call_args
        payload = call_args[1]["payload"]

        self.assertIn("agent_name", payload)
        self.assertIn("location_name", payload)
        self.assertIn("payment_method", payload)
        self.assertIn("time", payload)
        self.assertEqual(payload["agent_name"], self.agent.username)
        self.assertEqual(payload["location_name"], self.location.name)

    @patch("notifications.services.emit_event")
    def test_sale_email_handles_missing_cost_gracefully(self, mock_emit_event):
        """Test that email handles missing cost values without crashing."""
        # Create item without cost
        item_no_cost = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="999999999999999",
            selling_price=Decimal("100000"),
            status="IN_STOCK",
            current_location=self.location,
        )

        sale = Sale.objects.create(
            item=item_no_cost,
            agent=self.agent,
            location=self.location,
            price=Decimal("100000"),
            sold_at=timezone.now().date(),
        )

        # Should not raise exception
        notify_sale_completion(sale)

        # Verify payload handles missing cost
        call_args = mock_emit_event.call_args
        payload = call_args[1]["payload"]

        # Cost should be None or empty string
        self.assertIn("cost", payload)
        # Profit might also be None if cost is missing
        self.assertIn("profit", payload)

    @patch("notifications.services.emit_event")
    def test_sale_email_includes_profit_margin(self, mock_emit_event):
        """Test that email includes profit margin when profit and revenue are available."""
        sale = Sale.objects.create(
            item=self.item,
            agent=self.agent,
            location=self.location,
            price=Decimal("100000"),
            sold_at=timezone.now().date(),
        )

        notify_sale_completion(sale)

        # Verify payload includes profit_margin
        call_args = mock_emit_event.call_args
        payload = call_args[1]["payload"]

        # Profit margin should be calculated if profit and revenue exist
        if payload.get("profit") and payload.get("revenue"):
            self.assertIn("profit_margin", payload)

    @patch("notifications.services.emit_event")
    def test_sale_email_includes_sale_url(self, mock_emit_event):
        """Test that email includes link to sales page if available."""
        sale = Sale.objects.create(
            item=self.item,
            agent=self.agent,
            location=self.location,
            price=Decimal("100000"),
            sold_at=timezone.now().date(),
        )

        notify_sale_completion(sale)

        # Verify payload includes sale_url (may be None if reverse fails)
        call_args = mock_emit_event.call_args
        payload = call_args[1]["payload"]

        self.assertIn("sale_url", payload)

    @patch("notifications.services.emit_event")
    def test_sale_email_includes_imei_when_relevant(self, mock_emit_event):
        """Test that email includes IMEI/SKU when relevant (phones vertical)."""
        sale = Sale.objects.create(
            item=self.item,
            agent=self.agent,
            location=self.location,
            price=Decimal("100000"),
            sold_at=timezone.now().date(),
        )

        notify_sale_completion(sale)

        # Verify payload includes IMEI
        call_args = mock_emit_event.call_args
        payload = call_args[1]["payload"]

        self.assertIn("imei", payload)
        self.assertIn("sku", payload)
        # IMEI should be present for phones
        if self.item.imei:
            self.assertEqual(payload["imei"], self.item.imei)
