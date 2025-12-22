# tests/smoke/fixtures.py
"""
Shared test fixtures for smoke tests.
Creates deterministic test data for all verticals.
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import Location, MerchProduct
from inventory.business_kinds import BusinessKind
from conftest import unique_slug

User = get_user_model()


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
    def create_admin_user(username="admin_user", email="admin@test.com", password="testpass123"):
        """Create admin/manager user."""
        user = User.objects.create_user(
            username=username,
            email=email,
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
    def create_agent_user(username="agent_user", email="agent@test.com", password="testpass123"):
        """Create agent user."""
        return User.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_staff=False,
            is_superuser=False,
        )
    
    @staticmethod
    def create_superuser(username="superuser", email="super@test.com", password="testpass123"):
        """Create platform superuser."""
        return User.objects.create_superuser(
            username=username,
            email=email,
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
        
        # Create users
        admin_username = f"admin_{business_kind}"
        agent_username = f"agent_{business_kind}"
        password = "testpass123"
        
        admin_user = SmokeTestFixtures.create_admin_user(
            username=admin_username,
            email=f"{admin_username}@test.com",
            password=password
        )
        agent_user = SmokeTestFixtures.create_agent_user(
            username=agent_username,
            email=f"{agent_username}@test.com",
            password=password
        )
        
        # Assign roles
        SmokeTestFixtures.assign_manager_role(admin_user, business, location)
        SmokeTestFixtures.assign_agent_role(agent_user, business, location)
        
        # Create product (if applicable)
        product = None
        if business_kind == BusinessKind.PHONES:
            product = SmokeTestFixtures.create_phone_product(business, location)
        elif business_kind == BusinessKind.PHARMACY:
            product = SmokeTestFixtures.create_pharmacy_product(business, location)
        elif business_kind == BusinessKind.CLOTHING:
            product = SmokeTestFixtures.create_clothing_product(business, location)
        elif business_kind == BusinessKind.LIQUOR:
            product = SmokeTestFixtures.create_liquor_product(business, location)
        # Gym has no products (membership-based)
        
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

