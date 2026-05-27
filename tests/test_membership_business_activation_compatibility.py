# tests/test_membership_business_activation_compatibility.py
"""
Unit tests for Membership/Business activation compatibility (SSOT + backwards compat).

EVIDENCE OF ORIGINAL FAILURES:
- TypeError: Membership() got unexpected keyword arguments: 'is_active'
- AttributeError: property 'is_active' of 'Business' object has no setter
- AttributeError: 'Business' object has no attribute 'members'
- AttributeError: property 'location' of 'InventoryItem' object has no setter

GOAL:
Restore backwards-compatible behavior safely:
- Membership must accept `is_active` in creation (default True).
- Business.is_active must be settable in tests without breaking prod logic.
- Business.members should exist (queryset-like accessor).
- InventoryItem.location must be settable if tests expect it.
"""

import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import Location, Product, InventoryItem

User = get_user_model()


class TestMembershipIsActiveField(TestCase):
    """Test Membership.is_active field works for backwards compatibility."""

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Test Location"
        )

    def test_membership_creation_with_is_active_true(self):
        """Test: Membership.objects.create(..., is_active=True) works."""
        # This was failing with: TypeError: Membership() got unexpected keyword arguments: 'is_active'
        membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
            is_active=True
        )
        
        self.assertIsNotNone(membership.pk)
        self.assertTrue(membership.is_active)
        self.assertEqual(membership.status, "ACTIVE")

    def test_membership_creation_with_is_active_false(self):
        """Test: Membership can be created with is_active=False."""
        membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="PENDING",
            is_active=False
        )
        
        self.assertIsNotNone(membership.pk)
        self.assertFalse(membership.is_active)

    def test_membership_creation_without_is_active(self):
        """Test: Membership creation without is_active (uses default)."""
        membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.assertIsNotNone(membership.pk)
        # Default should be True
        self.assertTrue(membership.is_active)

    def test_membership_is_active_persists(self):
        """Test: is_active value persists to database."""
        membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
            is_active=True
        )
        
        # Reload from DB
        reloaded = Membership.objects.get(pk=membership.pk)
        self.assertTrue(reloaded.is_active)


class TestBusinessIsActiveSetter(TestCase):
    """Test Business.is_active setter for backwards compatibility."""

    def test_business_is_active_setter_true(self):
        """Test: business.is_active = True sets status to ACTIVE."""
        # This was failing with: AttributeError: property 'is_active' of 'Business' object has no setter
        business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="PENDING"
        )
        
        # Set is_active to True
        business.is_active = True
        self.assertEqual(business.status, "ACTIVE")
        
        # Persist and verify
        business.save()
        reloaded = Business.objects.get(pk=business.pk)
        self.assertEqual(reloaded.status, "ACTIVE")
        self.assertTrue(reloaded.is_active)

    def test_business_is_active_setter_false(self):
        """Test: business.is_active = False sets status to SUSPENDED."""
        business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
        
        # Set is_active to False
        business.is_active = False
        self.assertEqual(business.status, "SUSPENDED")
        
        # Persist and verify
        business.save()
        reloaded = Business.objects.get(pk=business.pk)
        self.assertEqual(reloaded.status, "SUSPENDED")
        self.assertFalse(reloaded.is_active)

    def test_business_is_active_getter(self):
        """Test: business.is_active getter works correctly."""
        business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
        self.assertTrue(business.is_active)
        
        business.status = "SUSPENDED"
        self.assertFalse(business.is_active)
        
        business.status = "PENDING"
        self.assertFalse(business.is_active)


class TestBusinessMembersProperty(TestCase):
    """Test Business.members property for backwards compatibility."""

    def setUp(self):
        """Create test fixtures."""
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
        self.user1 = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            password="pass123"
        )
        self.user2 = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            password="pass123"
        )

    def test_business_members_property_exists(self):
        """Test: business.members property exists and returns queryset."""
        # This was failing with: AttributeError: 'Business' object has no attribute 'members'
        self.assertTrue(hasattr(self.business, "members"))
        members = self.business.members
        self.assertIsNotNone(members)

    def test_business_members_returns_memberships(self):
        """Test: business.members returns the memberships queryset."""
        # Create memberships
        Membership.objects.create(
            user=self.user1,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        Membership.objects.create(
            user=self.user2,
            business=self.business,
            role="MANAGER",
            status="PENDING"
        )
        
        # Access via members property
        members = self.business.members.all()
        self.assertEqual(members.count(), 2)

    def test_business_members_filter_works(self):
        """Test: business.members.filter() works correctly."""
        Membership.objects.create(
            user=self.user1,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        Membership.objects.create(
            user=self.user2,
            business=self.business,
            role="MANAGER",
            status="PENDING"
        )
        
        # Filter for ACTIVE only
        active_members = self.business.members.filter(status="ACTIVE")
        self.assertEqual(active_members.count(), 1)
        self.assertEqual(active_members.first().user, self.user1)


class TestInventoryItemLocationSetter(TestCase):
    """Test InventoryItem.location setter for backwards compatibility."""

    def setUp(self):
        """Create test fixtures."""
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
        self.location1 = Location.objects.create(
            business=self.business,
            name="Location 1"
        )
        self.location2 = Location.objects.create(
            business=self.business,
            name="Location 2"
        )
        self.product = Product.objects.create(
            code="TEST001",
            name="Test Product",
            brand="TestBrand",
            model="TestModel",
            variant="Standard"
        )

    def test_inventory_item_location_setter(self):
        """Test: item.location = loc sets underlying current_location FK."""
        # This was failing with: AttributeError: property 'location' of 'InventoryItem' object has no setter
        item = InventoryItem.all_objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location1,
            order_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            status="IN_STOCK"
        )
        
        # Set location via setter
        item.location = self.location2
        self.assertEqual(item.current_location, self.location2)
        
        # Persist and verify
        item.save()
        reloaded = InventoryItem.all_objects.get(pk=item.pk)
        self.assertEqual(reloaded.current_location, self.location2)

    def test_inventory_item_location_getter(self):
        """Test: item.location getter returns current_location."""
        item = InventoryItem.all_objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location1,
            order_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            status="IN_STOCK"
        )
        
        self.assertEqual(item.location, self.location1)
        self.assertEqual(item.location, item.current_location)

    def test_inventory_item_location_setter_on_creation(self):
        """Test: Can create item by setting location (not current_location)."""
        # Some legacy code might do this
        item = InventoryItem(
            business=self.business,
            product=self.product,
            order_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            status="IN_STOCK"
        )
        item.location = self.location1
        item.save()
        
        self.assertEqual(item.current_location, self.location1)
        reloaded = InventoryItem.all_objects.get(pk=item.pk)
        self.assertEqual(reloaded.current_location, self.location1)


@pytest.mark.django_db
class TestMembershipIsActiveIntegration:
    """Pytest-style tests for Membership is_active integration."""

    def test_membership_is_active_with_agent_role(self):
        """Test: Agent membership with is_active=True works."""
        user = User.objects.create_user(
            username="agent",
            email="agent@example.com",
            password="pass123"
        )
        business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
        location = Location.objects.create(
            business=business,
            name="Store 1"
        )
        
        # Create agent membership with is_active
        membership = Membership.objects.create(
            user=user,
            business=business,
            location=location,
            role="AGENT",
            status="ACTIVE",
            is_active=True
        )
        
        assert membership.pk is not None
        assert membership.is_active is True
        assert membership.status == "ACTIVE"

    def test_membership_filtering_by_is_active(self):
        """Test: Can filter memberships by is_active field."""
        user = User.objects.create_user(
            username="user",
            email="user@example.com",
            password="pass123"
        )
        business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
        
        # Create memberships with different is_active states
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            is_active=True
        )
        
        # Query by is_active
        active_memberships = Membership.objects.filter(is_active=True)
        assert active_memberships.count() >= 1


@pytest.mark.django_db
class TestBackwardsCompatibilityNoRegressions:
    """Test that changes don't break existing functionality."""

    def test_membership_creation_traditional_way_still_works(self):
        """Test: Creating membership without is_active still works."""
        user = User.objects.create_user(
            username="user",
            email="user@example.com",
            password="pass123"
        )
        business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
        
        # Traditional creation (no is_active param)
        membership = Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        assert membership.pk is not None
        assert membership.status == "ACTIVE"

    def test_business_status_field_unchanged(self):
        """Test: Business status field still works as before."""
        business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="PENDING"
        )
        
        assert business.status == "PENDING"
        assert business.is_active is False
        
        business.status = "ACTIVE"
        business.save()
        
        reloaded = Business.objects.get(pk=business.pk)
        assert reloaded.status == "ACTIVE"
        assert reloaded.is_active is True

    def test_inventory_item_current_location_unchanged(self):
        """Test: InventoryItem current_location field still works."""
        business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
        location = Location.objects.create(
            business=business,
            name="Store"
        )
        product = Product.objects.create(
            code="TEST001",
            name="Test Product",
            brand="Brand",
            model="Model",
            variant="Variant"
        )
        
        # Create using current_location (traditional way)
        item = InventoryItem.all_objects.create(
            business=business,
            product=product,
            current_location=location,
            order_price=Decimal("100.00"),
            status="IN_STOCK"
        )
        
        assert item.current_location == location
        assert item.location == location  # Getter should work too

