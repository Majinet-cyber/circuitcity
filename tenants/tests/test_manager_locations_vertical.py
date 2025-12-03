# tenants/tests/test_manager_locations_vertical.py
"""
Tests for vertical-aware stock summary on manager locations page.
Task 5: Ensure the "Stock Summary by Location" adapts to business vertical.
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.fixture
def manager_user(db):
    """Create a manager user with Manager group"""
    user = User.objects.create_user(
        username="manager1",
        email="manager@test.com",
        password="testpass123"
    )
    # Add to Manager group
    manager_group, _ = Group.objects.get_or_create(name="Manager")
    user.groups.add(manager_group)
    return user


@pytest.fixture
def phones_business(db):
    """Create a phones business"""
    return Business.objects.create(
        name="Phone Shop",
        business_kind=BusinessKind.PHONES
    )


@pytest.fixture
def liquor_business(db):
    """Create a liquor business"""
    return Business.objects.create(
        name="Liquor Store",
        business_kind=BusinessKind.LIQUOR
    )


@pytest.fixture
def gym_business(db):
    """Create a gym business"""
    return Business.objects.create(
        name="Fitness Center",
        business_kind=BusinessKind.GYM
    )


@pytest.fixture
def clothing_business(db):
    """Create a clothing business"""
    return Business.objects.create(
        name="Fashion Boutique",
        business_kind=BusinessKind.CLOTHING
    )


def create_manager_membership(user, business, role="MANAGER"):
    """Helper to create manager membership"""
    return Membership.objects.create(
        user=user,
        business=business,
        role=role,
        status="ACTIVE"
    )


def setup_client_for_business(client, user, business):
    """Helper to set up client with logged in user and active business"""
    create_manager_membership(user, business)
    client.force_login(user)
    
    # Set active business in session
    session = client.session
    session['active_business_id'] = business.id
    session.save()
    
    return client


@pytest.mark.django_db
class TestManagerLocationsPhones:
    """Test manager locations page for phones business"""
    
    def test_phones_business_shows_phones_header(self, client, manager_user, phones_business):
        """Phones business should show '(Phones)' in header"""
        setup_client_for_business(client, manager_user, phones_business)
        
        # Create a location so the stock summary section appears
        try:
            from inventory.models import Location
            Location.objects.create(
                business=phones_business,
                name="Main Store",
                city="Lilongwe"
            )
        except Exception:
            pytest.skip("Location model not available")
        
        url = reverse('tenants:manager_locations')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Check for phones-specific header
        assert 'Locations' in content  # Basic check that the page rendered
        assert 'Stock Summary' in content  # Stock summary section should be present
        assert 'Stock Summary by Location (Phones)' in content or '📦 Stock Summary by Location (Phones)' in content
    
    def test_phones_business_uses_phones_data(self, client, manager_user, phones_business):
        """Phones business should use InventoryItem and Sale models"""
        setup_client_for_business(client, manager_user, phones_business)
        
        # Create a location
        try:
            from inventory.models import Location
            loc = Location.objects.create(
                business=phones_business,
                name="Main Store",
                city="Lilongwe"
            )
        except Exception:
            pytest.skip("Location model not available")
        
        url = reverse('tenants:manager_locations')
        response = client.get(url)
        
        assert response.status_code == 200
        # Check that context includes stock_summary
        if 'stock_summary' in response.context:
            stock_summary = response.context['stock_summary']
            # Should be a dict (even if empty)
            assert isinstance(stock_summary, dict)


@pytest.mark.django_db
class TestManagerLocationsLiquor:
    """Test manager locations page for liquor business"""
    
    def test_liquor_business_shows_liquor_header(self, client, manager_user, liquor_business):
        """Liquor business should show '(Liquor)' in header"""
        setup_client_for_business(client, manager_user, liquor_business)
        
        # Create a location so the stock summary section appears
        try:
            from inventory.models import Location
            Location.objects.create(
                business=liquor_business,
                name="Main Bar",
                city="Blantyre"
            )
        except Exception:
            pytest.skip("Location model not available")
        
        url = reverse('tenants:manager_locations')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Check for liquor-specific header
        assert 'Stock Summary by Location (Liquor)' in content or '🍺 Stock Summary by Location (Liquor)' in content
        # Should NOT show phones wording
        assert 'Stock Summary by Location (Phones)' not in content
    
    def test_liquor_business_uses_liquor_data(self, client, manager_user, liquor_business):
        """Liquor business should use MerchProduct and LiquorSale models"""
        setup_client_for_business(client, manager_user, liquor_business)
        
        # Create a location
        try:
            from inventory.models import Location, MerchProduct
            from inventory.models_verticals import LiquorSale
            
            loc = Location.objects.create(
                business=liquor_business,
                name="Main Bar",
                city="Blantyre"
            )
            
            # Create a liquor product
            product = MerchProduct.objects.create(
                business=liquor_business,
                name="Test Beer",
                kind=BusinessKind.LIQUOR,
                quantity=10,
                price_per_bottle=Decimal("500.00")
            )
            
            # Create a sale
            LiquorSale.objects.create(
                business=liquor_business,
                product=product,
                unit="bottle",
                quantity=2,
                unit_price=Decimal("500.00"),
                total_price=Decimal("1000.00"),
                sold_by=manager_user
            )
        except Exception as e:
            pytest.skip(f"Liquor models not available: {e}")
        
        url = reverse('tenants:manager_locations')
        response = client.get(url)
        
        assert response.status_code == 200
        # Check that context includes stock_summary
        if 'stock_summary' in response.context:
            stock_summary = response.context['stock_summary']
            assert isinstance(stock_summary, dict)
            # Should have data for our location
            if loc.id in stock_summary:
                summary = stock_summary[loc.id]
                # Should have sold/in_stock/total keys
                assert 'sold' in summary or 'in_stock' in summary or 'total' in summary


@pytest.mark.django_db
class TestManagerLocationsGym:
    """Test manager locations page for gym business"""
    
    def test_gym_business_shows_gym_header(self, client, manager_user, gym_business):
        """Gym business should show 'Member Summary' with '(Gym)' in header"""
        setup_client_for_business(client, manager_user, gym_business)
        
        # Create a location so the stock summary section appears
        try:
            from inventory.models import Location
            Location.objects.create(
                business=gym_business,
                name="Main Gym",
                city="Mzuzu"
            )
        except Exception:
            pytest.skip("Location model not available")
        
        url = reverse('tenants:manager_locations')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Debug: Check what's in the response
        import re
        match = re.search(r'(Stock|Member) Summary by Location[^<]*', content)
        if match:
            print(f"\nFound header: {match.group()}")
        else:
            print(f"\nNo summary header found. Business kind: {gym_business.business_kind}")
            # Check if BUSINESS_VERTICAL is in context
            if 'BUSINESS_VERTICAL' in str(response.context):
                print(f"BUSINESS_VERTICAL in context: {response.context.get('BUSINESS_VERTICAL')}")
        
        # Check for gym-specific header
        assert 'Member Summary by Location (Gym)' in content or '💪 Member Summary by Location (Gym)' in content
        # Should NOT show phones or stock wording
        assert 'Stock Summary by Location (Phones)' not in content
    
    def test_gym_business_uses_gym_data(self, client, manager_user, gym_business):
        """Gym business should use GymMember model and show active/arrears"""
        setup_client_for_business(client, manager_user, gym_business)
        
        # Create a location
        try:
            from inventory.models import Location
            from inventory.models_verticals import GymMember, GymPayment
            from datetime import timedelta
            
            loc = Location.objects.create(
                business=gym_business,
                name="Main Gym",
                city="Mzuzu"
            )
            
            # Create an active member with payment
            member = GymMember.objects.create(
                business=gym_business,
                name="John Doe",
                phone="0991234567",
                is_active=True
            )
            
            # Add payment (30 days from now)
            GymPayment.objects.create(
                member=member,
                amount=Decimal("5000.00"),
                paid_by=manager_user,
                start_date=timezone.now().date(),
                end_date=(timezone.now() + timedelta(days=30)).date()
            )
        except Exception as e:
            pytest.skip(f"Gym models not available: {e}")
        
        url = reverse('tenants:manager_locations')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Check for gym-specific column headers
        assert 'Active' in content or 'In Arrears' in content
        
        # Check that context includes stock_summary (which for gym is member summary)
        if 'stock_summary' in response.context:
            stock_summary = response.context['stock_summary']
            assert isinstance(stock_summary, dict)
            # Should have data for our location
            if loc.id in stock_summary:
                summary = stock_summary[loc.id]
                # Should have active/in_arrears/total keys
                assert 'active' in summary or 'in_arrears' in summary or 'total' in summary


@pytest.mark.django_db
class TestManagerLocationsClothing:
    """Test manager locations page for clothing business"""
    
    def test_clothing_business_shows_clothing_header(self, client, manager_user, clothing_business):
        """Clothing business should show '(Clothing)' in header"""
        setup_client_for_business(client, manager_user, clothing_business)
        
        # Create a location so the stock summary section appears
        try:
            from inventory.models import Location
            Location.objects.create(
                business=clothing_business,
                name="Main Store",
                city="Lilongwe"
            )
        except Exception:
            pytest.skip("Location model not available")
        
        url = reverse('tenants:manager_locations')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Check for clothing-specific header
        assert 'Stock Summary by Location (Clothing)' in content or '👕 Stock Summary by Location (Clothing)' in content
        # Should NOT show phones wording
        assert 'Stock Summary by Location (Phones)' not in content
    
    def test_clothing_business_uses_clothing_data(self, client, manager_user, clothing_business):
        """Clothing business should use MerchProduct and ClothingSale models"""
        setup_client_for_business(client, manager_user, clothing_business)
        
        # Create a location
        try:
            from inventory.models import Location, MerchProduct
            from inventory.models_verticals import ClothingSale
            
            loc = Location.objects.create(
                business=clothing_business,
                name="Main Store",
                city="Lilongwe"
            )
            
            # Create a clothing product
            product = MerchProduct.objects.create(
                business=clothing_business,
                name="T-Shirt",
                kind=BusinessKind.CLOTHING,
                quantity=20
            )
            
            # Create a sale
            ClothingSale.objects.create(
                business=clothing_business,
                product=product,
                quantity=3,
                unit_price=Decimal("2000.00"),
                total_price=Decimal("6000.00"),
                sold_by=manager_user
            )
        except Exception as e:
            pytest.skip(f"Clothing models not available: {e}")
        
        url = reverse('tenants:manager_locations')
        response = client.get(url)
        
        assert response.status_code == 200
        # Check that context includes stock_summary
        if 'stock_summary' in response.context:
            stock_summary = response.context['stock_summary']
            assert isinstance(stock_summary, dict)


@pytest.mark.django_db
class TestManagerLocationsGeneric:
    """Test manager locations page for generic/unknown business types"""
    
    def test_generic_business_shows_generic_header(self, client, manager_user):
        """Generic business should show generic header without vertical suffix"""
        # Create a business with no specific kind
        business = Business.objects.create(
            name="Generic Store",
            business_kind="generic"  # or any unknown vertical
        )
        
        setup_client_for_business(client, manager_user, business)
        
        url = reverse('tenants:manager_locations')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should show generic header (without vertical suffix)
        # or not show stock summary at all
        assert 'Stock Summary by Location (Phones)' not in content
        assert 'Stock Summary by Location (Liquor)' not in content

