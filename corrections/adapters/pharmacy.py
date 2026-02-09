"""
Pharmacy Vertical Adapter for Corrections Framework (Feb 2026)
===============================================================

Registers correctable entities for the Pharmacy & Cosmetics vertical:
- Pharmacy Products (MerchProduct with kind=PHARMACY)
- Pharmacy Batches (PharmacyBatch - expiry, quantities, pricing)
- Pharmacy Sales (PharmacySale - sale records with batch tracking)

Allows managers to fix:
- Product information errors (name, category, pricing defaults)
- Batch data errors (batch numbers, expiry dates, costs, quantities)
- Sale data errors (quantities, prices, payment methods, timestamps)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict
import datetime

from django.db.models import F, Q, QuerySet
from django.utils import timezone

from corrections.registry import (
    VerticalAdapter,
    EntityConfig,
    FieldConfig,
    register_vertical,
)
from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch, PharmacySale
from inventory.business_kinds import BusinessKind


@register_vertical('pharmacy')
class PharmacyAdapter(VerticalAdapter):
    """Pharmacy & Cosmetics vertical adapter."""
    
    vertical_key = 'pharmacy'
    vertical_label = 'Pharmacy & Cosmetics'
    
    def get_entities(self) -> Dict[str, EntityConfig]:
        """
        Define correctable entities for Pharmacy vertical.
        """
        return {
            # Pharmacy Product (base product info)
            'pharmacy_product': EntityConfig(
                entity_label='pharmacy_product',
                model=MerchProduct,
                label='Pharmacy Product',
                description='Fix product names, categories, barcodes, and default pricing',
                base_filters={'kind': BusinessKind.PHARMACY},  # Only show pharmacy products
                fields={
                    'name': FieldConfig(
                        field_name='name',
                        label='Product Name',
                        field_type='string',
                        validator=lambda val: len(str(val).strip()) > 0,
                        coercer=lambda val: str(val).strip(),
                        help_text='Product name (required)',
                        required=True,
                    ),
                    'category': FieldConfig(
                        field_name='category',
                        label='Category',
                        field_type='string',
                        validator=lambda val: True,  # Any category accepted
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Product category (e.g., Antibiotics, Cosmetics)',
                        required=False,
                    ),
                    'barcode': FieldConfig(
                        field_name='barcode',
                        label='Barcode',
                        field_type='string',
                        validator=lambda val: True,  # Any barcode format accepted
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Product barcode (optional)',
                        required=False,
                    ),
                    'sku': FieldConfig(
                        field_name='sku',
                        label='SKU',
                        field_type='string',
                        validator=lambda val: True,
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Stock keeping unit (optional)',
                        required=False,
                    ),
                    'description': FieldConfig(
                        field_name='description',
                        label='Description',
                        field_type='string',
                        validator=lambda val: True,
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Product description',
                        required=False,
                    ),
                },
            ),
            
            # Pharmacy Batch (batch-level stock with expiry tracking)
            'pharmacy_batch': EntityConfig(
                entity_label='pharmacy_batch',
                model=PharmacyBatch,
                label='Pharmacy Batch',
                description='Fix batch numbers, expiry dates, costs, quantities, and pricing',
                fields={
                    'batch_number': FieldConfig(
                        field_name='batch_number',
                        label='Batch Number',
                        field_type='string',
                        validator=lambda val: True,  # Any batch number accepted
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Manufacturer batch/lot number',
                        required=False,
                    ),
                    'barcode': FieldConfig(
                        field_name='barcode',
                        label='Batch Barcode',
                        field_type='string',
                        validator=lambda val: True,
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Batch-specific barcode',
                        required=False,
                    ),
                    'expiry_date': FieldConfig(
                        field_name='expiry_date',
                        label='Expiry Date',
                        field_type='date',
                        validator=lambda val: val is None or isinstance(val, (datetime.date, str)),
                        coercer=lambda val: val if isinstance(val, datetime.date) else (
                            datetime.date.fromisoformat(str(val)) if val else None
                        ),
                        help_text='Expiry date (YYYY-MM-DD, optional for cosmetics)',
                        required=False,
                    ),
                    'quantity': FieldConfig(
                        field_name='quantity',
                        label='Quantity',
                        field_type='integer',
                        validator=lambda val: int(val) >= 0,
                        coercer=lambda val: int(val),
                        help_text='Current quantity in stock (must be >= 0)',
                        required=True,
                    ),
                    'reorder_level': FieldConfig(
                        field_name='reorder_level',
                        label='Reorder Level',
                        field_type='integer',
                        validator=lambda val: int(val) >= 0,
                        coercer=lambda val: int(val),
                        help_text='Alert threshold for low stock',
                        required=True,
                    ),
                    'cost_price': FieldConfig(
                        field_name='cost_price',
                        label='Cost Price',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Cost per unit (must be >= 0)',
                        required=True,
                    ),
                    'selling_price': FieldConfig(
                        field_name='selling_price',
                        label='Selling Price',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Selling price per unit (must be >= 0)',
                        required=True,
                    ),
                    'supplier': FieldConfig(
                        field_name='supplier',
                        label='Supplier',
                        field_type='string',
                        validator=lambda val: True,
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Supplier name',
                        required=False,
                    ),
                    'received_date': FieldConfig(
                        field_name='received_date',
                        label='Received Date',
                        field_type='date',
                        validator=lambda val: isinstance(val, (datetime.date, str)),
                        coercer=lambda val: val if isinstance(val, datetime.date) else datetime.date.fromisoformat(str(val)),
                        help_text='Date batch was received',
                        required=True,
                    ),
                },
            ),
            
            # Pharmacy Sale
            'pharmacy_sale': EntityConfig(
                entity_label='pharmacy_sale',
                model=PharmacySale,
                label='Pharmacy Sale',
                description='Fix sale quantities, unit prices, payment methods, and timestamps',
                business_filter_path='business',  # PharmacySale has direct business field
                fields={
                    'quantity': FieldConfig(
                        field_name='quantity',
                        label='Quantity Sold',
                        field_type='integer',
                        validator=lambda val: int(val) > 0,
                        coercer=lambda val: int(val),
                        help_text='Quantity sold (must be > 0)',
                        required=True,
                    ),
                    'unit_price': FieldConfig(
                        field_name='unit_price',
                        label='Unit Price',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Selling price per unit (must be >= 0)',
                        required=True,
                    ),
                    'unit_cost': FieldConfig(
                        field_name='unit_cost',
                        label='Unit Cost',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Cost price per unit (for profit calculation)',
                        required=True,
                    ),
                    'total_amount': FieldConfig(
                        field_name='total_amount',
                        label='Total Amount',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Total sale amount (quantity × unit_price)',
                        required=True,
                    ),
                    'payment_method': FieldConfig(
                        field_name='payment_method',
                        label='Payment Method',
                        field_type='string',
                        validator=lambda val: val in ['CASH', 'MOBILE_MONEY', 'BANK', 'CREDIT'],
                        coercer=lambda val: str(val).upper(),
                        help_text='CASH, MOBILE_MONEY, BANK, or CREDIT',
                        required=True,
                    ),
                    'customer_name': FieldConfig(
                        field_name='customer_name',
                        label='Customer Name',
                        field_type='string',
                        validator=lambda val: True,
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Customer name (optional)',
                        required=False,
                    ),
                    'customer_phone': FieldConfig(
                        field_name='customer_phone',
                        label='Customer Phone',
                        field_type='string',
                        validator=lambda val: True,
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Customer phone number (optional)',
                        required=False,
                    ),
                    'prescription_number': FieldConfig(
                        field_name='prescription_number',
                        label='Prescription Number',
                        field_type='string',
                        validator=lambda val: True,
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Prescription reference (if applicable)',
                        required=False,
                    ),
                    'sold_at': FieldConfig(
                        field_name='sold_at',
                        label='Sale Timestamp',
                        field_type='datetime',
                        validator=lambda val: isinstance(val, (datetime.datetime, str)),
                        coercer=lambda val: val if isinstance(val, datetime.datetime) else (
                            timezone.datetime.fromisoformat(str(val)) if val else timezone.now()
                        ),
                        help_text='Date and time of sale',
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
        - Batches with expiry dates in the past but still active
        - Batches with negative quantities
        - Sales where total_amount != quantity * unit_price
        - Sales with selling price lower than cost
        - Products with missing critical data
        """
        today = timezone.now().date()
        
        if entity_label == 'pharmacy_batch':
            # Find batches with data issues
            try:
                return PharmacyBatch.objects.filter(
                    business=business,
                    is_archived=False,
                ).filter(
                    Q(expiry_date__lt=today) |  # Expired but not archived
                    Q(quantity__lt=0) |  # Negative quantity (data error)
                    Q(selling_price__lt=F('cost_price')) |  # Selling below cost
                    Q(cost_price__lte=0)  # Zero or negative cost
                ).select_related('merch_product').order_by('expiry_date')[:limit]
            except Exception:
                return PharmacyBatch.objects.none()
        
        elif entity_label == 'pharmacy_sale':
            # Find sales with calculation errors
            try:
                return PharmacySale.objects.filter(
                    business=business,
                    is_deleted=False,
                    is_reversed=False,
                ).annotate(
                    calculated_total=F('quantity') * F('unit_price')
                ).filter(
                    # Total doesn't match calculation (with 1 MWK tolerance)
                    Q(total_amount__lt=F('calculated_total') - Decimal('1')) |
                    Q(total_amount__gt=F('calculated_total') + Decimal('1')) |
                    # Sold below cost
                    Q(unit_price__lt=F('unit_cost'))
                ).select_related('batch', 'batch__merch_product').order_by('-sold_at')[:limit]
            except Exception:
                return PharmacySale.objects.none()
        
        elif entity_label == 'pharmacy_product':
            # Find products with missing critical data
            try:
                return MerchProduct.objects.filter(
                    business=business,
                    kind=BusinessKind.PHARMACY,
                    is_active=True,
                ).filter(
                    Q(name='') | Q(name__isnull=True) |  # Missing name
                    Q(category='') | Q(category__isnull=True)  # Missing category
                ).order_by('name')[:limit]
            except Exception:
                return MerchProduct.objects.none()
        
        else:
            return PharmacyBatch.objects.none()
    
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
        
        if entity_label == 'pharmacy_sale':
            # For sales, changing amounts impacts revenue and profit
            if field_name == 'total_amount':
                old_amt = Decimal(str(old_value)) if old_value else Decimal('0.00')
                new_amt = Decimal(str(new_value)) if new_value else Decimal('0.00')
                revenue_impact = new_amt - old_amt
                # Profit impact (need to recalculate based on cost)
                try:
                    total_cost = obj.unit_cost * Decimal(str(obj.quantity))
                    old_profit = old_amt - total_cost
                    new_profit = new_amt - total_cost
                    profit_impact = new_profit - old_profit
                except:
                    profit_impact = revenue_impact  # Fallback
            
            elif field_name == 'unit_price':
                old_price = Decimal(str(old_value)) if old_value else Decimal('0.00')
                new_price = Decimal(str(new_value)) if new_value else Decimal('0.00')
                qty = Decimal(str(obj.quantity))
                revenue_impact = (new_price - old_price) * qty
                profit_impact = revenue_impact  # Full impact on profit
            
            elif field_name == 'unit_cost':
                old_cost = Decimal(str(old_value)) if old_value else Decimal('0.00')
                new_cost = Decimal(str(new_value)) if new_value else Decimal('0.00')
                qty = Decimal(str(obj.quantity))
                # Cost increase = profit decrease
                profit_impact = (old_cost - new_cost) * qty
            
            elif field_name == 'quantity':
                old_qty = int(old_value) if old_value else 0
                new_qty = int(new_value) if new_value else 0
                qty_diff = new_qty - old_qty
                revenue_impact = Decimal(str(qty_diff)) * obj.unit_price
                profit_impact = Decimal(str(qty_diff)) * (obj.unit_price - obj.unit_cost)
        
        elif entity_label == 'pharmacy_batch':
            # Batch corrections don't affect historical revenue, only inventory value
            if field_name in ('cost_price', 'selling_price'):
                # Show potential impact on future sales
                old_price = Decimal(str(old_value)) if old_value else Decimal('0.00')
                new_price = Decimal(str(new_value)) if new_value else Decimal('0.00')
                qty = Decimal(str(obj.quantity))
                
                if field_name == 'selling_price':
                    # Potential revenue impact if all units sold at new price
                    revenue_impact = (new_price - old_price) * qty
                    profit_impact = revenue_impact
                elif field_name == 'cost_price':
                    # Cost increase = profit decrease
                    profit_impact = (old_price - new_price) * qty
            
            elif field_name == 'quantity':
                # Quantity correction affects inventory value
                old_qty = int(old_value) if old_value else 0
                new_qty = int(new_value) if new_value else 0
                qty_diff = Decimal(str(new_qty - old_qty))
                # Impact on inventory value (at cost)
                cost_impact = qty_diff * obj.cost_price
                # Note: This doesn't affect profit directly, just inventory valuation
                revenue_impact = Decimal('0.00')
                profit_impact = Decimal('0.00')
        
        return {
            'revenue_impact': revenue_impact,
            'profit_impact': profit_impact,
        }
    
    def post_correction_hook(
        self,
        entity_label: str,
        obj,
        field_name: str,
        old_value,
        new_value,
    ) -> None:
        """
        Post-correction hook for pharmacy entities.
        
        Handles:
        - Recalculating pharmacy_sale totals when quantity/unit_price changes
        - Validating pharmacy_batch expiry dates
        - Ensuring data consistency
        """
        if entity_label == 'pharmacy_sale':
            # Recalculate total_amount if quantity or unit_price changed
            if field_name in ('quantity', 'unit_price'):
                obj.total_amount = Decimal(str(obj.quantity)) * obj.unit_price
                obj.save(update_fields=['total_amount', 'updated_at'])
            
            # Validate payment method
            if field_name == 'payment_method':
                valid_methods = ['CASH', 'MOBILE_MONEY', 'BANK', 'CREDIT']
                if obj.payment_method not in valid_methods:
                    raise ValueError(f'Invalid payment method: {obj.payment_method}. Must be one of {valid_methods}')
        
        elif entity_label == 'pharmacy_batch':
            # Validate expiry date is not in the past (unless explicitly allowed)
            if field_name == 'expiry_date' and obj.expiry_date:
                # Allow past dates (for correcting historical data), but warn if very old
                pass
            
            # Validate pricing
            if field_name in ('cost_price', 'selling_price'):
                if obj.cost_price < 0:
                    raise ValueError('Cost price cannot be negative')
                if obj.selling_price < 0:
                    raise ValueError('Selling price cannot be negative')
            
            # Validate quantity
            if field_name == 'quantity':
                if obj.quantity < 0:
                    raise ValueError('Quantity cannot be negative')


# Export
__all__ = ['PharmacyAdapter']

