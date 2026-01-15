# inventory/services/farm_agronomy.py
"""
Farm Smart Agronomy Estimator Module.

Provides curated local dataset for Malawi crop recommendations:
- Yield estimates per acre (conservative ranges)
- Fertiliser recommendations (split application schedules)
- Configurable "recommendation profiles" for future admin editing

IMPORTANT: These are ESTIMATES for planning purposes only.
Actual results vary based on weather, soil, management practices.

No internet connection required at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict, List, Any


@dataclass
class YieldEstimate:
    """Estimated yield range for a crop."""
    low_bags_per_acre: Decimal
    high_bags_per_acre: Decimal
    unit: str = "50kg bags"
    conditions_note: str = "Good conditions (adequate rain, good soil)"


@dataclass
class FertiliserStage:
    """Fertiliser application stage recommendation."""
    stage_name: str  # e.g., "Basal", "Top-dressing 1", "Top-dressing 2"
    timing: str  # e.g., "At planting", "3 weeks after emergence"
    fertiliser_type: str  # e.g., "NPK 23:21:0+4S", "Urea"
    kg_per_acre_low: Decimal
    kg_per_acre_high: Decimal
    notes: str = ""


@dataclass
class FertiliserRecommendation:
    """Complete fertiliser recommendation for a crop."""
    stages: List[FertiliserStage]
    total_cost_estimate_mwk_per_acre: Optional[Decimal] = None
    ratio_note: str = ""


@dataclass
class CropRecommendation:
    """Complete recommendation profile for a crop."""
    crop_code: str
    crop_name: str
    yield_estimate: YieldEstimate
    fertiliser_recommendation: FertiliserRecommendation
    seed_rate_kg_per_acre: Optional[Decimal] = None
    recommended_varieties: List[str] = None
    planting_window: str = ""
    disclaimer: str = "Estimates for planning only. Actual results vary based on weather, soil conditions, and farm management practices."


# ==============================================================================
# CURATED LOCAL DATASET (Malawi-specific)
# ==============================================================================

CROP_RECOMMENDATIONS: Dict[str, CropRecommendation] = {
    # MAIZE - Primary staple crop
    "maize": CropRecommendation(
        crop_code="maize",
        crop_name="Maize (Chimanga)",
        yield_estimate=YieldEstimate(
            low_bags_per_acre=Decimal("8"),
            high_bags_per_acre=Decimal("20"),
            unit="50kg bags",
            conditions_note="Good rain (800-1200mm), well-prepared land, timely planting",
        ),
        fertiliser_recommendation=FertiliserRecommendation(
            stages=[
                FertiliserStage(
                    stage_name="Basal Application",
                    timing="At planting",
                    fertiliser_type="NPK 23:21:0+4S",
                    kg_per_acre_low=Decimal("40"),
                    kg_per_acre_high=Decimal("60"),
                    notes="Apply in planting furrow, mix with soil",
                ),
                FertiliserStage(
                    stage_name="Top-dressing 1",
                    timing="3-4 weeks after emergence (knee-high)",
                    fertiliser_type="Urea",
                    kg_per_acre_low=Decimal("20"),
                    kg_per_acre_high=Decimal("40"),
                    notes="Apply around plants, incorporate if possible",
                ),
                FertiliserStage(
                    stage_name="Top-dressing 2 (optional)",
                    timing="6-8 weeks after emergence (tasseling)",
                    fertiliser_type="Urea",
                    kg_per_acre_low=Decimal("10"),
                    kg_per_acre_high=Decimal("20"),
                    notes="For high-yield potential fields only",
                ),
            ],
            ratio_note="Stage 1 focus: Growth (2:1 NPK:Urea); Later stages: N boost (Urea alone)",
        ),
        seed_rate_kg_per_acre=Decimal("10"),
        recommended_varieties=["SeedCo SC719", "DK8031 (Dekalb)", "MH18", "Local/OPV"],
        planting_window="Nov 15 - Dec 31 (main season)",
    ),

    # SOYA BEANS
    "soya": CropRecommendation(
        crop_code="soya",
        crop_name="Soya Beans (Soya)",
        yield_estimate=YieldEstimate(
            low_bags_per_acre=Decimal("6"),
            high_bags_per_acre=Decimal("12"),
            unit="50kg bags",
            conditions_note="Good drainage, inoculated seed, timely weeding",
        ),
        fertiliser_recommendation=FertiliserRecommendation(
            stages=[
                FertiliserStage(
                    stage_name="Basal Only",
                    timing="At planting",
                    fertiliser_type="D-Compound (10:20:20)",
                    kg_per_acre_low=Decimal("20"),
                    kg_per_acre_high=Decimal("40"),
                    notes="Legumes fix nitrogen; focus on P and K",
                ),
            ],
            ratio_note="Legumes need less N; ensure inoculation for N-fixation",
        ),
        seed_rate_kg_per_acre=Decimal("30"),
        recommended_varieties=["Tikolore", "Makwacha", "Ocepara-4"],
        planting_window="Dec 1 - Jan 15",
    ),

    # GROUNDNUTS
    "groundnuts": CropRecommendation(
        crop_code="groundnuts",
        crop_name="Groundnuts (Mtedza)",
        yield_estimate=YieldEstimate(
            low_bags_per_acre=Decimal("6"),
            high_bags_per_acre=Decimal("15"),
            unit="50kg bags (unshelled)",
            conditions_note="Sandy loam soil, good pegging conditions",
        ),
        fertiliser_recommendation=FertiliserRecommendation(
            stages=[
                FertiliserStage(
                    stage_name="Basal",
                    timing="At planting",
                    fertiliser_type="SSP (Single Super Phosphate)",
                    kg_per_acre_low=Decimal("40"),
                    kg_per_acre_high=Decimal("60"),
                    notes="Groundnuts need calcium; gypsum is beneficial",
                ),
            ],
            ratio_note="Focus on P and Ca; avoid excess N which promotes foliage over pods",
        ),
        seed_rate_kg_per_acre=Decimal("40"),
        recommended_varieties=["CG7", "Chalimbana", "Nsinjiro"],
        planting_window="Dec 1 - Jan 31",
    ),

    # TOBACCO
    "tobacco": CropRecommendation(
        crop_code="tobacco",
        crop_name="Tobacco (Fodya)",
        yield_estimate=YieldEstimate(
            low_bags_per_acre=Decimal("400"),
            high_bags_per_acre=Decimal("800"),
            unit="kg (green leaf)",
            conditions_note="Good curing facilities, proper grading",
        ),
        fertiliser_recommendation=FertiliserRecommendation(
            stages=[
                FertiliserStage(
                    stage_name="Basal",
                    timing="At transplanting",
                    fertiliser_type="Tobacco Compound (D or S)",
                    kg_per_acre_low=Decimal("80"),
                    kg_per_acre_high=Decimal("100"),
                    notes="Apply in planting holes",
                ),
                FertiliserStage(
                    stage_name="Top-dressing",
                    timing="4-6 weeks after transplanting",
                    fertiliser_type="CAN",
                    kg_per_acre_low=Decimal("60"),
                    kg_per_acre_high=Decimal("80"),
                    notes="Split into 2 applications if high rainfall",
                ),
            ],
            ratio_note="Tobacco needs balanced nutrition; avoid chloride fertilisers",
        ),
        seed_rate_kg_per_acre=None,  # Transplants
        recommended_varieties=["KRK1", "CC27", "CC35"],
        planting_window="Aug-Sep (nursery), Oct-Dec (transplant)",
    ),

    # RICE
    "rice": CropRecommendation(
        crop_code="rice",
        crop_name="Rice (Mpunga)",
        yield_estimate=YieldEstimate(
            low_bags_per_acre=Decimal("10"),
            high_bags_per_acre=Decimal("25"),
            unit="50kg bags (paddy)",
            conditions_note="Irrigated/flooded conditions, good water management",
        ),
        fertiliser_recommendation=FertiliserRecommendation(
            stages=[
                FertiliserStage(
                    stage_name="Basal",
                    timing="At transplanting/seeding",
                    fertiliser_type="NPK 23:21:0+4S",
                    kg_per_acre_low=Decimal("40"),
                    kg_per_acre_high=Decimal("60"),
                    notes="Incorporate into puddled soil",
                ),
                FertiliserStage(
                    stage_name="Top-dressing",
                    timing="Tillering stage",
                    fertiliser_type="Urea",
                    kg_per_acre_low=Decimal("40"),
                    kg_per_acre_high=Decimal("60"),
                    notes="Apply when field is drained",
                ),
            ],
        ),
        seed_rate_kg_per_acre=Decimal("25"),
        recommended_varieties=["Faya", "Kilombero", "NERICA"],
        planting_window="Dec-Feb (rainfed), various (irrigated)",
    ),

    # BEANS
    "beans": CropRecommendation(
        crop_code="beans",
        crop_name="Common Beans (Nyemba)",
        yield_estimate=YieldEstimate(
            low_bags_per_acre=Decimal("4"),
            high_bags_per_acre=Decimal("10"),
            unit="50kg bags",
            conditions_note="Cool highlands, disease-free seed",
        ),
        fertiliser_recommendation=FertiliserRecommendation(
            stages=[
                FertiliserStage(
                    stage_name="Basal",
                    timing="At planting",
                    fertiliser_type="D-Compound",
                    kg_per_acre_low=Decimal("20"),
                    kg_per_acre_high=Decimal("40"),
                    notes="Legume crop - minimal N needed",
                ),
            ],
        ),
        seed_rate_kg_per_acre=Decimal("35"),
        recommended_varieties=["Kalima", "Sugar Beans", "Napilira"],
        planting_window="Feb-Mar (relay) or Dec-Jan (sole)",
    ),

    # CASSAVA
    "cassava": CropRecommendation(
        crop_code="cassava",
        crop_name="Cassava (Chinangwa)",
        yield_estimate=YieldEstimate(
            low_bags_per_acre=Decimal("80"),
            high_bags_per_acre=Decimal("160"),
            unit="50kg bags (fresh roots)",
            conditions_note="12-18 months growth, well-drained soils",
        ),
        fertiliser_recommendation=FertiliserRecommendation(
            stages=[
                FertiliserStage(
                    stage_name="Basal (optional)",
                    timing="At planting",
                    fertiliser_type="NPK 23:21:0+4S",
                    kg_per_acre_low=Decimal("20"),
                    kg_per_acre_high=Decimal("40"),
                    notes="Cassava is often grown without fertiliser in Malawi",
                ),
            ],
        ),
        seed_rate_kg_per_acre=None,  # Cuttings
        recommended_varieties=["Mbundumali", "Sauti", "Improved varieties"],
        planting_window="Oct-Dec (with rains)",
    ),

    # SWEET POTATO
    "sweet_potato": CropRecommendation(
        crop_code="sweet_potato",
        crop_name="Sweet Potato (Mbatata)",
        yield_estimate=YieldEstimate(
            low_bags_per_acre=Decimal("40"),
            high_bags_per_acre=Decimal("100"),
            unit="50kg bags (fresh)",
            conditions_note="3-5 months growth, well-drained ridges",
        ),
        fertiliser_recommendation=FertiliserRecommendation(
            stages=[
                FertiliserStage(
                    stage_name="Basal (optional)",
                    timing="Before ridging",
                    fertiliser_type="NPK 10:20:20",
                    kg_per_acre_low=Decimal("20"),
                    kg_per_acre_high=Decimal("40"),
                    notes="Focus on K for root development",
                ),
            ],
        ),
        seed_rate_kg_per_acre=None,  # Vines
        recommended_varieties=["Kenya", "Zondeni", "Orange-fleshed varieties"],
        planting_window="Dec-Feb",
    ),

    # VEGETABLES (generic)
    "vegetables": CropRecommendation(
        crop_code="vegetables",
        crop_name="Vegetables (Mixed)",
        yield_estimate=YieldEstimate(
            low_bags_per_acre=Decimal("50"),
            high_bags_per_acre=Decimal("200"),
            unit="50kg bags/crates",
            conditions_note="Varies by crop; irrigation recommended",
        ),
        fertiliser_recommendation=FertiliserRecommendation(
            stages=[
                FertiliserStage(
                    stage_name="Basal",
                    timing="Before transplanting",
                    fertiliser_type="D-Compound",
                    kg_per_acre_low=Decimal("40"),
                    kg_per_acre_high=Decimal("80"),
                    notes="Mix with compost/manure for best results",
                ),
                FertiliserStage(
                    stage_name="Top-dressing",
                    timing="2-3 weeks after transplanting",
                    fertiliser_type="CAN or Urea",
                    kg_per_acre_low=Decimal("20"),
                    kg_per_acre_high=Decimal("40"),
                    notes="Repeat every 2 weeks for leafy vegetables",
                ),
            ],
        ),
        seed_rate_kg_per_acre=None,  # Varies
        recommended_varieties=["Local adapted varieties"],
        planting_window="Year-round with irrigation",
    ),
}

# Default for unknown crops
DEFAULT_RECOMMENDATION = CropRecommendation(
    crop_code="other",
    crop_name="Other Crop",
    yield_estimate=YieldEstimate(
        low_bags_per_acre=Decimal("5"),
        high_bags_per_acre=Decimal("20"),
        unit="50kg bags",
        conditions_note="Varies by crop type and conditions",
    ),
    fertiliser_recommendation=FertiliserRecommendation(
        stages=[
            FertiliserStage(
                stage_name="General Basal",
                timing="At planting",
                fertiliser_type="NPK 23:21:0+4S",
                kg_per_acre_low=Decimal("30"),
                kg_per_acre_high=Decimal("50"),
            ),
        ],
    ),
)


# ==============================================================================
# PUBLIC API
# ==============================================================================

def get_crop_recommendation(crop_code: str) -> CropRecommendation:
    """
    Get recommendation profile for a crop.
    
    Args:
        crop_code: Crop code (e.g., "maize", "soya", "groundnuts")
    
    Returns:
        CropRecommendation with yield and fertiliser estimates
    """
    return CROP_RECOMMENDATIONS.get(crop_code.lower(), DEFAULT_RECOMMENDATION)


def estimate_yield_for_acres(crop_code: str, acres: Decimal) -> Dict[str, Any]:
    """
    Estimate yield range for given acreage.
    
    Args:
        crop_code: Crop code
        acres: Number of acres planted
    
    Returns:
        Dict with yield estimates and notes
    """
    rec = get_crop_recommendation(crop_code)
    yield_est = rec.yield_estimate
    
    return {
        "crop_name": rec.crop_name,
        "acres": float(acres),
        "low_estimate": float(yield_est.low_bags_per_acre * acres),
        "high_estimate": float(yield_est.high_bags_per_acre * acres),
        "unit": yield_est.unit,
        "conditions_note": yield_est.conditions_note,
        "disclaimer": rec.disclaimer,
    }


def estimate_fertiliser_for_acres(crop_code: str, acres: Decimal) -> Dict[str, Any]:
    """
    Estimate fertiliser requirements for given acreage.
    
    Args:
        crop_code: Crop code
        acres: Number of acres planted
    
    Returns:
        Dict with fertiliser stages and totals
    """
    rec = get_crop_recommendation(crop_code)
    fert_rec = rec.fertiliser_recommendation
    
    stages = []
    total_low = Decimal("0")
    total_high = Decimal("0")
    
    for stage in fert_rec.stages:
        stage_low = stage.kg_per_acre_low * acres
        stage_high = stage.kg_per_acre_high * acres
        total_low += stage_low
        total_high += stage_high
        
        stages.append({
            "stage_name": stage.stage_name,
            "timing": stage.timing,
            "fertiliser_type": stage.fertiliser_type,
            "kg_low": float(stage_low),
            "kg_high": float(stage_high),
            "notes": stage.notes,
        })
    
    return {
        "crop_name": rec.crop_name,
        "acres": float(acres),
        "stages": stages,
        "total_kg_low": float(total_low),
        "total_kg_high": float(total_high),
        "ratio_note": fert_rec.ratio_note,
        "disclaimer": rec.disclaimer,
    }


def get_full_recommendation(crop_code: str, acres: Decimal) -> Dict[str, Any]:
    """
    Get complete recommendation for a crop and acreage.
    
    Args:
        crop_code: Crop code
        acres: Number of acres
    
    Returns:
        Dict with yield, fertiliser, and variety recommendations
    """
    rec = get_crop_recommendation(crop_code)
    
    return {
        "crop_code": rec.crop_code,
        "crop_name": rec.crop_name,
        "acres": float(acres),
        "yield_estimate": estimate_yield_for_acres(crop_code, acres),
        "fertiliser_estimate": estimate_fertiliser_for_acres(crop_code, acres),
        "seed_rate_kg_per_acre": float(rec.seed_rate_kg_per_acre) if rec.seed_rate_kg_per_acre else None,
        "seed_total_kg": float(rec.seed_rate_kg_per_acre * acres) if rec.seed_rate_kg_per_acre else None,
        "recommended_varieties": rec.recommended_varieties or [],
        "planting_window": rec.planting_window,
        "disclaimer": rec.disclaimer,
    }


def create_draft_expense_items(
    crop_code: str,
    acres: Decimal,
    use_high_estimate: bool = False
) -> List[Dict[str, Any]]:
    """
    Create draft expense items based on fertiliser recommendations.
    
    These can be saved as FarmLedgerEntry records or displayed as suggestions.
    
    Args:
        crop_code: Crop code
        acres: Number of acres
        use_high_estimate: If True, use high estimates; otherwise use low
    
    Returns:
        List of draft expense item dicts
    """
    rec = get_crop_recommendation(crop_code)
    fert_rec = rec.fertiliser_recommendation
    
    expense_items = []
    for stage in fert_rec.stages:
        if use_high_estimate:
            kg_needed = stage.kg_per_acre_high * acres
        else:
            kg_needed = stage.kg_per_acre_low * acres
        
        expense_items.append({
            "category": "fertiliser",
            "description": f"{stage.fertiliser_type} - {stage.stage_name}",
            "quantity": float(kg_needed),
            "unit": "kg",
            "notes": f"{stage.timing}. {stage.notes}",
            "is_draft": True,
            "from_recommendation": True,
        })
    
    return expense_items


def get_available_crops() -> List[Dict[str, str]]:
    """
    Get list of available crop codes for UI selection.
    
    Returns:
        List of {code, name} dicts
    """
    return [
        {"code": rec.crop_code, "name": rec.crop_name}
        for rec in CROP_RECOMMENDATIONS.values()
    ]

