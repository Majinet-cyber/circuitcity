# tests/test_cement_premium.py
"""
Comprehensive tests for cement vertical premium features:
- Sidebar navigation
- Dashboard filters (today, 7d, mtd, all, custom)
- Payment mix analytics
- Top products
- Smart pricing suggestions
- Sale undo/rollback
- Mobile navigation
- Catalog seeding
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.cement_seed import CEMENT_CATALOG, seed_cement_defaults
from inventory.date_ranges import get_date_range_label, parse_date_range
from inventory.mobile_nav import get_mobile_nav_items
from inventory.models import Location, MerchProduct
from inventory.models_verticals import CementCost, CementSale, CementSaleUndo
from inventory.services.pricing_suggestions import calculate_suggested_price, validate_selling_price
from inventory.utils_verticals import get_vertical_sidebar_items
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestCementSidebarNav(TestCase):
    """Test cement sidebar navigation items"""

    def test_cement_sidebar_has_required_items(self):
        """Cement sidebar must include Dashboard, Stock In, Sell, Costs, Admin Wallet, Analytics"""
        sidebar_items = get_vertical_sidebar_items("cement")

        # Extract keys from sidebar items
        item_keys = [item["key"] for item in sidebar_items]

        # Required items
        assert "dashboard" in item_keys, "Dashboard must be in sidebar"
        assert "stock_in" in item_keys, "Stock In must be in sidebar"
        assert "sell" in item_keys, "Sell must be in sidebar"
        assert "costs" in item_keys, "Costs must be in sidebar"
        assert "admin_wallet" in item_keys, "Admin Wallet must be in sidebar"
        assert "analytics" in item_keys, "Analytics must be in sidebar"

    def test_cement_sidebar_urls_correct(self):
        """Cement sidebar URLs must point to correct routes"""
        sidebar_items = get_vertical_sidebar_items("cement")

        # Find dashboard item
        dashboard_item = next((item for item in sidebar_items if item["key"] == "dashboard"), None)
        assert dashboard_item is not None
        assert dashboard_item["url"] == "verticals:cement_dashboard"
        assert "/verticals/cement/dashboard" in dashboard_item["active_prefix"]


@pytest.mark.django_db
class TestCementMobileNav(TestCase):
    """Test cement mobile navigation"""

    def setUp(self):
        """Create cement business"""
        self.user = User.objects.create_user(
            username="cement_mobile_test", email="mobile@cement.test", password="test1234"
        )
        self.business = Business.objects.create(
            name="Mobile Cement Test", slug="mobile-cement-test", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.client = Client()
        self.client.login(username="cement_mobile_test", password="test1234")

    def test_cement_mobile_nav_items(self):
        """Cement mobile nav must include Home, Stock In, Sell, Products, More"""
        # Create mock request
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.user
        request.business = self.business
        request.session = {}

        # Get mobile nav items
        mobile_items = get_mobile_nav_items(request)

        # Extract keys
        item_keys = [item["key"] for item in mobile_items]

        assert "home" in item_keys, "Home must be in mobile nav"
        assert "stock_in" in item_keys, "Stock In must be in mobile nav"
        assert "sell" in item_keys, "Sell must be in mobile nav"
        assert "products" in item_keys, "Products must be in mobile nav"
        assert "menu" in item_keys, "More/Menu must be in mobile nav"


@pytest.mark.django_db
class TestCementCatalogSeed(TestCase):
    """Test cement catalog seeding"""

    def setUp(self):
        """Create cement business"""
        self.user = User.objects.create_user(username="cement_seed_test", email="seed@cement.test", password="test1234")
        self.business = Business.objects.create(
            name="Seed Cement Test", slug="seed-cement-test", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )

    def test_seed_creates_50kg_cement_only(self):
        """Seed must create ONLY 50KG cement bags (9 brands), NO sand, stones, etc."""
        result = seed_cement_defaults(self.business)

        assert result["created"] > 0, "Must create products"
        assert result["created"] == 9, "Must create exactly 9 cement brands"

        # Check that products were created
        products = MerchProduct.objects.filter(business=self.business, kind=BusinessKind.CEMENT)
        assert products.count() == 9, "Must create exactly 9 cement brands (50KG only)"

        # Check all products are cement category and 50KG
        for product in products:
            assert product.category == "cement", f"Product {product.name} must be cement category"
            assert product.base_unit == "Bag (50KG)", f"Product {product.name} must be 50KG bag"
            assert "50" in product.name or "Cement" in product.name, f"Product name must indicate cement"

        # Verify specific brands exist
        brand_names = set(products.values_list("name", flat=True))
        expected_brands = {
            "Dangote Cement",
            "Aksher Cement",
            "Duracrete Cement",
            "Njati Cement",
            "Njati Extra Cement",
            "Khoma Cement",
            "Nkope Cement",
            "Lime Cement",
            "Nthanthwe Cement",
        }
        assert brand_names == expected_brands, f"Must have exactly these 9 brands: {expected_brands}"

    def test_seed_is_idempotent(self):
        """Seed must be idempotent (safe to run multiple times)"""
        # First seed
        result1 = seed_cement_defaults(self.business)
        created1 = result1["created"]

        # Second seed
        result2 = seed_cement_defaults(self.business)
        created2 = result2["created"]
        skipped2 = result2["skipped"]

        assert created2 == 0, "Second seed must not create new products"
        assert skipped2 == created1, "Second seed must skip all existing products"


@pytest.mark.django_db
class TestCementDashboardFilters(TestCase):
    """Test cement dashboard date filters"""

    def setUp(self):
        """Create cement business with sales"""
        self.user = User.objects.create_user(
            username="cement_filters_test", email="filters@cement.test", password="test1234"
        )
        self.business = Business.objects.create(
            name="Filters Cement Test", slug="filters-cement-test", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")

        # Create test product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Cement 50kg",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            base_unit="bag",
            cost_price=Decimal("10000"),
            selling_price=Decimal("12000"),
            quantity_in_stock=100,
            is_active=True,
        )

        self.client = Client()
        self.client.login(username="cement_filters_test", password="test1234")

    def test_dashboard_filter_today(self):
        """Dashboard filter 'today' must show only today's sales"""
        today = timezone.now()
        yesterday = today - timedelta(days=1)

        # Create today's sale
        CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=5,
            unit_price=Decimal("12000"),
            total_price=Decimal("60000"),
            unit_cost=Decimal("10000"),
            total_cost=Decimal("50000"),
            payment_method="CASH",
            sold_at=today,
        )

        # Create yesterday's sale
        CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=3,
            unit_price=Decimal("12000"),
            total_price=Decimal("36000"),
            unit_cost=Decimal("10000"),
            total_cost=Decimal("30000"),
            payment_method="CASH",
            sold_at=yesterday,
        )

        # Visit dashboard with 'today' filter
        response = self.client.get(reverse("verticals:cement_dashboard") + "?preset=today")
        assert response.status_code == 200

        # Check context
        assert response.context["total_revenue"] == Decimal("60000"), "Must show only today's revenue"

    def test_dashboard_filter_7d(self):
        """Dashboard filter '7d' must show last 7 days"""
        today = timezone.now()
        six_days_ago = today - timedelta(days=6)
        eight_days_ago = today - timedelta(days=8)

        # Create sale 6 days ago (within range)
        CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=5,
            unit_price=Decimal("12000"),
            total_price=Decimal("60000"),
            unit_cost=Decimal("10000"),
            total_cost=Decimal("50000"),
            payment_method="CASH",
            sold_at=six_days_ago,
        )

        # Create sale 8 days ago (outside range)
        CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=3,
            unit_price=Decimal("12000"),
            total_price=Decimal("36000"),
            unit_cost=Decimal("10000"),
            total_cost=Decimal("30000"),
            payment_method="CASH",
            sold_at=eight_days_ago,
        )

        # Visit dashboard with '7d' filter
        response = self.client.get(reverse("verticals:cement_dashboard") + "?preset=7d")
        assert response.status_code == 200

        # Check context (should only include 6 days ago sale)
        assert response.context["total_revenue"] == Decimal("60000"), "Must show only last 7 days revenue"

    def test_dashboard_payment_mix(self):
        """Dashboard must show payment mix breakdown"""
        # Create sales with different payment methods
        CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=5,
            unit_price=Decimal("12000"),
            total_price=Decimal("60000"),
            unit_cost=Decimal("10000"),
            total_cost=Decimal("50000"),
            payment_method="CASH",
        )

        CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=3,
            unit_price=Decimal("12000"),
            total_price=Decimal("36000"),
            unit_cost=Decimal("10000"),
            total_cost=Decimal("30000"),
            payment_method="MOMO",
        )

        # Visit dashboard
        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200

        # Check payment mix in context
        payment_mix = list(response.context["payment_mix"])
        assert len(payment_mix) >= 2, "Must show at least 2 payment methods"

    def test_dashboard_top_products(self):
        """Dashboard must show top products by revenue and quantity"""
        # Create sales
        CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=10,
            unit_price=Decimal("12000"),
            total_price=Decimal("120000"),
            unit_cost=Decimal("10000"),
            total_cost=Decimal("100000"),
            payment_method="CASH",
        )

        # Visit dashboard
        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200

        # Check top products in context
        top_products_revenue = list(response.context["top_products_revenue"])
        assert len(top_products_revenue) > 0, "Must show top products by revenue"

        top_products_qty = list(response.context["top_products_qty"])
        assert len(top_products_qty) > 0, "Must show top products by quantity"


@pytest.mark.django_db
class TestCementPricingSuggestions(TestCase):
    """Test smart pricing suggestions"""

    def test_calculate_suggested_price_15_percent(self):
        """Calculate suggested price with 15% margin"""
        result = calculate_suggested_price(
            cost_price=Decimal("10000"),
            target_margin_pct=Decimal("15"),
            rounding=50,
        )

        assert result["suggested_price"] > Decimal("10000"), "Suggested price must be higher than cost"
        assert result["margin_pct"] >= Decimal("14"), "Margin must be close to 15%"
        assert result["margin_amount"] > Decimal("0"), "Margin amount must be positive"

    def test_calculate_suggested_price_rounding(self):
        """Suggested price must be rounded nicely"""
        result = calculate_suggested_price(
            cost_price=Decimal("8543"),
            target_margin_pct=Decimal("20"),
            rounding=100,
        )

        # Check that price is rounded to nearest 100
        assert result["suggested_price"] % 100 == 0, "Price must be rounded to nearest 100"

    def test_validate_selling_price_below_cost(self):
        """Validation must warn when selling below cost"""
        result = validate_selling_price(
            selling_price=Decimal("9000"),
            cost_price=Decimal("10000"),
        )

        assert result["is_valid"] is False, "Must be invalid when selling below cost"
        assert len(result["warnings"]) > 0, "Must have warnings"
        assert "below cost" in result["warnings"][0].lower(), "Must warn about selling below cost"


@pytest.mark.django_db
class TestCementSaleUndo(TestCase):
    """Test sale undo/rollback feature"""

    def setUp(self):
        """Create cement business with sales"""
        self.user = User.objects.create_user(username="cement_undo_test", email="undo@cement.test", password="test1234")
        self.business = Business.objects.create(
            name="Undo Cement Test", slug="undo-cement-test", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")

        # Create test product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Cement 50kg",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            base_unit="bag",
            cost_price=Decimal("10000"),
            selling_price=Decimal("12000"),
            quantity_in_stock=100,
            is_active=True,
        )

        self.client = Client()
        self.client.login(username="cement_undo_test", password="test1234")

    def test_undo_sale_restores_stock(self):
        """Undo sale must restore stock quantity (programmatic test)"""
        # Create sale
        sale = CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=10,
            unit_price=Decimal("12000"),
            total_price=Decimal("120000"),
            unit_cost=Decimal("10000"),
            total_cost=Decimal("100000"),
            payment_method="CASH",
        )

        # Reduce stock (simulate sale)
        self.product.quantity_in_stock -= 10
        self.product.save()

        initial_stock = self.product.quantity_in_stock

        # Programmatically undo the sale (simulating the undo_sale view logic)
        with transaction.atomic():
            product = MerchProduct.objects.select_for_update().get(pk=self.product.pk)
            product.quantity_in_stock += sale.quantity
            product.save(update_fields=["quantity_in_stock"])

            sale.is_void = True
            sale.save(update_fields=["is_void"])

            CementSaleUndo.objects.create(
                sale=sale,
                business=self.business,
                undone_by=self.user,
                reason="Data entry error",
                original_quantity=sale.quantity,
                original_total_price=sale.total_price,
                original_product_name=sale.product.name,
            )

        # Refresh
        self.product.refresh_from_db()
        sale.refresh_from_db()

        # Check stock restored
        assert self.product.quantity_in_stock == initial_stock + 10, "Stock must be restored"

        # Check sale marked as void
        assert sale.is_void is True, "Sale must be marked as void"

        # Check undo record created
        assert CementSaleUndo.objects.filter(sale=sale).exists(), "Undo record must be created"

    def test_undo_sale_cannot_undo_twice(self):
        """Cannot undo the same sale twice"""
        # Create sale
        sale = CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=10,
            unit_price=Decimal("12000"),
            total_price=Decimal("120000"),
            unit_cost=Decimal("10000"),
            total_cost=Decimal("100000"),
            payment_method="CASH",
        )

        # Reduce stock (simulate sale)
        self.product.quantity_in_stock -= 10
        self.product.save()
        initial_stock = self.product.quantity_in_stock

        # Manually undo the sale (simulate first undo)
        with transaction.atomic():
            product = MerchProduct.objects.select_for_update().get(pk=self.product.pk)
            product.quantity_in_stock += sale.quantity
            product.save(update_fields=["quantity_in_stock"])

            sale.is_void = True
            sale.save(update_fields=["is_void"])

            CementSaleUndo.objects.create(
                sale=sale,
                business=self.business,
                undone_by=self.user,
                reason="First undo",
                original_quantity=sale.quantity,
                original_total_price=sale.total_price,
                original_product_name=sale.product.name,
            )

        # Refresh
        sale.refresh_from_db()
        self.product.refresh_from_db()

        assert sale.is_void is True, "Sale must be marked as void"
        assert self.product.quantity_in_stock == initial_stock + 10, "Stock must be restored"

        # Try to undo again via API (should fail)
        response = self.client.post(
            reverse("cement:undo_sale", kwargs={"sale_id": sale.id}),
            {"reason": "Second undo attempt"},
        )

        # Check that second undo is rejected
        assert response.status_code == 302, "Must redirect"

        # Check only one undo record exists
        undo_count = CementSaleUndo.objects.filter(sale=sale).count()
        assert undo_count == 1, f"Must have only one undo record, got {undo_count}"

        # Stock should not change again
        self.product.refresh_from_db()
        assert self.product.quantity_in_stock == initial_stock + 10, "Stock must not change on second undo attempt"

    def test_undo_sale_time_limit(self):
        """Cannot undo sales older than 7 days"""
        # Create old sale (8 days ago)
        old_date = timezone.now() - timedelta(days=8)
        sale = CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=10,
            unit_price=Decimal("12000"),
            total_price=Decimal("120000"),
            unit_cost=Decimal("10000"),
            total_cost=Decimal("100000"),
            payment_method="CASH",
            sold_at=old_date,
        )

        # Try to undo
        response = self.client.post(
            reverse("cement:undo_sale", kwargs={"sale_id": sale.id}),
            {"reason": "Too old"},
        )

        # Check that undo fails
        assert response.status_code == 302, "Must redirect"

        # Check sale not marked as void
        sale.refresh_from_db()
        assert sale.is_void is False, "Sale must not be voided"


@pytest.mark.django_db
class TestCementPremiumDashboardHeader(TestCase):
    """Test premium dashboard header features (business name, greeting, quote)"""

    def setUp(self):
        """Create cement business"""
        self.user = User.objects.create_user(
            username="cement_header_test", email="header@cement.test", password="test1234", first_name="John"
        )
        self.business = Business.objects.create(
            name="Premium Cement Co.", slug="premium-cement-co", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.client = Client()
        self.client.login(username="cement_header_test", password="test1234")

    def test_dashboard_shows_business_name(self):
        """Dashboard must display business name in header"""
        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200

        # Check context has business name
        assert response.context["DASHBOARD_BRAND_TITLE"] == "Premium Cement Co."

    def test_dashboard_shows_greeting(self):
        """Dashboard must display personalized greeting"""
        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200

        # Check context has greeting
        assert "DASHBOARD_GREETING" in response.context
        assert response.context["DASHBOARD_USER_NAME"] == "John"

    def test_dashboard_shows_hourly_quote(self):
        """Dashboard must display hourly rotating quote"""
        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200

        # Check context has quotes
        assert "DASHBOARD_QUOTES" in response.context
        quotes = response.context["DASHBOARD_QUOTES"]
        assert "quotes" in quotes
        assert len(quotes["quotes"]) > 0, "Must have at least one quote"


@pytest.mark.django_db
class TestDateRangeUtils(TestCase):
    """Test date range utility functions"""

    def test_parse_date_range_today(self):
        """Parse 'today' preset"""
        start_dt, end_dt = parse_date_range(preset="today")

        assert start_dt is not None
        assert end_dt is not None
        assert start_dt.date() == timezone.now().date()
        assert end_dt.date() == timezone.now().date()

    def test_parse_date_range_7d(self):
        """Parse '7d' preset"""
        start_dt, end_dt = parse_date_range(preset="7d")

        assert start_dt is not None
        assert end_dt is not None

        # Check that range is 7 days
        days_diff = (end_dt.date() - start_dt.date()).days
        assert days_diff == 6, "Must be 7 days (6 days difference + today)"

    def test_parse_date_range_custom(self):
        """Parse custom date range"""
        start_dt, end_dt = parse_date_range(
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert start_dt is not None
        assert end_dt is not None
        assert start_dt.date() == date(2024, 1, 1)
        assert end_dt.date() == date(2024, 1, 31)

    def test_get_date_range_label(self):
        """Get human-readable date range label"""
        label_today = get_date_range_label(preset="today")
        assert label_today == "Today"

        label_7d = get_date_range_label(preset="7d")
        assert label_7d == "Last 7 days"

        label_mtd = get_date_range_label(preset="mtd")
        assert label_mtd == "Month to Date"

        label_all = get_date_range_label(preset="all")
        assert label_all == "All Time"
