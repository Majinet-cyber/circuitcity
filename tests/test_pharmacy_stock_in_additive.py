# tests/test_pharmacy_stock_in_additive.py
"""
Tests for pharmacy stock-in critical fixes:
  - Re-stock must reuse the SAME product and increase stock (no duplicates)
  - Case/whitespace variations map to the same product
  - Recently Stocked prefills last cost, reorder_level, supplier
  - Unauthorized access blocked
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch
from tenants.models import Business, Membership

User = get_user_model()

STOCK_IN_URL = "pharmacy:stock_in"

TOMORROW = date.today() + timedelta(days=365)


def _create_pharmacy_fixtures(slug="pharm-test-additive"):
    """Create a minimal pharmacy business + manager user."""
    from tenants.models import Location

    business = Business.objects.create(
        name="Additive Pharmacy",
        slug=slug,
        business_kind="pharmacy",
        status="ACTIVE",
    )
    location = Location.objects.create(
        business=business,
        name="Main",
        is_default=True,
    )
    user = User.objects.create_user(
        username=f"mgr_{slug}@test.com",
        email=f"mgr_{slug}@test.com",
        password="StrongPass99!",
    )
    Membership.objects.create(user=user, business=business, role="MANAGER")
    return {"business": business, "location": location, "user": user}


def _auth_client(user, business, location):
    client = Client()
    client.login(username=user.username, password="StrongPass99!")
    session = client.session
    session["active_business_id"] = business.id
    session["active_location_id"] = location.id
    session.save()
    return client


def _post_stock_in(client, overrides=None):
    """POST a valid stock-in form with sensible defaults."""
    data = {
        "product_name": "Yun Tablets",
        "category": "medicine",
        "quantity": "10",
        "cost_price": "1000",
        "selling_price": "1500",
        "batch_number": "BT-2026-001",
        "expiry_date": str(TOMORROW),
        "reorder_level": "5",
        "has_barcode": "no",
        "supplier": "ABC Distributors",
    }
    if overrides:
        data.update(overrides)
    return client.post(reverse(STOCK_IN_URL), data, follow=True)


@pytest.mark.django_db
class TestStockInAdditive(TestCase):
    """Core: stock-in must increase stock, never create duplicates."""

    def setUp(self):
        f = _create_pharmacy_fixtures("pharm-additive-1")
        self.business = f["business"]
        self.location = f["location"]
        self.user = f["user"]
        self.client = _auth_client(self.user, self.business, self.location)

    def test_first_stock_in_creates_product_and_batch(self):
        """Initial stock-in creates exactly one product and one batch."""
        _post_stock_in(self.client)

        products = MerchProduct.objects.filter(business=self.business, kind="pharmacy", name__iexact="Yun Tablets")
        self.assertEqual(products.count(), 1)

        batches = PharmacyBatch.objects.filter(business=self.business, merch_product=products.first())
        self.assertEqual(batches.count(), 1)
        self.assertEqual(batches.first().quantity, 10)

    def test_restock_same_product_adds_to_stock(self):
        """Stocking in the same product twice increases stock, not duplicates."""
        _post_stock_in(self.client, {"batch_number": "BT-2026-001", "quantity": "10"})
        _post_stock_in(self.client, {"batch_number": "BT-2026-002", "quantity": "5"})

        products = MerchProduct.objects.filter(
            business=self.business, kind="pharmacy", name__iexact="Yun Tablets"
        )
        self.assertEqual(products.count(), 1, "Must NOT create duplicate product records")

        product = products.first()
        total = (
            PharmacyBatch.objects.filter(business=self.business, merch_product=product, is_archived=False)
            .values_list("quantity", flat=True)
        )
        self.assertEqual(sum(total), 15, "Total stock must be 10 + 5 = 15")

    def test_quantity_in_stock_is_synced_after_stock_in(self):
        """MerchProduct.quantity_in_stock must equal sum of active batch quantities."""
        _post_stock_in(self.client, {"batch_number": "BT-2026-001", "quantity": "10"})
        _post_stock_in(self.client, {"batch_number": "BT-2026-002", "quantity": "5"})

        product = MerchProduct.objects.get(business=self.business, kind="pharmacy", name__iexact="Yun Tablets")
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 15)

    def test_same_batch_restock_increments_existing_batch(self):
        """POSTing same batch_number+expiry again must add qty to that batch, not create a new one."""
        _post_stock_in(self.client, {"batch_number": "BT-2026-001", "quantity": "10"})
        _post_stock_in(self.client, {"batch_number": "BT-2026-001", "quantity": "7"})

        product = MerchProduct.objects.get(business=self.business, kind="pharmacy", name__iexact="Yun Tablets")
        batches = PharmacyBatch.objects.filter(business=self.business, merch_product=product)
        self.assertEqual(batches.count(), 1, "Same batch_number+expiry must NOT create a second batch row")
        self.assertEqual(batches.first().quantity, 17)


@pytest.mark.django_db
class TestStockInNoDuplicatesOnCaseVariants(TestCase):
    """Stock-in with different case / whitespace must reuse the same product."""

    def setUp(self):
        f = _create_pharmacy_fixtures("pharm-additive-2")
        self.business = f["business"]
        self.location = f["location"]
        self.user = f["user"]
        self.client = _auth_client(self.user, self.business, self.location)

    def test_same_product_different_case(self):
        """'Yun' and 'yun' must map to ONE product."""
        _post_stock_in(self.client, {"product_name": "Yun", "batch_number": "BT-A"})
        _post_stock_in(self.client, {"product_name": "yun", "batch_number": "BT-B"})

        count = MerchProduct.objects.filter(business=self.business, kind="pharmacy", name__iexact="yun").count()
        self.assertEqual(count, 1, "'yun' and 'Yun' must not create two product records")

    def test_same_product_with_leading_trailing_spaces(self):
        """' yun ' must resolve to the same product as 'yun'."""
        _post_stock_in(self.client, {"product_name": "Yun", "batch_number": "BT-A"})
        _post_stock_in(self.client, {"product_name": " yun ", "batch_number": "BT-B"})

        count = MerchProduct.objects.filter(business=self.business, kind="pharmacy", name__iexact="yun").count()
        self.assertEqual(count, 1)

    def test_total_stock_is_correct_after_case_variant_restock(self):
        """Total stock must be the sum of all stock-ins regardless of name casing."""
        _post_stock_in(self.client, {"product_name": "Yun", "batch_number": "BT-A", "quantity": "8"})
        _post_stock_in(self.client, {"product_name": "YUN", "batch_number": "BT-B", "quantity": "4"})

        product = MerchProduct.objects.filter(business=self.business, kind="pharmacy", name__iexact="yun").first()
        self.assertIsNotNone(product)
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 12)


@pytest.mark.django_db
class TestRecentlyStockedPrefill(TestCase):
    """Recently Stocked chip must prefill last batch's cost, reorder, supplier."""

    def setUp(self):
        f = _create_pharmacy_fixtures("pharm-additive-3")
        self.business = f["business"]
        self.location = f["location"]
        self.user = f["user"]
        self.client = _auth_client(self.user, self.business, self.location)

    def test_prefill_last_batch_data_in_context(self):
        """GET ?prefill_id=<product_id> must populate prefill_last_batch context."""
        # Create product with a batch
        product = MerchProduct.objects.create(
            business=self.business,
            name="Test Drug",
            kind="pharmacy",
            category="medicine",
            spec_label="",
        )
        batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=product,
            batch_number="BT-PREFILL-001",
            expiry_date=TOMORROW,
            quantity=20,
            cost_price=Decimal("3400"),
            selling_price=Decimal("5000"),
            reorder_level=10,
            supplier="Test Supplier Co",
        )

        url = reverse(STOCK_IN_URL) + f"?prefill_id={product.pk}&category=medicine"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        ctx = response.context
        self.assertIsNotNone(ctx.get("prefill_product"), "prefill_product should be in context")
        self.assertIsNotNone(ctx.get("prefill_last_batch"), "prefill_last_batch should be in context")

        last_batch = ctx["prefill_last_batch"]
        self.assertEqual(last_batch.cost_price, Decimal("3400"))
        self.assertEqual(last_batch.reorder_level, 10)
        self.assertEqual(last_batch.supplier, "Test Supplier Co")

    def test_prefill_id_invalid_gives_no_prefill(self):
        """Invalid prefill_id must not error; prefill_product should be None."""
        url = reverse(STOCK_IN_URL) + "?prefill_id=99999"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context.get("prefill_product"))


@pytest.mark.django_db
class TestStockInPermissions(TestCase):
    """Unauthorized users must not be able to stock-in."""

    def setUp(self):
        f = _create_pharmacy_fixtures("pharm-additive-4")
        self.business = f["business"]
        self.location = f["location"]
        self.user = f["user"]

    def test_anonymous_cannot_stock_in_get(self):
        """Anonymous GET is redirected to login."""
        client = Client()
        response = client.get(reverse(STOCK_IN_URL))
        self.assertIn(response.status_code, [302, 301])
        self.assertIn("/login", response["Location"].lower() if "Location" in response else "")

    def test_anonymous_cannot_stock_in_post(self):
        """Anonymous POST is redirected to login."""
        client = Client()
        response = _post_stock_in(client)
        # follow=True — should not produce a product
        count = MerchProduct.objects.filter(business=self.business, kind="pharmacy").count()
        self.assertEqual(count, 0)
