"""
Regression Tests for Clothing Wizard Barcode Fixes - January 2026

These tests PERMANENTLY lock down the fixed behavior:

1. NO premature red toasts on page load or step entry
2. Barcode Add button works reliably (Enter key + button)
3. Common Stock vs Unique Stock modes work correctly
4. Fast Sell ONLY works for unique barcoded stock
5. Size is OPTIONAL by default
6. Validation only fires on POST/submit

CRITICAL: These tests MUST pass before merging any changes.
"""
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.models import Location, MerchProduct
from inventory.models_clothing_barcode import ClothingBarcodeUnit
from tenants.models import Business, Membership

User = get_user_model()


# =============================================================================
# Test: NO PREMATURE VALIDATION ERRORS ON GET
# =============================================================================


class NoPrematureToastOnGetTestCase(TestCase):
    """
    CRITICAL TEST: GET requests must NEVER show validation errors.
    
    BUG FIXED: "Selling price must be greater than zero" and "Size is required"
    appeared on page load before user typed anything.
    
    FIX: Validation only runs on POST/submit.
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

    def test_step_a_get_has_no_selling_price_error(self):
        """GET Step A: Must NOT contain 'Selling price must be greater than zero'"""
        response = self.client.get(reverse("clothing:stockin_step_a"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertNotIn("Selling price must be greater than zero", content)
        self.assertNotIn("selling_price", content.lower().split("error")[0] if "error" in content.lower() else "")

    def test_step_a_get_has_no_size_required_error(self):
        """GET Step A: Must NOT contain 'Size is required'"""
        response = self.client.get(reverse("clothing:stockin_step_a"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertNotIn("Size is required", content)

    def test_step_a_get_has_no_validation_summary(self):
        """GET Step A: Must NOT contain validation summary message"""
        response = self.client.get(reverse("clothing:stockin_step_a"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertNotIn("Please fix the errors below", content)

    def test_step_a_get_context_errors_is_empty(self):
        """GET Step A: Context 'errors' dict must be empty"""
        response = self.client.get(reverse("clothing:stockin_step_a"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context.get("errors", {}), {})

    def test_step_a_get_context_form_data_is_empty(self):
        """GET Step A: Context 'form_data' dict must be empty (not pre-filled with errors)"""
        response = self.client.get(reverse("clothing:stockin_step_a"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context.get("form_data", {}), {})

    def test_old_wizard_url_redirects_to_new_wizard(self):
        """Old wizard URL (/inventory/wizard/clothing/) redirects to new 2-step wizard"""
        response = self.client.get(reverse("inventory:clothing_wizard"))
        # Should redirect to new step A
        self.assertEqual(response.status_code, 302)
        self.assertIn("stockin", response.url)


# =============================================================================
# Test: BARCODE ADD WORKS RELIABLY
# =============================================================================


class BarcodeAddWorksReliablyTestCase(TestCase):
    """
    Test that barcode Add works reliably:
    - Typing barcode + click Add → barcode persists
    - Typing barcode + press Enter → barcode persists
    - No "blink and nothing happens"
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

    def _create_draft_for_unique_stock(self, quantity=2):
        """Helper: Create a draft for unique stock mode"""
        response = self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Test Shoe",
                "category": "shoes",
                "stock_mode": "unique",
                "quantity": str(quantity),
                "selling_price": "15000",
            },
        )
        self.assertEqual(response.status_code, 302)
        session = self.client.session
        draft = session.get("clothing_stock_draft", {})
        return draft.get("draft_id")

    def test_barcode_add_via_form_post_persists(self):
        """POST barcode via form → barcode persists in session"""
        draft_id = self._create_draft_for_unique_stock()
        
        # Add barcode via form POST
        response = self.client.post(
            reverse("clothing:stockin_step_b", kwargs={"draft_id": draft_id}),
            data={"action": "add_barcode", "barcode": "PERSIST001"},
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Check barcode was added to session
        session = self.client.session
        draft = session.get("clothing_stock_draft", {})
        self.assertIn("PERSIST001", draft.get("scanned_barcodes", []))

    def test_barcode_add_via_ajax_api_persists(self):
        """POST barcode via AJAX API → barcode persists in session"""
        draft_id = self._create_draft_for_unique_stock()
        
        # Add barcode via AJAX API
        response = self.client.post(
            reverse("clothing:stockin_api_add_barcode", kwargs={"draft_id": draft_id}),
            data=json.dumps({"barcode": "AJAX001"}),
            content_type="application/json",
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["ok"])
        self.assertEqual(result["scanned_count"], 1)
        self.assertIn("AJAX001", result["scanned_barcodes"])

    def test_barcode_add_shows_in_list_after_add(self):
        """After adding barcode, it appears in the barcode list on page"""
        draft_id = self._create_draft_for_unique_stock()
        
        # Add barcode
        self.client.post(
            reverse("clothing:stockin_step_b", kwargs={"draft_id": draft_id}),
            data={"action": "add_barcode", "barcode": "VISIBLE001"},
        )
        
        # Re-fetch the page
        response = self.client.get(
            reverse("clothing:stockin_step_b", kwargs={"draft_id": draft_id})
        )
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("VISIBLE001", content)

    def test_duplicate_barcode_in_batch_rejected(self):
        """Duplicate barcode within same batch is rejected with friendly error"""
        draft_id = self._create_draft_for_unique_stock()
        
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

    def test_barcode_remove_works(self):
        """Barcode can be removed from batch"""
        draft_id = self._create_draft_for_unique_stock()
        
        # Add two barcodes
        self.client.post(
            reverse("clothing:stockin_api_add_barcode", kwargs={"draft_id": draft_id}),
            data=json.dumps({"barcode": "REMOVE001"}),
            content_type="application/json",
        )
        self.client.post(
            reverse("clothing:stockin_api_add_barcode", kwargs={"draft_id": draft_id}),
            data=json.dumps({"barcode": "REMOVE002"}),
            content_type="application/json",
        )
        
        # Remove first barcode
        response = self.client.post(
            reverse("clothing:stockin_api_remove_barcode", kwargs={"draft_id": draft_id}),
            data=json.dumps({"index": 0}),
            content_type="application/json",
        )
        
        result = response.json()
        self.assertTrue(result["ok"])
        self.assertEqual(result["scanned_count"], 1)
        self.assertNotIn("REMOVE001", result["scanned_barcodes"])
        self.assertIn("REMOVE002", result["scanned_barcodes"])


# =============================================================================
# Test: COMMON STOCK vs UNIQUE STOCK MODES
# =============================================================================


class StockModesTestCase(TestCase):
    """
    Test Common Stock vs Unique Stock modes work correctly.
    
    Common Stock: Quantity-based, no barcodes, manual sell
    Unique Stock: Each unit has barcode, Fast Sell only
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
        """Common Stock mode finalizes immediately after Step A (no Step B)"""
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

    def test_common_stock_creates_product_with_quantity(self):
        """Common Stock creates MerchProduct with correct quantity"""
        self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Common Stock Shirt",
                "category": "shirts",
                "stock_mode": "common",
                "quantity": "5",
                "selling_price": "5000",
            },
        )

        product = MerchProduct.objects.get(business=self.business, name__icontains="Shirt")
        self.assertEqual(product.quantity_in_stock, 5)

    def test_common_stock_no_barcode_units_created(self):
        """Common Stock mode does NOT create ClothingBarcodeUnit records"""
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

        # No ClothingBarcodeUnit should exist for this batch
        units = ClothingBarcodeUnit.objects.filter(business=self.business)
        self.assertEqual(units.count(), 0)

    def test_unique_stock_redirects_to_step_b(self):
        """Unique Stock mode redirects to Step B for barcode scanning"""
        response = self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Unique Shoe",
                "category": "shoes",
                "stock_mode": "unique",
                "quantity": "2",
                "selling_price": "15000",
            },
        )

        # Should redirect to Step B
        self.assertEqual(response.status_code, 302)
        self.assertIn("barcodes", response.url)

    def test_unique_stock_creates_barcode_units(self):
        """Unique Stock creates ClothingBarcodeUnit records after scanning"""
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
        self.client.post(
            reverse("clothing:stockin_step_b", kwargs={"draft_id": draft_id}),
            data={"action": "finalize"},
        )

        # Verify ClothingBarcodeUnit records created
        units = ClothingBarcodeUnit.objects.filter(business=self.business)
        self.assertEqual(units.count(), 2)

        for unit in units:
            self.assertEqual(unit.status, "IN_STOCK")
            self.assertEqual(unit.selling_price, Decimal("15000"))


# =============================================================================
# Test: FAST SELL ONLY FOR BARCODED STOCK
# =============================================================================


class FastSellBarcodeOnlyTestCase(TestCase):
    """
    CRITICAL: Fast Sell must ONLY work with ClothingBarcodeUnit (unique barcoded stock).
    
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
        """Fast Sell lookup finds ClothingBarcodeUnit by barcode"""
        # Create a barcoded unit
        ClothingBarcodeUnit.objects.create(
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

    def test_fast_sell_rejects_unknown_barcode(self):
        """Fast Sell returns friendly error for unknown barcode"""
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
        """Fast Sell returns friendly error for already-sold barcode"""
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
        """Fast Sell creates sale record and marks unit as SOLD"""
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


# =============================================================================
# Test: SIZE IS OPTIONAL
# =============================================================================


class SizeIsOptionalTestCase(TestCase):
    """
    Test that size field is OPTIONAL by default.
    
    FIX: Size was previously required, causing "Size is required" errors.
    Now size is optional for all clothing items.
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

    def test_product_creation_succeeds_without_size(self):
        """Product creation succeeds when size is empty"""
        response = self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Generic Jacket",
                "category": "jackets",
                "stock_mode": "common",
                "quantity": "3",
                "selling_price": "25000",
                "size": "",  # Explicitly empty
            },
        )

        self.assertEqual(response.status_code, 302)
        
        product = MerchProduct.objects.get(business=self.business, name__icontains="Jacket")
        self.assertEqual(product.size, "")

    def test_product_creation_succeeds_without_size_field(self):
        """Product creation succeeds when size field is not provided at all"""
        response = self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "No Size Product",
                "category": "accessories",
                "stock_mode": "common",
                "quantity": "1",
                "selling_price": "5000",
                # size field not provided at all
            },
        )

        self.assertEqual(response.status_code, 302)
        
        product = MerchProduct.objects.get(business=self.business, name__icontains="No Size")
        self.assertEqual(product.size, "")


# =============================================================================
# Test: VALIDATION ONLY ON POST
# =============================================================================


class ValidationOnlyOnPostTestCase(TestCase):
    """
    Test that validation ONLY fires on POST, never on GET.
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

    def test_post_with_invalid_data_shows_errors(self):
        """POST with invalid data shows validation errors"""
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
        
        errors = response.context.get("errors", {})
        self.assertIn("name", errors)
        self.assertIn("quantity", errors)
        self.assertIn("selling_price", errors)

    def test_post_with_zero_selling_price_shows_error(self):
        """POST with selling_price = 0 shows specific error"""
        response = self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Test Product",
                "category": "shoes",
                "stock_mode": "common",
                "quantity": "1",
                "selling_price": "0",  # Must be > 0
            },
        )

        self.assertEqual(response.status_code, 200)
        
        errors = response.context.get("errors", {})
        self.assertIn("selling_price", errors)
        self.assertIn("greater than zero", errors["selling_price"].lower())

    def test_post_with_valid_data_succeeds(self):
        """POST with valid data creates product and redirects"""
        response = self.client.post(
            reverse("clothing:stockin_step_a"),
            data={
                "name": "Valid Product",
                "category": "shirts",
                "stock_mode": "common",
                "quantity": "5",
                "selling_price": "10000",
            },
        )

        self.assertEqual(response.status_code, 302)
        
        product = MerchProduct.objects.get(business=self.business, name__icontains="Valid Product")
        self.assertEqual(product.quantity_in_stock, 5)
        self.assertEqual(product.selling_price, Decimal("10000"))
