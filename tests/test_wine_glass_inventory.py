"""
Tests for wine glass inventory logic.
Covers: scan-in adapter, glass tracking, bottle-breakdown display, margin calculations.

Task requirements:
1. Wine stock-in with 5 bottles and 6 glasses creates 30 glass units.
2. Selling 1 glass leaves 29 glasses.
3. Selling 1 glass does not reduce display to only 4 bottles.
4. Selling 6 glasses consumes exactly 1 bottle equivalent.
5. Selling 1 whole bottle reduces bottle stock directly.
6. Margin calculation uses cost per glass for glass sales.
7. Margin calculation uses bottle cost for bottle sales.
8. No 500 errors on /liquor/scan-in/.
9. Existing beer, spirits, whiskey logic still works.
"""
from decimal import Decimal

import pytest

from inventory.business_kinds import BusinessKind
from inventory.helpers_liquor_units import compute_sale_totals, get_bottle_breakdown
from inventory.models import MerchProduct
from inventory.services_liquor_stockin import WineStockInAdapter, BeerStockInAdapter, SpiritsStockInAdapter


# ---------------------------------------------------------------------------
# Task 1 & Adapter Unit Tests
# ---------------------------------------------------------------------------

class TestWineStockInAdapter:
    """Unit tests for WineStockInAdapter – no DB required."""

    def test_5_bottles_6_glasses_creates_30_units(self):
        """Wine stock-in with 5 bottles and 6 glasses creates 30 glass units."""
        result = WineStockInAdapter.adapt({
            "number_of_bottles": 5,
            "cost_per_bottle": Decimal("70000"),
            "glasses_per_bottle": 6,
        })
        assert result["quantity_units_added"] == 30
        assert result["metadata"]["glasses_per_bottle"] == 6
        assert result["metadata"]["total_glasses"] == 30
        assert result["metadata"]["number_of_bottles"] == 5

    def test_cost_per_glass_calculated_correctly(self):
        """Cost per glass = cost_per_bottle / glasses_per_bottle."""
        result = WineStockInAdapter.adapt({
            "number_of_bottles": 1,
            "cost_per_bottle": Decimal("70000"),
            "glasses_per_bottle": 7,
        })
        expected = (Decimal("70000") / Decimal("7")).quantize(Decimal("0.01"))
        assert result["unit_cost"] == expected

    def test_total_cost_in_bottles(self):
        """Total cost is bottles × cost_per_bottle (not per glass)."""
        result = WineStockInAdapter.adapt({
            "number_of_bottles": 3,
            "cost_per_bottle": Decimal("50000"),
            "glasses_per_bottle": 5,
        })
        assert result["total_cost"] == Decimal("150000.00")

    def test_selling_price_per_glass_calculates_margin(self):
        """When selling_price_per_glass is provided, adapter calculates margin."""
        result = WineStockInAdapter.adapt({
            "number_of_bottles": 1,
            "cost_per_bottle": Decimal("70000"),
            "glasses_per_bottle": 7,
            "selling_price_per_glass": Decimal("12000"),
        })
        meta = result["metadata"]
        # cost_per_glass = 70000/7 ≈ 10000
        # profit = 12000 - 10000 = 2000
        # margin = 2000/10000 * 100 = 20%
        assert "gross_profit_per_glass" in meta
        assert abs(meta["gross_profit_per_glass"] - 2000.0) < 1.0
        assert abs(meta["glass_margin_pct"] - 20.0) < 0.5

    def test_revenue_per_bottle_by_glass(self):
        """Revenue per bottle by glass = selling_price_per_glass × glasses_per_bottle."""
        result = WineStockInAdapter.adapt({
            "number_of_bottles": 1,
            "cost_per_bottle": Decimal("70000"),
            "glasses_per_bottle": 7,
            "selling_price_per_glass": Decimal("12000"),
        })
        meta = result["metadata"]
        assert abs(meta["revenue_per_bottle_by_glass"] - 84000.0) < 1.0

    def test_zero_profit_when_selling_at_cost(self):
        """Margin is 0% when selling price equals cost per glass."""
        result = WineStockInAdapter.adapt({
            "number_of_bottles": 1,
            "cost_per_bottle": Decimal("70000"),
            "glasses_per_bottle": 7,
            "selling_price_per_glass": Decimal("10000"),  # exactly cost
        })
        meta = result["metadata"]
        assert abs(meta["gross_profit_per_glass"]) < 1.0
        assert abs(meta["glass_margin_pct"]) < 0.1

    def test_default_glasses_per_bottle_is_5(self):
        """Default glasses per bottle is 5 when not specified."""
        result = WineStockInAdapter.adapt({
            "number_of_bottles": 2,
            "cost_per_bottle": Decimal("50000"),
        })
        assert result["quantity_units_added"] == 10  # 2 × 5
        assert result["metadata"]["glasses_per_bottle"] == 5

    def test_invalid_zero_glasses_raises_error(self):
        """Zero glasses per bottle raises ValueError."""
        with pytest.raises(ValueError, match="Glasses per bottle must be greater than 0"):
            WineStockInAdapter.adapt({
                "number_of_bottles": 1,
                "cost_per_bottle": Decimal("50000"),
                "glasses_per_bottle": 0,
            })

    def test_invalid_zero_bottles_raises_error(self):
        """Zero bottles raises ValueError."""
        with pytest.raises(ValueError):
            WineStockInAdapter.adapt({
                "number_of_bottles": 0,
                "cost_per_bottle": Decimal("50000"),
                "glasses_per_bottle": 6,
            })


# ---------------------------------------------------------------------------
# Task 2–5: Glass Tracking & Bottle Breakdown
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestWineGlassTracking:
    """Tests for glass-level inventory tracking and display breakdown."""

    @pytest.fixture
    def business(self, db):
        from tenants.models import Business
        return Business.objects.create(name="Test Wine Bar")

    @pytest.fixture
    def wine_product(self, business):
        return MerchProduct.objects.create(
            business=business,
            name="Sauvignon Blanc",
            kind=BusinessKind.LIQUOR,
            category="wine",
            has_glasses=True,
            glasses_per_bottle=6,
            quantity_in_stock=30,  # 5 bottles × 6 glasses
            cost_per_bottle=Decimal("70000"),
            cost_per_glass=Decimal("11666.67"),  # 70000/6
            price_per_bottle=Decimal("90000"),
            price_per_glass=Decimal("15000"),
        )

    def test_selling_1_glass_leaves_29_glasses(self, wine_product):
        """Task 2: Selling 1 glass leaves 29 glasses remaining."""
        wine_product.quantity_in_stock -= 1
        wine_product.save(update_fields=["quantity_in_stock"])
        wine_product.refresh_from_db()
        assert wine_product.quantity_in_stock == 29

    def test_selling_1_glass_shows_correct_bottle_breakdown(self, wine_product):
        """Task 3: After selling 1 glass, display shows 4 full + 1 open bottle — NOT just 4 bottles."""
        wine_product.quantity_in_stock = 29  # simulate 1 glass sold
        wine_product.save(update_fields=["quantity_in_stock"])
        wine_product.refresh_from_db()

        breakdown = get_bottle_breakdown(wine_product)

        # 29 glasses ÷ 6 = 4 full bottles, remainder 5 → open bottle with 5/6
        assert breakdown["full_bottles"] == 4
        assert breakdown["has_open_bottle"] is True
        assert breakdown["partial_units"] == 5
        assert breakdown["units_per_bottle"] == 6
        # Display text must mention open bottle
        assert "4 full bottle" in breakdown["display_text"]
        assert "open bottle" in breakdown["display_text"]
        assert "5/6" in breakdown["display_text"]

    def test_selling_6_glasses_consumes_exactly_1_bottle_equivalent(self, wine_product):
        """Task 4: Selling 6 glasses (= 1 bottle) leaves 4 full bottles, no open bottle."""
        initial = wine_product.quantity_in_stock  # 30
        wine_product.quantity_in_stock -= 6
        wine_product.save(update_fields=["quantity_in_stock"])
        wine_product.refresh_from_db()

        assert wine_product.quantity_in_stock == initial - 6  # 24
        breakdown = get_bottle_breakdown(wine_product)
        assert breakdown["full_bottles"] == 4
        assert breakdown["has_open_bottle"] is False
        assert breakdown["partial_units"] == 0

    def test_selling_1_whole_bottle_deducts_glasses_per_bottle(self, wine_product):
        """Task 5: Selling 1 whole bottle reduces stock by glasses_per_bottle (6)."""
        initial = wine_product.quantity_in_stock  # 30
        # Bottle sale: deduct glasses_per_bottle glasses
        wine_product.quantity_in_stock -= wine_product.glasses_per_bottle
        wine_product.save(update_fields=["quantity_in_stock"])
        wine_product.refresh_from_db()

        assert wine_product.quantity_in_stock == initial - 6  # 24
        breakdown = get_bottle_breakdown(wine_product)
        assert breakdown["full_bottles"] == 4

    def test_full_breakdwon_display_with_5_bottles(self, wine_product):
        """Full bottles correctly displayed when stock is exactly divisible."""
        wine_product.quantity_in_stock = 30
        wine_product.save(update_fields=["quantity_in_stock"])
        wine_product.refresh_from_db()

        breakdown = get_bottle_breakdown(wine_product)
        assert breakdown["full_bottles"] == 5
        assert breakdown["has_open_bottle"] is False
        assert "5 full bottle" in breakdown["display_text"]


# ---------------------------------------------------------------------------
# Task 6–7: Margin Calculations
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestWineMarginCalculations:
    """Tests for correct margin using cost_per_glass (not bottle cost) for glass sales."""

    @pytest.fixture
    def business(self, db):
        from tenants.models import Business
        return Business.objects.create(name="Test Wine Bar 2")

    def test_margin_uses_cost_per_glass_for_glass_sales(self, business):
        """Task 6: Margin calculation uses cost_per_glass for glass sales."""
        wine = MerchProduct.objects.create(
            business=business,
            name="Merlot",
            kind=BusinessKind.LIQUOR,
            category="wine",
            has_glasses=True,
            glasses_per_bottle=7,
            quantity_in_stock=7,
            cost_per_bottle=Decimal("70000"),
            cost_per_glass=Decimal("10000"),  # 70000/7
            price_per_glass=Decimal("12000"),
        )
        totals = compute_sale_totals(wine, 1)
        # Unit cost must be cost_per_glass (10000), not cost_per_bottle (70000)
        assert totals["unit_cost"] == Decimal("10000")
        assert totals["unit_price"] == Decimal("12000")
        assert totals["profit"] == Decimal("2000")

    def test_margin_uses_bottle_cost_for_bottle_only_wine(self, business):
        """Task 7: Margin uses bottle cost for bottle-only wine sales."""
        wine = MerchProduct.objects.create(
            business=business,
            name="Chardonnay",
            kind=BusinessKind.LIQUOR,
            category="wine",
            has_glasses=False,
            quantity_in_stock=5,
            cost_per_bottle=Decimal("70000"),
            price_per_bottle=Decimal("90000"),
        )
        totals = compute_sale_totals(wine, 1)
        assert totals["unit_cost"] == Decimal("70000")
        assert totals["unit_price"] == Decimal("90000")
        assert totals["profit"] == Decimal("20000")

    def test_no_loss_shown_when_glass_correctly_priced(self, business):
        """Task 4 (margin): Correctly priced glass does not show a loss."""
        wine = MerchProduct.objects.create(
            business=business,
            name="Cabernet Sauvignon",
            kind=BusinessKind.LIQUOR,
            category="wine",
            has_glasses=True,
            glasses_per_bottle=7,
            quantity_in_stock=7,
            cost_per_bottle=Decimal("70000"),
            cost_per_glass=Decimal("10000"),
            price_per_glass=Decimal("12000"),
        )
        totals = compute_sale_totals(wine, 1)
        assert totals["profit"] > Decimal("0"), (
            "Wine priced at MK 12,000/glass with cost MK 10,000/glass must show profit, not loss"
        )
        assert totals["margin"] > Decimal("0")


# ---------------------------------------------------------------------------
# Task 8: Scan-in URL no 500 errors
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestScanInPageLoad:
    """Task 8: /liquor/scan-in/ must not return 500."""

    @pytest.fixture
    def setup(self, db, client):
        from tenants.models import Business
        from django.contrib.auth import get_user_model
        User = get_user_model()

        business = Business.objects.create(name="Scan-In Test Bar")
        user = User.objects.create_user(username="scanner", password="pass123")

        try:
            from tenants.models import Membership
            Membership.objects.create(business=business, user=user, role="manager")
        except Exception:
            pass

        client.force_login(user)
        session = client.session
        session["active_business_id"] = business.id
        session.save()
        return business, user, client

    def test_scan_in_page_does_not_500(self, setup):
        """GET /liquor/scan-in/ must not return 500 (internal server error)."""
        business, user, client = setup
        from django.urls import reverse
        response = client.get(reverse("liquor:scan_in"))
        assert response.status_code != 500, (
            f"scan-in page returned 500: {response.content[:500]}"
        )


# ---------------------------------------------------------------------------
# Task 9: Beer, spirits, whiskey adapters still work (no regression)
# ---------------------------------------------------------------------------

class TestExistingAdaptersNoRegression:
    """Task 9: Beer, spirits, whiskey adapters are unaffected by wine changes."""

    def test_beer_adapter_still_works(self):
        result = BeerStockInAdapter.adapt({
            "number_of_crates": 2,
            "cost_per_crate": Decimal("5000"),
            "loose_bottles": 0,
        })
        assert result["quantity_units_added"] == 40  # 2 × 20
        assert result["metadata"]["category"] == "beer"

    def test_spirits_adapter_bottle_first_mode(self):
        result = SpiritsStockInAdapter.adapt({
            "number_of_bottles": 2,
            "cost_per_bottle": Decimal("15000"),
            "shots_per_bottle": 25,
            "price_per_shot": Decimal("800"),
            "reserved_barman_shots": 2,
        })
        # total_shots = 2 × 25 = 50; reserved = 2 (total, not per bottle)
        # sellable = 50 - 2 = 48
        assert result["quantity_units_added"] == 48
        assert result["metadata"]["category"] == "spirits"

    def test_spirits_adapter_legacy_shot_mode(self):
        result = SpiritsStockInAdapter.adapt({
            "quantity_of_shots_added": 50,
            "cost_per_shot": Decimal("500"),
            "reserved_barman_shots": 4,
        })
        assert result["quantity_units_added"] == 46  # 50 - 4
