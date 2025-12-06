"""
Test to ensure migration graph consistency.

This test catches invalid migration dependencies that would cause NodeNotFoundError,
such as migrations pointing to non-existent parent migrations.
"""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import NodeNotFoundError


@pytest.mark.django_db
def test_migration_graph_is_consistent():
    """
    Ensure Django can build the migration graph without NodeNotFoundError.
    
    This catches invalid dependencies like:
    - Migrations pointing to non-existent parent migrations
    - Circular dependencies
    - Gaps in the migration chain
    
    If this test fails, check the migration dependencies in the failing app
    and ensure they reference migrations that actually exist.
    """
    executor = MigrationExecutor(connection)
    try:
        # This is where Django validates all migration dependencies
        executor.loader.build_graph()
    except NodeNotFoundError as exc:
        pytest.fail(
            f"Inconsistent migration graph detected: {exc}\n\n"
            f"This usually means a migration file has a dependency on a migration "
            f"that doesn't exist. Check the migration files and fix the dependencies."
        )


@pytest.mark.django_db
def test_no_duplicate_migration_numbers():
    """
    Ensure there are no migrations with duplicate numbers in the same app.
    
    For example, having both 0004_add_feature_a.py and 0004_add_feature_b.py
    in the same app will cause migration conflicts.
    """
    from django.apps import apps
    from collections import defaultdict
    
    executor = MigrationExecutor(connection)
    loader = executor.loader
    
    # Group migrations by app and number
    migrations_by_app = defaultdict(lambda: defaultdict(list))
    
    for app_label, migration_name in loader.disk_migrations.keys():
        # Extract migration number (e.g., "0004" from "0004_add_feature")
        parts = migration_name.split('_')
        if parts[0].isdigit():
            number = parts[0]
            migrations_by_app[app_label][number].append(migration_name)
    
    # Check for duplicates
    duplicates = []
    for app_label, numbers in migrations_by_app.items():
        for number, migration_names in numbers.items():
            if len(migration_names) > 1:
                duplicates.append(f"{app_label}: {', '.join(migration_names)}")
    
    if duplicates:
        pytest.fail(
            f"Found migrations with duplicate numbers:\n" +
            "\n".join(f"  - {dup}" for dup in duplicates) +
            f"\n\nRename migrations to use unique sequential numbers."
        )

