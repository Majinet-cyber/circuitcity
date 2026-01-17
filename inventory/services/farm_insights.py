# inventory/services/farm_insights.py
"""
Farm Insights Engine - Deterministic Rule-Based Recommendations

Generates prioritized recommendations for farm operations based on:
- Crop seasons (fertilizer schedules, yield estimates)
- Livestock batches (feed, vet, production estimates)
- Assets (maintenance reminders)

NO external API calls. All recommendations are rule-based with clear disclaimers.

Design: Configurable constants for easy adjustment to local agronomic advice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Any

from django.utils import timezone


# ==============================================================================
# CONFIGURATION CONSTANTS (SSOT for agronomic rules)
# ==============================================================================

class InsightPriority(Enum):
    """Priority levels for insights"""
    CRITICAL = "critical"   # Urgent action needed (within 3 days)
    HIGH = "high"           # Action needed this week
    MEDIUM = "medium"       # Recommended action within 2 weeks
    LOW = "low"             # Nice to have / planning


class InsightCategory(Enum):
    """Categories of insights"""
    FERTILIZER = "fertilizer"
    IRRIGATION = "irrigation"
    PEST_DISEASE = "pest_disease"
    HARVEST = "harvest"
    FEED = "feed"
    VETERINARY = "veterinary"
    PRODUCTION = "production"
    MAINTENANCE = "maintenance"
    PLANNING = "planning"


# Maize fertilizer schedule (weeks since planting)
# Based on common Malawi smallholder practices
MAIZE_FERTILIZER_SCHEDULE = {
    # week_range: (recommendation_key, npk_kg_per_acre, urea_kg_per_acre, notes)
    (2, 4): {
        "key": "first_top_dressing",
        "title": "Apply 1st top dressing (Maize)",
        "npk_per_acre": 25,  # kg NPK 23:21:0 per acre
        "urea_per_acre": 12.5,  # kg Urea per acre (ratio ~2:1)
        "bag_size_kg": 50,
        "notes": "Best practice window for 1st application. Apply when soil is moist.",
    },
    (5, 7): {
        "key": "second_top_dressing",
        "title": "Apply 2nd top dressing (Maize)",
        "npk_per_acre": 12.5,  # kg NPK per acre
        "urea_per_acre": 25,  # kg Urea per acre (ratio ~1:2)
        "bag_size_kg": 50,
        "notes": "Second application emphasizes nitrogen (Urea heavier).",
    },
}

# Default yield estimates per acre (bags of 50kg each)
CROP_YIELD_DEFAULTS = {
    "maize": {"min_bags_per_acre": 12, "max_bags_per_acre": 25, "avg_bags_per_acre": 18},
    "soya": {"min_bags_per_acre": 6, "max_bags_per_acre": 15, "avg_bags_per_acre": 10},
    "groundnuts": {"min_bags_per_acre": 8, "max_bags_per_acre": 20, "avg_bags_per_acre": 12},
    "tobacco": {"min_kg_per_acre": 800, "max_kg_per_acre": 2000, "avg_kg_per_acre": 1200},
    "beans": {"min_bags_per_acre": 4, "max_bags_per_acre": 12, "avg_bags_per_acre": 7},
}

# Livestock production defaults
LIVESTOCK_DEFAULTS = {
    "chickens": {
        "broiler": {
            "feed_kg_per_bird_per_week": 0.7,
            "expected_mortality_pct": 5,
            "weeks_to_market": 6,
            "avg_weight_at_market_kg": 2.0,
        },
        "layer": {
            "feed_kg_per_bird_per_week": 0.85,
            "expected_mortality_pct": 3,
            "weeks_to_laying": 18,
            "eggs_per_week": 5,
        },
    },
    "pigs": {
        "generic": {
            "feed_kg_per_pig_per_week": 10,
            "expected_mortality_pct": 3,
            "months_to_market": 6,
            "avg_weight_at_market_kg": 80,
        },
    },
    "goats": {
        "generic": {
            "feed_supplement_kg_per_week": 2,
            "expected_mortality_pct": 5,
            "months_to_market": 8,
            "avg_weight_at_market_kg": 25,
        },
    },
    "cattle": {
        "generic": {
            "feed_supplement_kg_per_week": 5,
            "expected_mortality_pct": 2,
            "months_to_market": 18,
            "avg_weight_at_market_kg": 350,
        },
    },
}

# Vet checkpoint reminders (weeks since batch start)
VET_CHECKPOINTS = {
    "chickens": [1, 2, 3, 4],  # Weekly vaccinations for first month
    "pigs": [4, 8, 12],  # Monthly checkpoints
    "goats": [4, 12, 24],  # Deworming schedule
    "cattle": [4, 12, 24, 48],  # Vaccination schedule
}


# ==============================================================================
# INSIGHT DATA CLASSES
# ==============================================================================

@dataclass
class FarmInsight:
    """A single farm recommendation/insight"""
    id: str  # Unique identifier
    title: str  # Action-oriented title
    reason: str  # Why this recommendation
    category: InsightCategory
    priority: InsightPriority
    
    # Optional details
    suggested_quantities: Optional[str] = None
    confidence_note: str = "Estimate—adjust to local extension advice & soil tests."
    
    # For CTA prefill
    season_id: Optional[int] = None
    batch_id: Optional[int] = None
    entry_prefill: Dict[str, Any] = field(default_factory=dict)
    
    # Display helpers
    icon: str = "bi-lightbulb"
    color: str = "blue"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "reason": self.reason,
            "category": self.category.value,
            "priority": self.priority.value,
            "suggested_quantities": self.suggested_quantities,
            "confidence_note": self.confidence_note,
            "season_id": self.season_id,
            "batch_id": self.batch_id,
            "entry_prefill": self.entry_prefill,
            "icon": self.icon,
            "color": self.color,
        }


# ==============================================================================
# INSIGHT GENERATION FUNCTIONS
# ==============================================================================

def generate_crop_insights(seasons: List[Any], today: date) -> List[FarmInsight]:
    """
    Generate insights for crop seasons.
    
    Args:
        seasons: List of FarmCropSeason objects (or dicts with same fields)
        today: Current date for calculations
    
    Returns:
        List of FarmInsight objects
    """
    insights = []
    
    for season in seasons:
        # Handle both objects and dicts
        if hasattr(season, "id"):
            season_id = season.id
            crop_type = getattr(season, "crop_type", "").lower()
            start_date = season.start_date
            area_value = float(getattr(season, "area_value", 1))
            status = getattr(season, "status", "active")
            name = getattr(season, "name", crop_type.title())
        else:
            season_id = season.get("id")
            crop_type = season.get("crop_type", "").lower()
            start_date = season.get("start_date")
            area_value = float(season.get("area_value", 1))
            status = season.get("status", "active")
            name = season.get("name", crop_type.title())
        
        # Skip non-active seasons
        if status not in ("active", "planning"):
            continue
        
        # Calculate weeks since planting
        if isinstance(start_date, str):
            from datetime import datetime
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        
        weeks_since_planting = max(0, (today - start_date).days // 7)
        
        # Maize-specific fertilizer recommendations
        if crop_type == "maize":
            for week_range, rec_data in MAIZE_FERTILIZER_SCHEDULE.items():
                min_week, max_week = week_range
                
                if min_week <= weeks_since_planting <= max_week:
                    # Calculate bags needed
                    npk_kg_total = rec_data["npk_per_acre"] * area_value
                    urea_kg_total = rec_data["urea_per_acre"] * area_value
                    bag_size = rec_data["bag_size_kg"]
                    
                    npk_bags = round(npk_kg_total / bag_size, 1)
                    urea_bags = round(urea_kg_total / bag_size, 1)
                    
                    # Determine priority based on week position
                    if weeks_since_planting == min_week:
                        priority = InsightPriority.HIGH
                    elif weeks_since_planting >= max_week:
                        priority = InsightPriority.CRITICAL
                    else:
                        priority = InsightPriority.MEDIUM
                    
                    insight = FarmInsight(
                        id=f"maize_fert_{rec_data['key']}_{season_id}",
                        title=rec_data["title"],
                        reason=f"Week {weeks_since_planting} since planting; {rec_data['notes']}",
                        category=InsightCategory.FERTILIZER,
                        priority=priority,
                        suggested_quantities=f"For {area_value:.1f} acres: NPK ~{npk_bags} bags, Urea ~{urea_bags} bags (50kg)",
                        season_id=season_id,
                        entry_prefill={
                            "type": "fertiliser",
                            "category": "fertiliser",
                            "notes": f"[AI Suggested] {rec_data['title']} - {rec_data['notes']}",
                            "quantity_npk": npk_bags,
                            "quantity_urea": urea_bags,
                        },
                        icon="bi-droplet-fill",
                        color="green",
                    )
                    insights.append(insight)
                    break  # Only one fertilizer rec per season at a time
        
        # Generic crop harvest reminder (if near expected end)
        if hasattr(season, "end_date") and season.end_date:
            days_to_end = (season.end_date - today).days
            if 0 < days_to_end <= 14:
                insights.append(FarmInsight(
                    id=f"harvest_reminder_{season_id}",
                    title=f"Prepare for harvest ({name})",
                    reason=f"Expected harvest in {days_to_end} days. Plan labor and storage.",
                    category=InsightCategory.HARVEST,
                    priority=InsightPriority.HIGH if days_to_end <= 7 else InsightPriority.MEDIUM,
                    season_id=season_id,
                    entry_prefill={
                        "type": "harvest",
                        "category": "harvest",
                        "notes": f"Harvest for {name}",
                    },
                    icon="bi-basket-fill",
                    color="amber",
                ))
    
    return insights


def generate_livestock_insights(batches: List[Any], today: date) -> List[FarmInsight]:
    """
    Generate insights for livestock batches.
    
    Args:
        batches: List of FarmLivestockBatch objects (or dicts)
        today: Current date
    
    Returns:
        List of FarmInsight objects
    """
    insights = []
    
    for batch in batches:
        # Handle both objects and dicts
        if hasattr(batch, "id"):
            batch_id = batch.id
            animal_type = getattr(batch, "animal_type", "").lower()
            created_at = batch.created_at
            count_current = getattr(batch, "count_current", 0)
            name = getattr(batch, "name", animal_type.title())
            is_active = getattr(batch, "is_active", True)
        else:
            batch_id = batch.get("id")
            animal_type = batch.get("animal_type", "").lower()
            created_at = batch.get("created_at", today)
            count_current = batch.get("count_current", 0)
            name = batch.get("name", animal_type.title())
            is_active = batch.get("is_active", True)
        
        if not is_active or count_current == 0:
            continue
        
        # Convert created_at to date
        if hasattr(created_at, "date"):
            start_date = created_at.date()
        elif isinstance(created_at, str):
            from datetime import datetime
            start_date = datetime.strptime(created_at[:10], "%Y-%m-%d").date()
        else:
            start_date = created_at
        
        weeks_since_start = max(0, (today - start_date).days // 7)
        
        # Get defaults for animal type
        animal_defaults = LIVESTOCK_DEFAULTS.get(animal_type, {})
        breed_defaults = animal_defaults.get("generic", animal_defaults.get("broiler", {}))
        
        # Feed reminder (weekly)
        if breed_defaults.get("feed_kg_per_bird_per_week") or breed_defaults.get("feed_kg_per_pig_per_week"):
            feed_rate = (
                breed_defaults.get("feed_kg_per_bird_per_week") or 
                breed_defaults.get("feed_kg_per_pig_per_week") or
                breed_defaults.get("feed_supplement_kg_per_week", 0)
            )
            weekly_feed_kg = count_current * feed_rate
            
            insights.append(FarmInsight(
                id=f"feed_schedule_{batch_id}",
                title=f"Weekly feed for {name}",
                reason=f"Estimated weekly feed requirement for {count_current} {animal_type}",
                category=InsightCategory.FEED,
                priority=InsightPriority.MEDIUM,
                suggested_quantities=f"~{weekly_feed_kg:.0f} kg/week ({feed_rate} kg per animal)",
                batch_id=batch_id,
                entry_prefill={
                    "type": "feed",
                    "category": "feed",
                    "notes": f"Weekly feed for {name}",
                    "quantity": weekly_feed_kg,
                },
                icon="bi-basket3-fill",
                color="amber",
            ))
        
        # Vet checkpoint reminders
        vet_weeks = VET_CHECKPOINTS.get(animal_type, [])
        for vet_week in vet_weeks:
            if weeks_since_start == vet_week or (weeks_since_start == vet_week + 1 and weeks_since_start <= vet_week + 1):
                insights.append(FarmInsight(
                    id=f"vet_checkpoint_{batch_id}_week{vet_week}",
                    title=f"Vet checkpoint for {name}",
                    reason=f"Week {vet_week} vaccination/health check schedule",
                    category=InsightCategory.VETERINARY,
                    priority=InsightPriority.HIGH,
                    batch_id=batch_id,
                    entry_prefill={
                        "type": "veterinary",
                        "category": "vet",
                        "notes": f"Week {vet_week} health check",
                    },
                    icon="bi-heart-pulse-fill",
                    color="red",
                ))
                break  # Only one vet reminder per batch
        
        # Mortality warning (if mortality rate expected)
        mortality_pct = breed_defaults.get("expected_mortality_pct", 0)
        if mortality_pct > 0 and weeks_since_start >= 1:
            expected_losses = int(count_current * (mortality_pct / 100))
            if expected_losses > 0:
                insights.append(FarmInsight(
                    id=f"mortality_warning_{batch_id}",
                    title=f"Monitor mortality ({name})",
                    reason=f"Expected ~{mortality_pct}% mortality rate. Record any deaths promptly.",
                    category=InsightCategory.VETERINARY,
                    priority=InsightPriority.LOW,
                    batch_id=batch_id,
                    entry_prefill={
                        "type": "death",
                        "category": "death",
                        "notes": f"Mortality tracking for {name}",
                    },
                    icon="bi-exclamation-triangle",
                    color="red",
                ))
    
    return insights


def generate_all_insights(
    business,
    seasons: Optional[List[Any]] = None,
    batches: Optional[List[Any]] = None,
    assets: Optional[List[Any]] = None,
    today: Optional[date] = None,
    limit: int = 10,
) -> List[FarmInsight]:
    """
    Generate all insights for a farm business.
    
    Args:
        business: Business object
        seasons: Optional list of crop seasons (will query if None)
        batches: Optional list of livestock batches (will query if None)
        assets: Optional list of assets (will query if None)
        today: Current date (defaults to now)
        limit: Maximum insights to return
    
    Returns:
        List of FarmInsight objects, sorted by priority
    """
    if today is None:
        today = timezone.now().date()
    
    all_insights = []
    
    # Query data if not provided
    if seasons is None:
        from inventory.models_farm import FarmCropSeason, FarmSeasonStatus
        seasons = list(FarmCropSeason.objects.filter(
            business=business,
            status__in=[FarmSeasonStatus.ACTIVE, FarmSeasonStatus.PLANNING],
        ))
    
    if batches is None:
        from inventory.models_farm import FarmLivestockBatch
        batches = list(FarmLivestockBatch.objects.filter(
            business=business,
            is_active=True,
        ))
    
    # Generate insights
    all_insights.extend(generate_crop_insights(seasons, today))
    all_insights.extend(generate_livestock_insights(batches, today))
    
    # Sort by priority (critical first, then high, medium, low)
    priority_order = {
        InsightPriority.CRITICAL: 0,
        InsightPriority.HIGH: 1,
        InsightPriority.MEDIUM: 2,
        InsightPriority.LOW: 3,
    }
    all_insights.sort(key=lambda x: priority_order.get(x.priority, 99))
    
    return all_insights[:limit]


# ==============================================================================
# ENTRY TYPE RECOMMENDATIONS (for smart Add Entry)
# ==============================================================================

# Entry types by season type
CROP_ENTRY_TYPES = [
    {"value": "fertiliser", "label": "Fertiliser", "icon": "bi-droplet-fill", "color": "green"},
    {"value": "weeding", "label": "Weeding", "icon": "bi-scissors", "color": "blue"},
    {"value": "irrigation", "label": "Irrigation", "icon": "bi-moisture", "color": "cyan"},
    {"value": "pest_disease", "label": "Pest/Disease", "icon": "bi-bug", "color": "red"},
    {"value": "harvest", "label": "Harvest", "icon": "bi-basket-fill", "color": "amber"},
    {"value": "sale", "label": "Sale", "icon": "bi-cash-coin", "color": "green"},
    {"value": "other", "label": "Other", "icon": "bi-three-dots", "color": "gray"},
]

LIVESTOCK_ENTRY_TYPES = [
    {"value": "feed", "label": "Feed", "icon": "bi-basket3-fill", "color": "amber"},
    {"value": "veterinary", "label": "Veterinary", "icon": "bi-heart-pulse-fill", "color": "red"},
    {"value": "birth", "label": "Births", "icon": "bi-plus-circle-fill", "color": "green"},
    {"value": "death", "label": "Deaths", "icon": "bi-dash-circle-fill", "color": "red"},
    {"value": "purchase", "label": "Purchase", "icon": "bi-cart-plus-fill", "color": "blue"},
    {"value": "sale", "label": "Sale", "icon": "bi-cash-coin", "color": "green"},
    {"value": "transfer", "label": "Transfer", "icon": "bi-arrow-left-right", "color": "purple"},
    {"value": "other", "label": "Other", "icon": "bi-three-dots", "color": "gray"},
]


def get_entry_types_for_season(season_type: str) -> List[Dict[str, str]]:
    """
    Get appropriate entry types based on season/batch type.
    
    Args:
        season_type: "crop" or "livestock"
    
    Returns:
        List of entry type options
    """
    if season_type == "livestock":
        return LIVESTOCK_ENTRY_TYPES
    return CROP_ENTRY_TYPES


def get_recommended_actions_for_season(
    season: Any,
    today: Optional[date] = None,
    limit: int = 4,
) -> List[FarmInsight]:
    """
    Get recommended actions for a specific season or batch.
    Used in the Add Entry smart recommendations panel.
    
    Args:
        season: FarmCropSeason or FarmLivestockBatch object
        today: Current date
        limit: Maximum recommendations
    
    Returns:
        List of FarmInsight objects specific to this season/batch
    """
    if today is None:
        today = timezone.now().date()
    
    insights = []
    
    # Determine if crop or livestock
    if hasattr(season, "crop_type"):
        # It's a crop season
        insights = generate_crop_insights([season], today)
    elif hasattr(season, "animal_type"):
        # It's a livestock batch
        insights = generate_livestock_insights([season], today)
    
    return insights[:limit]


def calculate_fertilizer_estimate(
    crop_type: str,
    area_acres: float,
    week_since_planting: int,
) -> Dict[str, Any]:
    """
    Calculate fertilizer estimates for a given crop and area.
    
    Args:
        crop_type: Crop type (e.g., "maize")
        area_acres: Area in acres
        week_since_planting: Weeks since planting
    
    Returns:
        Dict with NPK and Urea bag estimates
    """
    if crop_type.lower() != "maize":
        return {
            "has_recommendation": False,
            "message": f"Fertilizer schedule not available for {crop_type}. Use local extension advice.",
        }
    
    for week_range, rec_data in MAIZE_FERTILIZER_SCHEDULE.items():
        min_week, max_week = week_range
        if min_week <= week_since_planting <= max_week:
            npk_kg_total = rec_data["npk_per_acre"] * area_acres
            urea_kg_total = rec_data["urea_per_acre"] * area_acres
            bag_size = rec_data["bag_size_kg"]
            
            return {
                "has_recommendation": True,
                "stage": rec_data["key"],
                "title": rec_data["title"],
                "npk_bags": round(npk_kg_total / bag_size, 1),
                "urea_bags": round(urea_kg_total / bag_size, 1),
                "npk_kg": npk_kg_total,
                "urea_kg": urea_kg_total,
                "bag_size_kg": bag_size,
                "notes": rec_data["notes"],
                "disclaimer": "Estimate—adjust to local extension advice & soil tests.",
            }
    
    return {
        "has_recommendation": False,
        "message": f"Week {week_since_planting}: Outside recommended fertilizer windows.",
    }


def calculate_yield_estimate(
    crop_type: str,
    area_acres: float,
) -> Dict[str, Any]:
    """
    Calculate yield estimate for a given crop and area.
    
    Args:
        crop_type: Crop type (e.g., "maize")
        area_acres: Area in acres
    
    Returns:
        Dict with yield estimates
    """
    defaults = CROP_YIELD_DEFAULTS.get(crop_type.lower(), {})
    
    if not defaults:
        return {
            "has_estimate": False,
            "message": f"Yield estimates not available for {crop_type}.",
        }
    
    # Handle different units (bags vs kg)
    if "avg_bags_per_acre" in defaults:
        return {
            "has_estimate": True,
            "unit": "bags",
            "bag_size_kg": 50,
            "min_yield": round(defaults["min_bags_per_acre"] * area_acres, 1),
            "max_yield": round(defaults["max_bags_per_acre"] * area_acres, 1),
            "avg_yield": round(defaults["avg_bags_per_acre"] * area_acres, 1),
            "disclaimer": "Estimate based on good conditions. Actual yield varies by soil, weather, and inputs.",
        }
    elif "avg_kg_per_acre" in defaults:
        return {
            "has_estimate": True,
            "unit": "kg",
            "min_yield": round(defaults["min_kg_per_acre"] * area_acres, 1),
            "max_yield": round(defaults["max_kg_per_acre"] * area_acres, 1),
            "avg_yield": round(defaults["avg_kg_per_acre"] * area_acres, 1),
            "disclaimer": "Estimate based on good conditions. Actual yield varies by soil, weather, and inputs.",
        }
    
    return {
        "has_estimate": False,
        "message": "Yield data not configured.",
    }

