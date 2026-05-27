"""
Tests for Farm Dashboard Resilience and Migration Safety.

CRITICAL: Ensures that:
1. Farm migrations exist and create necessary tables
2. Farm dashboard renders correctly with data
3. Farm dashboard handles missing tables gracefully (no 500 errors)
4. All tests prevent regression of the "no such table" bug

These tests lock down the fix for the farm dashboard 500 error.
"""
import pytest
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.db import connection, OperationalError
from django.db.migrations.executor import MigrationExecutor

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind

User = get_user_model()


class FarmMigrationExistenceTest(TestCase):
    """Test that Farm model migrations exist and table is created."""

    def test_farm_ledger_entry_table_exists(self):
        """
        CRITICAL: Ensure inventory_farmledgerentry table exists after migrations.
        
        This test verifies that the migration was created and applied,
        preventing the "no such table: inventory_farmledgerentry" error.
        """
        with connection.cursor() as cursor:
            # Get all table names
            table_names = connection.introspection.table_names(cursor)
            
            # Assert the farm ledger table exists
            self.assertIn(
                "inventory_farmledgerentry",
                table_names,
                "inventory_farmledgerentry table must exist after migrations"
            )
    
    def test_farm_livestock_batch_table_exists(self):
        """Ensure inventory_farmlivestockbatch table exists."""
        with connection.cursor() as cursor:
            table_names = connection.introspection.table_names(cursor)
            self.assertIn(
                "inventory_farmlivestockbatch",
                table_names,
                "inventory_farmlivestockbatch table must exist after migrations"
            )
    
    def test_farm_livestock_event_table_exists(self):
        """Ensure inventory_farmlivestockevent table exists."""
        with connection.cursor() as cursor:
            table_names = connection.introspection.table_names(cursor)
            self.assertIn(
                "inventory_farmlivestockevent",
                table_names,
                "inventory_farmlivestockevent table must exist after migrations"
            )
    
    def test_farm_crop_season_table_exists(self):
        """Ensure inventory_farmcropseason table exists."""
        with connection.cursor() as cursor:
            table_names = connection.introspection.table_names(cursor)
            self.assertIn(
                "inventory_farmcropseason",
                table_names,
                "inventory_farmcropseason table must exist after migrations"
            )
    
    def test_farm_migration_file_exists(self):
        """Ensure the farm models migration file exists."""
        from django.db.migrations.loader import MigrationLoader
        
        loader = MigrationLoader(connection)
        
        # Check that inventory app has migrations
        self.assertIn(
            "inventory",
            loader.migrated_apps,
            "inventory app must have migrations"
        )
        
        # Get all inventory migrations
        inventory_migrations = [
            name for app, name in loader.disk_migrations.keys()
            if app == "inventory"
        ]
        
        # Check that at least one migration contains farm models
        # (The migration we created should be named something like "0113_farm_models")
        farm_migration_exists = any(
            "farm" in migration_name.lower()
            for migration_name in inventory_migrations
        )
        
        self.assertTrue(
            farm_migration_exists,
            f"Farm migration should exist in inventory migrations. Found: {inventory_migrations}"
        )


class FarmDashboardRenderTest(TestCase):
    """Test that farm dashboard renders correctly with proper data."""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="farm_manager@test.com",
            email="farm_manager@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Test Farm",
            slug="test-farm",
            business_kind="farm",
            status="ACTIVE",
            created_by=self.user,
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

    def test_farm_dashboard_returns_200(self):
        """
        CRITICAL: Farm dashboard should return 200 OK.
        
        This test verifies that with migrations applied, the dashboard
        renders without any 500 errors.
        """
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        # Access farm dashboard
        response = self.client.get("/verticals/farm/dashboard/")
        
        # Should return 200
        self.assertEqual(
            response.status_code,
            200,
            f"Farm dashboard should return 200, got {response.status_code}. "
            f"Check if migrations are applied."
        )
    
    def test_farm_dashboard_renders_with_no_data(self):
        """
        CRITICAL: Farm dashboard should render even with zero ledger entries.
        
        This is the "empty state" scenario - new farm business with no transactions.
        """
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        self.assertEqual(response.status_code, 200)
        
        # Should contain farm-specific content
        content = response.content.decode("utf-8")
        self.assertIn(
            "Farm Manager",
            content,
            "Dashboard should show 'Farm Manager' title"
        )
    
    def test_farm_dashboard_context_has_required_keys(self):
        """Ensure dashboard context has all required keys for template."""
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        self.assertEqual(response.status_code, 200)
        
        # Check for required context keys
        context = response.context
        
        required_keys = [
            "active_tab",
            "hero_title",
            "snapshot",
            "profit_trend_json",
            "expense_breakdown_json",
        ]
        
        for key in required_keys:
            self.assertIn(
                key,
                context,
                f"Dashboard context must contain '{key}'"
            )


class FarmDashboardFailSafeTest(TestCase):
    """Test that farm dashboard handles missing tables gracefully."""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="farm_manager@test.com",
            email="farm_manager@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Test Farm",
            slug="test-farm",
            business_kind="farm",
            status="ACTIVE",
            created_by=self.user,
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

    @patch("inventory.models_farm.FarmLedgerEntry.objects.filter")
    def test_farm_dashboard_handles_missing_table(self, mock_filter):
        """
        CRITICAL: Farm dashboard should NOT 500 if table is missing.
        
        This simulates the scenario where the code exists but migrations
        haven't been applied yet. The dashboard should:
        - Return 200 (not 500)
        - Set farm_setup_required flag
        - Show empty state gracefully
        """
        # Simulate "no such table" error
        mock_filter.side_effect = OperationalError(
            "no such table: inventory_farmledgerentry"
        )
        
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        # Should return 200, NOT 500
        self.assertEqual(
            response.status_code,
            200,
            "Dashboard should return 200 even if table is missing (fail-safe)"
        )
        
        # Should set farm_setup_required flag
        context = response.context
        self.assertTrue(
            context.get("farm_setup_required", False),
            "Dashboard should set farm_setup_required=True when table is missing"
        )
    
    @patch("inventory.models_farm.FarmLedgerEntry.objects.filter")
    def test_farm_dashboard_reraises_other_db_errors(self, mock_filter):
        """
        CRITICAL: Only catch "no such table" errors, not all DB errors.
        
        Other database errors (permissions, corruption, etc.) should
        still raise 500 so they're visible and can be fixed.
        """
        # Simulate a different database error (not "no such table")
        mock_filter.side_effect = OperationalError(
            "database is locked"
        )
        
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        # This should raise an exception (500 error)
        with self.assertRaises(OperationalError):
            response = self.client.get("/verticals/farm/dashboard/")


class FarmDashboardWithDataTest(TestCase):
    """Test farm dashboard with actual ledger data."""

    def setUp(self):
        """Set up test data with ledger entries"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="farm_manager@test.com",
            email="farm_manager@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Test Farm",
            slug="test-farm",
            business_kind="farm",
            status="ACTIVE",
            created_by=self.user,
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )
    
    def test_farm_dashboard_with_ledger_entries(self):
        """Test that dashboard works when ledger entries exist."""
        from inventory.models_farm import FarmLedgerEntry, FarmEntryType
        from django.utils import timezone
        
        # Create a test ledger entry
        FarmLedgerEntry.objects.create(
            business=self.business,
            date=timezone.now().date(),
            entry_type=FarmEntryType.SALE,
            amount_mwk=Decimal("50000.00"),
            description="Test Sale",
            created_by=self.user,
        )
        
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/")
        
        self.assertEqual(response.status_code, 200)
        
        # Snapshot should have data
        snapshot = response.context.get("snapshot")
        self.assertIsNotNone(snapshot, "Dashboard should have snapshot")


class FarmDashboardNoRegressionTest(TestCase):
    """Ensure farm dashboard doesn't regress to other verticals."""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="farm_manager@test.com",
            email="farm_manager@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Test Farm",
            slug="test-farm",
            business_kind="farm",
            status="ACTIVE",
            created_by=self.user,
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

    def test_farm_dashboard_not_generic_fallback(self):
        """
        CRITICAL: Farm business must NOT land on /verticals/none/ or show generic fallback.
        """
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        response = self.client.get("/verticals/farm/dashboard/", follow=True)
        
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode("utf-8")
        
        # Should NOT contain generic fallback messages
        self.assertNotIn(
            "Business Type Not Configured",
            content,
            "Farm dashboard must NOT show 'Business Type Not Configured'"
        )
        
        # Should NOT have been redirected to /verticals/none/
        final_url = response.request["PATH_INFO"]
        self.assertNotIn(
            "/verticals/none/",
            final_url,
            f"Farm business should NOT be on /verticals/none/, got: {final_url}"
        )
        
        # Should contain farm-specific content
        self.assertIn(
            "Farm Manager",
            content,
            "Farm dashboard should show 'Farm Manager' (not generic content)"
        )

