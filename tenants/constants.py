"""
Canonical constants for the tenants app.

This module provides the single source of truth for BusinessKind and other
tenant-related constants. All code should import from here.
"""
from inventory.business_kinds import BusinessKind

__all__ = ["BusinessKind"]
