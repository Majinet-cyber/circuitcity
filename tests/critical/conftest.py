# tests/critical/conftest.py
"""
Critical test fixtures and helpers.

These fixtures provide a standardized, deterministic way to create test data
for all verticals. Designed for bank-grade reliability testing.

SSOT: All vertical definitions come from inventory.business_kinds.BusinessKind
"""
from __future__ import annotations

import pytest
from decimal import Decimal
from uuid import uuid4
from typing import TYPE_CHECKING, Optional, Dict, Any, Tuple

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.utils import timezone
from django.utils.text import slugify

if TYPE_CHECKING:
    from tenants.models import Business, Membership
    from inventory.models import Location

User = get_user_model()


# =============================================================================
# SINGLE SOURCE OF TRUTH: Vertical Definitions
# =============================================================================
# All verticals from BusinessKind enum with their endpoint mappings

# Full list of all verticals (from BusinessKind)
ALL_VERTICALS = [
    "phones",
    "liquor",
    "grocery",
    "pharmacy",
    "clothing",
    "gym",
    "hardware",
    "cement",
    "farm",
    "welding",
]

# Core verticals tested in critical suite
# All verticals including farm/welding are now included - migrations exist and work correctly.
VERTICALS = [
    "phones",
    "liquor",
    "grocery",
    "pharmacy",
    "clothing",
    "gym",
    "hardware",
    "cement",
    "farm",
    "welding",
]

# Verticals with domain-specific models (for documentation only - all work in tests)
DOMAIN_SPECIFIC_VERTICALS = ["farm", "welding"]

# Endpoint map: vertical -> (dashboard_url_name, stock_add_url_name, sell_url_name)
# Use None if vertical doesn't support that operation (e.g., gym has no stock_add)
VERTICAL_ENDPOINTS = {
    "phones": {
        "dashboard": "inventory_verticals:phones_dashboard",
        "dashboard_path": "/inventory/verticals/phones/dashboard/",
        "stock_add": "inventory:scan_in",
        "stock_add_path": "/inventory/scan-in/",
        "sell": "inventory:phone_sale_wizard",
        "sell_path": "/inventory/phone-sale-wizard/",
        "stock_method": "imei_serial",
    },
    "liquor": {
        "dashboard": "verticals:liquor_dashboard",
        "dashboard_path": "/verticals/liquor/dashboard/",
        "stock_add": "liquor:scan_in",
        "stock_add_path": "/liquor/scan-in/",
        "sell": "liquor:sell",
        "sell_path": "/liquor/sell/",
        "stock_method": "barcode",
    },
    "grocery": {
        "dashboard": "groceries:dashboard",
        "dashboard_path": "/groceries/dashboard/",
        "stock_add": "groceries:stock_in",
        "stock_add_path": "/groceries/stock-in/",
        "sell": "groceries:sell",
        "sell_path": "/groceries/sell/",
        "stock_method": "barcode",
    },
    "pharmacy": {
        "dashboard": "verticals:pharmacy_hub",
        "dashboard_path": "/verticals/pharmacy/hub/",
        "stock_add": "pharmacy:stock_in",
        "stock_add_path": "/pharmacy/stock-in/",
        "sell": "pharmacy:sell",
        "sell_path": "/pharmacy/sell/",
        "stock_method": "barcode",
    },
    "clothing": {
        "dashboard": "verticals:clothing_dashboard",
        "dashboard_path": "/verticals/clothing/dashboard/",
        "stock_add": "inventory:clothing_wizard",
        "stock_add_path": "/inventory/wizard/clothing/",
        "sell": "verticals:clothing_sell",
        "sell_path": "/verticals/clothing/sell/",
        "stock_method": "no_barcode",  # Clothing uses size/color variants
    },
    "gym": {
        "dashboard": "verticals:gym_dashboard",
        "dashboard_path": "/verticals/gym/dashboard/",
        "stock_add": None,  # Gym is membership-based, no stock
        "stock_add_path": None,
        "sell": None,  # Gym uses membership payments, not sales
        "sell_path": None,
        "stock_method": None,
    },
    "hardware": {
        "dashboard": "inventory:generic_dashboard",
        "dashboard_path": "/inventory/generic-dashboard/",
        "stock_add": "inventory:scan_in",
        "stock_add_path": "/inventory/scan-in/",
        "sell": "inventory:scan_sold",
        "sell_path": "/inventory/scan-sold/",
        "stock_method": "barcode",
    },
    "cement": {
        "dashboard": "verticals:cement_dashboard",
        "dashboard_path": "/verticals/cement/dashboard/",
        "stock_add": "cement:stock_in",
        "stock_add_path": "/cement/stock-in/",
        "sell": "cement:sell",
        "sell_path": "/cement/sell/",
        "stock_method": "generic_sku",
    },
    "farm": {
        "dashboard": "verticals:farm_dashboard",
        "dashboard_path": "/verticals/farm/dashboard/",
        "stock_add": "verticals:farm_add_expense",  # Farm uses ledger, not stock
        "stock_add_path": "/verticals/farm/ledger/add-expense/",
        "sell": "verticals:farm_add_sale",  # Farm uses ledger sales
        "sell_path": "/verticals/farm/ledger/add-sale/",
        "stock_method": "ledger",
    },
    "welding": {
        "dashboard": "verticals:welding_dashboard",
        "dashboard_path": "/verticals/welding/dashboard/",
        "stock_add": "verticals:welding_stock_in",
        "stock_add_path": "/verticals/welding/stock-in/",
        "sell": "verticals:welding_invoices_list",  # Welding uses job invoicing
        "sell_path": "/verticals/welding/invoices/",
        "stock_method": "generic_sku",
    },
}


def _unique_suffix() -> str:
    """Generate unique suffix for test data to prevent collisions."""
    return uuid4().hex[:8]


# =============================================================================
# URL Resolution Helpers
# =============================================================================

def get_url(vertical: str, endpoint_type: str) -> Optional[str]:
    """
    Get URL for a vertical endpoint using reverse() with fallback to path.
    
    Args:
        vertical: Vertical key (e.g., "phones", "farm")
        endpoint_type: One of "dashboard", "stock_add", "sell"
    
    Returns:
        Resolved URL or None if endpoint doesn't exist for this vertical
    """
    from django.urls import reverse, NoReverseMatch
    
    endpoints = VERTICAL_ENDPOINTS.get(vertical, {})
    url_name = endpoints.get(endpoint_type)
    fallback_path = endpoints.get(f"{endpoint_type}_path")
    
    if url_name is None:
        return None
    
    try:
        return reverse(url_name)
    except NoReverseMatch:
        # URL name doesn't exist - use fallback path
        return fallback_path


def get_dashboard_url(vertical: str) -> Optional[str]:
    """Get dashboard URL for a vertical using reverse()."""
    return get_url(vertical, "dashboard")


def get_stock_add_url(vertical: str) -> Optional[str]:
    """Get stock add URL for a vertical using reverse()."""
    return get_url(vertical, "stock_add")


def get_sell_url(vertical: str) -> Optional[str]:
    """Get sell URL for a vertical using reverse()."""
    return get_url(vertical, "sell")


# =============================================================================
# Helper Functions (Importable)
# =============================================================================

def create_user(
    email: str = None,
    password: str = "testpass123",
    username: str = None,
    is_staff: bool = False,
) -> User:
    """
    Create a test user with unique credentials.
    
    Args:
        email: User email (defaults to unique generated email)
        password: User password
        username: Username (defaults to email)
        is_staff: Whether user is staff
    
    Returns:
        User instance
    """
    suffix = _unique_suffix()
    email = email or f"user_{suffix}@test.com"
    username = username or email
    
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
    )
    if is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    return user


def create_business(
    name: str = None,
    kind: str = "phones",
    created_by: User = None,
    status: str = "ACTIVE",
) -> "Business":
    """
    Create a test business.
    
    Args:
        name: Business name (defaults to unique generated name)
        kind: Business vertical kind
        created_by: User who created the business
        status: Business status
    
    Returns:
        Business instance
    """
    from tenants.models import Business
    
    suffix = _unique_suffix()
    name = name or f"Test Business {suffix}"
    slug = slugify(name)
    
    return Business.objects.create(
        name=name,
        slug=slug,
        business_kind=kind,
        created_by=created_by,
        status=status,
        currency="MWK",
    )


def create_location(
    business: "Business",
    name: str = None,
    is_headquarters: bool = True,
) -> "Location":
    """
    Create a test location.
    
    Args:
        business: Business instance
        name: Location name (defaults to unique generated name)
        is_headquarters: Whether this is the HQ location
    
    Returns:
        Location instance
    """
    from inventory.models import Location
    
    suffix = _unique_suffix()
    name = name or f"Location {suffix}"
    
    return Location.objects.create(
        business=business,
        name=name,
        is_headquarters=is_headquarters,
        address="123 Test St",
        city="Test City",
    )


def create_membership(
    user: User,
    business: "Business",
    role: str = "MANAGER",
    location: "Location" = None,
    status: str = "ACTIVE",
) -> "Membership":
    """
    Create a membership and assign Django auth groups.
    
    Args:
        user: User instance
        business: Business instance
        role: Role string ("MANAGER" or "AGENT")
        location: Location instance (required for AGENT, optional for MANAGER)
        status: Membership status
    
    Returns:
        Membership instance
    """
    from tenants.models import Membership
    
    membership, created = Membership.objects.get_or_create(
        user=user,
        business=business,
        defaults={
            "role": role,
            "status": status,
            "location": location,
        }
    )
    
    if not created:
        membership.role = role
        membership.status = status
        membership.location = location
        membership.save()
    
    # Add to Django auth groups (required by require_role decorator)
    group_name = f"biz:{business.pk}:{role}"
    group, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(group)
    
    return membership


def login_client(
    client: Client,
    user: User,
    password: str = "testpass123",
) -> bool:
    """
    Login user with Django test client.
    
    Args:
        client: Django test client
        user: User to login
        password: User password
    
    Returns:
        True if login successful
    """
    return client.login(username=user.username, password=password)


def set_active_business(client: Client, business: "Business") -> None:
    """
    Set active business in client session.
    
    Args:
        client: Django test client
        business: Business to set as active
    """
    session = client.session
    session["active_business_id"] = business.id
    session["biz_id"] = business.id
    session["business_id"] = business.id
    session.save()


def set_active_location(client: Client, location: "Location") -> None:
    """
    Set active location in client session.
    
    Args:
        client: Django test client
        location: Location to set as active
    """
    session = client.session
    session["active_location_id"] = location.id
    session["location_id"] = location.id
    session.save()


def bootstrap_business_with_user(
    kind: str,
    role: str = "MANAGER",
) -> Tuple[User, "Business", "Location"]:
    """
    Create a complete business setup with user, business, location, and membership.
    
    This is the primary helper for setting up test fixtures.
    
    Args:
        kind: Business vertical kind
        role: Role to assign to user ("MANAGER" or "AGENT")
    
    Returns:
        Tuple of (user, business, location)
    """
    user = create_user()
    business = create_business(kind=kind, created_by=user)
    location = create_location(business)
    create_membership(user, business, role=role, location=location)
    
    return user, business, location


def setup_authenticated_client(
    user: User,
    business: "Business",
    location: "Location",
    password: str = "testpass123",
) -> Client:
    """
    Create and configure a Django test client with authentication and session.
    
    Args:
        user: User to authenticate
        business: Business to set as active
        location: Location to set as active
        password: User password
    
    Returns:
        Configured Django test client
    """
    client = Client()
    login_client(client, user, password)
    set_active_business(client, business)
    set_active_location(client, location)
    return client


# =============================================================================
# Pytest Fixtures
# =============================================================================

@pytest.fixture
def critical_user(db):
    """Create a test user for critical tests."""
    return create_user()


@pytest.fixture
def critical_business(db, critical_user):
    """Create a test business for critical tests."""
    return create_business(created_by=critical_user)


@pytest.fixture
def critical_location(db, critical_business):
    """Create a test location for critical tests."""
    return create_location(critical_business)


@pytest.fixture
def critical_setup(db):
    """
    Create a complete critical test setup.
    
    Returns:
        dict with keys: user, business, location, client, password
    """
    user, business, location = bootstrap_business_with_user("phones")
    password = "testpass123"
    client = setup_authenticated_client(user, business, location, password)
    
    return {
        "user": user,
        "business": business,
        "location": location,
        "client": client,
        "password": password,
    }


@pytest.fixture(params=VERTICALS)
def all_verticals(request, db):
    """
    Parametrized fixture that provides a setup for each vertical.
    
    Yields:
        dict with keys: vertical, user, business, location, client, endpoints
    """
    vertical = request.param
    user, business, location = bootstrap_business_with_user(vertical)
    client = setup_authenticated_client(user, business, location)
    
    return {
        "vertical": vertical,
        "user": user,
        "business": business,
        "location": location,
        "client": client,
        "endpoints": VERTICAL_ENDPOINTS.get(vertical, {}),
    }

