# inventory/liquor_stockin_wizard_adapter.py
"""
Liquor Stock-In Wizard Adapter
Handles type-specific calculation logic for Beer, Cider, Wine, Spirits, and Whisky
"""
from decimal import Decimal
from typing import Dict, Any, Tuple
from django.core.exceptions import ValidationError


class LiquorStockInAdapter:
    """Adapter for computing type-specific stock-in values"""
    
    # Constants
    BEER_BOTTLES_PER_CRATE = 20
    WINE_GLASSES_PER_BOTTLE = 5
    SPIRITS_SHOTS_PER_BOTTLE = 30
    WHISKY_SHOTS_PER_BOTTLE = 30
    
    @classmethod
    def compute_beer_stockin(cls, crates: int, loose_bottles: int, cost_per_crate: Decimal) -> Dict[str, Any]:
        """
        Beer: Crate-based stock-in
        
        Args:
            crates: Number of crates (required, >= 1)
            loose_bottles: Number of loose bottles (optional, >= 0, default 0)
            cost_per_crate: Cost per crate (required, > 0)
        
        Returns:
            {
                'quantity_units_added': int,  # Total bottles
                'unit_cost': Decimal,  # Cost per bottle
                'total_cost': Decimal,
                'calculation_details': dict
            }
        """
        # Validate inputs
        if crates < 1:
            raise ValidationError('Crates must be at least 1')
        if loose_bottles < 0:
            raise ValidationError('Loose bottles cannot be negative')
        if cost_per_crate <= 0:
            raise ValidationError('Cost per crate must be greater than 0')
        
        # Calculate
        total_bottles = (crates * cls.BEER_BOTTLES_PER_CRATE) + loose_bottles
        loose_cost = (cost_per_crate / Decimal(cls.BEER_BOTTLES_PER_CRATE)) * Decimal(loose_bottles)
        total_cost = (Decimal(crates) * cost_per_crate) + loose_cost
        unit_cost_per_bottle = (total_cost / Decimal(total_bottles)).quantize(Decimal('0.01'))
        
        return {
            'quantity_units_added': total_bottles,
            'unit_cost': unit_cost_per_bottle,
            'total_cost': total_cost,
            'calculation_details': {
                'crates': crates,
                'loose_bottles': loose_bottles,
                'cost_per_crate': cost_per_crate,
                'bottles_per_crate': cls.BEER_BOTTLES_PER_CRATE,
            }
        }
    
    @classmethod
    def compute_cider_stockin(cls, quantity_bottles: int, cost_per_bottle: Decimal) -> Dict[str, Any]:
        """
        Cider: Bottle-based stock-in
        
        Args:
            quantity_bottles: Number of bottles (required, >= 1)
            cost_per_bottle: Cost per bottle (required, > 0)
        
        Returns:
            {
                'quantity_units_added': int,
                'unit_cost': Decimal,
                'total_cost': Decimal,
                'calculation_details': dict
            }
        """
        # Validate inputs
        if quantity_bottles < 1:
            raise ValidationError('Quantity must be at least 1')
        if cost_per_bottle <= 0:
            raise ValidationError('Cost per bottle must be greater than 0')
        
        # Calculate
        total_cost = Decimal(quantity_bottles) * cost_per_bottle
        
        return {
            'quantity_units_added': quantity_bottles,
            'unit_cost': cost_per_bottle,
            'total_cost': total_cost,
            'calculation_details': {
                'quantity_bottles': quantity_bottles,
                'cost_per_bottle': cost_per_bottle,
            }
        }
    
    @classmethod
    def compute_wine_stockin(cls, bottles: int, cost_per_bottle: Decimal) -> Dict[str, Any]:
        """
        Wine: Glass-based stock-in (1 bottle = 5 glasses)
        We stock in by bottles but sell by glass
        
        Args:
            bottles: Number of bottles purchased (required, >= 1)
            cost_per_bottle: Cost per bottle (required, > 0)
        
        Returns:
            {
                'quantity_units_added': int,  # Total glasses
                'unit_cost': Decimal,  # Cost per glass
                'total_cost': Decimal,
                'calculation_details': dict
            }
        """
        # Validate inputs
        if bottles < 1:
            raise ValidationError('Bottles must be at least 1')
        if cost_per_bottle <= 0:
            raise ValidationError('Cost per bottle must be greater than 0')
        
        # Calculate
        total_glasses = bottles * cls.WINE_GLASSES_PER_BOTTLE
        total_cost = Decimal(bottles) * cost_per_bottle
        unit_cost_per_glass = (cost_per_bottle / Decimal(cls.WINE_GLASSES_PER_BOTTLE)).quantize(Decimal('0.01'))
        
        return {
            'quantity_units_added': total_glasses,
            'unit_cost': unit_cost_per_glass,
            'total_cost': total_cost,
            'calculation_details': {
                'bottles': bottles,
                'cost_per_bottle': cost_per_bottle,
                'glasses_per_bottle': cls.WINE_GLASSES_PER_BOTTLE,
                'total_glasses': total_glasses,
            }
        }
    
    @classmethod
    def compute_spirits_stockin(cls, shots_added: int, cost_per_shot: Decimal, reserved_barman_shots: int = 0) -> Dict[str, Any]:
        """
        Spirits: Shot-based stock-in with reserved barman shots (1 bottle = 30 shots)
        
        Args:
            shots_added: Total shots added (required, >= 1)
            cost_per_shot: Cost per shot (required, > 0)
            reserved_barman_shots: Reserved shots for barman (optional, >= 0, default 0)
        
        Returns:
            {
                'quantity_units_added': int,  # Sellable shots only
                'unit_cost': Decimal,  # Cost per shot
                'total_cost': Decimal,
                'reserved_shots': int,
                'calculation_details': dict
            }
        """
        # Validate inputs
        if shots_added < 1:
            raise ValidationError('Shots added must be at least 1')
        if cost_per_shot <= 0:
            raise ValidationError('Cost per shot must be greater than 0')
        if reserved_barman_shots < 0:
            raise ValidationError('Reserved shots cannot be negative')
        if reserved_barman_shots >= shots_added:
            raise ValidationError('Reserved shots must be less than total shots added')
        
        # Calculate
        sellable_shots = shots_added - reserved_barman_shots
        total_cost = Decimal(shots_added) * cost_per_shot
        
        return {
            'quantity_units_added': sellable_shots,
            'unit_cost': cost_per_shot,
            'total_cost': total_cost,
            'reserved_shots': reserved_barman_shots,
            'calculation_details': {
                'shots_added': shots_added,
                'cost_per_shot': cost_per_shot,
                'reserved_barman_shots': reserved_barman_shots,
                'sellable_shots': sellable_shots,
                'shots_per_bottle': cls.SPIRITS_SHOTS_PER_BOTTLE,
            }
        }
    
    @classmethod
    def compute_whisky_stockin(cls, shots_added: int, cost_per_shot: Decimal, reserved_barman_shots: int = 0) -> Dict[str, Any]:
        """
        Whisky: Same as Spirits (shot-based with reserved barman shots)
        
        Args:
            shots_added: Total shots added (required, >= 1)
            cost_per_shot: Cost per shot (required, > 0)
            reserved_barman_shots: Reserved shots for barman (optional, >= 0, default 0)
        
        Returns:
            {
                'quantity_units_added': int,  # Sellable shots only
                'unit_cost': Decimal,  # Cost per shot
                'total_cost': Decimal,
                'reserved_shots': int,
                'calculation_details': dict
            }
        """
        # Whisky uses same logic as spirits
        result = cls.compute_spirits_stockin(shots_added, cost_per_shot, reserved_barman_shots)
        result['calculation_details']['shots_per_bottle'] = cls.WHISKY_SHOTS_PER_BOTTLE
        return result
    
    @classmethod
    def compute_stockin(cls, liquor_type: str, **kwargs) -> Dict[str, Any]:
        """
        Dispatch to appropriate computation method based on liquor type
        
        Args:
            liquor_type: One of 'beer', 'cider', 'wine', 'spirits', 'whisky'
            **kwargs: Type-specific parameters
        
        Returns:
            Dict with computed values
        
        Raises:
            ValueError: If liquor_type is invalid
            ValidationError: If inputs are invalid
        """
        liquor_type = liquor_type.lower().strip()
        
        if liquor_type == 'beer':
            return cls.compute_beer_stockin(
                crates=kwargs.get('crates'),
                loose_bottles=kwargs.get('loose_bottles', 0),
                cost_per_crate=kwargs.get('cost_per_crate')
            )
        elif liquor_type == 'cider':
            return cls.compute_cider_stockin(
                quantity_bottles=kwargs.get('quantity_bottles'),
                cost_per_bottle=kwargs.get('cost_per_bottle')
            )
        elif liquor_type == 'wine':
            return cls.compute_wine_stockin(
                bottles=kwargs.get('bottles'),
                cost_per_bottle=kwargs.get('cost_per_bottle')
            )
        elif liquor_type == 'spirits':
            return cls.compute_spirits_stockin(
                shots_added=kwargs.get('shots_added'),
                cost_per_shot=kwargs.get('cost_per_shot'),
                reserved_barman_shots=kwargs.get('reserved_barman_shots', 0)
            )
        elif liquor_type == 'whisky':
            return cls.compute_whisky_stockin(
                shots_added=kwargs.get('shots_added'),
                cost_per_shot=kwargs.get('cost_per_shot'),
                reserved_barman_shots=kwargs.get('reserved_barman_shots', 0)
            )
        else:
            raise ValueError(f'Invalid liquor type: {liquor_type}')




