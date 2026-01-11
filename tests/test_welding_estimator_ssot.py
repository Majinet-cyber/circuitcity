# tests/test_welding_estimator_ssot.py
"""
Unit tests for Welding Estimator SSOT service.

Tests the pure functions in inventory/services/welding_estimator.py
These tests verify:
- BOM estimation from templates
- Cost calculation (materials, labour, overhead, margin)
- Tuning update (bounded learning)
- Quote generation

All tests use in-memory data structures, no database required.
"""
import pytest
from decimal import Decimal

from inventory.services.welding_estimator import (
    seed_default_materials,
    estimate_bom,
    compute_cost,
    update_tuning,
    generate_quote_from_template,
    get_default_materials,
    get_default_templates,
    MaterialData,
    BOMItem,
    TuningData,
)


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def materials_catalog():
    """Sample materials catalog with prices."""
    return {
        "TUBE_40x40": MaterialData(
            id=1,
            code="TUBE_40x40",
            name="Square Tube 40x40mm (6m)",
            category="tube",
            unit="length_6m",
            price_mwk=Decimal("28000"),
            quantity_in_stock=Decimal("10"),
        ),
        "TUBE_25x25": MaterialData(
            id=2,
            code="TUBE_25x25",
            name="Square Tube 25x25mm (6m)",
            category="tube",
            unit="length_6m",
            price_mwk=Decimal("15000"),
            quantity_in_stock=Decimal("15"),
        ),
        "FLAT_25x3": MaterialData(
            id=3,
            code="FLAT_25x3",
            name="Flat Bar 25x3mm (6m)",
            category="flat_bar",
            unit="length_6m",
            price_mwk=Decimal("8000"),
            quantity_in_stock=Decimal("5"),
        ),
        "RED_OXIDE_5L": MaterialData(
            id=4,
            code="RED_OXIDE_5L",
            name="Red Oxide 5L",
            category="paint",
            unit="piece",
            price_mwk=Decimal("12000"),
            quantity_in_stock=Decimal("3"),
        ),
        "RED_OXIDE_1L": MaterialData(
            id=5,
            code="RED_OXIDE_1L",
            name="Red Oxide 1L",
            category="paint",
            unit="piece",
            price_mwk=Decimal("3500"),
            quantity_in_stock=Decimal("5"),
        ),
        "PAINT_GLOSS_5L": MaterialData(
            id=6,
            code="PAINT_GLOSS_5L",
            name="Gloss Paint 5L",
            category="paint",
            unit="piece",
            price_mwk=Decimal("18000"),
            quantity_in_stock=Decimal("2"),
        ),
        "PAINT_GLOSS_1L": MaterialData(
            id=7,
            code="PAINT_GLOSS_1L",
            name="Gloss Paint 1L",
            category="paint",
            unit="piece",
            price_mwk=Decimal("5000"),
            quantity_in_stock=Decimal("4"),
        ),
        "ELECTRODE_2.5_PKT": MaterialData(
            id=8,
            code="ELECTRODE_2.5_PKT",
            name="Electrodes 2.5mm (packet)",
            category="consumable",
            unit="packet",
            price_mwk=Decimal("3500"),
            quantity_in_stock=Decimal("10"),
        ),
        "DISC_CUT_4IN": MaterialData(
            id=9,
            code="DISC_CUT_4IN",
            name="Cutting Disc 4in",
            category="consumable",
            unit="piece",
            price_mwk=Decimal("1500"),
            quantity_in_stock=Decimal("20"),
        ),
    }


@pytest.fixture
def default_tuning():
    """Default tuning with no adjustments."""
    return TuningData(
        tube_multiplier=Decimal("1.00"),
        paint_multiplier=Decimal("1.00"),
        consumable_multiplier=Decimal("1.00"),
        labour_multiplier=Decimal("1.00"),
        samples_count=0,
    )


@pytest.fixture
def sample_bom():
    """Sample BOM for cost testing."""
    return [
        BOMItem(
            material_code="TUBE_40x40",
            material_name="Square Tube 40x40mm (6m)",
            category="tube",
            quantity=Decimal("3"),
            unit="length_6m",
            unit_price_mwk=Decimal("28000"),
            line_total_mwk=Decimal("84000"),
        ),
        BOMItem(
            material_code="FLAT_25x3",
            material_name="Flat Bar 25x3mm (6m)",
            category="flat_bar",
            quantity=Decimal("1"),
            unit="length_6m",
            unit_price_mwk=Decimal("8000"),
            line_total_mwk=Decimal("8000"),
        ),
        BOMItem(
            material_code="RED_OXIDE_5L",
            material_name="Red Oxide 5L",
            category="paint",
            quantity=Decimal("0.5"),
            unit="piece",
            unit_price_mwk=Decimal("12000"),
            line_total_mwk=Decimal("6000"),
        ),
        BOMItem(
            material_code="ELECTRODE_2.5_PKT",
            material_name="Electrodes 2.5mm (packet)",
            category="consumable",
            quantity=Decimal("1"),
            unit="packet",
            unit_price_mwk=Decimal("3500"),
            line_total_mwk=Decimal("3500"),
        ),
    ]


# ==============================================================================
# SEED DEFAULT MATERIALS TESTS
# ==============================================================================


class TestSeedDefaultMaterials:
    """Test default materials seeding logic."""

    def test_seed_all_when_empty(self):
        """Test that all materials are seeded when catalog is empty."""
        to_seed = seed_default_materials([])
        
        # Should include all default materials
        assert len(to_seed) > 20  # We have 20+ default materials

    def test_seed_none_when_all_exist(self):
        """Test that nothing is seeded when all materials exist."""
        default_mats = get_default_materials()
        existing_codes = [m["code"] for m in default_mats]
        
        to_seed = seed_default_materials(existing_codes)
        
        assert len(to_seed) == 0

    def test_seed_partial(self):
        """Test that only missing materials are seeded."""
        # Only have TUBE_25x25 and TUBE_40x40
        existing = ["TUBE_25x25", "TUBE_40x40"]
        
        to_seed = seed_default_materials(existing)
        
        # Should not include the existing codes
        seeded_codes = [m["code"] for m in to_seed]
        assert "TUBE_25x25" not in seeded_codes
        assert "TUBE_40x40" not in seeded_codes
        
        # But should include others
        assert "TUBE_50x50" in seeded_codes
        assert "RED_OXIDE_5L" in seeded_codes


# ==============================================================================
# BOM ESTIMATION TESTS
# ==============================================================================


class TestEstimateBom:
    """Test BOM estimation from templates."""

    def test_bom_for_bed_4x6(self, materials_catalog, default_tuning):
        """Test BOM generation for a 4x6 bed frame."""
        result = estimate_bom(
            template_code="BED_4x6",
            specs={"width_ft": 4, "length_ft": 6},
            tuning=default_tuning,
            materials_catalog=materials_catalog,
        )
        
        # Should have BOM items
        assert len(result.bom) > 0
        
        # Should include tubes
        tube_items = [b for b in result.bom if b["category"] == "tube"]
        assert len(tube_items) > 0
        
        # Total tube length should be calculated
        assert result.total_tube_length_m > 0

    def test_bom_applies_tuning_multiplier(self, materials_catalog):
        """Test that tuning multipliers are applied."""
        tuning = TuningData(
            tube_multiplier=Decimal("1.20"),  # 20% more tubes needed
            paint_multiplier=Decimal("1.00"),
            consumable_multiplier=Decimal("1.00"),
            labour_multiplier=Decimal("1.00"),
            samples_count=5,
        )
        
        # Get baseline
        baseline = estimate_bom(
            "BED_4x6", {}, None, materials_catalog,
        )
        
        # Get tuned
        tuned = estimate_bom(
            "BED_4x6", {}, tuning, materials_catalog,
        )
        
        # Compare tube quantities
        baseline_tubes = sum(
            b["quantity"] for b in baseline.bom if b["category"] == "tube"
        )
        tuned_tubes = sum(
            b["quantity"] for b in tuned.bom if b["category"] == "tube"
        )
        
        # Tuned should be 20% higher
        assert tuned_tubes == baseline_tubes * Decimal("1.20")

    def test_bom_unknown_template_returns_empty(self, materials_catalog, default_tuning):
        """Test that unknown template returns empty BOM."""
        result = estimate_bom(
            template_code="UNKNOWN_PRODUCT",
            specs={},
            tuning=default_tuning,
            materials_catalog=materials_catalog,
        )
        
        assert len(result.bom) == 0
        assert "Unknown template" in result.cut_list_notes

    def test_bom_cut_list_recommendation(self, materials_catalog, default_tuning):
        """Test that cut list recommendations are calculated."""
        result = estimate_bom(
            template_code="BED_4x6",
            specs={},
            tuning=default_tuning,
            materials_catalog=materials_catalog,
        )
        
        # Should recommend some 6m lengths
        assert result.recommended_6m_lengths > 0
        
        # Wastage factor should be 1.10 (10%)
        assert result.wastage_factor == Decimal("1.10")


# ==============================================================================
# COST CALCULATION TESTS
# ==============================================================================


class TestComputeCost:
    """Test cost calculation logic."""

    def test_materials_cost_exact(self, sample_bom):
        """Test that materials cost sums line totals exactly."""
        result = compute_cost(
            bom_items=sample_bom,
            labour_hours=Decimal("4"),
            labour_rate_per_hour=Decimal("5000"),
            overhead_pct=Decimal("10"),
            margin_pct=Decimal("25"),
        )
        
        # Materials: 84000 + 8000 + 6000 + 3500 = 101500
        assert result["materials_cost"] == Decimal("101500")

    def test_labour_cost_exact(self, sample_bom):
        """Test that labour cost is hours * rate."""
        result = compute_cost(
            bom_items=sample_bom,
            labour_hours=Decimal("4"),
            labour_rate_per_hour=Decimal("5000"),
            overhead_pct=Decimal("10"),
            margin_pct=Decimal("25"),
        )
        
        # Labour: 4 hours * 5000 = 20000
        assert result["labour_cost"] == Decimal("20000")

    def test_overhead_cost_percentage(self, sample_bom):
        """Test that overhead is calculated as percentage of base costs."""
        result = compute_cost(
            bom_items=sample_bom,
            labour_hours=Decimal("4"),
            labour_rate_per_hour=Decimal("5000"),
            overhead_pct=Decimal("10"),  # 10%
            margin_pct=Decimal("0"),
        )
        
        # Base: 101500 (materials) + 20000 (labour) = 121500
        # Overhead: 121500 * 0.10 = 12150
        assert result["overhead_cost"] == Decimal("12150")

    def test_margin_cost_percentage(self, sample_bom):
        """Test that margin is calculated as percentage of subtotal."""
        result = compute_cost(
            bom_items=sample_bom,
            labour_hours=Decimal("4"),
            labour_rate_per_hour=Decimal("5000"),
            overhead_pct=Decimal("10"),
            margin_pct=Decimal("25"),  # 25%
        )
        
        # Subtotal before margin: 101500 + 20000 + 12150 = 133650
        # Margin: 133650 * 0.25 = 33412.50
        assert result["margin_amount"] == Decimal("33412.50")

    def test_total_calculation(self, sample_bom):
        """Test that total is correctly calculated."""
        result = compute_cost(
            bom_items=sample_bom,
            labour_hours=Decimal("4"),
            labour_rate_per_hour=Decimal("5000"),
            overhead_pct=Decimal("10"),
            margin_pct=Decimal("25"),
        )
        
        # Total: 133650 + 33412.50 = 167062.50
        expected_total = Decimal("167062.50")
        assert result["total"] == expected_total

    def test_min_price_is_break_even(self, sample_bom):
        """Test that min price equals subtotal before margin."""
        result = compute_cost(
            bom_items=sample_bom,
            labour_hours=Decimal("4"),
            labour_rate_per_hour=Decimal("5000"),
            overhead_pct=Decimal("10"),
            margin_pct=Decimal("25"),
        )
        
        # Min price should be subtotal (no margin)
        assert result["min_price"] == result["subtotal_before_margin"]

    def test_zero_labour_hours(self):
        """Test calculation with zero labour."""
        bom = [
            BOMItem(
                material_code="TUBE_40x40",
                material_name="Tube",
                category="tube",
                quantity=Decimal("1"),
                unit="piece",
                unit_price_mwk=Decimal("10000"),
                line_total_mwk=Decimal("10000"),
            ),
        ]
        
        result = compute_cost(
            bom_items=bom,
            labour_hours=Decimal("0"),
            labour_rate_per_hour=Decimal("5000"),
            overhead_pct=Decimal("10"),
            margin_pct=Decimal("20"),
        )
        
        assert result["labour_cost"] == Decimal("0")
        assert result["materials_cost"] == Decimal("10000")


# ==============================================================================
# TUNING UPDATE TESTS
# ==============================================================================


class TestUpdateTuning:
    """Test tuning update (learning) logic."""

    def test_tuning_update_increases_multiplier(self, default_tuning):
        """Test that using more material increases multiplier."""
        estimated_bom = [
            BOMItem(
                material_code="TUBE_40x40",
                material_name="Tube",
                category="tube",
                quantity=Decimal("3"),
                unit="piece",
                unit_price_mwk=Decimal("28000"),
                line_total_mwk=Decimal("84000"),
            ),
        ]
        actual_bom = [
            BOMItem(
                material_code="TUBE_40x40",
                material_name="Tube",
                category="tube",
                quantity=Decimal("4"),  # Used more than estimated
                unit="piece",
                unit_price_mwk=Decimal("28000"),
                line_total_mwk=Decimal("112000"),
            ),
        ]
        
        new_tuning = update_tuning(
            default_tuning,
            estimated_bom,
            actual_bom,
            estimated_labour=Decimal("4"),
            actual_labour=Decimal("4"),
        )
        
        # Tube multiplier should increase
        assert new_tuning["tube_multiplier"] > Decimal("1.00")

    def test_tuning_update_decreases_multiplier(self, default_tuning):
        """Test that using less material decreases multiplier."""
        estimated_bom = [
            BOMItem(
                material_code="TUBE_40x40",
                material_name="Tube",
                category="tube",
                quantity=Decimal("4"),
                unit="piece",
                unit_price_mwk=Decimal("28000"),
                line_total_mwk=Decimal("112000"),
            ),
        ]
        actual_bom = [
            BOMItem(
                material_code="TUBE_40x40",
                material_name="Tube",
                category="tube",
                quantity=Decimal("3"),  # Used less than estimated
                unit="piece",
                unit_price_mwk=Decimal("28000"),
                line_total_mwk=Decimal("84000"),
            ),
        ]
        
        new_tuning = update_tuning(
            default_tuning,
            estimated_bom,
            actual_bom,
            estimated_labour=Decimal("4"),
            actual_labour=Decimal("4"),
        )
        
        # Tube multiplier should decrease
        assert new_tuning["tube_multiplier"] < Decimal("1.00")

    def test_tuning_bounded_min(self, default_tuning):
        """Test that multiplier doesn't go below minimum."""
        # Start with very low multiplier
        low_tuning = TuningData(
            tube_multiplier=Decimal("0.60"),
            paint_multiplier=Decimal("1.00"),
            consumable_multiplier=Decimal("1.00"),
            labour_multiplier=Decimal("1.00"),
            samples_count=10,
        )
        
        # Extreme underestimate (actual much less than estimated)
        estimated_bom = [
            BOMItem(
                material_code="TUBE_40x40",
                material_name="Tube",
                category="tube",
                quantity=Decimal("10"),
                unit="piece",
                unit_price_mwk=Decimal("28000"),
                line_total_mwk=Decimal("280000"),
            ),
        ]
        actual_bom = [
            BOMItem(
                material_code="TUBE_40x40",
                material_name="Tube",
                category="tube",
                quantity=Decimal("1"),  # Way less than estimated
                unit="piece",
                unit_price_mwk=Decimal("28000"),
                line_total_mwk=Decimal("28000"),
            ),
        ]
        
        new_tuning = update_tuning(
            low_tuning,
            estimated_bom,
            actual_bom,
            estimated_labour=Decimal("4"),
            actual_labour=Decimal("4"),
        )
        
        # Should not go below 0.5
        assert new_tuning["tube_multiplier"] >= Decimal("0.50")

    def test_tuning_bounded_max(self, default_tuning):
        """Test that multiplier doesn't exceed maximum."""
        # Start with high multiplier
        high_tuning = TuningData(
            tube_multiplier=Decimal("1.90"),
            paint_multiplier=Decimal("1.00"),
            consumable_multiplier=Decimal("1.00"),
            labour_multiplier=Decimal("1.00"),
            samples_count=10,
        )
        
        # Extreme overestimate (actual much more than estimated)
        estimated_bom = [
            BOMItem(
                material_code="TUBE_40x40",
                material_name="Tube",
                category="tube",
                quantity=Decimal("1"),
                unit="piece",
                unit_price_mwk=Decimal("28000"),
                line_total_mwk=Decimal("28000"),
            ),
        ]
        actual_bom = [
            BOMItem(
                material_code="TUBE_40x40",
                material_name="Tube",
                category="tube",
                quantity=Decimal("10"),  # Way more than estimated
                unit="piece",
                unit_price_mwk=Decimal("28000"),
                line_total_mwk=Decimal("280000"),
            ),
        ]
        
        new_tuning = update_tuning(
            high_tuning,
            estimated_bom,
            actual_bom,
            estimated_labour=Decimal("4"),
            actual_labour=Decimal("4"),
        )
        
        # Should not exceed 2.0
        assert new_tuning["tube_multiplier"] <= Decimal("2.00")

    def test_tuning_samples_count_increments(self, default_tuning):
        """Test that samples count increments after update."""
        new_tuning = update_tuning(
            default_tuning,
            [],
            [],
            estimated_labour=Decimal("4"),
            actual_labour=Decimal("4"),
        )
        
        assert new_tuning["samples_count"] == 1


# ==============================================================================
# QUOTE GENERATION TESTS
# ==============================================================================


class TestGenerateQuoteFromTemplate:
    """Test complete quote generation."""

    def test_quote_generation_returns_complete_result(self, materials_catalog):
        """Test that quote generation returns all required fields."""
        result = generate_quote_from_template(
            template_code="BED_4x6",
            specs={},
            materials_catalog=materials_catalog,
            tuning=None,
            labour_rate_per_hour=Decimal("5000"),
        )
        
        # Should have BOM
        assert len(result.bom) > 0
        
        # Should have cost breakdown
        assert result.cost_breakdown["materials_cost"] > 0
        
        # Should have recommended and min prices
        assert result.recommended_price > result.min_price

    def test_quote_prices_match_breakdown(self, materials_catalog):
        """Test that quote prices match cost breakdown."""
        result = generate_quote_from_template(
            template_code="BED_4x6",
            specs={},
            materials_catalog=materials_catalog,
            tuning=None,
            labour_rate_per_hour=Decimal("5000"),
            overhead_pct=Decimal("10"),
            margin_pct=Decimal("25"),
        )
        
        # Recommended price should equal total
        assert result.recommended_price == result.cost_breakdown["total"]
        
        # Min price should equal subtotal
        assert result.min_price == result.cost_breakdown["min_price"]

    def test_quote_with_tuning(self, materials_catalog):
        """Test that tuning affects quote result."""
        tuning = TuningData(
            tube_multiplier=Decimal("1.50"),  # 50% more tubes
            paint_multiplier=Decimal("1.00"),
            consumable_multiplier=Decimal("1.00"),
            labour_multiplier=Decimal("1.20"),  # 20% more labour
            samples_count=10,
        )
        
        baseline = generate_quote_from_template(
            "BED_4x6", {}, materials_catalog, None, Decimal("5000"),
        )
        
        tuned = generate_quote_from_template(
            "BED_4x6", {}, materials_catalog, tuning, Decimal("5000"),
        )
        
        # Tuned should be more expensive
        assert tuned.recommended_price > baseline.recommended_price

