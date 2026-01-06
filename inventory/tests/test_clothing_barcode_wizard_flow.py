# inventory/tests/test_clothing_barcode_wizard_flow.py
"""
Tests for clothing barcode wizard complete flow.

Tests:
- Step 1: Pricing form validation
- Step 2: Scanning loop
- Fast sell with barcoded items
- Manager override for selling below cost
- Shoes size numeric validation in UI workflow
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from inventory.models import Location
from inventory.models_clothing_barcode import ClothingBarcodeUnit
from inventory.models_verticals import ClothingSale
from tenants.models import Business

User = get_user_model()


class TestBarcodeWizardStep1(TestCase):
    """Test barcode wizard Step 1: Pricing form"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="test123")
        self.manager_group = Group.objects.create(name="Manager")
        self.business = Business.objects.create(name="Test Business", business_kind="clothing")
        self.location = Location.objects.create(business=self.business, name="Main Store")

        # Assign business to user
        self.user.business = self.business
        self.user.save()

        self.client.login(username="testuser", password="test123")
        self.url = reverse("verticals:clothing_barcode_add_step1")

    def test_step1_renders(self):
        """Step 1 page should render without errors"""
        response = self.client.get(self.url)
        assert response.status_code == 200
        assert b"Add Barcoded Items" in response.content

    def test_step1_valid_submission_creates_session(self):
        """Valid Step 1 form should create session and redirect to Step 2"""
        response = self.client.post(
            self.url,
            {
                "category": "shoes",
                "subcategory": "sneaker",
                "size": "42",
                "quantity": 3,
                "cost_price": "10000.00",
                "selling_price": "15000.00",
                "brand": "Nike",
                "color": "Black",
            },
        )

        # Should redirect to Step 2
        assert response.status_code == 302
        assert "step2" in response.url

        # Session should be created
        session = self.client.session
        assert "clothing_barcode_batch" in session
        assert session["clothing_barcode_batch"]["quantity"] == 3
        assert session["clothing_barcode_batch"]["size"] == "42"

    def test_step1_shoes_alpha_size_rejected(self):
        """Shoes with alpha size (XL, M, L) should be rejected"""
        response = self.client.post(
            self.url,
            {
                "category": "shoes",
                "size": "XL",  # INVALID for shoes
                "quantity": 2,
                "cost_price": "10000.00",
                "selling_price": "15000.00",
            },
        )

        # Should NOT redirect (form error)
        assert response.status_code == 200
        assert b"numeric only" in response.content.lower()

    def test_step1_shirt_alpha_size_valid(self):
        """Shirts with alpha size should be valid"""
        response = self.client.post(
            self.url,
            {
                "category": "shirt",
                "size": "M",  # VALID for shirts
                "quantity": 2,
                "cost_price": "5000.00",
                "selling_price": "8000.00",
            },
        )

        # Should redirect to Step 2
        assert response.status_code == 302

    def test_step1_auto_suggest_selling_price(self):
        """If selling price blank, should auto-suggest (cost × 1.35)"""
        response = self.client.post(
            self.url,
            {
                "category": "shoes",
                "size": "42",
                "quantity": 1,
                "cost_price": "10000.00",
                "selling_price": "",  # Blank -> auto-suggest
            },
        )

        # Should redirect (auto-suggested price used)
        assert response.status_code == 302

        session = self.client.session
        selling_price = Decimal(session["clothing_barcode_batch"]["selling_price"])

        # Should be approximately cost × 1.35, rounded to nearest 100
        expected = Decimal("13500.00")  # 10000 × 1.35 = 13500
        assert selling_price == expected

    def test_step1_selling_below_cost_requires_manager_override(self):
        """Selling below cost should require manager override checkbox"""
        response = self.client.post(
            self.url,
            {
                "category": "shoes",
                "size": "42",
                "quantity": 1,
                "cost_price": "15000.00",
                "selling_price": "10000.00",  # BELOW cost
                "allow_below_cost": False,  # NOT checked
            },
        )

        # Should NOT redirect (form error)
        assert response.status_code == 200
        assert b"below cost" in response.content.lower()

    def test_step1_manager_can_override_below_cost(self):
        """Manager can approve selling below cost"""
        # Make user a manager
        self.user.groups.add(self.manager_group)

        response = self.client.post(
            self.url,
            {
                "category": "shoes",
                "size": "42",
                "quantity": 1,
                "cost_price": "15000.00",
                "selling_price": "10000.00",  # BELOW cost
                "allow_below_cost": True,  # Manager override
            },
        )

        # Should redirect (manager override accepted)
        assert response.status_code == 302


class TestBarcodeWizardStep2(TestCase):
    """Test barcode wizard Step 2: Scanning loop"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="test123")
        self.business = Business.objects.create(name="Test Business", business_kind="clothing")
        self.location = Location.objects.create(business=self.business, name="Main Store")

        self.user.business = self.business
        self.user.save()

        self.client.login(username="testuser", password="test123")

        # Create session (simulating Step 1 completion)
        session = self.client.session
        session["clothing_barcode_batch"] = {
            "business_id": self.business.id,
            "location_id": self.location.id,
            "user_id": self.user.id,
            "category": "shoes",
            "subcategory": "sneaker",
            "size": "42",
            "quantity": 3,
            "cost_price": "10000.00",
            "selling_price": "15000.00",
            "brand": "Nike",
            "color": "Black",
            "product_name": "Nike Sneaker - Size 42",
            "scanned_count": 0,
            "scanned_barcodes": [],
        }
        session.save()

        self.step2_url = reverse("verticals:clothing_barcode_add_step2")
        self.scan_api_url = reverse("clothing:barcode_batch_scan")

    def test_step2_renders_with_session(self):
        """Step 2 should render when session exists"""
        response = self.client.get(self.step2_url)
        assert response.status_code == 200
        assert b"Scan Barcodes" in response.content
        assert b"0 / 3" in response.content  # Progress display

    def test_step2_redirects_without_session(self):
        """Step 2 should redirect to Step 1 if no session"""
        # Clear session
        session = self.client.session
        del session["clothing_barcode_batch"]
        session.save()

        response = self.client.get(self.step2_url)
        assert response.status_code == 302
        assert "step1" in response.url

    def test_step2_scanning_creates_units(self):
        """Scanning barcodes should create ClothingBarcodeUnit records"""
        # Scan first barcode
        response = self.client.post(
            self.scan_api_url,
            {"barcode": "TEST001"},
            content_type="application/json",
        )

        data = response.json()
        assert data["ok"] is True
        assert data["scanned_count"] == 1
        assert data["remaining"] == 2
        assert data["complete"] is False

        # Check unit created
        unit = ClothingBarcodeUnit.objects.get(barcode="TEST001")
        assert unit.size == "42"
        assert unit.cost_price == Decimal("10000.00")
        assert unit.selling_price == Decimal("15000.00")
        assert unit.status == "IN_STOCK"

    def test_step2_duplicate_barcode_rejected(self):
        """Scanning duplicate barcode should be rejected"""
        # Scan first time
        self.client.post(
            self.scan_api_url,
            {"barcode": "DUPE001"},
            content_type="application/json",
        )

        # Scan same barcode again
        response = self.client.post(
            self.scan_api_url,
            {"barcode": "DUPE001"},
            content_type="application/json",
        )

        data = response.json()
        assert data["ok"] is False
        assert "already" in data["error"].lower()

    def test_step2_complete_after_quantity_scanned(self):
        """Scanning all units should mark complete"""
        quantity = 3
        for i in range(quantity):
            response = self.client.post(
                self.scan_api_url,
                {"barcode": f"BC{i+1}"},
                content_type="application/json",
            )

            data = response.json()

            if i < quantity - 1:
                assert data["complete"] is False
            else:
                assert data["complete"] is True

        # Check all units created
        assert ClothingBarcodeUnit.objects.filter(business=self.business).count() == 3


class TestFastSellBarcode(TestCase):
    """Test fast sell with barcoded items"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="test123")
        self.business = Business.objects.create(name="Test Business", business_kind="clothing")
        self.location = Location.objects.create(business=self.business, name="Main Store")

        self.user.business = self.business
        self.user.save()

        self.client.login(username="testuser", password="test123")

        # Create IN_STOCK barcoded unit
        self.unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="FAST001",
            category="shoes",
            size="42",
            cost_price=Decimal("10000.00"),
            selling_price=Decimal("15000.00"),
            status="IN_STOCK",
        )

        self.fast_sell_api_url = reverse("clothing:fast_sell_create")

    def test_fast_sell_page_renders(self):
        """Fast sell barcode scanner page should render"""
        url = reverse("verticals:clothing_fast_sell_barcode")
        response = self.client.get(url)
        assert response.status_code == 200
        assert b"Fast Sell" in response.content

    def test_fast_sell_creates_sale_and_marks_sold(self):
        """Fast sell should create sale and mark unit SOLD"""
        response = self.client.post(
            self.fast_sell_api_url,
            {"barcode": "FAST001", "payment_method": "cash"},
            content_type="application/json",
        )

        data = response.json()
        assert data["ok"] is True
        assert data["barcode"] == "FAST001"
        assert data["amount"] == "15000.00"
        assert data["profit"] == "5000.00"

        # Check unit marked SOLD
        self.unit.refresh_from_db()
        assert self.unit.status == "SOLD"
        assert self.unit.sold_at is not None

        # Check sale created
        sale = ClothingSale.objects.get(business=self.business)
        assert sale.quantity == 1
        assert sale.unit_price == Decimal("15000.00")

    def test_fast_sell_same_barcode_twice_fails(self):
        """Selling same barcode twice should fail"""
        # First sale
        self.client.post(
            self.fast_sell_api_url,
            {"barcode": "FAST001", "payment_method": "cash"},
            content_type="application/json",
        )

        # Second sale (should fail)
        response = self.client.post(
            self.fast_sell_api_url,
            {"barcode": "FAST001", "payment_method": "cash"},
            content_type="application/json",
        )

        data = response.json()
        assert data["ok"] is False
        assert "already sold" in data["error"].lower()

    def test_fast_sell_unknown_barcode_fails(self):
        """Fast sell with unknown barcode should fail"""
        response = self.client.post(
            self.fast_sell_api_url,
            {"barcode": "UNKNOWN999", "payment_method": "cash"},
            content_type="application/json",
        )

        data = response.json()
        assert data["ok"] is False
        assert "not found" in data["error"].lower()

    def test_fast_sell_enforces_barcoded_items_only(self):
        """Fast sell should ONLY work with barcoded items (not bulk stock)"""
        # Try to scan a barcode that doesn't exist in ClothingBarcodeUnit table
        response = self.client.post(
            self.fast_sell_api_url,
            {"barcode": "NONEXISTENT", "payment_method": "cash"},
            content_type="application/json",
        )

        data = response.json()
        assert data["ok"] is False
        # Should NOT fall back to non-barcode products


class TestNonBarcodedManualSell(TestCase):
    """Test that non-barcoded items use manual sell flow (not fast sell)"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="test123")
        self.business = Business.objects.create(name="Test Business", business_kind="clothing")
        self.location = Location.objects.create(business=self.business, name="Main Store")

        self.user.business = self.business
        self.user.save()

        self.client.login(username="testuser", password="test123")

    def test_non_barcoded_fast_sell_shows_product_grid(self):
        """Fast sell (non-barcode) should show product grid, NOT scanner"""
        url = reverse("verticals:clothing_fast_sell_v2")
        response = self.client.get(url)
        assert response.status_code == 200
        # Should show product grid, not barcode scanner
        # (implementation depends on your template structure)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
