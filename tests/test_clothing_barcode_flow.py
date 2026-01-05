"""
Comprehensive tests for Clothing barcode wizard flow.

Tests the new flow where:
1. User selects "has barcode" yes/no
2. User enters pricing & quantity
3. If yes, user scans barcodes
4. Product is created with correct barcode associations
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


class ClothingBarcodeFlowTest(TestCase):
    """Test the clothing barcode wizard flow"""

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
            slug="test-clothing-barcode",
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status="ACTIVE",
        )
        self.user.active_business = self.business
        self.user.save()

        self.client.login(username="manager", password="testpass123")
        self.submit_url = reverse("inventory:clothing_wizard_submit")

    def test_has_barcode_requires_price_and_qty_first(self):
        """
        If user selects has_barcode=yes but doesn't provide valid price/qty,
        server returns 200 with error message (not 400).
        """
        # Submit with has_barcode=yes but missing/invalid pricing
        data = {
            "category": "shirt",
            "size": "M",
            "has_barcode": "yes",
            "selling_price": 0,  # Invalid (must be > 0)
            "initial_stock": 2,
            "barcodes": ["BARCODE001", "BARCODE002"]
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data),
            content_type="application/json"
        )

        # CRITICAL: Must return 200, not 400
        self.assertEqual(response.status_code, 200)

        # Check response contains error
        result = response.json()
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)
        self.assertIn("price", result["error"].lower())

        # Verify no product was created
        self.assertEqual(MerchProduct.objects.filter(business=self.business).count(), 0)

    def test_barcode_step_requires_exact_qty_unique_insufficient(self):
        """
        qty=2, barcodes=[A] -> 200 error, no stock created
        User must scan exactly qty unique barcodes.
        """
        data = {
            "category": "shoes",
            "size": "42",
            "has_barcode": "yes",
            "selling_price": "15000.00",
            "cost_price": "10000.00",
            "initial_stock": 2,
            "barcodes": ["BARCODE001"]  # Only 1 barcode, but qty=2
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data),
            content_type="application/json"
        )

        # CRITICAL: Must return 200, not 400
        self.assertEqual(response.status_code, 200)

        # Check response contains error about insufficient barcodes
        result = response.json()
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)
        self.assertIn("scan", result["error"].lower())
        self.assertIn("2", result["error"])  # Should mention qty=2

        # Verify no product was created
        self.assertEqual(MerchProduct.objects.filter(business=self.business).count(), 0)

    def test_barcode_step_requires_exact_qty_unique_success(self):
        """
        qty=2, barcodes=[A,B] -> success redirect, creates 2 units with those barcodes
        """
        data = {
            "category": "shoes",
            "size": "42",
            "has_barcode": "yes",
            "selling_price": "15000.00",
            "cost_price": "10000.00",
            "initial_stock": 2,
            "barcodes": ["BARCODE001", "BARCODE002"]  # Correct number of barcodes
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

        # Verify product was created
        product = MerchProduct.objects.filter(
            business=self.business,
            category="shoes",
            size="42"
        ).first()
        self.assertIsNotNone(product)
        self.assertEqual(product.quantity_in_stock, 2)
        self.assertEqual(product.selling_price, Decimal("15000.00"))
        self.assertEqual(product.cost_price, Decimal("10000.00"))

        # Check that barcode is set (first one)
        self.assertEqual(product.barcode, "BARCODE001")

    def test_barcode_duplicate_detection(self):
        """
        If user tries to use a barcode that's already in the database,
        system should detect it and return error.
        """
        # Create existing product with barcode
        existing_product = MerchProduct.objects.create(
            business=self.business,
            name="Existing Shoes",
            kind=BusinessKind.CLOTHING,
            category="shoes",
            size="40",
            spec_label="Size 40",
            selling_price=Decimal("10000.00"),
            cost_price=Decimal("7000.00"),
            quantity_in_stock=1,
            barcode="DUPLICATE_BARCODE",
            is_active=True,
        )

        # Try to create new product with same barcode
        data = {
            "category": "shirt",
            "size": "L",
            "has_barcode": "yes",
            "selling_price": "5000.00",
            "cost_price": "3000.00",
            "initial_stock": 1,
            "barcodes": ["DUPLICATE_BARCODE"]  # Same barcode as existing product
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data),
            content_type="application/json"
        )

        # Should return 200 with error (not 400)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)
        # Error should mention duplicate or existing
        error_msg = result["error"].lower()
        self.assertTrue("duplicate" in error_msg or "already" in error_msg or "exists" in error_msg)

    def test_no_barcode_still_works(self):
        """
        qty=2, has_barcode=no -> success, creates stock without barcodes
        The "no barcode" flow must continue to work correctly.
        """
        data = {
            "category": "jeans",
            "size": "32",
            "has_barcode": "no",  # No barcode
            "selling_price": "8000.00",
            "cost_price": "5000.00",
            "initial_stock": 2
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

        # Verify product was created without barcode
        product = MerchProduct.objects.filter(
            business=self.business,
            category="jeans",
            size="32"
        ).first()
        self.assertIsNotNone(product)
        self.assertEqual(product.quantity_in_stock, 2)
        self.assertIsNone(product.barcode)  # No barcode set

    def test_never_returns_400_on_submit_for_validation_errors(self):
        """
        Missing or invalid fields should return 200 with form errors, not 400.
        This ensures the wizard stays open and users can fix errors.
        """
        test_cases = [
            # Missing category
            {
                "data": {
                    "size": "M",
                    "selling_price": "5000.00",
                    "initial_stock": 1,
                    "has_barcode": "no"
                },
                "expected_error_contains": "category"
            },
            # Missing size
            {
                "data": {
                    "category": "shirt",
                    "selling_price": "5000.00",
                    "initial_stock": 1,
                    "has_barcode": "no"
                },
                "expected_error_contains": "size"
            },
            # Invalid selling price (zero)
            {
                "data": {
                    "category": "shirt",
                    "size": "M",
                    "selling_price": "0",
                    "initial_stock": 1,
                    "has_barcode": "no"
                },
                "expected_error_contains": "price"
            },
            # Invalid selling price (negative)
            {
                "data": {
                    "category": "shirt",
                    "size": "M",
                    "selling_price": "-100",
                    "initial_stock": 1,
                    "has_barcode": "no"
                },
                "expected_error_contains": "price"
            },
            # Negative quantity
            {
                "data": {
                    "category": "shirt",
                    "size": "M",
                    "selling_price": "5000.00",
                    "initial_stock": -1,
                    "has_barcode": "no"
                },
                "expected_error_contains": "quantity"
            },
        ]

        for i, test_case in enumerate(test_cases):
            with self.subTest(case=i):
                response = self.client.post(
                    self.submit_url,
                    data=json.dumps(test_case["data"]),
                    content_type="application/json"
                )

                # CRITICAL: Must return 200, not 400
                self.assertEqual(
                    response.status_code,
                    200,
                    f"Test case {i} returned {response.status_code} instead of 200"
                )

                # Check response contains error
                result = response.json()
                self.assertFalse(result.get("success"))
                self.assertIn("error", result)
                self.assertIn(
                    test_case["expected_error_contains"],
                    result["error"].lower()
                )

    def test_multiple_products_with_unique_barcodes(self):
        """
        Test creating multiple products, each with unique barcodes.
        Ensures barcode uniqueness is enforced across products.
        """
        # Create first product with barcode
        data1 = {
            "category": "shoes",
            "size": "40",
            "has_barcode": "yes",
            "selling_price": "10000.00",
            "cost_price": "7000.00",
            "initial_stock": 1,
            "barcodes": ["SHOE_BARCODE_001"]
        }

        response1 = self.client.post(
            self.submit_url,
            data=json.dumps(data1),
            content_type="application/json"
        )

        self.assertEqual(response1.status_code, 200)
        result1 = response1.json()
        self.assertTrue(result1.get("success"))

        # Create second product with different barcode (should succeed)
        data2 = {
            "category": "shirt",
            "size": "L",
            "has_barcode": "yes",
            "selling_price": "5000.00",
            "cost_price": "3000.00",
            "initial_stock": 1,
            "barcodes": ["SHIRT_BARCODE_001"]
        }

        response2 = self.client.post(
            self.submit_url,
            data=json.dumps(data2),
            content_type="application/json"
        )

        self.assertEqual(response2.status_code, 200)
        result2 = response2.json()
        self.assertTrue(result2.get("success"))

        # Verify both products exist
        products = MerchProduct.objects.filter(business=self.business)
        self.assertEqual(products.count(), 2)

        # Verify barcodes are unique
        barcodes = [p.barcode for p in products]
        self.assertEqual(len(barcodes), len(set(barcodes)))  # All unique

    def test_barcode_check_api_endpoint(self):
        """Test the barcode duplicate check API endpoint"""
        # Create a product with a barcode
        existing_product = MerchProduct.objects.create(
            business=self.business,
            name="Test Product",
            kind=BusinessKind.CLOTHING,
            category="shirt",
            size="M",
            spec_label="Size M",
            selling_price=Decimal("5000.00"),
            cost_price=Decimal("3000.00"),
            quantity_in_stock=1,
            barcode="EXISTING_BARCODE",
            is_active=True,
        )

        check_url = reverse("inventory:check_barcode_duplicate")

        # Check existing barcode
        response = self.client.post(
            check_url,
            data=json.dumps({"barcode": "EXISTING_BARCODE"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result.get("exists"))
        self.assertEqual(result.get("product_name"), "Test Product")

        # Check non-existing barcode
        response = self.client.post(
            check_url,
            data=json.dumps({"barcode": "NEW_BARCODE"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result.get("exists"))


class ClothingBarcodeFlowEdgeCasesTest(TestCase):
    """Test edge cases in the barcode flow"""

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
            slug="test-edge-cases",
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status="ACTIVE",
        )
        self.user.active_business = self.business
        self.user.save()

        self.client.login(username="manager", password="testpass123")
        self.submit_url = reverse("inventory:clothing_wizard_submit")

    def test_large_quantity_requires_many_barcodes(self):
        """Test with large quantity (e.g., 10 items) requires 10 unique barcodes"""
        barcodes = [f"BARCODE_{str(i).zfill(3)}" for i in range(10)]

        data = {
            "category": "shirt",
            "size": "M",
            "has_barcode": "yes",
            "selling_price": "5000.00",
            "cost_price": "3000.00",
            "initial_stock": 10,
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
        self.assertEqual(product.quantity_in_stock, 10)

    def test_empty_barcode_list_with_has_barcode_yes(self):
        """If has_barcode=yes but barcodes list is empty, should return error"""
        data = {
            "category": "shoes",
            "size": "40",
            "has_barcode": "yes",
            "selling_price": "10000.00",
            "initial_stock": 2,
            "barcodes": []  # Empty list
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result.get("success"))
        self.assertIn("barcode", result["error"].lower())

    def test_whitespace_trimming_in_barcodes(self):
        """Barcodes with leading/trailing whitespace should be trimmed"""
        data = {
            "category": "shirt",
            "size": "L",
            "has_barcode": "yes",
            "selling_price": "5000.00",
            "initial_stock": 2,
            "barcodes": ["  BARCODE001  ", "BARCODE002   "]  # With whitespace
        }

        response = self.client.post(
            self.submit_url,
            data=json.dumps(data),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result.get("success"))

        # Verify product was created and barcode is trimmed
        product = MerchProduct.objects.filter(business=self.business).first()
        self.assertIsNotNone(product)
        self.assertEqual(product.barcode, "BARCODE001")  # No whitespace

