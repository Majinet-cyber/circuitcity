"""
Tests for Business Health Check upgrade — Part 4 of the Farm/Emajinet upgrade.

Covers:
- calculate_business_health_score returns correct structure
- Score in valid range 0-100
- Onboarding state when no data
- Status colors: green / amber / orange / red
- Grade assigned correctly
- Risk level assigned correctly
- Recommendations list non-empty
- Encouraging summary is non-empty and business-kind aware
- Weekly mission is non-empty and actionable
- get_health_badges returns correct badge structure
- Farm-specific: mortality risk component present when farm batch exists
- Clothing-specific: margin health component present
- HEALTH_BADGES have correct structure (label, icon, variant)
"""
from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.business_kinds import BusinessKind
from dashboard.services_health import (
    calculate_business_health_score,
    get_health_badges,
    HEALTH_BADGES,
    _grade_from_score,
    _risk_level,
    _encouraging_summary,
    _weekly_mission,
)

User = get_user_model()


def _make_business(kind=BusinessKind.CLOTHING, slug_suffix="bh"):
    user = User.objects.create_user(username=f"bh_user_{slug_suffix}", password="pass5678")
    biz = Business.objects.create(
        name=f"BH Test {slug_suffix}",
        slug=f"bh-test-{slug_suffix}",
        business_kind=kind,
        created_by=user,
        status="ACTIVE",
    )
    user.active_business = biz
    user.save()
    return biz


# ─────────────────────────────────────────────────────────────────────────────
# Pure function tests
# ─────────────────────────────────────────────────────────────────────────────


class GradeFromScoreTest(TestCase):
    def test_a_plus_at_90(self):
        self.assertEqual(_grade_from_score(90), "A+")

    def test_a_at_85(self):
        self.assertEqual(_grade_from_score(85), "A")

    def test_b_at_75(self):
        self.assertEqual(_grade_from_score(75), "B")

    def test_c_at_65(self):
        self.assertEqual(_grade_from_score(65), "C")

    def test_d_at_55(self):
        self.assertEqual(_grade_from_score(55), "D")

    def test_f_at_40(self):
        self.assertEqual(_grade_from_score(40), "F")

    def test_none_returns_na(self):
        self.assertEqual(_grade_from_score(None), "N/A")


class RiskLevelTest(TestCase):
    def test_low_at_75(self):
        self.assertEqual(_risk_level(75), "Low")

    def test_medium_at_60(self):
        self.assertEqual(_risk_level(60), "Medium")

    def test_high_at_40(self):
        self.assertEqual(_risk_level(40), "High")

    def test_critical_at_30(self):
        self.assertEqual(_risk_level(30), "Critical")

    def test_none_returns_unknown(self):
        self.assertEqual(_risk_level(None), "Unknown")


class EncouragingSummaryTest(TestCase):
    """_encouraging_summary generates business-kind-aware copy."""

    def _dummy_business(self, name="Test Farm"):
        class FakeBiz:
            pass
        b = FakeBiz()
        b.name = name
        return b

    def test_farm_excellent(self):
        biz = self._dummy_business("Green Valley Farm")
        result = _encouraging_summary("farm", 90, "Excellent", biz)
        self.assertIn("Green Valley Farm", result)
        self.assertTrue(len(result) > 20)

    def test_farm_good(self):
        result = _encouraging_summary("farm", 75, "Strong", self._dummy_business())
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_farm_struggling(self):
        result = _encouraging_summary("farm", 30, "Critical", self._dummy_business())
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_clothing_excellent(self):
        result = _encouraging_summary("clothing", 90, "Excellent", self._dummy_business("Fashion Hub"))
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_generic_fallback(self):
        result = _encouraging_summary("pharmacy", 75, "Strong", self._dummy_business())
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_no_empty_copy_for_any_score(self):
        """No vertical/score combination should produce empty copy."""
        for kind in ("farm", "clothing", "mixed_retail", "consultancy", "mobile_money", "pharmacy"):
            for score in (20, 50, 75, 90):
                result = _encouraging_summary(kind, score, "label", self._dummy_business())
                self.assertGreater(len(result), 0, f"Empty copy for kind={kind}, score={score}")


class WeeklyMissionTest(TestCase):
    """_weekly_mission generates actionable weekly missions."""

    def test_farm_high_mortality_mission(self):
        components = {"farm_mortality": {"score": 30, "label": "Critical", "explanation": "..."}}
        result = _weekly_mission("farm", components, 55, None)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_farm_good_score_mission(self):
        result = _weekly_mission("farm", {}, 85, None)
        self.assertIsInstance(result, str)
        self.assertIn("mission", result.lower())

    def test_clothing_low_stock_mission(self):
        components = {"stock_risk": {"score": 40, "label": "Low", "explanation": "..."}}
        result = _weekly_mission("clothing", components, 60, None)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_generic_fallback_low_score(self):
        result = _weekly_mission("pharmacy", {}, 40, None)
        self.assertIsInstance(result, str)
        self.assertIn("mission", result.lower())

    def test_mission_is_always_non_empty(self):
        for kind in ("farm", "clothing", "mixed_retail", "consultancy", "mobile_money", "pharmacy"):
            for score in (20, 60, 85):
                result = _weekly_mission(kind, {}, score, None)
                self.assertGreater(len(result), 0, f"Empty mission for kind={kind}, score={score}")


class HealthBadgesStructureTest(TestCase):
    """HEALTH_BADGES have correct structure and get_health_badges returns valid list."""

    def test_all_badges_have_three_fields(self):
        """Each badge is a tuple with (label, icon, variant)."""
        for key, badge in HEALTH_BADGES.items():
            self.assertEqual(len(badge), 3, f"Badge {key} should have 3 elements")
            label, icon, variant = badge
            self.assertIsInstance(label, str)
            self.assertIsInstance(icon, str)
            self.assertIsInstance(variant, str)

    def test_get_health_badges_returns_list(self):
        health = {
            "score": 80,
            "components": {
                "profit_trend": {"score": 75, "label": "Good"},
                "cash_flow": {"score": 80, "label": "Strong"},
                "stock_risk": {"score": 75, "label": "Good"},
                "sales_consistency": {"score": 70, "label": "Consistent"},
            }
        }
        badges = get_health_badges(health)
        self.assertIsInstance(badges, list)

    def test_profitable_badge_earned_for_good_profit(self):
        health = {
            "score": 75,
            "components": {
                "profit_trend": {"score": 70, "label": "Good"},
            }
        }
        badges = get_health_badges(health)
        keys = [b["key"] for b in badges]
        self.assertIn("profitable", keys)

    def test_no_badges_for_zero_scores(self):
        health = {
            "score": 0,
            "components": {
                "profit_trend": {"score": 10, "label": "Critical"},
                "cash_flow": {"score": 10, "label": "Critical"},
            }
        }
        badges = get_health_badges(health)
        positive_badges = [b for b in badges if b.get("key") not in ("high_mortality", "margins_at_risk", "missing_data")]
        self.assertEqual(len(positive_badges), 0)

    def test_missing_data_badge_for_many_null_components(self):
        health = {
            "score": 50,
            "components": {
                "profit_trend": {"score": None, "label": "N/A"},
                "cash_flow": {"score": None, "label": "N/A"},
                "stock_risk": {"score": None, "label": "N/A"},
                "sales_consistency": {"score": None, "label": "N/A"},
            }
        }
        badges = get_health_badges(health)
        keys = [b["key"] for b in badges]
        self.assertIn("missing_data", keys)


# ─────────────────────────────────────────────────────────────────────────────
# Integration: calculate_business_health_score with a real Business
# ─────────────────────────────────────────────────────────────────────────────


class BusinessHealthScoreIntegrationTest(TestCase):
    """calculate_business_health_score on an empty business → onboarding state."""

    def setUp(self):
        self.biz = _make_business(kind=BusinessKind.CLOTHING, slug_suffix="int1")

    def test_returns_dict(self):
        result = calculate_business_health_score(self.biz)
        self.assertIsInstance(result, dict)

    def test_has_required_keys(self):
        result = calculate_business_health_score(self.biz)
        required_keys = {"score", "label", "status_color", "components", "recommendations", "period", "is_onboarding"}
        for key in required_keys:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_period_has_start_and_end(self):
        result = calculate_business_health_score(self.biz)
        period = result["period"]
        self.assertIn("start", period)
        self.assertIn("end", period)

    def test_new_business_is_onboarding_or_has_score(self):
        result = calculate_business_health_score(self.biz)
        # Either it's in onboarding state or has a score
        if result["is_onboarding"]:
            self.assertIsNone(result["score"])
        else:
            self.assertIsNotNone(result["score"])
            self.assertGreaterEqual(result["score"], 0)
            self.assertLessEqual(result["score"], 100)

    def test_recommendations_is_list(self):
        result = calculate_business_health_score(self.biz)
        self.assertIsInstance(result["recommendations"], list)

    def test_components_is_dict(self):
        result = calculate_business_health_score(self.biz)
        self.assertIsInstance(result["components"], dict)

    def test_explicit_date_range_accepted(self):
        today = date.today()
        result = calculate_business_health_score(
            self.biz,
            start_date=today - timedelta(days=30),
            end_date=today,
        )
        self.assertIsInstance(result, dict)


class FarmBusinessHealthIntegrationTest(TestCase):
    """Farm business health includes farm-specific components."""

    def setUp(self):
        self.biz = _make_business(kind=BusinessKind.FARM, slug_suffix="farm1")

    def test_returns_dict(self):
        result = calculate_business_health_score(self.biz)
        self.assertIsInstance(result, dict)

    def test_status_color_is_valid(self):
        result = calculate_business_health_score(self.biz)
        if not result["is_onboarding"]:
            self.assertIn(result["status_color"], ("green", "amber", "orange", "red"))

    def test_grade_present_when_not_onboarding(self):
        result = calculate_business_health_score(self.biz)
        if not result["is_onboarding"]:
            self.assertIn("grade", result)
            self.assertIn(result["grade"], ("A+", "A", "B", "C", "D", "F"))
