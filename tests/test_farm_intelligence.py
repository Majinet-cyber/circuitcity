"""
Tests for Farm Intelligence Service functions (Phase 1 upgrade).

All functions under test are pure (no DB access) — fast, no ORM required.
Uses pytest style (matching the rest of the test suite).
"""
from __future__ import annotations

import pytest  # noqa: F401  (needed for pytest collection)
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional


# ---------------------------------------------------------------------------
# Helpers to build typed dicts without importing from the full Django stack
# ---------------------------------------------------------------------------

def _batch(
    id=1,
    name="Test Batch",
    animal_type="pigs",
    count_current=10,
    valuation_enabled=False,
    avg_weight_kg=None,
    price_per_kg_mwk=None,
    price_per_animal_mwk=None,
    expected_sale_price_mwk=None,
) -> dict:
    return {
        "id": id,
        "name": name,
        "animal_type": animal_type,
        "count_current": count_current,
        "valuation_enabled": valuation_enabled,
        "avg_weight_kg": avg_weight_kg,
        "price_per_kg_mwk": price_per_kg_mwk,
        "price_per_animal_mwk": price_per_animal_mwk,
        "expected_sale_price_mwk": expected_sale_price_mwk,
    }


def _event(batch_id=1, event_type="purchase", count=10, date_val=None, unit_price_mwk=None) -> dict:
    return {
        "id": 1,
        "batch_id": batch_id,
        "event_type": event_type,
        "date": date_val or date(2026, 1, 1),
        "count": count,
        "unit_price_mwk": unit_price_mwk,
    }


def _ledger(entry_type="expense", category="feed", amount=10000, enterprise_type="pigs",
            crop_season_id=None, livestock_batch_id=None) -> dict:
    return {
        "id": 1,
        "date": date(2026, 5, 1),
        "entry_type": entry_type,
        "enterprise_type": enterprise_type,
        "category": category,
        "amount_mwk": Decimal(str(amount)),
        "quantity": None,
        "unit": "item",
        "crop_season_id": crop_season_id,
        "livestock_batch_id": livestock_batch_id,
    }


def _season(
    id=1,
    crop_type="maize",
    name="Maize 2026",
    start_date=None,
    end_date=None,
    area_value="2.0",
    area_unit="acre",
    projected_yield=None,
    projected_price=None,
    actual_yield=None,
    actual_price=None,
    status="active",
) -> dict:
    return {
        "id": id,
        "crop_type": crop_type,
        "name": name,
        "start_date": start_date or date(2026, 1, 1),
        "end_date": end_date,
        "area_value": Decimal(area_value),
        "area_unit": area_unit,
        "projected_yield": Decimal(str(projected_yield)) if projected_yield else None,
        "yield_unit": "bag",
        "projected_price_per_unit_mwk": Decimal(str(projected_price)) if projected_price else None,
        "actual_yield": Decimal(str(actual_yield)) if actual_yield else None,
        "actual_price_per_unit_mwk": Decimal(str(actual_price)) if actual_price else None,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Import target functions
# ---------------------------------------------------------------------------

from inventory.services.farm_manager import (
    CategorizedAlerts,
    CropIntelligenceResult,
    LivestockIntelligenceResult,
    LivestockSimulationResult,
    FarmScoreResult,
    compute_categorized_alerts,
    compute_crop_intelligence,
    compute_farm_score,
    compute_livestock_intelligence,
    compute_livestock_marketplace_readiness,
    compute_livestock_simulation,
    compute_mortality_risk_level,
    generate_farm_recommendations,
)


# ===========================================================================
# 1. MORTALITY RISK LEVEL
# ===========================================================================

class TestMortalityRiskLevel:

    def test_none_returns_unknown(self):
        assert compute_mortality_risk_level(None) == "unknown"

    def test_zero_returns_good(self):
        assert compute_mortality_risk_level(Decimal("0")) == "good"

    def test_below_5_is_good(self):
        assert compute_mortality_risk_level(Decimal("4.9")) == "good"

    def test_exactly_5_is_watch(self):
        assert compute_mortality_risk_level(Decimal("5")) == "watch"

    def test_7_is_watch(self):
        assert compute_mortality_risk_level(Decimal("7")) == "watch"

    def test_exactly_10_is_high_risk(self):
        assert compute_mortality_risk_level(Decimal("10")) == "high_risk"

    def test_15_is_high_risk(self):
        assert compute_mortality_risk_level(Decimal("15")) == "high_risk"

    def test_exactly_20_is_critical(self):
        assert compute_mortality_risk_level(Decimal("20")) == "critical"

    def test_50_is_critical(self):
        assert compute_mortality_risk_level(Decimal("50")) == "critical"


# ===========================================================================
# 2. LIVESTOCK INTELLIGENCE
# ===========================================================================

TODAY = date(2026, 5, 26)
CREATED = date(2026, 1, 1)


class TestLivestockIntelligence:

    def test_basic_mortality_rate(self):
        batch = _batch(id=1, count_current=8)
        events = [
            _event(1, "purchase", 10, date(2026, 1, 5)),
            _event(1, "death", 2, date(2026, 2, 1)),
        ]
        result = compute_livestock_intelligence(batch, events, [], CREATED, TODAY)
        assert abs(float(result.mortality_rate) - 20.0) < 0.1
        assert result.mortality_risk_level == "critical"

    def test_no_events_unknown_risk(self):
        batch = _batch(id=1)
        result = compute_livestock_intelligence(batch, [], [], CREATED, TODAY)
        assert result.mortality_rate is None
        assert result.mortality_risk_level == "unknown"

    def test_count_current_calculated_from_events(self):
        batch = _batch(id=1, count_current=0)
        events = [
            _event(1, "purchase", 20, date(2026, 1, 5)),
            _event(1, "death", 3, date(2026, 2, 1)),
            _event(1, "sale", 5, date(2026, 3, 1)),
        ]
        result = compute_livestock_intelligence(batch, events, [], CREATED, TODAY)
        assert result.count_current == 12  # 20 - 3 - 5

    def test_total_cost_from_ledger(self):
        batch = _batch(id=1)
        events = [_event(1, "purchase", 10)]
        ledger = [
            _ledger("expense", "feed", 50000),
            _ledger("expense", "vet", 15000),
        ]
        result = compute_livestock_intelligence(batch, events, ledger, CREATED, TODAY)
        assert result.total_cost_mwk == Decimal("65000")
        assert result.feed_cost_mwk == Decimal("50000")
        assert result.medicine_cost_mwk == Decimal("15000")

    def test_net_profit_positive(self):
        batch = _batch(id=1)
        events = [_event(1, "purchase", 10)]
        ledger = [
            _ledger("expense", "feed", 20000),
            _ledger("sale", "sale", 50000),
        ]
        result = compute_livestock_intelligence(batch, events, ledger, CREATED, TODAY)
        assert result.net_profit_mwk == Decimal("30000")

    def test_break_even_price(self):
        batch = _batch(id=1)
        events = [_event(1, "purchase", 10)]
        ledger = [_ledger("expense", "feed", 50000)]
        result = compute_livestock_intelligence(batch, events, ledger, CREATED, TODAY)
        # 10 remaining after 10 purchased, 0 deaths → count = 10
        # break_even = 50000 / 10 = 5000
        assert result.break_even_price_mwk == Decimal("5000")

    def test_days_in_cycle(self):
        batch = _batch(id=1)
        created = date(2026, 1, 1)
        today = date(2026, 5, 26)
        result = compute_livestock_intelligence(batch, [], [], created, today)
        assert result.days_in_cycle == (today - created).days

    def test_survival_rate_complement_of_mortality(self):
        batch = _batch(id=1)
        events = [
            _event(1, "purchase", 100),
            _event(1, "death", 10),
        ]
        result = compute_livestock_intelligence(batch, events, [], CREATED, TODAY)
        assert abs(float(result.survival_rate) - 90.0) < 0.1

    def test_health_score_drops_with_critical_mortality(self):
        batch = _batch(id=1)
        events = [
            _event(1, "purchase", 10),
            _event(1, "death", 5),
        ]
        result = compute_livestock_intelligence(batch, events, [], CREATED, TODAY)
        # mortality = 50% → critical → health score should be <= 60
        assert result.batch_health_score <= 60


# ===========================================================================
# 3. LIVESTOCK SIMULATION
# ===========================================================================

def _base_sim_batch():
    return _batch(id=1, name="Pigs A", count_current=14, price_per_animal_mwk=Decimal("15000"))


class TestLivestockSimulation:

    def test_expected_revenue(self):
        result = compute_livestock_simulation(_base_sim_batch(), Decimal("100000"), Decimal("15000"), 14)
        assert result.expected_case_revenue == Decimal("210000")

    def test_expected_profit(self):
        result = compute_livestock_simulation(_base_sim_batch(), Decimal("100000"), Decimal("15000"), 14)
        assert result.expected_case_profit == Decimal("110000")  # 210000 - 100000

    def test_best_case_higher_than_expected(self):
        result = compute_livestock_simulation(_base_sim_batch(), Decimal("100000"), Decimal("15000"), 14)
        assert result.best_case_profit > result.expected_case_profit

    def test_worst_case_lower_than_expected(self):
        result = compute_livestock_simulation(_base_sim_batch(), Decimal("100000"), Decimal("15000"), 14)
        assert result.worst_case_profit < result.expected_case_profit

    def test_break_even_price(self):
        result = compute_livestock_simulation(_base_sim_batch(), Decimal("140000"), Decimal("15000"), 14)
        assert result.break_even_price == Decimal("10000")  # 140000 / 14

    def test_roi_positive_when_profit_positive(self):
        result = compute_livestock_simulation(_base_sim_batch(), Decimal("100000"), Decimal("15000"), 14)
        assert result.roi_pct is not None
        assert result.roi_pct > Decimal("0")

    def test_zero_count_zero_revenue(self):
        batch = _batch(id=1, count_current=0)
        result = compute_livestock_simulation(batch, Decimal("0"), Decimal("15000"), 0)
        assert result.expected_case_revenue == Decimal("0")
        assert result.expected_case_profit == Decimal("0")

    def test_summary_text_generated(self):
        result = compute_livestock_simulation(_base_sim_batch(), Decimal("100000"), Decimal("15000"), 14)
        assert "14" in result.summary
        assert "MWK" in result.summary

    def test_no_price_returns_placeholder_summary(self):
        batch = _batch(id=1, count_current=10)
        result = compute_livestock_simulation(batch, Decimal("50000"), None, 10)
        assert "Set a sale price" in result.summary


# ===========================================================================
# 4. CROP INTELLIGENCE
# ===========================================================================

class TestCropIntelligence:

    def test_harvest_readiness_ready_when_within_14_days(self):
        today = date(2026, 5, 26)
        season = _season(end_date=date(2026, 6, 5), status="active")
        result = compute_crop_intelligence(season, [], today)
        assert result.harvest_readiness == "ready"

    def test_harvest_readiness_near_when_within_30_days(self):
        today = date(2026, 5, 26)
        season = _season(end_date=date(2026, 6, 20), status="active")
        result = compute_crop_intelligence(season, [], today)
        assert result.harvest_readiness == "near"

    def test_harvest_readiness_growing_when_no_end_date(self):
        today = date(2026, 5, 26)
        season = _season(status="active")
        result = compute_crop_intelligence(season, [], today)
        assert result.harvest_readiness == "growing"

    def test_harvest_readiness_harvested_for_closed_status(self):
        today = date(2026, 5, 26)
        season = _season(status="harvested")
        result = compute_crop_intelligence(season, [], today)
        assert result.harvest_readiness == "harvested"

    def test_input_cost_from_ledger(self):
        today = date(2026, 5, 26)
        season = _season()
        ledger = [
            _ledger("expense", "fertiliser", 30000),
            _ledger("expense", "labour", 20000),
        ]
        result = compute_crop_intelligence(season, ledger, today)
        assert result.input_cost_mwk == Decimal("50000")

    def test_input_cost_per_acre(self):
        today = date(2026, 5, 26)
        season = _season(area_value="2.0")
        ledger = [_ledger("expense", "fertiliser", 40000)]
        result = compute_crop_intelligence(season, ledger, today)
        assert result.input_cost_per_acre == Decimal("20000")

    def test_projected_income_when_yield_and_price_set(self):
        today = date(2026, 5, 26)
        season = _season(projected_yield="100", projected_price="5000")
        result = compute_crop_intelligence(season, [], today)
        assert result.projected_income_mwk == Decimal("500000")

    def test_projected_profit(self):
        today = date(2026, 5, 26)
        season = _season(projected_yield="100", projected_price="5000")
        ledger = [_ledger("expense", "fertiliser", 100000)]
        result = compute_crop_intelligence(season, ledger, today)
        assert result.projected_profit_mwk == Decimal("400000")

    def test_break_even_price(self):
        today = date(2026, 5, 26)
        season = _season(projected_yield="100", area_value="2.0")
        ledger = [_ledger("expense", "fertiliser", 50000)]
        result = compute_crop_intelligence(season, ledger, today)
        assert result.break_even_price == Decimal("500")  # 50000 / 100

    def test_yield_per_acre(self):
        today = date(2026, 5, 26)
        season = _season(projected_yield="80", area_value="4.0")
        result = compute_crop_intelligence(season, [], today)
        assert result.yield_per_acre == Decimal("20")  # 80 / 4

    def test_risk_level_risky_when_cost_exceeds_income(self):
        today = date(2026, 5, 26)
        season = _season(projected_yield="10", projected_price="1000")  # income = 10000
        ledger = [_ledger("expense", "fertiliser", 50000)]              # cost = 50000
        result = compute_crop_intelligence(season, ledger, today)
        assert result.risk_level == "risky"

    def test_risk_level_good_when_income_much_higher_than_cost(self):
        today = date(2026, 5, 26)
        season = _season(projected_yield="100", projected_price="5000")  # income = 500000
        ledger = [_ledger("expense", "fertiliser", 50000)]               # cost = 50000
        result = compute_crop_intelligence(season, ledger, today)
        assert result.risk_level == "good"

    def test_recommendation_generated_for_missing_yield(self):
        today = date(2026, 5, 26)
        season = _season(status="active")   # no projected_yield
        result = compute_crop_intelligence(season, [], today)
        assert any("yield" in r.lower() for r in result.recommendations)

    def test_days_to_harvest_correct(self):
        today = date(2026, 5, 26)
        end_date = date(2026, 6, 5)
        season = _season(end_date=end_date, status="active")
        result = compute_crop_intelligence(season, [], today)
        assert result.days_to_harvest == (end_date - today).days


# ===========================================================================
# 5. EGG PRODUCTION SUMMARY
# ===========================================================================

def _run_egg(daily_records, total_eggs=None, today=None, total_cost=None, total_sales=None):
    from inventory.services.farm_manager import compute_egg_summary
    total_eggs = total_eggs or sum(r.get("eggs_collected", 0) for r in daily_records)
    return compute_egg_summary(
        batch_id=1,
        batch_name="Layers A",
        initial_birds=100,
        current_birds=100,
        total_eggs=total_eggs,
        total_feed_kg=Decimal("50"),
        total_cost=total_cost or Decimal("0"),
        total_sales=total_sales or Decimal("0"),
        daily_records=daily_records,
        today=today or date(2026, 5, 26),
    )


class TestEggProductionSummary:

    def test_eggs_today(self):
        today = date(2026, 5, 26)
        records = [{"date": today, "eggs_collected": 90}]
        result = _run_egg(records, today=today)
        assert result.eggs_today == 90

    def test_eggs_this_week(self):
        today = date(2026, 5, 26)
        records = [{"date": today - timedelta(days=i), "eggs_collected": 80} for i in range(5)]
        result = _run_egg(records, today=today)
        assert result.eggs_this_week == 400

    def test_eggs_in_stock(self):
        today = date(2026, 5, 26)
        records = [{"date": today, "eggs_collected": 100, "eggs_sold": 30}]
        result = _run_egg(records, total_eggs=100, today=today)
        assert result.eggs_in_stock == 70  # 100 - 30 - 0 spoiled

    def test_feed_cost_per_egg(self):
        today = date(2026, 5, 26)
        records = [{"date": today, "eggs_collected": 100}]
        result = _run_egg(records, total_eggs=100, today=today, total_cost=Decimal("10000"))
        assert result.feed_cost_per_egg == Decimal("100")  # 10000 / 100

    def test_spoilage_rate(self):
        today = date(2026, 5, 26)
        records = [{"date": today, "eggs_collected": 100, "eggs_spoiled": 10}]
        result = _run_egg(records, total_eggs=100, today=today)
        assert result.spoilage_rate == Decimal("10")  # 10/100 * 100

    def test_trend_up_when_more_eggs_this_week(self):
        today = date(2026, 5, 26)
        records = (
            [{"date": today - timedelta(days=i), "eggs_collected": 100} for i in range(5)]
            + [{"date": today - timedelta(days=7 + i), "eggs_collected": 50} for i in range(5)]
        )
        result = _run_egg(records, today=today)
        assert result.trend == "up"


# ===========================================================================
# 6. FARM SCORE
# ===========================================================================

def _score_kwargs(**overrides):
    kwargs = dict(
        net_profit=Decimal("100000"),
        total_income=Decimal("500000"),
        total_expenses=Decimal("400000"),
        livestock_risk_levels=["good"],
        active_crop_seasons_count=2,
        missing_yield_count=0,
        missing_sale_price_count=0,
        marketplace_listings_count=1,
        days_since_last_sale=5,
        days_since_last_expense=3,
        has_recent_livestock_event=True,
    )
    kwargs.update(overrides)
    return kwargs


class TestFarmScore:

    def test_score_in_range(self):
        result = compute_farm_score(**_score_kwargs())
        assert 0 <= result.score <= 100

    def test_profitable_farm_badge_earned(self):
        result = compute_farm_score(**_score_kwargs(net_profit=Decimal("50000")))
        assert "Profitable Farm" in result.badges

    def test_negative_profit_no_profitable_badge(self):
        result = compute_farm_score(**_score_kwargs(net_profit=Decimal("-5000")))
        assert "Profitable Farm" not in result.badges

    def test_critical_mortality_lowers_score(self):
        good_result = compute_farm_score(**_score_kwargs(livestock_risk_levels=["good"]))
        critical_result = compute_farm_score(**_score_kwargs(livestock_risk_levels=["critical"]))
        assert good_result.score > critical_result.score

    def test_rank_struggling_when_score_very_low(self):
        result = compute_farm_score(**_score_kwargs(
            net_profit=Decimal("-100000"),
            livestock_risk_levels=["critical", "critical"],
            days_since_last_sale=60,
            days_since_last_expense=60,
            marketplace_listings_count=0,
            missing_yield_count=5,
            missing_sale_price_count=5,
        ))
        assert result.rank in ["Struggling Farm", "Seedling Farm"]

    def test_rank_boundaries_are_valid(self):
        from inventory.services.farm_manager import FARM_RANKS
        for threshold, label in FARM_RANKS:
            assert isinstance(threshold, int)
            assert isinstance(label, str)

    def test_low_mortality_badge_earned(self):
        result = compute_farm_score(**_score_kwargs(livestock_risk_levels=["good", "watch"]))
        assert "Low Mortality" in result.badges

    def test_marketplace_ready_badge_earned(self):
        result = compute_farm_score(**_score_kwargs(marketplace_listings_count=2))
        assert "Marketplace Ready" in result.badges

    def test_no_marketplace_adds_weakness(self):
        result = compute_farm_score(**_score_kwargs(marketplace_listings_count=0))
        assert any("marketplace" in w.lower() for w in result.weaknesses)

    def test_xp_equals_score_times_10(self):
        result = compute_farm_score(**_score_kwargs())
        assert result.xp_points == result.score * 10

    def test_next_action_generated(self):
        result = compute_farm_score(**_score_kwargs())
        assert isinstance(result.next_action, str)
        assert len(result.next_action) > 5

    def test_clean_records_badge_with_recent_activity(self):
        result = compute_farm_score(**_score_kwargs(days_since_last_sale=3, days_since_last_expense=5))
        assert "Clean Records" in result.badges


# ===========================================================================
# 7. MARKETPLACE READINESS
# ===========================================================================

class TestMarketplaceReadiness:

    def test_ready_when_stock_and_price(self):
        result = compute_livestock_marketplace_readiness(10, Decimal("15000"), None, False, "Some description here.", False)
        assert result.is_ready

    def test_not_ready_when_no_stock(self):
        result = compute_livestock_marketplace_readiness(0, Decimal("15000"), None, True, "", False)
        assert not result.is_ready
        assert "No animals in stock" in result.missing_items

    def test_not_ready_when_no_price(self):
        result = compute_livestock_marketplace_readiness(10, None, None, True, "", False)
        assert not result.is_ready
        assert "No asking price set" in result.missing_items

    def test_not_ready_when_already_published(self):
        result = compute_livestock_marketplace_readiness(10, Decimal("15000"), None, True, "Full description here.", True)
        assert not result.is_ready

    def test_score_max_when_all_present(self):
        result = compute_livestock_marketplace_readiness(10, Decimal("15000"), None, True, "Healthy pigs ready for sale.", False)
        assert result.readiness_score == 100

    def test_score_40_when_only_stock(self):
        result = compute_livestock_marketplace_readiness(10, None, None, False, "", False)
        assert result.readiness_score == 40


# ===========================================================================
# 8. RECOMMENDATION GENERATOR
# ===========================================================================

class TestRecommendationGenerator:

    def _make_intel(self, mortality_risk="good", has_asking_price=True, has_stock=True,
                    deaths=0, mortality_rate=Decimal("3"), net_profit=Decimal("10000"),
                    batch_name="Test Batch"):
        return LivestockIntelligenceResult(
            batch_id=1,
            batch_name=batch_name,
            animal_type="pigs",
            count_current=10 if has_stock else 0,
            births_total=0,
            deaths_total=deaths,
            purchases_total=10,
            sales_total=0,
            mortality_rate=mortality_rate,
            survival_rate=Decimal("100") - mortality_rate if mortality_rate else None,
            mortality_risk_level=mortality_risk,
            feed_cost_mwk=Decimal("0"),
            medicine_cost_mwk=Decimal("0"),
            labour_cost_mwk=Decimal("0"),
            other_cost_mwk=Decimal("0"),
            total_cost_mwk=Decimal("0"),
            revenue_mwk=Decimal("0"),
            net_profit_mwk=net_profit,
            profit_per_animal_mwk=None,
            cost_per_surviving_animal_mwk=None,
            break_even_price_mwk=None,
            batch_health_score=80,
            days_in_cycle=30,
            estimated_value=None,
            has_asking_price=has_asking_price,
            has_stock=has_stock,
            recommendations=[],
        )

    def _make_crop(self, harvest_readiness="growing", projected_income=None, status="active",
                   season_name="Maize 2026", days_to_harvest=None):
        return CropIntelligenceResult(
            season_id=1,
            season_name=season_name,
            crop_type="maize",
            area_value=Decimal("2"),
            area_unit="acre",
            status=status,
            input_cost_mwk=Decimal("0"),
            input_cost_per_acre=None,
            projected_income_mwk=projected_income,
            projected_profit_mwk=None,
            yield_per_acre=None,
            break_even_price=None,
            actual_income_mwk=None,
            actual_profit_mwk=None,
            harvest_readiness=harvest_readiness,
            risk_level="unknown",
            days_to_harvest=days_to_harvest,
            recommendations=[],
        )

    def test_critical_mortality_is_first(self):
        intel = self._make_intel(mortality_risk="critical", mortality_rate=Decimal("30"), deaths=30)
        recs = generate_farm_recommendations(
            net_profit=Decimal("10000"),
            livestock_intelligences=[intel],
            crop_intelligences=[],
            has_marketplace_listings=True,
            has_poultry=False,
            days_since_egg_record=None,
            days_since_last_sale=3,
        )
        assert len(recs) > 0
        assert "critical" in recs[0].lower()

    def test_missing_sale_price_generates_recommendation(self):
        intel = self._make_intel(has_asking_price=False, has_stock=True)
        recs = generate_farm_recommendations(
            net_profit=Decimal("10000"),
            livestock_intelligences=[intel],
            crop_intelligences=[],
            has_marketplace_listings=True,
            has_poultry=False,
            days_since_egg_record=None,
            days_since_last_sale=3,
        )
        assert any("sale price" in r.lower() for r in recs)

    def test_ready_harvest_generates_recommendation(self):
        crop = self._make_crop(harvest_readiness="ready", days_to_harvest=5)
        recs = generate_farm_recommendations(
            net_profit=Decimal("10000"),
            livestock_intelligences=[],
            crop_intelligences=[crop],
            has_marketplace_listings=True,
            has_poultry=False,
            days_since_egg_record=None,
            days_since_last_sale=5,
        )
        assert any("harvest" in r.lower() for r in recs)

    def test_no_marketplace_generates_recommendation(self):
        recs = generate_farm_recommendations(
            net_profit=Decimal("10000"),
            livestock_intelligences=[],
            crop_intelligences=[],
            has_marketplace_listings=False,
            has_poultry=False,
            days_since_egg_record=None,
            days_since_last_sale=5,
        )
        assert any("marketplace" in r.lower() for r in recs)

    def test_egg_overdue_generates_recommendation(self):
        recs = generate_farm_recommendations(
            net_profit=Decimal("10000"),
            livestock_intelligences=[],
            crop_intelligences=[],
            has_marketplace_listings=True,
            has_poultry=True,
            days_since_egg_record=1,
            days_since_last_sale=5,
        )
        assert any("egg" in r.lower() for r in recs)

    def test_limit_respected(self):
        intels = [self._make_intel(has_asking_price=False, batch_name=f"Batch {i}") for i in range(10)]
        recs = generate_farm_recommendations(
            net_profit=Decimal("-100000"),
            livestock_intelligences=intels,
            crop_intelligences=[],
            has_marketplace_listings=False,
            has_poultry=True,
            days_since_egg_record=5,
            days_since_last_sale=60,
            limit=5,
        )
        assert len(recs) <= 5


# ===========================================================================
# 9. CATEGORIZED ALERTS
# ===========================================================================

class TestCategorizedAlerts:

    def _base_intel(self, mortality_risk="good", has_asking=True, has_stock=True,
                    net_profit=Decimal("0")):
        return LivestockIntelligenceResult(
            batch_id=1,
            batch_name="Batch A",
            animal_type="pigs",
            count_current=10 if has_stock else 0,
            births_total=0,
            deaths_total=0,
            purchases_total=10,
            sales_total=0,
            mortality_rate=Decimal("3") if mortality_risk == "good" else Decimal("25"),
            survival_rate=Decimal("97") if mortality_risk == "good" else Decimal("75"),
            mortality_risk_level=mortality_risk,
            feed_cost_mwk=Decimal("0"),
            medicine_cost_mwk=Decimal("0"),
            labour_cost_mwk=Decimal("0"),
            other_cost_mwk=Decimal("0"),
            total_cost_mwk=Decimal("0"),
            revenue_mwk=Decimal("0"),
            net_profit_mwk=net_profit,
            profit_per_animal_mwk=None,
            cost_per_surviving_animal_mwk=None,
            break_even_price_mwk=None,
            batch_health_score=80,
            days_in_cycle=30,
            estimated_value=None,
            has_asking_price=has_asking,
            has_stock=has_stock,
            recommendations=[],
        )

    def _base_crop(self, harvest_readiness="growing", projected_income=None, status="active"):
        return CropIntelligenceResult(
            season_id=1,
            season_name="Maize 2026",
            crop_type="maize",
            area_value=Decimal("2"),
            area_unit="acre",
            status=status,
            input_cost_mwk=Decimal("0"),
            input_cost_per_acre=None,
            projected_income_mwk=projected_income,
            projected_profit_mwk=None,
            yield_per_acre=None,
            break_even_price=None,
            actual_income_mwk=None,
            actual_profit_mwk=None,
            harvest_readiness=harvest_readiness,
            risk_level="unknown",
            days_to_harvest=5,
            recommendations=[],
        )

    def test_negative_profit_creates_critical_alert(self):
        result = compute_categorized_alerts(
            net_profit=Decimal("-50000"),
            total_income=Decimal("200000"),
            total_expenses=Decimal("250000"),
            livestock_intelligences=[],
            crop_intelligences=[],
            days_since_last_sale=5,
            marketplace_listings_count=1,
        )
        assert any(a.alert_type == "negative_profit" for a in result.critical)

    def test_critical_mortality_creates_critical_alert(self):
        intel = self._base_intel(mortality_risk="critical")
        result = compute_categorized_alerts(
            net_profit=Decimal("0"),
            total_income=Decimal("100000"),
            total_expenses=Decimal("80000"),
            livestock_intelligences=[intel],
            crop_intelligences=[],
            days_since_last_sale=5,
            marketplace_listings_count=1,
        )
        assert any(a.alert_type == "high_mortality" for a in result.critical)

    def test_high_mortality_creates_warning_not_critical(self):
        intel = self._base_intel(mortality_risk="high_risk")
        intel.mortality_rate = Decimal("15")
        result = compute_categorized_alerts(
            net_profit=Decimal("0"),
            total_income=Decimal("100000"),
            total_expenses=Decimal("80000"),
            livestock_intelligences=[intel],
            crop_intelligences=[],
            days_since_last_sale=5,
            marketplace_listings_count=1,
        )
        assert any(a.alert_type == "high_mortality_warning" for a in result.warnings)
        assert not any(a.alert_type == "high_mortality" for a in result.critical)

    def test_harvest_ready_creates_opportunity(self):
        crop = self._base_crop(harvest_readiness="ready")
        result = compute_categorized_alerts(
            net_profit=Decimal("0"),
            total_income=Decimal("100000"),
            total_expenses=Decimal("80000"),
            livestock_intelligences=[],
            crop_intelligences=[crop],
            days_since_last_sale=5,
            marketplace_listings_count=1,
        )
        assert any(a.alert_type == "harvest_ready" for a in result.opportunities)

    def test_profitable_batch_creates_opportunity(self):
        intel = self._base_intel(net_profit=Decimal("100000"))
        result = compute_categorized_alerts(
            net_profit=Decimal("100000"),
            total_income=Decimal("200000"),
            total_expenses=Decimal("100000"),
            livestock_intelligences=[intel],
            crop_intelligences=[],
            days_since_last_sale=5,
            marketplace_listings_count=1,
        )
        assert any(a.alert_type == "profitable_batch" for a in result.opportunities)

    def test_no_marketplace_creates_warning(self):
        result = compute_categorized_alerts(
            net_profit=Decimal("10000"),
            total_income=Decimal("100000"),
            total_expenses=Decimal("90000"),
            livestock_intelligences=[],
            crop_intelligences=[],
            days_since_last_sale=5,
            marketplace_listings_count=0,
        )
        assert any(a.alert_type == "no_marketplace" for a in result.warnings)

    def test_total_count_correct(self):
        result = compute_categorized_alerts(
            net_profit=Decimal("-10000"),
            total_income=Decimal("0"),
            total_expenses=Decimal("10000"),
            livestock_intelligences=[],
            crop_intelligences=[],
            days_since_last_sale=20,
            marketplace_listings_count=0,
        )
        expected = len(result.critical) + len(result.warnings) + len(result.opportunities)
        assert result.total_count == expected
