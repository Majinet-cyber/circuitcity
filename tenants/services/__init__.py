# tenants/services/__init__.py
"""
SSOT services for tenant management.

This package contains canonical helpers for:
- Active business resolution
- Business kind normalization
- Other tenant-scoped operations
"""
from .active_business import (
    get_active_business,
    ensure_active_business,
    set_active_business,
)

__all__ = [
    "get_active_business",
    "ensure_active_business",
    "set_active_business",
]

