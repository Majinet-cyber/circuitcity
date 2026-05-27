"""
Phones Vertical Adapter for Corrections Framework (Feb 2026)
=============================================================

Registers correctable entities for the Phones vertical:
- Phone Sales (InventoryItem where status=SOLD)
- Stock-In Records (InventoryItem where status=IN_STOCK)
- Accessory Products (AccessoryProduct)
- Accessory Stock (AccessoryStock)

This adapter migrates the existing Phones-specific correction system
(inventory/services_data_correction.py) to the new generic framework.
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
from inventory.models import InventoryItem, normalize_imei
from inventory.models_accessories import AccessoryProduct, AccessoryStock


@register_vertical('phones')
class PhonesAdapter(VerticalAdapter):
    """Phones vertical adapter."""
    
    vertical_key = 'phones'
    vertical_label = 'Phones'
    
    def get_entities(self) -> Dict[str, EntityConfig]:
        """
        Define correctable entities for Phones vertical.
        """
        return {
            # Phone Sale (InventoryItem where status=SOLD)
            'phone_sale': EntityConfig(
                entity_label='phone_sale',
                model=InventoryItem,
                label='Phone Sale',
                description='Sold phone record',
                fields={
                    'selling_price': FieldConfig(
                        field_name='selling_price',
                        label='Selling Price',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) > 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Must be greater than 0',
                        required=True,
                    ),
                    'order_price': FieldConfig(
                        field_name='order_price',
                        label='Order/Cost Price',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Must be 0 or greater',
                        required=True,
                    ),
                    'imei': FieldConfig(
                        field_name='imei',
                        label='IMEI',
                        field_type='string',
                        validator=lambda val: len(str(val).strip()) == 15 and str(val).strip().isdigit(),
                        coercer=lambda val: normalize_imei(val),
                        help_text='Must be exactly 15 digits',
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
            
            # Phone Stock-In (InventoryItem where status=IN_STOCK)
            'phone_stock': EntityConfig(
                entity_label='phone_stock',
                model=InventoryItem,
                label='Phone Stock-In',
                description='Phone in stock (not yet sold)',
                fields={
                    'order_price': FieldConfig(
                        field_name='order_price',
                        label='Order/Cost Price',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Must be 0 or greater',
                        required=True,
                    ),
                    'imei': FieldConfig(
                        field_name='imei',
                        label='IMEI',
                        field_type='string',
                        validator=lambda val: len(str(val).strip()) == 15 and str(val).strip().isdigit(),
                        coercer=lambda val: normalize_imei(val),
                        help_text='Must be exactly 15 digits',
                        required=True,
                    ),
                },
            ),
            
            # Accessory Product
            'accessory_product': EntityConfig(
                entity_label='accessory_product',
                model=AccessoryProduct,
                label='Accessory Product',
                description='Accessory product master data',
                fields={
                    'name': FieldConfig(
                        field_name='name',
                        label='Product Name',
                        field_type='string',
                        validator=lambda val: len(str(val).strip()) > 0,
                        coercer=lambda val: str(val).strip(),
                        help_text='Product name (must be unique)',
                        required=True,
                    ),
                    'sku': FieldConfig(
                        field_name='sku',
                        label='SKU',
                        field_type='string',
                        validator=lambda val: len(str(val).strip()) > 0,
                        coercer=lambda val: str(val).strip().upper(),
                        help_text='SKU code (must be unique)',
                        required=False,
                    ),
                    'default_selling_price': FieldConfig(
                        field_name='default_selling_price',
                        label='Default Selling Price',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) > 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Must be greater than 0',
                        required=True,
                    ),
                    'default_order_price': FieldConfig(
                        field_name='default_order_price',
                        label='Default Order Price',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Must be 0 or greater',
                        required=True,
                    ),
                },
            ),
            
            # Accessory Stock
            'accessory_stock': EntityConfig(
                entity_label='accessory_stock',
                model=AccessoryStock,
                label='Accessory Stock',
                description='Accessory stock levels by location',
                fields={
                    'qty_on_hand': FieldConfig(
                        field_name='qty_on_hand',
                        label='Quantity on Hand',
                        field_type='integer',
                        validator=lambda val: int(val) >= 0,
                        coercer=lambda val: int(val),
                        help_text='Must be 0 or greater',
                        required=True,
                    ),
                    'avg_cost': FieldConfig(
                        field_name='avg_cost',
                        label='Average Cost',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Must be 0 or greater',
                        required=True,
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
        - Phone sales where selling_price < order_price (selling at a loss)
        - Phone sales with duplicate IMEIs
        - Accessories with negative stock
        """
        if entity_label == 'phone_sale':
            # Find sales where selling price < cost price (losses)
            return InventoryItem.objects.filter(
                business=business,
                status='SOLD',
                is_active=True,
                selling_price__lt=F('order_price'),
            ).select_related('product', 'sold_by').order_by('-sold_at')[:limit]
        
        elif entity_label == 'phone_stock':
            # Find stock items with unusual pricing (cost = 0 or very high)
            return InventoryItem.objects.filter(
                business=business,
                status='IN_STOCK',
                is_active=True,
            ).filter(
                Q(order_price=0) | Q(order_price__gt=1000000)
            ).select_related('product').order_by('-received_at')[:limit]
        
        elif entity_label == 'accessory_stock':
            # Find accessories with negative stock (data error)
            return AccessoryStock.objects.filter(
                business=business,
                qty_on_hand__lt=0,
            ).select_related('product', 'location').order_by('-updated_at')[:limit]
        
        else:
            # Return empty queryset for other entities
            return InventoryItem.objects.none()
    
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
        
        if entity_label == 'phone_sale':
            # For sold phones, changing prices impacts revenue and profit
            if field_name == 'selling_price':
                old_price = Decimal(str(old_value)) if old_value else Decimal('0.00')
                new_price = Decimal(str(new_value)) if new_value else Decimal('0.00')
                revenue_impact = new_price - old_price
                profit_impact = revenue_impact  # Profit changes by same amount
            
            elif field_name == 'order_price':
                old_cost = Decimal(str(old_value)) if old_value else Decimal('0.00')
                new_cost = Decimal(str(new_value)) if new_value else Decimal('0.00')
                cost_change = new_cost - old_cost
                profit_impact = -cost_change  # Higher cost = lower profit
        
        return {
            'revenue_impact': revenue_impact,
            'profit_impact': profit_impact,
        }


# Export
__all__ = ['PhonesAdapter']

