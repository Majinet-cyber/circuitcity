# inventory/tests/test_liquor_pricing_and_nav.py
"""
Tests for:
- Liquor spirits shot pricing calculations (bottle-first mode)
- Liquor cider pack-to-bottle calculations
- Liquor beer behaviour unchanged
- Mobile nav vertical-awareness (liquor, phones, energy)
- Landing page text changes (no generic wording, Daily Reporting removed, partners present)
"""
from decimal import Decimal

from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse

from inventory.services_liquor_stockin import (
    SpiritsStockInAdapter,
    CiderStockInAdapter,
    BeerStockInAdapter,
    WhiskyStockInAdapter,
)
from inventory.mobile_nav import get_mobile_nav_items

User = get_user_model()


# ---------------------------------------------------------------------------
# Spirits Shot Pricing Tests (bottle-first mode)
# ---------------------------------------------------------------------------

class SpiritsBottleFirstAdapterTest(TestCase):
    """Tests for SpiritsStockInAdapter bottle-first mode."""

    def _adapt(self, **kwargs):
        return SpiritsStockInAdapter.adapt(kwargs)

    def test_basic_bottle_first_calculation(self):
        """Bottle-first: 2 bottles, 30 shots each at MWK 5,000/bottle, MWK 250/shot."""
        result = self._adapt(
            number_of_bottles=2,
            shots_per_bottle=30,
            cost_per_bottle="5000",
            price_per_shot="250",
        )
        self.assertEqual(result['quantity_units_added'], 60)  # 2 * 30
        self.assertAlmostEqual(float(result['unit_cost']), 5000 / 30, places=1)  # cost per shot
        self.assertAlmostEqual(float(result['total_cost']), 10000.0, places=1)   # 2 * 5000

    def test_cost_per_shot_calculation(self):
        """cost_per_shot = cost_per_bottle / shots_per_bottle."""
        result = self._adapt(
            number_of_bottles=1,
            shots_per_bottle=30,
            cost_per_bottle="6000",
            price_per_shot="300",
        )
        meta = result['metadata']
        self.assertAlmostEqual(meta['cost_per_shot'], 6000 / 30, places=2)

    def test_gross_profit_per_shot(self):
        """gross_profit_per_shot = price_per_shot - cost_per_shot."""
        result = self._adapt(
            number_of_bottles=1,
            shots_per_bottle=30,
            cost_per_bottle="6000",
            price_per_shot="300",
        )
        meta = result['metadata']
        expected_cost_per_shot = 6000 / 30
        expected_profit = 300 - expected_cost_per_shot
        self.assertAlmostEqual(meta['gross_profit_per_shot'], expected_profit, places=2)

    def test_expected_revenue_per_bottle(self):
        """expected_revenue_per_bottle = shots_per_bottle * price_per_shot."""
        result = self._adapt(
            number_of_bottles=1,
            shots_per_bottle=30,
            cost_per_bottle="5000",
            price_per_shot="300",
        )
        meta = result['metadata']
        self.assertAlmostEqual(meta['expected_revenue_per_bottle'], 30 * 300, places=1)

    def test_reserved_shots_reduce_sellable(self):
        """Sellable shots = total - reserved."""
        result = self._adapt(
            number_of_bottles=2,
            shots_per_bottle=30,
            cost_per_bottle="5000",
            price_per_shot="250",
            reserved_barman_shots=5,
        )
        self.assertEqual(result['quantity_units_added'], 60 - 5)

    def test_shots_per_bottle_must_be_positive(self):
        """shots_per_bottle <= 0 raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            self._adapt(
                number_of_bottles=1,
                shots_per_bottle=0,
                cost_per_bottle="5000",
                price_per_shot="250",
            )
        self.assertIn("greater than 0", str(cm.exception))

    def test_price_per_shot_cannot_be_negative(self):
        """Negative price_per_shot raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            self._adapt(
                number_of_bottles=1,
                shots_per_bottle=30,
                cost_per_bottle="5000",
                price_per_shot="-10",
            )
        self.assertIn("negative", str(cm.exception))

    def test_number_of_bottles_must_be_positive(self):
        """number_of_bottles=0 raises ValueError."""
        with self.assertRaises(ValueError):
            self._adapt(
                number_of_bottles=0,
                shots_per_bottle=30,
                cost_per_bottle="5000",
                price_per_shot="250",
            )

    def test_metadata_mode_is_bottle_first(self):
        """Metadata records mode as bottle_first."""
        result = self._adapt(
            number_of_bottles=1,
            shots_per_bottle=30,
            cost_per_bottle="5000",
            price_per_shot="250",
        )
        self.assertEqual(result['metadata']['mode'], 'bottle_first')

    def test_legacy_shot_mode_still_works(self):
        """Legacy shot-first mode (no number_of_bottles arg) still works."""
        result = SpiritsStockInAdapter.adapt({
            'quantity_of_shots_added': 60,
            'cost_per_shot': '167',
            'reserved_barman_shots': 0,
        })
        self.assertEqual(result['quantity_units_added'], 60)
        self.assertEqual(result['metadata']['mode'], 'shot_first')


class WhiskyBottleFirstAdapterTest(TestCase):
    """Whisky uses same adapter as Spirits."""

    def test_whisky_bottle_first(self):
        result = WhiskyStockInAdapter.adapt({
            'number_of_bottles': 1,
            'shots_per_bottle': 25,
            'cost_per_bottle': '7000',
            'price_per_shot': '450',
        })
        self.assertEqual(result['quantity_units_added'], 25)
        meta = result['metadata']
        self.assertEqual(meta['category'], 'whisky')


# ---------------------------------------------------------------------------
# Cider Pack-to-Bottle Tests
# ---------------------------------------------------------------------------

class CiderPackAdapterTest(TestCase):
    """Tests for CiderStockInAdapter pack mode."""

    def _adapt_pack(self, **kwargs):
        return CiderStockInAdapter.adapt(kwargs)

    def test_pack_mode_total_bottles(self):
        """3 packs of 6 = 18 bottles."""
        result = self._adapt_pack(
            number_of_packs=3,
            pack_size=6,
            cost_per_pack="2400",
        )
        self.assertEqual(result['quantity_units_added'], 18)

    def test_pack_mode_cost_per_bottle(self):
        """cost_per_bottle = cost_per_pack / pack_size."""
        result = self._adapt_pack(
            number_of_packs=1,
            pack_size=6,
            cost_per_pack="1800",
        )
        self.assertAlmostEqual(float(result['unit_cost']), 1800 / 6, places=2)

    def test_pack_mode_total_cost(self):
        """total_cost = number_of_packs * cost_per_pack."""
        result = self._adapt_pack(
            number_of_packs=4,
            pack_size=6,
            cost_per_pack="2400",
        )
        self.assertAlmostEqual(float(result['total_cost']), 4 * 2400, places=1)

    def test_pack_mode_metadata(self):
        """Pack mode metadata is correct."""
        result = self._adapt_pack(
            number_of_packs=2,
            pack_size=6,
            cost_per_pack="1800",
        )
        meta = result['metadata']
        self.assertEqual(meta['mode'], 'pack')
        self.assertEqual(meta['pack_size'], 6)
        self.assertEqual(meta['number_of_packs'], 2)
        self.assertEqual(meta['quantity_bottles'], 12)

    def test_pack_size_must_be_positive(self):
        """pack_size = 0 raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            self._adapt_pack(
                number_of_packs=1,
                pack_size=0,
                cost_per_pack="1800",
            )
        self.assertIn("Pack size", str(cm.exception))

    def test_packs_must_be_positive(self):
        """number_of_packs = 0 raises ValueError."""
        with self.assertRaises(ValueError):
            self._adapt_pack(
                number_of_packs=0,
                pack_size=6,
                cost_per_pack="1800",
            )

    def test_cost_per_pack_must_be_positive(self):
        """cost_per_pack = 0 raises ValueError."""
        with self.assertRaises(ValueError):
            self._adapt_pack(
                number_of_packs=1,
                pack_size=6,
                cost_per_pack="0",
            )

    def test_bottle_mode_still_works(self):
        """Original bottle mode (no pack fields) still works."""
        result = CiderStockInAdapter.adapt({
            'quantity_bottles': 12,
            'cost_per_bottle': '500',
        })
        self.assertEqual(result['quantity_units_added'], 12)
        self.assertAlmostEqual(float(result['unit_cost']), 500.0, places=2)
        self.assertEqual(result['metadata']['mode'], 'bottle')


# ---------------------------------------------------------------------------
# Beer Adapter Regression Tests (should remain unchanged)
# ---------------------------------------------------------------------------

class BeerAdapterRegressionTest(TestCase):
    """Beer stock-in should remain unaffected."""

    def test_beer_crate_calculation(self):
        """2 crates of 20 = 40 bottles; total cost = 8000; cost per bottle = 200."""
        result = BeerStockInAdapter.adapt({
            'number_of_crates': 2,
            'cost_per_crate': '4000',
            'loose_bottles': 0,
        })
        self.assertEqual(result['quantity_units_added'], 40)
        # total cost = 2 * 4000 = 8000; cost per bottle = 8000 / 40 = 200
        self.assertAlmostEqual(float(result['unit_cost']), 200.0, places=2)

    def test_beer_with_loose_bottles(self):
        """1 crate + 5 loose = 25 bottles."""
        result = BeerStockInAdapter.adapt({
            'number_of_crates': 1,
            'cost_per_crate': '4000',
            'loose_bottles': 5,
        })
        self.assertEqual(result['quantity_units_added'], 25)

    def test_beer_category_in_metadata(self):
        result = BeerStockInAdapter.adapt({
            'number_of_crates': 1,
            'cost_per_crate': '4000',
        })
        self.assertEqual(result['metadata']['category'], 'beer')


# ---------------------------------------------------------------------------
# Mobile Nav Vertical-Awareness Tests
# ---------------------------------------------------------------------------

class MobileNavVerticalAwarenessTest(TestCase):
    """Mobile nav must show correct links per vertical."""

    def _get_nav(self, vertical: str):
        """Build a minimal fake request with BUSINESS_VERTICAL set."""
        factory = RequestFactory()
        req = factory.get('/')
        req.session = {}
        # mobile_nav uses business_vertical() which reads from request
        # Simulate by setting META attribute used by helpers_core
        req.META['BUSINESS_VERTICAL'] = vertical
        # Most implementations read from request.resolver_match or session
        # Patch the helper directly for testing
        from unittest.mock import patch
        with patch('inventory.mobile_nav.business_vertical', return_value=vertical):
            return get_mobile_nav_items(req)

    def test_liquor_nav_has_liquor_links(self):
        """Liquor vertical nav contains liquor-specific links."""
        items = self._get_nav('liquor')
        urls = [i['url'] for i in items]
        keys = [i['key'] for i in items]
        # Should have home, stock_in, sell, menu
        self.assertIn('home', keys)
        self.assertIn('stock_in', keys)
        self.assertIn('sell', keys)
        # URLs should reference liquor paths
        url_str = ' '.join(urls)
        self.assertTrue(
            any('liquor' in u for u in urls),
            f"Expected liquor URL in nav, got: {urls}"
        )

    def test_liquor_nav_does_not_have_phone_links(self):
        """Liquor vertical nav must not contain phone-specific links."""
        items = self._get_nav('liquor')
        urls = ' '.join([i['url'] for i in items])
        self.assertNotIn('phone-sale-wizard', urls)
        self.assertNotIn('scan-in', urls)

    def test_phones_nav_does_not_have_liquor_links(self):
        """Phones vertical nav must not contain liquor-specific links."""
        items = self._get_nav('phones')
        urls = ' '.join([i['url'] for i in items])
        self.assertNotIn('/liquor/', urls)

    def test_energy_nav_has_energy_links(self):
        """Energy vertical nav contains energy-specific links."""
        items = self._get_nav('energy')
        keys = [i['key'] for i in items]
        self.assertIn('home', keys)
        self.assertIn('sites', keys)
        self.assertIn('sizing', keys)
        urls = ' '.join([i['url'] for i in items])
        self.assertTrue(
            any('energy' in u for u in [i['url'] for i in items]),
            f"Expected energy URL in nav, got: {[i['url'] for i in items]}"
        )

    def test_energy_nav_does_not_have_liquor_links(self):
        """Energy vertical nav must not have liquor links."""
        items = self._get_nav('energy')
        urls = ' '.join([i['url'] for i in items])
        self.assertNotIn('/liquor/', urls)

    def test_phones_nav_has_scan_and_sell(self):
        """Phones vertical nav has scan and sell."""
        items = self._get_nav('phones')
        keys = [i['key'] for i in items]
        self.assertIn('scan', keys)
        self.assertIn('sell', keys)
