# tenants/helpers_location_summary.py
"""
Helper functions to compute stock/member summaries per location for different verticals.
Used by the manager_locations view to show vertical-aware data.
"""
from __future__ import annotations
from typing import Dict, List, Any
from django.db.models import Count, Q


def get_phones_stock_summary(business, locations: List) -> Dict[int, Dict[str, int]]:
    """
    Compute stock summary for phones vertical.
    Returns: {location_id: {"sold": int, "in_stock": int, "total": int}}
    """
    stock_summary = {}
    
    try:
        from inventory.models import InventoryItem
        from sales.models import Sale
        
        for loc in locations:
            loc_id = getattr(loc, "id", None)
            if not loc_id:
                continue
            
            # In stock count
            in_stock = InventoryItem.objects.filter(
                business=business,
                current_location_id=loc_id,
                status="IN_STOCK",
                is_active=True
            ).count()
            
            # Sold count (via Sales)
            sold = Sale.objects.filter(
                location_id=loc_id,
                location__business=business
            ).count()
            
            # Total = in_stock + sold
            total = in_stock + sold
            
            stock_summary[loc_id] = {
                "sold": sold,
                "in_stock": in_stock,
                "total": total,
            }
    except Exception:
        # If models not available, return empty
        pass
    
    return stock_summary


def get_liquor_stock_summary(business, locations: List) -> Dict[int, Dict[str, int]]:
    """
    Compute stock summary for liquor vertical.
    Returns: {location_id: {"sold": int, "in_stock": int, "total": int}}
    
    - Sold: Count of bottles sold via LiquorSale (where unit="bottle")
    - In Stock: Count of bottles from latest LiquorShiftStock snapshots
    - Total: sold + in_stock
    """
    stock_summary = {}
    
    try:
        from inventory.models import MerchProduct
        from inventory.models_verticals import LiquorSale, LiquorShiftStock
        from inventory.business_kinds import BusinessKind
        from django.db.models import Subquery, OuterRef
        
        for loc in locations:
            loc_id = getattr(loc, "id", None)
            if not loc_id:
                continue
            
            # Get latest stock snapshots for products at this location
            latest_snapshots = LiquorShiftStock.objects.filter(
                product=OuterRef('pk'),
                shift__business=business,
                shift__location_id=loc_id
            ).order_by('-recorded_at')
            
            # Get products with their latest stock counts
            products_qs = MerchProduct.objects.filter(
                business=business,
                kind=BusinessKind.LIQUOR,
                is_active=True,
                is_archived=False,
            ).annotate(
                latest_bottles=Subquery(latest_snapshots.values('bottles_count')[:1])
            )
            
            # Sum up bottles in stock
            in_stock = sum(p.latest_bottles or 0 for p in products_qs)
            
            # Sold: count bottles sold via LiquorSale at this location
            sold_qs = LiquorSale.objects.filter(
                business=business,
                unit="bottle",
                shift__location_id=loc_id
            )
            
            # Try to filter by location via shift
            if hasattr(LiquorSale, "shift") and hasattr(LiquorSale.shift.field.related_model, "location_id"):
                sold_qs = sold_qs.filter(shift__location_id=loc_id)
            
            # Count total bottles sold (sum of quantity)
            sold = sum(s.quantity for s in sold_qs)
            
            total = in_stock + sold
            
            stock_summary[loc_id] = {
                "sold": sold,
                "in_stock": in_stock,
                "total": total,
            }
    except Exception:
        # If models not available, return empty
        pass
    
    return stock_summary


def get_gym_member_summary(business, locations: List) -> Dict[int, Dict[str, int]]:
    """
    Compute member summary for gym vertical.
    Returns: {location_id: {"active": int, "in_arrears": int, "total": int}}
    
    - Active: Members with days_left() > 0
    - In Arrears: Members with days_left() == 0
    - Total: active + in_arrears
    """
    stock_summary = {}
    
    # Initialize with zeros for all locations
    for loc in locations:
        loc_id = getattr(loc, "id", None)
        if loc_id:
            stock_summary[loc_id] = {
                "active": 0,
                "in_arrears": 0,
                "total": 0,
            }
    
    try:
        from inventory.models_verticals import GymMember
        
        # Note: GymMember doesn't have location FK, so we compute business-wide
        # and show the same data for all locations
        # If location support is needed, we'd need to add location FK to GymMember
        
        active_members = GymMember.objects.filter(
            business=business,
            is_active=True,
            is_archived=False
        )
        
        # Calculate members in arrears vs active
        members_active_count = 0
        members_in_arrears_count = 0
        
        for member in active_members:
            if member.days_left() == 0:
                members_in_arrears_count += 1
            else:
                members_active_count += 1
        
        total_members = active_members.count()
        
        # For now, show same data for all locations
        # (since GymMember doesn't have location FK)
        for loc_id in stock_summary.keys():
            stock_summary[loc_id] = {
                "active": members_active_count,
                "in_arrears": members_in_arrears_count,
                "total": total_members,
            }
    except Exception:
        # If models not available, keep zeros
        pass
    
    return stock_summary


def get_clothing_stock_summary(business, locations: List) -> Dict[int, Dict[str, int]]:
    """
    Compute stock summary for clothing vertical.
    Returns: {location_id: {"sold": int, "in_stock": int, "total": int}}
    
    - Sold: Count of items sold via ClothingSale
    - In Stock: Count of items in MerchProduct.quantity (where kind=clothing, is_active=True)
    - Total: sold + in_stock
    """
    stock_summary = {}
    
    # Initialize with zeros for all locations
    for loc in locations:
        loc_id = getattr(loc, "id", None)
        if loc_id:
            stock_summary[loc_id] = {
                "sold": 0,
                "in_stock": 0,
                "total": 0,
            }
    
    try:
        from inventory.models import MerchProduct
        from inventory.models_verticals import ClothingSale
        from inventory.business_kinds import BusinessKind
        
        for loc_id in stock_summary.keys():
            # In stock: sum of quantity field for clothing products at this location
            in_stock_qs = MerchProduct.objects.filter(
                business=business,
                kind=BusinessKind.CLOTHING,
                is_active=True,
                is_archived=False,
            )
            
            # Check if MerchProduct has location FK
            if hasattr(MerchProduct, "location_id"):
                in_stock_qs = in_stock_qs.filter(location_id=loc_id)
            
            # Sum quantities (items in stock)
            in_stock = sum(getattr(p, "quantity", 0) or 0 for p in in_stock_qs)
            
            # Sold: sum quantities from ClothingSale
            sold_qs = ClothingSale.objects.filter(business=business)
            
            # ClothingSale doesn't have location FK, so business-wide for now
            # Count total items sold (sum of quantity)
            sold = sum(s.quantity for s in sold_qs)
            
            total = in_stock + sold
            
            stock_summary[loc_id] = {
                "sold": sold,
                "in_stock": in_stock,
                "total": total,
            }
    except Exception:
        # If models not available, keep zeros
        pass
    
    return stock_summary


def get_generic_stock_summary(business, locations: List) -> Dict[int, Dict[str, int]]:
    """
    Generic fallback for unknown verticals.
    Returns empty summary or a simple message.
    """
    # Return empty dict - the template will handle showing "no data available"
    return {}


def get_stock_summary_for_vertical(vertical: str, business, locations: List) -> Dict[int, Dict[str, int]]:
    """
    Dispatch to the appropriate helper based on vertical.
    
    Args:
        vertical: Business vertical (phones, liquor, gym, clothing, etc.)
        business: Business instance
        locations: List of location objects
    
    Returns:
        Dict mapping location_id to summary dict with keys appropriate to the vertical
    """
    if vertical == "phones":
        return get_phones_stock_summary(business, locations)
    elif vertical == "liquor":
        return get_liquor_stock_summary(business, locations)
    elif vertical == "gym":
        return get_gym_member_summary(business, locations)
    elif vertical == "clothing":
        return get_clothing_stock_summary(business, locations)
    else:
        return get_generic_stock_summary(business, locations)

