"""
Tests for enhanced Business Health Score:
- Farm vertical components (mortality, feed pressure, marketplace readiness)
- Clothing vertical components (margin health, stock turnover)
- Badge computation
- Gamified copy (encouraging_summary, weekly_mission)
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from tenants.models import Business
from dashboard.services_health import (
    calculate_business_health_score,
    get_health_badges,
    _farm_health_components,
    _clothing_health_components,
    _encouraging_summary,
    _weekly_mission,
)

User = get_user_model()


def _make_farm_business(slug="test-farm"):
    return Business.objects.create(
        name="Test Farm",
        slug=slug,
        business_kind="farm",
        status="ACTIVE",
    )


def _make_clothing_business(slug="test-clothing"):
    return Business.objects.create(
        name="Test Clothing",
        slug=slug,
        business_kind="clothing",
        status="ACTIVE",
    )


class EncouragingSummaryTest(TestCase):
    """_encouraging_summary returns correct catchy copy for each vertical."""

    def test_farm_excellent(self):
        biz = _make_farm_business("farm-ex")
        text = _encouraging_summary("farm", 90, "Excellent", biz)
        self.assertIn("Test Farm", text)
        self.assertIn("thriving", text.lower())

    def test_farm_medium(self):
        biz = _make_farm_business("farm-med")
        text = _encouraging_summary("farm", 70, "Good", biz)
        self.assertIn("Test Farm", text)

    def test_farm_low(self):
        biz = _make_farm_business("farm-low")
        text = _encouraging_summary("farm", 30, "Critical", biz)
        self.assertIn("Act now", text)

    def test_clothing_excellent(self):
        biz = _make_clothing_business("cloth-ex")
        text = _encouraging_summary("clothing", 90, "Excellent", biz)
        self.assertIn("Test Clothing", text)
        self.assertIn("strong", text.lower())

    def test_clothing_medium(self):
        biz = _make_clothing_business("cloth-med")
        text = _encouraging_summary("clothing", 65, "Fair", biz)
        self.assertIn("Test Clothing", text)

    def test_clothing_low(self):
        biz = _make_clothing_business("cloth-low")
        text = _encouraging_summary("clothing", 40, "At Risk", biz)
        self.assertIn("pricing", text.lower())


class WeeklyMissionTest(TestCase):
    """_weekly_mission returns farm/clothing-specific missions."""

    def test_farm_high_mortality_mission(self):
        components = {"farm_mortality": {"score": 30}}
        mission = _weekly_mission("farm", components, 60, None)
        self.assertIn("mortality", mission.lower())

    def test_farm_feed_pressure_mission(self):
        components = {"farm_feed_pressure": {"score": 40}, "farm_mortality": {"score": 80}}
        mission = _weekly_mission("farm", components, 60, None)
        self.assertIn("feed", mission.lower())

    def test_farm_good_mission(self):
        components = {"farm_mortality": {"score": 85}, "farm_feed_pressure": {"score": 80}}
        mission = _weekly_mission("farm", components, 80, None)
        self.assertIn("marketplace", mission.lower())

    def test_clothing_low_stock_mission(self):
        components = {"stock_risk": {"score": 40}}
        mission = _weekly_mission("clothing", components, 60, None)
        self.assertIn("restock", mission.lower())

    def test_clothing_margin_mission(self):
        components = {"stock_risk": {"score": 80}, "clothing_margin_health": {"score": 45}}
        mission = _weekly_mission("clothing", components, 65, None)
        self.assertIn("margin", mission.lower())


class GetHealthBadgesTest(TestCase):
    """get_health_badges derives correct badges from health result."""

    def _health_result(self, score, components=None):
        return {
            "score": score,
            "components": components or {},
        }

    def test_profitable_badge_earned(self):
        result = self._health_result(75, {"profit_trend": {"score": 75}})
        badges = get_health_badges(result)
        keys = [b["key"] for b in badges]
        self.assertIn("profitable", keys)

    def test_low_risk_badge_at_high_score(self):
        result = self._health_result(75)
        badges = get_health_badges(result)
        keys = [b["key"] for b in badges]
        self.assertIn("low_risk", keys)

    def test_no_low_risk_badge_at_low_score(self):
        result = self._health_result(45)
        badges = get_health_badges(result)
        keys = [b["key"] for b in badges]
        self.assertNotIn("low_risk", keys)

    def test_missing_data_badge_when_many_nulls(self):
        components = {
            "profit_trend": {"score": None},
            "cash_flow": {"score": None},
            "stock_risk": {"score": None},
            "sales_consistency": {"score": None},
        }
        result = self._health_result(0, components)
        badges = get_health_badges(result)
        keys = [b["key"] for b in badges]
        self.assertIn("missing_data", keys)

    def test_farm_high_mortality_badge(self):
        components = {"farm_mortality": {"score": 20}}
        result = self._health_result(40, components)
        badges = get_health_badges(result)
        keys = [b["key"] for b in badges]
        self.assertIn("high_mortality", keys)

    def test_clothing_margins_at_risk_badge(self):
        components = {"clothing_margin_health": {"score": 30}}
        result = self._health_result(55, components)
        badges = get_health_badges(result)
        keys = [b["key"] for b in badges]
        self.assertIn("margins_at_risk", keys)

    def test_records_clean_badge_no_nulls(self):
        components = {
            "profit_trend": {"score": 80},
            "cash_flow": {"score": 75},
            "stock_risk": {"score": 70},
        }
        result = self._health_result(75, components)
        badges = get_health_badges(result)
        keys = [b["key"] for b in badges]
        self.assertIn("records_clean", keys)


class CalculateBusinessHealthFarmTest(TestCase):
    """calculate_business_health_score doesn't crash for farm business."""

    def test_farm_business_health_no_crash(self):
        biz = _make_farm_business("farm-health-test")
        result = calculate_business_health_score(biz)
        self.assertIsInstance(result, dict)
        self.assertIn("score", result)
        self.assertIn("components", result)

    def test_farm_business_health_has_encouraging_summary(self):
        biz = _make_farm_business("farm-summary-test")
        result = calculate_business_health_score(biz)
        self.assertIn("encouraging_summary", result)

    def test_clothing_business_health_no_crash(self):
        biz = _make_clothing_business("clothing-health-test")
        result = calculate_business_health_score(biz)
        self.assertIsInstance(result, dict)
        self.assertIn("score", result)


class FarmHealthComponentsTest(TestCase):
    """_farm_health_components returns expected structure."""

    def test_farm_components_no_crash_empty(self):
        biz = _make_farm_business("farm-comp-test")
        today = date.today()
        result = _farm_health_components(biz, today.replace(day=1), today)
        self.assertIsInstance(result, dict)

    def test_farm_components_with_batches(self):
        """Farm components return structured data when batches exist."""
        from inventory.models_farm import FarmLivestockBatch, FarmAnimalType
        biz = _make_farm_business("farm-comp-batch")
        batch = FarmLivestockBatch.objects.create(
            business=biz,
            name="Test Batch",
            animal_type=FarmAnimalType.CATTLE,
            count_current=18,
        )
        today = date.today()
        result = _farm_health_components(biz, today.replace(day=1), today)
        # Should have mortality component
        self.assertIn("farm_mortality", result)
        mort = result["farm_mortality"]
        self.assertIn("score", mort)
        self.assertIn("label", mort)
        self.assertIn("explanation", mort)
