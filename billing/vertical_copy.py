# billing/vertical_copy.py
"""
Vertical-Aware Billing Copy Map (SSOT)

Maps vertical-specific terminology for billing pages to ensure
consistent and appropriate language across different business types.

Usage:
    from billing.vertical_copy import get_billing_copy
    
    copy = get_billing_copy("farm")
    # copy.location_singular -> "farm"
    # copy.staff_plural -> "assistant managers"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class VerticalBillingCopy:
    """Billing copy for a specific vertical."""
    vertical: str
    
    # Location terminology
    location_singular: str  # "shop" / "farm" / "gym"
    location_plural: str    # "shops" / "farms" / "gyms"
    
    # Staff terminology
    staff_singular: str     # "agent" / "assistant manager" / "trainer"
    staff_plural: str       # "agents" / "assistant managers" / "trainers"
    
    # Business terminology
    business_noun: str      # "business" / "farm" / "gym"
    
    # Plan description template
    plan_description_template: str  # "Includes 1 {location} and up to {n} {staff}"
    
    def format_plan_description(self, max_locations: int, max_staff: int) -> str:
        """Format the plan description with limits."""
        loc = self.location_singular if max_locations == 1 else self.location_plural
        staff = self.staff_singular if max_staff == 1 else self.staff_plural
        
        if max_locations == 1 and max_staff == 0:
            return f"Includes 1 {loc}, no {self.staff_plural}"
        elif max_locations == 1:
            return f"Includes 1 {loc} and up to {max_staff} {staff}"
        elif max_locations == -1:  # Unlimited
            return f"Unlimited {self.location_plural} and {self.staff_plural}"
        else:
            return f"Includes {max_locations} {loc} and up to {max_staff} {staff}"


# ==============================================================================
# VERTICAL COPY DEFINITIONS
# ==============================================================================

VERTICAL_COPY_MAP: dict[str, VerticalBillingCopy] = {
    # Farm vertical - uses "farm" and "assistant managers"
    "farm": VerticalBillingCopy(
        vertical="farm",
        location_singular="farm",
        location_plural="farms",
        staff_singular="assistant manager",
        staff_plural="assistant managers",
        business_noun="farm",
        plan_description_template="Includes {locations} and up to {staff}",
    ),
    
    # Gym vertical - uses "gym" and "trainers"
    "gym": VerticalBillingCopy(
        vertical="gym",
        location_singular="gym",
        location_plural="gyms",
        staff_singular="trainer",
        staff_plural="trainers",
        business_noun="gym",
        plan_description_template="Includes {locations} and up to {staff}",
    ),
    
    # Phones vertical - uses "shop" and "agents"
    "phones": VerticalBillingCopy(
        vertical="phones",
        location_singular="shop",
        location_plural="shops",
        staff_singular="agent",
        staff_plural="agents",
        business_noun="business",
        plan_description_template="Includes {locations} and up to {staff}",
    ),
    
    # Clothing vertical - uses "shop" and "agents"
    "clothing": VerticalBillingCopy(
        vertical="clothing",
        location_singular="shop",
        location_plural="shops",
        staff_singular="agent",
        staff_plural="agents",
        business_noun="business",
        plan_description_template="Includes {locations} and up to {staff}",
    ),
    
    # Cement vertical - uses "depot" and "agents"
    "cement": VerticalBillingCopy(
        vertical="cement",
        location_singular="depot",
        location_plural="depots",
        staff_singular="agent",
        staff_plural="agents",
        business_noun="business",
        plan_description_template="Includes {locations} and up to {staff}",
    ),
    
    # Liquor vertical - uses "bar" and "barmen"
    "liquor": VerticalBillingCopy(
        vertical="liquor",
        location_singular="bar",
        location_plural="bars",
        staff_singular="barman",
        staff_plural="barmen",
        business_noun="business",
        plan_description_template="Includes {locations} and up to {staff}",
    ),
    
    # Pharmacy vertical - uses "pharmacy" and "staff"
    "pharmacy": VerticalBillingCopy(
        vertical="pharmacy",
        location_singular="pharmacy",
        location_plural="pharmacies",
        staff_singular="staff member",
        staff_plural="staff members",
        business_noun="pharmacy",
        plan_description_template="Includes {locations} and up to {staff}",
    ),
    
    # Groceries vertical - uses "store" and "agents"
    "groceries": VerticalBillingCopy(
        vertical="groceries",
        location_singular="store",
        location_plural="stores",
        staff_singular="agent",
        staff_plural="agents",
        business_noun="store",
        plan_description_template="Includes {locations} and up to {staff}",
    ),
    
    # Welding vertical - uses "workshop" and "welders"
    "welding": VerticalBillingCopy(
        vertical="welding",
        location_singular="workshop",
        location_plural="workshops",
        staff_singular="welder",
        staff_plural="welders",
        business_noun="workshop",
        plan_description_template="Includes {locations} and up to {staff}",
    ),
}

# Default copy for unknown verticals (uses shop/agents)
DEFAULT_BILLING_COPY = VerticalBillingCopy(
    vertical="default",
    location_singular="shop",
    location_plural="shops",
    staff_singular="agent",
    staff_plural="agents",
    business_noun="business",
    plan_description_template="Includes {locations} and up to {staff}",
)


def get_billing_copy(vertical: Optional[str]) -> VerticalBillingCopy:
    """
    Get billing copy for a vertical.
    
    Args:
        vertical: Vertical code (e.g., "farm", "gym", "phones")
    
    Returns:
        VerticalBillingCopy with appropriate terminology
        Falls back to default (shop/agents) if vertical unknown.
    """
    if not vertical:
        return DEFAULT_BILLING_COPY
    
    return VERTICAL_COPY_MAP.get(vertical.lower(), DEFAULT_BILLING_COPY)


def get_billing_copy_for_business(business) -> VerticalBillingCopy:
    """
    Get billing copy for a business object.
    
    Args:
        business: Business model instance with business_kind attribute
    
    Returns:
        VerticalBillingCopy with appropriate terminology
    """
    if not business:
        return DEFAULT_BILLING_COPY
    
    # Get business_kind - handle both string and enum
    kind = getattr(business, "business_kind", None)
    if kind is None:
        return DEFAULT_BILLING_COPY
    
    # Convert enum to string if needed
    if hasattr(kind, "value"):
        kind = kind.value
    
    return get_billing_copy(str(kind).lower())

