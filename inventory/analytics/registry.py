# inventory/analytics/registry.py
"""
Registry for analytics adapters by business vertical.
"""
from __future__ import annotations

import logging
from typing import Optional

from .adapters.base import AnalyticsAdapter
from .adapters.phones import PhonesAdapter
from .adapters.clothing import ClothingAdapter
from .adapters.pharmacy import PharmacyAdapter
from .adapters.liquor import LiquorAdapter
from .adapters.gym import GymAdapter

logger = logging.getLogger(__name__)

# Vertical normalization mapping for common variations/typos
_VERTICAL_NORMALIZATION = {
    'pharmacy_cosmetics': 'pharmacy',
    'cosmetics': 'pharmacy',
    'liqour': 'liquor',  # Common typo
    'liquour': 'liquor',  # Another typo variant
    'bar': 'liquor',
    'pub': 'liquor',
    'gym_fitness': 'gym',
    'fitness': 'gym',
    'clothing_apparel': 'clothing',
    'apparel': 'clothing',
    'phone': 'phones',
    'mobile': 'phones',
    'electronics': 'phones',
}


def normalize_vertical(vertical: str) -> str:
    """
    Normalize vertical string to canonical form.
    
    Args:
        vertical: Raw vertical string from business model
    
    Returns:
        Normalized vertical string
    """
    if not vertical:
        return 'phones'  # Default
    
    normalized = str(vertical).strip().lower()
    
    # Check normalization map first
    if normalized in _VERTICAL_NORMALIZATION:
        return _VERTICAL_NORMALIZATION[normalized]
    
    # Return as-is if already canonical
    return normalized


def get_adapter(vertical: str, business=None) -> AnalyticsAdapter:
    """
    Get analytics adapter for the given vertical.
    
    Args:
        vertical: Business vertical ('phones', 'clothing', 'pharmacy', 'liquor', 'gym')
        business: Optional business instance for logging
    
    Returns:
        AnalyticsAdapter instance for the vertical
    """
    raw_vertical = vertical
    vertical = normalize_vertical(vertical)
    
    adapter_map = {
        'phones': PhonesAdapter,
        'clothing': ClothingAdapter,
        'pharmacy': PharmacyAdapter,
        'liquor': LiquorAdapter,
        'gym': GymAdapter,
    }
    
    adapter_class = adapter_map.get(vertical)
    if not adapter_class:
        # Default to phones adapter for unknown verticals
        logger.warning(
            f"Unknown vertical '{vertical}' (raw: '{raw_vertical}'), "
            f"falling back to PhonesAdapter"
        )
        adapter_class = PhonesAdapter
    
    # Log adapter selection for debugging
    if business:
        logger.info(
            f"Adapter selection: business_id={getattr(business, 'id', None)}, "
            f"vertical_raw='{raw_vertical}', vertical_normalized='{vertical}', "
            f"adapter={adapter_class.__name__}"
        )
    else:
        logger.debug(
            f"Adapter selection: vertical_raw='{raw_vertical}', "
            f"vertical_normalized='{vertical}', adapter={adapter_class.__name__}"
        )
    
    return adapter_class()

