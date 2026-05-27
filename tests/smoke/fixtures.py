# tests/smoke/fixtures.py
"""
Shared test fixtures for smoke tests.
Creates deterministic test data for all verticals.

CRITICAL: All fixtures use unique usernames to prevent IntegrityError collisions
when tests run in parallel or with shared state.
"""
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from django.utils.crypto import get_random_string

from tenants.models import Business, Membership
from inventory.models import Location, MerchProduct
from inventory.business_kinds import BusinessKind
from conftest import unique_slug

User = get_user_model()


def _unique_username(base: str = "user") -> str:
    """
    Generate a unique username to prevent IntegrityError collisions.
    Uses random suffix to ensure uniqueness across test runs.
    """
    return f"{base}_{get_random_string(8).lower()}"


class SmokeTestFixtures:
    """Factory for creating test data for smoke tests."""
    
    @staticmethod
    def create_business(name="Test Business", business_kind=BusinessKind.PHONES):
        """Create a test business."""
        return Business.objects.create(
            name=name,
            slug=unique_slug(name),
            status="ACTIVE",
            business_kind=business_kind,
            currency="MWK",
        )
    
    @staticmethod
    def create_hq_location(business, name="HQ Location"):
        """Create headquarters location."""
        return Location.objects.create(
            business=business,
            name=name,
            is_headquarters=True,
            address="123 Test St",
            city="Test City",
        )
    
    @staticmethod
    def create_branch_location(business, name="Branch Location"):
        """Create branch location."""
        return Location.objects.create(
            business=business,
            name=name,
            is_headquarters=False,
            address="456 Branch Ave",
            city="Test City",
        )
    
    @staticmethod
    def create_admin_user(username=None, email=None, password="testpass123"):
        """
        Create admin/manager user with unique username.
        
        CRITICAL: Always generates unique username to prevent IntegrityError.
        If username is provided, a random suffix is still appended for safety.
        """
        unique_name = _unique_username(username or "admin")
        unique_email = email or f"{unique_name}@test.com"
        
        user = User.objects.create_user(
            username=unique_name,
            email=unique_email,
            password=password,
            is_staff=False,
            is_superuser=False,
        )
        # Set profile flag if exists
        if hasattr(user, 'profile'):
            user.profile.is_manager = True
            user.profile.save()
        return user
    
    @staticmethod
    def create_agent_user(username=None, email=None, password="testpass123"):
        """
        Create agent user with unique username.
        
        CRITICAL: Always generates unique username to prevent IntegrityError.
        """
        unique_name = _unique_username(username or "agent")
        unique_email = email or f"{unique_name}@test.com"
        
        return User.objects.create_user(
            username=unique_name,
            email=unique_email,
            password=password,
            is_staff=False,
            is_superuser=False,
        )
    
    @staticmethod
    def create_superuser(username=None, email=None, password="testpass123"):
        """
        Create platform superuser with unique username.
        
        CRITICAL: Always generates unique username to prevent IntegrityError.
        """
        unique_name = _unique_username(username or "superuser")
        unique_email = email or f"{unique_name}@test.com"
        
        return User.objects.create_superuser(
            username=unique_name,
            email=unique_email,
            password=password,
        )
    
    @staticmethod
    def assign_manager_role(user, business, location=None):
        """Assign MANAGER role to user for business."""
        # Create Django group for business-scoped manager role
        group_name = f"biz:{business.pk}:MANAGER"
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)
        
        # Create Membership
        membership, _ = Membership.objects.get_or_create(
            user=user,
            business=business,
            defaults={
                'role': 'MANAGER',
                'status': 'ACTIVE',
                'location': location,
            }
        )
        return membership
    
    @staticmethod
    def assign_agent_role(user, business, location):
        """Assign AGENT role to user for business (requires location)."""
        # Create Django group for business-scoped agent role
        group_name = f"biz:{business.pk}:AGENT"
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)
        
        # Create Membership (agents MUST have location)
        membership, _ = Membership.objects.get_or_create(
            user=user,
            business=business,
            location=location,
            defaults={
                'role': 'AGENT',
                'status': 'ACTIVE',
            }
        )
        return membership
    
    @staticmethod
    def create_phone_product(business, location, name="iPhone 12", cost=50000, price=60000):
        """Create a phone product."""
        return MerchProduct.objects.create(
            business=business,
            location=location,
            name=name,
            cost_price=Decimal(str(cost)),
            selling_price=Decimal(str(price)),
            quantity=10,
            category="phones",
            vertical_type="phones",
            status="ACTIVE",
        )
    
    @staticmethod
    def create_pharmacy_product(business, location, name="Paracetamol 500mg", cost=100, price=150):
        """Create a pharmacy product with batch tracking."""
        return MerchProduct.objects.create(
            business=business,
            location=location,
            name=name,
            cost_price=Decimal(str(cost)),
            selling_price=Decimal(str(price)),
            quantity=100,
            category="medicine",
            vertical_type="pharmacy",
            status="ACTIVE",
            # Batch fields (if exist)
            batch_number="BATCH001",
            expiry_date=timezone.now().date() + timezone.timedelta(days=365),
        )
    
    @staticmethod
    def create_clothing_product(business, location, name="T-Shirt", size="M", color="Blue", cost=500, price=800):
        """Create a clothing product."""
        return MerchProduct.objects.create(
            business=business,
            location=location,
            name=name,
            cost_price=Decimal(str(cost)),
            selling_price=Decimal(str(price)),
            quantity=20,
            category="clothing",
            vertical_type="clothing",
            status="ACTIVE",
            # Clothing-specific fields (if exist)
            size=size,
            color=color,
        )
    
    @staticmethod
    def create_liquor_product(business, location, name="Whiskey", cost=5000, price=7000):
        """Create a liquor product."""
        return MerchProduct.objects.create(
            business=business,
            location=location,
            name=name,
            cost_price=Decimal(str(cost)),
            selling_price=Decimal(str(price)),
            quantity=50,
            category="spirits",
            vertical_type="liquor",
            status="ACTIVE",
            # Liquor-specific fields (if exist)
            has_shots=True,
            shots_per_bottle=20,
            barman_shots_reserved=2,
            price_per_bottle=Decimal(str(price)),
            price_per_shot=Decimal("500"),
        )
    
    @staticmethod
    def create_complete_vertical_setup(business_kind, business_name=None):
        """
        Create a complete setup for a vertical: business, location, admin, agent, product.
        
        CRITICAL: Uses unique usernames to prevent IntegrityError collisions.
        
        Returns:
            dict: {
                'business': Business,
                'location': Location,
                'admin_user': User,
                'admin_password': str,
                'agent_user': User,
                'agent_password': str,
                'product': MerchProduct (if applicable),
            }
        """
        if not business_name:
            business_name = f"Test {business_kind.title()} Business"
        
        # Create business and location
        business = SmokeTestFixtures.create_business(business_name, business_kind)
        location = SmokeTestFixtures.create_hq_location(business, f"{business_name} HQ")
        
        # Create users (with unique usernames - suffix appended automatically)
        password = "testpass123"
        
        admin_user = SmokeTestFixtures.create_admin_user(
            username=f"admin_{business_kind}",
            password=password
        )
        agent_user = SmokeTestFixtures.create_agent_user(
            username=f"agent_{business_kind}",
            password=password
        )
        
        # Assign roles
        SmokeTestFixtures.assign_manager_role(admin_user, business, location)
        SmokeTestFixtures.assign_agent_role(agent_user, business, location)
        
        # Create product using safe_create helper (if applicable)
        product = None
        try:
            from inventory.compat_create import safe_create
            
            if business_kind == BusinessKind.PHONES:
                product = safe_create(
                    MerchProduct,
                    business=business,
                    location=location,
                    name="iPhone 12",
                    cost_price=Decimal("50000"),
                    selling_price=Decimal("60000"),
                    quantity=10,
                    category="phones",
                    vertical_type="phones",
                    status="ACTIVE",
                )
            elif business_kind == BusinessKind.PHARMACY:
                product = safe_create(
                    MerchProduct,
                    business=business,
                    location=location,
                    name="Paracetamol 500mg",
                    cost_price=Decimal("100"),
                    selling_price=Decimal("150"),
                    quantity=100,
                    category="medicine",
                    vertical_type="pharmacy",
                    status="ACTIVE",
                    batch_number="BATCH001",
                    expiry_date=timezone.now().date() + timezone.timedelta(days=365),
                )
            elif business_kind == BusinessKind.CLOTHING:
                product = safe_create(
                    MerchProduct,
                    business=business,
                    location=location,
                    name="T-Shirt",
                    cost_price=Decimal("500"),
                    selling_price=Decimal("800"),
                    quantity=20,
                    category="clothing",
                    vertical_type="clothing",
                    status="ACTIVE",
                    size="M",
                    color="Blue",
                )
            elif business_kind == BusinessKind.LIQUOR:
                product = safe_create(
                    MerchProduct,
                    business=business,
                    location=location,
                    name="Whiskey",
                    cost_price=Decimal("5000"),
                    selling_price=Decimal("7000"),
                    quantity=50,
                    category="spirits",
                    vertical_type="liquor",
                    status="ACTIVE",
                    has_shots=True,
                    shots_per_bottle=20,
                    barman_shots_reserved=2,
                    price_per_bottle=Decimal("7000"),
                    price_per_shot=Decimal("500"),
                )
            # Gym has no products (membership-based)
        except ImportError:
            # Fallback if safe_create not available yet - use old methods
            if business_kind == BusinessKind.PHONES:
                product = SmokeTestFixtures.create_phone_product(business, location)
            elif business_kind == BusinessKind.PHARMACY:
                product = SmokeTestFixtures.create_pharmacy_product(business, location)
            elif business_kind == BusinessKind.CLOTHING:
                product = SmokeTestFixtures.create_clothing_product(business, location)
            elif business_kind == BusinessKind.LIQUOR:
                product = SmokeTestFixtures.create_liquor_product(business, location)
        
        return {
            'business': business,
            'location': location,
            'admin_user': admin_user,
            'admin_password': password,
            'agent_user': agent_user,
            'agent_password': password,
            'product': product,
        }


__all__ = ['SmokeTestFixtures']

