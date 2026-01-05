from django.db import models


class BusinessKind(models.TextChoices):
    """
    Business vertical choices for signup and vertical-aware routing.

    IMPORTANT FINDINGS (Hardware Vertical Upgrade):
    ================================================
    1. VERTICAL CODE STORED IN DB: business_kind field in tenants.models.Business
       - Value: "cement" (DO NOT RENAME - keeps data migration safe)

    2. DISPLAY NAME SOURCE OF TRUTH: inventory.utils_verticals.get_vertical_display_name()
       - Line 208-220 in inventory/utils_verticals.py
       - Currently returns "Cement Store" for "cement" vertical
       - THIS IS WHERE WE CHANGE THE UI DISPLAY NAME

    3. SIDEBAR MENU RENDERING: inventory.utils_verticals.get_vertical_sidebar_items()
       - Line 1345-1523 handles "cement" vertical sidebar
       - This is where we add the "Products" tab

    4. SIGNUP FORM CHOICES: This file (BusinessKind.choices) + circuitcity/accounts/forms.py
       - Line 456-460 in circuitcity/accounts/forms.py uses BusinessKind.choices
       - Templates: templates/accounts/signup_manager.html (lines 215-220)
       - Line 11 below controls the signup dropdown label

    5. URLs:
       - Cement dashboard: /verticals/cement/dashboard/ (verticals/urls.py line 121)
       - Cement operations: /cement/* (inventory/urls_cement.py)
       - View logic: inventory/verticals/cement.py
    """

    PHONES = "phones", "Phones & Electronics"
    LIQUOR = "liquor", "Liquor / Bar"
    GROCERY = "grocery", "Grocery / General"
    PHARMACY = "pharmacy", "Cosmetics & Pharmacy"
    CLOTHING = "clothing", "Clothing"
    GYM = "gym", "Gym / Fitness"
    CEMENT = "cement", "Hardware & General Dealers"  # RENAMED: Was "Cement / Hardware"


__all__ = ["BusinessKind"]
