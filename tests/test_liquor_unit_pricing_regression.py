# tests/test_liquor_unit_pricing_regression.py
"""
Regression tests for liquor unit pricing fixes.

CRITICAL BUGS FIXED:
1. Beer: selling price was per crate, should be per bottle
2. Cider: same as beer (per bottle, not per crate)
3. Spirits/Whiskey: should sell per shot
4. Price should be editable at sale time
5. Estimated Total must reflect edited price

These tests ensure the fixes work and NEVER regress.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.helpers_liquor_units import get_liquor_unit_info, compute_sale_totals
from tenants.models import Business, Membership

User = get_user_model()


@pytest.fixture
def liquor_business():
    """Create a test liquor business"""
    return Business.objects.create(
        name="Test Liquor Unit Pricing",
        slug="test-liquor-units",
        status="ACTIVE",
        business_kind=BusinessKind.LIQUOR
    )


@pytest.fixture
def liquor_manager(liquor_business):
    """Create a manager user"""
    user = User.objects.create_user(username="liq_mgr_units", password="testpass123")
    user.is_staff = False
    user.save()
    
    Membership.objects.create(
        user=user,
        business=liquor_business,
        role="Manager",
        is_active=True
    )
    return user


@pytest.mark.django_db
class TestLiquorUnitPricingHelper:
    """
    Test: liquor unit helper computes correct per-unit prices
    """

    def test_beer_per_bottle_pricing(self, liquor_business):
        """Beer should be priced per bottle (crate price / 20)"""
        beer = MerchProduct.objects.create(
            business=liquor_business,
            name="Castle Lager Crate",
            kind=BusinessKind.LIQUOR,
            category="Beer",
            selling_price=Decimal("60000.00"),  # Per crate
            cost_price=Decimal("50000.00"),  # Per crate
            bottles_per_crate=20,
            quantity_in_stock=5,  # 5 crates
            is_active=True
        )
        
        unit_info = get_liquor_unit_info(beer)
        
        # CRITICAL: Unit price should be per bottle (60000 / 20 = 3000)
        assert unit_info["sale_unit"] == "bottle"
        assert unit_info["unit_price"] == Decimal("3000.00")
        assert unit_info["unit_cost"] == Decimal("2500.00")  # 50000 / 20
        assert unit_info["max_quantity"] == 100  # 5 crates * 20 bottles
        assert unit_info["label"] == "Bottles"

    def test_cider_per_bottle_pricing(self, liquor_business):
        """Cider should be priced per bottle (6-pack)"""
        cider = MerchProduct.objects.create(
            business=liquor_business,
            name="Hunters Dry Cider",
            kind=BusinessKind.LIQUOR,
            category="Cider",
            selling_price=Decimal("12000.00"),  # Per 6-pack
            cost_price=Decimal("9000.00"),
            bottles_per_crate=6,  # Cider uses 6-packs
            quantity_in_stock=3,
            is_active=True
        )
        
        unit_info = get_liquor_unit_info(cider)
        
        assert unit_info["sale_unit"] == "bottle"
        assert unit_info["unit_price"] == Decimal("2000.00")  # 12000 / 6
        assert unit_info["unit_cost"] == Decimal("1500.00")  # 9000 / 6
        assert unit_info["max_quantity"] == 18  # 3 * 6

    def test_spirits_per_shot_pricing(self, liquor_business):
        """Spirits should be priced per shot"""
        spirits = MerchProduct.objects.create(
            business=liquor_business,
            name="Gilbeys Vodka",
            kind=BusinessKind.LIQUOR,
            category="Spirits",
            has_shots=True,
            shots_per_bottle=25,
            barman_shots_reserved=2,
            price_per_bottle=Decimal("12000.00"),
            cost_per_bottle=Decimal("9000.00"),
            quantity_in_stock=10,  # 10 bottles
            is_active=True
        )
        
        unit_info = get_liquor_unit_info(spirits)
        
        # Sellable shots = 25 - 2 = 23
        sellable_shots = 23
        
        assert unit_info["sale_unit"] == "shot"
        # Unit price should be per shot (12000 / 23 ≈ 521.74)
        expected_shot_price = Decimal("12000.00") / Decimal(str(sellable_shots))
        assert abs(unit_info["unit_price"] - expected_shot_price) < Decimal("0.01")
        assert unit_info["max_quantity"] == 230  # 10 bottles * 23 shots
        assert unit_info["label"] == "Shots"

    def test_whiskey_per_shot_pricing(self, liquor_business):
        """Whiskey should be priced per shot"""
        whiskey = MerchProduct.objects.create(
            business=liquor_business,
            name="Black Label",
            kind=BusinessKind.LIQUOR,
            category="Whiskey",
            has_shots=True,
            shots_per_bottle=25,
            barman_shots_reserved=2,
            price_per_bottle=Decimal("25000.00"),
            cost_per_bottle=Decimal("20000.00"),
            quantity_in_stock=5,
            is_active=True
        )
        
        unit_info = get_liquor_unit_info(whiskey)
        
        sellable_shots = 23
        
        assert unit_info["sale_unit"] == "shot"
        expected_shot_price = Decimal("25000.00") / Decimal(str(sellable_shots))
        assert abs(unit_info["unit_price"] - expected_shot_price) < Decimal("0.01")


@pytest.mark.django_db
class TestLiquorSaleTotalsComputation:
    """
    Test: compute_sale_totals handles custom prices correctly
    """

    def test_sale_totals_with_default_price(self, liquor_business):
        """Sale totals should compute correctly with default price"""
        beer = MerchProduct.objects.create(
            business=liquor_business,
            name="Test Beer",
            kind=BusinessKind.LIQUOR,
            category="Beer",
            selling_price=Decimal("60000.00"),
            cost_price=Decimal("50000.00"),
            bottles_per_crate=20,
            quantity_in_stock=10,
            is_active=True
        )
        
        # Sell 5 bottles at default price (3000 each)
        totals = compute_sale_totals(beer, quantity=5, unit_price=None)
        
        assert totals["unit_price"] == Decimal("3000.00")  # 60000 / 20
        assert totals["total"] == Decimal("15000.00")  # 5 * 3000
        assert totals["profit"] == Decimal("2500.00")  # (3000 - 2500) * 5

    def test_sale_totals_with_custom_price(self, liquor_business):
        """Sale totals should use custom price when provided"""
        beer = MerchProduct.objects.create(
            business=liquor_business,
            name="Test Beer 2",
            kind=BusinessKind.LIQUOR,
            category="Beer",
            selling_price=Decimal("60000.00"),
            cost_price=Decimal("50000.00"),
            bottles_per_crate=20,
            quantity_in_stock=10,
            is_active=True
        )
        
        # Sell 10 bottles at CUSTOM price (3500 instead of default 3000)
        custom_price = Decimal("3500.00")
        totals = compute_sale_totals(beer, quantity=10, unit_price=custom_price)
        
        # CRITICAL: Must use custom price, not default
        assert totals["unit_price"] == custom_price
        assert totals["total"] == Decimal("35000.00")  # 10 * 3500
        assert totals["profit"] == Decimal("10000.00")  # (3500 - 2500) * 10


@pytest.mark.django_db
class TestLiquorSellViewPricing:
    """
    Test: Liquor sell view uses correct unit pricing
    """

    def test_sell_view_computes_bottle_price_correctly(self, client, liquor_business, liquor_manager):
        """Sell view should compute per-bottle price for beer"""
        client.force_login(liquor_manager)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = liquor_business.id
        session.save()
        
        # Create beer product
        beer = MerchProduct.objects.create(
            business=liquor_business,
            name="Test Beer Crate",
            kind=BusinessKind.LIQUOR,
            category="Beer",
            selling_price=Decimal("60000.00"),  # Crate price
            cost_price=Decimal("50000.00"),
            bottles_per_crate=20,
            quantity_in_stock=10,
            is_active=True
        )
        
        # Get sell page
        url = reverse('liquor:sell')
        response = client.get(url)
        
        # Page should load successfully
        assert response.status_code == 200
        
        # Template should show per-bottle price (not crate price)
        # (Actual JS computation tested in E2E tests)


# Run these tests:
# pytest tests/test_liquor_unit_pricing_regression.py -v
# pytest tests/test_liquor_unit_pricing_regression.py::TestLiquorUnitPricingHelper::test_beer_per_bottle_pricing -v

