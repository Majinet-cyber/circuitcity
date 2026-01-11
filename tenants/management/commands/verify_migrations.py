"""
Management command to verify migrations are ready for deployment.
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from io import StringIO
import sys


class Command(BaseCommand):
    help = "Verify that migrations are ready for deployment (no errors, consistent state)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("="*70))
        self.stdout.write(self.style.SUCCESS("MIGRATION DEPLOYMENT READINESS CHECK"))
        self.stdout.write(self.style.SUCCESS("="*70))
        
        checks_passed = []
        checks_failed = []
        
        # Check 1: No unapplied migrations
        self.stdout.write("\n" + "="*70)
        self.stdout.write("CHECK 1: No unapplied model changes")
        self.stdout.write("="*70)
        try:
            call_command('makemigrations', '--check', '--dry-run', stdout=StringIO())
            self.stdout.write(self.style.SUCCESS("✓ PASS: No unapplied model changes"))
            checks_passed.append("No unapplied model changes")
        except SystemExit as e:
            if e.code == 0:
                self.stdout.write(self.style.SUCCESS("✓ PASS: No unapplied model changes"))
                checks_passed.append("No unapplied model changes")
            else:
                self.stdout.write(self.style.ERROR("✗ FAIL: Found unapplied model changes"))
                checks_failed.append("Unapplied model changes detected")
        
        # Check 2: Migration plan is valid
        self.stdout.write("\n" + "="*70)
        self.stdout.write("CHECK 2: Migration plan is consistent")
        self.stdout.write("="*70)
        try:
            output = StringIO()
            call_command('migrate', '--plan', stdout=output)
            plan_output = output.getvalue()
            
            # Check for obvious errors
            if 'InconsistentMigrationHistory' in plan_output or 'ConflictingMigrations' in plan_output:
                self.stdout.write(self.style.ERROR("✗ FAIL: Migration plan has conflicts"))
                self.stdout.write(plan_output)
                checks_failed.append("Migration plan conflicts")
            else:
                self.stdout.write(self.style.SUCCESS("✓ PASS: Migration plan is consistent"))
                self.stdout.write(f"Found {plan_output.count('Migrate:'):} migrations to apply")
                checks_passed.append("Migration plan consistent")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ FAIL: Error checking migration plan: {e}"))
            checks_failed.append("Migration plan error")
        
        # Check 3: Database connectivity
        self.stdout.write("\n" + "="*70)
        self.stdout.write("CHECK 3: Database connectivity")
        self.stdout.write("="*70)
        try:
            from django.db import connection
            connection.ensure_connection()
            self.stdout.write(self.style.SUCCESS(f"✓ PASS: Connected to {connection.vendor} database"))
            checks_passed.append("Database connectivity")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ FAIL: Cannot connect to database: {e}"))
            checks_failed.append("Database connection failed")
        
        # Summary
        self.stdout.write("\n" + "="*70)
        self.stdout.write("SUMMARY")
        self.stdout.write("="*70)
        
        total_checks = len(checks_passed) + len(checks_failed)
        self.stdout.write(f"\nPassed: {len(checks_passed)}/{total_checks}")
        
        if checks_passed:
            self.stdout.write("\nPassed checks:")
            for check in checks_passed:
                self.stdout.write(self.style.SUCCESS(f"  ✓ {check}"))
        
        if checks_failed:
            self.stdout.write("\nFailed checks:")
            for check in checks_failed:
                self.stdout.write(self.style.ERROR(f"  ✗ {check}"))
            self.stdout.write(self.style.ERROR("\n✗ MIGRATIONS NOT READY FOR DEPLOYMENT"))
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("\n✓ ALL CHECKS PASSED - Migrations are ready!"))
            sys.exit(0)

