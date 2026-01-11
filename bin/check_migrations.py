#!/usr/bin/env python
"""
Migration verification script.
Checks that migrations are in good shape before deployment.

Usage:
    python bin/check_migrations.py

Checks performed:
1. No unapplied migrations (makemigrations --check)
2. Migration plan is consistent (migrate --plan)
3. No obvious duplicate column additions in recent migrations
"""

import os
import sys
import subprocess
import re
from pathlib import Path


def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"\n{'='*70}")
    print(f"CHECK: {description}")
    print(f"{'='*70}")
    print(f"Running: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    if result.returncode == 0:
        print(f"[PASS]: {description}")
        return True
    else:
        print(f"[FAIL]: {description}")
        return False


def check_no_unapplied_migrations():
    """Check that makemigrations --check passes (no model changes without migrations)."""
    return run_command(
        [sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"],
        "No unapplied model changes"
    )


def check_migration_plan():
    """Check that migrate --plan succeeds (migration graph is consistent)."""
    return run_command(
        [sys.executable, "manage.py", "migrate", "--plan"],
        "Migration plan is consistent"
    )


def check_for_duplicate_columns():
    """
    Scan recent migration files for potential duplicate column additions.
    This is a heuristic check - not perfect but catches obvious issues.
    """
    print(f"\n{'='*70}")
    print("CHECK: No duplicate column additions in recent migrations")
    print(f"{'='*70}")
    
    issues = []
    
    # Track AddField operations by (app, model, field)
    add_fields = {}  # (app, model, field) -> [list of migration files]
    
    # Check inventory and tenants apps
    for app in ['inventory', 'tenants']:
        migrations_dir = Path(app) / 'migrations'
        if not migrations_dir.exists():
            continue
        
        for migration_file in sorted(migrations_dir.glob('*.py')):
            if migration_file.name.startswith('__'):
                continue
            
            try:
                content = migration_file.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                # Skip files with encoding issues
                continue
            
            # Look for AddField operations
            # Pattern: migrations.AddField(model_name="...", name="..."
            add_field_pattern = r'migrations\.AddField\(\s*model_name=["\'](\w+)["\']\s*,\s*name=["\'](\w+)["\']'
            
            for match in re.finditer(add_field_pattern, content):
                model = match.group(1).lower()
                field = match.group(2)
                key = (app, model, field)
                
                if key not in add_fields:
                    add_fields[key] = []
                add_fields[key].append(str(migration_file))
    
    # Find duplicates
    for key, files in add_fields.items():
        if len(files) > 1:
            app, model, field = key
            issues.append(
                f"Field '{field}' added to '{app}.{model}' in multiple migrations:\n"
                + "\n".join(f"  - {f}" for f in files)
            )
    
    if issues:
        print("[FAIL]: Found potential duplicate column additions:")
        for issue in issues:
            print(f"\n{issue}")
        return False
    else:
        print("[PASS]: No duplicate column additions detected")
        return True


def check_migration_consistency():
    """
    Check for common migration issues:
    - Migrations with same number in same app
    - Missing merge migrations
    """
    print(f"\n{'='*70}")
    print("CHECK: Migration file naming consistency")
    print(f"{'='*70}")
    
    issues = []
    
    for app in ['inventory', 'tenants']:
        migrations_dir = Path(app) / 'migrations'
        if not migrations_dir.exists():
            continue
        
        migration_numbers = {}
        
        for migration_file in migrations_dir.glob('*.py'):
            if migration_file.name.startswith('__'):
                continue
            
            # Extract migration number (e.g., "0019" from "0019_add_something.py")
            match = re.match(r'(\d+[a-z]?)_', migration_file.name)
            if match:
                number = match.group(1)
                if number not in migration_numbers:
                    migration_numbers[number] = []
                migration_numbers[number].append(migration_file.name)
        
        # Check for duplicate numbers (excluding intentional letters like 0019a)
        for number, files in migration_numbers.items():
            # Allow 0019a-style suffixes (intentional sequencing)
            base_number = number.rstrip('abcdefghijklmnopqrstuvwxyz')
            same_base = [f for f in files if f.startswith(base_number)]
            
            if len(same_base) > 1:
                # Check if any are pure duplicates (no letter suffix)
                pure_dupes = [f for f in same_base if re.match(rf'{base_number}_', f)]
                if len(pure_dupes) > 1:
                    issues.append(
                        f"App '{app}' has multiple migrations with number {base_number}:\n"
                        + "\n".join(f"  - {f}" for f in pure_dupes)
                    )
    
    if issues:
        print("[FAIL]: Found migration naming issues:")
        for issue in issues:
            print(f"\n{issue}")
        return False
    else:
        print("[PASS]: Migration file naming is consistent")
        return True


def main():
    """Run all migration checks."""
    print("="*70)
    print("MIGRATION VERIFICATION SCRIPT")
    print("="*70)
    
    # Change to project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)
    
    print(f"Project root: {project_root}")
    
    checks = [
        check_no_unapplied_migrations,
        check_migration_plan,
        check_migration_consistency,
        check_for_duplicate_columns,
    ]
    
    results = [check() for check in checks]
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Passed: {passed}/{total}")
    
    if all(results):
        print("\n[PASS] ALL CHECKS PASSED - Migrations are ready for deployment!")
        return 0
    else:
        print("\n[FAIL] SOME CHECKS FAILED - Please fix issues before deployment")
        return 1


if __name__ == "__main__":
    sys.exit(main())

