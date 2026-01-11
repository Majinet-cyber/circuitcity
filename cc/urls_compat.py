# cc/urls_compat.py
"""
SINGLE SOURCE OF TRUTH (SSOT) for URL name compatibility aliases.

This module defines backward-compatible URL aliases that are imported and used
across multiple URLConf files to ensure consistency without duplication.

IMPORTANT: This is the ONE AND ONLY place where these aliases are defined.
All URLConfs that need these aliases MUST import from here.

Usage in URLConf files:
    from cc.urls_compat import get_compat_urlpatterns
    urlpatterns += get_compat_urlpatterns()
"""
from django.urls import path
from django.views.generic import RedirectView


def get_compat_urlpatterns():
    """
    Return a list of backward-compatible URL patterns.
    
    These patterns allow legacy code and tests to use simple URL names
    without namespace prefixes:
    - reverse('home') → /home/
    - reverse('stock') → redirects to inventory:stock_list
    - reverse('sell') → redirects to inventory:scan_sold
    - reverse('scan') → redirects to inventory:scan_in
    - reverse('wallet') → redirects to wallet:agent_wallet
    - reverse('sim') → redirects to simulator:home
    - reverse('businesses') → redirects to hq:business_directory
    - reverse('pharmacy_stock_in') → redirects to pharmacy:stock_in
    - reverse('member_qr_image') → redirects to gym:members_list (fallback when no UUID)
    - reverse('member_qr_image_with_uuid', kwargs={'qr_uuid': uuid}) → redirects to gym:member_qr_png
      (defined in urls_compat_extra.py)
    - reverse('export_monthly_costs') → redirects to reports:export_monthly_costs
    - reverse('export_monthly_sales') → redirects to reports:export_monthly_sales
    - reverse('export_monthly_summary') → redirects to reports:export_monthly_summary
    
    Returns:
        list: List of URL patterns for compatibility aliases
    """
    return [
        # ======================================================================================
        # BACKWARDS-COMPATIBLE GLOBAL ALIASES (SSOT)
        # These allow reverse('name') to work without namespace prefixes.
        # ======================================================================================
        
        # Core aliases
        path("__alias__/stock/", RedirectView.as_view(pattern_name="inventory:stock_list", permanent=False), name="stock"),
        path("__alias__/sell/", RedirectView.as_view(pattern_name="inventory:scan_sold", permanent=False), name="sell"),
        path("__alias__/scan/", RedirectView.as_view(pattern_name="inventory:scan_in", permanent=False), name="scan"),
        path("__alias__/wallet/", RedirectView.as_view(pattern_name="wallet:agent_wallet", permanent=False), name="wallet"),
        path("__alias__/sim/", RedirectView.as_view(pattern_name="simulator:home", permanent=False), name="sim"),
        path("__alias__/businesses/", RedirectView.as_view(pattern_name="hq:business_directory", permanent=False), name="businesses"),
        
        # Vertical-specific aliases
        path("__alias__/pharmacy-stock-in/", RedirectView.as_view(pattern_name="pharmacy:stock_in", permanent=False), name="pharmacy_stock_in"),
        # NOTE: member_qr_image without UUID redirects to gym members list.
        # Use reverse('member_qr_image_with_uuid', kwargs={'qr_uuid': ...}) for specific member QR.
        path("__alias__/member-qr-image/", RedirectView.as_view(pattern_name="gym:members_list", permanent=False), name="member_qr_image"),
        
        # Reports export aliases (point to canonical reports:export_* URLs)
        path("__alias__/export-monthly-costs/", RedirectView.as_view(pattern_name="reports:export_monthly_costs", permanent=False), name="export_monthly_costs"),
        path("__alias__/export-monthly-sales/", RedirectView.as_view(pattern_name="reports:export_monthly_sales", permanent=False), name="export_monthly_sales"),
        path("__alias__/export-monthly-summary/", RedirectView.as_view(pattern_name="reports:export_monthly_summary", permanent=False), name="export_monthly_summary"),
    ]


def get_compat_urlpatterns_for_app_router():
    """
    Return compatibility patterns specifically for app_router namespace.
    
    These patterns are included in app_router/urls.py to ensure that
    reverse() calls within that context can resolve compatibility names.
    
    Returns:
        list: List of URL patterns scoped to app_router
    """
    return [
        # App router has its own 'home', 'scan', 'sell', 'stock', 'wallet', 'sim' 
        # in the app_router namespace, so these are already covered.
        # We only need to add any missing cross-namespace aliases if needed.
    ]


# Convenience function for testing
def all_compat_url_names():
    """
    Return a list of all compatibility URL names defined in this module.
    
    Useful for testing that all expected names can be reversed.
    
    Returns:
        list: List of URL name strings
    """
    return [
        'home',  # Note: 'home' is defined in main cc/urls.py, not here
        'stock',
        'sell',
        'scan',
        'wallet',
        'sim',
        'businesses',
        'pharmacy_stock_in',
        'member_qr_image',  # Redirects to gym:members_list (no UUID required)
        'member_qr_image_with_uuid',  # Defined in urls_compat_extra.py (requires UUID)
        'export_monthly_costs',
        'export_monthly_sales',
        'export_monthly_summary',
    ]

