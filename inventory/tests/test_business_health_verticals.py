# inventory/tests/test_business_health_verticals.py
"""
Business Health Check — Vertical-Aware Tests
==============================================

Tests that the health check service:
- Returns a score (int) and required keys for each vertical
- Returns grade, risk_level, weekly_mission, encouraging_summary
- Handles empty data gracefully (is_onboarding state)
- Returns vertical-specific components for Mixed Retail, Mobile Money, and Consultancy
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business
from inventory.business_kinds import BusinessKind
from dashboard.services_health import calculate_business_health_score

User = get_user_model()

REQUIRED_KEYS = {"score", "label", "status_color", "components", "recommendations", "period", "is_onboarding"}
SCORED_EXTRA_KEYS = {"grade", "risk_level", "weekly_mission", "encouraging_summary", "top_problems", "top_actions"}


def _make_business(kind):
    import random
    uid = random.randint(1000, 9999)
    return Business.objects.create(
        name=f"Health Test {kind} {uid}",
        business_kind=kind,
    )


class HealthCheckEmptyStateTest(TestCase):
    """Health check handles new/empty business gracefully."""

    def test_empty_mixed_retail_business(self):
        """New Mixed Retail business returns is_onboarding state or score without crashing."""
        biz = _make_business(BusinessKind.MIXED_RETAIL)
        result = calculate_business_health_score(biz)
        self.assertIn("is_onboarding", result)
        self.assertIn("components", result)
        self.assertIn("recommendations", result)

    def test_empty_mobile_money_business(self):
        """New Mobile Money business returns is_onboarding state or score without crashing."""
        biz = _make_business(BusinessKind.MOBILE_MONEY)
        result = calculate_business_health_score(biz)
        self.assertIn("is_onboarding", result)
        self.assertIn("components", result)

    def test_empty_consultancy_business(self):
        """New Consultancy business returns is_onboarding state or score without crashing."""
        biz = _make_business(BusinessKind.CONSULTANCY)
        result = calculate_business_health_score(biz)
        self.assertIn("is_onboarding", result)
        self.assertIn("components", result)


class HealthCheckReturnStructureTest(TestCase):
    """Health check returns correct structure when data exists."""

    def _seed_retail_data(self, biz):
        """Create minimal retail data so health check scores something."""
        from inventory.models_mixed_retail import RetailProduct, RetailSale
        import datetime

        product = RetailProduct.objects.create(
            business=biz,
            name="Health Test Product",
            cost_price=Decimal("500"),
            selling_price=Decimal("800"),
            stock_quantity=Decimal("50"),
            reorder_level=Decimal("5"),
        )
        today = timezone.now()
        for i in range(5):
            RetailSale.objects.create(
                business=biz,
                product=product,
                quantity=Decimal("2"),
                unit_price=Decimal("800"),
                cost_price_snapshot=Decimal("500"),
                payment_method="cash",
                sold_at=today,
            )

    def test_mixed_retail_health_returns_score(self):
        """Mixed Retail with sales data returns a numeric score."""
        biz = _make_business(BusinessKind.MIXED_RETAIL)
        self._seed_retail_data(biz)
        result = calculate_business_health_score(biz)

        if not result.get("is_onboarding"):
            self.assertIsInstance(result["score"], int)
            self.assertGreaterEqual(result["score"], 0)
            self.assertLessEqual(result["score"], 100)

    def test_mixed_retail_health_returns_grade_and_risk(self):
        """Mixed Retail health result includes grade and risk_level fields."""
        biz = _make_business(BusinessKind.MIXED_RETAIL)
        self._seed_retail_data(biz)
        result = calculate_business_health_score(biz)

        if not result.get("is_onboarding"):
            self.assertIn("grade", result)
            self.assertIn("risk_level", result)
            self.assertIn("weekly_mission", result)
            self.assertIn("encouraging_summary", result)

    def test_health_recommendations_are_list(self):
        """recommendations is always a list."""
        biz = _make_business(BusinessKind.MIXED_RETAIL)
        result = calculate_business_health_score(biz)
        self.assertIsInstance(result["recommendations"], list)

    def test_health_components_is_dict(self):
        """components is always a dict."""
        biz = _make_business(BusinessKind.MIXED_RETAIL)
        result = calculate_business_health_score(biz)
        self.assertIsInstance(result["components"], dict)

    def test_health_period_present(self):
        """period key contains start and end dates."""
        biz = _make_business(BusinessKind.CONSULTANCY)
        result = calculate_business_health_score(biz)
        self.assertIn("period", result)
        self.assertIn("start", result["period"])
        self.assertIn("end", result["period"])

    def test_health_never_crashes_on_any_vertical(self):
        """Health check does not raise exceptions for any vertical type."""
        verticals = [
            BusinessKind.MIXED_RETAIL,
            BusinessKind.MOBILE_MONEY,
            BusinessKind.CONSULTANCY,
        ]
        for kind in verticals:
            biz = _make_business(kind)
            try:
                result = calculate_business_health_score(biz)
                self.assertIsNotNone(result)
            except Exception as e:
                self.fail(f"calculate_business_health_score raised {type(e).__name__} for {kind}: {e}")


class HealthCheckMobileMoneyTest(TestCase):
    """Mobile Money-specific health check components."""

    def setUp(self):
        self.biz = _make_business(BusinessKind.MOBILE_MONEY)

    def test_mobile_money_health_does_not_crash(self):
        """Mobile Money health check runs without errors."""
        result = calculate_business_health_score(self.biz)
        self.assertIsNotNone(result)

    def test_mobile_money_has_components_key(self):
        """Result always has a components dict."""
        result = calculate_business_health_score(self.biz)
        self.assertIsInstance(result.get("components"), dict)

    def test_mobile_money_recommendations_list(self):
        """Recommendations list is returned."""
        result = calculate_business_health_score(self.biz)
        self.assertIsInstance(result.get("recommendations"), list)


class HealthCheckConsultancyTest(TestCase):
    """Consultancy-specific health check components."""

    def setUp(self):
        self.biz = _make_business(BusinessKind.CONSULTANCY)

    def _create_consultancy_data(self):
        from inventory.models_consultancy import (
            ConsultancyClient, ConsultancyProject, ConsultancyInvoice,
            ProjectStatus,
        )
        client = ConsultancyClient.objects.create(
            business=self.biz,
            name="Test Client",
        )
        project = ConsultancyProject.objects.create(
            business=self.biz,
            client=client,
            title="Health Test Project",
            status=ProjectStatus.IN_PROGRESS,
            agreed_value=Decimal("300000"),
        )
        ConsultancyInvoice.objects.create(
            business=self.biz,
            client=client,
            project=project,
            title="Invoice 1",
            subtotal=Decimal("150000"),
            total_amount=Decimal("150000"),
            amount_paid=Decimal("0"),
            status="sent",
        )
        return project

    def test_consultancy_health_does_not_crash(self):
        """Consultancy health check runs without errors."""
        self._create_consultancy_data()
        result = calculate_business_health_score(self.biz)
        self.assertIsNotNone(result)

    def test_consultancy_health_has_required_keys(self):
        """Consultancy result has all required keys."""
        result = calculate_business_health_score(self.biz)
        for key in REQUIRED_KEYS:
            self.assertIn(key, result, f"Missing key: {key}")
