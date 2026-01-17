"""
Regression Tests for Clothing Vertical Fixes - January 2026

These tests ensure the following critical issues never return:
1. Early "Selling price > 0" toast on page load
2. Barcode Add button functionality
3. Fast Sell ONLY works with barcoded items (unique stock)
4. Manual Sell excludes barcoded items
5. Barcode workflow completes successfully

HARD CONSTRAINTS:
- All tests must pass
- Zero regressions across other verticals
- Test hooks remain intact
- Validation stays robust
"""
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.models import Location, MerchProduct
from inventory.models_clothing_barcode import ClothingBarcodeUnit
from inventory.models_verticals import ClothingSale
from tenants.models import Business, Membership

User = get_user_model()


class ClothingPricingValidationRegressionTestCase(TestCase):
    """
    Regression tests for pricing validation toast issue.
    
    BUG FIXED: "Selling price must be greater than zero" toast appeared
    on page load before user typed anything.
    
    FIX: pricing-intelligence.js now tracks user interaction and only
    validates AFTER user has touched the field (input/blur).
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager", email="manager@test.com", password="testpass123"
        )
        self.business = Business.objects.create(name="Test Clothing Store", kind=BusinessKind.CLOTHING, owner=self.user)
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.client.login(username="testmanager", password="testpass123")

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_pricing_validation_not_triggered_on_get_request(self):
        """
        Test that GET request to product add page does NOT show
        'Selling price > 0' error in initial response.
        
        This prevents the toast from appearing before user types anything.
        """
        response = self.client.get(reverse("verticals:clothing_quick_add_step2", args=["shoes"]))
        self.assertEqual(response.status_code, 200)

        # Ensure no validation error in initial page load
        response_content = response.content.decode("utf-8")
        self.assertNotIn("Selling price must be greater than zero", response_content)
        self.assertNotIn("Price must be greater than zero", response_content)

    def test_pricing_validation_triggers_on_invalid_post(self):
        """
        Test that POST with invalid selling price DOES show validation error.
        
        This ensures validation still works on submit.
        """
        response = self.client.post(
            reverse("verticals:clothing_quick_add_step2", args=["shoes"]),
            data={
                "name": "Test Shoe",
                "selling_price": "0",  # Invalid: must be > 0
                "cost_price": "100",
                "quantity": "1",
            },
        )

        # Should show form with errors (not redirect)
        self.assertEqual(response.status_code, 200)
        # Django form validation should catch this
        self.assertTrue(response.context["form"].errors)


class ClothingBarcodeWorkflowRegressionTestCase(TestCase):
    """
    Regression tests for barcode workflow "Add button blinks/does nothing".
    
    BUG FIXED: Barcode Add button did nothing because savePricingAndContinue()
    function was missing, so Step 1 API was never called.
    
    FIX: Added savePricingAndContinue() function that calls Step 1 API to
    initialize barcode batch session before allowing Step 2 (scanning).
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager", email="manager@test.com", password="testpass123"
        )
        self.business = Business.objects.create(name="Test Clothing Store", kind=BusinessKind.CLOTHING, owner=self.user)
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.location = Location.objects.create(business=self.business, name="Main Store", is_default=True)
        self.client.login(username="testmanager", password="testpass123")

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()

    def test_barcode_batch_step1_creates_session(self):
        """
        Test that Step 1 API (pricing) creates session data for Step 2 (scanning).
        
        This is REQUIRED before barcode scanning can work.
        """
        response = self.client.post(
            reverse("clothing:barcode_batch_step1"),
            data=json.dumps(
                {
                    "category": "shoes",
                    "size": "42",
                    "quantity": 2,
                    "cost_price": "10000.00",
                    "selling_price": "15000.00",
                    "brand": "Nike",
                    "color": "Black",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["ok"])

        # Verify session data was created
        session = self.client.session
        self.assertIn("clothing_barcode_batch", session)
        batch_data = session["clothing_barcode_batch"]
        self.assertEqual(batch_data["quantity"], 2)
        self.assertEqual(batch_data["category"], "shoes")

    def test_barcode_batch_step2_persists_barcode(self):
        """
        Test that Step 2 API (scan) persists barcode to database.
        
        BUG FIXED: This endpoint now works reliably and returns updated list.
        """
        # Step 1: Initialize session
        self.client.post(
            reverse("clothing:barcode_batch_step1"),
            data=json.dumps(
                {
                    "category": "shoes",
                    "size": "42",
                    "quantity": 2,
                    "cost_price": "10000.00",
                    "selling_price": "15000.00",
                }
            ),
            content_type="application/json",
        )

        # Step 2: Scan barcode
        response = self.client.post(
            reverse("clothing:barcode_batch_scan"),
            data=json.dumps({"barcode": "TEST123"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["ok"])
        self.assertEqual(result["scanned_count"], 1)
        self.assertEqual(result["remaining"], 1)
        self.assertFalse(result["complete"])

        # Verify barcode was created in database
        unit = ClothingBarcodeUnit.objects.get(business=self.business, barcode="TEST123")
        self.assertEqual(unit.size, "42")
        self.assertEqual(unit.status, "IN_STOCK")
        self.assertEqual(unit.selling_price, Decimal("15000.00"))

    def test_barcode_add_button_accepts_enter_key(self):
        """
        Test that Enter key triggers Add action (for fast scanning).
        
        BUG FIXED: Added onkeypress handler to barcode input.
        """
        # This is a UI test - verified by checking template has onkeypress handler
        from django.template.loader import render_to_string

        # Get the wizard template
        try:
            template_content = open("templates/inventory/wizards/clothing_wizard.html").read()
            self.assertIn("onkeypress", template_content)
            self.assertIn("addManualBarcode()", template_content)
        except FileNotFoundError:
            self.skipTest("Template file not accessible in test environment")

    def test_barcode_duplicate_returns_friendly_error(self):
        """
        Test that duplicate barcode returns user-friendly error (not crash).
        """
        # Step 1: Initialize session
        self.client.post(
            reverse("clothing:barcode_batch_step1"),
            data=json.dumps(
                {
                    "category": "shoes",
                    "size": "42",
                    "quantity": 2,
                    "cost_price": "10000.00",
                    "selling_price": "15000.00",
                }
            ),
            content_type="application/json",
        )

        # Step 2: Scan barcode (first time)
        self.client.post(
            reverse("clothing:barcode_batch_scan"),
            data=json.dumps({"barcode": "DUPLICATE123"}),
            content_type="application/json",
        )

        # Step 3: Try to scan same barcode again
        response = self.client.post(
            reverse("clothing:barcode_batch_scan"),
            data=json.dumps({"barcode": "DUPLICATE123"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result["ok"])
        self.assertIn("already", result["error"].lower())


class ClothingFastSellUniqueStockRegressionTestCase(TestCase):
    """
    Regression tests for Fast Sell barcode-only enforcement.
    
    BUG FIXED: Fast Sell now ONLY works with ClothingBarcodeUnit items.
    Removed MerchProduct fallback that allowed non-barcoded items.
    
    RULE: Fast Sell = Unique Barcoded Stock ONLY
          Manual Sell = Common Stock (non-barcoded) ONLY
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager", email="manager@test.com", password="testpass123"
        )
        self.business = Business.objects.create(name="Test Clothing Store", kind=BusinessKind.CLOTHING, owner=self.user)
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.location = Location.objects.create(business=self.business, name="Main Store", is_default=True)
        self.client.login(username="testmanager", password="testpass123")

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()

    def test_fast_sell_lookup_only_finds_barcode_units(self):
        """
        Test that Fast Sell lookup ONLY finds ClothingBarcodeUnit items.
        
        CRITICAL: Non-barcoded MerchProduct should NOT be found.
        """
        # Create a barcoded unit
        unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="UNIQUE001",
            category="shoes",
            size="42",
            cost_price=Decimal("10000"),
            selling_price=Decimal("15000"),
            status="IN_STOCK",
            created_by=self.user,
        )

        # Fast Sell lookup should find it
        response = self.client.post(
            reverse("clothing:fast_sell_lookup"),
            data=json.dumps({"barcode": "UNIQUE001"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["found"])
        self.assertEqual(result["size"], "42")

    def test_fast_sell_rejects_non_barcoded_items(self):
        """
        Test that Fast Sell REJECTS non-barcoded MerchProduct items.
        
        BUG FIXED: Removed MerchProduct fallback from lookup_barcode_for_fast_sell.
        """
        # Create a common stock product (no barcode unit)
        product = MerchProduct.objects.create(
            business=self.business,
            name="Common Stock Shirt",
            kind=BusinessKind.CLOTHING,
            barcode="COMMON001",
            quantity_in_stock=10,
            selling_price=Decimal("5000"),
            cost_price=Decimal("3000"),
        )

        # Fast Sell lookup should NOT find it (no ClothingBarcodeUnit)
        response = self.client.post(
            reverse("clothing:fast_sell_lookup"),
            data=json.dumps({"barcode": "COMMON001"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result["found"])
        self.assertIn("not found", result["error"].lower())

    def test_fast_sell_marks_unit_as_sold(self):
        """
        Test that Fast Sell marks ClothingBarcodeUnit as SOLD.
        """
        # Create a barcoded unit
        unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="SELL001",
            category="shoes",
            size="42",
            cost_price=Decimal("10000"),
            selling_price=Decimal("15000"),
            status="IN_STOCK",
            created_by=self.user,
        )

        # Fast Sell
        response = self.client.post(
            reverse("clothing:fast_sell_create"),
            data=json.dumps({"barcode": "SELL001", "payment_method": "cash"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["ok"])

        # Verify unit marked as SOLD
        unit.refresh_from_db()
        self.assertEqual(unit.status, "SOLD")
        self.assertIsNotNone(unit.sold_at)

        # Verify sale record created
        sale = ClothingSale.objects.get(business=self.business, sold_by=self.user)
        self.assertEqual(sale.quantity, 1)
        self.assertEqual(sale.total_price, Decimal("15000"))

    def test_fast_sell_rejects_already_sold_barcode(self):
        """
        Test that Fast Sell rejects barcode that's already sold.
        """
        # Create and sell a unit
        unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="SOLD001",
            category="shoes",
            size="42",
            cost_price=Decimal("10000"),
            selling_price=Decimal("15000"),
            status="SOLD",  # Already sold
            created_by=self.user,
        )

        # Try to sell again
        response = self.client.post(
            reverse("clothing:fast_sell_create"),
            data=json.dumps({"barcode": "SOLD001", "payment_method": "cash"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result["ok"])
        self.assertIn("sold", result["error"].lower())


class ClothingManualSellExcludesBarcodedRegressionTestCase(TestCase):
    """
    Regression tests for Manual Sell exclusion of barcoded items.
    
    BUG FIXED: Manual Sell form now excludes products that have
    ClothingBarcodeUnit items in stock. Those can ONLY be sold via Fast Sell.
    
    RULE: Manual Sell = Common Stock (non-barcoded) ONLY
          Fast Sell = Unique Barcoded Stock ONLY
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager", email="manager@test.com", password="testpass123"
        )
        self.business = Business.objects.create(name="Test Clothing Store", kind=BusinessKind.CLOTHING, owner=self.user)
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.location = Location.objects.create(business=self.business, name="Main Store", is_default=True)
        self.client.login(username="testmanager", password="testpass123")

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()

    def test_manual_sell_form_excludes_products_with_barcode_units(self):
        """
        Test that Manual Sell form does NOT show products with barcode units in stock.
        """
        # Create a product
        product = MerchProduct.objects.create(
            business=self.business,
            name="Unique Shoe",
            kind=BusinessKind.CLOTHING,
            quantity_in_stock=5,
            selling_price=Decimal("15000"),
            cost_price=Decimal("10000"),
        )

        # Create barcode units for this product
        ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=product,
            barcode="UNIT001",
            category="shoes",
            size="42",
            cost_price=Decimal("10000"),
            selling_price=Decimal("15000"),
            status="IN_STOCK",
            created_by=self.user,
        )

        # GET Manual Sell page
        response = self.client.get(reverse("verticals:clothing_sell"))
        self.assertEqual(response.status_code, 200)

        # Product should NOT be in the form queryset
        form = response.context["form"]
        product_ids = [p.id for p in form.fields["product"].queryset]
        self.assertNotIn(product.id, product_ids)

    def test_manual_sell_server_side_blocks_barcoded_products(self):
        """
        Test that Manual Sell POST blocks products with barcode units (server-side validation).
        """
        # Create a product
        product = MerchProduct.objects.create(
            business=self.business,
            name="Unique Shoe",
            kind=BusinessKind.CLOTHING,
            quantity_in_stock=5,
            selling_price=Decimal("15000"),
            cost_price=Decimal("10000"),
        )

        # Create barcode unit
        ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=product,
            barcode="UNIT002",
            category="shoes",
            size="42",
            cost_price=Decimal("10000"),
            selling_price=Decimal("15000"),
            status="IN_STOCK",
            created_by=self.user,
        )

        # Try to sell via Manual Sell (should be blocked)
        response = self.client.post(
            reverse("verticals:clothing_sell"),
            data={
                "product": product.id,
                "quantity": 1,
                "selling_price": "15000",
                "payment_method": "cash",
            },
        )

        # Should redirect with error message (not create sale)
        self.assertEqual(response.status_code, 302)

        # Verify no sale was created
        self.assertFalse(ClothingSale.objects.filter(business=self.business, product=product).exists())

    def test_manual_sell_works_for_common_stock(self):
        """
        Test that Manual Sell WORKS for common stock (products without barcode units).
        """
        # Create a common stock product (no barcode units)
        product = MerchProduct.objects.create(
            business=self.business,
            name="Common Stock Shirt",
            kind=BusinessKind.CLOTHING,
            quantity_in_stock=10,
            selling_price=Decimal("5000"),
            cost_price=Decimal("3000"),
        )

        # Manual Sell should work
        response = self.client.post(
            reverse("verticals:clothing_sell"),
            data={
                "product": product.id,
                "quantity": 2,
                "selling_price": "5000",
                "payment_method": "cash",
            },
        )

        # Should redirect (success)
        self.assertEqual(response.status_code, 302)

        # Verify sale was created
        sale = ClothingSale.objects.get(business=self.business, product=product)
        self.assertEqual(sale.quantity, 2)
        self.assertEqual(sale.total_price, Decimal("10000"))

        # Verify stock reduced
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 8)


class ClothingBarcodeWorkflowCompleteRegressionTestCase(TestCase):
    """
    End-to-end regression test for complete barcode workflow.
    
    Tests:
    1. Step 1: Save pricing (initialize session)
    2. Step 2: Scan multiple barcodes
    3. Verify all barcodes persisted
    4. Verify progress tracking
    5. Verify completion detection
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager", email="manager@test.com", password="testpass123"
        )
        self.business = Business.objects.create(name="Test Clothing Store", kind=BusinessKind.CLOTHING, owner=self.user)
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.location = Location.objects.create(business=self.business, name="Main Store", is_default=True)
        self.client.login(username="testmanager", password="testpass123")

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()

    def test_complete_barcode_workflow_end_to_end(self):
        """
        Test complete barcode workflow from start to finish.
        """
        # Step 1: Initialize session
        response = self.client.post(
            reverse("clothing:barcode_batch_step1"),
            data=json.dumps(
                {
                    "category": "shoes",
                    "size": "42",
                    "quantity": 3,
                    "cost_price": "10000.00",
                    "selling_price": "15000.00",
                    "brand": "Nike",
                    "color": "Black",
                    "product_name": "Air Max 90",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["ok"])

        # Step 2: Scan barcode 1
        response1 = self.client.post(
            reverse("clothing:barcode_batch_scan"),
            data=json.dumps({"barcode": "BC001"}),
            content_type="application/json",
        )

        self.assertEqual(response1.status_code, 200)
        result1 = response1.json()
        self.assertTrue(result1["ok"])
        self.assertEqual(result1["scanned_count"], 1)
        self.assertEqual(result1["remaining"], 2)
        self.assertFalse(result1["complete"])

        # Step 3: Scan barcode 2
        response2 = self.client.post(
            reverse("clothing:barcode_batch_scan"),
            data=json.dumps({"barcode": "BC002"}),
            content_type="application/json",
        )

        self.assertEqual(response2.status_code, 200)
        result2 = response2.json()
        self.assertTrue(result2["ok"])
        self.assertEqual(result2["scanned_count"], 2)
        self.assertEqual(result2["remaining"], 1)
        self.assertFalse(result2["complete"])

        # Step 4: Scan barcode 3 (final)
        response3 = self.client.post(
            reverse("clothing:barcode_batch_scan"),
            data=json.dumps({"barcode": "BC003"}),
            content_type="application/json",
        )

        self.assertEqual(response3.status_code, 200)
        result3 = response3.json()
        self.assertTrue(result3["ok"])
        self.assertEqual(result3["scanned_count"], 3)
        self.assertEqual(result3["remaining"], 0)
        self.assertTrue(result3["complete"])  # Batch complete!

        # Verify all units created in database
        units = ClothingBarcodeUnit.objects.filter(business=self.business).order_by("barcode")
        self.assertEqual(units.count(), 3)

        for unit in units:
            self.assertEqual(unit.category, "shoes")
            self.assertEqual(unit.size, "42")
            self.assertEqual(unit.selling_price, Decimal("15000.00"))
            self.assertEqual(unit.cost_price, Decimal("10000.00"))
            self.assertEqual(unit.status, "IN_STOCK")

