"""
Regression Tests for Redesigned Clothing Stock-In Wizard - January 2026

These tests LOCK DOWN the new 2-step wizard flow and ensure:
1. NO red toast errors on GET (page load / step entry)
2. Barcode Add button works and persists
3. Common Stock vs Unique Stock modes work correctly
4. Fast Sell only works with unique barcoded stock
5. Size is OPTIONAL by default
6. Validation only fires on POST/submit

CRITICAL: These tests must pass BEFORE and AFTER any changes to the wizard.
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


class ClothingWizardNoToastOnGetTestCase(TestCase):
    """
    CRITICAL TEST: Verify NO validation toast errors appear on GET requests.
    
    BUG FIXED: "Selling price must be greater than zero" and "Size is required"
    appeared on page load before user typed anything.
    
    FIX: Validation only runs on POST/submit, never on GET.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager", email="manager@test.com", password="testpass123"
        )
        self.business = Business.objects.create(
            name="Test Clothing Store", kind=BusinessKind.CLOTHING, owner=self.user
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.location = Location.objects.create(business=self.business, name="Main Store", is_default=True)
        self.client.login(username="testmanager", password="testpass123")

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()

    def test_step_a_get_has_no_validation_errors(self):
        """
        GET Step A: Response must NOT contain validation error messages.
        
        This test FAILS on broken behavior (validation on GET).
        """
        response = self.client.get(reverse("clothing:stockin_step_a"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        
        # CRITICAL: These strings must NOT appear on initial page load
        self.assertNotIn("Selling price must be greater than zero", content)
        self.assertNotIn("Selling price is required", content)
        self.assertNotIn("Size is required", content)
        self.assertNotIn("Product name is required", content)
        self.assertNotIn("Quantity must be at least 1", content)
        
        # Should NOT have validation summary
        self.assertNotIn("Please fix the errors below", content)

    def test_step_a_get_has_empty_form(self):
        """
        GET Step A: Form should be empty (no pre-filled values from previous errors).
        """
        response = self.client.get(reverse("clothing:stockin_step_a"))
        self.assertEqual(response.status_code, 200)
        
        # Context should have empty errors dict
        self.assertEqual(response.context.get("errors", {}), {})

    def test_step_b_get_requires_draft(self):
        """
        GET Step B without draft should redirect to Step A.
        """
        response = self.client.get(
            reverse("clothing:stockin_step_b", kwargs={"draft_id": "invalid123"})
        )
        # Should redirect to Step A with error message
        self.assertEqual(response.status_code, 302)


class ClothingWizardValidationOnSubmitTestCase(TestCase):
    """
    Tests for validation behavior on POST (submit).
    
    Validation errors should only appear AFTER user submits, not before.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager", email="manager@test.com", password="testpass123"
        )
        self.business = Business.objects.create(
            name="Test Clothing Store", kind=BusinessKind.CLOTHING, owner=self.user
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.location = Location.objects.create(business=self.business, name="Main Store", is_default=True)
        self.client.login(username="testmanager", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()

    def test_step_a_post_invalid_shows_errors(self):
        """
        POST Step A with invalid data shows validation errors.
        """
        response = self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "",  # Required, empty
                "category": "shoes",
                "stock_mode": "common",
                "quantity": "0",  # Must be >= 1
                "selling_price": "",  # Required
            },
        )

        self.assertEqual(response.status_code, 200)
        
        # Should have errors
        errors = response.context.get("errors", {})
        self.assertIn("name", errors)
        self.assertIn("quantity", errors)
        self.assertIn("selling_price", errors)

    def test_step_a_post_valid_common_stock_redirects_to_dashboard(self):
        """
        POST Step A with valid Common Stock data redirects to dashboard.
        """
        response = self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Test T-Shirt",
                "category": "tshirts",
                "stock_mode": "common",
                "quantity": "5",
                "selling_price": "5000",
                "cost_price": "3000",
                "size": "",  # Optional
            },
        )

        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertIn("clothing", response.url)
        
        # Product should be created
        product = MerchProduct.objects.get(business=self.business, name__icontains="T-Shirt")
        self.assertEqual(product.quantity_in_stock, 5)
        self.assertEqual(product.selling_price, Decimal("5000"))

    def test_step_a_post_valid_unique_stock_redirects_to_step_b(self):
        """
        POST Step A with valid Unique Stock data redirects to Step B.
        """
        response = self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Nike Air Max",
                "category": "shoes",
                "stock_mode": "unique",
                "quantity": "2",
                "selling_price": "15000",
                "cost_price": "10000",
                "size": "42",
                "brand": "Nike",
            },
        )

        # Should redirect to Step B
        self.assertEqual(response.status_code, 302)
        self.assertIn("barcodes", response.url)

    def test_size_is_optional(self):
        """
        Size field is OPTIONAL - product creation succeeds without size.
        """
        response = self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Vintage Jacket",
                "category": "jackets",
                "stock_mode": "common",
                "quantity": "3",
                "selling_price": "25000",
                "size": "",  # Explicitly empty - should be OK
            },
        )

        self.assertEqual(response.status_code, 302)
        
        # Product should be created
        product = MerchProduct.objects.get(business=self.business, name__icontains="Jacket")
        self.assertEqual(product.size, "")


class ClothingWizardBarcodeFlowTestCase(TestCase):
    """
    Tests for barcode scanning flow (Unique Stock mode).
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager", email="manager@test.com", password="testpass123"
        )
        self.business = Business.objects.create(
            name="Test Clothing Store", kind=BusinessKind.CLOTHING, owner=self.user
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.location = Location.objects.create(business=self.business, name="Main Store", is_default=True)
        self.client.login(username="testmanager", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()

    def test_barcode_add_persists_to_session(self):
        """
        Adding a barcode in Step B persists it to the draft session.
        """
        # Step A: Create draft for unique stock
        self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Test Shoe",
                "category": "shoes",
                "stock_mode": "unique",
                "quantity": "2",
                "selling_price": "15000",
            },
        )

        # Get draft from session
        session = self.client.session
        draft = session.get("clothing_stock_draft", {})
        draft_id = draft.get("draft_id")
        self.assertIsNotNone(draft_id)

        # Step B: Add first barcode
        response = self.client.post(
            reverse("clothing:stockin_step_b", kwargs={"draft_id": draft_id}),
            data={"action": "add_barcode", "barcode": "BARCODE001"},
        )

        self.assertEqual(response.status_code, 200)
        
        # Check barcode was added
        session = self.client.session
        draft = session.get("clothing_stock_draft", {})
        self.assertIn("BARCODE001", draft.get("scanned_barcodes", []))

    def test_barcode_add_via_ajax(self):
        """
        Adding barcode via AJAX API works.
        """
        # Step A: Create draft
        self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Test Shoe",
                "category": "shoes",
                "stock_mode": "unique",
                "quantity": "2",
                "selling_price": "15000",
            },
        )

        session = self.client.session
        draft = session.get("clothing_stock_draft", {})
        draft_id = draft.get("draft_id")

        # AJAX: Add barcode
        response = self.client.post(
            reverse("clothing:stockin_api_add_barcode", kwargs={"draft_id": draft_id}),
            data=json.dumps({"barcode": "AJAX001"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["ok"])
        self.assertEqual(result["scanned_count"], 1)
        self.assertEqual(result["remaining"], 1)
        self.assertFalse(result["complete"])

    def test_duplicate_barcode_in_batch_rejected(self):
        """
        Duplicate barcode within same batch is rejected with friendly error.
        """
        # Step A: Create draft
        self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Test Shoe",
                "category": "shoes",
                "stock_mode": "unique",
                "quantity": "2",
                "selling_price": "15000",
            },
        )

        session = self.client.session
        draft = session.get("clothing_stock_draft", {})
        draft_id = draft.get("draft_id")

        # Add first barcode
        self.client.post(
            reverse("clothing:stockin_api_add_barcode", kwargs={"draft_id": draft_id}),
            data=json.dumps({"barcode": "DUP001"}),
            content_type="application/json",
        )

        # Try to add same barcode again
        response = self.client.post(
            reverse("clothing:stockin_api_add_barcode", kwargs={"draft_id": draft_id}),
            data=json.dumps({"barcode": "DUP001"}),
            content_type="application/json",
        )

        result = response.json()
        self.assertFalse(result["ok"])
        self.assertIn("already", result["error"].lower())

    def test_complete_barcode_flow_creates_units(self):
        """
        Completing barcode flow creates ClothingBarcodeUnit records.
        """
        # Step A
        self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Test Shoe",
                "category": "shoes",
                "stock_mode": "unique",
                "quantity": "2",
                "selling_price": "15000",
                "cost_price": "10000",
                "size": "42",
            },
        )

        session = self.client.session
        draft = session.get("clothing_stock_draft", {})
        draft_id = draft.get("draft_id")

        # Add both barcodes
        self.client.post(
            reverse("clothing:stockin_api_add_barcode", kwargs={"draft_id": draft_id}),
            data=json.dumps({"barcode": "UNIT001"}),
            content_type="application/json",
        )
        self.client.post(
            reverse("clothing:stockin_api_add_barcode", kwargs={"draft_id": draft_id}),
            data=json.dumps({"barcode": "UNIT002"}),
            content_type="application/json",
        )

        # Finalize
        response = self.client.post(
            reverse("clothing:stockin_step_b", kwargs={"draft_id": draft_id}),
            data={"action": "finalize"},
        )

        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)

        # Verify ClothingBarcodeUnit records created
        units = ClothingBarcodeUnit.objects.filter(business=self.business)
        self.assertEqual(units.count(), 2)
        
        for unit in units:
            self.assertEqual(unit.status, "IN_STOCK")
            self.assertEqual(unit.selling_price, Decimal("15000"))
            self.assertEqual(unit.size, "42")


class ClothingWizardCommonStockTestCase(TestCase):
    """
    Tests for Common Stock mode (skips barcode step).
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager", email="manager@test.com", password="testpass123"
        )
        self.business = Business.objects.create(
            name="Test Clothing Store", kind=BusinessKind.CLOTHING, owner=self.user
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.location = Location.objects.create(business=self.business, name="Main Store", is_default=True)
        self.client.login(username="testmanager", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()

    def test_common_stock_skips_step_b(self):
        """
        Common Stock mode finalizes immediately after Step A (no Step B).
        """
        response = self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Basic T-Shirt",
                "category": "tshirts",
                "stock_mode": "common",
                "quantity": "10",
                "selling_price": "3000",
            },
        )

        # Should redirect to dashboard, NOT to barcodes
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("barcodes", response.url)

        # Product should be created with correct quantity
        product = MerchProduct.objects.get(business=self.business, name__icontains="T-Shirt")
        self.assertEqual(product.quantity_in_stock, 10)

    def test_common_stock_no_barcode_units_created(self):
        """
        Common Stock mode does NOT create ClothingBarcodeUnit records.
        """
        self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Common Stock Item",
                "category": "shirts",
                "stock_mode": "common",
                "quantity": "5",
                "selling_price": "5000",
            },
        )

        # No ClothingBarcodeUnit should exist
        units = ClothingBarcodeUnit.objects.filter(business=self.business)
        self.assertEqual(units.count(), 0)


class ClothingFastSellBarcodeOnlyTestCase(TestCase):
    """
    Tests for Fast Sell - MUST only work with barcoded items.
    
    RULE: Fast Sell = Unique Barcoded Stock ONLY
          Manual Sell = Common Stock (non-barcoded) ONLY
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager", email="manager@test.com", password="testpass123"
        )
        self.business = Business.objects.create(
            name="Test Clothing Store", kind=BusinessKind.CLOTHING, owner=self.user
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.location = Location.objects.create(business=self.business, name="Main Store", is_default=True)
        self.client.login(username="testmanager", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()

    def test_fast_sell_finds_barcoded_unit(self):
        """
        Fast Sell lookup finds ClothingBarcodeUnit by barcode.
        """
        # Create a barcoded unit
        unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="FASTSELL001",
            category="shoes",
            size="42",
            cost_price=Decimal("10000"),
            selling_price=Decimal("15000"),
            status="IN_STOCK",
            created_by=self.user,
        )

        response = self.client.post(
            reverse("clothing:fast_sell_lookup"),
            data=json.dumps({"barcode": "FASTSELL001"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["found"])
        self.assertEqual(result["size"], "42")
        self.assertEqual(Decimal(result["selling_price"]), Decimal("15000"))

    def test_fast_sell_rejects_non_barcoded_item(self):
        """
        Fast Sell lookup does NOT find common stock (non-barcoded) items.
        """
        # Create a common stock product (no ClothingBarcodeUnit)
        product = MerchProduct.objects.create(
            business=self.business,
            name="Common Stock Shirt",
            kind=BusinessKind.CLOTHING,
            barcode="COMMON001",  # Barcode on MerchProduct, but no ClothingBarcodeUnit
            quantity_in_stock=10,
            selling_price=Decimal("5000"),
        )

        response = self.client.post(
            reverse("clothing:fast_sell_lookup"),
            data=json.dumps({"barcode": "COMMON001"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result["found"])
        self.assertIn("not found", result["error"].lower())

    def test_fast_sell_rejects_unknown_barcode(self):
        """
        Fast Sell returns friendly error for unknown barcode.
        """
        response = self.client.post(
            reverse("clothing:fast_sell_lookup"),
            data=json.dumps({"barcode": "UNKNOWN999"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result["found"])
        self.assertIn("not found", result["error"].lower())

    def test_fast_sell_rejects_already_sold_barcode(self):
        """
        Fast Sell returns friendly error for already-sold barcode.
        """
        # Create a sold unit
        ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="SOLD001",
            category="shoes",
            size="42",
            selling_price=Decimal("15000"),
            status="SOLD",  # Already sold
            created_by=self.user,
        )

        response = self.client.post(
            reverse("clothing:fast_sell_lookup"),
            data=json.dumps({"barcode": "SOLD001"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result["found"])
        self.assertIn("sold", result["error"].lower())

    def test_fast_sell_creates_sale_and_marks_sold(self):
        """
        Fast Sell creates sale record and marks unit as SOLD.
        """
        unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="SELLME001",
            category="shoes",
            size="42",
            cost_price=Decimal("10000"),
            selling_price=Decimal("15000"),
            status="IN_STOCK",
            created_by=self.user,
        )

        response = self.client.post(
            reverse("clothing:fast_sell_create"),
            data=json.dumps({"barcode": "SELLME001", "payment_method": "cash"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["ok"])
        self.assertEqual(Decimal(result["amount"]), Decimal("15000"))

        # Verify unit marked as SOLD
        unit.refresh_from_db()
        self.assertEqual(unit.status, "SOLD")
        self.assertIsNotNone(unit.sold_at)

        # Verify sale record created
        sale = ClothingSale.objects.filter(business=self.business).first()
        self.assertIsNotNone(sale)
        self.assertEqual(sale.total_price, Decimal("15000"))


class ClothingOldWizardSizeOptionalTestCase(TestCase):
    """
    Tests for old wizard API - size must be optional.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager", email="manager@test.com", password="testpass123"
        )
        self.business = Business.objects.create(
            name="Test Clothing Store", kind=BusinessKind.CLOTHING, owner=self.user
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.location = Location.objects.create(business=self.business, name="Main Store", is_default=True)
        self.client.login(username="testmanager", password="testpass123")

        session = self.client.session
        session["active_business_id"] = self.business.id
        session["active_location_id"] = self.location.id
        session.save()

    def test_old_wizard_barcode_step1_size_optional(self):
        """
        Old barcode batch step 1 API accepts empty size.
        """
        response = self.client.post(
            reverse("clothing:barcode_batch_step1"),
            data=json.dumps({
                "category": "jackets",
                "size": "",  # Empty - should be OK
                "quantity": 2,
                "cost_price": "10000.00",
                "selling_price": "15000.00",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["ok"])

