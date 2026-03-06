# inventory/marketplace_vertical_config.py
"""
Vertical-aware marketplace configuration.

Each vertical defines:
- listing_fields: extra metadata fields shown/captured for listings
- cta_label: call-to-action button label on public listing page
- listing_type_label: what a "listing" is called in this vertical
- status_label_sold: what "sold" means in context
- hero_tagline: short tagline for the business public page
- show_price: whether to display price prominently
- show_location: whether location is important
- icon: Bootstrap icon class for this vertical in marketplace UI
"""
from __future__ import annotations

VERTICAL_MARKETPLACE_CONFIG: dict[str, dict] = {
    "phones": {
        "listing_fields": ["specs", "storage", "color", "condition", "network"],
        "cta_label": "Inquire / Buy",
        "listing_type_label": "Device",
        "status_label_sold": "Sold",
        "hero_tagline": "Browse phones, gadgets & electronics",
        "show_price": True,
        "show_location": True,
        "icon": "bi-phone",
        "metadata_labels": {
            "specs": "Specifications",
            "storage": "Storage / RAM",
            "color": "Colour",
            "condition": "Condition",
            "network": "Network / Carrier",
        },
    },
    "liquor": {
        "listing_fields": ["brand", "volume_ml", "alcohol_pct", "category"],
        "cta_label": "Order Now",
        "listing_type_label": "Product",
        "status_label_sold": "Sold Out",
        "hero_tagline": "Drinks, spirits & bar specials",
        "show_price": True,
        "show_location": True,
        "icon": "bi-cup-straw",
        "metadata_labels": {
            "brand": "Brand",
            "volume_ml": "Volume (ml)",
            "alcohol_pct": "Alcohol %",
            "category": "Category",
        },
    },
    "grocery": {
        "listing_fields": ["brand", "weight", "unit", "category"],
        "cta_label": "Order",
        "listing_type_label": "Product",
        "status_label_sold": "Out of Stock",
        "hero_tagline": "Fresh groceries & general goods",
        "show_price": True,
        "show_location": True,
        "icon": "bi-bag",
        "metadata_labels": {
            "brand": "Brand",
            "weight": "Weight / Size",
            "unit": "Unit",
            "category": "Category",
        },
    },
    "pharmacy": {
        "listing_fields": ["brand", "category", "form", "prescription_required"],
        "cta_label": "Inquire",
        "listing_type_label": "Product",
        "status_label_sold": "Out of Stock",
        "hero_tagline": "Health products, cosmetics & pharmacy",
        "show_price": True,
        "show_location": True,
        "icon": "bi-capsule",
        "metadata_labels": {
            "brand": "Brand",
            "category": "Category",
            "form": "Form (tablet, cream, etc.)",
            "prescription_required": "Prescription Required",
        },
    },
    "clothing": {
        "listing_fields": ["size", "color", "material", "gender", "age_group"],
        "cta_label": "Buy Now",
        "listing_type_label": "Item",
        "status_label_sold": "Sold",
        "hero_tagline": "Fashion, clothing & accessories",
        "show_price": True,
        "show_location": True,
        "icon": "bi-bag-heart",
        "metadata_labels": {
            "size": "Size",
            "color": "Colour",
            "material": "Material",
            "gender": "Gender",
            "age_group": "Age Group",
        },
    },
    "gym": {
        "listing_fields": ["program_type", "duration", "capacity", "schedule", "level"],
        "cta_label": "Join / Inquire",
        "listing_type_label": "Program / Service",
        "status_label_sold": "Full / Closed",
        "hero_tagline": "Gym programs, memberships & training",
        "show_price": True,
        "show_location": True,
        "icon": "bi-lightning",
        "metadata_labels": {
            "program_type": "Program Type",
            "duration": "Duration",
            "capacity": "Capacity",
            "schedule": "Schedule",
            "level": "Fitness Level",
        },
    },
    "hardware": {
        "listing_fields": ["brand", "category", "unit", "quantity_available"],
        "cta_label": "Inquire / Buy",
        "listing_type_label": "Product",
        "status_label_sold": "Out of Stock",
        "hero_tagline": "Hardware, tools & building materials",
        "show_price": True,
        "show_location": True,
        "icon": "bi-tools",
        "metadata_labels": {
            "brand": "Brand",
            "category": "Category",
            "unit": "Unit",
            "quantity_available": "Available Quantity",
        },
    },
    "cement": {
        "listing_fields": ["brand", "bag_weight", "quantity_available", "grade"],
        "cta_label": "Order",
        "listing_type_label": "Product",
        "status_label_sold": "Out of Stock",
        "hero_tagline": "Cement & building materials",
        "show_price": True,
        "show_location": True,
        "icon": "bi-bricks",
        "metadata_labels": {
            "brand": "Brand",
            "bag_weight": "Bag Weight",
            "quantity_available": "Bags Available",
            "grade": "Grade / Strength",
        },
    },
    "farm": {
        "listing_fields": ["produce_type", "unit", "quantity_available", "harvest_date", "farm_location"],
        "cta_label": "Order",
        "listing_type_label": "Produce / Goods",
        "status_label_sold": "Sold Out",
        "hero_tagline": "Fresh farm produce & agricultural goods",
        "show_price": True,
        "show_location": True,
        "icon": "bi-flower1",
        "metadata_labels": {
            "produce_type": "Produce Type",
            "unit": "Unit (kg, bag, crate)",
            "quantity_available": "Quantity Available",
            "harvest_date": "Harvest Date",
            "farm_location": "Farm Location",
        },
    },
    "welding": {
        "listing_fields": ["service_type", "material", "lead_time"],
        "cta_label": "Request Quote",
        "listing_type_label": "Service / Product",
        "status_label_sold": "Completed",
        "hero_tagline": "Welding, fabrication & metalwork",
        "show_price": True,
        "show_location": True,
        "icon": "bi-wrench-adjustable",
        "metadata_labels": {
            "service_type": "Service Type",
            "material": "Material",
            "lead_time": "Lead Time",
        },
    },
    "car_hire": {
        "listing_fields": [
            "seats", "transmission", "fuel_type", "rate_per_day",
            "rate_per_km", "pickup_location", "availability",
        ],
        "cta_label": "Book / Inquire",
        "listing_type_label": "Vehicle",
        "status_label_sold": "Unavailable",
        "hero_tagline": "Car hire, vehicle rentals & fleet",
        "show_price": True,
        "show_location": True,
        "icon": "bi-car-front",
        "metadata_labels": {
            "seats": "Seating Capacity",
            "transmission": "Transmission",
            "fuel_type": "Fuel Type",
            "rate_per_day": "Rate per Day",
            "rate_per_km": "Rate per KM",
            "pickup_location": "Pickup Location",
            "availability": "Availability",
        },
    },
    "car_dealer": {
        "listing_fields": [
            "make", "model", "year", "mileage", "transmission",
            "fuel_type", "color", "condition", "chassis_no",
        ],
        "cta_label": "Inquire",
        "listing_type_label": "Vehicle",
        "status_label_sold": "Sold",
        "hero_tagline": "Quality vehicles — browse our showroom",
        "show_price": True,
        "show_location": True,
        "icon": "bi-car-front-fill",
        "metadata_labels": {
            "make": "Make",
            "model": "Model",
            "year": "Year",
            "mileage": "Mileage (km)",
            "transmission": "Transmission",
            "fuel_type": "Fuel Type",
            "color": "Colour",
            "condition": "Condition",
            "chassis_no": "Chassis / VIN",
        },
    },
}

# Fallback config for unknown verticals
DEFAULT_CONFIG = {
    "listing_fields": [],
    "cta_label": "Inquire",
    "listing_type_label": "Listing",
    "status_label_sold": "Sold",
    "hero_tagline": "Browse our marketplace",
    "show_price": True,
    "show_location": True,
    "icon": "bi-shop",
    "metadata_labels": {},
}


def get_vertical_config(vertical: str | None) -> dict:
    """Return the marketplace config for the given vertical (falls back to DEFAULT_CONFIG)."""
    if not vertical:
        return DEFAULT_CONFIG
    return VERTICAL_MARKETPLACE_CONFIG.get(str(vertical).lower(), DEFAULT_CONFIG)


__all__ = [
    "VERTICAL_MARKETPLACE_CONFIG",
    "DEFAULT_CONFIG",
    "get_vertical_config",
]
