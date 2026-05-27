from django.db import models


class BusinessKind(models.TextChoices):
    """
    Business vertical choices for signup and vertical-aware routing.

    CANONICAL CODES (stored in DB):
    ================================
    - phones: Phones & Electronics
    - liquor: Liquor / Bar
    - grocery: Grocery / General
    - pharmacy: Cosmetics & Pharmacy
    - clothing: Clothing
    - gym: Gym / Fitness
    - hardware: Hardware & General Dealers (NEW - standalone vertical)
    - cement: Cement / Building Materials (legacy, kept for backward compatibility)

    CRITICAL: Hardware is now a separate canonical vertical from cement.
    - hardware → generic retail flows (Dashboard, Stock, Scan In, Sell, etc.)
    - cement → specialized cement/building materials flows (if needed)

    Display names are managed in inventory.utils_verticals.get_vertical_display_name()
    """

    PHONES = "phones", "Phones & Electronics"
    LIQUOR = "liquor", "Liquor / Bar"
    GROCERY = "grocery", "Grocery / General"
    PHARMACY = "pharmacy", "Cosmetics & Pharmacy"
    CLOTHING = "clothing", "Clothing"
    GYM = "gym", "Gym / Fitness"
    HARDWARE = "hardware", "Hardware & General Dealers"  # NEW: Standalone hardware vertical
    CEMENT = "cement", "Cement / Building Materials"  # Legacy: Kept for backward compatibility
    FARM = "farm", "Farm Manager"  # NEW: Farm profitability tracking
    WELDING = "welding", "Welding Workshop"  # NEW: Welding job estimation & invoicing
    CAR_HIRE = "car_hire", "Car Hire Service"  # NEW: Fleet management & trip bookings
    CAR_DEALER = "car_dealer", "Car Dealer"  # NEW: Vehicle dealership & marketplace
    ENERGY = "energy", "Renewable Energy"  # NEW: Solar, battery & energy management
    MOBILE_MONEY = "mobile_money", "Mobile Money Agent"  # NEW: Mobile money agent reconciliation
    MIXED_RETAIL = "mixed_retail", "Mixed Retail"  # NEW: Multi-department retail (clothing+electronics+furniture+etc.)
    CONSULTANCY = "consultancy", "Consultancy & Services"  # NEW: Consulting, freelance, agencies, repair, advisory
    BUTCHERY = "butchery", "Butchery"  # NEW: Butchery / meat shop with intake, processing & cut-based sales


__all__ = ["BusinessKind"]
