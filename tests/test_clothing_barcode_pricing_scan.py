"""
Tests for Clothing barcode wizard with inline pricing on scan page.

Tests that:
1. Scan page shows inline pricing form when pricing is missing
2. Pricing can be saved inline, then scanning enabled
3. Backend never returns 400 for validation errors
4. Complete flow works: has_barcode -> pricing -> scan -> save
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind
from tenants.models import Business
import json

User = get_user_model()


class ClothingBarcodePricingScanTest(TestCase):
    """Test the inline pricing + scan flow for clothing with barcodes"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="manager",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
        self.business = Business.objects.create(
            name="Test Clothing Store",
            slug="test-clothing-barcode-pricing",
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status="ACTIVE",
        )
        self.user.active_business = self.business
        self.user.save()

        self.client.login(username="manager", password="testpass123")
        self.submit_url = reverse("inventory:clothing_wizard_submit")

    def test_submit_with_complete_pricing_and_barcodes_success(self):
        """
        Complete happy path: has_barcode=yes, valid pricing, correct barcodes
        Should succeed without any 400 errors
        """
        data = {
            "category": "shoes",
            "size": "42",
            "has_barcode": "yes",
            "selling_price": "15000.00",
            "cost_price": "10000.00",
            "initial_stock": 2,
            "barcodes": ["SHOE_001", "SHOE_002"]
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data),
            content_type="application/json"
        )

        # Must return 200, not 400
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result.get("success"), f"Expected success but got: {result.get('error')}")

        # Verify product created
        product = MerchProduct.objects.filter(
            business=self.business,
            category="shoes",
            size="42"
        ).first()
        self.assertIsNotNone(product)
        self.assertEqual(product.quantity_in_stock, 2)
        self.assertEqual(product.selling_price, Decimal("15000.00"))
        self.assertEqual(product.cost_price, Decimal("10000.00"))

    def test_save_pricing_then_scan_requires_exact_qty(self):
        """
        After saving pricing, scanning requires exactly qty unique barcodes.
        
        Test scenario:
        - Submit with qty=2, but only 1 barcode -> 200 with error (not 400)
        - Submit with qty=2, with 2 barcodes -> success
        """
        # Case 1: Insufficient barcodes (1 instead of 2)
        data_insufficient = {
            "category": "shirt",
            "size": "M",
            "has_barcode": "yes",
            "selling_price": "5000.00",
            "cost_price": "3000.00",
            "initial_stock": 2,
            "barcodes": ["SHIRT_001"]  # Only 1 barcode
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data_insufficient),
            content_type="application/json"
        )

        # CRITICAL: Must return 200, not 400
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result.get("success"))
        self.assertIn("barcode", result["error"].lower())
        self.assertIn("2", result["error"])  # Should mention required count

        # Verify no product created
        self.assertEqual(
            MerchProduct.objects.filter(business=self.business, category="shirt").count(),
            0
        )

        # Case 2: Correct number of barcodes
        data_correct = {
            "category": "shirt",
            "size": "M",
            "has_barcode": "yes",
            "selling_price": "5000.00",
            "cost_price": "3000.00",
            "initial_stock": 2,
            "barcodes": ["SHIRT_001", "SHIRT_002"]  # Correct count
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data_correct),
            content_type="application/json"
        )

        # Should succeed
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result.get("success"))

        # Verify product created
        product = MerchProduct.objects.filter(business=self.business, category="shirt").first()
        self.assertIsNotNone(product)
        self.assertEqual(product.quantity_in_stock, 2)

    def test_submit_never_returns_400_for_validation(self):
        """
        All validation errors must return 200 with error messages, never 400.
        This ensures the wizard can display errors without crashing.
        """
        test_cases = [
            {
                "name": "Missing quantity with has_barcode",
                "data": {
                    "category": "shoes",
                    "size": "40",
                    "has_barcode": "yes",
                    "selling_price": "10000.00",
                    "initial_stock": 0,  # Invalid
                    "barcodes": []
                },
                "expected_error_contains": ["quantity", "barcode"]
            },
            {
                "name": "Missing selling price with has_barcode",
                "data": {
                    "category": "shoes",
                    "size": "40",
                    "has_barcode": "yes",
                    "selling_price": "0",  # Invalid
                    "initial_stock": 2,
                    "barcodes": ["BC1", "BC2"]
                },
                "expected_error_contains": "price"
            },
            {
                "name": "Missing barcodes when has_barcode=yes",
                "data": {
                    "category": "shoes",
                    "size": "40",
                    "has_barcode": "yes",
                    "selling_price": "10000.00",
                    "initial_stock": 2,
                    "barcodes": []  # Empty when should have 2
                },
                "expected_error_contains": "barcode"
            },
            {
                "name": "Negative cost price",
                "data": {
                    "category": "shoes",
                    "size": "40",
                    "has_barcode": "yes",
                    "selling_price": "10000.00",
                    "cost_price": "-100",  # Invalid
                    "initial_stock": 1,
                    "barcodes": ["BC1"]
                },
                "expected_error_contains": "cost"
            },
            {
                "name": "Missing category",
                "data": {
                    "size": "M",
                    "has_barcode": "yes",
                    "selling_price": "5000.00",
                    "initial_stock": 1,
                    "barcodes": ["BC1"]
                },
                "expected_error_contains": "category"
            },
            {
                "name": "Missing size",
                "data": {
                    "category": "shirt",
                    "has_barcode": "yes",
                    "selling_price": "5000.00",
                    "initial_stock": 1,
                    "barcodes": ["BC1"]
                },
                "expected_error_contains": "size"
            },
        ]

        for test_case in test_cases:
            with self.subTest(case=test_case["name"]):
                response = self.client.post(
                    self.submit_url,
                    data=json.dumps(test_case["data"]),
                    content_type="application/json"
                )

                # CRITICAL: Must return 200, never 400
                self.assertEqual(
                    response.status_code,
                    200,
                    f"Test '{test_case['name']}' returned {response.status_code} instead of 200"
                )

                # Check response contains error
                result = response.json()
                self.assertFalse(result.get("success"))
                self.assertIn("error", result)

                # Check error message contains expected keywords
                error_msg = result["error"].lower()
                expected = test_case["expected_error_contains"]
                if isinstance(expected, str):
                    expected = [expected]

                matched = any(keyword in error_msg for keyword in expected)
                self.assertTrue(
                    matched,
                    f"Error '{result['error']}' doesn't contain any of {expected}"
                )

    def test_no_barcode_flow_still_works(self):
        """
        Verify that the no-barcode flow continues to work correctly.
        User should not be forced to scan barcodes if they select "no".
        """
        data = {
            "category": "jeans",
            "size": "32",
            "has_barcode": "no",
            "selling_price": "8000.00",
            "cost_price": "5000.00",
            "initial_stock": 3
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data),
            content_type="application/json"
        )

        # Should succeed
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result.get("success"))

        # Verify product created without barcode
        product = MerchProduct.objects.filter(
            business=self.business,
            category="jeans",
            size="32"
        ).first()
        self.assertIsNotNone(product)
        self.assertEqual(product.quantity_in_stock, 3)
        self.assertIsNone(product.barcode)

    def test_duplicate_barcode_detection_returns_200(self):
        """
        If user tries to use a duplicate barcode, return 200 with friendly error.
        """
        # Create existing product with barcode
        existing = MerchProduct.objects.create(
            business=self.business,
            name="Existing Shoes",
            kind=BusinessKind.CLOTHING,
            category="shoes",
            size="40",
            spec_label="Size 40",
            selling_price=Decimal("10000.00"),
            cost_price=Decimal("7000.00"),
            quantity_in_stock=1,
            barcode="DUPLICATE_CODE",
            is_active=True,
        )

        # Try to create new product with same barcode
        data = {
            "category": "shirt",
            "size": "L",
            "has_barcode": "yes",
            "selling_price": "5000.00",
            "initial_stock": 1,
            "barcodes": ["DUPLICATE_CODE"]
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data),
            content_type="application/json"
        )

        # Must return 200, not 400
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result.get("success"))
        self.assertIn("barcode", result["error"].lower())
        # Error should be friendly and mention the existing product
        self.assertTrue(
            "already" in result["error"].lower() or "duplicate" in result["error"].lower()
        )

    def test_whitespace_trimming_in_pricing_and_barcodes(self):
        """
        Barcodes and pricing with whitespace should be trimmed automatically.
        """
        data = {
            "category": "shirt",
            "size": "M",
            "has_barcode": "yes",
            "selling_price": "  5000.00  ",  # With whitespace
            "cost_price": " 3000.00 ",
            "initial_stock": 2,
            "barcodes": ["  BARCODE_A  ", "BARCODE_B   "]  # With whitespace
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result.get("success"))

        # Verify product created with trimmed values
        product = MerchProduct.objects.filter(business=self.business).first()
        self.assertIsNotNone(product)
        self.assertEqual(product.selling_price, Decimal("5000.00"))
        self.assertEqual(product.barcode, "BARCODE_A")  # Trimmed

    def test_pricing_validation_on_inline_form(self):
        """
        Test that pricing validation works correctly when entered inline.
        Invalid pricing should return 200 with clear error messages.
        """
        # Zero selling price
        data_zero_price = {
            "category": "shoes",
            "size": "42",
            "has_barcode": "yes",
            "selling_price": "0.00",
            "initial_stock": 2,
            "barcodes": ["BC1", "BC2"]
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data_zero_price),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result.get("success"))
        self.assertIn("price", result["error"].lower())

        # Negative selling price
        data_negative_price = {
            "category": "shoes",
            "size": "42",
            "has_barcode": "yes",
            "selling_price": "-100",
            "initial_stock": 2,
            "barcodes": ["BC1", "BC2"]
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data_negative_price),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result.get("success"))
        self.assertIn("price", result["error"].lower())

    def test_large_quantity_with_many_barcodes(self):
        """
        Test that large quantities (e.g., 10 items) work correctly.
        """
        qty = 10
        barcodes = [f"BARCODE_{str(i).zfill(3)}" for i in range(qty)]

        data = {
            "category": "shirt",
            "size": "M",
            "has_barcode": "yes",
            "selling_price": "5000.00",
            "cost_price": "3000.00",
            "initial_stock": qty,
            "barcodes": barcodes
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result.get("success"))

        # Verify product with correct quantity
        product = MerchProduct.objects.filter(business=self.business).first()
        self.assertIsNotNone(product)
        self.assertEqual(product.quantity_in_stock, qty)


class ClothingBarcodePricingScanEdgeCasesTest(TestCase):
    """Test edge cases in the inline pricing + scan flow"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="manager",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
        self.business = Business.objects.create(
            name="Test Store Edge Cases",
            slug="test-edge-pricing-scan",
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status="ACTIVE",
        )
        self.user.active_business = self.business
        self.user.save()

        self.client.login(username="manager", password="testpass123")
        self.submit_url = reverse("inventory:clothing_wizard_submit")

    def test_decimal_precision_in_pricing(self):
        """Ensure decimal precision is preserved in pricing"""
        data = {
            "category": "shirt",
            "size": "M",
            "has_barcode": "yes",
            "selling_price": "5999.99",
            "cost_price": "3499.50",
            "initial_stock": 1,
            "barcodes": ["PRECISE_BC"]
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result.get("success"))

        product = MerchProduct.objects.filter(business=self.business).first()
        self.assertEqual(product.selling_price, Decimal("5999.99"))
        self.assertEqual(product.cost_price, Decimal("3499.50"))

    def test_empty_cost_price_is_optional(self):
        """Cost price should be optional"""
        data = {
            "category": "shoes",
            "size": "42",
            "has_barcode": "yes",
            "selling_price": "15000.00",
            # No cost_price provided
            "initial_stock": 1,
            "barcodes": ["NO_COST_BC"]
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result.get("success"))

        product = MerchProduct.objects.filter(business=self.business).first()
        self.assertIsNotNone(product)
        # Cost price should be None or 0
        self.assertTrue(product.cost_price is None or product.cost_price == Decimal("0"))

