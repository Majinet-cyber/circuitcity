# inventory/analytics/__init__.py
"""
Analytics package for business intelligence across all verticals.
Provides adapter-based architecture for vertical-specific analytics.
"""

from .registry import get_adapter

__all__ = ["get_adapter"]
