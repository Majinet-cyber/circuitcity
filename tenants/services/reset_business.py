# tenants/services/reset_business.py
"""
Service for resetting business operational data.

Wipes all sales, stock, and operational records while preserving:
- Business tenant record
- Locations
- User accounts + memberships
- Subscription/billing state
- Branding/settings
"""
from __future__ import annotations

import logging
from typing import Optional

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction

from tenants.models import Business

logger = logging.getLogger(__name__)
User = get_user_model()


# Explicit allowlist of models to reset (operational data only)
RESETTABLE_MODELS = [
    # Sales
    ("sales", "Sale"),
    ("sales", "SaleLine"),
    ("sales", "SaleCommission"),
    
    # Inventory - Stock
    ("inventory", "Stock"),  # If exists
    ("inventory", "StockMovement"),  # If exists
    ("inventory", "InventoryItem"),
    ("inventory", "MerchProduct"),
    ("inventory", "StockActivityLog"),
    
    # Vertical-specific operational data
    ("inventory", "LiquorSale"),
    ("inventory", "LiquorSaleLine"),
    ("inventory", "LiquorShift"),
    ("inventory", "LiquorShiftStock"),
    ("inventory", "PharmacySale"),
    ("inventory", "PharmacySaleLine"),
    ("inventory", "PharmacyBatch"),
    ("inventory", "GymMember"),
    ("inventory", "GymPayment"),
    ("inventory", "GymMemberLog"),
    ("inventory", "GymCheckin"),
    
    # Expenses/Costs
    ("cfo", "Expense"),
    
    # Wallet transactions (operational)
    ("wallet", "WalletTransaction"),
    ("wallet", "AgentWalletTransaction"),
    
    # Shifts/Sessions
    ("inventory", "ShiftSession"),
    ("timelogs", "TimeLog"),  # If exists
    
    # Accessories (if exists)
    ("inventory", "AccessoryStock"),
    ("inventory", "AccessoryStockLog"),
    
    # Layby (if exists)
    ("layby", "Layby"),  # If exists
    ("layby", "LaybyPayment"),  # If exists
]


def reset_business_data(
    business: Business,
    *,
    initiated_by: User,
    keep_catalog: bool = False,
) -> dict:
    """
    Reset all operational data for a business.
    
    Deletes:
    - All sales and sale lines
    - All inventory stock
    - All stock movements
    - All expenses
    - All vertical-specific operational data (liquor, pharmacy, gym, etc.)
    - All wallet transactions
    - All shifts/sessions
    
    Preserves:
    - Business record
    - Locations
    - User accounts and memberships
    - Subscription/billing
    - Branding/settings
    - Product catalog (if keep_catalog=True)
    
    Args:
        business: Business instance to reset
        initiated_by: User performing the reset (must be owner or superuser)
        keep_catalog: If True, preserve product catalog; if False, delete it too
    
    Returns:
        dict with counts of deleted records per model
    
    Raises:
        PermissionError: If user is not authorized
        ValueError: If business is invalid
    """
    # Permission check
    if not initiated_by.is_superuser:
        # Check if user is a manager/owner of this business
        from tenants.scope import get_membership
        membership = get_membership(initiated_by, business)
        if not membership or membership.role != "MANAGER" or membership.status != "ACTIVE":
            raise PermissionError("Only business owners/managers or superusers can reset business data")
    
    if not business:
        raise ValueError("Business is required")
    
    deleted_counts = {}
    
    with transaction.atomic():
        # Delete each resettable model
        for app_label, model_name in RESETTABLE_MODELS:
            try:
                Model = apps.get_model(app_label, model_name)
            except LookupError:
                # Model doesn't exist (optional models)
                logger.debug(f"Model {app_label}.{model_name} not found, skipping")
                continue
            
            # Determine filter field
            # Most models use business FK directly
            # Some use location__business
            if hasattr(Model, "business"):
                qs = Model.all_objects.filter(business=business)
            elif hasattr(Model, "location"):
                qs = Model.all_objects.filter(location__business=business)
            elif hasattr(Model, "item") and hasattr(Model.item, "business"):
                # For models that reference items with business
                qs = Model.all_objects.filter(item__business=business)
            elif model_name == "Sale":
                # Sale model: filter by location__business (Sale has location FK)
                qs = Model.all_objects.filter(location__business=business)
            else:
                logger.warning(f"Could not determine filter for {app_label}.{model_name}, skipping")
                continue
            
            count = qs.count()
            if count > 0:
                qs.delete()
                deleted_counts[f"{app_label}.{model_name}"] = count
                logger.info(f"Deleted {count} {app_label}.{model_name} records for business {business.id}")
        
        # Delete product catalog if requested
        if not keep_catalog:
            try:
                Product = apps.get_model("inventory", "Product")
                product_count = Product.all_objects.filter(business=business).count()
                if product_count > 0:
                    Product.all_objects.filter(business=business).delete()
                    deleted_counts["inventory.Product"] = product_count
                    logger.info(f"Deleted {product_count} products for business {business.id}")
            except Exception as e:
                logger.warning(f"Could not delete products: {e}")
        
        # Log the reset
        logger.info(
            f"Business {business.id} ({business.name}) reset by user {initiated_by.id}. "
            f"Deleted {sum(deleted_counts.values())} total records across {len(deleted_counts)} models."
        )
    
    return deleted_counts

