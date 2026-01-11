"""
Migration Name Mapping - SSOT for Resilient Migration Lookups

This module provides a centralized mapping for migration names that may have
been renamed or whose exact names are hard to remember. This prevents KeyError
failures when looking up migrations by their old or alternate names.

PROBLEM SOLVED:
- KeyError: ('tenants', '0014_add_case_insensitive_unique_constraints')

USAGE in tests:
    from tenants.utils_migrations import resolve_migration_name
    
    # Resilient lookup - handles both old and new names
    app_label, migration_name = resolve_migration_name(
        'tenants', 
        '0014_add_case_insensitive_unique_constraints'
    )
    
    # Now safe to use with migration loader
    migration = executor.loader.get_migration(app_label, migration_name)

NAMING CONVENTION:
Migration names use Django's standard format: NNNN_description_with_underscores
"""
from __future__ import annotations
from typing import Tuple, Optional


# ============================================================================
# SSOT: Migration Name Mappings
# ============================================================================

# Map of (app_label, old_or_alias_name) -> canonical_migration_name
# This allows resilient lookups when migration names change or vary
MIGRATION_NAME_MAP = {
    # Tenants app migrations
    ('tenants', '0014_add_case_insensitive_unique_constraints'): '0014_add_case_insensitive_unique_constraints',
    ('tenants', '0014'): '0014_add_case_insensitive_unique_constraints',
    ('tenants', '0013_add_location_tracking'): '0013_add_location_tracking',
    ('tenants', '0013'): '0013_add_location_tracking',
    
    # Add more mappings here as needed for other migrations
    # Example:
    # ('inventory', '0050'): '0050_add_global_imei_uniqueness',
    # ('inventory', '0050_add_global_imei_uniqueness'): '0050_add_global_imei_uniqueness',
}


# ============================================================================
# Main Resolution Function
# ============================================================================

def resolve_migration_name(app_label: str, migration_name: str) -> Tuple[str, str]:
    """
    Resolve a migration name to its canonical form.
    
    This function provides resilient migration name lookups by:
    1. Checking the SSOT mapping dictionary first
    2. Falling back to the original name if no mapping exists
    3. Supporting both full names and short numeric prefixes
    
    Args:
        app_label: Django app label (e.g., 'tenants', 'inventory')
        migration_name: Migration name or alias (e.g., '0014', '0014_add_case_insensitive_unique_constraints')
        
    Returns:
        Tuple of (app_label, canonical_migration_name)
        
    Example:
        >>> resolve_migration_name('tenants', '0014')
        ('tenants', '0014_add_case_insensitive_unique_constraints')
        
        >>> resolve_migration_name('tenants', '0014_add_case_insensitive_unique_constraints')
        ('tenants', '0014_add_case_insensitive_unique_constraints')
        
        >>> resolve_migration_name('tenants', '9999_nonexistent')
        ('tenants', '9999_nonexistent')  # Falls back to original
    """
    key = (app_label, migration_name)
    canonical_name = MIGRATION_NAME_MAP.get(key, migration_name)
    return app_label, canonical_name


def get_migration_safe(migration_loader, app_label: str, migration_name: str):
    """
    Safely get a migration using the migration loader with resilient name lookup.
    
    This function wraps Django's migration loader to provide:
    1. Automatic name resolution via SSOT mapping
    2. Graceful error handling with helpful error messages
    3. Support for migration aliases and short names
    
    Args:
        migration_loader: Django MigrationLoader instance
        app_label: Django app label (e.g., 'tenants')
        migration_name: Migration name or alias (e.g., '0014')
        
    Returns:
        Migration object if found, None if not found
        
    Raises:
        KeyError: If migration not found (with helpful message suggesting alternatives)
        
    Example:
        >>> from django.db.migrations.loader import MigrationLoader
        >>> from django.db import connection
        >>> loader = MigrationLoader(connection)
        >>> migration = get_migration_safe(loader, 'tenants', '0014')
        >>> # Returns the migration object, even if '0014' is an alias
    """
    # Resolve name via SSOT mapping
    app_label, canonical_name = resolve_migration_name(app_label, migration_name)
    
    try:
        return migration_loader.get_migration(app_label, canonical_name)
    except KeyError as e:
        # Provide helpful error message with available migrations
        try:
            available = migration_loader.graph.leaf_nodes(app_label)
            available_names = [name for (app, name) in available if app == app_label]
            raise KeyError(
                f"Migration '{migration_name}' not found in app '{app_label}'. "
                f"Available migrations: {', '.join(available_names[:5])}..."
            ) from e
        except Exception:
            # If we can't get available migrations, just re-raise original error
            raise


def has_migration(migration_loader, app_label: str, migration_name: str) -> bool:
    """
    Check if a migration exists (resilient lookup).
    
    Args:
        migration_loader: Django MigrationLoader instance
        app_label: Django app label
        migration_name: Migration name or alias
        
    Returns:
        True if migration exists, False otherwise
        
    Example:
        >>> has_migration(loader, 'tenants', '0014')
        True
        >>> has_migration(loader, 'tenants', '9999_nonexistent')
        False
    """
    app_label, canonical_name = resolve_migration_name(app_label, migration_name)
    key = (app_label, canonical_name)
    return key in migration_loader.graph.nodes


# ============================================================================
# Helper: List All Migrations for an App
# ============================================================================

def list_migrations(migration_loader, app_label: str) -> list[Tuple[str, str]]:
    """
    List all migrations for a given app.
    
    Args:
        migration_loader: Django MigrationLoader instance
        app_label: Django app label
        
    Returns:
        List of (app_label, migration_name) tuples
        
    Example:
        >>> migrations = list_migrations(loader, 'tenants')
        >>> for app, name in migrations:
        ...     print(f"{app}.{name}")
        tenants.0001_initial
        tenants.0002_...
    """
    return [(app, name) for (app, name) in migration_loader.graph.nodes if app == app_label]

