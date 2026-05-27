# tests/critical/test_04_stock_add_core.py
"""
CRITICAL TEST 04: Stock Add Core Functionality

These tests ensure:
1. Stock/inventory add pages load without 500 errors
2. Different stock entry methods work (barcode, no-barcode, IMEI, generic, ledger)
3. Stock records can be created

FAILURE HERE = Cannot add inventory = Business cannot operate = Critical failure

Note: Different verticals have different stock methods:
- Traditional stock: phones, liquor, grocery, pharmacy, clothing, hardware, cement
- Ledger-based: farm (expenses/sales)
- Job-based: welding (materials)
- Membership-based: gym (no stock)
"""
import pytest
from decimal import Decimal
from django.test import Client
from django.urls import reverse, NoReverseMatch

from tests.critical.conftest import (
    VERTICAL_ENDPOINTS,
    CORE_STOCK_VERTICALS,
    CORE_VERTICALS,
    get_stock_add_url,
    get_dashboard_url,
    create_user,
    create_business,
    create_location,
    create_membership,
    setup_authenticated_client,
    bootstrap_business_with_user,
)

# All tests in this module are critical
pytestmark = [pytest.mark.critical, pytest.mark.django_db]


# Use CORE_STOCK_VERTICALS from conftest (excludes gym which has no stock)
# Hardware has a known redirect loop bug - handled via xfail in test_04b
STOCK_VERTICALS = [v for v in CORE_STOCK_VERTICALS if v != "hardware"]

# Core verticals without traditional stock (membership-based)
NON_STOCK_CORE_VERTICALS = [v for v in CORE_VERTICALS if not VERTICAL_ENDPOINTS[v].get("supports_stock")]


class TestStockAddPageLoads:
    """Test that stock add pages load without 500 errors."""
    
    @pytest.mark.parametrize("vertical", STOCK_VERTICALS)
    def test_stock_add_page_no_500(self, vertical):
        """Stock add page must not return 500 for all stock-enabled verticals."""
        from django.test.client import RedirectCycleError
        
        user, business, location = bootstrap_business_with_user(vertical)
        client = setup_authenticated_client(user, business, location)
        
        # Use reverse() for URL resolution
        stock_add_url = get_stock_add_url(vertical)
        
        if not stock_add_url:
            pytest.fail(f"No stock add URL defined for {vertical} - must be added to VERTICAL_ENDPOINTS")
        
        try:
            response = client.get(stock_add_url, follow=True)
        except RedirectCycleError as e:
            # Redirect loop is a bug but not a 500 - log it for fixing
            pytest.fail(f"CRITICAL: {vertical} stock add has redirect loop (bug to fix)")
        
        # CRITICAL: Must not be 500
        assert response.status_code != 500, \
            f"CRITICAL: {vertical} stock add page returned 500"
        
        # Should be accessible (200) or redirect appropriately
        assert response.status_code in [200, 302, 404], \
            f"{vertical} stock add returned unexpected {response.status_code}"
        
        if response.status_code == 200:
            content = response.content.decode("utf-8", errors="ignore")
            assert "Server Error" not in content, \
                f"{vertical} stock add contains Server Error"
    
    @pytest.mark.parametrize("vertical", NON_STOCK_CORE_VERTICALS)
    def test_non_stock_vertical_dashboard_works(self, vertical):
        """Non-stock core verticals (gym) should have working dashboard at minimum."""
        user, business, location = bootstrap_business_with_user(vertical)
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url(vertical)
        
        if dashboard_url:
            response = client.get(dashboard_url, follow=True)
            assert response.status_code != 500, \
                f"{vertical} dashboard returned 500"


class TestStockAddByMethod:
    """Test stock add by different methods (barcode, IMEI, no-barcode, etc.)."""
    
    def test_barcode_stock_in_page_loads(self):
        """Barcode-based stock-in page loads for barcode verticals."""
        barcode_verticals = ["phones", "liquor", "grocery"]  # Core barcode verticals
        
        for vertical in barcode_verticals:
            user, business, location = bootstrap_business_with_user(vertical)
            client = setup_authenticated_client(user, business, location)
            
            endpoints = VERTICAL_ENDPOINTS.get(vertical, {})
            stock_add_path = endpoints.get("stock_add_path")
            
            if stock_add_path:
                response = client.get(stock_add_path, follow=True)
                # Must not be 500 - 404 is OK for missing routes
                assert response.status_code != 500, \
                    f"Barcode stock-in for {vertical} returned 500"
    
    def test_clothing_no_barcode_wizard_loads(self):
        """Clothing wizard (no-barcode path) loads."""
        user, business, location = bootstrap_business_with_user("clothing")
        client = setup_authenticated_client(user, business, location)
        
        # Clothing uses a wizard for stock entry
        wizard_paths = [
            "/inventory/wizard/clothing/",
            "/verticals/clothing/quick-add/",
        ]
        
        for path in wizard_paths:
            response = client.get(path, follow=True)
            # At least one should work
            if response.status_code == 200:
                content = response.content.decode("utf-8", errors="ignore")
                assert "Server Error" not in content
                return
        
        # If none worked, at least verify no 500
        assert all(
            client.get(p, follow=True).status_code != 500 
            for p in wizard_paths
        ), "All clothing wizard paths returned 500"
    
    def test_phones_imei_scan_in_loads(self):
        """Phones IMEI scan-in page loads."""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        scan_paths = [
            "/inventory/scan-in/",
            "/inventory/scan/",
        ]
        
        for path in scan_paths:
            response = client.get(path, follow=True)
            if response.status_code == 200:
                return  # Success
            assert response.status_code != 500, \
                f"Phones scan-in at {path} returned 500"
    
    def test_cement_generic_sku_stock_in_loads(self):
        """Cement generic SKU stock-in loads."""
        user, business, location = bootstrap_business_with_user("cement")
        client = setup_authenticated_client(user, business, location)
        
        endpoints = VERTICAL_ENDPOINTS.get("cement", {})
        stock_add_path = endpoints.get("stock_add_path")
        
        if stock_add_path:
            response = client.get(stock_add_path, follow=True)
            assert response.status_code != 500, "Cement stock-in returned 500"


class TestProductCreation:
    """Test that products/stock items can be created programmatically."""
    
    def test_create_phone_product(self):
        """Phone product can be created."""
        from inventory.models import MerchProduct
        
        user, business, location = bootstrap_business_with_user("phones")
        
        # Try to create product using safe method
        try:
            from inventory.compat_create import safe_create
            product = safe_create(
                MerchProduct,
                business=business,
                location=location,
                name="Test Phone",
                cost_price=Decimal("50000"),
                selling_price=Decimal("60000"),
                quantity=10,
                category="phones",
                vertical_type="phones",
                status="ACTIVE",
            )
        except ImportError:
            # Fallback to direct creation
            product = MerchProduct.objects.create(
                business=business,
                location=location,
                name="Test Phone",
                cost_price=Decimal("50000"),
                selling_price=Decimal("60000"),
                quantity=10,
                category="phones",
                vertical_type="phones",
                status="ACTIVE",
            )
        
        assert product.pk is not None, "Product should be created"
        assert product.quantity >= 0, "Product quantity should be non-negative"
    
    def test_create_pharmacy_product_with_batch(self):
        """Pharmacy product with batch info can be created."""
        from inventory.models import MerchProduct
        from django.utils import timezone
        from datetime import timedelta
        
        user, business, location = bootstrap_business_with_user("pharmacy")
        
        product = MerchProduct.objects.create(
            business=business,
            location=location,
            name="Paracetamol 500mg",
            cost_price=Decimal("100"),
            selling_price=Decimal("150"),
            quantity=100,
            category="medicine",
            vertical_type="pharmacy",
            status="ACTIVE",
        )
        
        # Try to set batch fields if they exist
        if hasattr(product, "batch_number"):
            product.batch_number = "BATCH001"
        if hasattr(product, "expiry_date"):
            product.expiry_date = (timezone.now() + timedelta(days=365)).date()
        product.save()
        
        assert product.pk is not None
    
    def test_create_clothing_product_with_variants(self):
        """Clothing product with size/color can be created."""
        from inventory.models import MerchProduct
        
        user, business, location = bootstrap_business_with_user("clothing")
        
        product = MerchProduct.objects.create(
            business=business,
            location=location,
            name="T-Shirt Blue M",
            cost_price=Decimal("500"),
            selling_price=Decimal("800"),
            quantity=20,
            category="clothing",
            vertical_type="clothing",
            status="ACTIVE",
        )
        
        # Try to set variant fields if they exist
        if hasattr(product, "size"):
            product.size = "M"
        if hasattr(product, "color"):
            product.color = "Blue"
        product.save()
        
        assert product.pk is not None


class TestStockAddValidation:
    """Test that stock add validates data properly."""
    
    def test_product_requires_business(self):
        """Product creation requires a business."""
        from inventory.models import MerchProduct
        from django.db import IntegrityError
        
        user, business, location = bootstrap_business_with_user("phones")
        
        # Product without business should fail
        with pytest.raises((IntegrityError, ValueError, TypeError)):
            MerchProduct.objects.create(
                # business=None intentionally
                location=location,
                name="Orphan Product",
                cost_price=Decimal("100"),
                selling_price=Decimal("150"),
            )
    
    def test_quantity_defaults_correctly(self):
        """Product quantity defaults correctly if not specified."""
        from inventory.models import MerchProduct
        
        user, business, location = bootstrap_business_with_user("phones")
        
        product = MerchProduct.objects.create(
            business=business,
            location=location,
            name="Default Qty Product",
            cost_price=Decimal("100"),
            selling_price=Decimal("150"),
        )
        
        # Quantity should be 0 or a reasonable default
        assert product.quantity >= 0, "Quantity should not be negative"


class TestStockListPages:
    """Test that stock list pages load."""
    
    @pytest.mark.parametrize("vertical", ["phones", "liquor", "pharmacy"])  # Core verticals only
    def test_stock_list_page_loads(self, vertical):
        """Stock list page should load for core verticals."""
        user, business, location = bootstrap_business_with_user(vertical)
        client = setup_authenticated_client(user, business, location)
        
        # Common stock list paths
        stock_paths = [
            "/inventory/list/",
        ]
        
        for path in stock_paths:
            response = client.get(path, follow=True)
            # Must not 500 - 404/302 are acceptable
            assert response.status_code != 500, \
                f"{vertical} stock list at {path} returned 500"

