# inventory/decorators.py
"""
Compatibility shim for inventory decorators.

This module re-exports decorators from their canonical locations to maintain
backward compatibility with imports like:
    from inventory.decorators import require_business

The actual implementations live in tenants.utils (require_business) and
tenants.decorators (require_vertical, etc.).
"""

# Re-export require_business from its canonical location
from tenants.utils import require_business

# Re-export vertical decorators if needed
try:
    from tenants.decorators import require_vertical, require_business_access, scope_to_business
except ImportError:
    # Graceful fallback if decorators module doesn't exist yet
    require_vertical = None
    require_business_access = None
    scope_to_business = None

__all__ = [
    "require_business",
    "require_vertical",
    "require_business_access",
    "scope_to_business",
]
