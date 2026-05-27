"""
Reusable test helpers for tenant setup (User, Business, Location, Membership, session).

This module provides canonical helpers to reduce duplication across tests.
When schema changes occur, update these helpers once instead of dozens of test files.
"""
from django.contrib.auth import get_user_model
from django.utils.text import slugify

from tenants.models import Business, Location, Membership

# Canonical import: MUST match what Business model uses
from tenants.constants import BusinessKind

User = get_user_model()


def make_user(email="manager@example.com", password="pass1234", is_staff=True, username=None):
    """
    Create a test user.
    
    Args:
        email: User email (default: "manager@example.com")
        password: User password (default: "pass1234")
        is_staff: Whether user is staff (default: True)
        username: Optional username (defaults to email if not provided)
    
    Returns:
        User instance
    """
    user = User.objects.create_user(
        email=email,
        password=password,
        username=username or email
    )
    if is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    return user


def make_business(
    *,
    created_by,
    kind=BusinessKind.PHARMACY,
    name="Test Business",
    slug=None,
    status="ACTIVE",
):
    """
    Create a test business.
    
    Args:
        created_by: User who created the business (required)
        kind: BusinessKind enum value (default: BusinessKind.PHARMACY)
        name: Business name (default: "Test Business")
        slug: Business slug (defaults to slugified name if not provided)
        status: Business status (default: "ACTIVE")
    
    Returns:
        Business instance
    """
    return Business.objects.create(
        name=name,
        slug=slug or slugify(name),
        business_kind=kind,
        created_by=created_by,
        status=status,
    )


def make_location(*, business, name="Main"):
    """
    Create a test location.
    
    Args:
        business: Business instance (required)
        name: Location name (default: "Main")
    
    Returns:
        Location instance
    """
    return Location.objects.create(business=business, name=name)


def make_membership(*, business, user, role="MANAGER", location=None, status="ACTIVE"):
    """
    Create a test membership.
    
    Important: Managers should have location=None. Agents should have location set.
    
    Args:
        business: Business instance (required)
        user: User instance (required)
        role: Role string - "MANAGER" or "AGENT" (default: "MANAGER")
        location: Location instance or None (default: None)
            - For MANAGER: should be None
            - For AGENT: should be set
        status: Status string - "PENDING", "ACTIVE", or "REJECTED" (default: "ACTIVE")
    
    Returns:
        Membership instance
    """
    return Membership.objects.create(
        business=business,
        user=user,
        role=role,
        status=status,
        location=location,
    )


def login_with_active_scope(client, user, business, location=None):
    """
    Login user and set active business/location in session.
    
    Args:
        client: Django test client
        user: User instance to login
        business: Business instance to set as active
        location: Optional Location instance to set as active
    
    Returns:
        Session object
    """
    client.force_login(user)
    session = client.session
    session["active_business_id"] = business.id
    if location:
        session["active_location_id"] = location.id
    session.save()
    return session

