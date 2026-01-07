# inventory/tests/test_clothing_barcode_service.py
"""
Tests for clothing barcode service layer.

Tests:
- Step 1: Validate prices/qty/size before scanning
- Step 2: Scan loop creates unique units
- Duplicate barcode detection
- Fast sell lookup and sale creation
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from inventory.models import Location
from inventory.models_clothing_barcode import ClothingBarcodeUnit
from inventory.services.clothing_barcode_service import (
    check_barcode_duplicate,
    create_barcode_batch_session,
    create_fast_sell_from_barcode,
    lookup_barcode_for_fast_sell,
    scan_barcode_unit,
)
from tenants.models import Business

User = get_user_model()


class TestBarcodeBatchSessionCreation(TestCase):
    """Test Step 1: Validate and store batch details"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test123")
        self.business = Business.objects.create(name="Test Business", kind="clothing")
        self.location = Location.objects.create(business=self.business, name="Main Store")

    def test_valid_batch_session_created(self):
        """Valid batch details should create session data"""
        session_data = create_barcode_batch_session(
            business=self.business,
            location=self.location,
            user=self.user,
            category="shoes",
            subcategory="sneaker",
            size="42",
            quantity=5,
            cost_price=Decimal("10000.00"),
            selling_price=Decimal("15000.00"),
            brand="Nike",
            color="Black",
        )

        assert session_data is not None
        assert session_data["quantity"] == 5
        assert session_data["size"] == "42"
        assert session_data["cost_price"] == "10000.00"
        assert session_data["selling_price"] == "15000.00"
        assert session_data["scanned_count"] == 0
        assert session_data["scanned_barcodes"] == []

    def test_zero_quantity_invalid(self):
        """Quantity must be >= 1"""
        with pytest.raises(ValidationError) as exc_info:
            create_barcode_batch_session(
                business=self.business,
                location=self.location,
                user=self.user,
                category="shoes",
                size="42",
                quantity=0,
                cost_price=Decimal("10000.00"),
                selling_price=Decimal("15000.00"),
            )
        assert "at least 1" in str(exc_info.value).lower()

    def test_negative_cost_price_invalid(self):
        """Cost price cannot be negative"""
        with pytest.raises(ValidationError):
            create_barcode_batch_session(
                business=self.business,
                location=self.location,
                user=self.user,
                category="shoes",
                size="42",
                quantity=5,
                cost_price=Decimal("-100.00"),
                selling_price=Decimal("15000.00"),
            )

    def test_zero_selling_price_invalid(self):
        """Selling price must be > 0"""
        with pytest.raises(ValidationError) as exc_info:
            create_barcode_batch_session(
                business=self.business,
                location=self.location,
                user=self.user,
                category="shoes",
                size="42",
                quantity=5,
                cost_price=Decimal("10000.00"),
                selling_price=Decimal("0.00"),
            )
        assert "greater than zero" in str(exc_info.value).lower()

    def test_shoes_alpha_size_invalid(self):
        """Shoes with alpha size should be rejected"""
        with pytest.raises(ValidationError) as exc_info:
            create_barcode_batch_session(
                business=self.business,
                location=self.location,
                user=self.user,
                category="shoes",
                subcategory="sneaker",
                size="XL",  # INVALID for shoes
                quantity=5,
                cost_price=Decimal("10000.00"),
                selling_price=Decimal("15000.00"),
            )
        assert "numeric only" in str(exc_info.value).lower()

    def test_shirt_alpha_size_valid(self):
        """Shirts with alpha size should be valid"""
        session_data = create_barcode_batch_session(
            business=self.business,
            location=self.location,
            user=self.user,
            category="shirt",
            size="M",  # VALID for shirts
            quantity=3,
            cost_price=Decimal("5000.00"),
            selling_price=Decimal("8000.00"),
        )

        assert session_data["size"] == "M"


class TestBarcodeScanLoop(TestCase):
    """Test Step 2: Scan loop creates unique units"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test123")
        self.business = Business.objects.create(name="Test Business", kind="clothing")
        self.location = Location.objects.create(business=self.business, name="Main Store")

        # Create session data
        self.session_data = create_barcode_batch_session(
            business=self.business,
            location=self.location,
            user=self.user,
            category="shoes",
            size="42",
            quantity=3,
            cost_price=Decimal("10000.00"),
            selling_price=Decimal("15000.00"),
        )

    def test_scan_creates_unit(self):
        """Scanning a barcode should create ClothingBarcodeUnit"""
        result = scan_barcode_unit(
            session_data=self.session_data,
            barcode="TEST123",
            business=self.business,
            location=self.location,
            user=self.user,
        )

        assert result["ok"] is True
        assert result["barcode"] == "TEST123"
        assert result["scanned_count"] == 1
        assert result["remaining"] == 2
        assert result["complete"] is False

        # Check database
        unit = ClothingBarcodeUnit.objects.get(barcode="TEST123")
        assert unit.size == "42"
        assert unit.cost_price == Decimal("10000.00")
        assert unit.selling_price == Decimal("15000.00")
        assert unit.status == "IN_STOCK"

    def test_scan_multiple_completes_batch(self):
        """Scanning quantity times should mark complete"""
        # Scan 3 times (quantity=3)
        barcodes = ["BC1", "BC2", "BC3"]
        for i, barcode in enumerate(barcodes):
            result = scan_barcode_unit(
                session_data=self.session_data,
                barcode=barcode,
                business=self.business,
                location=self.location,
                user=self.user,
            )

            # Update session
            self.session_data["scanned_barcodes"] = result["scanned_barcodes"]
            self.session_data["scanned_count"] = result["scanned_count"]

            if i < 2:
                assert result["complete"] is False
            else:
                assert result["complete"] is True

        # Check all units created
        assert ClothingBarcodeUnit.objects.filter(business=self.business).count() == 3

    def test_duplicate_barcode_in_batch_rejected(self):
        """Scanning same barcode twice in batch should be rejected"""
        # Scan first time
        result1 = scan_barcode_unit(
            session_data=self.session_data,
            barcode="DUPE123",
            business=self.business,
            location=self.location,
            user=self.user,
        )
        assert result1["ok"] is True

        # Update session
        self.session_data["scanned_barcodes"] = result1["scanned_barcodes"]

        # Scan same barcode again
        result2 = scan_barcode_unit(
            session_data=self.session_data,
            barcode="DUPE123",
            business=self.business,
            location=self.location,
            user=self.user,
        )
        assert result2["ok"] is False
        assert "already scanned" in result2["error"].lower()

    def test_duplicate_barcode_in_database_rejected(self):
        """Scanning barcode that exists in database should be rejected"""
        # Create existing unit
        ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="EXISTING123",
            size="40",
            cost_price=Decimal("5000.00"),
            selling_price=Decimal("8000.00"),
            status="IN_STOCK",
        )

        # Try to scan same barcode
        result = scan_barcode_unit(
            session_data=self.session_data,
            barcode="EXISTING123",
            business=self.business,
            location=self.location,
            user=self.user,
        )
        assert result["ok"] is False
        assert "already exists" in result["error"].lower()

    def test_barcode_too_short_rejected(self):
        """Barcode < 3 chars should be rejected"""
        result = scan_barcode_unit(
            session_data=self.session_data,
            barcode="AB",  # Only 2 chars
            business=self.business,
            location=self.location,
            user=self.user,
        )
        assert result["ok"] is False
        assert "at least 3" in result["error"].lower()


class TestFastSellLookup(TestCase):
    """Test fast sell barcode lookup"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test123")
        self.business = Business.objects.create(name="Test Business", kind="clothing")
        self.location = Location.objects.create(business=self.business, name="Main Store")

        # Create IN_STOCK unit
        self.unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="FAST123",
            category="shoes",
            size="42",
            cost_price=Decimal("10000.00"),
            selling_price=Decimal("15000.00"),
            status="IN_STOCK",
        )

    def test_lookup_finds_in_stock_unit(self):
        """Lookup should find IN_STOCK unit"""
        result = lookup_barcode_for_fast_sell(
            business=self.business,
            barcode="FAST123",
        )

        assert result["found"] is True
        assert result["unit"].id == self.unit.id
        assert result["barcode"] == "FAST123"
        assert result["size"] == "42"
        assert result["selling_price"] == Decimal("15000.00")

    def test_lookup_not_found_error(self):
        """Lookup for non-existent barcode should return error"""
        result = lookup_barcode_for_fast_sell(
            business=self.business,
            barcode="NOTFOUND",
        )

        assert result["found"] is False
        assert "not found" in result["error"].lower()

    def test_lookup_already_sold_error(self):
        """Lookup for SOLD unit should return error"""
        # Mark unit as sold
        self.unit.mark_sold()

        result = lookup_barcode_for_fast_sell(
            business=self.business,
            barcode="FAST123",
        )

        assert result["found"] is False
        assert "already sold" in result["error"].lower()


class TestFastSellCreate(TestCase):
    """Test fast sell sale creation"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test123")
        self.business = Business.objects.create(name="Test Business", kind="clothing")
        self.location = Location.objects.create(business=self.business, name="Main Store")

        # Create IN_STOCK unit
        self.unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="SELL123",
            category="shoes",
            size="42",
            cost_price=Decimal("10000.00"),
            selling_price=Decimal("15000.00"),
            status="IN_STOCK",
        )

    def test_fast_sell_creates_sale_and_marks_sold(self):
        """Fast sell should create sale and mark unit SOLD"""
        result = create_fast_sell_from_barcode(
            business=self.business,
            location=self.location,
            user=self.user,
            barcode="SELL123",
            payment_method="cash",
        )

        assert result["ok"] is True
        assert result["barcode"] == "SELL123"
        assert result["amount"] == Decimal("15000.00")
        assert result["cost"] == Decimal("10000.00")
        assert result["profit"] == Decimal("5000.00")
        assert "sale_id" in result

        # Check unit marked SOLD
        self.unit.refresh_from_db()
        assert self.unit.status == "SOLD"
        assert self.unit.sold_at is not None

    def test_fast_sell_same_barcode_twice_fails(self):
        """Selling same barcode twice should fail"""
        # First sale
        result1 = create_fast_sell_from_barcode(
            business=self.business,
            location=self.location,
            user=self.user,
            barcode="SELL123",
            payment_method="cash",
        )
        assert result1["ok"] is True

        # Second sale (should fail)
        result2 = create_fast_sell_from_barcode(
            business=self.business,
            location=self.location,
            user=self.user,
            barcode="SELL123",
            payment_method="cash",
        )
        assert result2["ok"] is False
        assert "already sold" in result2["error"].lower()

    def test_fast_sell_unknown_barcode_fails(self):
        """Fast sell with unknown barcode should fail"""
        result = create_fast_sell_from_barcode(
            business=self.business,
            location=self.location,
            user=self.user,
            barcode="UNKNOWN999",
            payment_method="cash",
        )
        assert result["ok"] is False
        assert "not found" in result["error"].lower()


class TestBarcodeDuplicateCheck(TestCase):
    """Test barcode duplicate checking"""

    def setUp(self):
        self.business = Business.objects.create(name="Test Business", kind="clothing")
        self.location = Location.objects.create(business=self.business, name="Main Store")

    def test_check_duplicate_not_exists(self):
        """Check should return exists=False for new barcode"""
        result = check_barcode_duplicate(
            business=self.business,
            barcode="NEW123",
        )
        assert result["exists"] is False
        assert result["unit"] is None

    def test_check_duplicate_exists(self):
        """Check should return exists=True for existing barcode"""
        # Create unit
        unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            barcode="DUPE123",
            size="42",
            cost_price=Decimal("10000.00"),
            selling_price=Decimal("15000.00"),
        )

        result = check_barcode_duplicate(
            business=self.business,
            barcode="DUPE123",
        )
        assert result["exists"] is True
        assert result["unit"].id == unit.id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
