# tests/test_liquor_stockin_wizard.py
"""
Comprehensive tests for Liquor Stock-In Wizard with type-specific calculations.
Tests Beer, Cider, Wine, Spirits, and Whisky stock-in flows.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.core.exceptions import ValidationError

from tenants.models import Business
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind
from inventory.liquor_stockin_wizard_adapter import LiquorStockInAdapter

User = get_user_model()


@pytest.fixture
def business(db):
    """Create a test business"""
    return Business.objects.create(
        name="Test Liquor Store",
        owner_email="owner@test.com",
        kind=BusinessKind.LIQUOR
    )


@pytest.fixture
def manager_user(db, business):
    """Create a manager user with proper permissions"""
    from tenants.models import Membership
    
    user = User.objects.create_user(
        username="manager",
        email="manager@test.com",
        password="testpass123"
    )
    user.is_staff = True
    user.save()
    
    # Create business membership with manager role
    Membership.objects.create(
        user=user,
        business=business,
        role='manager',
        is_active=True
    )
    
    return user


@pytest.fixture
def client_logged_in(client, manager_user, business):
    """Return a logged-in client with active business set"""
    client.login(username="manager", password="testpass123")
    
    # Set active business in session
    session = client.session
    session['active_business_id'] = business.id
    session.save()
    
    return client


@pytest.fixture
def beer_product(db, business):
    """Create a beer product"""
    return MerchProduct.objects.create(
        business=business,
        name="Castle Lager",
        kind=BusinessKind.LIQUOR,
        category="beer",
        quantity_in_stock=0,
        cost_per_bottle=Decimal("0.00"),
        is_active=True
    )


@pytest.fixture
def cider_product(db, business):
    """Create a cider product"""
    return MerchProduct.objects.create(
        business=business,
        name="Savanna Dry",
        kind=BusinessKind.LIQUOR,
        category="cider",
        quantity_in_stock=0,
        cost_per_bottle=Decimal("0.00"),
        is_active=True
    )


@pytest.fixture
def wine_product(db, business):
    """Create a wine product"""
    return MerchProduct.objects.create(
        business=business,
        name="Nederburg Cabernet",
        kind=BusinessKind.LIQUOR,
        category="wine",
        quantity_in_stock=0,
        cost_per_bottle=Decimal("0.00"),
        is_active=True
    )


@pytest.fixture
def spirits_product(db, business):
    """Create a spirits product"""
    return MerchProduct.objects.create(
        business=business,
        name="Smirnoff Vodka",
        kind=BusinessKind.LIQUOR,
        category="spirits",
        quantity_in_stock=0,
        cost_per_bottle=Decimal("0.00"),
        is_active=True
    )


@pytest.fixture
def whisky_product(db, business):
    """Create a whisky product"""
    return MerchProduct.objects.create(
        business=business,
        name="Johnnie Walker Black",
        kind=BusinessKind.LIQUOR,
        category="whisky",
        quantity_in_stock=0,
        cost_per_bottle=Decimal("0.00"),
        is_active=True
    )


# ============================================================================
# ADAPTER UNIT TESTS
# ============================================================================

class TestBeerAdapter:
    """Test Beer stock-in calculations"""
    
    def test_beer_calculation_basic(self):
        """Test basic beer calculation: 5 crates, no loose bottles"""
        result = LiquorStockInAdapter.compute_beer_stockin(
            crates=5,
            loose_bottles=0,
            cost_per_crate=Decimal("300000")
        )
        
        assert result['quantity_units_added'] == 100  # 5 crates * 20 bottles
        assert result['unit_cost'] == Decimal("15000.00")  # 1500000 / 100
        assert result['total_cost'] == Decimal("1500000")  # 5 * 300000
    
    def test_beer_calculation_with_loose(self):
        """Test beer calculation with loose bottles"""
        result = LiquorStockInAdapter.compute_beer_stockin(
            crates=2,
            loose_bottles=5,
            cost_per_crate=Decimal("200000")
        )
        
        # 2 crates = 40 bottles + 5 loose = 45 bottles
        assert result['quantity_units_added'] == 45
        # Loose cost = (200000 / 20) * 5 = 10000 * 5 = 50000
        # Total cost = (2 * 200000) + 50000 = 450000
        assert result['total_cost'] == Decimal("450000")
        # Unit cost = 450000 / 45 = 10000
        assert result['unit_cost'] == Decimal("10000.00")
    
    def test_beer_validation_negative_crates(self):
        """Test validation: negative crates should fail"""
        with pytest.raises(ValidationError, match="Crates must be at least 1"):
            LiquorStockInAdapter.compute_beer_stockin(
                crates=0,
                loose_bottles=0,
                cost_per_crate=Decimal("300000")
            )
    
    def test_beer_validation_zero_cost(self):
        """Test validation: zero cost should fail"""
        with pytest.raises(ValidationError, match="Cost per crate must be greater than 0"):
            LiquorStockInAdapter.compute_beer_stockin(
                crates=5,
                loose_bottles=0,
                cost_per_crate=Decimal("0")
            )


class TestCiderAdapter:
    """Test Cider stock-in calculations"""
    
    def test_cider_calculation(self):
        """Test cider calculation: 20 bottles at 1000 each"""
        result = LiquorStockInAdapter.compute_cider_stockin(
            quantity_bottles=20,
            cost_per_bottle=Decimal("1000")
        )
        
        assert result['quantity_units_added'] == 20
        assert result['unit_cost'] == Decimal("1000")
        assert result['total_cost'] == Decimal("20000")  # 20 * 1000
    
    def test_cider_validation_zero_quantity(self):
        """Test validation: zero quantity should fail"""
        with pytest.raises(ValidationError, match="Quantity must be at least 1"):
            LiquorStockInAdapter.compute_cider_stockin(
                quantity_bottles=0,
                cost_per_bottle=Decimal("1000")
            )


class TestWineAdapter:
    """Test Wine stock-in calculations"""
    
    def test_wine_calculation(self):
        """Test wine calculation: 2 bottles at 50000 each = 10 glasses"""
        result = LiquorStockInAdapter.compute_wine_stockin(
            bottles=2,
            cost_per_bottle=Decimal("50000")
        )
        
        assert result['quantity_units_added'] == 10  # 2 bottles * 5 glasses
        assert result['unit_cost'] == Decimal("10000.00")  # 50000 / 5
        assert result['total_cost'] == Decimal("100000")  # 2 * 50000
    
    def test_wine_calculation_single_bottle(self):
        """Test wine calculation with single bottle"""
        result = LiquorStockInAdapter.compute_wine_stockin(
            bottles=1,
            cost_per_bottle=Decimal("75000")
        )
        
        assert result['quantity_units_added'] == 5  # 1 bottle * 5 glasses
        assert result['unit_cost'] == Decimal("15000.00")  # 75000 / 5
        assert result['total_cost'] == Decimal("75000")


class TestSpiritsAdapter:
    """Test Spirits stock-in calculations"""
    
    def test_spirits_calculation_with_reserved(self):
        """Test spirits calculation: 60 shots, 10 reserved, 500 per shot"""
        result = LiquorStockInAdapter.compute_spirits_stockin(
            shots_added=60,
            cost_per_shot=Decimal("500"),
            reserved_barman_shots=10
        )
        
        assert result['quantity_units_added'] == 50  # 60 - 10 reserved
        assert result['unit_cost'] == Decimal("500")
        assert result['total_cost'] == Decimal("30000")  # 60 * 500
        assert result['reserved_shots'] == 10
    
    def test_spirits_calculation_no_reserved(self):
        """Test spirits calculation without reserved shots"""
        result = LiquorStockInAdapter.compute_spirits_stockin(
            shots_added=30,
            cost_per_shot=Decimal("1000"),
            reserved_barman_shots=0
        )
        
        assert result['quantity_units_added'] == 30
        assert result['unit_cost'] == Decimal("1000")
        assert result['total_cost'] == Decimal("30000")
        assert result['reserved_shots'] == 0
    
    def test_spirits_validation_reserved_exceeds_total(self):
        """Test validation: reserved >= total should fail"""
        with pytest.raises(ValidationError, match="Reserved shots must be less than total"):
            LiquorStockInAdapter.compute_spirits_stockin(
                shots_added=30,
                cost_per_shot=Decimal("500"),
                reserved_barman_shots=30
            )


class TestWhiskyAdapter:
    """Test Whisky stock-in calculations (same as Spirits)"""
    
    def test_whisky_calculation(self):
        """Test whisky calculation: 60 shots, 10 reserved, 500 per shot"""
        result = LiquorStockInAdapter.compute_whisky_stockin(
            shots_added=60,
            cost_per_shot=Decimal("500"),
            reserved_barman_shots=10
        )
        
        assert result['quantity_units_added'] == 50  # 60 - 10 reserved
        assert result['unit_cost'] == Decimal("500")
        assert result['total_cost'] == Decimal("30000")  # 60 * 500
        assert result['reserved_shots'] == 10


# ============================================================================
# INTEGRATION TESTS (View + Database)
# ============================================================================

@pytest.mark.django_db
class TestBeerStockInIntegration:
    """Test Beer stock-in through views"""
    
    def test_beer_stockin_view_page_loads(self, client_logged_in, beer_product, business):
        """Test that beer stock-in wizard page loads"""
        url = reverse('inventory:liquor_stock_in', kwargs={'product_id': beer_product.id})
        response = client_logged_in.get(url)
        
        assert response.status_code == 200
        assert 'beer' in response.content.decode().lower()
    
    def test_beer_stockin_submit(self, client_logged_in, beer_product, business):
        """Test beer stock-in submission"""
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': beer_product.id})
        response = client_logged_in.post(url, {
            'crates': '5',
            'loose_bottles': '0',
            'cost_per_crate': '300000',
            'date_received': '2026-02-12',
            'notes': 'Test stock-in'
        })
        
        # Refresh product from DB
        beer_product.refresh_from_db()
        
        # Verify calculations
        assert beer_product.quantity_in_stock == 100  # 5 crates * 20
        assert beer_product.cost_per_bottle == Decimal("15000.00")  # 1500000 / 100


@pytest.mark.django_db
class TestCiderStockInIntegration:
    """Test Cider stock-in through views"""
    
    def test_cider_stockin_submit(self, client_logged_in, cider_product, business):
        """Test cider stock-in submission"""
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': cider_product.id})
        response = client_logged_in.post(url, {
            'quantity_bottles': '20',
            'cost_per_bottle': '1000',
            'date_received': '2026-02-12',
            'notes': ''
        })
        
        cider_product.refresh_from_db()
        
        assert cider_product.quantity_in_stock == 20
        assert cider_product.cost_per_bottle == Decimal("1000")


@pytest.mark.django_db
class TestWineStockInIntegration:
    """Test Wine stock-in through views"""
    
    def test_wine_stockin_submit(self, client_logged_in, wine_product, business):
        """Test wine stock-in submission"""
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': wine_product.id})
        response = client_logged_in.post(url, {
            'bottles': '2',
            'cost_per_bottle': '50000',
            'date_received': '2026-02-12',
            'notes': ''
        })
        
        wine_product.refresh_from_db()
        
        assert wine_product.quantity_in_stock == 10  # 2 bottles * 5 glasses
        assert wine_product.cost_per_bottle == Decimal("10000.00")  # 50000 / 5


@pytest.mark.django_db
class TestSpiritsStockInIntegration:
    """Test Spirits stock-in through views"""
    
    def test_spirits_stockin_submit(self, client_logged_in, spirits_product, business):
        """Test spirits stock-in submission"""
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': spirits_product.id})
        response = client_logged_in.post(url, {
            'shots_added': '60',
            'cost_per_shot': '500',
            'reserved_barman_shots': '10',
            'date_received': '2026-02-12',
            'notes': ''
        })
        
        spirits_product.refresh_from_db()
        
        assert spirits_product.quantity_in_stock == 50  # 60 - 10 reserved
        assert spirits_product.cost_per_bottle == Decimal("500")


@pytest.mark.django_db
class TestWhiskyStockInIntegration:
    """Test Whisky stock-in through views"""
    
    def test_whisky_stockin_submit(self, client_logged_in, whisky_product, business):
        """Test whisky stock-in submission (same as spirits)"""
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': whisky_product.id})
        response = client_logged_in.post(url, {
            'shots_added': '60',
            'cost_per_shot': '500',
            'reserved_barman_shots': '10',
            'date_received': '2026-02-12',
            'notes': ''
        })
        
        whisky_product.refresh_from_db()
        
        assert whisky_product.quantity_in_stock == 50  # 60 - 10 reserved
        assert whisky_product.cost_per_bottle == Decimal("500")


# ============================================================================
# STOCK VALUE CALCULATION TESTS
# ============================================================================

@pytest.mark.django_db
class TestStockValueCalculation:
    """Test that stock value reflects added inventory cost"""
    
    def test_stock_value_after_beer_stockin(self, client_logged_in, beer_product, business):
        """Test stock value after beer stock-in"""
        # Stock in beer
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': beer_product.id})
        client_logged_in.post(url, {
            'crates': '5',
            'loose_bottles': '0',
            'cost_per_crate': '300000',
            'date_received': '2026-02-12',
            'notes': ''
        })
        
        beer_product.refresh_from_db()
        
        # Calculate expected stock value
        expected_stock_value = beer_product.quantity_in_stock * beer_product.cost_per_bottle
        # 100 bottles * 15000 = 1500000
        assert expected_stock_value == Decimal("1500000.00")
    
    def test_stock_value_after_wine_stockin(self, client_logged_in, wine_product, business):
        """Test stock value after wine stock-in"""
        # Stock in wine
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': wine_product.id})
        client_logged_in.post(url, {
            'bottles': '2',
            'cost_per_bottle': '50000',
            'date_received': '2026-02-12',
            'notes': ''
        })
        
        wine_product.refresh_from_db()
        
        # Calculate expected stock value
        # 10 glasses * 10000 per glass = 100000
        expected_stock_value = wine_product.quantity_in_stock * wine_product.cost_per_bottle
        assert expected_stock_value == Decimal("100000.00")

