"""
Tests for import compatibility shims (SSOT + backward compatibility).

This file tests that all backward-compatible import paths work correctly
to prevent ImportError/ModuleNotFoundError regressions.

Requirements:
- CLOTHING_CATEGORIES re-exported from inventory.verticals.clothing
- BusinessUserMembership alias in tenants.models
- accounts module import compatibility
- core.utils.money package functionality
"""
import pytest
from decimal import Decimal
from django.test import TestCase


class ClothingCategoriesImportTest(TestCase):
    """Test CLOTHING_CATEGORIES import compatibility"""

    def test_import_from_clothing_vertical(self):
        """Test that CLOTHING_CATEGORIES can be imported from inventory.verticals.clothing"""
        # This should not raise ImportError
        from inventory.verticals.clothing import CLOTHING_CATEGORIES
        
        # Verify it's a list of tuples
        self.assertIsInstance(CLOTHING_CATEGORIES, list)
        self.assertGreater(len(CLOTHING_CATEGORIES), 0)
        
        # Verify structure: (value, display_name, icon, item_type)
        first_category = CLOTHING_CATEGORIES[0]
        self.assertEqual(len(first_category), 4)
        self.assertIsInstance(first_category[0], str)  # value
        self.assertIsInstance(first_category[1], str)  # display_name
        self.assertIsInstance(first_category[2], str)  # icon
        self.assertIsInstance(first_category[3], str)  # item_type

    def test_import_from_ssot_source(self):
        """Test that CLOTHING_CATEGORIES can be imported from SSOT source"""
        # This is the single source of truth
        from inventory.clothing_config import CLOTHING_CATEGORIES
        
        self.assertIsInstance(CLOTHING_CATEGORIES, list)
        self.assertGreater(len(CLOTHING_CATEGORIES), 0)

    def test_both_imports_reference_same_object(self):
        """Verify that both import paths reference the same object (SSOT)"""
        from inventory.verticals.clothing import CLOTHING_CATEGORIES as cat1
        from inventory.clothing_config import CLOTHING_CATEGORIES as cat2
        
        # They should be the exact same object (not a copy)
        self.assertIs(cat1, cat2)


class BusinessUserMembershipImportTest(TestCase):
    """Test BusinessUserMembership alias compatibility"""

    def test_import_businessusermembership(self):
        """Test that BusinessUserMembership can be imported from tenants.models"""
        # This should not raise ImportError
        from tenants.models import BusinessUserMembership
        
        # Verify it exists and is a class
        self.assertIsNotNone(BusinessUserMembership)
        
    def test_import_membership(self):
        """Test that Membership (the actual model) can be imported"""
        from tenants.models import Membership
        
        self.assertIsNotNone(Membership)
    
    def test_alias_points_to_membership(self):
        """Verify that BusinessUserMembership is an alias for Membership"""
        from tenants.models import BusinessUserMembership, Membership
        
        # They should be the exact same class
        self.assertIs(BusinessUserMembership, Membership)

    def test_can_use_alias_for_queries(self):
        """Test that BusinessUserMembership alias works for ORM operations"""
        from tenants.models import BusinessUserMembership, Membership
        
        # Both should have the same manager
        self.assertIs(BusinessUserMembership.objects, Membership.objects)
        
        # Both should query the same table
        self.assertEqual(
            BusinessUserMembership._meta.db_table,
            Membership._meta.db_table
        )


class AccountsModuleImportTest(TestCase):
    """Test accounts module import compatibility"""

    def test_import_accounts_module(self):
        """Test that accounts module can be imported"""
        # This should not raise ImportError
        import accounts
        
        self.assertIsNotNone(accounts)

    def test_import_from_accounts_models(self):
        """Test that models can be imported from accounts"""
        from accounts.models import Profile
        
        self.assertIsNotNone(Profile)

    def test_import_from_circuitcity_accounts(self):
        """Test that the actual accounts app can be imported"""
        from circuitcity.accounts.models import Profile
        
        self.assertIsNotNone(Profile)

    def test_both_paths_reference_same_module(self):
        """Verify that both import paths reference the same Profile class"""
        from accounts.models import Profile as Profile1
        from circuitcity.accounts.models import Profile as Profile2
        
        # They should be the exact same class
        self.assertIs(Profile1, Profile2)


class CoreUtilsMoneyImportTest(TestCase):
    """Test core.utils.money package functionality"""

    def test_import_from_core_utils_money(self):
        """Test that functions can be imported from core.utils.money"""
        # This should not raise ImportError
        from core.utils.money import format_money, mwk_to_usd, get_mwk_per_usd
        
        self.assertIsNotNone(format_money)
        self.assertIsNotNone(mwk_to_usd)
        self.assertIsNotNone(get_mwk_per_usd)

    def test_import_from_core_utils(self):
        """Test that existing core.utils imports still work"""
        # This should not raise ImportError (backward compatibility)
        from core.utils import (
            safe_int,
            human_timedelta,
            days_between,
            format_money,
            haversine_m,
            in_geofence,
        )
        
        self.assertIsNotNone(safe_int)
        self.assertIsNotNone(human_timedelta)
        self.assertIsNotNone(days_between)
        self.assertIsNotNone(format_money)
        self.assertIsNotNone(haversine_m)
        self.assertIsNotNone(in_geofence)

    def test_core_utils_package_structure(self):
        """Verify that core.utils is a package with money submodule"""
        import core.utils
        import core.utils.money
        
        # Verify both exist
        self.assertIsNotNone(core.utils)
        self.assertIsNotNone(core.utils.money)
        
        # Verify core.utils has __init__.py content
        self.assertTrue(hasattr(core.utils, 'safe_int'))
        self.assertTrue(hasattr(core.utils, 'format_money'))
        
        # Verify core.utils.money has its own functions
        self.assertTrue(hasattr(core.utils.money, 'format_money'))
        self.assertTrue(hasattr(core.utils.money, 'mwk_to_usd'))
        self.assertTrue(hasattr(core.utils.money, 'get_mwk_per_usd'))

    def test_mwk_to_usd_conversion(self):
        """Test that mwk_to_usd function works correctly"""
        from core.utils.money import mwk_to_usd
        
        # Test conversion
        result = mwk_to_usd(Decimal("1750"), Decimal("1750"))
        self.assertEqual(result, Decimal("1.00"))
        
        # Test with None rate
        result = mwk_to_usd(Decimal("1000"), None)
        self.assertIsNone(result)

    def test_format_money_function(self):
        """Test that format_money function works correctly"""
        from core.utils.money import format_money
        
        # Test MWK formatting
        result = format_money(Decimal("100000"), "MWK", None, False)
        self.assertEqual(result, "MWK 100,000")
        
        # Test USD formatting with rate
        result = format_money(Decimal("1750"), "USD", Decimal("1750"), False)
        self.assertEqual(result, "USD 1.00")


class ImportCompatibilityIntegrationTest(TestCase):
    """Integration tests for all import compatibility shims"""

    def test_all_imports_work_together(self):
        """Test that all compatibility imports can be used together"""
        # Import everything that should work
        from inventory.verticals.clothing import CLOTHING_CATEGORIES
        from tenants.models import BusinessUserMembership, Membership
        from accounts.models import Profile
        from core.utils.money import format_money, mwk_to_usd
        from core.utils import safe_int, format_money as format_money_legacy
        
        # Verify all exist
        self.assertIsNotNone(CLOTHING_CATEGORIES)
        self.assertIsNotNone(BusinessUserMembership)
        self.assertIsNotNone(Membership)
        self.assertIsNotNone(Profile)
        self.assertIsNotNone(format_money)
        self.assertIsNotNone(mwk_to_usd)
        self.assertIsNotNone(safe_int)
        self.assertIsNotNone(format_money_legacy)
        
        # Verify aliases point to correct objects
        self.assertIs(BusinessUserMembership, Membership)

    def test_no_circular_imports(self):
        """Ensure no circular import issues with compatibility shims"""
        # This test passes if it doesn't raise an ImportError
        try:
            from inventory.verticals.clothing import CLOTHING_CATEGORIES
            from tenants.models import BusinessUserMembership
            from accounts.models import Profile
            from core.utils.money import format_money
            from core.utils import safe_int
        except ImportError as e:
            self.fail(f"Circular import detected: {e}")

