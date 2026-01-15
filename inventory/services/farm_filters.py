# inventory/services/farm_filters.py
"""
Farm Manager filtering infrastructure.
Provides reusable filtering logic for dashboard, sales, expenses, reports, etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List

from django.db.models import QuerySet, Q
from django.utils import timezone
from django.http import HttpRequest


@dataclass
class FilterState:
    """
    Immutable filter state parsed from request.
    Represents active filters and their resolved values.
    """
    # Date range
    range_preset: str  # today, 7d, mtd, ytd, custom
    start_date: date
    end_date: date
    range_label: str  # For display: "Today", "Last 7 Days", etc.
    
    # Facet filters (nullable)
    season_id: Optional[int] = None
    crop_type: Optional[str] = None
    animal_type: Optional[str] = None
    location_id: Optional[int] = None
    
    # Query string for URL generation
    query_params: Dict[str, str] = None
    
    def __post_init__(self):
        if self.query_params is None:
            self.query_params = {}
    
    @property
    def is_filtered(self) -> bool:
        """Check if any filters are active beyond default date range."""
        return bool(
            self.season_id 
            or self.crop_type 
            or self.animal_type 
            or self.location_id
            or self.range_preset != "mtd"
        )
    
    @property
    def active_filter_chips(self) -> List[Dict[str, Any]]:
        """Return list of active filters for display as chips."""
        chips = []
        
        # Date range chip
        if self.range_preset != "mtd":
            chips.append({
                "type": "range",
                "label": self.range_label,
                "param": "range",
                "value": self.range_preset,
            })
        
        if self.season_id:
            chips.append({
                "type": "season",
                "label": f"Season ID: {self.season_id}",
                "param": "season",
                "value": str(self.season_id),
            })
        
        if self.crop_type:
            chips.append({
                "type": "crop",
                "label": f"Crop: {self.crop_type}",
                "param": "crop",
                "value": self.crop_type,
            })
        
        if self.animal_type:
            chips.append({
                "type": "animal",
                "label": f"Animal: {self.animal_type}",
                "param": "animal",
                "value": self.animal_type,
            })
        
        if self.location_id:
            chips.append({
                "type": "location",
                "label": f"Location ID: {self.location_id}",
                "param": "location",
                "value": str(self.location_id),
            })
        
        return chips


def parse_farm_filters(request: HttpRequest, business=None) -> FilterState:
    """
    Parse filter parameters from request GET params.
    
    Supported params:
      - range: today | 7d | mtd | ytd | custom
      - start: YYYY-MM-DD (for custom range)
      - end: YYYY-MM-DD (for custom range)
      - season: season ID
      - crop: crop type string
      - animal: animal type string
      - location: location ID
    
    Returns:
        FilterState with resolved dates and facets
    """
    today = timezone.now().date()
    
    # Parse date range preset
    range_preset = request.GET.get("range", "mtd").lower()
    
    # Default to MTD (Month To Date)
    if range_preset == "today":
        start_date = today
        end_date = today
        range_label = "Today"
    elif range_preset == "7d":
        start_date = today - timedelta(days=7)
        end_date = today
        range_label = "Last 7 Days"
    elif range_preset == "ytd":
        start_date = date(today.year, 1, 1)
        end_date = today
        range_label = "This Year (YTD)"
    elif range_preset == "custom":
        # Custom date range from GET params
        start_str = request.GET.get("start", "")
        end_str = request.GET.get("end", "")
        
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date() if start_str else today.replace(day=1)
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date() if end_str else today
        except ValueError:
            # Fallback to MTD on invalid dates
            start_date = today.replace(day=1)
            end_date = today
            range_preset = "mtd"
        
        range_label = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
    else:
        # Default: MTD (Month To Date)
        range_preset = "mtd"
        start_date = today.replace(day=1)
        end_date = today
        range_label = "This Month (MTD)"
    
    # Parse facet filters
    season_id = None
    season_param = request.GET.get("season", "")
    if season_param and season_param.isdigit():
        season_id = int(season_param)
    
    crop_type = request.GET.get("crop", "") or None
    animal_type = request.GET.get("animal", "") or None
    
    location_id = None
    location_param = request.GET.get("location", "")
    if location_param and location_param.isdigit():
        location_id = int(location_param)
    
    # Build query params dict for URL generation
    query_params = {"range": range_preset}
    
    if range_preset == "custom":
        query_params["start"] = start_date.strftime("%Y-%m-%d")
        query_params["end"] = end_date.strftime("%Y-%m-%d")
    
    if season_id:
        query_params["season"] = str(season_id)
    if crop_type:
        query_params["crop"] = crop_type
    if animal_type:
        query_params["animal"] = animal_type
    if location_id:
        query_params["location"] = str(location_id)
    
    return FilterState(
        range_preset=range_preset,
        start_date=start_date,
        end_date=end_date,
        range_label=range_label,
        season_id=season_id,
        crop_type=crop_type,
        animal_type=animal_type,
        location_id=location_id,
        query_params=query_params,
    )


def apply_filters_to_ledger(
    queryset: QuerySet, 
    filter_state: FilterState
) -> QuerySet:
    """
    Apply FilterState to FarmLedgerEntry queryset.
    
    Args:
        queryset: Base FarmLedgerEntry queryset (already filtered by business)
        filter_state: Parsed filter state
    
    Returns:
        Filtered queryset
    """
    # Date range filter (always applied)
    queryset = queryset.filter(
        date__gte=filter_state.start_date,
        date__lte=filter_state.end_date,
    )
    
    # Season filter (crop sales/expenses)
    if filter_state.season_id:
        queryset = queryset.filter(crop_season_id=filter_state.season_id)
    
    # Crop type filter (via enterprise_type or linked season)
    if filter_state.crop_type:
        queryset = queryset.filter(
            Q(enterprise_type=filter_state.crop_type) |
            Q(crop_season__crop_type=filter_state.crop_type)
        )
    
    # Animal type filter (via enterprise_type or linked batch)
    if filter_state.animal_type:
        queryset = queryset.filter(
            Q(enterprise_type=filter_state.animal_type) |
            Q(livestock_batch__animal_type=filter_state.animal_type)
        )
    
    # Location filter
    if filter_state.location_id:
        queryset = queryset.filter(location_id=filter_state.location_id)
    
    return queryset


def apply_filters_to_seasons(
    queryset: QuerySet,
    filter_state: FilterState
) -> QuerySet:
    """
    Apply FilterState to FarmCropSeason queryset.
    """
    # Date range: filter by start_date overlap
    queryset = queryset.filter(
        Q(start_date__lte=filter_state.end_date) &
        (Q(end_date__gte=filter_state.start_date) | Q(end_date__isnull=True))
    )
    
    if filter_state.crop_type:
        queryset = queryset.filter(crop_type=filter_state.crop_type)
    
    if filter_state.location_id:
        queryset = queryset.filter(location_id=filter_state.location_id)
    
    return queryset


def apply_filters_to_livestock(
    queryset: QuerySet,
    filter_state: FilterState
) -> QuerySet:
    """
    Apply FilterState to FarmLivestockBatch queryset.
    """
    if filter_state.animal_type:
        queryset = queryset.filter(animal_type=filter_state.animal_type)
    
    if filter_state.location_id:
        queryset = queryset.filter(location_id=filter_state.location_id)
    
    return queryset


def get_available_filter_options(business) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get available filter options for the given business.
    Only returns options that have data (e.g., crops with seasons, animals with batches).
    
    Returns dict with:
        - crops: List of {value, label} dicts
        - animals: List of {value, label} dicts
        - seasons: List of {value, label, id} dicts
        - locations: List of {value, label, id} dicts
    """
    from inventory.models_farm import FarmCropSeason, FarmLivestockBatch, FarmCropType, FarmAnimalType
    from inventory.models import Location
    
    options = {
        "crops": [],
        "animals": [],
        "seasons": [],
        "locations": [],
    }
    
    if not business:
        return options
    
    # Get crops that have seasons
    existing_crop_types = (
        FarmCropSeason.objects
        .filter(business=business)
        .values_list("crop_type", flat=True)
        .distinct()
    )
    
    for crop_value, crop_label in FarmCropType.choices:
        if crop_value in existing_crop_types:
            options["crops"].append({
                "value": crop_value,
                "label": crop_label,
            })
    
    # Get animals that have batches
    existing_animal_types = (
        FarmLivestockBatch.objects
        .filter(business=business)
        .values_list("animal_type", flat=True)
        .distinct()
    )
    
    for animal_value, animal_label in FarmAnimalType.choices:
        if animal_value in existing_animal_types:
            options["animals"].append({
                "value": animal_value,
                "label": animal_label,
            })
    
    # Get active seasons
    seasons = (
        FarmCropSeason.objects
        .filter(business=business)
        .order_by("-start_date")[:20]
    )
    
    for season in seasons:
        options["seasons"].append({
            "id": season.id,
            "value": str(season.id),
            "label": season.name,
            "crop_type": season.crop_type,
        })
    
    # Get locations used by farm entries
    location_ids = set()
    
    # Locations from ledger entries
    from inventory.models_farm import FarmLedgerEntry
    ledger_locations = (
        FarmLedgerEntry.objects
        .filter(business=business, location__isnull=False)
        .values_list("location_id", flat=True)
        .distinct()
    )
    location_ids.update(ledger_locations)
    
    # Locations from seasons (use separate query to avoid sliced queryset issue)
    season_location_ids = (
        FarmCropSeason.objects
        .filter(business=business, location__isnull=False)
        .values_list("location_id", flat=True)
        .distinct()
    )
    location_ids.update(season_location_ids)
    
    # Locations from livestock
    batch_locations = (
        FarmLivestockBatch.objects
        .filter(business=business, location__isnull=False)
        .values_list("location_id", flat=True)
        .distinct()
    )
    location_ids.update(batch_locations)
    
    if location_ids:
        locations = Location.objects.filter(id__in=location_ids).order_by("name")
        for loc in locations:
            options["locations"].append({
                "id": loc.id,
                "value": str(loc.id),
                "label": loc.name,
            })
    
    return options

