"""
=============================================================================
SINGLE SOURCE OF TRUTH: Post-Authentication Redirect Logic
=============================================================================

This module provides centralized redirect logic after login/signup.

CRITICAL RULES:
1. On signup (any vertical): land on that vertical's Dashboard (NOT analytics)
2. On login: land on that business's Dashboard (NOT analytics)
3. Must be a single shared helper (no per-view hacks)

Usage:
    from circuitcity.accounts.services.post_auth_redirect import (
        get_post_login_redirect,
        get_post_signup_redirect
    )
    
    # After login
    return redirect(get_post_login_redirect(user, request))
    
    # After signup
    return redirect(get_post_signup_redirect(user, request, business))

=============================================================================
"""

import logging
from typing import Optional

from django.http import HttpRequest
from django.urls import reverse

logger = logging.getLogger(__name__)


def _get_vertical_dashboard_url(business_kind: str) -> str:
    """
    Map business_kind to its vertical-specific dashboard URL.
    
    This is the SINGLE SOURCE OF TRUTH for vertical dashboard routing.
    
    Args:
        business_kind: The business vertical (e.g., 'phones', 'clothing', 'gym')
        
    Returns:
        str: The URL name for the vertical's dashboard
    """
    # Vertical dashboard URL mapping
    VERTICAL_DASHBOARDS = {
        'phones': 'inventory_verticals:phones_dashboard',  # /inventory/verticals/phones/
        'clothing': 'verticals:clothing_dashboard',
        'gym': 'gym:dashboard',
        'cement': 'cement:dashboard',
        'hardware': 'cement:dashboard',  # Hardware uses cement dashboard
        'general_dealers': 'cement:dashboard',
        'liquor': 'liquor:dashboard',
        'farm': 'verticals:farm_dashboard',  # Farm Manager vertical
        'welding': 'verticals:welding_dashboard',  # Welding Workshop vertical
        'car_hire': 'verticals:car_hire_dashboard',  # Car Hire Service vertical
    }
    
    dashboard_url_name = VERTICAL_DASHBOARDS.get(
        business_kind,
        'inventory:inventory_dashboard'  # Safe fallback
    )
    
    try:
        return reverse(dashboard_url_name)
    except Exception as e:
        logger.warning(
            f"Could not reverse dashboard URL for {business_kind}: {e}. "
            f"Falling back to default dashboard."
        )
        # Ultimate fallback
        try:
            return reverse('inventory:inventory_dashboard')
        except Exception:
            return '/dashboard/'


def get_post_login_redirect(user, request: Optional[HttpRequest] = None) -> str:
    """
    Determine where to redirect user after successful login.
    
    ALWAYS redirects to the vertical's dashboard (never analytics).
    
    Args:
        user: The authenticated user object
        request: The HTTP request object (optional, but recommended)
        
    Returns:
        str: The redirect URL path
    """
    # Try to get business from request
    business = None
    if request:
        business = getattr(request, 'business', None)
        
        # Try session if not in request
        if not business:
            try:
                from tenants.models import Business
                business_id = request.session.get('active_business_id')
                if business_id:
                    business = Business.objects.filter(id=business_id).first()
            except Exception as e:
                logger.debug(f"Could not get business from session: {e}")
    
    # Try to get business from user's memberships
    if not business:
        try:
            from tenants.models import Membership
            membership = Membership.objects.filter(
                user=user,
                status='ACTIVE'
            ).select_related('business').first()
            
            if membership and hasattr(membership, 'business'):
                business = membership.business
        except Exception as e:
            logger.debug(f"Could not get business from membership: {e}")
    
    # Get vertical dashboard URL
    if business:
        business_kind = getattr(business, 'business_kind', None) or \
                       getattr(business, 'kind', None) or \
                       'phones'  # Safe default
        
        logger.info(
            f"Post-login redirect for user {user.id} to {business_kind} dashboard"
        )
        return _get_vertical_dashboard_url(business_kind)
    
    # No business found - redirect to default dashboard
    logger.info(
        f"Post-login redirect for user {user.id} to default dashboard (no business)"
    )
    try:
        return reverse('dashboard:home')
    except Exception:
        return '/dashboard/'


def get_post_signup_redirect(
    user,
    request: Optional[HttpRequest] = None,
    business=None
) -> str:
    """
    Determine where to redirect user after successful signup.
    
    ALWAYS redirects to the vertical's dashboard (never analytics).
    
    Args:
        user: The newly created user object
        request: The HTTP request object (optional)
        business: The business object (optional)
        
    Returns:
        str: The redirect URL path
    """
    # Try to get business from args, request, or user
    if not business and request:
        business = getattr(request, 'business', None)
        
        # Try session
        if not business:
            try:
                from tenants.models import Business
                business_id = request.session.get('active_business_id')
                if business_id:
                    business = Business.objects.filter(id=business_id).first()
            except Exception as e:
                logger.debug(f"Could not get business from session: {e}")
    
    # Try user memberships
    if not business:
        try:
            from tenants.models import Membership
            membership = Membership.objects.filter(
                user=user,
                status='ACTIVE'
            ).select_related('business').first()
            
            if membership and hasattr(membership, 'business'):
                business = membership.business
        except Exception as e:
            logger.debug(f"Could not get business from membership: {e}")
    
    # Get vertical dashboard URL
    if business:
        business_kind = getattr(business, 'business_kind', None) or \
                       getattr(business, 'kind', None) or \
                       'phones'
        
        logger.info(
            f"Post-signup redirect for user {user.id} to {business_kind} dashboard "
            f"(business: {business.name})"
        )
        return _get_vertical_dashboard_url(business_kind)
    
    # No business - redirect to general dashboard
    logger.info(
        f"Post-signup redirect for user {user.id} to default dashboard (no business)"
    )
    try:
        return reverse('dashboard:home')
    except Exception:
        return '/dashboard/'


def get_vertical_home_url(business_kind: str) -> str:
    """
    Get the "home" URL for a specific vertical (alias for dashboard).
    
    This is useful for mobile nav and other UI elements that need to
    link to the vertical's main page.
    
    Args:
        business_kind: The business vertical key
        
    Returns:
        str: The URL path
    """
    return _get_vertical_dashboard_url(business_kind)


def get_vertical_urls_for_nav(business_kind: str) -> dict:
    """
    Get all important URLs for a vertical (for mobile nav, etc.).
    
    Args:
        business_kind: The business vertical key
        
    Returns:
        dict: Dictionary with keys like 'home', 'scan', 'sell', 'stock'
    """
    # Vertical-specific URL patterns
    VERTICAL_NAV_URLS = {
        'phones': {
            'home': 'inventory:inventory_dashboard',
            'scan': 'inventory:scan_in',
            'sell': 'inventory:scan_sold',
            'stock': 'inventory:stock_list',
        },
        'clothing': {
            'home': 'verticals:clothing_dashboard',
            'scan': 'verticals:clothing_scan_in',
            'sell': 'verticals:clothing_sell',
            'stock': 'verticals:clothing_hub',
        },
        'gym': {
            'home': 'gym:dashboard',
            'members': 'gym:members_list',
            'payment': 'gym:add_payment',
            'checkin': 'inventory:time_logs',
        },
        'cement': {
            'home': 'cement:dashboard',
            'sell': 'cement:sell',
            'stock': 'cement:stock_in',
            'products': 'cement:products_catalog',
        },
        'hardware': {
            'home': 'cement:dashboard',
            'sell': 'cement:sell',
            'stock': 'cement:stock_in',
            'products': 'cement:products_catalog',
        },
        'farm': {
            'home': 'verticals:farm_dashboard',
            'ledger': 'verticals:farm_ledger_list',
            'add_expense': 'verticals:farm_add_expense',
            'add_sale': 'verticals:farm_add_sale',
            'livestock': 'verticals:farm_livestock_list',
            'crops': 'verticals:farm_crops_list',
        },
        'welding': {
            'home': 'verticals:welding_dashboard',
            'quotes': 'verticals:welding_quotes_list',
            'jobs': 'verticals:welding_jobs_list',
            'materials': 'verticals:welding_materials_list',
            'stock_in': 'verticals:welding_stock_in',
        },
        'car_hire': {
            'home': 'verticals:car_hire_dashboard',
            'vehicles': 'verticals:car_hire_vehicles',
            'trips': 'verticals:car_hire_trips',
            'add_vehicle': 'verticals:car_hire_vehicle_add',
            'add_trip': 'verticals:car_hire_trip_add',
            'maintenance': 'verticals:car_hire_maintenance',
        },
    }
    
    url_names = VERTICAL_NAV_URLS.get(business_kind, VERTICAL_NAV_URLS['phones'])
    
    # Reverse all URLs
    urls = {}
    for key, url_name in url_names.items():
        try:
            urls[key] = reverse(url_name)
        except Exception as e:
            logger.warning(f"Could not reverse URL {url_name} for {business_kind}: {e}")
            urls[key] = '#'
    
    return urls

