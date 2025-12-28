# inventory/views_router.py
"""
Business-aware router endpoints that prevent vertical leakage.
These routes read the current business vertical and redirect to the correct vertical-specific URL.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.contrib import messages

from inventory.helpers import business_vertical, get_active_business
from inventory.helpers_core import PHONES, CLOTHING, LIQUOR, PHARMACY, GYM
from tenants.utils import require_business


def _get_vertical_dashboard_url(vertical: str) -> str:
    """Get the dashboard URL for a given vertical."""
    try:
        if vertical == CLOTHING:
            return reverse("verticals:clothing_dashboard")
        elif vertical == LIQUOR:
            return reverse("verticals:liquor_dashboard")
        elif vertical == PHARMACY:
            return reverse("verticals:pharmacy_dashboard")
        elif vertical == GYM:
            return reverse("verticals:gym_dashboard")
        elif vertical == PHONES:
            # Use phones vertical dashboard instead of generic inventory dashboard
            return reverse("inventory_verticals:phones_dashboard")
        else:
            # Default fallback
            return reverse("inventory:inventory_dashboard")
    except NoReverseMatch:
        return reverse("inventory:inventory_dashboard")


def _get_vertical_scan_url(vertical: str) -> str:
    """Get the scan-in URL for a given vertical."""
    try:
        if vertical == CLOTHING:
            return reverse("inventory:scan_in")  # Clothing uses default scan-in
        elif vertical == LIQUOR:
            return reverse("liquor:inventory_dashboard")  # Liquor Hub
        elif vertical == PHARMACY:
            return reverse("inventory:scan_in")  # Pharmacy uses default
        elif vertical == GYM:
            return reverse("inventory:scan_in")  # Gym uses default
        elif vertical == PHONES:
            return reverse("inventory:scan_in")
        else:
            return reverse("inventory:scan_in")
    except NoReverseMatch:
        return reverse("inventory:scan_in")


def _get_vertical_sell_url(vertical: str) -> str:
    """Get the sell URL for a given vertical."""
    try:
        if vertical == CLOTHING:
            return reverse("verticals:clothing_sell")
        elif vertical == LIQUOR:
            return reverse("liquor:sell")
        elif vertical == PHARMACY:
            return reverse("inventory:scan_sold")  # Pharmacy uses default for now
        elif vertical == GYM:
            return reverse("inventory:scan_sold")  # Gym uses default for now
        elif vertical == PHONES:
            return reverse("inventory:phone_sale_wizard")
        else:
            return reverse("inventory:phone_sale_wizard")
    except NoReverseMatch:
        return reverse("inventory:phone_sale_wizard")


def _get_vertical_stock_url(vertical: str) -> str:
    """Get the stock list URL for a given vertical."""
    try:
        if vertical == CLOTHING:
            return reverse("inventory:stock_list")
        elif vertical == LIQUOR:
            return reverse("liquor:stock_overview")
        elif vertical == PHARMACY:
            return reverse("inventory:stock_list")  # Pharmacy uses default
        elif vertical == GYM:
            return reverse("inventory:stock_list")  # Gym uses default
        elif vertical == PHONES:
            return reverse("inventory:stock_list")
        else:
            return reverse("inventory:stock_list")
    except NoReverseMatch:
        return reverse("inventory:stock_list")


def _get_vertical_wallet_url(vertical: str) -> str:
    """Get the wallet URL (same for all verticals)."""
    try:
        return reverse("wallet:agent_wallet")
    except NoReverseMatch:
        return "/wallet/"


def _get_vertical_sim_url(vertical: str) -> str:
    """Get the simulator URL for a given vertical."""
    try:
        # All verticals use the business simulator which is vertical-aware
        return reverse("simulator:business_home")
    except NoReverseMatch:
        return "/simulator/business/"


@login_required
@require_business
def app_home(request: HttpRequest) -> HttpResponse:
    """Business-aware home router."""
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected")
        return redirect("dashboard:home")
    
    vertical = business_vertical(request)
    url = _get_vertical_dashboard_url(vertical)
    return redirect(url)


@login_required
@require_business
def app_scan(request: HttpRequest) -> HttpResponse:
    """Business-aware scan router."""
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected")
        return redirect("dashboard:home")
    
    vertical = business_vertical(request)
    url = _get_vertical_scan_url(vertical)
    return redirect(url)


@login_required
@require_business
def app_sell(request: HttpRequest) -> HttpResponse:
    """Business-aware sell router."""
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected")
        return redirect("dashboard:home")
    
    vertical = business_vertical(request)
    url = _get_vertical_sell_url(vertical)
    return redirect(url)


@login_required
@require_business
def app_stock(request: HttpRequest) -> HttpResponse:
    """Business-aware stock router."""
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected")
        return redirect("dashboard:home")
    
    vertical = business_vertical(request)
    url = _get_vertical_stock_url(vertical)
    return redirect(url)


@login_required
@require_business
def app_wallet(request: HttpRequest) -> HttpResponse:
    """Business-aware wallet router."""
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected")
        return redirect("dashboard:home")
    
    url = _get_vertical_wallet_url("")  # Wallet is same for all
    return redirect(url)


@login_required
@require_business
def app_sim(request: HttpRequest) -> HttpResponse:
    """Business-aware simulator router."""
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected")
        return redirect("dashboard:home")
    
    url = _get_vertical_sim_url("")  # Simulator is business-aware internally
    return redirect(url)


@login_required
@require_business
def app_analytics(request: HttpRequest) -> HttpResponse:
    """Business-aware analytics router."""
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected")
        return redirect("dashboard:home")
    
    try:
        from inventory.views_analytics import analytics_dashboard
        return analytics_dashboard(request)
    except ImportError:
        # Analytics not implemented yet, redirect to dashboard
        vertical = business_vertical(request)
        url = _get_vertical_dashboard_url(vertical)
        messages.info(request, "Analytics page coming soon")
        return redirect(url)

