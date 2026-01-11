"""
Regression tests for KeyError failures.

This test suite ensures that the SSOT (Single Source of Truth) implementation
prevents the following KeyError failures from recurring:

1. KeyError: 'sold_today'
2. KeyError: 'payment_mix_json'
3. KeyError: 'report_trend_json'
4. KeyError: 'report_summary'
5. KeyError: ('tenants', '0014_add_case_insensitive_unique_constraints')

These tests lock in the fixes and prevent regressions.
"""
import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.executor import MigrationExecutor

from tenants.models import Business, Location
from tenants.utils_migrations import (
    resolve_migration_name,
    get_migration_safe,
    has_migration,
)

User = get_user_model()


# ============================================================================
# CONTEXT KEY KEYERROR REGRESSION TESTS
# ============================================================================

class KeyErrorContextRegressionTestCase(TestCase):
    """
    Test that all context KeyErrors are fixed and won't regress.
    
    These tests verify that the SSOT defaults are applied to all views
    that previously caused KeyError failures in production.
    """
    
    def setUp(self):
        """Create minimal test data."""
        self.business = Business.objects.create(
            name="KeyError Test Shop",
            kind="phones",
            is_active=True,
        )
        
        self.location = Location.objects.create(
            name="Main Branch",
            business=self.business,
        )
        
        self.user = User.objects.create_user(
            username="keyerroruser",
            password="testpass123",
            is_staff=True,
        )
        
        self.client = Client()
        self.client.force_login(self.user)
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_reports_home_no_keyerror_sold_today(self):
        """
        Regression test: KeyError: 'sold_today'
        
        Verifies that reports home always has 'sold_today' in context.
        """
        response = self.client.get(reverse('reports:home'))
        
        self.assertEqual(response.status_code, 200)
        
        # CRITICAL: This key caused KeyError in production
        self.assertIn('sold_today', response.context)
        self.assertEqual(response.context['sold_today'], 0)
    
    def test_reports_home_no_keyerror_payment_mix_json(self):
        """
        Regression test: KeyError: 'payment_mix_json'
        
        Verifies that reports home always has 'payment_mix_json' in context.
        """
        response = self.client.get(reverse('reports:home'))
        
        self.assertEqual(response.status_code, 200)
        
        # CRITICAL: This key caused KeyError in production
        self.assertIn('payment_mix_json', response.context)
        
        # Verify it's valid JSON
        json_str = response.context['payment_mix_json']
        self.assertIsNotNone(json_str)
        parsed = json.loads(json_str)
        self.assertIsInstance(parsed, list)
    
    def test_reports_home_no_keyerror_report_trend_json(self):
        """
        Regression test: KeyError: 'report_trend_json'
        
        Verifies that reports home always has 'report_trend_json' in context.
        """
        response = self.client.get(reverse('reports:home'))
        
        self.assertEqual(response.status_code, 200)
        
        # CRITICAL: This key caused KeyError in production
        self.assertIn('report_trend_json', response.context)
        
        # Verify it's valid JSON
        json_str = response.context['report_trend_json']
        self.assertIsNotNone(json_str)
        parsed = json.loads(json_str)
        self.assertIsInstance(parsed, list)
    
    def test_reports_home_no_keyerror_report_summary(self):
        """
        Regression test: KeyError: 'report_summary'
        
        Verifies that reports home always has 'report_summary' in context.
        """
        response = self.client.get(reverse('reports:home'))
        
        self.assertEqual(response.status_code, 200)
        
        # CRITICAL: This key caused KeyError in production
        self.assertIn('report_summary', response.context)
        
        summary = response.context['report_summary']
        self.assertIsInstance(summary, dict)
        
        # Verify expected keys exist in summary
        expected_keys = [
            'total_revenue',
            'total_costs',
            'net_profit',
            'sales_count',
        ]
        
        for key in expected_keys:
            with self.subTest(key=key):
                self.assertIn(key, summary)
    
    def test_reports_sales_no_keyerror_all_keys(self):
        """
        Regression test: Verify all critical keys exist in sales report.
        """
        response = self.client.get(reverse('reports:sales'))
        
        self.assertEqual(response.status_code, 200)
        
        # All critical keys should exist
        critical_keys = [
            'sold_today',
            'payment_mix_json',
            'report_trend_json',
            'report_summary',
        ]
        
        for key in critical_keys:
            with self.subTest(key=key):
                self.assertIn(key, response.context,
                              f"Missing critical key: {key}")
    
    def test_reports_inventory_no_keyerror_all_keys(self):
        """
        Regression test: Verify all critical keys exist in inventory report.
        """
        response = self.client.get(reverse('reports:inventory'))
        
        self.assertEqual(response.status_code, 200)
        
        # All critical keys should exist
        critical_keys = [
            'sold_today',
            'payment_mix_json',
            'report_trend_json',
            'report_summary',
        ]
        
        for key in critical_keys:
            with self.subTest(key=key):
                self.assertIn(key, response.context,
                              f"Missing critical key: {key}")
    
    def test_all_reports_return_200_no_crash(self):
        """
        Integration test: Verify all report endpoints return 200 with no KeyError.
        
        This test ensures that all report views apply SSOT defaults correctly
        and never crash with KeyError.
        """
        report_urls = [
            ('reports:home', {}),
            ('reports:sales', {}),
            ('reports:inventory', {}),
        ]
        
        for url_name, kwargs in report_urls:
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name, kwargs=kwargs))
                
                # Should return 200 (not 500)
                self.assertEqual(response.status_code, 200,
                                f"{url_name} returned {response.status_code}")
                
                # Should have no Python KeyError exception in response
                # Check for actual error indicators, not just the string "KeyError"
                content = response.content.decode('utf-8')
                
                # Look for actual Django error page indicators
                self.assertNotIn('KeyError at /', content,
                               f"{url_name} contains KeyError exception")
                self.assertNotIn('Exception Type: KeyError', content,
                               f"{url_name} contains KeyError exception")
                self.assertNotIn('<h1>KeyError', content,
                               f"{url_name} contains KeyError exception")


# ============================================================================
# MIGRATION KEYERROR REGRESSION TESTS
# ============================================================================

class KeyErrorMigrationRegressionTestCase(TestCase):
    """
    Test that migration KeyErrors are fixed and won't regress.
    
    These tests verify that the migration name mapping prevents:
    - KeyError: ('tenants', '0014_add_case_insensitive_unique_constraints')
    """
    
    def setUp(self):
        """Set up migration loader."""
        self.loader = MigrationLoader(connection)
    
    def test_no_keyerror_for_tenants_0014_migration(self):
        """
        Regression test: KeyError: ('tenants', '0014_add_case_insensitive_unique_constraints')
        
        Verifies that the migration can be looked up without KeyError.
        """
        # This was the original failing lookup
        app_label, migration_name = resolve_migration_name(
            'tenants',
            '0014_add_case_insensitive_unique_constraints'
        )
        
        self.assertEqual(app_label, 'tenants')
        self.assertEqual(migration_name, '0014_add_case_insensitive_unique_constraints')
        
        # Should be able to get the migration without KeyError
        migration = get_migration_safe(
            self.loader,
            app_label,
            migration_name
        )
        
        self.assertIsNotNone(migration)
        self.assertEqual(migration.app_label, 'tenants')
    
    def test_migration_lookup_with_short_alias_no_keyerror(self):
        """
        Regression test: Verify short alias lookup works without KeyError.
        """
        # Short alias should resolve correctly
        app_label, migration_name = resolve_migration_name('tenants', '0014')
        
        self.assertEqual(app_label, 'tenants')
        self.assertEqual(migration_name, '0014_add_case_insensitive_unique_constraints')
        
        # Should be able to get the migration
        migration = get_migration_safe(self.loader, app_label, migration_name)
        
        self.assertIsNotNone(migration)
    
    def test_has_migration_returns_true_for_existing_no_keyerror(self):
        """
        Regression test: Verify has_migration doesn't raise KeyError.
        """
        # Should return True without KeyError
        exists = has_migration(
            self.loader,
            'tenants',
            '0014_add_case_insensitive_unique_constraints'
        )
        
        self.assertTrue(exists)
        
        # Should also work with alias
        exists_alias = has_migration(self.loader, 'tenants', '0014')
        self.assertTrue(exists_alias)
    
    def test_migration_lookup_in_executor_no_keyerror(self):
        """
        Integration test: Verify migration lookup in executor context.
        
        This simulates the real-world usage pattern where the KeyError occurred.
        """
        executor = MigrationExecutor(connection)
        
        # This was the original failing pattern
        migration = get_migration_safe(
            executor.loader,
            'tenants',
            '0014_add_case_insensitive_unique_constraints'
        )
        
        self.assertIsNotNone(migration)
        self.assertEqual(migration.app_label, 'tenants')
        self.assertIn('0014', migration.name)


# ============================================================================
# COMPREHENSIVE INTEGRATION TEST
# ============================================================================

class KeyErrorComprehensiveRegressionTestCase(TestCase):
    """
    Comprehensive regression test suite covering all KeyError scenarios.
    
    This test suite verifies that ALL KeyError failures mentioned in the
    task are fixed and won't regress.
    """
    
    def setUp(self):
        """Create test data."""
        self.business = Business.objects.create(
            name="Comprehensive Test Shop",
            kind="phones",
            is_active=True,
        )
        
        self.user = User.objects.create_user(
            username="comprehensiveuser",
            password="testpass123",
            is_staff=True,
        )
        
        self.client = Client()
        self.client.force_login(self.user)
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_all_five_keyerror_scenarios_are_fixed(self):
        """
        Master regression test: Verify all 5 KeyError scenarios are fixed.
        
        This test verifies:
        1. KeyError: 'sold_today' - FIXED
        2. KeyError: 'payment_mix_json' - FIXED
        3. KeyError: 'report_trend_json' - FIXED
        4. KeyError: 'report_summary' - FIXED
        5. KeyError: ('tenants', '0014_...') - FIXED
        """
        # Test scenarios 1-4: Context KeyErrors
        response = self.client.get(reverse('reports:home'))
        self.assertEqual(response.status_code, 200)
        
        # Verify all context keys exist
        self.assertIn('sold_today', response.context, "KeyError: 'sold_today' not fixed")
        self.assertIn('payment_mix_json', response.context, "KeyError: 'payment_mix_json' not fixed")
        self.assertIn('report_trend_json', response.context, "KeyError: 'report_trend_json' not fixed")
        self.assertIn('report_summary', response.context, "KeyError: 'report_summary' not fixed")
        
        # Test scenario 5: Migration KeyError
        loader = MigrationLoader(connection)
        migration = get_migration_safe(
            loader,
            'tenants',
            '0014_add_case_insensitive_unique_constraints'
        )
        self.assertIsNotNone(migration, "KeyError: migration lookup not fixed")
        
        # All scenarios PASSED!
        print("\n✅ All 5 KeyError scenarios are FIXED:")
        print("  1. KeyError: 'sold_today' - FIXED")
        print("  2. KeyError: 'payment_mix_json' - FIXED")
        print("  3. KeyError: 'report_trend_json' - FIXED")
        print("  4. KeyError: 'report_summary' - FIXED")
        print("  5. KeyError: migration lookup - FIXED")

