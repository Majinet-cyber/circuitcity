"""
Vertical Registry for Data Corrections (Feb 2026)
==================================================

A plugin-style registry that allows each vertical to register its correctable
entities, fields, validators, and query helpers.

Architecture:
- VerticalAdapter: Abstract base class for vertical-specific logic
- VerticalRegistry: Singleton that holds all registered verticals
- Decorator: @register_vertical('phones') for easy registration

Example Usage:
    # In corrections/adapters/phones.py
    from corrections.registry import register_vertical, VerticalAdapter

    @register_vertical('phones')
    class PhonesAdapter(VerticalAdapter):
        vertical_key = 'phones'
        vertical_label = 'Phones'

        def get_entities(self):
            return {
                'sale': {
                    'model': InventoryItem,
                    'label': 'Phone Sale',
                    'fields': {
                        'selling_price': {
                            'type': 'decimal',
                            'label': 'Selling Price',
                            'validator': lambda val: Decimal(val) > 0,
                            'coercer': lambda val: Decimal(val),
                        },
                        'order_price': {
                            'type': 'decimal',
                            'label': 'Order/Cost Price',
                            'validator': lambda val: Decimal(val) >= 0,
                            'coercer': lambda val: Decimal(val),
                        },
                        'imei': {
                            'type': 'string',
                            'label': 'IMEI',
                            'validator': lambda val: len(val) == 15 and val.isdigit(),
                            'coercer': lambda val: normalize_imei(val),
                        },
                    },
                },
            }

        def find_erroneous_entries(self, entity_label):
            if entity_label == 'sale':
                # Find sales with suspicious pricing
                return InventoryItem.objects.filter(
                    status='SOLD',
                    selling_price__lt=models.F('order_price')  # selling < cost
                )
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Type

from django.db.models import Model, QuerySet


class FieldConfig:
    """Configuration for a correctable field."""
    
    def __init__(
        self,
        field_name: str,
        label: str,
        field_type: str,  # 'string', 'integer', 'decimal', 'boolean', 'date', 'datetime'
        validator: Optional[Callable[[Any], bool]] = None,
        coercer: Optional[Callable[[Any], Any]] = None,
        help_text: str = '',
        required: bool = True,
    ):
        self.field_name = field_name
        self.label = label
        self.field_type = field_type
        self.validator = validator
        self.coercer = coercer or (lambda x: x)
        self.help_text = help_text
        self.required = required
    
    def validate(self, value: Any) -> tuple[bool, Optional[str]]:
        """
        Validate a value for this field.
        
        Returns:
            (is_valid, error_message)
        """
        if self.required and (value is None or value == ''):
            return False, f'{self.label} is required.'
        
        if value is not None and value != '' and self.validator:
            try:
                if not self.validator(value):
                    return False, f'Invalid {self.label}.'
            except Exception as e:
                return False, f'Validation error for {self.label}: {str(e)}'
        
        return True, None
    
    def coerce(self, value: Any) -> Any:
        """
        Coerce a raw value to the correct type for this field.
        """
        try:
            return self.coercer(value)
        except Exception as e:
            raise ValueError(f'Failed to coerce value for {self.label}: {str(e)}')


class EntityConfig:
    """Configuration for a correctable entity (e.g., 'sale', 'member')."""
    
    def __init__(
        self,
        entity_label: str,
        model: Type[Model],
        label: str,
        fields: Dict[str, FieldConfig],
        description: str = '',
        business_filter_path: str = 'business',
        base_filters: Optional[Dict[str, Any]] = None,
    ):
        self.entity_label = entity_label
        self.model = model
        self.label = label
        self.fields = fields
        self.description = description
        self.business_filter_path = business_filter_path  # e.g., 'business' or 'member__business'
        self.base_filters = base_filters or {}  # Additional filters (e.g., kind='pharmacy')
    
    def get_field(self, field_name: str) -> Optional[FieldConfig]:
        """Get field config by name."""
        return self.fields.get(field_name)
    
    def validate_field(self, field_name: str, value: Any) -> tuple[bool, Optional[str]]:
        """Validate a field value."""
        field_config = self.get_field(field_name)
        if not field_config:
            return False, f'Unknown field: {field_name}'
        return field_config.validate(value)
    
    def coerce_field(self, field_name: str, value: Any) -> Any:
        """Coerce a field value."""
        field_config = self.get_field(field_name)
        if not field_config:
            raise ValueError(f'Unknown field: {field_name}')
        return field_config.coerce(value)


class VerticalAdapter(ABC):
    """
    Abstract base class for vertical-specific correction logic.
    
    Each vertical (Phones, Clothing, Gym, etc.) implements an adapter that:
    - Defines correctable entities and their fields
    - Provides validators and coercers for each field
    - Optionally provides query helpers to find erroneous entries
    """
    
    vertical_key: str = ''  # e.g., 'phones', 'clothing', 'gym'
    vertical_label: str = ''  # e.g., 'Phones', 'Clothing', 'Gym'
    
    @abstractmethod
    def get_entities(self) -> Dict[str, EntityConfig]:
        """
        Return a dict of entity configs.
        
        Example:
            {
                'sale': EntityConfig(...),
                'accessory': EntityConfig(...),
            }
        """
        pass
    
    def find_erroneous_entries(
        self,
        entity_label: str,
        business,
        limit: int = 50,
    ) -> QuerySet:
        """
        Optional: Return a queryset of potentially erroneous entries for this entity.
        
        This is a helper for managers to quickly find records that may need correction.
        
        Example:
            # Find phone sales where selling price < order price
            if entity_label == 'sale':
                return InventoryItem.objects.filter(
                    business=business,
                    status='SOLD',
                    selling_price__lt=models.F('order_price')
                )[:limit]
        """
        # Default: return empty queryset
        model = self.get_entities()[entity_label].model
        return model.objects.none()
    
    def calculate_impact(
        self,
        entity_label: str,
        obj,
        field_name: str,
        old_value: Any,
        new_value: Any,
    ) -> Dict[str, Decimal]:
        """
        Optional: Calculate financial impact of a correction.
        
        Returns:
            {
                'revenue_impact': Decimal('0.00'),
                'profit_impact': Decimal('0.00'),
            }
        """
        return {
            'revenue_impact': Decimal('0.00'),
            'profit_impact': Decimal('0.00'),
        }
    
    def post_correction_hook(
        self,
        entity_label: str,
        obj,
        field_name: str,
        old_value: Any,
        new_value: Any,
    ) -> None:
        """
        Optional: Post-correction hook called after a field is updated.
        
        Use this to:
        - Recalculate derived fields (e.g., totals from line items)
        - Validate business rules (e.g., expiry >= manufacture date)
        - Trigger side effects (e.g., update related records)
        
        This is called AFTER the field is saved but within the same transaction.
        
        Args:
            entity_label: Entity being corrected (e.g., 'pharmacy_sale')
            obj: The model instance that was just updated
            field_name: Name of the field that was corrected
            old_value: Previous value
            new_value: New value
        """
        pass  # Default: no action


class VerticalRegistry:
    """
    Singleton registry of all vertical adapters.
    
    Provides:
    - get_adapter(vertical_key) -> VerticalAdapter
    - list_verticals() -> List[str]
    - get_entities(vertical_key) -> Dict[str, EntityConfig]
    """
    
    _instance = None
    _adapters: Dict[str, VerticalAdapter] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, adapter: VerticalAdapter):
        """Register a vertical adapter."""
        if not adapter.vertical_key:
            raise ValueError('VerticalAdapter must have a vertical_key')
        
        if adapter.vertical_key in self._adapters:
            print(f'[VerticalRegistry] Warning: Overwriting adapter for {adapter.vertical_key}')
        
        self._adapters[adapter.vertical_key] = adapter
        print(f'[VerticalRegistry] Registered adapter: {adapter.vertical_key} ({adapter.vertical_label})')
    
    def get_adapter(self, vertical_key: str) -> Optional[VerticalAdapter]:
        """Get adapter by vertical key."""
        return self._adapters.get(vertical_key)
    
    def list_verticals(self) -> List[Dict[str, str]]:
        """List all registered verticals."""
        return [
            {
                'key': key,
                'label': adapter.vertical_label,
            }
            for key, adapter in self._adapters.items()
        ]
    
    def get_entities(self, vertical_key: str) -> Optional[Dict[str, EntityConfig]]:
        """Get entities for a vertical."""
        adapter = self.get_adapter(vertical_key)
        if not adapter:
            return None
        return adapter.get_entities()
    
    def get_entity(self, vertical_key: str, entity_label: str) -> Optional[EntityConfig]:
        """Get a specific entity config."""
        entities = self.get_entities(vertical_key)
        if not entities:
            return None
        return entities.get(entity_label)


# Global registry instance
registry = VerticalRegistry()


def register_vertical(vertical_key: str):
    """
    Decorator to register a vertical adapter.
    
    Usage:
        @register_vertical('phones')
        class PhonesAdapter(VerticalAdapter):
            vertical_key = 'phones'
            vertical_label = 'Phones'
            ...
    """
    def decorator(adapter_class: Type[VerticalAdapter]):
        # Instantiate adapter
        adapter = adapter_class()
        
        # Override vertical_key if provided in decorator
        if vertical_key:
            adapter.vertical_key = vertical_key
        
        # Register
        registry.register(adapter)
        
        return adapter_class
    
    return decorator


# Export
__all__ = [
    'FieldConfig',
    'EntityConfig',
    'VerticalAdapter',
    'VerticalRegistry',
    'registry',
    'register_vertical',
]

