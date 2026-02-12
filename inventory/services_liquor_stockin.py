# inventory/services_liquor_stockin.py
"""
Category-aware stock-in adapters for Liquor products.
These adapters convert user-friendly inputs into standardized inventory transactions.

PART C: Backend architecture - one consistent save path with category-specific adapters.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Tuple
from django.db import transaction


def quantize_2dp(value: Decimal) -> Decimal:
    """Quantize decimal to 2 decimal places (standard for currency)."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class StockInAdapter:
    """Base adapter for category-specific stock-in calculations."""
    
    @staticmethod
    def adapt(user_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert user inputs to standardized transaction format.
        
        Returns:
            {
                'quantity_units_added': int,      # sellable units to add
                'unit_cost': Decimal,              # cost per sellable unit
                'total_cost': Decimal,             # derived total
                'notes': str,                      # optional notes
                'metadata': dict,                  # category-specific metadata
            }
        """
        raise NotImplementedError("Subclasses must implement adapt()")


class BeerStockInAdapter(StockInAdapter):
    """
    Adapter for Beer stock-in (sold by bottle, purchased by crate).
    
    Inputs:
        - number_of_crates (required)
        - cost_per_crate (required)
        - loose_bottles (optional, default 0)
        - date_received, notes (optional)
    
    System computes:
        - total_bottles = crates * 20 + loose
        - total_cost = crates * cost_per_crate
        - cost_per_bottle = total_cost / total_bottles (quantize 2dp)
    """
    
    BOTTLES_PER_CRATE = 20
    
    @staticmethod
    def adapt(user_inputs: Dict[str, Any]) -> Dict[str, Any]:
        number_of_crates = int(user_inputs.get('number_of_crates', 0))
        cost_per_crate = Decimal(str(user_inputs.get('cost_per_crate', 0)))
        loose_bottles = int(user_inputs.get('loose_bottles', 0))
        
        if number_of_crates < 0:
            raise ValueError("Number of crates cannot be negative")
        if cost_per_crate <= 0:
            raise ValueError("Cost per crate must be greater than 0")
        if loose_bottles < 0:
            raise ValueError("Loose bottles cannot be negative")
        
        # Calculate total bottles
        total_bottles = number_of_crates * BeerStockInAdapter.BOTTLES_PER_CRATE + loose_bottles
        
        if total_bottles == 0:
            raise ValueError("Total bottles must be greater than 0")
        
        # Calculate total cost (only for crates, loose bottles cost is implicit)
        total_cost = cost_per_crate * Decimal(number_of_crates)
        
        # Calculate cost per bottle
        cost_per_bottle = quantize_2dp(total_cost / Decimal(total_bottles))
        
        return {
            'quantity_units_added': total_bottles,
            'unit_cost': cost_per_bottle,
            'total_cost': total_cost,
            'notes': user_inputs.get('notes', ''),
            'metadata': {
                'category': 'beer',
                'number_of_crates': number_of_crates,
                'loose_bottles': loose_bottles,
                'cost_per_crate': float(cost_per_crate),
            }
        }


class CiderStockInAdapter(StockInAdapter):
    """
    Adapter for Cider stock-in (sold by bottle).
    
    Inputs:
        - quantity_bottles (required)
        - cost_per_bottle (required)
    
    System computes:
        - total_cost = quantity * cost_per_bottle
    """
    
    @staticmethod
    def adapt(user_inputs: Dict[str, Any]) -> Dict[str, Any]:
        quantity_bottles = int(user_inputs.get('quantity_bottles', 0))
        cost_per_bottle = Decimal(str(user_inputs.get('cost_per_bottle', 0)))
        
        if quantity_bottles <= 0:
            raise ValueError("Quantity must be greater than 0")
        if cost_per_bottle <= 0:
            raise ValueError("Cost per bottle must be greater than 0")
        
        total_cost = cost_per_bottle * Decimal(quantity_bottles)
        
        return {
            'quantity_units_added': quantity_bottles,
            'unit_cost': cost_per_bottle,
            'total_cost': quantize_2dp(total_cost),
            'notes': user_inputs.get('notes', ''),
            'metadata': {
                'category': 'cider',
                'quantity_bottles': quantity_bottles,
            }
        }


class WineStockInAdapter(StockInAdapter):
    """
    Adapter for Wine stock-in (sold by glass, purchased by bottle).
    
    Inputs:
        - number_of_bottles (required)
        - cost_per_bottle (required)
    
    System computes:
        - glasses = bottles * 5
        - unit_cost_per_glass = cost_per_bottle / 5
        - total_cost = bottles * cost_per_bottle
    
    Note: Stock is tracked in glasses (sellable unit).
    """
    
    GLASSES_PER_BOTTLE = 5
    
    @staticmethod
    def adapt(user_inputs: Dict[str, Any]) -> Dict[str, Any]:
        number_of_bottles = int(user_inputs.get('number_of_bottles', 0))
        cost_per_bottle = Decimal(str(user_inputs.get('cost_per_bottle', 0)))
        
        if number_of_bottles <= 0:
            raise ValueError("Number of bottles must be greater than 0")
        if cost_per_bottle <= 0:
            raise ValueError("Cost per bottle must be greater than 0")
        
        # Calculate glasses (sellable unit)
        total_glasses = number_of_bottles * WineStockInAdapter.GLASSES_PER_BOTTLE
        
        # Calculate cost per glass
        cost_per_glass = quantize_2dp(cost_per_bottle / Decimal(WineStockInAdapter.GLASSES_PER_BOTTLE))
        
        # Calculate total cost
        total_cost = cost_per_bottle * Decimal(number_of_bottles)
        
        return {
            'quantity_units_added': total_glasses,
            'unit_cost': cost_per_glass,
            'total_cost': quantize_2dp(total_cost),
            'notes': user_inputs.get('notes', ''),
            'metadata': {
                'category': 'wine',
                'number_of_bottles': number_of_bottles,
                'glasses_per_bottle': WineStockInAdapter.GLASSES_PER_BOTTLE,
            }
        }


class SpiritsStockInAdapter(StockInAdapter):
    """
    Adapter for Spirits stock-in (sold by shot).
    
    Inputs:
        - quantity_of_shots_added (required)
        - cost_per_shot (required)
        - reserved_barman_shots (optional, default 0)
    
    System computes:
        - sellable_shots = quantity - reserved
        - total_cost = quantity * cost_per_shot
        - equivalent_bottles = quantity / 30 (for reporting)
    
    Note: Reserved shots are NOT sellable and should not be added to inventory.
    """
    
    SHOTS_PER_BOTTLE = 30
    
    @staticmethod
    def adapt(user_inputs: Dict[str, Any]) -> Dict[str, Any]:
        quantity_of_shots_added = int(user_inputs.get('quantity_of_shots_added', 0))
        cost_per_shot = Decimal(str(user_inputs.get('cost_per_shot', 0)))
        reserved_barman_shots = int(user_inputs.get('reserved_barman_shots', 0))
        
        if quantity_of_shots_added <= 0:
            raise ValueError("Quantity of shots must be greater than 0")
        if cost_per_shot <= 0:
            raise ValueError("Cost per shot must be greater than 0")
        if reserved_barman_shots < 0:
            raise ValueError("Reserved shots cannot be negative")
        if reserved_barman_shots >= quantity_of_shots_added:
            raise ValueError("Reserved shots cannot exceed or equal total quantity")
        
        # Calculate sellable shots
        sellable_shots = quantity_of_shots_added - reserved_barman_shots
        
        # Calculate total cost (for ALL shots including reserved)
        total_cost = cost_per_shot * Decimal(quantity_of_shots_added)
        
        # Equivalent bottles for reporting
        equivalent_bottles = quantity_of_shots_added / SpiritsStockInAdapter.SHOTS_PER_BOTTLE
        
        return {
            'quantity_units_added': sellable_shots,
            'unit_cost': cost_per_shot,
            'total_cost': quantize_2dp(total_cost),
            'notes': user_inputs.get('notes', ''),
            'metadata': {
                'category': 'spirits',
                'total_shots_added': quantity_of_shots_added,
                'reserved_shots': reserved_barman_shots,
                'sellable_shots': sellable_shots,
                'equivalent_bottles': float(equivalent_bottles),
            }
        }


class WhiskyStockInAdapter(SpiritsStockInAdapter):
    """
    Adapter for Whisky stock-in (same as Spirits - sold by shot).
    Inherits all logic from SpiritsStockInAdapter.
    """
    
    @staticmethod
    def adapt(user_inputs: Dict[str, Any]) -> Dict[str, Any]:
        result = SpiritsStockInAdapter.adapt(user_inputs)
        result['metadata']['category'] = 'whisky'
        return result


def get_adapter_for_category(category: str) -> StockInAdapter:
    """
    Factory function to get the appropriate adapter for a category.
    
    Args:
        category: Product category (beer, cider, wine, spirits, whisky)
    
    Returns:
        Appropriate StockInAdapter subclass
    
    Raises:
        ValueError: If category is not supported
    """
    category_lower = category.lower().strip()
    
    adapters = {
        'beer': BeerStockInAdapter,
        'cider': CiderStockInAdapter,
        'wine': WineStockInAdapter,
        'spirits': SpiritsStockInAdapter,
        'whisky': WhiskyStockInAdapter,
    }
    
    adapter = adapters.get(category_lower)
    if not adapter:
        raise ValueError(f"Unsupported category: {category}")
    
    return adapter


def save_stock_in_transaction(product, adapted_data: Dict[str, Any], user, business=None, location=None, date_received=None) -> None:
    """
    Unified stock-in transaction save function.
    
    Args:
        product: MerchProduct instance
        adapted_data: Output from adapter.adapt() containing:
            - quantity_units_added
            - unit_cost
            - total_cost
            - notes
            - metadata
            - date_received (optional) - business date when stock was received
        user: User performing the transaction
        business: Business instance (optional, will use product.business)
        location: Location instance (optional)
        date_received: Date when stock was received (optional, defaults to today)
    """
    with transaction.atomic():
        # Update product stock
        current_stock = product.quantity_in_stock or 0
        product.quantity_in_stock = current_stock + adapted_data['quantity_units_added']
        
        # Update cost price
        product.cost_per_bottle = adapted_data['unit_cost']
        
        product.save(update_fields=['quantity_in_stock', 'cost_per_bottle'])
        
        # Create stock-in transaction log for COGS tracking (Liquor COGS card is inventory purchases cost when sales COGS is unavailable)
        from inventory.models_verticals import LiquorStockInTransaction
        from inventory.business_kinds import BusinessKind
        
        if product.kind == BusinessKind.LIQUOR:
            txn_data = {
                'business': business or product.business,
                'location': location,
                'product': product,
                'quantity_added': adapted_data['quantity_units_added'],
                'unit_cost': adapted_data['unit_cost'],
                'total_cost': adapted_data['total_cost'],
                'notes': adapted_data.get('notes', ''),
                'created_by': user,
            }
            
            # Use date_received from adapted_data if present, then from parameter, otherwise default to today
            if 'date_received' in adapted_data and adapted_data['date_received']:
                txn_data['date_received'] = adapted_data['date_received']
            elif date_received:
                txn_data['date_received'] = date_received
            
            LiquorStockInTransaction.objects.create(**txn_data)

