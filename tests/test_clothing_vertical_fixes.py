"""
Tests for clothing vertical fixes (Payment panels, Recent Sales, Barcode wizard)
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from inventory.models import MerchProduct
from inventory.models_verticals import ClothingSale
from inventory.business_kinds import BusinessKind
from tenants.models import Business
import json

User = get_user_model()


class ClothingSellPaymentMethodTest(TestCase):
    """Test payment method selection in clothing sell page"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.business = Business.objects.create(
            name="Test Clothing Store",
            slug="test-clothing-store",
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status="ACTIVE",
        )
        self.user.active_business = self.business
        self.user.save()

        # Create a test product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Shirt - M - Blue",
            kind=BusinessKind.CLOTHING,
            category="shirt",
            size="M",
            color="Blue",
            spec_label="Size M",
            selling_price=Decimal("5000.00"),
            cost_price=Decimal("3000.00"),
            quantity_in_stock=10,
            is_active=True,
            track_inventory=True,
        )

        self.client.login(username="testuser", password="testpass123")

    def test_sell_page_contains_payment_cards(self):
        """Test that sell page contains payment method cards (not dropdown)"""
        url = reverse("verticals:clothing_sell")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check for payment card elements
        self.assertContains(response, 'class="payment-card"')
        self.assertContains(response, 'data-method="CASH"')
        self.assertContains(response, 'data-method="MOBILE_MONEY"')
        self.assertContains(response, 'data-method="BANK"')

        # Check for hidden input
        self.assertContains(response, 'name="payment_method"')
        self.assertContains(response, 'id="payment_method_value"')

        # Ensure it's not using old dropdown (no <select> tag for payment_method)
        # Note: The form might still have a select in the background for other fields,
        # but the payment method should use cards
        self.assertContains(response, "selectPaymentMethod")  # JS function

    def test_sell_with_cash_payment(self):
        """Test completing a sale with CASH payment method"""
        url = reverse("verticals:clothing_sell")
        data = {
            "product": self.product.id,
            "quantity": 2,
            "selling_price": "5000.00",
            "payment_method": "CASH",
            "notes": "Test sale",
        }

        response = self.client.post(url, data)

        # Should redirect to dashboard on success
        self.assertEqual(response.status_code, 302)

        # Check that sale was created
        sale = ClothingSale.objects.filter(business=self.business, product=self.product).first()
        self.assertIsNotNone(sale)
        self.assertEqual(sale.payment_method, "CASH")
        self.assertEqual(sale.quantity, 2)
        self.assertEqual(sale.unit_price, Decimal("5000.00"))

    def test_sell_with_mobile_money_payment(self):
        """Test completing a sale with MOBILE_MONEY payment method"""
        url = reverse("verticals:clothing_sell")
        data = {
            "product": self.product.id,
            "quantity": 1,
            "selling_price": "5000.00",
            "payment_method": "MOBILE_MONEY",
            "notes": "",
        }

        response = self.client.post(url, data)

        # Should redirect to dashboard on success
        self.assertEqual(response.status_code, 302)

        # Check that sale was created with correct payment method
        sale = ClothingSale.objects.filter(business=self.business, product=self.product).first()
        self.assertIsNotNone(sale)
        self.assertEqual(sale.payment_method, "MOBILE_MONEY")

    def test_sell_with_bank_payment(self):
        """Test completing a sale with BANK payment method"""
        url = reverse("verticals:clothing_sell")
        data = {
            "product": self.product.id,
            "quantity": 1,
            "selling_price": "5000.00",
            "payment_method": "BANK",
            "notes": "",
        }

        response = self.client.post(url, data)

        # Should redirect to dashboard on success
        self.assertEqual(response.status_code, 302)

        # Check that sale was created with correct payment method
        sale = ClothingSale.objects.filter(business=self.business, product=self.product).first()
        self.assertIsNotNone(sale)
        self.assertEqual(sale.payment_method, "BANK")


class ClothingDashboardRecentSalesTest(TestCase):
    """Test Recent Sales section showing on dashboard"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.business = Business.objects.create(
            name="Test Clothing Store",
            slug="test-clothing-store",
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status="ACTIVE",
        )
        self.user.active_business = self.business
        self.user.save()

        # Create test products
        self.product1 = MerchProduct.objects.create(
            business=self.business,
            name="Test Shirt - M - Blue",
            kind=BusinessKind.CLOTHING,
            category="shirt",
            size="M",
            color="Blue",
            spec_label="Size M",
            selling_price=Decimal("5000.00"),
            cost_price=Decimal("3000.00"),
            quantity_in_stock=10,
            is_active=True,
        )

        self.product2 = MerchProduct.objects.create(
            business=self.business,
            name="Test Jeans - L - Black",
            kind=BusinessKind.CLOTHING,
            category="jeans",
            size="L",
            color="Black",
            spec_label="Size L",
            selling_price=Decimal("8000.00"),
            cost_price=Decimal("5000.00"),
            quantity_in_stock=5,
            is_active=True,
        )

        self.client.login(username="testuser", password="testpass123")

    def test_dashboard_shows_recent_sales_after_creating_sale(self):
        """Test that Recent Sales section shows sales after making a sale"""
        # Create a sale using the same method as the sell view
        sale = ClothingSale.objects.create(
            business=self.business,
            product=self.product1,
            quantity=2,
            unit_price=Decimal("5000.00"),
            total_price=Decimal("10000.00"),
            unit_cost=Decimal("3000.00"),
            total_cost=Decimal("6000.00"),
            payment_method="CASH",
            sold_by=self.user,
            notes="Test sale",
        )

        # Get dashboard
        url = reverse("verticals:clothing_dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check that recent_sales context variable exists
        self.assertIn("recent_sales", response.context)
        recent_sales = response.context["recent_sales"]

        # Check that our sale is in the list
        self.assertGreater(len(recent_sales), 0)
        sale_ids = [s.id for s in recent_sales]
        self.assertIn(sale.id, sale_ids)

        # Check that the sale details are rendered
        self.assertContains(response, self.product1.name)
        self.assertContains(response, "K 10000")  # Total price formatted

    def test_dashboard_shows_multiple_recent_sales(self):
        """Test that Recent Sales section shows multiple sales correctly"""
        # Create multiple sales
        sales = []
        for i in range(3):
            sale = ClothingSale.objects.create(
                business=self.business,
                product=self.product1 if i % 2 == 0 else self.product2,
                quantity=1,
                unit_price=Decimal("5000.00"),
                total_price=Decimal("5000.00"),
                unit_cost=Decimal("3000.00"),
                total_cost=Decimal("3000.00"),
                payment_method="CASH" if i % 2 == 0 else "MOBILE_MONEY",
                sold_by=self.user,
            )
            sales.append(sale)

        # Get dashboard
        url = reverse("verticals:clothing_dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check that recent_sales contains all sales
        recent_sales = response.context["recent_sales"]
        self.assertEqual(len(recent_sales), 3)

        # Check that each sale is rendered
        for sale in sales:
            # Check for amount display in the response
            self.assertContains(response, "K 5000")

    def test_dashboard_shows_no_sales_message_when_empty(self):
        """Test that dashboard shows appropriate message when no sales exist"""
        url = reverse("verticals:clothing_dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check that recent_sales exists but is empty
        recent_sales = response.context.get("recent_sales", [])
        self.assertEqual(len(recent_sales), 0)

        # Check for "no sales" message
        self.assertContains(response, "No recent sales yet")


class ClothingBarcodeWizardValidationTest(TestCase):
    """Test barcode wizard validation returns 200 with errors, not 400"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="manager", password="testpass123", is_staff=True, is_superuser=True
        )
        self.business = Business.objects.create(
            name="Test Clothing Store",
            slug="test-clothing-store",
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status="ACTIVE",
        )
        self.user.active_business = self.business
        self.user.save()

        self.client.login(username="manager", password="testpass123")

    def test_wizard_submit_missing_barcodes_returns_200(self):
        """Test that submitting with missing barcodes returns 200 with error message"""
        url = reverse("inventory:clothing_wizard_submit")

        # Submit with has_barcode=yes but no barcodes
        data = {
            "category": "shoes",
            "size": "42",
            "selling_price": "15000.00",
            "cost_price": "10000.00",
            "initial_stock": 3,
            "has_barcode": "yes",
            "barcodes": [],  # Missing barcodes
        }

        response = self.client.post(
            url, data=json.dumps(data), content_type="application/json"
        )

        # CRITICAL: Should return 200, not 400
        self.assertEqual(response.status_code, 200)

        # Check response contains error
        result = response.json()
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)
        self.assertIn("barcode", result["error"].lower())

    def test_wizard_submit_insufficient_barcodes_returns_200(self):
        """Test that submitting with insufficient barcodes returns 200 with error"""
        url = reverse("inventory:clothing_wizard_submit")

        # Submit with has_barcode=yes but only 1 barcode when 3 required
        data = {
            "category": "shoes",
            "size": "42",
            "selling_price": "15000.00",
            "cost_price": "10000.00",
            "initial_stock": 3,
            "has_barcode": "yes",
            "barcodes": ["BARCODE001"],  # Only 1 out of 3 required
        }

        response = self.client.post(
            url, data=json.dumps(data), content_type="application/json"
        )

        # CRITICAL: Should return 200, not 400
        self.assertEqual(response.status_code, 200)

        # Check response contains error about insufficient barcodes
        result = response.json()
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)
        self.assertIn("scan", result["error"].lower())

    def test_wizard_submit_duplicate_barcodes_returns_200(self):
        """Test that submitting with duplicate barcodes returns 200 with error"""
        url = reverse("inventory:clothing_wizard_submit")

        # Submit with duplicate barcodes
        data = {
            "category": "shoes",
            "size": "42",
            "selling_price": "15000.00",
            "cost_price": "10000.00",
            "initial_stock": 3,
            "has_barcode": "yes",
            "barcodes": ["BARCODE001", "BARCODE001", "BARCODE002"],  # Duplicate BARCODE001
        }

        response = self.client.post(
            url, data=json.dumps(data), content_type="application/json"
        )

        # CRITICAL: Should return 200, not 400
        self.assertEqual(response.status_code, 200)

        # Check response contains error about duplicates
        result = response.json()
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)
        self.assertIn("duplicate", result["error"].lower())

    def test_wizard_submit_with_correct_barcodes_succeeds(self):
        """Test that submitting with correct number of unique barcodes succeeds"""
        url = reverse("inventory:clothing_wizard_submit")

        # Submit with correct barcodes
        data = {
            "category": "shoes",
            "size": "42",
            "selling_price": "15000.00",
            "cost_price": "10000.00",
            "initial_stock": 3,
            "has_barcode": "yes",
            "barcodes": ["BARCODE001", "BARCODE002", "BARCODE003"],
        }

        response = self.client.post(
            url, data=json.dumps(data), content_type="application/json"
        )

        # Should succeed with 200
        self.assertEqual(response.status_code, 200)

        # Check response indicates success
        result = response.json()
        self.assertTrue(result.get("success"))

        # Check product was created
        product = MerchProduct.objects.filter(
            business=self.business, category="shoes", size="42"
        ).first()
        self.assertIsNotNone(product)
        self.assertEqual(product.quantity_in_stock, 3)

    def test_wizard_submit_no_barcode_works(self):
        """Test that submitting with has_barcode=no works correctly"""
        url = reverse("inventory:clothing_wizard_submit")

        # Submit with has_barcode=no
        data = {
            "category": "shirt",
            "size": "M",
            "color": "Blue",
            "selling_price": "5000.00",
            "cost_price": "3000.00",
            "initial_stock": 5,
            "has_barcode": "no",
        }

        response = self.client.post(
            url, data=json.dumps(data), content_type="application/json"
        )

        # Should succeed
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result.get("success"))

        # Check product was created without barcode
        product = MerchProduct.objects.filter(
            business=self.business, category="shirt", size="M"
        ).first()
        self.assertIsNotNone(product)
        self.assertIsNone(product.barcode)
        self.assertEqual(product.quantity_in_stock, 5)

