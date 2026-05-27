"""
Tests for Farm Intelligence upgrade — Part 1/2 of the Farm vertical.

Covers:
- compute_farm_score (farm_manager) returns FarmScoreResult with correct fields
- FarmScoreResult rank levels, badges, weaknesses
- compute_farm_score (farm_intelligence) complementary service
- compute_livestock_batch_intelligence: mortality, break-even, ROI, scores
- simulate_livestock_batch: best/expected/worst scenarios
- compute_crop_season_intelligence: harvest readiness, profitability
- compute_housing_plan: space estimates for different animal types
"""
from decimal import Decimal
from datetime import date, timedelta
from typing import Optional

from django.test import TestCase

# farm_manager.py — the version used by views
from inventory.services.farm_manager import (
    compute_farm_score,
    FarmScoreResult,
)

# farm_intelligence.py — complementary service
from inventory.services.farm_intelligence import (
    compute_livestock_batch_intelligence,
    compute_crop_season_intelligence,
    compute_housing_plan,
    simulate_livestock_batch,
    compute_farm_score as fi_compute_farm_score,
    FarmScoreResult as FIFarmScoreResult,
    LivestockBatchIntelligence,
    CropSeasonIntelligence,
    LivestockSimulationResult,
    HousingPlannerResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# Farm Score — farm_manager.py (used by dashboard view)
# ─────────────────────────────────────────────────────────────────────────────


class FarmScoreManagerTest(TestCase):
    """compute_farm_score in farm_manager.py."""

    def _score(self, **overrides):
        defaults = dict(
            net_profit=Decimal("50000"),
            total_income=Decimal("200000"),
            total_expenses=Decimal("150000"),
            livestock_risk_levels=[],
            active_crop_seasons_count=0,
            missing_yield_count=0,
            missing_sale_price_count=0,
            marketplace_listings_count=0,
            days_since_last_sale=10,
            days_since_last_expense=5,
            has_recent_livestock_event=False,
        )
        defaults.update(overrides)
        return compute_farm_score(**defaults)

    def test_returns_farm_score_result(self):
        self.assertIsInstance(self._score(), FarmScoreResult)

    def test_score_in_valid_range(self):
        result = self._score()
        self.assertGreaterEqual(result.score, 0)
        self.assertLessEqual(result.score, 100)

    def test_rank_is_non_empty_string(self):
        result = self._score()
        self.assertIsInstance(result.rank, str)
        self.assertTrue(len(result.rank) > 0)

    def test_profitable_earns_badge(self):
        result = self._score(net_profit=Decimal("100000"), total_income=Decimal("200000"))
        self.assertTrue(any("Profitable" in b or "profitable" in b.lower() for b in result.badges))

    def test_loss_generates_weakness(self):
        result = self._score(net_profit=Decimal("-10000"), total_income=Decimal("100000"))
        self.assertTrue(len(result.weaknesses) > 0)
        weakness_text = " ".join(result.weaknesses).lower()
        self.assertTrue("profit" in weakness_text or "loss" in weakness_text)

    def test_critical_mortality_generates_weakness(self):
        result = self._score(livestock_risk_levels=["critical"])
        weakness_text = " ".join(result.weaknesses).lower()
        self.assertIn("mortality", weakness_text)

    def test_no_marketplace_generates_weakness(self):
        result = self._score(active_crop_seasons_count=2, marketplace_listings_count=0)
        weakness_text = " ".join(result.weaknesses).lower()
        self.assertIn("marketplace", weakness_text)

    def test_good_farm_scores_above_50(self):
        result = self._score(
            net_profit=Decimal("200000"),
            total_income=Decimal("300000"),
            total_expenses=Decimal("100000"),
            livestock_risk_levels=[],
            active_crop_seasons_count=2,
            missing_yield_count=0,
            missing_sale_price_count=0,
            marketplace_listings_count=2,
            days_since_last_sale=3,
            days_since_last_expense=2,
        )
        self.assertGreater(result.score, 50)

    def test_xp_points_is_score_times_10(self):
        result = self._score()
        self.assertEqual(result.xp_points, result.score * 10)

    def test_next_action_is_meaningful_string(self):
        result = self._score()
        self.assertIsInstance(result.next_action, str)
        self.assertGreater(len(result.next_action), 5)

    def test_score_components_sum_equals_score(self):
        result = self._score()
        self.assertEqual(result.score, sum(result.score_components.values()))

    def test_no_data_keeps_score_low(self):
        result = self._score(
            net_profit=Decimal("0"),
            total_income=Decimal("0"),
            total_expenses=Decimal("0"),
            days_since_last_sale=None,
            days_since_last_expense=None,
        )
        self.assertLessEqual(result.score, 50)

    def test_worst_case_rank_is_struggling(self):
        result = self._score(
            net_profit=Decimal("-999999"),
            total_income=Decimal("1"),
            total_expenses=Decimal("999999"),
            livestock_risk_levels=["critical"],
            days_since_last_sale=None,
            days_since_last_expense=None,
        )
        self.assertEqual(result.rank, "Struggling Farm")


# ─────────────────────────────────────────────────────────────────────────────
# Farm Score — farm_intelligence.py (complementary)
# ─────────────────────────────────────────────────────────────────────────────


class FarmIntelligenceScoreTest(TestCase):
    """farm_intelligence.compute_farm_score."""

    def _score(self, **overrides):
        defaults = dict(
            net_profit_mwk=Decimal("80000"),
            total_income_mwk=Decimal("200000"),
            total_expenses_mwk=Decimal("120000"),
            livestock_snapshots=[],
            active_seasons_count=0,
            ledger_entries_count=15,
            recent_activity_days=5,
            marketplace_live_count=0,
            active_batches_count=0,
            crops_with_projected_yield=0,
            batches_with_sale_price=0,
            days_since_last_sale=7,
            feed_cost_mwk=Decimal("30000"),
        )
        defaults.update(overrides)
        return fi_compute_farm_score(**defaults)

    def test_returns_fi_score_result(self):
        self.assertIsInstance(self._score(), FIFarmScoreResult)

    def test_score_in_valid_range(self):
        result = self._score()
        self.assertGreaterEqual(result.score, 0)
        self.assertLessEqual(result.score, 100)

    def test_profitable_earns_badges(self):
        result = self._score(net_profit_mwk=Decimal("100000"), total_income_mwk=Decimal("200000"))
        self.assertGreater(len(result.earned_badges), 0)

    def test_xp_is_score_times_100(self):
        result = self._score()
        self.assertEqual(result.xp, result.score * 100)

    def test_rank_string(self):
        result = self._score()
        self.assertIsInstance(result.rank, str)
        self.assertTrue(len(result.rank) > 0)


# ─────────────────────────────────────────────────────────────────────────────
# Livestock Batch Intelligence
# ─────────────────────────────────────────────────────────────────────────────


class LivestockBatchIntelligenceTest(TestCase):
    """compute_livestock_batch_intelligence calculates correct metrics."""

    def _intel(self, **overrides):
        defaults = dict(
            batch_id=1,
            batch_name="Test Pig Batch",
            animal_type="pigs",
            count_current=18,
            births=0,
            deaths=2,
            purchases=20,
            sales=0,
            total_cost_mwk=Decimal("60000"),
            total_revenue_mwk=Decimal("0"),
            feed_cost_mwk=Decimal("40000"),
            expected_sale_price_mwk=Decimal("15000"),
            cost_basis_per_head_mwk=None,
        )
        defaults.update(overrides)
        return compute_livestock_batch_intelligence(**defaults)

    def test_returns_livestock_intelligence_object(self):
        self.assertIsInstance(self._intel(), LivestockBatchIntelligence)

    def test_mortality_rate_calculated_from_deaths_and_purchases(self):
        """Mortality = deaths / (births + purchases) × 100"""
        result = self._intel(purchases=20, births=0, deaths=4)
        self.assertIsNotNone(result.mortality_rate)
        self.assertAlmostEqual(float(result.mortality_rate), 20.0, places=0)

    def test_low_mortality_good_risk(self):
        result = self._intel(purchases=100, births=0, deaths=1)
        self.assertEqual(result.mortality_risk, "good")

    def test_high_mortality_high_risk(self):
        result = self._intel(purchases=100, births=0, deaths=15)
        self.assertIn(result.mortality_risk, ("high_risk", "critical"))

    def test_critical_mortality_threshold_20_pct(self):
        result = self._intel(purchases=100, births=0, deaths=25)
        self.assertEqual(result.mortality_risk, "critical")

    def test_break_even_price_is_cost_over_current_count(self):
        result = self._intel(count_current=18, total_cost_mwk=Decimal("90000"))
        self.assertIsNotNone(result.break_even_price_mwk)
        self.assertAlmostEqual(float(result.break_even_price_mwk), 5000.0, places=0)

    def test_zero_count_break_even_is_none(self):
        result = self._intel(count_current=0)
        self.assertIsNone(result.break_even_price_mwk)

    def test_net_profit_negative_with_no_revenue(self):
        result = self._intel(total_cost_mwk=Decimal("60000"), total_revenue_mwk=Decimal("0"))
        self.assertLess(result.net_profit_mwk, Decimal("0"))

    def test_net_profit_positive_when_revenue_exceeds_cost(self):
        result = self._intel(
            total_cost_mwk=Decimal("60000"),
            total_revenue_mwk=Decimal("120000"),
        )
        self.assertGreater(result.net_profit_mwk, Decimal("0"))

    def test_roi_pct_correct(self):
        result = self._intel(
            purchases=20, births=0, sales=20,
            total_cost_mwk=Decimal("50000"),
            total_revenue_mwk=Decimal("75000"),
        )
        self.assertIsNotNone(result.roi_pct)
        self.assertAlmostEqual(float(result.roi_pct), 50.0, places=0)

    def test_health_score_in_range(self):
        result = self._intel()
        self.assertGreaterEqual(result.health_score, 0)
        self.assertLessEqual(result.health_score, 100)

    def test_profit_score_in_range(self):
        result = self._intel()
        self.assertGreaterEqual(result.profit_score, 0)
        self.assertLessEqual(result.profit_score, 100)

    def test_feed_cost_stored(self):
        result = self._intel(feed_cost_mwk=Decimal("40000"))
        self.assertEqual(result.feed_cost_mwk, Decimal("40000"))

    def test_recommendation_non_empty_string(self):
        result = self._intel()
        self.assertIsInstance(result.recommendation, str)
        self.assertGreater(len(result.recommendation), 0)

    def test_earned_badges_list(self):
        result = self._intel()
        self.assertIsInstance(result.earned_badges, list)

    def test_low_mortality_earns_badge(self):
        result = self._intel(purchases=100, births=0, deaths=0)
        # earned_badges contains display labels like "Low Mortality"
        badge_text = " ".join(result.earned_badges).lower()
        self.assertIn("low mortality", badge_text)


# ─────────────────────────────────────────────────────────────────────────────
# Livestock Simulation (best/expected/worst)
# ─────────────────────────────────────────────────────────────────────────────


class LivestockSimulationTest(TestCase):
    """simulate_livestock_batch projects best/expected/worst scenarios."""

    def _sim(self, **overrides):
        defaults = dict(
            count_current=20,
            expected_sale_price_mwk=Decimal("10000"),
            total_cost_mwk=Decimal("80000"),
        )
        defaults.update(overrides)
        return simulate_livestock_batch(**defaults)

    def test_returns_simulation_result(self):
        self.assertIsInstance(self._sim(), LivestockSimulationResult)

    def test_expected_revenue_is_count_times_price(self):
        # Expected mortality 5%, so 20 × 0.95 = 19 animals, 19 × 10000 = 190000
        result = self._sim(count_current=20, expected_sale_price_mwk=Decimal("10000"))
        self.assertAlmostEqual(float(result.expected_revenue), 190000.0, delta=5000.0)

    def test_expected_profit_formula(self):
        result = self._sim()
        self.assertEqual(result.expected_profit, result.expected_revenue - result.total_cost)

    def test_best_profit_gte_expected_gte_worst(self):
        result = self._sim()
        self.assertGreaterEqual(result.best_profit, result.expected_profit)
        self.assertGreaterEqual(result.expected_profit, result.worst_profit)

    def test_roi_positive_when_profitable(self):
        result = self._sim(
            expected_sale_price_mwk=Decimal("20000"),
            total_cost_mwk=Decimal("50000"),
        )
        self.assertGreater(result.expected_roi, Decimal("0"))

    def test_roi_negative_when_price_below_cost(self):
        result = self._sim(
            count_current=5,
            expected_sale_price_mwk=Decimal("100"),  # way below break-even
            total_cost_mwk=Decimal("80000"),
        )
        self.assertLess(result.expected_roi, Decimal("0"))

    def test_break_even_price_is_cost_over_count(self):
        result = self._sim(count_current=20, total_cost_mwk=Decimal("100000"))
        self.assertIsNotNone(result.break_even_price)
        self.assertAlmostEqual(float(result.break_even_price), 5000.0, places=0)

    def test_zero_count_handles_gracefully(self):
        result = self._sim(count_current=0)
        self.assertIsNotNone(result)
        self.assertEqual(result.expected_revenue, Decimal("0"))

    def test_summary_is_non_empty_string(self):
        result = self._sim()
        self.assertIsInstance(result.summary, str)
        self.assertGreater(len(result.summary), 0)

    def test_custom_mortality_parameters(self):
        result = self._sim(
            mortality_pct_best=Decimal("0"),
            mortality_pct_expected=Decimal("10"),
            mortality_pct_worst=Decimal("30"),
        )
        self.assertGreater(result.best_profit, result.worst_profit)


# ─────────────────────────────────────────────────────────────────────────────
# Crop Season Intelligence
# ─────────────────────────────────────────────────────────────────────────────


class CropSeasonIntelligenceTest(TestCase):
    """compute_crop_season_intelligence evaluates crop health and forecasts."""

    def _ci(self, **overrides):
        today = date.today()
        defaults = dict(
            season_id=1,
            season_name="Maize Season 1",
            crop_type="maize",
            status="active",
            area_value=Decimal("2.0"),
            area_unit="ha",
            projected_yield=Decimal("5000"),
            actual_yield=None,
            yield_unit="kg",
            projected_price_per_unit=Decimal("40"),
            actual_price_per_unit=None,
            actual_costs=Decimal("80000"),
            start_date=today - timedelta(days=60),
            end_date=today + timedelta(days=30),
            today=today,
        )
        defaults.update(overrides)
        return compute_crop_season_intelligence(**defaults)

    def test_returns_crop_intelligence(self):
        self.assertIsInstance(self._ci(), CropSeasonIntelligence)

    def test_harvest_approaching_when_30_days_away(self):
        today = date.today()
        result = self._ci(end_date=today + timedelta(days=20))
        self.assertIn(result.harvest_readiness, ("approaching", "ready"))

    def test_harvest_not_due_far_future(self):
        today = date.today()
        result = self._ci(end_date=today + timedelta(days=120))
        self.assertEqual(result.harvest_readiness, "not_due")

    def test_harvest_overdue_past_end_date(self):
        today = date.today()
        result = self._ci(end_date=today - timedelta(days=14))
        self.assertEqual(result.harvest_readiness, "overdue")

    def test_break_even_price(self):
        """break_even = actual_costs / projected_yield"""
        result = self._ci(
            actual_costs=Decimal("100000"),
            projected_yield=Decimal("500"),
        )
        self.assertIsNotNone(result.break_even_price)
        self.assertAlmostEqual(float(result.break_even_price), 200.0, places=0)

    def test_profitability_profitable_when_income_exceeds_cost(self):
        """projected_income = 5000 kg × MWK 40 = 200,000; costs = 80,000 → profitable"""
        result = self._ci()
        self.assertEqual(result.profitability_flag, "profitable")

    def test_profitability_loss_when_cost_exceeds_income(self):
        result = self._ci(
            projected_yield=Decimal("100"),
            projected_price_per_unit=Decimal("5"),  # income = 500 << cost 80000
        )
        self.assertEqual(result.profitability_flag, "loss")

    def test_yield_per_area(self):
        """yield_per_area = projected_yield / area"""
        result = self._ci(projected_yield=Decimal("4000"), area_value=Decimal("2.0"))
        self.assertIsNotNone(result.yield_per_area)
        self.assertAlmostEqual(float(result.yield_per_area), 2000.0, places=0)

    def test_projected_income_calculated(self):
        """projected_income = projected_yield × projected_price_per_unit"""
        result = self._ci(projected_yield=Decimal("5000"), projected_price_per_unit=Decimal("40"))
        self.assertIsNotNone(result.projected_income)
        self.assertEqual(result.projected_income, Decimal("200000"))

    def test_recommendation_non_empty(self):
        result = self._ci()
        self.assertIsInstance(result.recommendation, str)
        self.assertGreater(len(result.recommendation), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Housing Planner
# ─────────────────────────────────────────────────────────────────────────────


class HousingPlannerTest(TestCase):
    """compute_housing_plan gives space/cost estimates per animal type."""

    def test_pigs_space_estimate(self):
        result = compute_housing_plan(animal_type="pigs", animal_count=20)
        self.assertIsInstance(result, HousingPlannerResult)
        self.assertGreater(result.floor_space_m2, 0)

    def test_chickens_housing_type(self):
        result = compute_housing_plan(animal_type="chickens", animal_count=100)
        self.assertIsInstance(result.housing_type, str)
        self.assertGreater(len(result.housing_type), 0)

    def test_cattle_biosecurity_checklist_non_empty(self):
        result = compute_housing_plan(animal_type="cattle", animal_count=10)
        self.assertIsInstance(result.biosecurity_checklist, list)
        self.assertGreater(len(result.biosecurity_checklist), 0)

    def test_cattle_hygiene_checklist_non_empty(self):
        result = compute_housing_plan(animal_type="cattle", animal_count=10)
        self.assertIsInstance(result.hygiene_checklist, list)
        self.assertGreater(len(result.hygiene_checklist), 0)

    def test_zero_count_gives_zero_space(self):
        result = compute_housing_plan(animal_type="goats", animal_count=0)
        self.assertIsNotNone(result)
        self.assertEqual(result.floor_space_m2, 0)

    def test_large_flock_scales_space(self):
        small = compute_housing_plan(animal_type="chickens", animal_count=10)
        large = compute_housing_plan(animal_type="chickens", animal_count=100)
        self.assertGreater(large.floor_space_m2, small.floor_space_m2)

    def test_three_d_ready_is_bool(self):
        result = compute_housing_plan(animal_type="pigs", animal_count=5)
        self.assertIsInstance(result.three_d_ready, bool)

    def test_layout_notes_non_empty(self):
        result = compute_housing_plan(animal_type="pigs", animal_count=10)
        self.assertIsInstance(result.layout_notes, str)
        self.assertGreater(len(result.layout_notes), 0)

    def test_ventilation_recommendation_non_empty(self):
        result = compute_housing_plan(animal_type="pigs", animal_count=10)
        self.assertIsInstance(result.ventilation_recommendation, str)
        self.assertGreater(len(result.ventilation_recommendation), 0)

    def test_feed_storage_scaled_by_count(self):
        small = compute_housing_plan(animal_type="pigs", animal_count=5)
        large = compute_housing_plan(animal_type="pigs", animal_count=50)
        self.assertGreater(large.feed_storage_kg, small.feed_storage_kg)
