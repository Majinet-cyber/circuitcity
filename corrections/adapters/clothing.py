"""
Clothing Vertical Adapter for Corrections Framework (Feb 2026)
===============================================================

Registers correctable entities for the Clothing vertical:
- Clothing Products (MerchProduct where kind='clothing')
- Clothing Sales (ClothingSale)
- Clothing Variants (ClothingVariant - optional size/color combos)

Allows managers to fix:
- Wrong pricing (selling_price, cost_price)
- Stock discrepancies (quantity_in_stock)
- Sale transaction errors (unit_price, quantity)
- Product metadata (name, size, color)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict

from django.db.models import F, Q, QuerySet

from corrections.registry import (
    VerticalAdapter,
    EntityConfig,
    FieldConfig,
    register_vertical,
)
from inventory.models import MerchProduct
from inventory.models_verticals import ClothingSale, ClothingVariant


@register_vertical('clothing')
class ClothingAdapter(VerticalAdapter):
    """Clothing vertical adapter."""
    
    vertical_key = 'clothing'
    vertical_label = 'Clothing'
    
    def get_entities(self) -> Dict[str, EntityConfig]:
        """
        Define correctable entities for Clothing vertical.
        """
        return {
            # Clothing Product (MerchProduct where kind='clothing')
            'clothing_product': EntityConfig(
                entity_label='clothing_product',
                model=MerchProduct,
                label='Clothing Product',
                description='Master product data (includes name, size, color, pricing)',
                fields={
                    'name': FieldConfig(
                        field_name='name',
                        label='Product Name',
                        field_type='string',
                        validator=lambda val: len(str(val).strip()) > 0,
                        coercer=lambda val: str(val).strip(),
                        help_text='Product name (must be unique per business)',
                        required=True,
                    ),
                    'size': FieldConfig(
                        field_name='size',
                        label='Size',
                        field_type='string',
                        validator=lambda val: True,  # Any size is valid
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Size (e.g., S, M, L, XL, 32, 42)',
                        required=False,
                    ),
                    'color': FieldConfig(
                        field_name='color',
                        label='Color',
                        field_type='string',
                        validator=lambda val: True,  # Any color is valid
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Color (e.g., Black, Navy, Red)',
                        required=False,
                    ),
                    'selling_price': FieldConfig(
                        field_name='selling_price',
                        label='Selling Price',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) > 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Must be greater than 0',
                        required=True,
                    ),
                    'cost_price': FieldConfig(
                        field_name='cost_price',
                        label='Cost Price',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Must be 0 or greater',
                        required=True,
                    ),
                    'quantity_in_stock': FieldConfig(
                        field_name='quantity_in_stock',
                        label='Quantity in Stock',
                        field_type='integer',
                        validator=lambda val: int(val) >= 0,
                        coercer=lambda val: int(val),
                        help_text='Must be 0 or greater',
                        required=True,
                    ),
                },
            ),
            
            # Clothing Sale
            'clothing_sale': EntityConfig(
                entity_label='clothing_sale',
                model=ClothingSale,
                label='Clothing Sale',
                description='Sales transaction record',
                fields={
                    'quantity': FieldConfig(
                        field_name='quantity',
                        label='Quantity Sold',
                        field_type='integer',
                        validator=lambda val: int(val) > 0,
                        coercer=lambda val: int(val),
                        help_text='Must be greater than 0',
                        required=True,
                    ),
                    'unit_price': FieldConfig(
                        field_name='unit_price',
                        label='Unit Price',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) > 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Price per unit (must be > 0)',
                        required=True,
                    ),
                    'total_price': FieldConfig(
                        field_name='total_price',
                        label='Total Price',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) > 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Total sale amount (must be > 0)',
                        required=True,
                    ),
                    'unit_cost': FieldConfig(
                        field_name='unit_cost',
                        label='Unit Cost',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Cost per unit (must be >= 0)',
                        required=True,
                    ),
                    'total_cost': FieldConfig(
                        field_name='total_cost',
                        label='Total Cost',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Total cost of goods sold (must be >= 0)',
                        required=True,
                    ),
                    'payment_method': FieldConfig(
                        field_name='payment_method',
                        label='Payment Method',
                        field_type='string',
                        validator=lambda val: val in ['CASH', 'BANK', 'MOBILE_MONEY'],
                        coercer=lambda val: str(val).upper(),
                        help_text='CASH, BANK, or MOBILE_MONEY',
                        required=False,
                    ),
                },
            ),
            
            # Clothing Variant (optional size/color combinations)
            'clothing_variant': EntityConfig(
                entity_label='clothing_variant',
                model=ClothingVariant,
                label='Clothing Variant',
                description='Size/color variant with specific stock and pricing',
                fields={
                    'size': FieldConfig(
                        field_name='size',
                        label='Size',
                        field_type='string',
                        validator=lambda val: True,
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Size for this variant',
                        required=False,
                    ),
                    'color': FieldConfig(
                        field_name='color',
                        label='Color',
                        field_type='string',
                        validator=lambda val: True,
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Color for this variant',
                        required=False,
                    ),
                    'quantity_in_stock': FieldConfig(
                        field_name='quantity_in_stock',
                        label='Stock Quantity',
                        field_type='integer',
                        validator=lambda val: int(val) >= 0,
                        coercer=lambda val: int(val),
                        help_text='Stock quantity for this variant',
                        required=True,
                    ),
                    'selling_price_override': FieldConfig(
                        field_name='selling_price_override',
                        label='Selling Price Override',
                        field_type='decimal',
                        validator=lambda val: val is None or Decimal(str(val)) > 0,
                        coercer=lambda val: Decimal(str(val)) if val else None,
                        help_text='Optional: Override selling price for this variant',
                        required=False,
                    ),
                    'cost_price_override': FieldConfig(
                        field_name='cost_price_override',
                        label='Cost Price Override',
                        field_type='decimal',
                        validator=lambda val: val is None or Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)) if val else None,
                        help_text='Optional: Override cost price for this variant',
                        required=False,
                    ),
                },
            ),
        }
    
    def find_erroneous_entries(
        self,
        entity_label: str,
        business,
        limit: int = 50,
    ) -> QuerySet:
        """
        Find potentially erroneous entries for quick correction.
        
        Heuristics:
        - Products with negative stock
        - Products where selling_price < cost_price (losses)
        - Sales where total_price < total_cost (losses)
        - Sales where total_price != unit_price * quantity (calculation error)
        """
        if entity_label == 'clothing_product':
            # Find products with issues
            return MerchProduct.objects.filter(
                business=business,
                kind='clothing',
                is_active=True,
            ).filter(
                Q(quantity_in_stock__lt=0) |  # Negative stock
                Q(selling_price__lt=F('cost_price'))  # Selling at a loss
            ).order_by('-updated_at')[:limit]
        
        elif entity_label == 'clothing_sale':
            # Find sales with issues
            return ClothingSale.objects.filter(
                business=business,
            ).filter(
                Q(total_price__lt=F('total_cost')) |  # Sale at a loss
                Q(total_price__lt=F('unit_price') * F('quantity') * Decimal('0.99')) |  # Total != unit * qty (with 1% tolerance)
                Q(total_price__gt=F('unit_price') * F('quantity') * Decimal('1.01'))
            ).select_related('product', 'sold_by').order_by('-sold_at')[:limit]
        
        elif entity_label == 'clothing_variant':
            # Find variants with negative stock
            return ClothingVariant.objects.filter(
                product__business=business,
                quantity_in_stock__lt=0,
                is_active=True,
            ).select_related('product').order_by('-updated_at')[:limit]
        
        else:
            return MerchProduct.objects.none()
    
    def calculate_impact(
        self,
        entity_label: str,
        obj,
        field_name: str,
        old_value,
        new_value,
    ) -> Dict[str, Decimal]:
        """
        Calculate financial impact of a correction.
        """
        revenue_impact = Decimal('0.00')
        profit_impact = Decimal('0.00')
        
        if entity_label == 'clothing_sale':
            # For sales, changing prices impacts revenue and profit
            if field_name == 'total_price':
                old_price = Decimal(str(old_value)) if old_value else Decimal('0.00')
                new_price = Decimal(str(new_value)) if new_value else Decimal('0.00')
                revenue_impact = new_price - old_price
                profit_impact = revenue_impact  # Profit changes by same amount
            
            elif field_name == 'unit_price':
                # Unit price change affects total price
                old_unit = Decimal(str(old_value)) if old_value else Decimal('0.00')
                new_unit = Decimal(str(new_value)) if new_value else Decimal('0.00')
                quantity = obj.quantity
                revenue_impact = (new_unit - old_unit) * quantity
                profit_impact = revenue_impact
            
            elif field_name == 'total_cost':
                old_cost = Decimal(str(old_value)) if old_value else Decimal('0.00')
                new_cost = Decimal(str(new_value)) if new_value else Decimal('0.00')
                cost_change = new_cost - old_cost
                profit_impact = -cost_change  # Higher cost = lower profit
            
            elif field_name == 'unit_cost':
                old_unit_cost = Decimal(str(old_value)) if old_value else Decimal('0.00')
                new_unit_cost = Decimal(str(new_value)) if new_value else Decimal('0.00')
                quantity = obj.quantity
                cost_change = (new_unit_cost - old_unit_cost) * quantity
                profit_impact = -cost_change
        
        elif entity_label == 'clothing_product':
            # For products, pricing changes don't affect past sales, only future
            # But we can show the potential impact on current stock
            if field_name == 'selling_price' and hasattr(obj, 'quantity_in_stock'):
                old_price = Decimal(str(old_value)) if old_value else Decimal('0.00')
                new_price = Decimal(str(new_value)) if new_value else Decimal('0.00')
                price_diff = new_price - old_price
                stock_qty = obj.quantity_in_stock
                # Potential impact if all current stock is sold
                revenue_impact = price_diff * stock_qty
                profit_impact = revenue_impact
        
        return {
            'revenue_impact': revenue_impact,
            'profit_impact': profit_impact,
        }


# Export
__all__ = ['ClothingAdapter']

