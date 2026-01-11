"""
Unit tests for migration name mapping utilities.

Tests the SSOT migration name resolution to prevent KeyError failures
when looking up migrations by old/alternate names.

NOTE: These tests require migrations to be enabled. They are skipped when
pytest runs with MIGRATION_MODULES=DisableMigrations (the default for speed).
"""
import pytest
from django.conf import settings
from django.test import TestCase
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from tenants.utils_migrations import (
    resolve_migration_name,
    get_migration_safe,
    has_migration,
    list_migrations,
)

def _skip_if_no_migrations(func):
    """Decorator to skip test if migrations are disabled at runtime."""
    import functools
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        from django.db.migrations.loader import MigrationLoader
        from django.db import connection
        loader = MigrationLoader(connection)
        # Check if tenants app has any migrations loaded
        tenants_migrations = [(app, name) for (app, name) in loader.graph.nodes if app == 'tenants']
        if not tenants_migrations:
            pytest.skip("Migrations disabled in test settings (no tenants migrations found)")
        return func(self, *args, **kwargs)
    return wrapper


class MigrationNameMappingTestCase(TestCase):
    """Test migration name mapping and resilient lookups."""
    
    def setUp(self):
        """Set up migration loader for tests."""
        self.loader = MigrationLoader(connection)
    
    def test_resolve_migration_name_with_full_name(self):
        """Test resolving migration with full canonical name."""
        app_label, name = resolve_migration_name(
            'tenants', 
            '0014_add_case_insensitive_unique_constraints'
        )
        self.assertEqual(app_label, 'tenants')
        self.assertEqual(name, '0014_add_case_insensitive_unique_constraints')
    
    def test_resolve_migration_name_with_short_alias(self):
        """Test resolving migration with short numeric alias."""
        app_label, name = resolve_migration_name('tenants', '0014')
        self.assertEqual(app_label, 'tenants')
        self.assertEqual(name, '0014_add_case_insensitive_unique_constraints')
    
    def test_resolve_migration_name_fallback(self):
        """Test that unknown names fall back to original."""
        app_label, name = resolve_migration_name('tenants', '9999_nonexistent')
        self.assertEqual(app_label, 'tenants')
        self.assertEqual(name, '9999_nonexistent')  # Falls back to original
    
    @_skip_if_no_migrations
    def test_get_migration_safe_with_canonical_name(self):
        """Test getting migration with canonical name."""
        # This should work without KeyError
        migration = get_migration_safe(
            self.loader,
            'tenants',
            '0014_add_case_insensitive_unique_constraints'
        )
        self.assertIsNotNone(migration)
        self.assertEqual(migration.app_label, 'tenants')
    
    @_skip_if_no_migrations
    def test_get_migration_safe_with_alias(self):
        """Test getting migration with short alias."""
        # This should resolve '0014' -> '0014_add_case_insensitive_unique_constraints'
        migration = get_migration_safe(self.loader, 'tenants', '0014')
        self.assertIsNotNone(migration)
        self.assertEqual(migration.app_label, 'tenants')
        # The migration should be the same as looking up by full name
        migration_full = get_migration_safe(
            self.loader,
            'tenants',
            '0014_add_case_insensitive_unique_constraints'
        )
        self.assertEqual(migration.name, migration_full.name)
    
    def test_get_migration_safe_nonexistent_raises_helpful_error(self):
        """Test that nonexistent migration raises KeyError with helpful message."""
        with self.assertRaises(KeyError) as cm:
            get_migration_safe(self.loader, 'tenants', '9999_nonexistent')
        
        error_msg = str(cm.exception)
        # Should mention the migration wasn't found
        self.assertIn('9999_nonexistent', error_msg)
        self.assertIn('not found', error_msg)
    
    @_skip_if_no_migrations
    def test_has_migration_existing(self):
        """Test checking if an existing migration exists."""
        # Should return True for existing migration
        exists = has_migration(
            self.loader,
            'tenants',
            '0014_add_case_insensitive_unique_constraints'
        )
        self.assertTrue(exists)
        
        # Should also work with alias
        exists_alias = has_migration(self.loader, 'tenants', '0014')
        self.assertTrue(exists_alias)
    
    def test_has_migration_nonexistent(self):
        """Test checking if a nonexistent migration exists."""
        exists = has_migration(self.loader, 'tenants', '9999_nonexistent')
        self.assertFalse(exists)
    
    @_skip_if_no_migrations
    def test_list_migrations_returns_all_for_app(self):
        """Test listing all migrations for an app."""
        migrations = list_migrations(self.loader, 'tenants')
        
        # Should return a list of tuples
        self.assertIsInstance(migrations, list)
        self.assertGreater(len(migrations), 0)
        
        # All should be for 'tenants' app
        for app, name in migrations:
            self.assertEqual(app, 'tenants')
        
        # Should include our test migration
        migration_names = [name for app, name in migrations]
        self.assertIn('0014_add_case_insensitive_unique_constraints', migration_names)
    
    @_skip_if_no_migrations
    def test_migration_mapping_prevents_keyerror_in_test(self):
        """
        Integration test: Verify the mapping prevents KeyError in actual test.
        
        This simulates the original failure scenario and verifies the fix.
        """
        from django.db.migrations.executor import MigrationExecutor
        
        executor = MigrationExecutor(connection)
        
        # This was the original failing line - now it should work
        migration = get_migration_safe(
            executor.loader,
            'tenants',
            '0014_add_case_insensitive_unique_constraints'
        )
        
        # Verify we got a valid migration object
        self.assertIsNotNone(migration)
        self.assertEqual(migration.app_label, 'tenants')
        self.assertIn('0014', migration.name)
        
        # Verify it has the expected operations (SeparateDatabaseAndState)
        self.assertGreater(len(migration.operations), 0)


class MigrationNameMappingEdgeCasesTestCase(TestCase):
    """Test edge cases and error conditions."""
    
    def test_resolve_empty_migration_name(self):
        """Test resolving empty migration name."""
        app_label, name = resolve_migration_name('tenants', '')
        self.assertEqual(app_label, 'tenants')
        self.assertEqual(name, '')  # Falls back to empty string
    
    def test_resolve_with_different_app(self):
        """Test resolving migration for different app."""
        app_label, name = resolve_migration_name('inventory', '0050')
        self.assertEqual(app_label, 'inventory')
        # Should fall back to original since not in map
        self.assertEqual(name, '0050')
    
    def test_multiple_resolve_calls_same_result(self):
        """Test that multiple resolve calls return consistent results."""
        result1 = resolve_migration_name('tenants', '0014')
        result2 = resolve_migration_name('tenants', '0014')
        self.assertEqual(result1, result2)

