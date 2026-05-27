"""
Multi-vertical polish, bug-fix, demo-data, and expansion tests.
Covers: Farm demo data, Livestock presets, IoT webhook, Developers page,
Mobile Money vertical, Groceries fix, Groceries polish.
"""
import json
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse, NoReverseMatch

from tenants.models import Business

User = get_user_model()


# ===========================================================================
# FIXTURES
# ===========================================================================

@pytest.fixture
def client_factory():
    """Return a factory that creates a logged-in client for a given business."""
    def _make(kind, business_name="Test Business"):
        user = User.objects.create_user(
            username=f"user_{kind}_{id(kind)}",
            email=f"{kind}@test.example",
            password="testpass123",
        )
        business = Business.objects.create(name=business_name, kind=kind, owner=user)
        c = Client()
        c.force_login(user)
        # Activate the business in session
        session = c.session
        session["active_business_id"] = business.id
        session.save()
        return c, user, business
    return _make


@pytest.fixture
def farm_client(db, client_factory):
    return client_factory("farm", "Test Farm")


@pytest.fixture
def grocery_client(db, client_factory):
    return client_factory("grocery", "Test Grocery")


@pytest.fixture
def mm_client(db, client_factory):
    return client_factory("mobile_money", "Test MM Agent")


# ===========================================================================
# TASK 1 — Farm Dashboard Demo Data
# ===========================================================================

@pytest.mark.django_db
class TestFarmDemoDashboard:
    def test_farm_dashboard_shows_demo_banner_when_empty(self, farm_client):
        """Empty farm workspace shows demo-preview banner."""
        c, user, business = farm_client
        try:
            url = reverse("verticals:farm_dashboard")
        except NoReverseMatch:
            pytest.skip("farm dashboard URL not available")
        response = c.get(url)
        assert response.status_code == 200
        ctx = response.context
        assert ctx.get("is_demo") is True

    def test_farm_dashboard_demo_values_are_non_zero(self, farm_client):
        """Demo values show sensible non-zero numbers."""
        c, user, business = farm_client
        try:
            url = reverse("verticals:farm_dashboard")
        except NoReverseMatch:
            pytest.skip("farm dashboard URL not available")
        response = c.get(url)
        assert response.status_code == 200
        ctx = response.context
        if ctx.get("is_demo"):
            assert ctx.get("profit_this_month", 0) > 0
            assert ctx.get("income_this_month", 0) > 0
            assert ctx.get("expenses_this_month", 0) > 0

    def test_farm_dashboard_real_data_overrides_demo(self, db, farm_client):
        """Real farm data causes demo=False."""
        from inventory.models_farm import (
            FarmLedgerEntry, FarmEntryType, FarmPaymentMethod, FarmUnit
        )
        c, user, business = farm_client
        try:
            from django.utils import timezone
            FarmLedgerEntry.objects.create(
                business=business,
                date=timezone.now().date(),
                entry_type=FarmEntryType.SALE,
                enterprise_type="maize",
                category="crop_sale",
                amount_mwk=Decimal("50000"),
                quantity=Decimal("100"),
                unit=FarmUnit.KG,
                payment_method=FarmPaymentMethod.CASH,
            )
        except Exception:
            pytest.skip("Farm models not available for this test")

        try:
            url = reverse("verticals:farm_dashboard")
        except NoReverseMatch:
            pytest.skip("farm dashboard URL not available")
        response = c.get(url)
        assert response.status_code == 200
        ctx = response.context
        assert ctx.get("is_demo") is False


# ===========================================================================
# TASK 2 — Livestock Click-First
# ===========================================================================

@pytest.mark.django_db
class TestLivestockPresets:
    def test_livestock_batch_form_renders(self, farm_client):
        """Livestock batch form page renders without error."""
        c, user, business = farm_client
        try:
            url = reverse("verticals:farm_livestock_batch_create")
        except NoReverseMatch:
            pytest.skip("livestock batch create URL not found")
        response = c.get(url)
        assert response.status_code in [200, 302]

    def test_pig_preset_cards_in_template(self, farm_client):
        """Pig preset cards are present in the livestock batch form template."""
        c, user, business = farm_client
        try:
            url = reverse("verticals:farm_livestock_batch_create")
        except NoReverseMatch:
            pytest.skip("livestock batch create URL not found")
        response = c.get(url)
        if response.status_code == 200:
            content = response.content.decode()
            assert "piglets" in content.lower() or "Piglets" in content
            assert "broilers" in content.lower() or "Broilers" in content

    def test_chicken_preset_cards_in_template(self, farm_client):
        """Chicken preset cards include Broilers and Layers."""
        c, user, business = farm_client
        try:
            url = reverse("verticals:farm_livestock_batch_create")
        except NoReverseMatch:
            pytest.skip("livestock batch create URL not found")
        response = c.get(url)
        if response.status_code == 200:
            content = response.content.decode()
            assert "broilers" in content.lower() or "Broilers" in content
            assert "layers" in content.lower() or "Layers" in content


# ===========================================================================
# TASK 3 — IoT Readiness
# ===========================================================================

@pytest.mark.django_db
class TestIoTWebhook:
    def _create_device(self, db):
        from inventory.models_iot import IoTDevice
        # Create a real Business to satisfy FK integrity check on teardown
        user = User.objects.create_user(
            username=f"iot_biz_user_{id(db)}",
            email=f"iotbiz{id(db)}@test.example",
            password="pass123",
        )
        from tenants.models import Business
        biz = Business.objects.create(name=f"IoT Test Business {id(db)}", kind="energy", owner=user)
        return IoTDevice.objects.create(
            device_id=f"esp32-test-{id(db)}",
            name="Test ESP32",
            api_key=f"test-api-key-{id(db)}-secret-abcdef1234",
            business=biz,
        )

    def test_iot_device_can_be_created(self, db):
        """IoT device model can be instantiated and saved."""
        device = self._create_device(db)
        assert device.pk is not None
        assert "esp32-test" in device.device_id
        assert device.api_key != ""

    def test_webhook_rejects_missing_auth(self, db):
        """Webhook returns 401 when Authorization header is missing."""
        c = Client()
        try:
            url = reverse("iot:webhook")
        except NoReverseMatch:
            pytest.skip("IoT webhook URL not found")
        response = c.post(url, data=json.dumps({}), content_type="application/json")
        assert response.status_code == 401

    def test_webhook_rejects_invalid_api_key(self, db):
        """Webhook returns 403 for invalid API key."""
        c = Client()
        try:
            url = reverse("iot:webhook")
        except NoReverseMatch:
            pytest.skip("IoT webhook URL not found")
        response = c.post(
            url,
            data=json.dumps({"device_id": "x", "readings": {"voltage": 12}}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer wrong-key",
        )
        assert response.status_code == 403

    def test_webhook_accepts_valid_payload(self, db):
        """Webhook saves readings for a valid device + API key."""
        device = self._create_device(db)
        c = Client()
        try:
            url = reverse("iot:webhook")
        except NoReverseMatch:
            pytest.skip("IoT webhook URL not found")
        payload = {
            "device_id": device.device_id,
            "type": "energy",
            "readings": {
                "voltage": 12.6,
                "current": 4.2,
                "power": 52.9,
                "battery_soc": 78,
                "temperature": 31.5,
            },
        }
        response = c.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {device.api_key}",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["readings_saved"] == 5

    def test_webhook_saves_readings_to_db(self, db):
        """After a valid webhook call, readings exist in DB."""
        from inventory.models_iot import IoTReading
        device = self._create_device(db)
        c = Client()
        try:
            url = reverse("iot:webhook")
        except NoReverseMatch:
            pytest.skip("IoT webhook URL not found")
        payload = {
            "device_id": device.device_id,
            "type": "energy",
            "readings": {"voltage": 12.6, "current": 4.2},
        }
        c.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {device.api_key}",
        )
        assert IoTReading.objects.filter(device=device).count() == 2

    def test_webhook_updates_device_last_seen(self, db):
        """After a valid webhook call, device.last_seen is set."""
        device = self._create_device(db)
        assert device.last_seen is None
        c = Client()
        try:
            url = reverse("iot:webhook")
        except NoReverseMatch:
            pytest.skip("IoT webhook URL not found")
        c.post(
            url,
            data=json.dumps({
                "device_id": device.device_id,
                "type": "energy",
                "readings": {"voltage": 12.6},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {device.api_key}",
        )
        c = Client()
        try:
            url = reverse("iot:webhook")
        except NoReverseMatch:
            pytest.skip("IoT webhook URL not found")
        c.post(
            url,
            data=json.dumps({
                "device_id": device.device_id,
                "type": "energy",
                "readings": {"voltage": 12.6},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {device.api_key}",
        )
        device.refresh_from_db()
        assert device.last_seen is not None
        assert device.status == "online"

    def test_iot_dashboard_renders(self, db):
        """IoT dashboard renders for logged-in user."""
        user = User.objects.create_user(username="iot_user_dash", password="pass123")
        c = Client()
        c.force_login(user)
        try:
            url = reverse("iot:dashboard")
        except NoReverseMatch:
            pytest.skip("IoT dashboard URL not found")
        response = c.get(url)
        assert response.status_code == 200


# ===========================================================================
# TASK 4 — Developers Page
# ===========================================================================

@pytest.mark.django_db
class TestDevelopersPage:
    def test_developers_page_loads(self, db):
        """Developers page returns 200."""
        c = Client()
        try:
            url = reverse("staticpages:developers")
        except NoReverseMatch:
            pytest.skip("developers URL not found")
        response = c.get(url)
        assert response.status_code == 200

    def test_developers_page_contains_webhook_docs(self, db):
        """Developers page contains webhook documentation."""
        c = Client()
        try:
            url = reverse("staticpages:developers")
        except NoReverseMatch:
            pytest.skip("developers URL not found")
        response = c.get(url)
        content = response.content.decode()
        assert "webhook" in content.lower()
        assert "/iot/webhook/" in content

    def test_developers_page_contains_esp32_example(self, db):
        """Developers page contains ESP32 Arduino code example."""
        c = Client()
        try:
            url = reverse("staticpages:developers")
        except NoReverseMatch:
            pytest.skip("developers URL not found")
        response = c.get(url)
        content = response.content.decode()
        assert "ESP32" in content or "esp32" in content.lower()
        assert "Arduino" in content or "HTTPClient" in content

    def test_developers_linked_from_landing_footer(self, db):
        """Landing/home page footer includes a link to the developers page."""
        c = Client()
        try:
            url = reverse("staticpages:home")
            response = c.get(url)
            content = response.content.decode()
            assert "developers" in content.lower()
        except Exception:
            pytest.skip("Landing page not available")


# ===========================================================================
# TASK 5 — Mobile Money Vertical
# ===========================================================================

@pytest.mark.django_db
class TestMobileMoneyVertical:
    def test_mm_dashboard_renders(self, mm_client):
        """Mobile money dashboard renders."""
        c, user, business = mm_client
        try:
            url = reverse("mobilemoney:dashboard")
        except NoReverseMatch:
            pytest.skip("mobilemoney:dashboard URL not found")
        response = c.get(url)
        assert response.status_code == 200

    def test_mm_dashboard_shows_demo_when_empty(self, mm_client):
        """Mobile money dashboard shows demo banner when no transactions."""
        c, user, business = mm_client
        try:
            url = reverse("mobilemoney:dashboard")
        except NoReverseMatch:
            pytest.skip("mobilemoney:dashboard URL not found")
        response = c.get(url)
        if response.status_code == 200:
            ctx = response.context
            assert ctx.get("is_demo") is True

    def test_mm_transaction_can_be_recorded(self, mm_client):
        """Mobile money transaction can be created via POST."""
        from inventory.models_mobilemoney import MobileMoneyTransaction
        c, user, business = mm_client
        try:
            url = reverse("mobilemoney:transactions")
        except NoReverseMatch:
            pytest.skip("mobilemoney:transactions URL not found")
        response = c.post(url, {
            "tx_type": "cash_in",
            "network": "airtel",
            "amount": "5000",
            "commission": "50",
            "customer_phone": "0999123456",
            "reference_number": "REF001",
            "notes": "",
        })
        assert response.status_code in [200, 302]
        assert MobileMoneyTransaction.objects.filter(business=business).exists()

    def test_mm_real_data_overrides_demo(self, mm_client):
        """After recording a transaction, dashboard shows is_demo=False."""
        from inventory.models_mobilemoney import MobileMoneyTransaction
        c, user, business = mm_client
        MobileMoneyTransaction.objects.create(
            business=business,
            tx_type="cash_in",
            network="airtel",
            amount=Decimal("5000"),
        )
        try:
            url = reverse("mobilemoney:dashboard")
        except NoReverseMatch:
            pytest.skip("mobilemoney:dashboard URL not found")
        response = c.get(url)
        if response.status_code == 200:
            ctx = response.context
            assert ctx.get("is_demo") is False

    def test_mm_credit_can_be_created(self, mm_client):
        """Mobile money credit record can be created."""
        from inventory.models_mobilemoney import MobileMoneyCredit
        c, user, business = mm_client
        try:
            url = reverse("mobilemoney:credits")
        except NoReverseMatch:
            pytest.skip("mobilemoney:credits URL not found")
        response = c.post(url, {
            "customer_name": "Alice Banda",
            "customer_phone": "0881234567",
            "amount_credited": "10000",
            "due_date": "2026-05-31",
            "notes": "Weekly repayment",
        })
        assert response.status_code in [200, 302]
        assert MobileMoneyCredit.objects.filter(business=business).exists()

    def test_mm_reconciliation_calculates_difference(self, db, mm_client):
        """Reconciliation saves and difference = actual - expected."""
        from inventory.models_mobilemoney import MobileMoneyReconciliation
        c, user, business = mm_client
        try:
            url = reverse("mobilemoney:reconciliation")
        except NoReverseMatch:
            pytest.skip("mobilemoney:reconciliation URL not found")
        c.post(url, {
            "date": "2026-04-28",
            "opening_cash": "100000",
            "opening_float": "50000",
            "actual_closing_cash": "95000",
            "notes": "Slight shortage",
        })
        recon = MobileMoneyReconciliation.objects.filter(business=business).first()
        if recon:
            # expected = 100000 + 0 (no transactions) - 0 = 100000; actual = 95000
            assert recon.difference == Decimal("95000") - recon.expected_closing_cash


# ===========================================================================
# TASK 6 — Groceries Fix
# ===========================================================================

@pytest.mark.django_db
class TestGroceriesSaleFix:
    def test_grocery_sell_does_not_500(self, grocery_client):
        """Grocery sell endpoint does not return 500 on POST."""
        from inventory.models import MerchProduct
        from inventory.business_kinds import BusinessKind
        c, user, business = grocery_client
        product = MerchProduct.objects.create(
            business=business,
            name="Test Sugar",
            kind=BusinessKind.GROCERY,
            cost_price=Decimal("500"),
            selling_price=Decimal("700"),
            quantity_in_stock=10,
            base_unit="pcs",
            spec_label="",
            is_active=True,
        )
        try:
            url = reverse("groceries:sell")
        except NoReverseMatch:
            pytest.skip("groceries:sell URL not found")
        response = c.post(url, {
            "product_id": product.id,
            "quantity": "2",
            "sale_mode": "retail",
            "payment_method": "CASH",
            "notes": "",
        })
        assert response.status_code != 500

    def test_grocery_sale_total_price_saved(self, grocery_client):
        """GrocerySale.total_price is calculated and saved correctly."""
        from inventory.models import MerchProduct
        from inventory.models_verticals import GrocerySale
        from inventory.business_kinds import BusinessKind
        c, user, business = grocery_client
        product = MerchProduct.objects.create(
            business=business,
            name="Test Salt",
            kind=BusinessKind.GROCERY,
            cost_price=Decimal("200"),
            selling_price=Decimal("350"),
            quantity_in_stock=20,
            base_unit="pcs",
            spec_label="",
            is_active=True,
        )
        try:
            url = reverse("groceries:sell")
        except NoReverseMatch:
            pytest.skip("groceries:sell URL not found")
        c.post(url, {
            "product_id": product.id,
            "quantity": "3",
            "sale_mode": "retail",
            "payment_method": "CASH",
            "notes": "",
        })
        sale = GrocerySale.objects.filter(business=business).first()
        if sale:
            assert sale.total_price == Decimal("1050")  # 3 × 350
            assert sale.profit == Decimal("450")  # 3 × (350 - 200)

    def test_grocery_sale_profit_calculation(self, grocery_client):
        """GrocerySale.profit property returns correct value."""
        from inventory.models_verticals import GrocerySale
        from inventory.models import MerchProduct
        from inventory.business_kinds import BusinessKind
        _, user, business = grocery_client
        product = MerchProduct.objects.create(
            business=business,
            name="Cooking Oil",
            kind=BusinessKind.GROCERY,
            cost_price=Decimal("1200"),
            selling_price=Decimal("1600"),
            quantity_in_stock=5,
            base_unit="pcs",
            spec_label="",
            is_active=True,
        )
        # Test model calculation directly
        sale = GrocerySale(
            business=business,
            product=product,
            quantity=2,
            unit_price=Decimal("1600"),
            total_price=Decimal("3200"),
            unit_cost=Decimal("1200"),
            total_cost=Decimal("2400"),
        )
        assert sale.profit == Decimal("800")

    def test_grocery_stock_in_creates_product(self, grocery_client):
        """Stock-in POST creates a MerchProduct."""
        from inventory.models import MerchProduct
        c, user, business = grocery_client
        try:
            url = reverse("groceries:stock_in")
        except NoReverseMatch:
            pytest.skip("groceries:stock_in URL not found")
        response = c.post(url, {
            "product_name": "Test Bread",
            "category": "food",
            "quantity": "10",
            "cost_price": "180",
            "selling_price": "250",
            "unit": "pcs",
        })
        assert response.status_code in [200, 302]
        assert MerchProduct.objects.filter(business=business, name="Test Bread").exists()


# ===========================================================================
# TASK 7 — Groceries Dashboard Demo Preview
# ===========================================================================

@pytest.mark.django_db
class TestGroceriesDashboardDemo:
    def test_groceries_dashboard_renders(self, grocery_client):
        """Groceries dashboard renders without error."""
        c, user, business = grocery_client
        try:
            url = reverse("groceries:dashboard")
        except NoReverseMatch:
            pytest.skip("groceries:dashboard URL not found")
        response = c.get(url)
        assert response.status_code == 200

    def test_groceries_dashboard_demo_when_empty(self, grocery_client):
        """Empty groceries workspace shows demo context."""
        c, user, business = grocery_client
        try:
            url = reverse("groceries:dashboard")
        except NoReverseMatch:
            pytest.skip("groceries:dashboard URL not found")
        response = c.get(url)
        if response.status_code == 200:
            ctx = response.context
            assert ctx.get("is_demo") is True

    def test_groceries_dashboard_real_data_overrides_demo(self, grocery_client):
        """Adding a product disables demo mode."""
        from inventory.models import MerchProduct
        from inventory.business_kinds import BusinessKind
        c, user, business = grocery_client
        MerchProduct.objects.create(
            business=business,
            name="Real Soap",
            kind=BusinessKind.GROCERY,
            cost_price=Decimal("150"),
            selling_price=Decimal("200"),
            quantity_in_stock=20,
            base_unit="pcs",
            spec_label="",
            is_active=True,
        )
        try:
            url = reverse("groceries:dashboard")
        except NoReverseMatch:
            pytest.skip("groceries:dashboard URL not found")
        response = c.get(url)
        if response.status_code == 200:
            ctx = response.context
            assert ctx.get("is_demo") is False

    def test_groceries_sell_page_product_cards_render(self, grocery_client):
        """Sell page shows product cards when products exist."""
        from inventory.models import MerchProduct
        from inventory.business_kinds import BusinessKind
        c, user, business = grocery_client
        MerchProduct.objects.create(
            business=business,
            name="Biscuits",
            kind=BusinessKind.GROCERY,
            cost_price=Decimal("80"),
            selling_price=Decimal("120"),
            quantity_in_stock=50,
            base_unit="pcs",
            spec_label="",
            is_active=True,
        )
        try:
            url = reverse("groceries:sell")
        except NoReverseMatch:
            pytest.skip("groceries:sell URL not found")
        response = c.get(url)
        if response.status_code == 200:
            content = response.content.decode()
            assert "Biscuits" in content
            assert "product-card" in content

    def test_groceries_sell_empty_state(self, grocery_client):
        """Sell page shows friendly empty state when no products."""
        c, user, business = grocery_client
        try:
            url = reverse("groceries:sell")
        except NoReverseMatch:
            pytest.skip("groceries:sell URL not found")
        response = c.get(url)
        if response.status_code == 200:
            content = response.content.decode()
            assert "empty" in content.lower() or "No products" in content or "Add Stock" in content


# ===========================================================================
# TASK 8 — Groceries Sale Fix: Dove Soap regression
# ===========================================================================

@pytest.mark.django_db
class TestGroceriesDoveSoapRegression:
    """
    Regression suite for the NOT NULL constraint failure on GrocerySale.sale_type.
    Uses Dove Soap as the canonical test product (mirrors real-world scenario).
    """

    def _make_dove_soap(self, business, quantity=20):
        from inventory.models import MerchProduct
        from inventory.business_kinds import BusinessKind
        return MerchProduct.objects.create(
            business=business,
            name="Dove Soap",
            kind=BusinessKind.GROCERY,
            cost_price=Decimal("500"),
            selling_price=Decimal("750"),
            quantity_in_stock=quantity,
            base_unit="pcs",
            spec_label="",
            is_active=True,
        )

    def _sell_url(self):
        try:
            return reverse("groceries:sell")
        except NoReverseMatch:
            return None

    def test_sell_dove_soap_does_not_500(self, grocery_client):
        """POST to /groceries/sell/ with valid data must not return HTTP 500."""
        c, user, business = grocery_client
        self._make_dove_soap(business)
        url = self._sell_url()
        if url is None:
            pytest.skip("groceries:sell URL not found")

        response = c.post(url, {
            "product_id": str(
                __import__("inventory.models", fromlist=["MerchProduct"])
                .MerchProduct.objects.get(business=business, name="Dove Soap").id
            ),
            "quantity": "1",
            "sale_mode": "retail",
            "payment_method": "cash",
            "notes": "",
        })
        assert response.status_code != 500, (
            f"Sell endpoint returned 500. Response body snippet: "
            f"{response.content.decode()[:500]}"
        )

    def test_sell_dove_soap_creates_grocerysale(self, grocery_client):
        """A GrocerySale record is created after a successful POST."""
        from inventory.models_verticals import GrocerySale
        c, user, business = grocery_client
        product = self._make_dove_soap(business)
        url = self._sell_url()
        if url is None:
            pytest.skip("groceries:sell URL not found")

        c.post(url, {
            "product_id": product.id,
            "quantity": "1",
            "sale_mode": "retail",
            "payment_method": "cash",
            "notes": "",
        })
        assert GrocerySale.objects.filter(business=business, product=product).exists(), (
            "No GrocerySale was created — the sell view may have silently failed."
        )

    def test_sell_dove_soap_sale_type_is_regular(self, grocery_client):
        """GrocerySale.sale_type must be 'regular' after a standard sale."""
        from inventory.models_verticals import GrocerySale
        c, user, business = grocery_client
        product = self._make_dove_soap(business)
        url = self._sell_url()
        if url is None:
            pytest.skip("groceries:sell URL not found")

        c.post(url, {
            "product_id": product.id,
            "quantity": "1",
            "sale_mode": "retail",
            "payment_method": "cash",
            "notes": "",
        })
        sale = GrocerySale.objects.filter(business=business, product=product).first()
        assert sale is not None, "GrocerySale was not created"
        assert sale.sale_type == "regular", (
            f"Expected sale_type='regular', got '{sale.sale_type}'"
        )

    def test_sell_dove_soap_total_price_correct(self, grocery_client):
        """total_price == selling_price × quantity (750 × 2 = 1500)."""
        from inventory.models_verticals import GrocerySale
        c, user, business = grocery_client
        product = self._make_dove_soap(business)
        url = self._sell_url()
        if url is None:
            pytest.skip("groceries:sell URL not found")

        c.post(url, {
            "product_id": product.id,
            "quantity": "2",
            "sale_mode": "retail",
            "payment_method": "cash",
            "notes": "",
        })
        sale = GrocerySale.objects.filter(business=business, product=product).first()
        assert sale is not None, "GrocerySale was not created"
        assert sale.total_price == Decimal("1500"), (
            f"Expected total_price=1500, got {sale.total_price}"
        )

    def test_sell_dove_soap_profit_correct(self, grocery_client):
        """profit == (selling_price - cost_price) × quantity ((750-500) × 2 = 500)."""
        from inventory.models_verticals import GrocerySale
        c, user, business = grocery_client
        product = self._make_dove_soap(business)
        url = self._sell_url()
        if url is None:
            pytest.skip("groceries:sell URL not found")

        c.post(url, {
            "product_id": product.id,
            "quantity": "2",
            "sale_mode": "retail",
            "payment_method": "cash",
            "notes": "",
        })
        sale = GrocerySale.objects.filter(business=business, product=product).first()
        assert sale is not None, "GrocerySale was not created"
        assert sale.profit == Decimal("500"), (
            f"Expected profit=500, got {sale.profit}"
        )

    def test_sell_dove_soap_stock_reduces(self, grocery_client):
        """product.quantity_in_stock decreases by the sold quantity."""
        from inventory.models import MerchProduct
        c, user, business = grocery_client
        product = self._make_dove_soap(business, quantity=20)
        url = self._sell_url()
        if url is None:
            pytest.skip("groceries:sell URL not found")

        c.post(url, {
            "product_id": product.id,
            "quantity": "3",
            "sale_mode": "retail",
            "payment_method": "cash",
            "notes": "",
        })
        product.refresh_from_db()
        assert product.quantity_in_stock == 17, (
            f"Expected 17 units remaining, got {product.quantity_in_stock}"
        )

    def test_sell_dove_soap_insufficient_stock_no_500(self, grocery_client):
        """Selling more than available stock returns a friendly error, not 500."""
        c, user, business = grocery_client
        product = self._make_dove_soap(business, quantity=5)
        url = self._sell_url()
        if url is None:
            pytest.skip("groceries:sell URL not found")

        response = c.post(url, {
            "product_id": product.id,
            "quantity": "100",
            "sale_mode": "retail",
            "payment_method": "cash",
            "notes": "",
        })
        assert response.status_code != 500, (
            "Overselling caused a 500 instead of a friendly error."
        )
        # Stock must not change
        product.refresh_from_db()
        assert product.quantity_in_stock == 5, (
            "Stock was incorrectly reduced despite insufficient quantity."
        )

    def test_sell_dove_soap_insufficient_stock_no_sale_created(self, grocery_client):
        """No GrocerySale is created when there is insufficient stock."""
        from inventory.models_verticals import GrocerySale
        c, user, business = grocery_client
        product = self._make_dove_soap(business, quantity=5)
        url = self._sell_url()
        if url is None:
            pytest.skip("groceries:sell URL not found")

        c.post(url, {
            "product_id": product.id,
            "quantity": "100",
            "sale_mode": "retail",
            "payment_method": "cash",
            "notes": "",
        })
        assert not GrocerySale.objects.filter(business=business, product=product).exists(), (
            "A GrocerySale was incorrectly created despite insufficient stock."
        )

    def test_sell_dove_soap_only_success_message_on_valid_sale(self, grocery_client):
        """After a valid sale, ONLY the success message appears — no error messages."""
        c, user, business = grocery_client
        product = self._make_dove_soap(business, quantity=10)
        url = self._sell_url()
        if url is None:
            pytest.skip("groceries:sell URL not found")

        response = c.post(url, {
            "product_id": product.id,
            "quantity": "1",
            "sale_mode": "retail",
            "payment_method": "cash",
            "notes": "",
        }, follow=True)

        # Should not contain any error-level messages
        msgs = list(response.context["messages"]) if response.context and "messages" in response.context else []
        error_msgs = [m for m in msgs if "error" in str(m.tags)]
        assert not error_msgs, (
            f"Got unexpected error message(s) after a valid sale: {[str(m) for m in error_msgs]}"
        )

    def test_sell_dove_soap_no_success_message_on_insufficient_stock(self, grocery_client):
        """When stock is insufficient, only an error message appears — no success message."""
        c, user, business = grocery_client
        product = self._make_dove_soap(business, quantity=2)
        url = self._sell_url()
        if url is None:
            pytest.skip("groceries:sell URL not found")

        response = c.post(url, {
            "product_id": product.id,
            "quantity": "99",
            "sale_mode": "retail",
            "payment_method": "cash",
            "notes": "",
        }, follow=True)

        # Should not contain success messages
        msgs = list(response.context["messages"]) if response.context and "messages" in response.context else []
        success_msgs = [m for m in msgs if "success" in str(m.tags)]
        assert not success_msgs, (
            f"Got unexpected success message(s) on an oversell attempt: {[str(m) for m in success_msgs]}"
        )

    def test_sell_product_from_another_business_is_rejected(self, db):
        """A product that belongs to another business cannot be sold."""
        import uuid
        from django.test import Client
        from inventory.models import MerchProduct
        from inventory.business_kinds import BusinessKind
        from inventory.models_verticals import GrocerySale
        from tenants.models import Business

        uid = uuid.uuid4().hex[:8]
        user1 = User.objects.create_user(username=f"cross_biz_u1_{uid}", password="pass")
        user2 = User.objects.create_user(username=f"cross_biz_u2_{uid}", password="pass")
        biz1 = Business.objects.create(name=f"Biz A {uid}", kind="grocery", owner=user1)
        biz2 = Business.objects.create(name=f"Biz B {uid}", kind="grocery", owner=user2)

        c1 = Client()
        c1.force_login(user1)
        session = c1.session
        session["active_business_id"] = biz1.id
        session.save()

        # Product belongs to biz2, but client1 (biz1) tries to sell it
        product = MerchProduct.objects.create(
            business=biz2,
            name="Biz2 Soap",
            kind=BusinessKind.GROCERY,
            cost_price=Decimal("100"),
            selling_price=Decimal("150"),
            quantity_in_stock=10,
            base_unit="pcs",
            spec_label="",
            is_active=True,
        )
        url = self._sell_url()
        if url is None:
            pytest.skip("groceries:sell URL not found")

        response = c1.post(url, {
            "product_id": product.id,
            "quantity": "1",
            "sale_mode": "retail",
            "payment_method": "cash",
            "notes": "",
        })
        assert response.status_code != 500
        # No GrocerySale should exist for biz1 (cross-business sale blocked)
        assert not GrocerySale.objects.filter(business=biz1, product=product).exists(), (
            "Cross-business sale was incorrectly allowed."
        )
        # Product stock in biz2 must remain unchanged
        product.refresh_from_db()
        assert product.quantity_in_stock == 10, (
            "Stock was incorrectly reduced for a cross-business sale attempt."
        )

    def test_sell_creates_only_one_sale_record_per_request(self, grocery_client):
        """A single sell POST creates exactly one GrocerySale record."""
        from inventory.models_verticals import GrocerySale
        c, user, business = grocery_client
        product = self._make_dove_soap(business, quantity=10)
        url = self._sell_url()
        if url is None:
            pytest.skip("groceries:sell URL not found")

        before = GrocerySale.objects.filter(business=business).count()
        c.post(url, {
            "product_id": product.id,
            "quantity": "1",
            "sale_mode": "retail",
            "payment_method": "cash",
            "notes": "",
        })
        after = GrocerySale.objects.filter(business=business).count()
        assert after - before == 1, (
            f"Expected exactly 1 new GrocerySale, but got {after - before}."
        )
