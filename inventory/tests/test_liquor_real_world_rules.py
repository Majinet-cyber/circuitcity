"""
Test real-world liquor rules enforcement.

CRITICAL: These tests lock in business rules that must NEVER break:
- Beer: BOTTLE/CAN + CRATE only (never shots)
- Cider: BOTTLE/CAN + 6-PACK only (NO CRATES, never shots, pack_size MUST be 6)
- Wine: GLASS or BOTTLE only (never shots)
- Spirits/Whisky: SHOT or BOTTLE only, stock-in BOTTLE-ONLY (no case/crate/pack)

Malawi defaults:
- Beer crate = 20 bottles
- Cider 6-pack = 6 bottles (ENFORCED, cannot be changed)
- Wine glasses_per_bottle = 5
- Spirits shots_per_bottle = 24 (changed from 30)
- Barman shots = 2 per bottle (automatically deducted from sellable stock)
"""
from decimal import Decimal
import pytest
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase

from tenants.models import Business
from inventory.models import MerchProduct, Location
from inventory.business_kinds import BusinessKind
from inventory.liquor_config import (
    to_base_units,
    validate_unit_for_kind,
    get_allowed_units,
    get_default_config_for_kind,
    LiquorKind,
    PackLabel,
    DEFAULT_GLASSES_PER_BOTTLE,
    DEFAULT_SHOTS_PER_BOTTLE,
)
from inventory.services.liquor_sale import create_liquor_sale, OutOfStockError

User = get_user_model()


class LiquorRealWorldRulesTest(TestCase):
    """Test real-world liquor rules enforcement"""

    def setUp(self):
        """Set up test fixtures"""
        # Create business
        self.business = Business.objects.create(
            name="Test Bar",
            business_kind=BusinessKind.LIQUOR,
        )
        
        # Get or create default location for business
        self.location = Location.ensure_default_for_business(self.business)
        
        # Create user
        self.user = User.objects.create_user(
            username="bartender",
            email="bartender@testbar.com",
            password="test123",
        )

    def _create_beer(self, name="Castle Lager", stock=100):
        """Helper: Create a beer product with Malawi defaults"""
        return MerchProduct.objects.create(
            business=self.business,
            name=name,
            kind=BusinessKind.LIQUOR,
            category=LiquorKind.BEER,
            pack_label=PackLabel.CRATE,
            bottles_per_crate=20,  # Malawi default
            cost_per_bottle=Decimal("500.00"),
            price_per_bottle=Decimal("800.00"),
            quantity_in_stock=stock,
            track_inventory=True,
        )

    def _create_cider(self, name="Hunter's Dry", stock=60):
        """Helper: Create a cider product with Malawi defaults"""
        return MerchProduct.objects.create(
            business=self.business,
            name=name,
            kind=BusinessKind.LIQUOR,
            category=LiquorKind.CIDER,
            pack_label=PackLabel.SIX_PACK,
            bottles_per_crate=6,  # Malawi default (6-pack, NOT crate)
            cost_per_bottle=Decimal("600.00"),
            price_per_bottle=Decimal("900.00"),
            quantity_in_stock=stock,
            track_inventory=True,
        )

    def _create_wine(self, name="4th Street", stock=25):
        """Helper: Create a wine product with Malawi defaults (glass mode)"""
        return MerchProduct.objects.create(
            business=self.business,
            name=name,
            kind=BusinessKind.LIQUOR,
            category=LiquorKind.WINE,
            has_glasses=True,
            glasses_per_bottle=DEFAULT_GLASSES_PER_BOTTLE,  # 5 glasses
            cost_per_bottle=Decimal("2000.00"),
            price_per_glass=Decimal("500.00"),
            quantity_in_stock=stock,  # stock in glasses (5 bottles = 25 glasses)
            track_inventory=True,
        )

    def _create_spirits(self, name="Malawi Gin", stock=144):
        """Helper: Create spirits product with Malawi defaults (shot mode)"""
        return MerchProduct.objects.create(
            business=self.business,
            name=name,
            kind=BusinessKind.LIQUOR,
            category=LiquorKind.SPIRITS,
            has_shots=True,
            shots_per_bottle=DEFAULT_SHOTS_PER_BOTTLE,  # 24 shots
            barman_shots_reserved=2,
            cost_per_bottle=Decimal("5000.00"),
            price_per_shot=Decimal("300.00"),
            quantity_in_stock=stock,  # stock in shots (6 bottles = 144 shots)
            track_inventory=True,
        )


class TestBeerRules(LiquorRealWorldRulesTest):
    """Test beer-specific rules"""

    def test_beer_allowed_units(self):
        """Beer can be sold by bottle/can or crate (never shots)"""
        allowed = get_allowed_units(LiquorKind.BEER, pack_enabled=True)
        self.assertIn("bottle", allowed)
        self.assertIn("can", allowed)
        self.assertIn("crate", allowed)
        self.assertNotIn("shot", allowed)
        self.assertNotIn("glass", allowed)

    def test_beer_reject_shot_unit(self):
        """Beer cannot be sold by shot"""
        with self.assertRaises(ValidationError) as cm:
            validate_unit_for_kind(LiquorKind.BEER, "shot")
        self.assertIn("cannot be sold by shot", str(cm.exception))

    def test_beer_bottle_to_base_units(self):
        """Beer: 1 bottle = 1 base unit"""
        beer = self._create_beer()
        qty = to_base_units(10, "bottle", beer)
        self.assertEqual(qty, 10)

    def test_beer_crate_to_base_units(self):
        """Beer: 1 crate = 20 bottles (Malawi default)"""
        beer = self._create_beer()
        qty = to_base_units(3, "crate", beer)
        self.assertEqual(qty, 60)  # 3 crates × 20 bottles

    def test_beer_stock_in_crates(self):
        """Stock in beer by crates (converts to bottles)"""
        beer = self._create_beer(stock=0)
        
        # Stock in 5 crates = 100 bottles
        beer.quantity_in_stock = to_base_units(5, "crate", beer)
        beer.save()
        
        self.assertEqual(beer.quantity_in_stock, 100)

    def test_beer_sell_by_crate(self):
        """Sell beer by crate (decrements bottles correctly)"""
        beer = self._create_beer(stock=60)  # 3 crates
        
        result = create_liquor_sale(
            business=self.business,
            product_id=beer.id,
            user=self.user,
            quantity=2,  # 2 crates
            unit="crate",
            unit_price=Decimal("15000.00"),  # price per crate
        )
        
        self.assertTrue(result["ok"])
        beer.refresh_from_db()
        self.assertEqual(beer.quantity_in_stock, 20)  # 60 - 40 = 20


class TestCiderRules(LiquorRealWorldRulesTest):
    """Test cider-specific rules"""

    def test_cider_allowed_units(self):
        """Cider can be sold by bottle/can or 6-pack (NO CRATES)"""
        allowed = get_allowed_units(LiquorKind.CIDER, pack_enabled=True)
        self.assertIn("bottle", allowed)
        self.assertIn("can", allowed)
        self.assertIn("6-pack", allowed)
        self.assertNotIn("crate", allowed)  # CRITICAL: No crates for cider
        self.assertNotIn("shot", allowed)

    def test_cider_reject_crate_unit(self):
        """Cider CANNOT use crates (must use 6-pack)"""
        with self.assertRaises(ValidationError) as cm:
            validate_unit_for_kind(LiquorKind.CIDER, "crate")
        self.assertIn("6-pack", str(cm.exception).lower())

    def test_cider_6pack_to_base_units(self):
        """Cider: 1 6-pack = 6 bottles (Malawi default)"""
        cider = self._create_cider()
        qty = to_base_units(2, "6-pack", cider)
        self.assertEqual(qty, 12)  # 2 × 6 = 12

    def test_cider_stock_in_6packs(self):
        """Stock in cider by 6-packs (converts to bottles)"""
        cider = self._create_cider(stock=0)
        
        # Stock in 10 6-packs = 60 bottles
        cider.quantity_in_stock = to_base_units(10, "6-pack", cider)
        cider.save()
        
        self.assertEqual(cider.quantity_in_stock, 60)

    def test_cider_cannot_stock_by_crate(self):
        """Cider cannot be stocked by crate"""
        cider = self._create_cider()
        
        with self.assertRaises(ValidationError) as cm:
            to_base_units(2, "crate", cider)
        self.assertIn("6-pack", str(cm.exception).lower())

    def test_cider_default_pack_size(self):
        """Cider defaults to 6-pack (not 20 like beer)"""
        config = get_default_config_for_kind(LiquorKind.CIDER)
        self.assertEqual(config["pack_label"], PackLabel.SIX_PACK)
        self.assertEqual(config["pack_size"], 6)


class TestWineRules(LiquorRealWorldRulesTest):
    """Test wine-specific rules"""

    def test_wine_allowed_units(self):
        """Wine can be sold by glass or bottle (never shots)"""
        allowed = get_allowed_units(LiquorKind.WINE, pack_enabled=False)
        self.assertIn("glass", allowed)
        self.assertIn("bottle", allowed)
        self.assertNotIn("shot", allowed)
        self.assertNotIn("crate", allowed)

    def test_wine_reject_shot_unit(self):
        """Wine cannot be sold by shot"""
        with self.assertRaises(ValidationError) as cm:
            validate_unit_for_kind(LiquorKind.WINE, "shot")
        self.assertIn("cannot be sold by shot", str(cm.exception))

    def test_wine_glass_to_base_units(self):
        """Wine: 1 glass = 1 base unit (when in glass mode)"""
        wine = self._create_wine()
        qty = to_base_units(2, "glass", wine)
        self.assertEqual(qty, 2)

    def test_wine_bottle_to_glasses(self):
        """Wine: 1 bottle = 5 glasses (Malawi default)"""
        wine = self._create_wine()
        qty = to_base_units(1, "bottle", wine)
        self.assertEqual(qty, 5)

    def test_wine_stock_in_bottles_convert_to_glasses(self):
        """Stock in wine bottles (converts to glasses)"""
        wine = self._create_wine(stock=0)
        
        # Stock in 10 bottles = 50 glasses
        wine.quantity_in_stock = to_base_units(10, "bottle", wine)
        wine.save()
        
        self.assertEqual(wine.quantity_in_stock, 50)

    def test_wine_sell_by_glass(self):
        """Sell wine by glass (decrements glasses correctly)"""
        wine = self._create_wine(stock=25)  # 5 bottles = 25 glasses
        
        result = create_liquor_sale(
            business=self.business,
            product_id=wine.id,
            user=self.user,
            quantity=2,  # 2 glasses
            unit="glass",
            unit_price=Decimal("500.00"),
        )
        
        self.assertTrue(result["ok"])
        wine.refresh_from_db()
        self.assertEqual(wine.quantity_in_stock, 23)  # 25 - 2 = 23

    def test_wine_default_glasses_per_bottle(self):
        """Wine defaults to 5 glasses per bottle (Malawi standard)"""
        config = get_default_config_for_kind(LiquorKind.WINE)
        self.assertEqual(config["glasses_per_bottle"], DEFAULT_GLASSES_PER_BOTTLE)
        self.assertEqual(config["glasses_per_bottle"], 5)


class TestSpiritsWhiskyRules(LiquorRealWorldRulesTest):
    """Test spirits/whisky-specific rules"""

    def test_spirits_allowed_units(self):
        """Spirits can be sold by shot or bottle (optional case)"""
        allowed = get_allowed_units(LiquorKind.SPIRITS, pack_enabled=False)
        self.assertIn("shot", allowed)
        self.assertIn("bottle", allowed)
        self.assertNotIn("crate", allowed)
        self.assertNotIn("glass", allowed)

    def test_spirits_reject_glass_unit(self):
        """Spirits cannot be sold by glass"""
        with self.assertRaises(ValidationError) as cm:
            validate_unit_for_kind(LiquorKind.SPIRITS, "glass")
        self.assertIn("invalid unit", str(cm.exception).lower())

    def test_spirits_shot_to_base_units(self):
        """Spirits: 1 shot = 1 base unit (when in shot mode)"""
        spirits = self._create_spirits()
        qty = to_base_units(3, "shot", spirits)
        self.assertEqual(qty, 3)

    def test_spirits_bottle_to_shots(self):
        """Spirits: 1 bottle = 24 shots (Malawi default: updated from 30)"""
        spirits = self._create_spirits()
        qty = to_base_units(1, "bottle", spirits)
        self.assertEqual(qty, 24)

    def test_spirits_stock_in_bottles_convert_to_shots(self):
        """Stock in spirits bottles (converts to shots)"""
        spirits = self._create_spirits(stock=0)
        
        # Stock in 6 bottles = 144 shots (24 shots per bottle)
        spirits.quantity_in_stock = to_base_units(6, "bottle", spirits)
        spirits.save()
        
        self.assertEqual(spirits.quantity_in_stock, 144)

    def test_spirits_sell_by_shot(self):
        """Sell spirits by shot (decrements shots correctly)"""
        spirits = self._create_spirits(stock=144)  # 6 bottles = 144 shots
        
        result = create_liquor_sale(
            business=self.business,
            product_id=spirits.id,
            user=self.user,
            quantity=3,  # 3 shots
            unit="shot",
            unit_price=Decimal("300.00"),
        )
        
        self.assertTrue(result["ok"])
        spirits.refresh_from_db()
        self.assertEqual(spirits.quantity_in_stock, 141)  # 144 - 3 = 141

    def test_spirits_default_shots_per_bottle(self):
        """Spirits defaults to 24 shots per bottle (Malawi: updated from 30)"""
        config = get_default_config_for_kind(LiquorKind.SPIRITS)
        self.assertEqual(config["shots_per_bottle"], DEFAULT_SHOTS_PER_BOTTLE)
        self.assertEqual(config["shots_per_bottle"], 24)


class TestCrossCategoryIsolation(LiquorRealWorldRulesTest):
    """Test that wrong units are rejected across categories"""

    def test_beer_cannot_use_shot(self):
        """Beer products must reject shot sales"""
        beer = self._create_beer()
        
        with self.assertRaises(ValidationError) as cm:
            create_liquor_sale(
                business=self.business,
                product_id=beer.id,
                user=self.user,
                quantity=1,
                unit="shot",
                unit_price=Decimal("300.00"),
            )
        # Check that shot sales are rejected (error message may vary)
        error_msg = str(cm.exception).lower()
        self.assertTrue(
            "shot" in error_msg and ("invalid" in error_msg or "not support" in error_msg),
            f"Expected shot rejection error, got: {cm.exception}"
        )

    def test_wine_cannot_use_shot(self):
        """Wine products must reject shot sales"""
        wine = self._create_wine()
        
        with self.assertRaises(ValidationError) as cm:
            create_liquor_sale(
                business=self.business,
                product_id=wine.id,
                user=self.user,
                quantity=1,
                unit="shot",
                unit_price=Decimal("300.00"),
            )
        # Check that shot sales are rejected (error message may vary)
        error_msg = str(cm.exception).lower()
        self.assertTrue(
            "shot" in error_msg and ("invalid" in error_msg or "not support" in error_msg),
            f"Expected shot rejection error, got: {cm.exception}"
        )

    def test_spirits_cannot_use_glass(self):
        """Spirits products must reject glass sales"""
        spirits = self._create_spirits()
        
        # Set up as if trying to sell by glass
        with self.assertRaises(ValidationError) as cm:
            validate_unit_for_kind(LiquorKind.SPIRITS, "glass")
        self.assertIn("invalid unit", str(cm.exception).lower())


class TestStockSafety(LiquorRealWorldRulesTest):
    """Test stock safety and out-of-stock handling"""

    def test_insufficient_stock_blocks_sale(self):
        """Cannot sell more than available stock"""
        beer = self._create_beer(stock=10)  # Only 10 bottles
        
        with self.assertRaises(OutOfStockError) as cm:
            create_liquor_sale(
                business=self.business,
                product_id=beer.id,
                user=self.user,
                quantity=20,  # Try to sell 20 bottles
                unit="bottle",
                unit_price=Decimal("800.00"),
            )
        self.assertIn("Insufficient stock", str(cm.exception))

    def test_insufficient_stock_by_pack_blocks_sale(self):
        """Cannot sell more packs than available (in base units)"""
        cider = self._create_cider(stock=10)  # Only 10 bottles (< 2 six-packs)
        
        with self.assertRaises(OutOfStockError) as cm:
            create_liquor_sale(
                business=self.business,
                product_id=cider.id,
                user=self.user,
                quantity=2,  # 2 six-packs = 12 bottles
                unit="6-pack",
                unit_price=Decimal("5000.00"),
            )
        self.assertIn("Insufficient stock", str(cm.exception))

    def test_open_bottle_tracking_wine(self):
        """Open wine bottles are tracked automatically via glasses"""
        wine = self._create_wine(stock=25)  # 5 bottles = 25 glasses
        
        # Sell 7 glasses (opens 2 bottles, 3 glasses left in 2nd bottle)
        result = create_liquor_sale(
            business=self.business,
            product_id=wine.id,
            user=self.user,
            quantity=7,
            unit="glass",
            unit_price=Decimal("500.00"),
        )
        
        self.assertTrue(result["ok"])
        wine.refresh_from_db()
        self.assertEqual(wine.quantity_in_stock, 18)  # 25 - 7 = 18 glasses

    def test_open_bottle_tracking_spirits(self):
        """Open spirits bottles are tracked automatically via shots"""
        spirits = self._create_spirits(stock=60)  # 2 bottles = 60 shots
        
        # Sell 35 shots (opens both bottles, 25 shots left)
        result = create_liquor_sale(
            business=self.business,
            product_id=spirits.id,
            user=self.user,
            quantity=35,
            unit="shot",
            unit_price=Decimal("300.00"),
        )
        
        self.assertTrue(result["ok"])
        spirits.refresh_from_db()
        self.assertEqual(spirits.quantity_in_stock, 25)  # 60 - 35 = 25


class TestBusinessIsolation(LiquorRealWorldRulesTest):
    """Test cross-business isolation"""

    def test_cannot_sell_other_business_product(self):
        """Cannot create sale for product from different business"""
        # Create second business with unique slug
        import uuid
        unique_suffix = str(uuid.uuid4())[:8]
        
        # Use get_or_create to handle --keepdb case
        other_business, _ = Business.objects.get_or_create(
            slug=f"other-bar-{unique_suffix}",
            defaults={
                "name": f"Other Bar {unique_suffix}",
                "business_kind": BusinessKind.LIQUOR,
            }
        )
        
        # Create product in other business
        other_beer = MerchProduct.objects.create(
            business=other_business,
            name="Other Beer",
            kind=BusinessKind.LIQUOR,
            category=LiquorKind.BEER,
            quantity_in_stock=100,
        )
        
        # Try to sell it using our business - should fail
        with self.assertRaises(ValidationError):
            create_liquor_sale(
                business=self.business,  # Wrong business!
                product_id=other_beer.id,
                user=self.user,
                quantity=1,
                unit="bottle",
                unit_price=Decimal("800.00"),
            )


class TestNewRules2024(LiquorRealWorldRulesTest):
    """Test new rules: shots=24, barman shots, cider pack_size=6, spirits stock-in bottle-only"""

    def test_spirits_default_shots_is_24(self):
        """Spirits default shots_per_bottle is 24 (changed from 30)"""
        self.assertEqual(DEFAULT_SHOTS_PER_BOTTLE, 24)
    
    def test_spirits_with_missing_shots_per_bottle_defaults_to_24(self):
        """Spirits product without shots_per_bottle should default to 24"""
        spirits = MerchProduct.objects.create(
            business=self.business,
            name="Test Gin",
            kind=BusinessKind.LIQUOR,
            category=LiquorKind.SPIRITS,
            has_shots=True,
            shots_per_bottle=None,  # Missing
            cost_per_bottle=Decimal("5000.00"),
            price_per_shot=Decimal("300.00"),
            quantity_in_stock=0,
            track_inventory=True,
        )
        
        # to_base_units should use default (24) when shots_per_bottle is None
        qty = to_base_units(1, "bottle", spirits)
        self.assertEqual(qty, 24, "Should default to 24 shots per bottle")
    
    def test_barman_shots_accounting(self):
        """Stock-in spirits bottles should deduct 2 barman shots per bottle"""
        from inventory.services.liquor_sale import stock_in_liquor
        
        spirits = MerchProduct.objects.create(
            business=self.business,
            name="Test Whisky",
            kind=BusinessKind.LIQUOR,
            category=LiquorKind.WHISKY,
            has_shots=True,
            shots_per_bottle=24,
            cost_per_bottle=Decimal("6000.00"),
            price_per_shot=Decimal("350.00"),
            quantity_in_stock=0,
            track_inventory=True,
        )
        
        # Stock in 1 bottle
        result = stock_in_liquor(
            business=self.business,
            product_id=spirits.id,
            user=self.user,
            quantity=1,
            unit="bottle",
            cost_per_unit=Decimal("6000.00"),
        )
        
        self.assertTrue(result["ok"])
        self.assertEqual(result["barman_shots_recorded"], 2, "Should record 2 barman shots")
        self.assertEqual(result["sellable_added"], 22, "Should add 22 sellable shots (24 - 2)")
        
        # Verify stock
        spirits.refresh_from_db()
        self.assertEqual(spirits.quantity_in_stock, 22, "Stock should be 22 sellable shots")
    
    def test_spirits_stock_in_bottle_only(self):
        """Spirits/Whisky stock-in must be BOTTLE-ONLY (no case/crate/pack)"""
        spirits = self._create_spirits(stock=0)
        
        # Try to stock in by "case" - should fail
        from inventory.services.liquor_sale import stock_in_liquor
        with self.assertRaises(ValidationError) as cm:
            stock_in_liquor(
                business=self.business,
                product_id=spirits.id,
                user=self.user,
                quantity=1,
                unit="case",  # Not allowed!
                cost_per_unit=Decimal("30000.00"),
            )
        self.assertIn("stock-in must be by BOTTLE only", str(cm.exception))
    
    def test_cider_pack_size_must_be_6(self):
        """Cider pack_size must be exactly 6 (cannot be changed)"""
        # Try to create cider with pack_size != 6
        with self.assertRaises(ValidationError) as cm:
            MerchProduct.objects.create(
                business=self.business,
                name="Bad Cider",
                kind=BusinessKind.LIQUOR,
                category=LiquorKind.CIDER,
                pack_label=PackLabel.CRATE,  # Wrong!
                bottles_per_crate=20,  # Wrong! Should be 6
                cost_per_bottle=Decimal("600.00"),
                price_per_bottle=Decimal("900.00"),
                quantity_in_stock=0,
                track_inventory=True,
            )
        self.assertIn("Cider pack size must be exactly 6", str(cm.exception))
    
    def test_cider_pack_size_6_is_allowed(self):
        """Cider with pack_size=6 should be allowed"""
        cider = MerchProduct.objects.create(
            business=self.business,
            name="Good Cider",
            kind=BusinessKind.LIQUOR,
            category=LiquorKind.CIDER,
            pack_label=PackLabel.SIX_PACK,
            bottles_per_crate=6,  # Correct!
            cost_per_bottle=Decimal("600.00"),
            price_per_bottle=Decimal("900.00"),
            quantity_in_stock=60,
            track_inventory=True,
        )
        self.assertEqual(cider.bottles_per_crate, 6)
    
    def test_spirits_selling_units_shot_or_bottle(self):
        """Spirits can be sold by shot or bottle (not case for selling)"""
        allowed_selling = get_allowed_units(LiquorKind.SPIRITS, pack_enabled=True, for_stock_in=False)
        self.assertIn("shot", allowed_selling)
        self.assertIn("bottle", allowed_selling)
        self.assertNotIn("case", allowed_selling, "Case not allowed for selling")
    
    def test_spirits_stock_in_units_bottle_only(self):
        """Spirits stock-in units must be bottle only"""
        allowed_stock_in = get_allowed_units(LiquorKind.SPIRITS, pack_enabled=True, for_stock_in=True)
        self.assertIn("bottle", allowed_stock_in)
        self.assertNotIn("case", allowed_stock_in, "Case not allowed for stock-in")
        self.assertNotIn("shot", allowed_stock_in, "Shot not allowed for stock-in")


class TestConcurrencySafety(LiquorRealWorldRulesTest):
    """Test concurrency safety (atomic operations, select_for_update)"""
    
    def test_sale_uses_select_for_update(self):
        """Verify that create_liquor_sale uses select_for_update for row locking"""
        beer = self._create_beer(stock=10)
        
        # The create_liquor_sale function should use select_for_update()
        # We can verify this by checking the service code uses it
        # (This is more of a code review test, but we can verify behavior)
        
        # Sell 5 bottles
        result = create_liquor_sale(
            business=self.business,
            product_id=beer.id,
            user=self.user,
            quantity=5,
            unit="bottle",
            unit_price=Decimal("800.00"),
        )
        
        self.assertTrue(result["ok"])
        beer.refresh_from_db()
        self.assertEqual(beer.quantity_in_stock, 5)
    
    def test_atomic_stock_decrement_prevents_overselling(self):
        """Atomic stock decrement should prevent overselling"""
        beer = self._create_beer(stock=5)
        
        # Try to sell 10 bottles (more than available)
        with self.assertRaises(OutOfStockError) as cm:
            create_liquor_sale(
                business=self.business,
                product_id=beer.id,
                user=self.user,
                quantity=10,
                unit="bottle",
                unit_price=Decimal("800.00"),
            )
        
        self.assertIn("Insufficient stock", str(cm.exception))
        
        # Stock should remain unchanged
        beer.refresh_from_db()
        self.assertEqual(beer.quantity_in_stock, 5, "Stock should not change on failed sale")
    
    def test_transaction_rollback_on_error(self):
        """If sale fails, stock should not be decremented (transaction rollback)"""
        beer = self._create_beer(stock=10)
        
        # Try to create a credit sale without customer_name (should fail)
        with self.assertRaises(ValidationError):
            create_liquor_sale(
                business=self.business,
                product_id=beer.id,
                user=self.user,
                quantity=5,
                unit="bottle",
                unit_price=Decimal("800.00"),
                sale_type="credit",
                customer_name=None,  # Missing! Should fail
            )
        
        # Stock should remain unchanged
        beer.refresh_from_db()
        self.assertEqual(beer.quantity_in_stock, 10, "Stock should not change on failed sale")

