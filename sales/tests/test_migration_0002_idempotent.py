"""
Regression test for migration 0002: ensure constraint addition is idempotent.

This test verifies that the sale_commission_pct_0_100 constraint can be added
even if it already exists in the database, preventing DuplicateObject errors.
"""
import unittest
from django.db import connection
from django.test import TestCase
from django.test.utils import setup_test_environment, teardown_test_environment
from django.core.management import call_command
from django.db.migrations.executor import MigrationExecutor


class TestMigration0002Idempotent(TestCase):
    """Test that migration 0002 is idempotent when constraints already exist."""

    app = 'sales'
    migrate_from = [('sales', '0001_initial')]
    migrate_to = [('sales', '0002_alter_sale_options_sale_created_at_and_more')]

    def setUp(self):
        """Set up test by migrating to 0001_initial."""
        self.executor = MigrationExecutor(connection)
        self.executor.loader.build_graph()
        
        # Only migrate backwards if not using SQLite
        if connection.vendor != 'sqlite':
            self.executor.migrate(self.migrate_from)
        
    @unittest.skipUnless(connection.vendor == 'postgresql', 'PostgreSQL-specific test')
    def test_migration_0002_succeeds_when_constraint_already_exists(self):
        """
        Test that migrating to 0002 succeeds even when the constraint already exists.
        
        This simulates the production scenario where:
        1. Database is at migration 0001
        2. Constraint is manually created (or exists from a previous failed migration)
        3. Migration to 0002 runs and should NOT fail
        """
        # Manually create the constraint that migration 0002 would add
        with connection.cursor() as cursor:
            cursor.execute("""
                ALTER TABLE sales_sale
                ADD CONSTRAINT sale_commission_pct_0_100 
                CHECK (commission_pct >= 0 AND commission_pct <= 100);
            """)
        
        # Now migrate to 0002 - this should succeed without DuplicateObject error
        try:
            self.executor.migrate(self.migrate_to)
            migration_successful = True
        except Exception as e:
            migration_successful = False
            self.fail(f"Migration 0002 failed when constraint already exists: {e}")
        
        self.assertTrue(migration_successful, "Migration 0002 should succeed even when constraint exists")
        
        # Verify the constraint exists after migration
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                WHERE c.conname = 'sale_commission_pct_0_100'
                AND t.relname = 'sales_sale'
            """)
            constraint_exists = cursor.fetchone() is not None
        
        self.assertTrue(constraint_exists, "Constraint should exist after migration")
    
    @unittest.skipUnless(connection.vendor == 'postgresql', 'PostgreSQL-specific test')
    def test_migration_0002_creates_constraint_when_not_exists(self):
        """
        Test that migrating to 0002 creates the constraint when it doesn't exist.
        
        This is the normal migration path.
        """
        # Migrate to 0002 without pre-creating the constraint
        self.executor.migrate(self.migrate_to)
        
        # Verify the constraint was created
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                WHERE c.conname = 'sale_commission_pct_0_100'
                AND t.relname = 'sales_sale'
            """)
            constraint_exists = cursor.fetchone() is not None
        
        self.assertTrue(constraint_exists, "Constraint should be created by migration")
    
    @unittest.skipUnless(connection.vendor == 'postgresql', 'PostgreSQL-specific test')
    def test_migration_0002_reverse_is_idempotent(self):
        """
        Test that reversing migration 0002 is also idempotent.
        """
        # First migrate forward to 0002
        self.executor.migrate(self.migrate_to)
        
        # Then migrate back to 0001
        self.executor.migrate(self.migrate_from)
        
        # Verify the constraint was removed
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                WHERE c.conname = 'sale_commission_pct_0_100'
                AND t.relname = 'sales_sale'
            """)
            constraint_exists = cursor.fetchone() is not None
        
        self.assertFalse(constraint_exists, "Constraint should be removed after reversing migration")
        
        # Try reversing again - should not fail even if constraint doesn't exist
        try:
            self.executor.migrate(self.migrate_from)
            reverse_successful = True
        except Exception as e:
            reverse_successful = False
            self.fail(f"Reversing migration 0002 twice should not fail: {e}")
        
        self.assertTrue(reverse_successful, "Reversing migration should be idempotent")

