# inventory/tests/test_new_verticals_regression.py
"""
Regression Tests — New Verticals Integration
==============================================

Tests ensure:
- New verticals (mixed_retail, consultancy) are registered in BusinessKind
- Sidebar navigation includes new verticals
- utils_verticals returns sidebar items for new verticals
- Existing verticals are not broken by additions
- Business kind display names work
"""
from django.test import TestCase


class BusinessKindRegressionTest(TestCase):
    """BusinessKind includes all expected verticals."""

    def test_mixed_retail_in_business_kind(self):
        from inventory.business_kinds import BusinessKind
        values = [v for v, _ in BusinessKind.choices]
        self.assertIn("mixed_retail", values, "MIXED_RETAIL not in BusinessKind")

    def test_consultancy_in_business_kind(self):
        from inventory.business_kinds import BusinessKind
        values = [v for v, _ in BusinessKind.choices]
        self.assertIn("consultancy", values, "CONSULTANCY not in BusinessKind")

    def test_mobile_money_in_business_kind(self):
        from inventory.business_kinds import BusinessKind
        values = [v for v, _ in BusinessKind.choices]
        self.assertIn("mobile_money", values, "MOBILE_MONEY not in BusinessKind")

    def test_existing_verticals_still_present(self):
        """Existing verticals not removed from BusinessKind."""
        from inventory.business_kinds import BusinessKind
        values = [v for v, _ in BusinessKind.choices]
        for expected in ["clothing", "phones", "farm"]:
            self.assertIn(expected, values, f"{expected} no longer in BusinessKind choices")


class UtilsVerticalsSidebarNewVerticals(TestCase):
    """New verticals have sidebar items registered."""

    def test_mixed_retail_sidebar_items(self):
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("mixed_retail")
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0, "Mixed Retail sidebar has no items")

    def test_consultancy_sidebar_items(self):
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("consultancy")
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0, "Consultancy sidebar has no items")

    def test_mixed_retail_display_name(self):
        from inventory.utils_verticals import get_vertical_display_name
        name = get_vertical_display_name("mixed_retail")
        self.assertIsNotNone(name)
        self.assertNotEqual(name, "")

    def test_consultancy_display_name(self):
        from inventory.utils_verticals import get_vertical_display_name
        name = get_vertical_display_name("consultancy")
        self.assertIsNotNone(name)
        self.assertNotEqual(name, "")

    def test_existing_clothing_sidebar_still_works(self):
        """Clothing sidebar unaffected by new verticals."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("clothing")
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)

    def test_existing_phones_sidebar_still_works(self):
        """Phones sidebar unaffected by new verticals."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        items = get_vertical_sidebar_items("phones")
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)


class UrlRegressionTest(TestCase):
    """URL patterns for new verticals exist and resolve."""

    def test_mixed_retail_urls_load(self):
        """mixed_retail URL patterns load without import errors."""
        try:
            from inventory import urls_mixed_retail
            self.assertIsNotNone(urls_mixed_retail.urlpatterns)
        except ImportError as e:
            self.fail(f"Could not import urls_mixed_retail: {e}")

    def test_consultancy_urls_load(self):
        """consultancy URL patterns load without import errors."""
        try:
            from inventory import urls_consultancy
            self.assertIsNotNone(urls_consultancy.urlpatterns)
        except ImportError as e:
            self.fail(f"Could not import urls_consultancy: {e}")

    def test_mixed_retail_views_import(self):
        """mixed_retail views module imports cleanly."""
        try:
            from inventory.verticals import mixed_retail  # noqa
        except ImportError as e:
            self.fail(f"Could not import verticals.mixed_retail: {e}")

    def test_consultancy_views_import(self):
        """consultancy views module imports cleanly."""
        try:
            from inventory.verticals import consultancy  # noqa
        except ImportError as e:
            self.fail(f"Could not import verticals.consultancy: {e}")


class ModelImportRegressionTest(TestCase):
    """All new model modules import without errors."""

    def test_mixed_retail_models_import(self):
        try:
            from inventory import models_mixed_retail  # noqa
        except ImportError as e:
            self.fail(f"models_mixed_retail import failed: {e}")

    def test_consultancy_models_import(self):
        try:
            from inventory import models_consultancy  # noqa
        except ImportError as e:
            self.fail(f"models_consultancy import failed: {e}")

    def test_mobile_money_models_import(self):
        try:
            from inventory import models_mobilemoney  # noqa
        except ImportError as e:
            self.fail(f"models_mobilemoney import failed: {e}")

    def test_mixed_retail_seed_import(self):
        try:
            from inventory import mixed_retail_seed  # noqa
        except ImportError as e:
            self.fail(f"mixed_retail_seed import failed: {e}")
