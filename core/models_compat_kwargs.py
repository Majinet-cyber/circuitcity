"""
core/models_compat_kwargs.py

Single Source of Truth (SSOT) for backwards-compatible kwarg handling.

This mixin allows Django models to accept legacy/deprecated kwargs during
__init__ and map them to their canonical field names, preventing TypeErrors
in tests and legacy code while maintaining a clean migration path.

Usage:
    class MyModel(CompatKwargsMixin, models.Model):
        COMPAT_MAP = {
            'old_kwarg': 'new_field',
            'another_old': 'canonical_field',
        }
        ...

Benefits:
- No code duplication across models
- Centralized compatibility logic
- Easy to deprecate: just remove entries from COMPAT_MAP
- Zero impact on production queries (only affects __init__)
- Preserves all Django model functionality (migrations, querysets, etc.)

Special handling:
- If the mapped field name starts with '_ignored_', the kwarg is dropped
  without mapping (useful for accepting kwargs that don't correspond to any field)
"""


class CompatKwargsMixin:
    """
    Mixin to handle backwards-compatible keyword arguments in model __init__.
    
    Subclasses should define a COMPAT_MAP dict mapping old kwargs to new field names.
    During __init__, any kwargs in COMPAT_MAP are automatically renamed before
    passing to the parent __init__.
    
    Example:
        class Business(CompatKwargsMixin, models.Model):
            COMPAT_MAP = {'vertical': 'business_kind', 'kind': 'business_kind'}
            business_kind = models.CharField(...)
    
    Now both of these work:
        Business(vertical='phones')  # legacy
        Business(business_kind='phones')  # canonical
    
    Special case - ignoring kwargs:
        class Product(CompatKwargsMixin, models.Model):
            COMPAT_MAP = {'business': '_ignored_business'}  # Silently drop 'business' kwarg
    """
    
    COMPAT_MAP = {}
    
    def __init__(self, *args, **kwargs):
        """
        Process compatibility kwargs before calling parent __init__.
        
        For each entry in COMPAT_MAP:
        - If the old kwarg is present in kwargs, rename it to the canonical field
        - If both old and new are present, canonical field takes precedence
        - Pop the old kwarg so Django doesn't see it
        - If the mapped field starts with '_ignored_', drop the kwarg entirely
        """
        if self.COMPAT_MAP:
            for old_name, new_name in self.COMPAT_MAP.items():
                if old_name in kwargs:
                    # Special case: if new_name starts with '_ignored_', just drop the kwarg
                    if new_name.startswith('_ignored_'):
                        kwargs.pop(old_name)
                    else:
                        # Only map if canonical field not already provided
                        if new_name not in kwargs:
                            kwargs[new_name] = kwargs[old_name]
                        # Always pop the old kwarg to prevent TypeError
                        kwargs.pop(old_name)
        
        super().__init__(*args, **kwargs)


