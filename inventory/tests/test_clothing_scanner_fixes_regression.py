# inventory/tests/test_clothing_scanner_fixes_regression.py
"""
Regression tests for Clothing Scanner Fixes (January 2026)

Tests the specific fixes requested:
1. No floating/blinking buttons on clothing hub
2. Fast sell scanner has enhanced UX
3. Selling price is required with smart margin feedback
4. Barcode scanner is powerful and works reliably

ZERO REGRESSIONS - All existing functionality must continue to work.
"""
import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business, Membership
from circuitcity.accounts.models import Profile
from inventory.models import Location, MerchProduct
from inventory.business_kinds import BusinessKind
from inventory.models_clothing_barcode import ClothingBarcodeUnit


User = get_user_model()


@pytest.mark.django_db
class TestClothingHubNoFloatingButtons(TestCase):
    """
    Regression test: Ensure floating/blinking scan/stock-in buttons are removed from hub.
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

    def test_hub_no_floating_buttons(self):
        """Hub page should not have floating/blinking action buttons."""
        response = self.client.get(reverse('verticals:clothing_hub'))
        
        # Should render successfully
        self.assertEqual(response.status_code, 200)
        
        # Should NOT contain floating button classes/IDs
        # cc-fab is the floating action button class
        content = response.content.decode()
        
        # Should not have position:fixed buttons with animation
        self.assertNotIn('cc-fab', content, 
                        "Hub should not have floating action button (cc-fab)")
        self.assertNotIn('animation: blink', content,
                        "Hub should not have blinking animations")
        self.assertNotIn('animation: pulse', content,
                        "Hub should not have pulse animations")


@pytest.mark.django_db
class TestFastSellScannerEnhanced(TestCase):
    """
    Regression test: Fast sell scanner must be powerful and scanner-first.
    """

    def setUp(self):
        self.business = Business.objects.create(
            name="Test Store",
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

    def test_fast_sell_has_enhanced_scanner_input(self):
        """Fast sell must have large, prominent scanner input with autofocus."""
        response = self.client.get(reverse('verticals:clothing_fast_sell_v2'))
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Must have barcode input
        self.assertIn('id="barcodeInput"', content,
                     "Fast sell must have barcode input")
        
        # Must have autofocus
        self.assertIn('autofocus', content,
                     "Scanner input must have autofocus")
        
        # Must have camera scan button
        self.assertIn('id="cameraScanBtn"', content,
                     "Must have camera scan button")
        
        # Must have scanner icon (📷)
        self.assertIn('📷', content,
                     "Must have scanner camera icon")
        
        # Must have enhanced styling (larger font, bold)
        self.assertIn('font-size: 1.3rem', content,
                     "Scanner input must have large font size")
        self.assertIn('font-weight: 600', content,
                     "Scanner input must be bold/prominent")

    def test_fast_sell_works_with_barcoded_items(self):
        """Fast sell must work when barcoded items exist."""
        # Create product
        product = MerchProduct.objects.create(
            business=self.business,
            name="Test Shirt",
            kind=BusinessKind.CLOTHING,
            selling_price=Decimal("5000.00"),
            cost_price=Decimal("3000.00"),
            is_active=True,
        )
        
        # Create barcoded unit
        ClothingBarcodeUnit.objects.create(
            business=self.business,
            location=self.location,
            product=product,
            barcode="TEST001",
            size="M",
            category="shirt",
            selling_price=Decimal("5000.00"),
            cost_price=Decimal("3000.00"),
            status="IN_STOCK",
            is_active=True,
        )
        
        response = self.client.get(reverse('verticals:clothing_fast_sell_v2'))
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode()
        
        # Should NOT show empty state
        self.assertNotIn('No barcoded items in stock', content,
                        "Should not show empty state when items exist")
        
        # Should show barcoded units count
        self.assertIn('Barcoded units:', content,
                     "Should display barcoded units count")


@pytest.mark.django_db
class TestSmartPricingRequired(TestCase):
    """
    Regression test: Selling price must be required with smart margin feedback.
    """

    def setUp(self):
        self.business = Business.objects.create(
            name="Test Store",
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
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager",
            is_active=True,
        )
        
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.active_business = self.business
        profile.active_location = self.location  # CRITICAL: Set active location
        profile.save()

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    @pytest.mark.skip(reason="Old wizard pricing - new 2-step wizard has different UX")
    def test_wizard_pricing_step_selling_price_required(self):
        """Wizard pricing step must mark selling price as REQUIRED."""
        # The wizard is JS-heavy, so we test the template contains required indicator
        response = self.client.get(reverse('inventory:clothing_wizard'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Must indicate selling price is required
        self.assertIn('*REQUIRED*', content,
                     "Wizard must mark selling price as required")
        
        # Must have smart pricing feedback function
        self.assertIn('updateInlineSmartPricing', content,
                     "Wizard must have smart pricing feedback JS")
        self.assertIn('updateSmartPricingFeedback', content,
                     "Wizard must have smart pricing feedback function")

    @pytest.mark.skip(reason="Old wizard margin labels - new 2-step wizard has different UX")
    def test_smart_pricing_shows_margin_labels(self):
        """Smart pricing must show margin labels (Low/Good/Excellent)."""
        response = self.client.get(reverse('inventory:clothing_wizard'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Must have margin label logic in JS
        self.assertIn('Low Margin', content,
                     "Must have Low Margin label")
        self.assertIn('Good Margin', content,
                     "Must have Good Margin label")
        self.assertIn('Excellent Margin', content,
                     "Must have Excellent Margin label")
        
        # Must calculate profit per unit
        self.assertIn('Profit per unit', content,
                     "Must show profit per unit")


@pytest.mark.django_db
class TestBarcodeStepScannerPowerful(TestCase):
    """
    Regression test: Barcode step must have powerful scanner (same as before).
    """

    def setUp(self):
        self.business = Business.objects.create(
            name="Test Store",
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
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager",
            is_active=True,
        )
        
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.active_business = self.business
        profile.active_location = self.location  # CRITICAL: Set active location
        profile.save()

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    @pytest.mark.skip(reason="Old wizard scanner - new 2-step wizard has different UX")
    def test_wizard_has_powerful_barcode_scanner(self):
        """Wizard barcode step must have powerful scanner with autofocus."""
        response = self.client.get(reverse('inventory:clothing_wizard'), follow=True)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Must have manual barcode input with autofocus
        self.assertIn('id="manual-barcode-input"', content,
                     "Wizard must have manual barcode input")
        self.assertIn('autofocus', content,
                     "Barcode input must have autofocus")
        
        # Must have Scan Barcode button (camera scanner)
        self.assertIn('Scan Barcode', content,
                     "Must have 'Scan Barcode' button")
        self.assertIn('openSmartBarcodeScanner', content,
                     "Must have scanner button handler")
        
        # Must have Enter key support
        self.assertIn('keypress', content,
                     "Must support Enter key for barcode input")


@pytest.mark.django_db
class TestZeroRegressions(TestCase):
    """
    Regression test: Ensure existing functionality still works.
    """

    def setUp(self):
        self.business = Business.objects.create(
            name="Test Store",
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
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager",
            is_active=True,
        )
        
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.active_business = self.business
        profile.active_location = self.location  # CRITICAL: Set active location
        profile.save()

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_clothing_hub_renders(self):
        """Clothing hub must render without errors."""
        response = self.client.get(reverse('verticals:clothing_hub'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Clothing Hub')

    def test_fast_sell_renders(self):
        """Fast sell must render without errors."""
        response = self.client.get(reverse('verticals:clothing_fast_sell_v2'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fast Sell')

    def test_wizard_renders(self):
        """Clothing wizard must render without errors."""
        response = self.client.get(reverse('inventory:clothing_wizard'), follow=True)
        self.assertEqual(response.status_code, 200)
        # Wizard is JS-heavy, just check it renders
        self.assertIn(b'wizard', response.content.lower())

    def test_product_cards_have_quick_actions(self):
        """Hub product cards must still have quick action buttons (not floating)."""
        # Create a product
        MerchProduct.objects.create(
            business=self.business,
            name="Test Product",
            kind=BusinessKind.CLOTHING,
            selling_price=Decimal("5000.00"),
            cost_price=Decimal("3000.00"),
            quantity_in_stock=5,
            is_active=True,
        )
        
        response = self.client.get(reverse('verticals:clothing_hub'))
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode()
        
        # Quick actions within cards are OK
        self.assertIn('Quick Actions', content,
                     "Product cards should have Quick Actions section")
        self.assertIn('Stock-In', content,
                     "Should have Stock-In button in card")

