# sales/tests/test_fast_sell.py
"""
Tests for Fast Sell feature and Liquor Barman attribution.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from inventory.models import MerchProduct
from inventory.models_verticals import LiquorSale
from sales.models import LiquorSaleAttribution
from tenants.constants import BusinessKind
from tests.helpers.tenant_setup import make_user, make_business, make_location, make_membership, login_with_active_scope


class FastSellLookupTests(TestCase):
    """Tests for Fast Sell product lookup"""

    def setUp(self):
        self.client = Client()

        # Create user, business, location, and membership
        self.user = make_user(email="testuser@example.com", username="testuser", password="testpass123")
        self.business = make_business(created_by=self.user, kind=BusinessKind.LIQUOR, name="Test Liquor Store")
        self.location = make_location(business=self.business, name="Main Store")
        make_membership(business=self.business, user=self.user, role="AGENT", location=self.location, status="ACTIVE")

        # Create test product with barcode
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Beer",
            kind="liquor",
            category="beer",
            barcode="123456789",
            quantity_in_stock=10,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
            is_active=True,
        )

        # Login and set active business in session
        login_with_active_scope(self.client, self.user, self.business)

    def test_lookup_returns_found_product(self):
        """Lookup should return product when barcode matches"""
        url = reverse("verticals:liquor_fast_sell_lookup")
        response = self.client.get(url, {"barcode": "123456789"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["found"])
        self.assertEqual(data["product"]["name"], "Test Beer")
        self.assertEqual(data["stock_qty"], 10)
        self.assertEqual(data["selling_price"], 800.0)
        self.assertFalse(data["needs_price"])

    def test_lookup_returns_not_found_for_missing_barcode(self):
        """Lookup should return not found for non-existent barcode"""
        url = reverse("verticals:liquor_fast_sell_lookup")
        response = self.client.get(url, {"barcode": "999999999"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertFalse(data["found"])

    def test_lookup_returns_needs_price_when_price_missing(self):
        """Lookup should indicate when selling price is missing"""
        self.product.selling_price = Decimal("0.00")
        self.product.save()

        url = reverse("verticals:liquor_fast_sell_lookup")
        response = self.client.get(url, {"barcode": "123456789"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["found"])
        self.assertTrue(data["needs_price"])


class FastSellCreateTests(TestCase):
    """Tests for Fast Sell sale creation"""

    def setUp(self):
        self.client = Client()

        # Create user, business, location, and membership
        self.user = make_user(email="testuser@example.com", username="testuser", password="testpass123")
        self.business = make_business(created_by=self.user, kind=BusinessKind.LIQUOR, name="Test Liquor Store")
        self.location = make_location(business=self.business, name="Main Store")
        make_membership(business=self.business, user=self.user, role="AGENT", location=self.location, status="ACTIVE")

        # Create test product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Beer",
            kind="liquor",
            category="beer",
            barcode="123456789",
            quantity_in_stock=10,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
            is_active=True,
        )

        # Login and set active business and location in session
        login_with_active_scope(self.client, self.user, self.business, self.location)

    def test_fast_sell_decrements_stock(self):
        """Fast sell should decrement product stock"""
        import json

        url = reverse("verticals:liquor_fast_sell_sell")
        response = self.client.post(
            url,
            data=json.dumps({"barcode": "123456789", "quantity": 2, "payment_method": "cash"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])

        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, 8)

    def test_fast_sell_creates_sale_record(self):
        """Fast sell should create LiquorSale record"""
        import json

        url = reverse("verticals:liquor_fast_sell_sell")
        response = self.client.post(
            url,
            data=json.dumps({"barcode": "123456789", "quantity": 1, "payment_method": "cash"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("sale_id", data)

        # Verify sale exists
        sale = LiquorSale.objects.get(id=data["sale_id"])
        self.assertEqual(sale.quantity, 1)
        self.assertEqual(sale.unit_price, Decimal("800.00"))
        self.assertEqual(sale.payment_method, "cash")

    def test_fast_sell_updates_price_when_provided(self):
        """Fast sell should update product price when provided"""
        import json

        # Set product price to 0
        self.product.selling_price = Decimal("0.00")
        self.product.save()

        url = reverse("verticals:liquor_fast_sell_sell")
        response = self.client.post(
            url,
            data=json.dumps(
                {"barcode": "123456789", "quantity": 1, "payment_method": "cash", "selling_price": "850.00"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])

        self.product.refresh_from_db()
        self.assertEqual(self.product.selling_price, Decimal("850.00"))


class LiquorBarmanAttributionTests(TestCase):
    """Tests for Liquor Barman sale attribution"""

    def setUp(self):
        self.client = Client()

        # Create business and location
        manager = make_user(email="manager@example.com", username="manager", password="testpass123")
        self.business = make_business(created_by=manager, kind=BusinessKind.LIQUOR, name="Test Liquor Store")
        self.location = make_location(business=self.business, name="Main Store")

        # Create barman and agent
        self.barman = make_user(email="barman@example.com", username="barman", password="testpass123")
        self.agent = make_user(email="agent1@example.com", username="agent1", password="testpass123")

        # Attach to business via Membership
        make_membership(business=self.business, user=self.barman, location=self.location, role="AGENT", status="ACTIVE")
        make_membership(business=self.business, user=self.agent, location=self.location, role="AGENT", status="ACTIVE")

        # Add LIQUOR_BARMAN role
        from django.contrib.auth.models import Group

        barman_group = Group.objects.create(name=f"biz:{self.business.pk}:LIQUOR_BARMAN")
        self.barman.groups.add(barman_group)

        # Add AGENT role
        agent_group = Group.objects.create(name=f"biz:{self.business.pk}:AGENT")
        self.agent.groups.add(agent_group)

        # Create test product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Beer",
            kind="liquor",
            category="beer",
            barcode="123456789",
            quantity_in_stock=10,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
            is_active=True,
        )

        # Set active business in session
        login_with_active_scope(self.client, self.barman, self.business)

    def test_barman_can_assign_sale_to_agent(self):
        """Barman should be able to assign sale to agent"""
        self.client.login(username="barman", password="testpass123")

        url = reverse("verticals:liquor_fast_sell_sell")
        response = self.client.post(
            url,
            data={
                "barcode": "123456789",
                "quantity": 1,
                "payment_method": "cash",
                "attributed_to_agent_id": self.agent.id,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])

        # Verify attribution was created
        attribution = LiquorSaleAttribution.objects.get(liquor_sale_id=data["sale_id"])
        self.assertEqual(attribution.attributed_by, self.barman)
        self.assertEqual(attribution.attributed_to, self.agent)
        self.assertEqual(attribution.status, LiquorSaleAttribution.STATUS_PENDING)

    def test_attribution_can_be_reconciled(self):
        """Attribution should be markable as reconciled"""
        # Create attribution
        sale = LiquorSale.objects.create(
            business=self.business,
            product=self.product,
            unit="bottle",
            quantity=1,
            unit_price=Decimal("800.00"),
            total_price=Decimal("800.00"),
            unit_cost=Decimal("500.00"),
            total_cost=Decimal("500.00"),
            payment_method="cash",
            sold_by=self.barman,
        )

        attribution = LiquorSaleAttribution.objects.create(
            liquor_sale_id=sale.id,
            business=self.business,
            attributed_by=self.barman,
            attributed_to=self.agent,
            sale_amount=Decimal("800.00"),
            status=LiquorSaleAttribution.STATUS_PENDING,
        )

        # Mark as reconciled
        attribution.mark_reconciled(self.barman)

        # Verify status changed
        attribution.refresh_from_db()
        self.assertEqual(attribution.status, LiquorSaleAttribution.STATUS_RECONCILED)
        self.assertEqual(attribution.reconciled_by, self.barman)
        self.assertIsNotNone(attribution.reconciled_at)

    def test_agent_sees_pending_count(self):
        """Agent should see count of pending attributions"""
        # Create multiple attributions
        for i in range(3):
            sale = LiquorSale.objects.create(
                business=self.business,
                product=self.product,
                unit="bottle",
                quantity=1,
                unit_price=Decimal("800.00"),
                total_price=Decimal("800.00"),
                unit_cost=Decimal("500.00"),
                total_cost=Decimal("500.00"),
                payment_method="cash",
                sold_by=self.barman,
            )

            LiquorSaleAttribution.objects.create(
                liquor_sale_id=sale.id,
                business=self.business,
                attributed_by=self.barman,
                attributed_to=self.agent,
                sale_amount=Decimal("800.00"),
                status=LiquorSaleAttribution.STATUS_PENDING,
            )

        # Count pending attributions for agent
        pending_count = LiquorSaleAttribution.objects.filter(
            business=self.business, attributed_to=self.agent, status=LiquorSaleAttribution.STATUS_PENDING
        ).count()

        self.assertEqual(pending_count, 3)


class FastSellPermissionTests(TestCase):
    """Tests for Fast Sell permissions"""

    def setUp(self):
        self.client = Client()

        # Create business
        manager = make_user(email="manager@example.com", username="manager", password="testpass123")
        self.business = make_business(created_by=manager, kind=BusinessKind.LIQUOR, name="Test Liquor Store")

    def test_unauthenticated_cannot_access_fast_sell(self):
        """Unauthenticated users should not access Fast Sell"""
        url = reverse("verticals:liquor_fast_sell_page")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_wrong_vertical_cannot_access_liquor_fast_sell(self):
        """Users from other verticals should not access liquor Fast Sell"""
        # Create pharmacy business
        pharmacist = make_user(email="pharmacist@example.com", username="pharmacist", password="testpass123")
        pharmacy_business = make_business(created_by=pharmacist, kind=BusinessKind.PHARMACY, name="Test Pharmacy")
        location = make_location(business=pharmacy_business, name="Main Store")
        make_membership(business=pharmacy_business, user=pharmacist, location=location, role="AGENT", status="ACTIVE")

        login_with_active_scope(self.client, pharmacist, pharmacy_business, location)

        # Should not access liquor fast sell
        url = reverse("verticals:liquor_fast_sell_page")
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403, 404])
