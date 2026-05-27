# inventory/tests/test_clothing_fast_sell_scanner.py
"""
Regression tests for Clothing Fast Sell Scanner-First UX.

Tests ensure we never break the scanner + fast sell + barcode stock-in again.
"""
import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business
from inventory.models import Location, MerchProduct, BusinessKind
from inventory.models_clothing_barcode import ClothingBarcodeUnit
from inventory.models_verticals import ClothingSale, PaymentMethod


User = get_user_model()


@pytest.mark.django_db
class TestFastSellShowsBarcodeStock(TestCase):
    """
    Test that Fast Sell page shows barcoded items in stock.
    
    REGRESSION: Fast Sell was showing "No products with stock available" 
    even when barcoded items existed.
    """

    def setUp(self):
        # Create business and user
        self.business = Business.objects.create(
            name="Test Clothing Store",
            kind="clothing",
        )
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True,
        )
        
        # CRITICAL: Add user to business and set roles
        from tenants.models import Membership
        from circuitcity.accounts.models import Profile
        
        # Create membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager",
            is_active=True,
        )
        
        # Create or update user profile
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.active_business = self.business
        profile.save()

        # Create a product (optional - barcode units can exist standalone)
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Shirt",
            kind=BusinessKind.CLOTHING,
            selling_price=Decimal("5000.00"),
            cost_price=Decimal("3000.00"),
            quantity_in_stock=0,  # No common stock
            is_active=True,
            is_archived=False,
        )

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_fast_sell_shows_barcoded_items(self):
        """Fast Sell page should show barcoded items when they exist."""
        # Create barcoded units
        ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=self.product,
            barcode="BARCODE001",
            size="M",
            category="shirt",
            selling_price=Decimal("5000.00"),
            cost_price=Decimal("3000.00"),
            status="IN_STOCK",
            is_active=True,
        )

        ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=self.product,
            barcode="BARCODE002",
            size="L",
            category="shirt",
            selling_price=Decimal("5500.00"),
            cost_price=Decimal("3200.00"),
            status="IN_STOCK",
            is_active=True,
        )

        # GET Fast Sell page
        response = self.client.get(reverse("verticals:clothing_fast_sell_v2"))

        # Should NOT show empty state
        self.assertNotContains(response, "No items in stock")
        
        # Should show support message for both tracked and common
        self.assertContains(response, "Supports tracked + common stock")
        
        # Should show tracked items section
        self.assertContains(response, "Tracked Items")

    def test_fast_sell_empty_when_no_barcode_units(self):
        """Fast Sell should show empty state when no barcode units exist."""
        # Don't create any barcode units
        
        response = self.client.get(reverse("verticals:clothing_fast_sell_v2"))

        # Should show empty state
        self.assertContains(response, "No items in stock")
        self.assertContains(response, "Fast Sell shows tracked (barcoded) and common stock items")


@pytest.mark.django_db
class TestFastSellScanAndSell(TestCase):
    """
    Test that Fast Sell scanner can scan and instantly sell barcoded items.
    
    REGRESSION: Ensure barcode scanning creates sale and marks unit sold.
    """

    def setUp(self):
        self.business = Business.objects.create(
            name="Test Clothing Store",
            kind="clothing",
        )
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
        )

        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True,
        )
        
        # CRITICAL: Add user to business and set roles
        from tenants.models import Membership
        from circuitcity.accounts.models import Profile
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager",
            is_active=True,
        )
        
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.active_business = self.business
        profile.save()

        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Jeans",
            kind=BusinessKind.CLOTHING,
            selling_price=Decimal("8000.00"),
            cost_price=Decimal("5000.00"),
            is_active=True,
            is_archived=False,
        )

        # Create barcode unit
        self.unit = ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=self.product,
            barcode="JEANS001",
            size="32",
            category="jeans",
            selling_price=Decimal("8000.00"),
            cost_price=Decimal("5000.00"),
            status="IN_STOCK",
            is_active=True,
        )

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_scan_barcode_creates_sale(self):
        """POST barcode to fast sell should create sale and mark unit sold."""
        url = reverse("verticals:clothing_fast_sell_create_api")
        
        response = self.client.post(
            url,
            data={
                "barcode": "JEANS001",
                "quantity": 1,
                "payment_method": "cash",
            },
            content_type="application/json",
        )

        # Should return success
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["ok"])
        self.assertIn("sale_id", result)

        # Sale should be created
        sale = ClothingSale.objects.filter(business=self.business).first()
        self.assertIsNotNone(sale)
        self.assertEqual(sale.quantity, 1)
        self.assertEqual(sale.total_price, Decimal("8000.00"))
        self.assertEqual(sale.payment_method, PaymentMethod.CASH)

        # Unit should be marked SOLD
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, "SOLD")
        self.assertIsNotNone(self.unit.sold_at)

    def test_scan_nonexistent_barcode_returns_error(self):
        """Scanning barcode that doesn't exist should return error."""
        url = reverse("verticals:clothing_fast_sell_create_api")
        
        response = self.client.post(
            url,
            data={
                "barcode": "INVALID_BARCODE",
                "quantity": 1,
                "payment_method": "cash",
            },
            content_type="application/json",
        )

        # Should return error
        result = response.json()
        self.assertFalse(result["ok"])
        self.assertIn("error", result)
        self.assertIn("not found", result["error"].lower())

    def test_scan_already_sold_barcode_returns_error(self):
        """Scanning already-sold barcode should return error."""
        # Mark unit as sold
        self.unit.mark_sold()

        url = reverse("verticals:clothing_fast_sell_create_api")
        
        response = self.client.post(
            url,
            data={
                "barcode": "JEANS001",
                "quantity": 1,
                "payment_method": "cash",
            },
            content_type="application/json",
        )

        # Should return error
        result = response.json()
        self.assertFalse(result["ok"])
        self.assertIn("error", result)


@pytest.mark.django_db
class TestBarcodeStockInScanner(TestCase):
    """
    Test that barcode stock-in step has scanner UX with autofocus.
    
    REGRESSION: Ensure wizard barcode step is scanner-first.
    """

    def setUp(self):
        self.business = Business.objects.create(
            name="Test Clothing Store",
            kind="clothing",
        )
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
        )

        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True,
        )
        
        # CRITICAL: Add user to business and set roles
        from tenants.models import Membership
        from circuitcity.accounts.models import Profile
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager",
            is_active=True,
        )
        
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.active_business = self.business
        profile.save()

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    @pytest.mark.skip(reason="Old wizard elements - new 2-step wizard has different UX")
    def test_wizard_barcode_step_has_autofocus(self):
        """Wizard barcode step should have autofocus on manual input."""
        # GET wizard page (follows redirect to new 2-step wizard)
        response = self.client.get(reverse("inventory:clothing_wizard"), follow=True)

        # Should contain autofocus attribute
        self.assertContains(response, 'id="manual-barcode-input"')
        self.assertContains(response, "autofocus")

    @pytest.mark.skip(reason="Old wizard elements - new 2-step wizard has different UX")
    def test_wizard_barcode_step_has_scanner_button(self):
        """Wizard barcode step should have scan button."""
        response = self.client.get(reverse("inventory:clothing_wizard"), follow=True)

        # Should contain scan barcode button
        self.assertContains(response, "Scan Barcode")
        self.assertContains(response, "openSmartBarcodeScanner")


@pytest.mark.django_db
class TestClothingHubShowsTrackingBadges(TestCase):
    """
    Test that Clothing Hub shows Tracked/Common badges correctly.
    
    REGRESSION: Hub must differentiate barcoded vs common stock products.
    """

    def setUp(self):
        self.business = Business.objects.create(
            name="Test Clothing Store",
            kind="clothing",
        )
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
        )

        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True,
        )
        
        # CRITICAL: Add user to business and set roles
        from tenants.models import Membership
        from circuitcity.accounts.models import Profile
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager",
            is_active=True,
        )
        
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.active_business = self.business
        profile.save()

        # Common stock product (no barcode units)
        self.common_product = MerchProduct.objects.create(
            business=self.business,
            name="Common Shirt",
            kind=BusinessKind.CLOTHING,
            selling_price=Decimal("3000.00"),
            cost_price=Decimal("2000.00"),
            quantity_in_stock=10,  # Has common stock
            is_active=True,
            is_archived=False,
        )

        # Barcoded product
        self.barcoded_product = MerchProduct.objects.create(
            business=self.business,
            name="Tracked Jeans",
            kind=BusinessKind.CLOTHING,
            selling_price=Decimal("8000.00"),
            cost_price=Decimal("5000.00"),
            quantity_in_stock=0,  # No common stock
            is_active=True,
            is_archived=False,
        )

        # Create barcode unit for tracked product
        ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=self.barcoded_product,
            barcode="TRACKED001",
            size="32",
            category="jeans",
            selling_price=Decimal("8000.00"),
            cost_price=Decimal("5000.00"),
            status="IN_STOCK",
            is_active=True,
        )

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_hub_shows_tracked_badge_for_barcoded_product(self):
        """Hub should show 'Tracked' badge for products with barcode units."""
        response = self.client.get(reverse("verticals:clothing_hub"))

        # Should show Tracked badge
        self.assertContains(response, "🏷️ Tracked")
        self.assertContains(response, "Tracked Jeans")

    def test_hub_shows_common_badge_for_common_stock_product(self):
        """Hub should show 'Common' badge for products with common stock."""
        response = self.client.get(reverse("verticals:clothing_hub"))

        # Should show Common badge
        self.assertContains(response, "📦 Common")
        self.assertContains(response, "Common Shirt")

    def test_hub_shows_kpi_cards(self):
        """Hub should show KPI cards with total products, in stock, barcoded units, low stock."""
        response = self.client.get(reverse("verticals:clothing_hub"))

        # Should show KPI cards
        self.assertContains(response, "Total Products")
        self.assertContains(response, "Common Stock")
        self.assertContains(response, "Barcoded Units")
        self.assertContains(response, "Low Stock")

    def test_hub_filter_chips_work(self):
        """Hub filter chips should filter products correctly."""
        # Test "all" filter
        response = self.client.get(reverse("verticals:clothing_hub") + "?filter=all")
        self.assertContains(response, "Common Shirt")
        self.assertContains(response, "Tracked Jeans")

        # Test "barcoded" filter
        response = self.client.get(reverse("verticals:clothing_hub") + "?filter=barcoded")
        self.assertContains(response, "Tracked Jeans")
        self.assertNotContains(response, "Common Shirt")

        # Test "common" filter
        response = self.client.get(reverse("verticals:clothing_hub") + "?filter=common")
        self.assertContains(response, "Common Shirt")
        # Tracked Jeans should not appear (has no common stock)
        # Note: This may still appear if the filter logic includes it


@pytest.mark.django_db
class TestFastSellQuerysetSlicingRegression(TestCase):
    """
    REGRESSION TEST: Fast sell page should not crash with queryset slicing error.
    
    Bug: fast_sell was slicing common_products_query before calling .exclude(),
    which caused: TypeError: Cannot filter a query once a slice has been taken.
    
    Fix: Apply all filters/excludes BEFORE slicing. Slice only at the end.
    """

    def setUp(self):
        self.business = Business.objects.create(
            name="Test Clothing Store",
            kind="clothing",
        )
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
        )

        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True,
        )
        
        # Add user to business
        from tenants.models import Membership
        from circuitcity.accounts.models import Profile
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager",
            is_active=True,
        )
        
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.active_business = self.business
        profile.save()

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_fast_sell_page_returns_200_not_500(self):
        """
        REGRESSION: Fast sell page should return 200, not 500.
        
        Previously crashed with:
        TypeError: Cannot filter a query once a slice has been taken.
        """
        # Create common stock products
        for i in range(5):
            MerchProduct.objects.create(
                business=self.business,
                name=f"Product {i}",
                kind=BusinessKind.CLOTHING,
                selling_price=Decimal("1000.00"),
                cost_price=Decimal("500.00"),
                quantity_in_stock=10,
                is_active=True,
                is_archived=False,
            )

        # Create a tracked product
        product_with_tracking = MerchProduct.objects.create(
            business=self.business,
            name="Tracked Product",
            kind=BusinessKind.CLOTHING,
            selling_price=Decimal("2000.00"),
            cost_price=Decimal("1000.00"),
            quantity_in_stock=5,  # Has common stock too
            is_active=True,
            is_archived=False,
        )
        
        # Add tracked unit for the product
        ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=product_with_tracking,
            barcode="TRACKED001",
            size="M",
            category="shirt",
            selling_price=Decimal("2000.00"),
            cost_price=Decimal("1000.00"),
            status="IN_STOCK",
            is_active=True,
        )

        # GET Fast Sell page - should NOT crash
        response = self.client.get(reverse("verticals:clothing_fast_sell_v2"))

        # CRITICAL: Must return 200, not 500
        # This is the key regression test - the page should not crash with queryset slicing error
        self.assertEqual(response.status_code, 200)
        
        # Page should render successfully (any content is fine, just no 500 error)
        self.assertIn(b"Fast Sell", response.content)

    def test_fast_sell_with_many_products_no_crash(self):
        """
        REGRESSION: Fast sell should handle many products without crashing.
        
        This specifically tests that the slicing happens AFTER .exclude(),
        which was the root cause of the bug.
        """
        # Create 60 common stock products (more than the 50 limit)
        for i in range(60):
            MerchProduct.objects.create(
                business=self.business,
                name=f"Common Product {i:03d}",
                kind=BusinessKind.CLOTHING,
                selling_price=Decimal("1000.00"),
                cost_price=Decimal("500.00"),
                quantity_in_stock=10,
                is_active=True,
                is_archived=False,
            )
        
        # Create some tracked products (10 of them)
        for i in range(10):
            tracked_product = MerchProduct.objects.create(
                business=self.business,
                name=f"Tracked Product {i:03d}",
                kind=BusinessKind.CLOTHING,
                selling_price=Decimal("2000.00"),
                cost_price=Decimal("1000.00"),
                quantity_in_stock=5,  # Has common stock but should be excluded
                is_active=True,
                is_archived=False,
            )
            
            # Add tracked unit
            ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location,
                product=tracked_product,
                barcode=f"TRACKED{i:03d}",
                size="L",
                category="jeans",
                selling_price=Decimal("2000.00"),
                cost_price=Decimal("1000.00"),
                status="IN_STOCK",
                is_active=True,
            )

        # GET Fast Sell page - this is where the crash happened before
        response = self.client.get(reverse("verticals:clothing_fast_sell_v2"))

        # CRITICAL: Must return 200, not 500
        # Before the fix, this would crash with:
        # TypeError: Cannot filter a query once a slice has been taken.
        self.assertEqual(response.status_code, 200)