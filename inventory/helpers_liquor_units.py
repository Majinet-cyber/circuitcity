# inventory/helpers_liquor_units.py
"""
SSOT helper for liquor unit pricing calculations.
Handles per-bottle, per-shot conversions for different liquor categories.

CRITICAL: This is the Single Source of Truth for unit pricing logic.
DO NOT duplicate this logic elsewhere.
"""
from decimal import Decimal
from typing import Dict, Optional

def get_liquor_unit_info(product) -> Dict:
    """
    Get unit pricing information for a liquor product.
    
    Args:
        product: MerchProduct instance (liquor)
    
    Returns:
        dict with keys:
            - sale_unit: "bottle" or "shot" or "glass"
            - units_per_item: int (e.g., 20 for beer crate, 25 for spirits bottle)
            - unit_price: Decimal (price per selling unit)
            - unit_cost: Decimal (cost per selling unit)
            - max_quantity: int (available stock in selling units)
            - label: str (human-readable label for UI)
    """
    category = (product.category or "").lower()
    
    # Default values
    sale_unit = "bottle"
    units_per_item = 1
    unit_price = Decimal("0.00")
    unit_cost = Decimal("0.00")
    available_stock = product.quantity_in_stock or 0
    
    # Beer & Cider: sold per bottle (from crates)
    if category in ["beer", "cider"]:
        sale_unit = "bottle"
        units_per_crate = product.bottles_per_crate or 20  # Default 20 bottles per crate
        units_per_item = units_per_crate
        
        # Calculate per-bottle price
        if product.price_per_bottle:
            # Explicit per-bottle price is set
            unit_price = product.price_per_bottle
        elif product.selling_price:
            # Selling price is per crate, divide by bottles per crate
            unit_price = product.selling_price / Decimal(str(units_per_crate))
        
        # Calculate per-bottle cost
        if product.cost_per_bottle:
            unit_cost = product.cost_per_bottle
        elif product.cost_price:
            # Cost price is per crate, divide by bottles per crate
            unit_cost = product.cost_price / Decimal(str(units_per_crate))
        
        # Stock is in crates, convert to bottles
        max_quantity = available_stock * units_per_crate
        label = "Bottles"
        
    # Spirits & Whiskey: sold per shot
    elif category in ["spirits", "whiskey"]:
        sale_unit = "shot"
        shots_per_bottle = product.sellable_shots_per_bottle or 23  # Default 25 - 2 reserved
        units_per_item = shots_per_bottle
        
        # Calculate per-shot price
        if product.price_per_shot:
            unit_price = product.price_per_shot
        elif product.price_per_bottle and shots_per_bottle > 0:
            # Calculate from bottle price
            unit_price = product.price_per_bottle / Decimal(str(shots_per_bottle))
        
        # Calculate per-shot cost
        if product.cost_per_shot:
            unit_cost = product.cost_per_shot
        elif product.cost_per_bottle and shots_per_bottle > 0:
            unit_cost = product.cost_per_bottle / Decimal(str(shots_per_bottle))
        
        # Stock is in bottles, convert to shots
        max_quantity = available_stock * shots_per_bottle
        label = "Shots"
    
    # Wine: sold per glass
    elif category == "wine":
        sale_unit = "glass"
        glasses_per_bottle = product.glasses_per_bottle or 5  # Default 5 glasses per bottle
        units_per_item = glasses_per_bottle
        
        # Calculate per-glass price
        if product.price_per_glass:
            unit_price = product.price_per_glass
        elif product.price_per_bottle and glasses_per_bottle > 0:
            unit_price = product.price_per_bottle / Decimal(str(glasses_per_bottle))
        
        # Calculate per-glass cost
        if product.cost_per_glass:
            unit_cost = product.cost_per_glass
        elif product.cost_per_bottle and glasses_per_bottle > 0:
            unit_cost = product.cost_per_bottle / Decimal(str(glasses_per_bottle))
        
        # Stock is in bottles, convert to glasses
        max_quantity = available_stock * glasses_per_bottle
        label = "Glasses"
    
    # Other categories: default to bottle
    else:
        sale_unit = "bottle"
        units_per_item = 1
        
        # Use bottle price if available, fallback to selling_price
        if product.price_per_bottle:
            unit_price = product.price_per_bottle
        elif product.selling_price:
            unit_price = product.selling_price
        
        # Use bottle cost if available, fallback to cost_price
        if product.cost_per_bottle:
            unit_cost = product.cost_per_bottle
        elif product.cost_price:
            unit_cost = product.cost_price
        
        max_quantity = available_stock
        label = "Bottles"
    
    return {
        "sale_unit": sale_unit,
        "units_per_item": units_per_item,
        "unit_price": unit_price,
        "unit_cost": unit_cost,
        "max_quantity": max_quantity,
        "label": label,
        "category": category,
    }


def compute_sale_totals(product, quantity: int, unit_price: Optional[Decimal] = None) -> Dict:
    """
    Compute sale totals for a liquor product.
    
    Args:
        product: MerchProduct instance
        quantity: Number of units to sell
        unit_price: Optional override price (if None, uses default from product)
    
    Returns:
        dict with keys:
            - unit_price: Decimal
            - unit_cost: Decimal
            - total: Decimal (quantity * unit_price)
            - total_cost: Decimal (quantity * unit_cost)
            - profit: Decimal (total - total_cost)
            - margin: Decimal (profit / total * 100, or 0 if total is 0)
    """
    unit_info = get_liquor_unit_info(product)
    
    # Use provided unit_price or default from product
    if unit_price is None:
        unit_price = unit_info["unit_price"]
    
    unit_cost = unit_info["unit_cost"]
    
    # Calculate totals
    total = Decimal(str(quantity)) * unit_price
    total_cost = Decimal(str(quantity)) * unit_cost
    profit = total - total_cost
    
    # Calculate margin
    if total > 0:
        margin = (profit / total) * Decimal("100.00")
    else:
        margin = Decimal("0.00")
    
    return {
        "unit_price": unit_price,
        "unit_cost": unit_cost,
        "total": total,
        "total_cost": total_cost,
        "profit": profit,
        "margin": margin,
    }

