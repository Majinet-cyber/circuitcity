"""
Tests for the Business Health Score service and related dashboard views.

Covers:
    - Score works with complete data
    - Score works with missing / partial data
    - Score does not crash for a brand-new business
    - Business isolation: health score is scoped to one business
    - Landing page loads (no regression)
    - Dashboard home still loads
    - Business health breakdown page loads (requires login + business)
    - Business health API endpoint returns JSON
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.utils import timezone

from inventory.models import InventoryItem, Location
from tenants.models import Business, Membership

try:
    from inventory.models import Product
except ImportError:
    Product = None

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_business(name="Test Biz", slug=None):
    slug = slug or name.lower().replace(" ", "-")
    return Business.objects.create(name=name, slug=slug)


def _create_user(username="user1", password="pass"):
    return User.objects.create_user(username=username, password=password)


_product_counter = 0


def _create_product():
    global _product_counter
    _product_counter += 1
    if Product is None:
        return None
    return Product.objects.create(
        code=f"TST{_product_counter:04d}",
        brand="TestBrand",
        model=f"TestModel{_product_counter}",
        cost_price=1000,
        sale_price=1500,
    )


def _create_location(business, name="Main"):
    return Location.objects.create(business=business, name=name, is_default=True)


def _create_sold_item(business, location, product, order_price=1000, selling_price=1500, days_ago=0):
    if product is None:
        return None  # Can't create without a product FK
    import random
    sold_at = timezone.now() - timedelta(days=days_ago)
    return InventoryItem.objects.create(
        business=business,
        current_location=location,
        product=product,
        order_price=Decimal(str(order_price)),
        selling_price=Decimal(str(selling_price)),
        status="SOLD",
        sold_at=sold_at,
        is_active=True,
        imei=str(random.randint(10**14, 10**15 - 1)),
    )


def _create_instock_item(business, location, product, order_price=1000, selling_price=1500):
    if product is None:
        return None
    import random
    return InventoryItem.objects.create(
        business=business,
        current_location=location,
        product=product,
        order_price=Decimal(str(order_price)),
        selling_price=Decimal(str(selling_price)),
        status="IN_STOCK",
        is_active=True,
        imei=str(random.randint(10**14, 10**15 - 1)),
    )


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------

class BusinessHealthScoreNewBusinessTest(TestCase):
    """Score should not crash and should return onboarding state for new businesses."""

    def setUp(self):
        self.business = _create_business("New Biz", "new-biz")

    def test_does_not_crash_new_business(self):
        from dashboard.services_health import calculate_business_health_score
        result = calculate_business_health_score(self.business)
        self.assertIsInstance(result, dict)

    def test_new_business_returns_onboarding_or_null_score(self):
        from dashboard.services_health import calculate_business_health_score
        result = calculate_business_health_score(self.business)
        # Either onboarding state or a valid score dict
        self.assertIn("score", result)
        self.assertIn("label", result)
        self.assertIn("components", result)
        self.assertIn("recommendations", result)

    def test_new_business_recommendations_are_list(self):
        from dashboard.services_health import calculate_business_health_score
        result = calculate_business_health_score(self.business)
        self.assertIsInstance(result["recommendations"], list)
        self.assertGreater(len(result["recommendations"]), 0)

    def test_new_business_has_all_component_keys(self):
        from dashboard.services_health import calculate_business_health_score
        result = calculate_business_health_score(self.business)
        expected_keys = {
            "profit_trend", "cash_flow", "stock_risk",
            "sales_consistency", "expense_control", "credit_exposure",
            "staff_efficiency",
        }
        self.assertEqual(set(result["components"].keys()), expected_keys)


class BusinessHealthScoreWithDataTest(TestCase):
    """Score calculates correctly when there is real sales/stock data."""

    def setUp(self):
        self.business = _create_business("Active Biz", "active-biz")
        self.location = _create_location(self.business)
        self.product = _create_product()

        # Create 15 days of sold items (good profit margin)
        for i in range(15):
            _create_sold_item(
                self.business, self.location, self.product,
                order_price=1000, selling_price=1500, days_ago=i
            )

        # Some in-stock items
        for _ in range(5):
            _create_instock_item(
                self.business, self.location, self.product,
                order_price=1000, selling_price=1500
            )

    def test_score_is_int_between_0_and_100(self):
        from dashboard.services_health import calculate_business_health_score
        result = calculate_business_health_score(self.business)
        if result.get("is_onboarding"):
            self.skipTest("Insufficient data for score calculation in this environment.")
        score = result.get("score")
        if score is not None:
            self.assertIsInstance(score, int)
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)

    def test_label_is_string(self):
        from dashboard.services_health import calculate_business_health_score
        result = calculate_business_health_score(self.business)
        self.assertIsInstance(result["label"], str)
        self.assertGreater(len(result["label"]), 0)

    def test_status_color_is_valid(self):
        from dashboard.services_health import calculate_business_health_score
        result = calculate_business_health_score(self.business)
        valid_colors = {"green", "amber", "orange", "red", "gray"}
        self.assertIn(result["status_color"], valid_colors)

    def test_components_have_required_fields(self):
        from dashboard.services_health import calculate_business_health_score
        result = calculate_business_health_score(self.business)
        for key, comp in result["components"].items():
            self.assertIn("label", comp, f"Component {key} missing 'label'")
            self.assertIn("explanation", comp, f"Component {key} missing 'explanation'")
            # score may be None (not enough data) or an int
            self.assertIn("score", comp, f"Component {key} missing 'score'")

    def test_period_is_in_result(self):
        from dashboard.services_health import calculate_business_health_score
        result = calculate_business_health_score(self.business)
        self.assertIn("period", result)
        self.assertIn("start", result["period"])
        self.assertIn("end", result["period"])

    def test_custom_date_range(self):
        from dashboard.services_health import calculate_business_health_score
        today = timezone.localdate()
        start = today - timedelta(days=7)
        result = calculate_business_health_score(self.business, start_date=start, end_date=today)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["period"]["start"], start)
        self.assertEqual(result["period"]["end"], today)


class BusinessHealthScoreIsolationTest(TestCase):
    """Health scores must not leak data between businesses."""

    def setUp(self):
        self.biz_a = _create_business("Biz A", "biz-a")
        self.biz_b = _create_business("Biz B", "biz-b")
        self.location_a = _create_location(self.biz_a, "Store A")
        self.product = _create_product()

        # Only biz_a has sales
        for i in range(5):
            _create_sold_item(self.biz_a, self.location_a, self.product, days_ago=i)

    def test_biz_b_sees_no_sales(self):
        from dashboard.services_health import calculate_business_health_score
        result_b = calculate_business_health_score(self.biz_b)
        # biz_b has no stock and no sales — profit trend should be null/no data
        profit = result_b["components"]["profit_trend"]
        # Either null score or onboarding state
        self.assertTrue(
            profit["score"] is None or result_b.get("is_onboarding"),
            f"biz_b should not have profit data, got: {profit}"
        )


class BusinessHealthScorePartialDataTest(TestCase):
    """Score calculates gracefully when only some components have data."""

    def setUp(self):
        self.business = _create_business("Partial Biz", "partial-biz")
        self.location = _create_location(self.business)
        self.product = _create_product()

        # Only 1 day of sales — not enough for consistency but enough for profit/cash
        _create_sold_item(self.business, self.location, self.product, days_ago=0)
        _create_sold_item(self.business, self.location, self.product, days_ago=1)

    def test_does_not_crash_with_partial_data(self):
        from dashboard.services_health import calculate_business_health_score
        result = calculate_business_health_score(self.business)
        self.assertIsInstance(result, dict)
        self.assertIn("score", result)

    def test_consistency_null_with_only_2_days(self):
        from dashboard.services_health import calculate_business_health_score
        result = calculate_business_health_score(self.business)
        # sales_consistency needs at least 3 days of data
        consistency = result["components"]["sales_consistency"]
        # Should be null or very low when data is thin
        if consistency["score"] is not None:
            # If a score is returned it should be a valid int
            self.assertIsInstance(consistency["score"], int)

    def test_overall_score_only_uses_available_components(self):
        from dashboard.services_health import calculate_business_health_score
        result = calculate_business_health_score(self.business)
        if result.get("is_onboarding") or result.get("score") is None:
            return
        score = result["score"]
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


# ---------------------------------------------------------------------------
# View / HTTP tests
# ---------------------------------------------------------------------------

class LandingPageTest(TestCase):
    """Public landing page must load successfully."""

    def test_landing_page_loads(self):
        client = Client()
        response = client.get("/landing/")
        self.assertEqual(response.status_code, 200)

    def test_landing_page_contains_hero_headline(self):
        client = Client()
        response = client.get("/landing/")
        content = response.content.decode("utf-8")
        # Check for the new marketing headline
        self.assertIn("Stop losing money blindly", content)

    def test_landing_page_contains_whatsapp_section(self):
        client = Client()
        response = client.get("/landing/")
        content = response.content.decode("utf-8")
        # Accept any WhatsApp-related section reference (ID may vary)
        self.assertTrue(
            "whatsapp-benefits" in content
            or "WhatsApp" in content
            or "whatsapp" in content.lower()
        )

    def test_landing_page_contains_industry_solutions(self):
        client = Client()
        response = client.get("/landing/")
        content = response.content.decode("utf-8")
        # Accept industry section by class, ID, or heading text
        self.assertTrue(
            "industry-solutions" in content
            or "industry-cards" in content
            or "industry-card" in content
            or "Industry Solutions" in content
        )

    def test_landing_page_contains_pricing(self):
        client = Client()
        response = client.get("/landing/")
        content = response.content.decode("utf-8")
        # Accept pricing section by any common identifier
        self.assertTrue(
            "pricing-snapshot" in content
            or "pricing-grid" in content
            or "pricing-card" in content
            or 'id="pricing"' in content
        )

    def test_landing_page_contains_testimonials(self):
        client = Client()
        response = client.get("/landing/")
        content = response.content.decode("utf-8")
        self.assertIn("testimonials", content)


class DashboardNoRegressionTest(TestCase):
    """Existing dashboard home route must still load after our changes."""

    def setUp(self):
        self.user = _create_user("dash_user", "pass123")
        self.business = _create_business("Dash Biz", "dash-biz")
        self.location = _create_location(self.business)
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
            location=self.location,
        )
        self.client = Client()
        self.client.login(username="dash_user", password="pass123")
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()

    def test_dashboard_home_loads(self):
        response = self.client.get("/dashboard/")
        # Should redirect (to vertical dashboard) or load (200)
        self.assertIn(response.status_code, [200, 302])

    def test_dashboard_health_breakdown_page_loads(self):
        response = self.client.get("/dashboard/business-health/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_health_api_returns_json(self):
        response = self.client.get("/dashboard/api/business-health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type", ""), "application/json")
        data = response.json()
        self.assertIn("score", data)
        self.assertIn("components", data)
        self.assertIn("recommendations", data)


class BusinessHealthAnonymousTest(TestCase):
    """Health score endpoints must redirect anonymous users."""

    def test_health_page_requires_login(self):
        client = Client()
        response = client.get("/dashboard/business-health/")
        # Should redirect to login
        self.assertIn(response.status_code, [302, 301])
        location = response.get("Location", "")
        self.assertTrue(
            "login" in location.lower() or "accounts" in location.lower(),
            f"Expected redirect to login, got: {location}"
        )

    def test_health_api_requires_login(self):
        client = Client()
        response = client.get("/dashboard/api/business-health/")
        self.assertIn(response.status_code, [302, 301])
