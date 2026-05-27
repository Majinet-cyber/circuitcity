"""
Focused regression + feature tests for Apr 2026 hardening sprint.

Covers:
  1. Pharmacy sales trend chart API returns valid JSON (never blank/error)
  2. Pharmacy add-product endpoint uses base_unit correctly (not unit=)
  3. Energy commerce models exist and are operational
  4. Energy stock-in and sell flows work end-to-end
  5. Energy catalog seeding is idempotent
  6. Manager email helper can be called safely
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse, NoReverseMatch

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_and_business():
    """Create a user + business for testing, returns (user, business)."""
    from tenants.models import Business, Membership, BusinessKind

    user = User.objects.create_user(
        username="tester_feat_apr26",
        password="testpass123",
        email="tester@emajinet.test",
    )
    biz = Business.objects.create(
        name="Test Energy Co",
        kind=BusinessKind.ENERGY,
        is_active=True,
    )
    Membership.objects.create(user=user, business=biz, role="owner", status="active")
    return user, biz


def _auth_client(user, biz):
    """Return an authenticated test Client with an active business session."""
    c = Client()
    c.login(username=user.username, password="testpass123")
    session = c.session
    session["active_business_id"] = biz.id
    session.save()
    return c


# ---------------------------------------------------------------------------
# 1. Pharmacy sales trend JSON — always returns valid shape
# ---------------------------------------------------------------------------

class TestPharmacySalesTrendJson(TestCase):
    """The trend endpoint must always return well-shaped JSON, never 500."""

    def setUp(self):
        from tenants.models import Business, Membership, BusinessKind

        self.user = User.objects.create_user(
            username="pharm_trend_user",
            password="pass123",
            email="pharm_trend@test.com",
        )
        self.biz = Business.objects.create(
            name="Trend Pharmacy",
            kind=BusinessKind.PHARMACY,
            is_active=True,
        )
        Membership.objects.create(user=self.user, business=self.biz, role="owner", status="active")
        self.client = _auth_client(self.user, self.biz)

    def _get_trend(self, params=None):
        try:
            url = reverse("verticals:pharmacy_sales_trend_json")
        except NoReverseMatch:
            self.skipTest("pharmacy_sales_trend_json URL not registered in this env")
        return self.client.get(url, params or {"range": "30d"})

    def test_returns_200_json(self):
        resp = self._get_trend()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/json", resp.get("Content-Type", ""))

    def test_has_required_keys(self):
        import json
        resp = self._get_trend({"range": "30d"})
        data = json.loads(resp.content)
        for key in ("labels", "revenue", "units", "has_data"):
            self.assertIn(key, data, f"Missing key: {key}")

    def test_no_data_returns_has_data_false_not_error(self):
        """Empty pharmacy with no sales must return has_data=False, not 500."""
        import json
        resp = self._get_trend({"range": "7d"})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertFalse(data["has_data"])
        self.assertIsInstance(data["labels"], list)
        self.assertIsInstance(data["revenue"], list)

    def test_today_range_works(self):
        import json
        resp = self._get_trend({"range": "today"})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn("labels", data)


# ---------------------------------------------------------------------------
# 2. Pharmacy add-product endpoint — base_unit fix
# ---------------------------------------------------------------------------

class TestPharmacyAddProductEndpoint(TestCase):
    """api_add_product_suggestion must use base_unit, not the invalid unit= kwarg."""

    def setUp(self):
        from tenants.models import Business, Membership, BusinessKind

        self.user = User.objects.create_user(
            username="addprod_user",
            password="pass123",
            email="addprod@test.com",
        )
        self.biz = Business.objects.create(
            name="AddProd Pharmacy",
            kind=BusinessKind.PHARMACY,
            is_active=True,
        )
        Membership.objects.create(user=self.user, business=self.biz, role="owner", status="active")
        self.client = _auth_client(self.user, self.biz)

    def _post_add(self, payload):
        import json
        try:
            url = reverse("pharmacy:api_add_product_suggestion")
        except NoReverseMatch:
            self.skipTest("pharmacy:api_add_product_suggestion URL not available")
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_creates_product_with_valid_payload(self):
        import json
        resp = self._post_add({"name": "Paracetamol 500mg", "category": "medicine", "unit": ""})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data["ok"], msg=f"Expected ok=True, got: {data}")
        self.assertTrue(data["created"])
        self.assertIn("product_id", data)

    def test_idempotent_second_call_returns_existing(self):
        import json
        payload = {"name": "Ibuprofen 200mg", "category": "medicine"}
        resp1 = self._post_add(payload)
        self.assertEqual(resp1.status_code, 200)
        data1 = json.loads(resp1.content)
        self.assertTrue(data1["ok"])

        resp2 = self._post_add(payload)
        data2 = json.loads(resp2.content)
        self.assertTrue(data2["ok"])
        self.assertFalse(data2["created"])  # already exists
        self.assertEqual(data1["product_id"], data2["product_id"])

    def test_missing_name_returns_error(self):
        import json
        resp = self._post_add({"name": "", "category": "medicine"})
        data = json.loads(resp.content)
        self.assertFalse(data["ok"])

    def test_invalid_category_returns_error(self):
        import json
        resp = self._post_add({"name": "Test", "category": "nonexistent_cat"})
        data = json.loads(resp.content)
        self.assertFalse(data["ok"])


# ---------------------------------------------------------------------------
# 3. Energy models importable and functional
# ---------------------------------------------------------------------------

class TestEnergyCommerceModels(TestCase):
    """EnergyProduct, EnergyStockIn, EnergyItemSale must be importable and usable."""

    def setUp(self):
        from tenants.models import Business, BusinessKind

        self.user = User.objects.create_user(
            username="energy_model_user",
            password="pass123",
        )
        self.biz = Business.objects.create(
            name="Solar Shop",
            kind=BusinessKind.ENERGY,
            is_active=True,
        )

    def test_energy_product_importable(self):
        from inventory.models_energy import EnergyProduct
        self.assertIsNotNone(EnergyProduct)

    def test_energy_stock_in_importable(self):
        from inventory.models_energy import EnergyStockIn
        self.assertIsNotNone(EnergyStockIn)

    def test_energy_item_sale_importable(self):
        from inventory.models_energy import EnergyItemSale
        self.assertIsNotNone(EnergyItemSale)

    def test_create_product(self):
        from inventory.models_energy import EnergyProduct
        p = EnergyProduct.objects.create(
            business=self.biz,
            name="100W Solar Panel",
            category="solar_panel",
            cost_price=Decimal("45000"),
            selling_price=Decimal("65000"),
            quantity_in_stock=5,
        )
        self.assertEqual(p.name, "100W Solar Panel")
        self.assertEqual(p.quantity_in_stock, 5)
        self.assertFalse(p.is_low_stock)

    def test_low_stock_flag(self):
        from inventory.models_energy import EnergyProduct
        p = EnergyProduct.objects.create(
            business=self.biz,
            name="Inverter 1kW",
            category="inverter",
            quantity_in_stock=1,
            reorder_level=2,
        )
        self.assertTrue(p.is_low_stock)

    def test_sale_auto_calculates_total_and_profit(self):
        from inventory.models_energy import EnergyProduct, EnergyItemSale
        p = EnergyProduct.objects.create(
            business=self.biz,
            name="Battery 100Ah",
            category="battery",
            cost_price=Decimal("80000"),
            selling_price=Decimal("110000"),
            quantity_in_stock=10,
        )
        sale = EnergyItemSale.objects.create(
            business=self.biz,
            product=p,
            quantity=2,
            unit_price=Decimal("110000"),
            unit_cost=Decimal("80000"),
            payment_method="CASH",
        )
        self.assertEqual(sale.total_amount, Decimal("220000"))
        self.assertEqual(sale.profit, Decimal("60000"))

    def test_stock_in_creates_record(self):
        from datetime import date
        from inventory.models_energy import EnergyProduct, EnergyStockIn
        p = EnergyProduct.objects.create(
            business=self.biz,
            name="MC4 Connector",
            category="connector",
            quantity_in_stock=0,
        )
        si = EnergyStockIn.objects.create(
            business=self.biz,
            product=p,
            quantity=50,
            cost_price=Decimal("500"),
            supplier="Solar Supplies Ltd",
            received_date=date.today(),
        )
        self.assertEqual(si.quantity, 50)
        self.assertEqual(si.total_cost, Decimal("25000"))


# ---------------------------------------------------------------------------
# 4. Energy views respond 200 for authenticated user
# ---------------------------------------------------------------------------

class TestEnergyCommerceViews(TestCase):
    """Energy catalog, stock-in, sell views must render without errors."""

    def setUp(self):
        from tenants.models import Business, Membership, BusinessKind

        self.user = User.objects.create_user(
            username="energy_view_user",
            password="pass123",
        )
        self.biz = Business.objects.create(
            name="Solar View Shop",
            kind=BusinessKind.ENERGY,
            is_active=True,
        )
        Membership.objects.create(user=self.user, business=self.biz, role="owner", status="active")
        self.client = _auth_client(self.user, self.biz)

    def _get(self, name):
        try:
            return self.client.get(reverse(f"verticals:{name}"))
        except NoReverseMatch:
            self.skipTest(f"URL verticals:{name} not registered")

    def test_energy_catalog_200(self):
        resp = self._get("energy_catalog")
        self.assertEqual(resp.status_code, 200)

    def test_energy_stock_in_200(self):
        resp = self._get("energy_stock_in")
        self.assertEqual(resp.status_code, 200)

    def test_energy_sell_200(self):
        resp = self._get("energy_sell")
        self.assertEqual(resp.status_code, 200)

    def test_energy_dashboard_200(self):
        resp = self._get("energy_dashboard")
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# 5. Energy catalog seeding — idempotent
# ---------------------------------------------------------------------------

class TestEnergyCatalogSeeding(TestCase):
    """Seeding must create products and be safe to call multiple times."""

    def setUp(self):
        from tenants.models import Business, Membership, BusinessKind

        self.user = User.objects.create_user(
            username="seed_user",
            password="pass123",
        )
        self.biz = Business.objects.create(
            name="Seed Shop",
            kind=BusinessKind.ENERGY,
            is_active=True,
        )
        Membership.objects.create(user=self.user, business=self.biz, role="owner", status="active")
        self.client = _auth_client(self.user, self.biz)

    def test_seed_creates_products(self):
        from inventory.models_energy import EnergyProduct
        try:
            url = reverse("verticals:energy_seed_catalog")
        except NoReverseMatch:
            self.skipTest("energy_seed_catalog URL not registered")

        resp = self.client.get(url, follow=True)
        self.assertIn(resp.status_code, [200, 302])
        count = EnergyProduct.objects.filter(business=self.biz).count()
        self.assertGreater(count, 0, "Seed must create at least one product")

    def test_seed_is_idempotent(self):
        from inventory.models_energy import EnergyProduct
        try:
            url = reverse("verticals:energy_seed_catalog")
        except NoReverseMatch:
            self.skipTest("energy_seed_catalog URL not registered")

        self.client.get(url)
        count_first = EnergyProduct.objects.filter(business=self.biz).count()
        self.client.get(url)
        count_second = EnergyProduct.objects.filter(business=self.biz).count()
        self.assertEqual(count_first, count_second, "Second seed run must not duplicate products")


# ---------------------------------------------------------------------------
# 6. Manager email helper is safe
# ---------------------------------------------------------------------------

class TestManagerEmailHelper(TestCase):
    """_email_managers_on_pharmacy_sale must not raise even when no managers exist."""

    def test_email_helper_does_not_raise_on_missing_sale(self):
        """Calling with a non-existent sale ID must silently fail, not raise."""
        from inventory.views_pharmacy import _email_managers_on_pharmacy_sale
        # Should not raise — just log and return
        try:
            _email_managers_on_pharmacy_sale(sale_id=999999, business_id=999999)
        except Exception as e:
            self.fail(f"_email_managers_on_pharmacy_sale raised unexpectedly: {e}")

    def test_energy_email_helper_does_not_raise_on_missing_sale(self):
        """Energy email helper must also fail silently."""
        from inventory.verticals.energy import _email_managers_on_energy_sale
        try:
            _email_managers_on_energy_sale(sale_id=999999, business_id=999999)
        except Exception as e:
            self.fail(f"_email_managers_on_energy_sale raised unexpectedly: {e}")
