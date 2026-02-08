# inventory/tests/test_clothing_unified_fast_sell.py
"""
Tests for unified Fast Sell functionality - supports BOTH tracked units AND common stock.

Test Coverage:
- Lookup endpoint (tracked + common)
- Sell endpoint (tracked + common)
- Double-sell prevention (tracked units)
- Stock decrement (common items)
- Tracked unit list view
- Hub clickable pills
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from inventory.models import MerchProduct, Location, BusinessKind
from inventory.models_clothing_barcode import ClothingBarcodeUnit
from inventory.models_verticals import ClothingSale
from tenants.models import Business, Membership

User = get_user_model()


class ClothingUnifiedFastSellTestCase(TestCase):
    """Base test case with common setup"""

    def setUp(self):
        # Create user
        self.user = User.objects.create_user(
            username="testmanager",
            email="manager@test.com",
            password="testpass123",
        )

        # Create business
        self.business = Business.objects.create(
            name="Test Clothing Store",
            slug="test-clothing",
            business_kind=BusinessKind.CLOTHING,
        )

        # Create membership (manager)
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager",
        )

        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True,
        )

        # Set active location
        self.user.active_location = self.location
        self.user.save()

        # Create client and login
        self.client = Client()
        self.client.login(username="testmanager", password="testpass123")


class TestLookupUnifiedAPI(ClothingUnifiedFastSellTestCase):
    """Test unified lookup endpoint"""

    def test_lookup_tracked_unit_by_barcode(self):
        """Test looking up a tracked unit by barcode"""
        # Create tracked unit
        unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="TRACK001",
            category="shoes",
            size="42",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00"),
            status="IN_STOCK",
            is_active=True,
            created_by=self.user,
        )

        # Lookup
        url = reverse("verticals:clothing_fast_sell_lookup_unified_api")
        response = self.client.get(url, {"code": "TRACK001"})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["ok"])
        self.assertTrue(data["found"])
        self.assertEqual(data["kind"], "tracked_unit")
        self.assertEqual(data["item"]["tracked_unit_id"], unit.id)
        self.assertEqual(data["item"]["barcode"], "TRACK001")
        self.assertEqual(data["item"]["size"], "42")
        self.assertEqual(data["item"]["selling_price"], 80.0)

    def test_lookup_common_stock_by_barcode(self):
        """Test looking up common stock by barcode"""
        # Create common stock product
        product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.CLOTHING,
            name="T-Shirt - Blue - Medium",
            barcode="COMMON001",
            size="M",
            color="Blue",
            cost_price=Decimal("15.00"),
            selling_price=Decimal("30.00"),
            quantity_in_stock=10,
            is_active=True,
        )

        # Lookup
        url = reverse("verticals:clothing_fast_sell_lookup_unified_api")
        response = self.client.get(url, {"code": "COMMON001"})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["ok"])
        self.assertTrue(data["found"])
        self.assertEqual(data["kind"], "common_item")
        self.assertEqual(data["item"]["product_id"], product.id)
        self.assertEqual(data["item"]["barcode"], "COMMON001")
        self.assertEqual(data["item"]["selling_price"], 30.0)
        self.assertEqual(data["item"]["qty_available"], 10)

    def test_lookup_common_stock_by_sku(self):
        """Test looking up common stock by SKU (fallback)"""
        # Create common stock product with SKU
        product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.CLOTHING,
            name="Jeans - Black - 32",
            sku="SKU-JEANS-001",
            size="32",
            color="Black",
            cost_price=Decimal("40.00"),
            selling_price=Decimal("70.00"),
            quantity_in_stock=5,
            is_active=True,
        )

        # Lookup by SKU
        url = reverse("verticals:clothing_fast_sell_lookup_unified_api")
        response = self.client.get(url, {"code": "SKU-JEANS-001"})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["ok"])
        self.assertTrue(data["found"])
        self.assertEqual(data["kind"], "common_item")
        self.assertEqual(data["item"]["product_id"], product.id)

    def test_lookup_priority_tracked_over_common(self):
        """Test that tracked units have priority over common stock"""
        # Create both with same code
        unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="DUPLICATE001",
            category="shoes",
            size="42",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00"),
            status="IN_STOCK",
            is_active=True,
            created_by=self.user,
        )

        product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.CLOTHING,
            name="Common Item",
            barcode="DUPLICATE001",
            cost_price=Decimal("20.00"),
            selling_price=Decimal("40.00"),
            quantity_in_stock=5,
            is_active=True,
        )

        # Lookup - should return tracked unit
        url = reverse("verticals:clothing_fast_sell_lookup_unified_api")
        response = self.client.get(url, {"code": "DUPLICATE001"})

        data = response.json()
        self.assertEqual(data["kind"], "tracked_unit")
        self.assertEqual(data["item"]["tracked_unit_id"], unit.id)

    def test_lookup_not_found(self):
        """Test lookup for non-existent code"""
        url = reverse("verticals:clothing_fast_sell_lookup_unified_api")
        response = self.client.get(url, {"code": "NOTFOUND"})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["ok"])
        self.assertFalse(data["found"])
        self.assertIn("error", data)

    def test_lookup_sold_tracked_unit(self):
        """Test looking up a SOLD tracked unit (should return helpful error)"""
        # Create sold unit
        unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="SOLD001",
            category="shoes",
            size="42",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00"),
            status="SOLD",
            is_active=True,
            created_by=self.user,
        )

        # Lookup
        url = reverse("verticals:clothing_fast_sell_lookup_unified_api")
        response = self.client.get(url, {"code": "SOLD001"})

        data = response.json()
        self.assertFalse(data["found"])
        self.assertIn("already sold", data["error"])


class TestSellUnifiedAPI(ClothingUnifiedFastSellTestCase):
    """Test unified sell endpoint"""

    def test_sell_tracked_unit(self):
        """Test selling a tracked unit"""
        # Create tracked unit
        unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="SELL_TRACK001",
            category="shoes",
            size="42",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00"),
            status="IN_STOCK",
            is_active=True,
            created_by=self.user,
        )

        # Sell
        url = reverse("verticals:clothing_fast_sell_sell_unified_api")
        response = self.client.post(
            url,
            data={
                "kind": "tracked_unit",
                "tracked_unit_id": unit.id,
                "payment_method": "cash",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["ok"])
        self.assertIn("sale_id", data)
        self.assertIn("message", data)
        self.assertEqual(data["kind"], "tracked_unit")

        # Verify sale created
        sale = ClothingSale.objects.get(id=data["sale_id"])
        self.assertEqual(sale.business, self.business)
        self.assertEqual(sale.barcode_unit, unit)
        self.assertEqual(sale.quantity, 1)
        self.assertEqual(sale.total_price, Decimal("80.00"))

        # Verify unit marked as SOLD
        unit.refresh_from_db()
        self.assertEqual(unit.status, "SOLD")
        self.assertIsNotNone(unit.sold_at)

    def test_sell_tracked_unit_double_sell_prevention(self):
        """Test that double-selling a tracked unit is prevented"""
        # Create and sell unit
        unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="DOUBLE001",
            category="shoes",
            size="42",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00"),
            status="IN_STOCK",
            is_active=True,
            created_by=self.user,
        )

        url = reverse("verticals:clothing_fast_sell_sell_unified_api")

        # First sale - should succeed
        response1 = self.client.post(
            url,
            data={
                "kind": "tracked_unit",
                "tracked_unit_id": unit.id,
                "payment_method": "cash",
            },
            content_type="application/json",
        )

        self.assertEqual(response1.status_code, 200)
        self.assertTrue(response1.json()["ok"])

        # Second sale - should fail
        response2 = self.client.post(
            url,
            data={
                "kind": "tracked_unit",
                "tracked_unit_id": unit.id,
                "payment_method": "cash",
            },
            content_type="application/json",
        )

        self.assertEqual(response2.status_code, 400)
        data = response2.json()
        self.assertFalse(data["ok"])
        self.assertIn("already sold", data["error"].lower())

        # Verify only ONE sale exists
        sale_count = ClothingSale.objects.filter(barcode_unit=unit).count()
        self.assertEqual(sale_count, 1)

    def test_sell_common_stock(self):
        """Test selling common stock"""
        # Create common stock product
        product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.CLOTHING,
            name="T-Shirt - Blue - M",
            barcode="COMMON_SELL001",
            size="M",
            cost_price=Decimal("15.00"),
            selling_price=Decimal("30.00"),
            quantity_in_stock=10,
            is_active=True,
        )

        # Sell qty=1
        url = reverse("verticals:clothing_fast_sell_sell_unified_api")
        response = self.client.post(
            url,
            data={
                "kind": "common_item",
                "product_id": product.id,
                "quantity": 1,
                "payment_method": "cash",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["ok"])
        self.assertIn("sale_id", data)
        self.assertEqual(data["kind"], "common_item")

        # Verify sale created
        sale = ClothingSale.objects.get(id=data["sale_id"])
        self.assertEqual(sale.product, product)
        self.assertIsNone(sale.barcode_unit)  # No barcode unit for common
        self.assertEqual(sale.quantity, 1)
        self.assertEqual(sale.total_price, Decimal("30.00"))

        # Verify stock decremented
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 9)

    def test_sell_common_stock_multiple_qty(self):
        """Test selling multiple units of common stock"""
        # Create common stock product
        product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.CLOTHING,
            name="Socks - White",
            cost_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity_in_stock=20,
            is_active=True,
        )

        # Sell qty=5
        url = reverse("verticals:clothing_fast_sell_sell_unified_api")
        response = self.client.post(
            url,
            data={
                "kind": "common_item",
                "product_id": product.id,
                "quantity": 5,
                "payment_method": "cash",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["ok"])

        # Verify sale
        sale = ClothingSale.objects.get(id=data["sale_id"])
        self.assertEqual(sale.quantity, 5)
        self.assertEqual(sale.total_price, Decimal("50.00"))  # 5 * 10

        # Verify stock decremented correctly
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 15)  # 20 - 5

    def test_sell_common_stock_insufficient_stock(self):
        """Test selling more than available stock (should fail)"""
        # Create product with limited stock
        product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.CLOTHING,
            name="Limited Item",
            selling_price=Decimal("50.00"),
            quantity_in_stock=3,
            is_active=True,
        )

        # Try to sell qty=5 (only 3 available)
        url = reverse("verticals:clothing_fast_sell_sell_unified_api")
        response = self.client.post(
            url,
            data={
                "kind": "common_item",
                "product_id": product.id,
                "quantity": 5,
                "payment_method": "cash",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()

        self.assertFalse(data["ok"])
        self.assertIn("insufficient stock", data["error"].lower())

        # Verify no sale created
        sale_count = ClothingSale.objects.filter(product=product).count()
        self.assertEqual(sale_count, 0)

        # Verify stock unchanged
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 3)


class TestTrackedUnitsListView(ClothingUnifiedFastSellTestCase):
    """Test tracked units list view"""

    def test_tracked_units_list_view_accessible(self):
        """Test that tracked units list view is accessible"""
        # Create product
        product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.CLOTHING,
            name="Test Product",
            is_active=True,
        )

        # Create some tracked units
        for i in range(3):
            ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location,
                product=product,
                barcode=f"UNIT{i:03d}",
                category="shoes",
                size="42",
                cost_price=Decimal("50.00"),
                selling_price=Decimal("80.00"),
                status="IN_STOCK",
                is_active=True,
                created_by=self.user,
            )

        # Access view
        url = reverse("verticals:clothing_tracked_units_list", args=[product.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tracked Units")
        self.assertContains(response, "UNIT000")
        self.assertContains(response, "UNIT001")
        self.assertContains(response, "UNIT002")

    def test_tracked_units_list_filters(self):
        """Test filtering tracked units by status"""
        # Create product
        product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.CLOTHING,
            name="Test Product",
            is_active=True,
        )

        # Create available units
        ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=product,
            barcode="AVAIL001",
            category="shoes",
            size="42",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00"),
            status="IN_STOCK",
            is_active=True,
            created_by=self.user,
        )

        # Create sold unit
        ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=product,
            barcode="SOLD001",
            category="shoes",
            size="42",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00"),
            status="SOLD",
            is_active=True,
            created_by=self.user,
        )

        url = reverse("verticals:clothing_tracked_units_list", args=[product.id])

        # Test "available" filter (default)
        response = self.client.get(url, {"status": "available"})
        self.assertContains(response, "AVAIL001")
        self.assertNotContains(response, "SOLD001")

        # Test "sold" filter
        response = self.client.get(url, {"status": "sold"})
        self.assertContains(response, "SOLD001")
        self.assertNotContains(response, "AVAIL001")

        # Test "all" filter
        response = self.client.get(url, {"status": "all"})
        self.assertContains(response, "AVAIL001")
        self.assertContains(response, "SOLD001")


class TestHubClickablePills(ClothingUnifiedFastSellTestCase):
    """Test that Hub page has clickable tracked pills"""

    def test_hub_tracked_pill_is_link(self):
        """Test that tracked pill in Hub is a clickable link"""
        # Create product with tracked units
        product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.CLOTHING,
            name="Test Product",
            is_active=True,
        )

        ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=product,
            barcode="UNIT001",
            category="shoes",
            size="42",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00"),
            status="IN_STOCK",
            is_active=True,
            created_by=self.user,
        )

        # Access Hub
        url = reverse("verticals:clothing_hub")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check that tracked pill exists and is a link
        tracked_units_url = reverse("verticals:clothing_tracked_units_list", args=[product.id])
        self.assertContains(response, tracked_units_url)
        self.assertContains(response, "Tracked (1 units)")


class TestEndToEndFlow(ClothingUnifiedFastSellTestCase):
    """End-to-end integration tests"""

    def test_e2e_tracked_unit_fast_sell(self):
        """Test complete flow: scan tracked barcode → instant sell"""
        # Create tracked unit
        unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="E2E_TRACK001",
            category="shoes",
            size="42",
            brand="Nike",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00"),
            status="IN_STOCK",
            is_active=True,
            created_by=self.user,
        )

        # Step 1: Lookup
        lookup_url = reverse("verticals:clothing_fast_sell_lookup_unified_api")
        lookup_response = self.client.get(lookup_url, {"code": "E2E_TRACK001"})
        lookup_data = lookup_response.json()

        self.assertTrue(lookup_data["found"])
        self.assertEqual(lookup_data["kind"], "tracked_unit")

        # Step 2: Sell
        sell_url = reverse("verticals:clothing_fast_sell_sell_unified_api")
        sell_response = self.client.post(
            sell_url,
            data={
                "kind": "tracked_unit",
                "tracked_unit_id": lookup_data["item"]["tracked_unit_id"],
                "payment_method": "cash",
            },
            content_type="application/json",
        )
        sell_data = sell_response.json()

        self.assertTrue(sell_data["ok"])

        # Verify sale
        sale = ClothingSale.objects.get(id=sell_data["sale_id"])
        self.assertEqual(sale.barcode_unit, unit)
        self.assertEqual(sale.total_price, Decimal("80.00"))

        # Verify unit sold
        unit.refresh_from_db()
        self.assertEqual(unit.status, "SOLD")

    def test_e2e_common_stock_fast_sell(self):
        """Test complete flow: scan common product code → instant sell"""
        # Create common stock product
        product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.CLOTHING,
            name="T-Shirt - Blue - M",
            barcode="E2E_COMMON001",
            size="M",
            color="Blue",
            cost_price=Decimal("15.00"),
            selling_price=Decimal("30.00"),
            quantity_in_stock=10,
            is_active=True,
        )

        # Step 1: Lookup
        lookup_url = reverse("verticals:clothing_fast_sell_lookup_unified_api")
        lookup_response = self.client.get(lookup_url, {"code": "E2E_COMMON001"})
        lookup_data = lookup_response.json()

        self.assertTrue(lookup_data["found"])
        self.assertEqual(lookup_data["kind"], "common_item")

        # Step 2: Sell
        sell_url = reverse("verticals:clothing_fast_sell_sell_unified_api")
        sell_response = self.client.post(
            sell_url,
            data={
                "kind": "common_item",
                "product_id": lookup_data["item"]["product_id"],
                "quantity": 1,
                "payment_method": "cash",
            },
            content_type="application/json",
        )
        sell_data = sell_response.json()

        self.assertTrue(sell_data["ok"])

        # Verify sale
        sale = ClothingSale.objects.get(id=sell_data["sale_id"])
        self.assertEqual(sale.product, product)
        self.assertIsNone(sale.barcode_unit)
        self.assertEqual(sale.total_price, Decimal("30.00"))

        # Verify stock decremented
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 9)


class TestResolveProductAPI(ClothingUnifiedFastSellTestCase):
    """Test resolve-product endpoint for getting next available tracked unit"""

    def test_resolve_product_returns_next_available_unit(self):
        """Test resolving a product returns the oldest available tracked unit (FIFO)"""
        # Create product
        product = MerchProduct.objects.create(
            business=self.business,
            name="Nike Sneakers",
            kind=BusinessKind.CLOTHING,
            category="shoes",
            size="42",
            selling_price=Decimal("100.00"),
            cost_price=Decimal("60.00"),
            is_active=True,
        )

        # Create multiple tracked units (different timestamps)
        import time
        unit1 = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=product,
            barcode="UNIT001",
            category="shoes",
            size="42",
            brand="Nike",
            cost_price=Decimal("60.00"),
            selling_price=Decimal("100.00"),
            status="IN_STOCK",
            is_active=True,
            created_by=self.user,
        )
        
        time.sleep(0.01)  # Ensure different timestamp
        
        unit2 = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=product,
            barcode="UNIT002",
            category="shoes",
            size="42",
            brand="Nike",
            cost_price=Decimal("60.00"),
            selling_price=Decimal("100.00"),
            status="IN_STOCK",
            is_active=True,
            created_by=self.user,
        )

        # Resolve - should return oldest (unit1)
        url = reverse("verticals:clothing_fast_sell_resolve_product_api")
        response = self.client.get(url, {
            "product_id": product.id,
            "size": "42",
            "category": "shoes",
            "brand": "Nike"
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["ok"])
        self.assertTrue(data["found"])
        self.assertEqual(data["unit"]["tracked_unit_id"], unit1.id)
        self.assertEqual(data["unit"]["barcode"], "UNIT001")

    def test_resolve_product_skips_sold_units(self):
        """Test that resolve-product only returns IN_STOCK units"""
        # Create product
        product = MerchProduct.objects.create(
            business=self.business,
            name="Adidas Shoes",
            kind=BusinessKind.CLOTHING,
            category="shoes",
            size="40",
            selling_price=Decimal("90.00"),
            cost_price=Decimal("50.00"),
            is_active=True,
        )

        # Create sold unit
        sold_unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=product,
            barcode="SOLD_UNIT",
            category="shoes",
            size="40",
            brand="Adidas",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("90.00"),
            status="SOLD",  # Already sold
            is_active=True,
            created_by=self.user,
        )

        # Create available unit
        available_unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=product,
            barcode="AVAILABLE_UNIT",
            category="shoes",
            size="40",
            brand="Adidas",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("90.00"),
            status="IN_STOCK",
            is_active=True,
            created_by=self.user,
        )

        # Resolve - should return available unit, not sold one
        url = reverse("verticals:clothing_fast_sell_resolve_product_api")
        response = self.client.get(url, {
            "product_id": product.id,
            "size": "40",
            "category": "shoes",
            "brand": "Adidas"
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["ok"])
        self.assertTrue(data["found"])
        self.assertEqual(data["unit"]["tracked_unit_id"], available_unit.id)
        self.assertEqual(data["unit"]["barcode"], "AVAILABLE_UNIT")

    def test_resolve_product_not_found(self):
        """Test resolve-product returns not found when no units available"""
        # Create product with no tracked units
        product = MerchProduct.objects.create(
            business=self.business,
            name="Empty Product",
            kind=BusinessKind.CLOTHING,
            category="shirts",
            size="M",
            selling_price=Decimal("50.00"),
            is_active=True,
        )

        # Try to resolve
        url = reverse("verticals:clothing_fast_sell_resolve_product_api")
        response = self.client.get(url, {
            "product_id": product.id,
            "size": "M",
            "category": "shirts",
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["ok"])
        self.assertFalse(data["found"])
        self.assertIn("error", data)
        self.assertIn("No available units", data["error"])

    def test_resolve_product_requires_product_id(self):
        """Test resolve-product validates product_id is provided"""
        url = reverse("verticals:clothing_fast_sell_resolve_product_api")
        response = self.client.get(url, {})

        self.assertEqual(response.status_code, 400)
        data = response.json()

        self.assertFalse(data["ok"])
        self.assertIn("error", data)
        self.assertIn("product_id required", data["error"])

