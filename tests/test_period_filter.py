# tests/test_period_filter.py
"""
Regression tests for Period Filter functionality (All time + Month picker).
Ensures dashboard aggregations work correctly across all verticals.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from tenants.models import Business

User = get_user_model()


@pytest.mark.django_db
class TestPeriodFilterSSoT:
    """Test the SSOT period filter utility in base.py - ALL OPTIONS"""

    def test_parse_period_all_time(self, rf):
        """Test period=all returns None dates and correct label"""
        from inventory.verticals.base import parse_date_range_from_request

        request = rf.get("/dashboard/?period=all")
        result = parse_date_range_from_request(request)

        assert result["filter_mode"] == "all"
        assert result["period"] == "all"
        assert result["month"] is None
        assert result["year"] is None
        assert result["start_date"] is None
        assert result["end_date"] is None
        assert result["range_label"] == "All time"

    def test_parse_period_month_current_year(self, rf):
        """Test period=month with month param defaults to current year"""
        from inventory.verticals.base import parse_date_range_from_request

        request = rf.get("/dashboard/?period=month&month=3")  # March
        result = parse_date_range_from_request(request)

        current_year = timezone.now().year

        assert result["filter_mode"] == "month"
        assert result["period"] == "month"
        assert result["month"] == 3
        assert result["year"] == current_year
        # Check dates (now timezone-aware datetimes)
        assert result["start_date"].date() == date(current_year, 3, 1)
        assert result["end_date"].date() == date(current_year, 4, 1)  # First day of next month (exclusive)
        assert "March" in result["range_label"]

    def test_parse_period_month_with_year(self, rf):
        """Test period=month with both month and year params"""
        from inventory.verticals.base import parse_date_range_from_request

        request = rf.get("/dashboard/?period=month&month=12&year=2025")  # December 2025
        result = parse_date_range_from_request(request)

        assert result["filter_mode"] == "month"
        assert result["period"] == "month"
        assert result["month"] == 12
        assert result["year"] == 2025
        # Check dates (now timezone-aware datetimes)
        assert result["start_date"].date() == date(2025, 12, 1)
        assert result["end_date"].date() == date(2026, 1, 1)  # Wraps to next year
        assert result["range_label"] == "December 2025"

    def test_parse_range_mtd(self, rf):
        """Test range=mtd (Month-to-date) - RESTORED"""
        from inventory.verticals.base import parse_date_range_from_request

        request = rf.get("/dashboard/?range=mtd")
        result = parse_date_range_from_request(request)

        today = timezone.now().date()
        month_start = today.replace(day=1)
        tomorrow = today + timedelta(days=1)

        assert result["filter_mode"] == "mtd"
        assert result["period"] is None  # Legacy mode
        # Check dates (now timezone-aware datetimes)
        assert result["start_date"].date() == month_start
        assert result["end_date"].date() == tomorrow  # Exclusive end
        assert "MTD" in result["range_label"] or "This month" in result["range_label"]

    def test_parse_range_last7(self, rf):
        """Test range=last7 (Last 7 days) - RESTORED"""
        from inventory.verticals.base import parse_date_range_from_request

        request = rf.get("/dashboard/?range=last7")
        result = parse_date_range_from_request(request)

        today = timezone.now().date()
        expected_start = today - timedelta(days=6)  # 6 days ago + today = 7 days
        tomorrow = today + timedelta(days=1)

        assert result["filter_mode"] == "last7"
        assert result["period"] is None
        # Check dates (now timezone-aware datetimes)
        assert result["start_date"].date() == expected_start
        assert result["end_date"].date() == tomorrow
        assert "7 days" in result["range_label"].lower()

    def test_parse_range_custom(self, rf):
        """Test range=custom with start/end dates - RESTORED"""
        from inventory.verticals.base import parse_date_range_from_request

        request = rf.get("/dashboard/?range=custom&start=2025-03-01&end=2025-03-15")
        result = parse_date_range_from_request(request)

        assert result["filter_mode"] == "custom"
        assert result["period"] is None
        # Check dates (now timezone-aware datetimes)
        assert result["start_date"].date() == date(2025, 3, 1)
        assert result["end_date"].date() == date(2025, 3, 16)  # Exclusive end (end + 1 day)
        assert result["custom_start"] == date(2025, 3, 1)
        assert result["custom_end"] == date(2025, 3, 15)  # Original inclusive end

    def test_precedence_range_wins_over_period(self, rf):
        """Test that legacy range param takes precedence over period param"""
        from inventory.verticals.base import parse_date_range_from_request

        # Both range and period provided - range should win
        request = rf.get("/dashboard/?range=last7&period=all")
        result = parse_date_range_from_request(request)

        assert result["filter_mode"] == "last7"  # range wins
        assert result["period"] is None  # Not using period mode

    def test_default_fallback_mtd(self, rf):
        """Test default behavior when no params provided (should be MTD)"""
        from inventory.verticals.base import parse_date_range_from_request

        request = rf.get("/dashboard/")  # No params
        result = parse_date_range_from_request(request)

        today = timezone.now().date()
        month_start = today.replace(day=1)

        assert result["filter_mode"] == "mtd"
        # Check dates (now timezone-aware datetimes)
        assert result["start_date"].date() == month_start
        assert result["end_date"] is not None


@pytest.mark.django_db
class TestClothingPeriodFilter:
    """Test period filter in Clothing vertical"""

    @pytest.fixture
    def setup_clothing_data(self, db):
        """Create test business, user, and sales data across different months"""
        # Create business
        business = Business.objects.create(
            name="Test Clothing Store",
            business_kind=BusinessKind.CLOTHING,
        )

        # Create test user
        user = User.objects.create_user(
            username="testclerk",
            email="clerk@test.com",
            password="testpass123",
        )

        # Import models
        from inventory.models import MerchProduct
        from inventory.models_verticals import ClothingSale

        # Create product
        product = MerchProduct.objects.create(
            business=business,
            name="Test T-Shirt",
            kind=BusinessKind.CLOTHING,
            selling_price=Decimal("50.00"),
            cost_price=Decimal("25.00"),
        )

        # Create sales across different months
        january_date = timezone.make_aware(timezone.datetime(2025, 1, 15, 10, 0, 0))
        february_date = timezone.make_aware(timezone.datetime(2025, 2, 15, 10, 0, 0))
        march_date = timezone.make_aware(timezone.datetime(2025, 3, 15, 10, 0, 0))

        # January: 2 sales, 100 revenue
        ClothingSale.objects.create(
            business=business,
            product=product,
            quantity=1,
            unit_price=Decimal("50.00"),
            total_price=Decimal("50.00"),
            total_cost=Decimal("25.00"),
            sold_at=january_date,
            sold_by=user,
        )
        ClothingSale.objects.create(
            business=business,
            product=product,
            quantity=1,
            unit_price=Decimal("50.00"),
            total_price=Decimal("50.00"),
            total_cost=Decimal("25.00"),
            sold_at=january_date + timedelta(days=1),
            sold_by=user,
        )

        # February: 1 sale, 50 revenue
        ClothingSale.objects.create(
            business=business,
            product=product,
            quantity=1,
            unit_price=Decimal("50.00"),
            total_price=Decimal("50.00"),
            total_cost=Decimal("25.00"),
            sold_at=february_date,
            sold_by=user,
        )

        # March: 3 sales, 150 revenue
        for i in range(3):
            ClothingSale.objects.create(
                business=business,
                product=product,
                quantity=1,
                unit_price=Decimal("50.00"),
                total_price=Decimal("50.00"),
                total_cost=Decimal("25.00"),
                sold_at=march_date + timedelta(days=i),
                sold_by=user,
            )

        return {
            "business": business,
            "user": user,
            "product": product,
        }

    def test_clothing_month_filter_january(self, rf, setup_clothing_data):
        """Test filtering clothing dashboard by January 2025"""
        from inventory.verticals.base import clothing_sales_metrics

        business = setup_clothing_data["business"]

        # Call with January 2025
        result = clothing_sales_metrics(
            business,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 2, 1),  # Exclusive end
        )

        # Should only show January sales: 2 sales, 100 revenue, 50 cost
        assert result["total_sales"] == 2
        assert result["revenue"] == Decimal("100.00")
        assert result["cost_of_goods"] == Decimal("50.00")

    def test_clothing_month_filter_march(self, rf, setup_clothing_data):
        """Test filtering clothing dashboard by March 2025"""
        from inventory.verticals.base import clothing_sales_metrics

        business = setup_clothing_data["business"]

        # Call with March 2025
        result = clothing_sales_metrics(
            business,
            start_date=date(2025, 3, 1),
            end_date=date(2025, 4, 1),  # Exclusive end
        )

        # Should only show March sales: 3 sales, 150 revenue, 75 cost
        assert result["total_sales"] == 3
        assert result["revenue"] == Decimal("150.00")
        assert result["cost_of_goods"] == Decimal("75.00")

    def test_clothing_all_time_filter(self, rf, setup_clothing_data):
        """Test all-time aggregation (no date filtering)"""
        from inventory.models_verticals import ClothingSale
        from django.db.models import Sum, Count
        from decimal import Decimal

        business = setup_clothing_data["business"]

        # Query all sales directly (no date filter = all-time)
        sales_qs = ClothingSale.objects.filter(business=business)

        # Manually aggregate
        aggregates = sales_qs.aggregate(
            total_sales=Count("id"),
            revenue=Sum("total_price"),
            cost=Sum("total_cost"),
        )

        # Should show all sales: 6 sales total (2+1+3), 300 revenue, 150 cost
        assert aggregates["total_sales"] == 6
        assert aggregates["revenue"] == Decimal("300.00")
        assert aggregates["cost"] == Decimal("150.00")


@pytest.mark.django_db
class TestPhonesPeriodFilter:
    """Test period filter in Phones vertical"""

    @pytest.fixture
    def setup_phones_data(self, db):
        """Create test business, user, and inventory data across different months"""
        # Create business
        business = Business.objects.create(
            name="Test Phone Store",
            business_kind=BusinessKind.PHONES,
        )

        # Create test user
        user = User.objects.create_user(
            username="testclerk",
            email="clerk@test.com",
            password="testpass123",
        )

        # Import models
        from inventory.models import InventoryItem, PhoneProduct

        # Create phone product
        phone = PhoneProduct.objects.create(
            business=business,
            brand="Samsung",
            model="Galaxy S21",
            variant="128GB",
        )

        # Create sold phones across different months
        january_date = timezone.make_aware(timezone.datetime(2025, 1, 15, 10, 0, 0))
        february_date = timezone.make_aware(timezone.datetime(2025, 2, 15, 10, 0, 0))

        # January: 2 phones sold, 1000 revenue
        for i in range(2):
            InventoryItem.objects.create(
                business=business,
                product=phone,
                status="SOLD",
                order_price=Decimal("300.00"),
                selling_price=Decimal("500.00"),
                sold_at=january_date + timedelta(days=i),
                assigned_agent=user,
            )

        # February: 1 phone sold, 500 revenue
        InventoryItem.objects.create(
            business=business,
            product=phone,
            status="SOLD",
            order_price=Decimal("300.00"),
            selling_price=Decimal("500.00"),
            sold_at=february_date,
            assigned_agent=user,
        )

        return {
            "business": business,
            "user": user,
            "phone": phone,
        }

    def test_phones_month_filter_january(self, rf, setup_phones_data):
        """Test filtering phones dashboard by January 2025"""
        from inventory.verticals.base import phone_sales_metrics

        business = setup_phones_data["business"]

        # Call with January 2025
        result = phone_sales_metrics(
            business,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 2, 1),  # Exclusive end
        )

        # Should only show January sales: 2 phones, 1000 revenue, 600 cost
        assert result["units_sold"] == 2
        assert result["revenue"] == Decimal("1000.00")
        assert result["cost_of_goods"] == Decimal("600.00")

    def test_phones_all_time_filter(self, rf, setup_phones_data):
        """Test all-time aggregation for phones"""
        from inventory.models import InventoryItem
        from django.db.models import Sum, Count
        from decimal import Decimal

        business = setup_phones_data["business"]

        # Query sold items directly (simulates what phone_sales_metrics does)
        sold_items = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            is_active=True,
        )
        # For all-time, we don't apply date filtering

        # Manually aggregate
        aggregates = sold_items.aggregate(
            units_sold=Count("id"),
            revenue=Sum("selling_price"),
            cost=Sum("order_price"),
        )

        # Should show all sales: 3 phones, 1500 revenue, 900 cost
        assert aggregates["units_sold"] == 3
        assert aggregates["revenue"] == Decimal("1500.00")
        assert aggregates["cost"] == Decimal("900.00")


@pytest.mark.django_db
class TestPeriodFilterQueryString:
    """Test that query strings are properly constructed and parsed"""

    def test_period_all_query_string(self, client, admin_user):
        """Test ?period=all works in actual dashboard request"""
        client.force_login(admin_user)

        # Create business for user
        business = Business.objects.create(
            name="Test Business",
            business_kind=BusinessKind.PHONES,
        )
        business.memberships.create(user=admin_user, role="MANAGER")

        # Request dashboard with period=all (use phones-specific URL)
        response = client.get("/inventory/verticals/phones/dashboard/?period=all")

        # Should not error (200 or redirect depending on setup)
        assert response.status_code in [200, 302]

    def test_period_month_query_string(self, client, admin_user):
        """Test ?period=month&month=5 works in actual dashboard request"""
        client.force_login(admin_user)

        # Create business for user
        business = Business.objects.create(
            name="Test Business",
            business_kind=BusinessKind.CLOTHING,
        )
        business.memberships.create(user=admin_user, role="MANAGER")

        # Request dashboard with period=month&month=5 (May) (use clothing-specific URL)
        response = client.get("/inventory/verticals/clothing/dashboard/?period=month&month=5")

        # Should not error
        assert response.status_code in [200, 302]

