# Generated migration to fix EmailOTP table name variants
# Handles: accounts_email_otp, emailotp -> accounts_emailotp

from django.db import migrations


def rename_emailotp_table_variants(apps, schema_editor):
    """
    Conditionally rename EmailOTP table variants to the canonical name.

    Safe across environments:
    - If accounts_emailotp exists -> do nothing.
    - Else if accounts_email_otp exists -> rename to accounts_emailotp.
    - Else if emailotp exists -> rename to accounts_emailotp.
    - If none exist -> do nothing.

    Works on SQLite + Postgres.
    """
    connection = schema_editor.connection
    existing = {t.lower() for t in connection.introspection.table_names()}

    target = "accounts_emailotp"
    if target.lower() in existing:
        # Target table already exists, nothing to do
        return

    # Check for variant table names (in order of preference)
    candidates = ["accounts_email_otp", "emailotp"]
    source = next((c for c in candidates if c.lower() in existing), None)

    if not source:
        # No variant table found, nothing to do
        return

    # Rename the variant table to the canonical name
    qs = schema_editor.quote_name
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {qs(source)} RENAME TO {qs(target)}")


def reverse_rename_emailotp_table_variants(apps, schema_editor):
    """
    Reverse: rename accounts_emailotp back to emailotp if needed.
    Note: This is a best-effort reversal. In practice, the reverse may not be needed.
    """
    connection = schema_editor.connection
    existing = {t.lower() for t in connection.introspection.table_names()}

    source = "accounts_emailotp"
    target = "emailotp"

    if source.lower() in existing and target.lower() not in existing:
        qs = schema_editor.quote_name
        with connection.cursor() as cursor:
            cursor.execute(f"ALTER TABLE {qs(source)} RENAME TO {qs(target)}")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_remove_emailotp_accounts_em_email_377460_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(
            rename_emailotp_table_variants,
            reverse_rename_emailotp_table_variants,
        ),
    ]
