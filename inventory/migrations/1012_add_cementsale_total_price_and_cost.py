# Generated manually to fix missing total_price and total_cost columns
# Made IDEMPOTENT to handle cases where columns may already exist

from decimal import Decimal

from django.db import migrations, models


def backfill_totals(apps, schema_editor):
    """
    Backfill total_price and total_cost for existing CementSale rows.
    Compute from quantity * unit_price and quantity * unit_cost.
    Safe to run multiple times - only updates rows where totals are 0.
    """
    CementSale = apps.get_model("inventory", "CementSale")

    # Update rows that have zero totals (need backfill)
    for sale in CementSale.objects.filter(total_price=0, total_cost=0):
        sale.total_price = Decimal(sale.quantity) * sale.unit_price
        sale.total_cost = Decimal(sale.quantity) * sale.unit_cost
        sale.save(update_fields=["total_price", "total_cost"])


def add_columns_idempotent(apps, schema_editor):
    """
    Add total_price and total_cost columns using idempotent SQL.
    Uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS for Postgres.
    For SQLite, checks existing columns first.
    """
    connection = schema_editor.connection
    db_vendor = connection.vendor
    
    CementSale = apps.get_model("inventory", "CementSale")
    table_name = CementSale._meta.db_table
    quoted_table = connection.ops.quote_name(table_name)
    
    if db_vendor == 'postgresql':
        with connection.cursor() as cursor:
            # Add total_price if not exists
            cursor.execute(f"""
                ALTER TABLE {quoted_table}
                ADD COLUMN IF NOT EXISTS total_price NUMERIC(12, 2) DEFAULT 0.00 NOT NULL
            """)
            
            # Add total_cost if not exists
            cursor.execute(f"""
                ALTER TABLE {quoted_table}
                ADD COLUMN IF NOT EXISTS total_cost NUMERIC(12, 2) DEFAULT 0.00 NOT NULL
            """)
            
    elif db_vendor == 'sqlite':
        with connection.cursor() as cursor:
            # Check existing columns
            cursor.execute(f"PRAGMA table_info({quoted_table})")
            existing_columns = {row[1] for row in cursor.fetchall()}
            
            if 'total_price' not in existing_columns:
                cursor.execute(f"""
                    ALTER TABLE {quoted_table}
                    ADD COLUMN total_price DECIMAL(12, 2) DEFAULT 0.00 NOT NULL
                """)
            
            if 'total_cost' not in existing_columns:
                cursor.execute(f"""
                    ALTER TABLE {quoted_table}
                    ADD COLUMN total_cost DECIMAL(12, 2) DEFAULT 0.00 NOT NULL
                """)


class Migration(migrations.Migration):
    """
    Idempotent migration to add total_price and total_cost to CementSale.
    
    SAFETY:
    - Uses ADD COLUMN IF NOT EXISTS on Postgres
    - Checks existing columns on SQLite
    - Safe to run on databases where columns already exist
    - Safe to run on fresh databases where columns don't exist
    - SeparateDatabaseAndState ensures Django's state is updated correctly
    """
    
    dependencies = [
        ("inventory", "1011_pharmacy_packaging_fields"),
    ]

    operations = [
        # Database operations: Add columns idempotently using raw SQL
        migrations.RunPython(
            add_columns_idempotent,
            reverse_code=migrations.RunPython.noop,
        ),
        
        # State operations: Register fields in Django's migration state
        # These are separate so state updates even if columns already exist
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # Database changes already done above
            ],
            state_operations=[
                migrations.AddField(
                    model_name="cementsale",
                    name="total_price",
                    field=models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        default=Decimal("0.00"),
                    ),
                    preserve_default=True,
                ),
                migrations.AddField(
                    model_name="cementsale",
                    name="total_cost",
                    field=models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        default=Decimal("0.00"),
                        help_text="Total cost of goods sold",
                    ),
                    preserve_default=True,
                ),
            ],
        ),
        
        # Backfill existing rows (idempotent - only updates zeros)
        migrations.RunPython(
            backfill_totals,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
