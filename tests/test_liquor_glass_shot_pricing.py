"""
Tests for liquor glass and shot pricing with auto-cost calculation
"""
from decimal import Decimal
import pytest
from django.contrib.auth import get_user_model
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind
from tenants.models import Business

User = get_user_model()


@pytest.mark.django_db
class TestLiquorGlassShotPricing:
    """Test glass and shot pricing with automatic cost calculations"""
    
    @pytest.fixture
    def business(self):
        """Create a test business"""
        return Business.objects.create(
            name="Test Liquor Store"
        )
    
    @pytest.fixture
    def manager(self):
        """Create a test manager user"""
        return User.objects.create_user(
            username="manager",
            password="testpass123",
            is_staff=True
        )
    
    def test_wine_glass_cost_auto_calculation(self, business):
        """Test that cost per glass is auto-calculated from bottle cost"""
        wine = MerchProduct.objects.create(
            business=business,
            name="Nederburg Cabernet Sauvignon",
            kind=BusinessKind.LIQUOR,
            category="wine",
            has_glasses=True,
            glasses_per_bottle=5,
            cost_per_bottle=Decimal("5000.00"),
            price_per_bottle=Decimal("8000.00"),
            price_per_glass=Decimal("2000.00")
        )
        
        # Refresh from database to get auto-calculated values
        wine.refresh_from_db()
        
        # Assert cost per glass was auto-calculated
        expected_cost_per_glass = Decimal("5000.00") / Decimal("5")
        assert wine.cost_per_glass == expected_cost_per_glass.quantize(Decimal("0.01"))
        assert wine.cost_per_glass == Decimal("1000.00")
    
    def test_spirits_shot_cost_auto_calculation(self, business):
        """Test that cost per shot is auto-calculated from bottle cost"""
        vodka = MerchProduct.objects.create(
            business=business,
            name="Smirnoff Vodka",
            kind=BusinessKind.LIQUOR,
            category="spirits",
            has_shots=True,
            shots_per_bottle=25,
            barman_shots_reserved=2,
            cost_per_bottle=Decimal("10000.00"),
            price_per_bottle=Decimal("15000.00"),
            price_per_shot=Decimal("800.00")
        )
        
        # Refresh from database to get auto-calculated values
        vodka.refresh_from_db()
        
        # Assert cost per shot was auto-calculated based on sellable shots
        sellable_shots = 25 - 2  # 23 sellable shots
        expected_cost_per_shot = Decimal("10000.00") / Decimal(str(sellable_shots))
        assert vodka.cost_per_shot == expected_cost_per_shot.quantize(Decimal("0.01"))
        assert vodka.cost_per_shot == Decimal("434.78")
    
    def test_whiskey_shot_cost_with_different_reserved(self, business):
        """Test shot cost calculation with different barman reserved amounts"""
        whiskey = MerchProduct.objects.create(
            business=business,
            name="Jameson Irish Whiskey",
            kind=BusinessKind.LIQUOR,
            category="whiskey",
            has_shots=True,
            shots_per_bottle=30,
            barman_shots_reserved=3,
            cost_per_bottle=Decimal("12000.00"),
            price_per_bottle=Decimal("18000.00"),
            price_per_shot=Decimal("1000.00")
        )
        
        whiskey.refresh_from_db()
        
        # Sellable shots: 30 - 3 = 27
        expected_cost_per_shot = Decimal("12000.00") / Decimal("27")
        assert whiskey.cost_per_shot == expected_cost_per_shot.quantize(Decimal("0.01"))
        assert whiskey.cost_per_shot == Decimal("444.44")
    
    def test_manual_cost_override_not_overwritten(self, business):
        """Test that manually set cost per glass is not overwritten"""
        wine = MerchProduct.objects.create(
            business=business,
            name="Premium Wine",
            kind=BusinessKind.LIQUOR,
            category="wine",
            has_glasses=True,
            glasses_per_bottle=5,
            cost_per_bottle=Decimal("5000.00"),
            price_per_glass=Decimal("2000.00"),
            cost_per_glass=Decimal("1200.00")  # Manually set higher cost
        )
        
        wine.refresh_from_db()
        
        # Manual cost should be preserved
        assert wine.cost_per_glass == Decimal("1200.00")
    
    def test_get_cost_for_unit_glass(self, business):
        """Test get_cost_for_unit returns correct cost for glass"""
        wine = MerchProduct.objects.create(
            business=business,
            name="Test Wine",
            kind=BusinessKind.LIQUOR,
            has_glasses=True,
            glasses_per_bottle=5,
            cost_per_bottle=Decimal("5000.00"),
            cost_per_glass=Decimal("1000.00"),
            price_per_glass=Decimal("2000.00")
        )
        
        cost = wine.get_cost_for_unit("glass")
        assert cost == Decimal("1000.00")
    
    def test_get_cost_for_unit_shot(self, business):
        """Test get_cost_for_unit returns correct cost for shot"""
        vodka = MerchProduct.objects.create(
            business=business,
            name="Test Vodka",
            kind=BusinessKind.LIQUOR,
            has_shots=True,
            shots_per_bottle=25,
            barman_shots_reserved=2,
            cost_per_bottle=Decimal("10000.00"),
            cost_per_shot=Decimal("435.00"),
            price_per_shot=Decimal("800.00")
        )
        
        cost = vodka.get_cost_for_unit("shot")
        assert cost == Decimal("435.00")
    
    def test_get_price_for_unit_glass(self, business):
        """Test get_price_for_unit returns correct price for glass"""
        wine = MerchProduct.objects.create(
            business=business,
            name="Test Wine",
            kind=BusinessKind.LIQUOR,
            has_glasses=True,
            price_per_glass=Decimal("2000.00")
        )
        
        price = wine.get_price_for_unit("glass")
        assert price == Decimal("2000.00")
    
    def test_get_price_for_unit_shot(self, business):
        """Test get_price_for_unit returns correct price for shot"""
        vodka = MerchProduct.objects.create(
            business=business,
            name="Test Vodka",
            kind=BusinessKind.LIQUOR,
            has_shots=True,
            price_per_shot=Decimal("800.00")
        )
        
        price = vodka.get_price_for_unit("shot")
        assert price == Decimal("800.00")
    
    def test_profit_calculation_glass(self, business):
        """Test profit calculation for glass sales"""
        wine = MerchProduct.objects.create(
            business=business,
            name="Profitable Wine",
            kind=BusinessKind.LIQUOR,
            has_glasses=True,
            glasses_per_bottle=5,
            cost_per_bottle=Decimal("5000.00"),
            price_per_glass=Decimal("2000.00")
        )
        
        wine.refresh_from_db()
        
        # Selling 1 glass
        unit_cost = wine.get_cost_for_unit("glass")
        unit_price = wine.get_price_for_unit("glass")
        profit = unit_price - unit_cost
        
        assert profit == Decimal("1000.00")  # MK 2000 - MK 1000
        
        # Margin calculation
        margin_percent = (profit / unit_price) * 100
        assert margin_percent == Decimal("50.00")  # 50% margin
    
    def test_profit_calculation_shot(self, business):
        """Test profit calculation for shot sales"""
        vodka = MerchProduct.objects.create(
            business=business,
            name="Profitable Vodka",
            kind=BusinessKind.LIQUOR,
            has_shots=True,
            shots_per_bottle=25,
            barman_shots_reserved=2,
            cost_per_bottle=Decimal("10000.00"),
            price_per_shot=Decimal("1000.00")
        )
        
        vodka.refresh_from_db()
        
        # Selling 1 shot
        unit_cost = vodka.get_cost_for_unit("shot")
        unit_price = vodka.get_price_for_unit("shot")
        profit = unit_price - unit_cost
        
        # Cost per shot: 10000 / 23 = 434.78
        # Profit: 1000 - 434.78 = 565.22
        assert profit > Decimal("565.00")
        assert profit < Decimal("566.00")
    
    def test_below_cost_detection(self, business):
        """Test detection of selling below cost"""
        wine = MerchProduct.objects.create(
            business=business,
            name="Loss Wine",
            kind=BusinessKind.LIQUOR,
            has_glasses=True,
            glasses_per_bottle=5,
            cost_per_bottle=Decimal("5000.00"),
            price_per_glass=Decimal("800.00")  # Below cost!
        )
        
        wine.refresh_from_db()
        
        unit_cost = wine.get_cost_for_unit("glass")  # MK 1000
        unit_price = wine.get_price_for_unit("glass")  # MK 800
        
        # Assert selling below cost
        assert unit_price < unit_cost
        loss = unit_cost - unit_price
        assert loss == Decimal("200.00")
    
    def test_zero_barman_reserved_shots(self, business):
        """Test shot calculation with zero barman reserved shots"""
        vodka = MerchProduct.objects.create(
            business=business,
            name="No Reserve Vodka",
            kind=BusinessKind.LIQUOR,
            has_shots=True,
            shots_per_bottle=25,
            barman_shots_reserved=0,
            cost_per_bottle=Decimal("10000.00"),
            price_per_shot=Decimal("500.00")
        )
        
        vodka.refresh_from_db()
        
        # All 25 shots are sellable
        expected_cost_per_shot = Decimal("10000.00") / Decimal("25")
        assert vodka.cost_per_shot == expected_cost_per_shot.quantize(Decimal("0.01"))
        assert vodka.cost_per_shot == Decimal("400.00")

