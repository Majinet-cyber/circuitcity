"""
Tests for migration consistency and idempotency.
These tests ensure that migrations don't have common issues.
"""

from django.test import TestCase
from django.core.management import call_command
from io import StringIO
import re
from pathlib import Path


class MigrationConsistencyTests(TestCase):
    """Test that migrations are consistent and well-formed."""
    
    def test_no_unapplied_migrations(self):
        """Test that there are no model changes without migrations."""
        try:
            out = StringIO()
            call_command('makemigrations', '--check', '--dry-run', stdout=out)
            # If we get here, no migrations needed
            self.assertTrue(True)
        except SystemExit as e:
            if e.code == 0:
                self.assertTrue(True)
            else:
                self.fail("Found unapplied model changes. Run makemigrations.")
    
    def test_migration_plan_valid(self):
        """Test that the migration plan is valid (no conflicts)."""
        out = StringIO()
        try:
            call_command('migrate', '--plan', stdout=out)
            output = out.getvalue()
            
            # Check for error indicators
            self.assertNotIn('InconsistentMigrationHistory', output,
                           "Migration history is inconsistent")
            self.assertNotIn('ConflictingMigrations', output,
                           "Found conflicting migrations")
            self.assertNotIn('Error', output,
                           "Error in migration plan")
        except Exception as e:
            self.fail(f"Migration plan failed: {e}")
    
    def test_no_duplicate_migration_numbers(self):
        """Test that there are no duplicate migration numbers in the same app."""
        for app in ['inventory', 'tenants']:
            migrations_dir = Path(app) / 'migrations'
            if not migrations_dir.exists():
                continue
            
            migration_numbers = {}
            
            for migration_file in migrations_dir.glob('*.py'):
                if migration_file.name.startswith('__'):
                    continue
                
                # Extract base migration number (e.g., "0019" from "0019_add_something.py")
                match = re.match(r'(\d+)_', migration_file.name)
                if match:
                    number = match.group(1)
                    
                    if number not in migration_numbers:
                        migration_numbers[number] = []
                    migration_numbers[number].append(migration_file.name)
            
            # Check for pure duplicates (not 0019/0019a which is intentional)
            for number, files in migration_numbers.items():
                # Filter to only files with exact number (not 0019a, 0019b, etc.)
                pure_matches = [f for f in files if re.match(rf'{number}_', f)]
                
                self.assertLessEqual(
                    len(pure_matches), 1,
                    f"App '{app}' has multiple migrations with number {number}: {pure_matches}"
                )


class CementSaleMigrationTests(TestCase):
    """Test that CementSale migrations are idempotent."""
    
    def test_cementsale_has_total_fields(self):
        """Test that CementSale model has total_price and total_cost fields."""
        from inventory.models_verticals import CementSale
        
        # Check that fields exist in model
        field_names = [f.name for f in CementSale._meta.get_fields()]
        
        self.assertIn('total_price', field_names,
                     "CementSale should have total_price field")
        self.assertIn('total_cost', field_names,
                     "CementSale should have total_cost field")
    
    def test_cementsale_auto_calculates_totals(self):
        """Test that CementSale automatically calculates totals on save."""
        from inventory.models_verticals import CementSale
        from tenants.models import Business
        from inventory.models import MerchProduct
        from decimal import Decimal
        
        # Create test business
        business = Business.objects.create(
            name="Test Hardware Store",
            business_kind="cement",
        )
        
        # Create test product
        product = MerchProduct.objects.create(
            business=business,
            name="Test Cement",
            kind="cement",
            selling_price=Decimal("100.00"),
        )
        
        # Create sale without setting totals
        sale = CementSale.objects.create(
            business=business,
            product=product,
            quantity=5,
            unit_price=Decimal("100.00"),
            unit_cost=Decimal("80.00"),
        )
        
        # Verify totals were auto-calculated
        self.assertEqual(sale.total_price, Decimal("500.00"))
        self.assertEqual(sale.total_cost, Decimal("400.00"))
        self.assertEqual(sale.profit, Decimal("100.00"))


class TenantsMigrationTests(TestCase):
    """Test that tenants migrations are consistent."""
    
    def test_business_has_section_flags(self):
        """Test that Business model has section flag fields."""
        from tenants.models import Business
        
        field_names = [f.name for f in Business._meta.get_fields()]
        
        self.assertIn('has_cement_section', field_names,
                     "Business should have has_cement_section field")
        self.assertIn('has_groceries_section', field_names,
                     "Business should have has_groceries_section field")
        self.assertIn('has_cosmetics_section', field_names,
                     "Business should have has_cosmetics_section field")
    
    def test_business_kind_choices_include_cement(self):
        """Test that business_kind choices include cement."""
        from tenants.models import Business
        
        business_kind_field = Business._meta.get_field('business_kind')
        choices = [choice[0] for choice in business_kind_field.choices]
        
        self.assertIn('cement', choices,
                     "Business.business_kind choices should include 'cement'")

