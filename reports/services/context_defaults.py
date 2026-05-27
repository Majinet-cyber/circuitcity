"""
Reports Context Defaults - Single Source of Truth for Report/Dashboard Context Keys

This module provides safe default values for all report and dashboard context keys
to prevent KeyError failures in templates and views.

PROBLEM SOLVED:
- KeyError: 'sold_today'
- KeyError: 'payment_mix_json'
- KeyError: 'report_trend_json'
- KeyError: 'report_summary'

USAGE in views:
    from reports.services.context_defaults import apply_default_report_context
    
    ctx = {
        "business": business,
        "report_summary": {...},  # your data
    }
    
    # Apply defaults before render (ensures all keys exist)
    ctx = apply_default_report_context(ctx)
    return render(request, "reports/home.html", ctx)

NAMING CONVENTION:
All report context keys use lower_snake_case for consistency with Django conventions.
"""
from __future__ import annotations
from decimal import Decimal
from typing import Any, Dict


# ============================================================================
# SSOT: Report Context Defaults
# ============================================================================

REPORT_CONTEXT_DEFAULTS = {
    # Sales metrics
    "sold_today": 0,
    "sales_count": 0,
    "units_sold": 0,
    "items_sold_today": 0,
    
    # Financial metrics (safe zero defaults)
    "total_revenue": Decimal("0.00"),
    "total_costs": Decimal("0.00"),
    "total_profit": Decimal("0.00"),
    "revenue_today": Decimal("0.00"),
    "profit_today": Decimal("0.00"),
    "cost_today": Decimal("0.00"),
    
    # Summary dict (for reports)
    "report_summary": {
        "total_revenue": 0.0,
        "total_cogs": 0.0,
        "total_costs": 0.0,
        "total_commissions": 0.0,
        "gross_profit": 0.0,
        "net_profit": 0.0,
        "sales_count": 0,
    },
    
    # JSON-serialized data for charts (safe empty defaults)
    "payment_mix_json": "[]",
    "report_trend_json": "[]",
    "quotes_json": "[]",
    
    # Lists for top performers
    "top_products": [],
    "top_agents": [],
    
    # Payment mix
    "payment_mix": None,
    "payment_mix_period": None,
    
    # Stock metrics
    "items_in_stock": 0,
    "active_stock_count": 0,
    "stock_value": Decimal("0.00"),
    
    # Period labels
    "period_start": None,
    "period_end": None,
    "period_label": "Today",
    "range_label": "Today",
    
    # Filters
    "filters": None,
    
    # Daily sales targets (for gamification)
    "daily_sales_target": 0,
    "sales_progress_pct": 0,
}


# ============================================================================
# Main SSOT Function
# ============================================================================

def apply_default_report_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply safe default values for all report/dashboard context keys.
    
    This function ensures that all expected keys exist in the context,
    preventing KeyError failures in templates and views.
    
    Args:
        context: Existing context dict from view
        
    Returns:
        Context dict with all default keys applied (existing values preserved)
        
    Example:
        >>> ctx = {"business": biz, "sold_today": 5}
        >>> ctx = apply_default_report_context(ctx)
        >>> # ctx now has all default keys, with sold_today=5 preserved
    """
    # Create a new dict starting with defaults
    result = REPORT_CONTEXT_DEFAULTS.copy()
    
    # Override with provided values (preserves all explicit values)
    result.update(context)
    
    # Special handling: merge report_summary if it exists
    if "report_summary" in context and isinstance(context["report_summary"], dict):
        # Start with default summary
        merged_summary = REPORT_CONTEXT_DEFAULTS["report_summary"].copy()
        # Merge in provided summary values
        merged_summary.update(context["report_summary"])
        result["report_summary"] = merged_summary
    
    return result


# ============================================================================
# Helper: Apply defaults only for specific keys (if needed)
# ============================================================================

def ensure_keys_exist(context: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    """
    Ensure specific keys exist in context (useful for partial updates).
    
    Args:
        context: Existing context dict
        *keys: Keys to ensure exist (must be in REPORT_CONTEXT_DEFAULTS)
        
    Returns:
        Context dict with specified keys guaranteed to exist
        
    Example:
        >>> ctx = {"business": biz}
        >>> ctx = ensure_keys_exist(ctx, "sold_today", "payment_mix_json")
        >>> # ctx now has sold_today=0 and payment_mix_json="[]"
    """
    result = context.copy()
    for key in keys:
        if key not in result and key in REPORT_CONTEXT_DEFAULTS:
            result[key] = REPORT_CONTEXT_DEFAULTS[key]
    return result


# ============================================================================
# SSOT Alias: apply_report_defaults (canonical shorthand)
# ============================================================================

def apply_report_defaults(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply safe default values for report/dashboard context keys.
    
    This is the canonical SSOT function for ensuring all report context keys
    exist with safe defaults. Use this in all views that render reports or
    dashboard templates.
    
    This is an alias for apply_default_report_context with a shorter name
    following the naming convention requested in the SSOT implementation spec.
    
    Args:
        ctx: Existing context dict from view
        
    Returns:
        Context dict with all default keys applied (existing values preserved)
        
    Example:
        >>> ctx = {"business": biz, "custom_key": "value"}
        >>> ctx = apply_report_defaults(ctx)
        >>> # ctx now has sold_today=0, payment_mix_json="[]", etc.
        >>> # custom_key="value" is preserved
        
    SSOT Keys Guaranteed:
        - sold_today: 0
        - payment_mix_json: "[]"
        - report_trend_json: "[]"
        - report_summary: {...}
        - And all other REPORT_CONTEXT_DEFAULTS keys
    """
    # Use setdefault pattern for efficiency
    ctx.setdefault("sold_today", 0)
    ctx.setdefault("payment_mix_json", "[]")
    ctx.setdefault("report_trend_json", "[]")
    ctx.setdefault("report_summary", REPORT_CONTEXT_DEFAULTS["report_summary"].copy())
    
    # Apply remaining defaults using the full function
    return apply_default_report_context(ctx)
