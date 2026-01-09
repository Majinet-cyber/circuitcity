# tests/test_farm_manager_ssot.py
"""
Unit tests for Farm Manager SSOT service.

Tests the pure functions in inventory/services/farm_manager.py
These tests verify:
- Monthly profit calculations (exact arithmetic)
- Enterprise profit calculations
- Crop season projections (projected vs actual)
- Livestock snapshot calculations (counts, mortality)
- Alert logic (deterministic)

All tests use in-memory data structures, no database required.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from inventory.services.farm_manager import (
    compute_monthly_profit,
    compute_enterprise_profit,
    compute_crop_projection,
    compute_livestock_snapshot,
    compute_alerts,
    LedgerEntryData,
    LivestockBatchData,
    LivestockEventData,
    CropSeasonData,
    MonthlyProfitResult,
)


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def sample_ledger_entries():
    """Sample ledger entries for January 2026."""
    return [
        # Expenses
        LedgerEntryData(
            id=1,
            date=date(2026, 1, 5),
            entry_type="expense",
            enterprise_type="pigs",
            category="feed",
            amount_mwk=Decimal("50000"),
            quantity=Decimal("10"),
            unit="bag",
        ),
        LedgerEntryData(
            id=2,
            date=date(2026, 1, 10),
            entry_type="expense",
            enterprise_type="pigs",
            category="vet",
            amount_mwk=Decimal("25000"),
            quantity=None,
            unit="item",
        ),
        LedgerEntryData(
            id=3,
            date=date(2026, 1, 15),
            entry_type="expense",
            enterprise_type="maize",
            category="fertiliser",
            amount_mwk=Decimal("100000"),
            quantity=Decimal("5"),
            unit="bag",
        ),
        # Sales
        LedgerEntryData(
            id=4,
            date=date(2026, 1, 20),
            entry_type="sale",
            enterprise_type="pigs",
            category="sale",
            amount_mwk=Decimal("300000"),
            quantity=Decimal("3"),
            unit="head",
        ),
        LedgerEntryData(
            id=5,
            date=date(2026, 1, 25),
            entry_type="sale",
            enterprise_type="chickens",
            category="sale",
            amount_mwk=Decimal("50000"),
            quantity=Decimal("20"),
            unit="head",
        ),
        # December entry (should be excluded from January)
        LedgerEntryData(
            id=6,
            date=date(2025, 12, 15),
            entry_type="expense",
            enterprise_type="general",
            category="labour",
            amount_mwk=Decimal("30000"),
            quantity=Decimal("3"),
            unit="day",
        ),
    ]


@pytest.fixture
def sample_livestock_batch():
    """Sample livestock batch with valuation enabled."""
    return LivestockBatchData(
        id=1,
        animal_type="pigs",
        name="Gilts Group 1",
        count_current=25,
        valuation_enabled=True,
        avg_weight_kg=Decimal("80"),
        price_per_kg_mwk=Decimal("2500"),
        price_per_animal_mwk=None,
    )


@pytest.fixture
def sample_livestock_events():
    """Sample livestock events."""
    return [
        LivestockEventData(
            id=1,
            batch_id=1,
            event_type="purchase",
            date=date(2026, 1, 1),
            count=20,
            unit_price_mwk=Decimal("100000"),
        ),
        LivestockEventData(
            id=2,
            batch_id=1,
            event_type="birth",
            date=date(2026, 1, 10),
            count=8,
            unit_price_mwk=None,
        ),
        LivestockEventData(
            id=3,
            batch_id=1,
            event_type="death",
            date=date(2026, 1, 15),
            count=2,
            unit_price_mwk=None,
        ),
        LivestockEventData(
            id=4,
            batch_id=1,
            event_type="sale",
            date=date(2026, 1, 25),
            count=3,
            unit_price_mwk=Decimal("150000"),
        ),
    ]


@pytest.fixture
def sample_crop_season():
    """Sample crop season with projections."""
    return CropSeasonData(
        id=1,
        crop_type="maize",
        name="Maize 2026 Main Season",
        start_date=date(2025, 11, 1),
        end_date=date(2026, 4, 30),
        area_value=Decimal("5"),
        area_unit="acre",
        projected_yield=Decimal("100"),
        yield_unit="bag",
        projected_price_per_unit_mwk=Decimal("25000"),
        actual_yield=Decimal("85"),
        actual_price_per_unit_mwk=Decimal("22000"),
        status="harvested",
    )


# ==============================================================================
# MONTHLY PROFIT TESTS
# ==============================================================================


class TestComputeMonthlyProfit:
    """Test monthly profit computation."""

    def test_monthly_profit_exact_arithmetic(self, sample_ledger_entries):
        """Test that monthly profit is calculated exactly."""
        result = compute_monthly_profit(sample_ledger_entries, 2026, 1)
        
        # January expenses: 50000 + 25000 + 100000 = 175000
        assert result.total_expenses == Decimal("175000")
        
        # January income: 300000 + 50000 = 350000
        assert result.total_income == Decimal("350000")
        
        # Net profit: 350000 - 175000 = 175000
        assert result.net_profit == Decimal("175000")

    def test_monthly_profit_counts(self, sample_ledger_entries):
        """Test that entry counts are correct."""
        result = compute_monthly_profit(sample_ledger_entries, 2026, 1)
        
        # 3 expense entries in January
        assert result.expense_count == 3
        
        # 2 sale entries in January
        assert result.sales_count == 2

    def test_monthly_profit_excludes_other_months(self, sample_ledger_entries):
        """Test that entries from other months are excluded."""
        # December should only have 1 entry
        result = compute_monthly_profit(sample_ledger_entries, 2025, 12)
        
        assert result.total_expenses == Decimal("30000")
        assert result.total_income == Decimal("0")
        assert result.expense_count == 1

    def test_top_expense_categories(self, sample_ledger_entries):
        """Test that top expense categories are ranked correctly."""
        result = compute_monthly_profit(sample_ledger_entries, 2026, 1)
        
        # Should have 3 categories: fertiliser (100k), feed (50k), vet (25k)
        assert len(result.top_expense_categories) == 3
        
        # First should be fertiliser
        assert result.top_expense_categories[0]["category"] == "fertiliser"
        assert result.top_expense_categories[0]["amount"] == Decimal("100000")

    def test_income_by_enterprise(self, sample_ledger_entries):
        """Test income breakdown by enterprise."""
        result = compute_monthly_profit(sample_ledger_entries, 2026, 1)
        
        assert result.income_by_enterprise["pigs"] == Decimal("300000")
        assert result.income_by_enterprise["chickens"] == Decimal("50000")

    def test_expense_by_enterprise(self, sample_ledger_entries):
        """Test expense breakdown by enterprise."""
        result = compute_monthly_profit(sample_ledger_entries, 2026, 1)
        
        # Pigs: 50000 (feed) + 25000 (vet) = 75000
        assert result.expense_by_enterprise["pigs"] == Decimal("75000")
        
        # Maize: 100000 (fertiliser)
        assert result.expense_by_enterprise["maize"] == Decimal("100000")

    def test_empty_month_returns_zeros(self):
        """Test that empty month returns zero values."""
        result = compute_monthly_profit([], 2026, 1)
        
        assert result.total_income == Decimal("0")
        assert result.total_expenses == Decimal("0")
        assert result.net_profit == Decimal("0")
        assert result.sales_count == 0
        assert result.expense_count == 0


# ==============================================================================
# ENTERPRISE PROFIT TESTS
# ==============================================================================


class TestComputeEnterpriseProfit:
    """Test enterprise-specific profit computation."""

    def test_enterprise_profit_pigs(self, sample_ledger_entries):
        """Test profit calculation for pig enterprise."""
        result = compute_enterprise_profit(sample_ledger_entries, "pigs")
        
        # Pigs income: 300000
        assert result.total_income == Decimal("300000")
        
        # Pigs expenses: 50000 + 25000 = 75000
        assert result.total_expenses == Decimal("75000")
        
        # Net: 300000 - 75000 = 225000
        assert result.net_profit == Decimal("225000")

    def test_enterprise_profit_with_date_filter(self, sample_ledger_entries):
        """Test profit calculation with date filtering."""
        result = compute_enterprise_profit(
            sample_ledger_entries,
            "pigs",
            start_date=date(2026, 1, 10),
            end_date=date(2026, 1, 20),
        )
        
        # Only vet expense (25000) and one sale (300000) in this range
        assert result.total_expenses == Decimal("25000")
        assert result.total_income == Decimal("300000")


# ==============================================================================
# CROP PROJECTION TESTS
# ==============================================================================


class TestComputeCropProjection:
    """Test crop season projection computation."""

    def test_crop_projection_projected_income(self, sample_crop_season, sample_ledger_entries):
        """Test projected income calculation."""
        result = compute_crop_projection(sample_crop_season, sample_ledger_entries)
        
        # Projected: 100 bags * 25000 = 2,500,000
        assert result.projected_income == Decimal("2500000")

    def test_crop_projection_actual_income(self, sample_crop_season, sample_ledger_entries):
        """Test actual income calculation."""
        result = compute_crop_projection(sample_crop_season, sample_ledger_entries)
        
        # Actual: 85 bags * 22000 = 1,870,000
        assert result.actual_income == Decimal("1870000")

    def test_crop_projection_income_variance(self, sample_crop_season, sample_ledger_entries):
        """Test income variance calculation."""
        result = compute_crop_projection(sample_crop_season, sample_ledger_entries)
        
        # Variance: 1,870,000 - 2,500,000 = -630,000
        assert result.income_variance == Decimal("-630000")
        
        # Variance %: -630000 / 2500000 * 100 = -25.2%
        assert result.income_variance_pct == Decimal("-25.2")


# ==============================================================================
# LIVESTOCK SNAPSHOT TESTS
# ==============================================================================


class TestComputeLivestockSnapshot:
    """Test livestock snapshot computation."""

    def test_livestock_count_from_events(self, sample_livestock_batch, sample_livestock_events):
        """Test that count is calculated correctly from events."""
        result = compute_livestock_snapshot(
            sample_livestock_batch,
            sample_livestock_events,
            as_of_date=date(2026, 1, 31),
        )
        
        # Initial: 0, Purchase: +20, Birth: +8, Death: -2, Sale: -3 = 23
        assert result.count_current == 23

    def test_livestock_totals(self, sample_livestock_batch, sample_livestock_events):
        """Test event totals are calculated correctly."""
        result = compute_livestock_snapshot(
            sample_livestock_batch,
            sample_livestock_events,
            as_of_date=date(2026, 1, 31),
        )
        
        assert result.births_total == 8
        assert result.deaths_total == 2
        assert result.purchases_total == 20
        assert result.sales_total == 3

    def test_livestock_mortality_rate(self, sample_livestock_batch, sample_livestock_events):
        """Test mortality rate calculation."""
        result = compute_livestock_snapshot(
            sample_livestock_batch,
            sample_livestock_events,
            as_of_date=date(2026, 1, 31),
        )
        
        # Mortality: 2 deaths / (20 purchases + 8 births) = 2/28 = 7.14%
        expected_rate = Decimal("2") / Decimal("28") * 100
        assert abs(result.mortality_rate - expected_rate) < Decimal("0.01")

    def test_livestock_valuation_by_weight(self, sample_livestock_batch, sample_livestock_events):
        """Test valuation calculation using weight-based pricing."""
        result = compute_livestock_snapshot(
            sample_livestock_batch,
            sample_livestock_events,
            as_of_date=date(2026, 1, 31),
        )
        
        # Value: 23 animals * 80kg * 2500 MWK/kg = 4,600,000
        assert result.estimated_value == Decimal("4600000")

    def test_livestock_valuation_disabled(self, sample_livestock_events):
        """Test that valuation is None when disabled."""
        batch = LivestockBatchData(
            id=1,
            animal_type="pigs",
            name="Test Batch",
            count_current=25,
            valuation_enabled=False,  # Disabled
            avg_weight_kg=Decimal("80"),
            price_per_kg_mwk=Decimal("2500"),
            price_per_animal_mwk=None,
        )
        
        result = compute_livestock_snapshot(batch, sample_livestock_events)
        
        assert result.estimated_value is None

    def test_livestock_as_of_date_filtering(self, sample_livestock_batch, sample_livestock_events):
        """Test that events after as_of_date are excluded."""
        # Only events up to Jan 15 (purchase, birth, death)
        result = compute_livestock_snapshot(
            sample_livestock_batch,
            sample_livestock_events,
            as_of_date=date(2026, 1, 15),
        )
        
        # Count: 20 + 8 - 2 = 26 (sale on Jan 25 excluded)
        assert result.count_current == 26


# ==============================================================================
# ALERTS TESTS
# ==============================================================================


class TestComputeAlerts:
    """Test alert computation logic."""

    def test_alert_expenses_rising(self):
        """Test that expense increase triggers alert."""
        current = MonthlyProfitResult(
            year=2026,
            month=1,
            total_income=Decimal("100000"),
            total_expenses=Decimal("150000"),  # 50% higher than previous
            net_profit=Decimal("-50000"),
            sales_count=5,
            expense_count=10,
            top_expense_categories=[],
            income_by_enterprise={},
            expense_by_enterprise={},
        )
        previous = MonthlyProfitResult(
            year=2025,
            month=12,
            total_income=Decimal("100000"),
            total_expenses=Decimal("100000"),
            net_profit=Decimal("0"),
            sales_count=5,
            expense_count=8,
            top_expense_categories=[],
            income_by_enterprise={},
            expense_by_enterprise={},
        )
        
        alerts = compute_alerts(current, previous, [], None)
        
        expense_alerts = [a for a in alerts if a.alert_type == "expenses_rising"]
        assert len(expense_alerts) == 1
        assert expense_alerts[0].severity == "warning"

    def test_alert_no_sales(self):
        """Test that no sales triggers alert."""
        current = MonthlyProfitResult(
            year=2026,
            month=1,
            total_income=Decimal("0"),
            total_expenses=Decimal("50000"),
            net_profit=Decimal("-50000"),
            sales_count=0,
            expense_count=5,
            top_expense_categories=[],
            income_by_enterprise={},
            expense_by_enterprise={},
        )
        
        alerts = compute_alerts(current, None, [], days_since_last_sale=20)
        
        no_sale_alerts = [a for a in alerts if a.alert_type == "no_sales"]
        assert len(no_sale_alerts) == 1
        assert "20" in no_sale_alerts[0].message

    def test_alert_high_mortality(self):
        """Test that high mortality triggers alert."""
        from inventory.services.farm_manager import LivestockSnapshotResult
        
        snapshot = LivestockSnapshotResult(
            batch_id=1,
            batch_name="Sick Batch",
            animal_type="pigs",
            count_current=10,
            births_total=20,
            deaths_total=8,  # 40% mortality
            purchases_total=0,
            sales_total=2,
            mortality_rate=Decimal("40.0"),
            estimated_value=None,
        )
        
        current = MonthlyProfitResult(
            year=2026, month=1, total_income=Decimal("100000"),
            total_expenses=Decimal("50000"), net_profit=Decimal("50000"),
            sales_count=5, expense_count=5, top_expense_categories=[],
            income_by_enterprise={}, expense_by_enterprise={},
        )
        
        alerts = compute_alerts(current, None, [snapshot], None)
        
        mortality_alerts = [a for a in alerts if a.alert_type == "high_mortality"]
        assert len(mortality_alerts) == 1
        assert mortality_alerts[0].severity == "critical"

    def test_alert_negative_profit(self):
        """Test that negative profit triggers critical alert."""
        current = MonthlyProfitResult(
            year=2026,
            month=1,
            total_income=Decimal("50000"),
            total_expenses=Decimal("100000"),
            net_profit=Decimal("-50000"),  # Loss
            sales_count=5,
            expense_count=10,
            top_expense_categories=[],
            income_by_enterprise={},
            expense_by_enterprise={},
        )
        
        alerts = compute_alerts(current, None, [], None)
        
        profit_alerts = [a for a in alerts if a.alert_type == "negative_profit"]
        assert len(profit_alerts) == 1
        assert profit_alerts[0].severity == "critical"

    def test_no_alerts_when_healthy(self):
        """Test that no alerts fire when business is healthy."""
        current = MonthlyProfitResult(
            year=2026,
            month=1,
            total_income=Decimal("200000"),
            total_expenses=Decimal("100000"),
            net_profit=Decimal("100000"),  # 50% margin
            sales_count=10,
            expense_count=5,
            top_expense_categories=[],
            income_by_enterprise={},
            expense_by_enterprise={},
        )
        previous = MonthlyProfitResult(
            year=2025,
            month=12,
            total_income=Decimal("180000"),
            total_expenses=Decimal("95000"),  # Expenses stayed similar
            net_profit=Decimal("85000"),
            sales_count=9,
            expense_count=5,
            top_expense_categories=[],
            income_by_enterprise={},
            expense_by_enterprise={},
        )
        
        alerts = compute_alerts(current, previous, [], days_since_last_sale=2)
        
        # Should have no alerts
        assert len(alerts) == 0

