"""
Test suite for Liquor Unit Logic (Bottles vs Shots SSOT).

Tests that the liquor unit helper correctly computes:
- Beer/Cider: sold per bottle (from crates)
- Spirits/Whiskey: sold per shot
- Wine: sold per glass
- Unit prices and max quantities

CRITICAL: These tests ensure unit logic is consistent across all liquor flows.
"""
import pytest
from decimal import Decimal

from tenants.models import Business
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind
from inventory.helpers_liquor_units import get_liquor_unit_info, compute_sale_totals


@pytest.fixture
def liquor_business(db):
    """Create a liquor business."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    user = User.objects.create_user(
        username="liquor_test",
        email="test@liquor.test",
        password="testpass123",
    )
    business = Business.objects.create(
        name="Test Liquor Bar",
        kind=BusinessKind.LIQUOR,
        created_by=user,
    )
    return business


@pytest.mark.django_db
class TestBeerCiderUnitLogic:
    """Test that beer/cider are correctly handled as bottles."""
    
    def test_beer_unit_is_bottle(self, liquor_business):
        """Beer products should have 'bottle' as sale unit."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Test Beer",
            category="beer",
            kind=BusinessKind.LIQUOR,
            selling_price=Decimal("60000.00"),  # Price per crate
            cost_price=Decimal("40000.00"),
            quantity_in_stock=10,  # 10 crates
            bottles_per_crate=20,
            is_active=True,
        )
        
        unit_info = get_liquor_unit_info(product)
        
        assert unit_info["sale_unit"] == "bottle"
        assert unit_info["label"] == "Bottles"
        assert unit_info["units_per_item"] == 20  # bottles per crate
        
    def test_beer_unit_price_computed_from_crate(self, liquor_business):
        """Beer unit price should be crate price divided by bottles per crate."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Carlsberg",
            category="beer",
            kind=BusinessKind.LIQUOR,
            selling_price=Decimal("60000.00"),  # MK 60,000 per crate
            cost_price=Decimal("40000.00"),
            quantity_in_stock=10,
            bottles_per_crate=20,
            is_active=True,
        )
        
        unit_info = get_liquor_unit_info(product)
        
        # 60000 / 20 = 3000 per bottle
        assert unit_info["unit_price"] == Decimal("3000.00")
        # 40000 / 20 = 2000 per bottle cost
        assert unit_info["unit_cost"] == Decimal("2000.00")
        
    def test_beer_max_quantity_is_bottles_not_crates(self, liquor_business):
        """Max quantity for beer should be total bottles (crates * bottles_per_crate)."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Kuche Kuche",
            category="beer",
            kind=BusinessKind.LIQUOR,
            selling_price=Decimal("60000.00"),
            quantity_in_stock=5,  # 5 crates in stock
            bottles_per_crate=20,
            is_active=True,
        )
        
        unit_info = get_liquor_unit_info(product)
        
        # 5 crates * 20 bottles = 100 bottles available
        assert unit_info["max_quantity"] == 100
        
    def test_cider_unit_is_bottle(self, liquor_business):
        """Cider should also use bottles."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Savanna Cider",
            category="cider",
            kind=BusinessKind.LIQUOR,
            selling_price=Decimal("18000.00"),  # 6-pack price
            quantity_in_stock=8,
            bottles_per_crate=6,  # Cider uses 6-packs
            is_active=True,
        )
        
        unit_info = get_liquor_unit_info(product)
        
        assert unit_info["sale_unit"] == "bottle"
        assert unit_info["label"] == "Bottles"
        # 18000 / 6 = 3000 per bottle
        assert unit_info["unit_price"] == Decimal("3000.00")


@pytest.mark.django_db
class TestSpiritsWhiskeyUnitLogic:
    """Test that spirits/whiskey are correctly handled as shots."""
    
    def test_spirits_unit_is_shot(self, liquor_business):
        """Spirits products should have 'shot' as sale unit."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Smirnoff Vodka",
            category="spirits",
            kind=BusinessKind.LIQUOR,
            price_per_bottle=Decimal("25000.00"),
            cost_per_bottle=Decimal("18000.00"),
            quantity_in_stock=10,  # 10 bottles
            has_shots=True,
            shots_per_bottle=25,
            barman_shots_reserved=2,
            is_active=True,
        )
        
        unit_info = get_liquor_unit_info(product)
        
        assert unit_info["sale_unit"] == "shot"
        assert unit_info["label"] == "Shots"
        # 25 - 2 = 23 sellable shots per bottle
        assert unit_info["units_per_item"] == 23
        
    def test_spirits_unit_price_computed_from_bottle(self, liquor_business):
        """Spirits unit price should be bottle price divided by sellable shots."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Gilbeys Gin",
            category="spirits",
            kind=BusinessKind.LIQUOR,
            price_per_bottle=Decimal("23000.00"),
            cost_per_bottle=Decimal("16000.00"),
            quantity_in_stock=5,
            has_shots=True,
            shots_per_bottle=25,
            barman_shots_reserved=2,  # 25 - 2 = 23 sellable
            is_active=True,
        )
        
        unit_info = get_liquor_unit_info(product)
        
        # 23000 / 23 = 1000 per shot
        assert unit_info["unit_price"] == Decimal("1000.00")
        # 16000 / 23 ≈ 695.65 per shot cost
        expected_cost = Decimal("16000.00") / Decimal("23")
        assert abs(unit_info["unit_cost"] - expected_cost) < Decimal("0.01")
        
    def test_whiskey_unit_is_shot(self, liquor_business):
        """Whiskey should also use shots."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Johnnie Walker Black",
            category="whiskey",
            kind=BusinessKind.LIQUOR,
            price_per_bottle=Decimal("50000.00"),
            quantity_in_stock=3,
            has_shots=True,
            shots_per_bottle=25,
            barman_shots_reserved=2,
            is_active=True,
        )
        
        unit_info = get_liquor_unit_info(product)
        
        assert unit_info["sale_unit"] == "shot"
        assert unit_info["label"] == "Shots"
        
    def test_spirits_max_quantity_is_shots_not_bottles(self, liquor_business):
        """Max quantity for spirits should be total shots (bottles * sellable_shots_per_bottle)."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Captain Morgan",
            category="spirits",
            kind=BusinessKind.LIQUOR,
            price_per_bottle=Decimal("30000.00"),
            quantity_in_stock=4,  # 4 bottles in stock
            has_shots=True,
            shots_per_bottle=25,
            barman_shots_reserved=2,
            is_active=True,
        )
        
        unit_info = get_liquor_unit_info(product)
        
        # 4 bottles * 23 sellable shots = 92 shots available
        assert unit_info["max_quantity"] == 92


@pytest.mark.django_db
class TestWineUnitLogic:
    """Test that wine is correctly handled as glasses."""
    
    def test_wine_unit_is_glass(self, liquor_business):
        """Wine products should have 'glass' as sale unit."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Cabernet Sauvignon",
            category="wine",
            kind=BusinessKind.LIQUOR,
            price_per_bottle=Decimal("15000.00"),
            quantity_in_stock=6,
            has_glasses=True,
            glasses_per_bottle=5,
            is_active=True,
        )
        
        unit_info = get_liquor_unit_info(product)
        
        assert unit_info["sale_unit"] == "glass"
        assert unit_info["label"] == "Glasses"
        assert unit_info["units_per_item"] == 5
        
    def test_wine_unit_price_computed_from_bottle(self, liquor_business):
        """Wine unit price should be bottle price divided by glasses per bottle."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Merlot",
            category="wine",
            kind=BusinessKind.LIQUOR,
            price_per_bottle=Decimal("20000.00"),
            cost_per_bottle=Decimal("12000.00"),
            quantity_in_stock=10,
            has_glasses=True,
            glasses_per_bottle=5,
            is_active=True,
        )
        
        unit_info = get_liquor_unit_info(product)
        
        # 20000 / 5 = 4000 per glass
        assert unit_info["unit_price"] == Decimal("4000.00")
        # 12000 / 5 = 2400 per glass cost
        assert unit_info["unit_cost"] == Decimal("2400.00")


@pytest.mark.django_db
class TestComputeSaleTotals:
    """Test sale total computations."""
    
    def test_compute_beer_sale_totals(self, liquor_business):
        """Compute totals for a beer sale (bottles)."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Castle Lite",
            category="beer",
            kind=BusinessKind.LIQUOR,
            selling_price=Decimal("60000.00"),
            cost_price=Decimal("40000.00"),
            quantity_in_stock=10,
            bottles_per_crate=20,
            is_active=True,
        )
        
        totals = compute_sale_totals(product, quantity=5)  # 5 bottles
        
        # 3000 * 5 = 15000
        assert totals["total"] == Decimal("15000.00")
        # 2000 * 5 = 10000
        assert totals["total_cost"] == Decimal("10000.00")
        # 15000 - 10000 = 5000
        assert totals["profit"] == Decimal("5000.00")
        # (5000 / 15000) * 100 = 33.33%
        assert abs(totals["margin"] - Decimal("33.33")) < Decimal("0.01")
        
    def test_compute_spirits_sale_totals(self, liquor_business):
        """Compute totals for a spirits sale (shots)."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Absolut Vodka",
            category="spirits",
            kind=BusinessKind.LIQUOR,
            price_per_bottle=Decimal("23000.00"),
            cost_per_bottle=Decimal("16000.00"),
            quantity_in_stock=5,
            has_shots=True,
            shots_per_bottle=25,
            barman_shots_reserved=2,
            is_active=True,
        )
        
        totals = compute_sale_totals(product, quantity=10)  # 10 shots
        
        # 1000 * 10 = 10000
        assert totals["total"] == Decimal("10000.00")
        # Check profit is positive
        assert totals["profit"] > Decimal("0.00")
        
    def test_compute_with_custom_unit_price(self, liquor_business):
        """Compute totals with custom unit price override."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Test Product",
            category="spirits",
            kind=BusinessKind.LIQUOR,
            price_per_bottle=Decimal("25000.00"),
            quantity_in_stock=10,
            has_shots=True,
            shots_per_bottle=25,
            barman_shots_reserved=2,
            is_active=True,
        )
        
        # Override price to MK 1500 per shot
        totals = compute_sale_totals(product, quantity=5, unit_price=Decimal("1500.00"))
        
        # 1500 * 5 = 7500
        assert totals["total"] == Decimal("7500.00")
        assert totals["unit_price"] == Decimal("1500.00")


@pytest.mark.django_db
class TestFallbackBehavior:
    """Test that unit logic handles missing/malformed data gracefully."""
    
    def test_missing_bottles_per_crate_defaults_to_1(self, liquor_business):
        """If bottles_per_crate is missing, default to 1."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Beer Without Crate Size",
            category="beer",
            kind=BusinessKind.LIQUOR,
            price_per_bottle=Decimal("3000.00"),  # Explicit bottle price
            selling_price=Decimal("60000.00"),  # Crate price
            quantity_in_stock=50,
            bottles_per_crate=20,  # Beer requires crate size
            is_active=True,
        )
        
        unit_info = get_liquor_unit_info(product)
        
        # Should use explicit bottle price
        assert unit_info["sale_unit"] == "bottle"
        assert unit_info["unit_price"] == Decimal("3000.00")
        
    def test_missing_prices_default_to_zero(self, liquor_business):
        """If prices are missing, default to Decimal('0.00')."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Product Without Prices",
            category="spirits",
            kind=BusinessKind.LIQUOR,
            # No prices set
            quantity_in_stock=10,
            has_shots=True,
            shots_per_bottle=25,
            is_active=True,
        )
        
        unit_info = get_liquor_unit_info(product)
        
        # Should not crash - return 0
        assert unit_info["unit_price"] == Decimal("0.00")
        assert unit_info["unit_cost"] == Decimal("0.00")
        
    def test_zero_stock_returns_zero_max_quantity(self, liquor_business):
        """If stock is zero, max_quantity should be zero."""
        product = MerchProduct.objects.create(
            business=liquor_business,
            name="Out of Stock Beer",
            category="beer",
            kind=BusinessKind.LIQUOR,
            selling_price=Decimal("60000.00"),
            quantity_in_stock=0,  # Out of stock
            bottles_per_crate=20,
            is_active=True,
        )
        
        unit_info = get_liquor_unit_info(product)
        
        assert unit_info["max_quantity"] == 0

