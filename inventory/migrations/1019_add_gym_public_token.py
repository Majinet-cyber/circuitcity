"""
Add public_token field to GymMember for short, non-guessable public status links.
Also backfills existing members with unique tokens.

Migration steps:
1. Add public_token field WITHOUT unique constraint (allow duplicates) - IDEMPOTENT
2. Backfill all existing members with unique tokens
3. Add unique constraint after backfill - IDEMPOTENT

IDEMPOTENCY:
This migration is safe to run multiple times. It checks if column/indexes exist before
creating them, which fixes the Render deploy issue with pre-existing _like indexes.
"""
import secrets

from django.db import migrations, models


def add_public_token_column_idempotent(apps, schema_editor):
    """
    Idempotently add public_token column and indexes.
    Safe to run even if column/indexes already exist.
    """
    connection = schema_editor.connection
    vendor = connection.vendor
    
    if vendor == "postgresql":
        with connection.cursor() as cursor:
            # Check if column exists
            cursor.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'inventory_gymmember'
                AND column_name = 'public_token'
            """)
            column_exists = cursor.fetchone() is not None
            
            # Add column if missing
            if not column_exists:
                cursor.execute("""
                    ALTER TABLE inventory_gymmember
                    ADD COLUMN public_token varchar(22) NULL
                """)
            
            # Drop problematic LIKE index if it exists (safe to recreate)
            cursor.execute("""
                DROP INDEX IF EXISTS inventory_gymmember_public_token_208110ff_like
            """)
            
            # Ensure standard btree index exists
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS inventory_gymmember_public_token_208110ff
                ON inventory_gymmember (public_token)
            """)
            
            # Recreate LIKE index with varchar_pattern_ops (PostgreSQL-specific)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS inventory_gymmember_public_token_208110ff_like
                ON inventory_gymmember (public_token varchar_pattern_ops)
            """)
    
    elif vendor == "sqlite":
        with connection.cursor() as cursor:
            # Check if column exists
            cursor.execute("PRAGMA table_info(inventory_gymmember)")
            columns = {row[1] for row in cursor.fetchall()}
            
            if "public_token" not in columns:
                # Add column if missing
                cursor.execute("""
                    ALTER TABLE inventory_gymmember
                    ADD COLUMN public_token varchar(22) NULL
                """)
            
            # Create index if not exists (SQLite supports this)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS inventory_gymmember_public_token_208110ff
                ON inventory_gymmember (public_token)
            """)
    
    else:
        # For other vendors, try to add via schema_editor if column doesn't exist
        # This is a best-effort fallback
        pass


def add_unique_constraint_idempotent(apps, schema_editor):
    """
    Idempotently add unique constraint to public_token.
    Safe to run even if constraint/index already exists.
    """
    connection = schema_editor.connection
    vendor = connection.vendor
    
    if vendor == "postgresql":
        with connection.cursor() as cursor:
            # Drop existing unique constraint/index if it exists
            cursor.execute("""
                DROP INDEX IF EXISTS inventory_gymmember_public_token_key
            """)
            cursor.execute("""
                DROP INDEX IF EXISTS inventory_gymmember_public_token_208110ff_uniq
            """)
            
            # Create unique index (idempotent)
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS inventory_gymmember_public_token_key
                ON inventory_gymmember (public_token)
            """)
    
    elif vendor == "sqlite":
        with connection.cursor() as cursor:
            # Check if unique index already exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type = 'index'
                AND tbl_name = 'inventory_gymmember'
                AND name LIKE '%public_token%'
                AND sql LIKE '%UNIQUE%'
            """)
            unique_exists = cursor.fetchone() is not None
            
            if not unique_exists:
                # Create unique index
                cursor.execute("""
                    CREATE UNIQUE INDEX inventory_gymmember_public_token_key
                    ON inventory_gymmember (public_token)
                """)
    
    else:
        # Best-effort fallback for other vendors
        pass


def generate_unique_public_token(apps, schema_editor):
    """Backfill existing GymMember records with unique public_token values."""
    GymMember = apps.get_model("inventory", "GymMember")
    
    # Track all generated tokens to ensure uniqueness
    existing_tokens = set(
        GymMember.objects.exclude(public_token="").exclude(public_token__isnull=True).values_list("public_token", flat=True)
    )
    
    members_to_update = GymMember.objects.filter(public_token="") | GymMember.objects.filter(public_token__isnull=True)
    
    for member in members_to_update:
        # Generate unique token
        for _ in range(100):  # More retries for safety
            token = secrets.token_urlsafe(16)[:22]
            if token not in existing_tokens:
                member.public_token = token
                existing_tokens.add(token)
                member.save(update_fields=["public_token"])
                break
        else:
            # Fallback: extremely unlikely but generate another token
            token = secrets.token_urlsafe(16)[:22]
            member.public_token = token
            member.save(update_fields=["public_token"])


def reverse_backfill(apps, schema_editor):
    """Clear public_token on reverse (for rollback safety, though typically no-op)."""
    # No-op: we don't want to lose tokens on rollback
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1018_clothingbarcodeunit"),
        ("inventory", "0115_alter_agentprofile_location"),
    ]

    operations = [
        # Step 1: Add the public_token field WITHOUT unique constraint
        # Use SeparateDatabaseAndState to make DB operations idempotent
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # Update Django's migration state to include the field
                migrations.AddField(
                    model_name="gymmember",
                    name="public_token",
                    field=models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="Non-guessable token for public member status page (URL-safe)",
                        max_length=22,
                        null=True,  # Allow null temporarily
                    ),
                ),
            ],
            database_operations=[
                # Idempotent DB operation that checks before creating
                migrations.RunPython(
                    add_public_token_column_idempotent,
                    reverse_code=migrations.RunPython.noop,
                ),
            ],
        ),
        # Step 2: Backfill existing members with unique tokens
        migrations.RunPython(generate_unique_public_token, reverse_backfill),
        # Step 3: Add unique constraint now that all values are populated
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # Update Django's migration state to add unique constraint
                migrations.AlterField(
                    model_name="gymmember",
                    name="public_token",
                    field=models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="Non-guessable token for public member status page (URL-safe)",
                        max_length=22,
                        unique=True,
                    ),
                ),
            ],
            database_operations=[
                # Idempotent DB operation that checks before creating unique constraint
                migrations.RunPython(
                    add_unique_constraint_idempotent,
                    reverse_code=migrations.RunPython.noop,
                ),
            ],
        ),
    ]
