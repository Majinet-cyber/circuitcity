"""
Direct SQLite migration script for marketplace status column.
Applies: tenants/0032, inventory/1041, inventory/1042, inventory/1043 schema changes.
Runs standalone without Django manage.py startup overhead.
"""
import sqlite3
import sys

DB = "db.sqlite3"

conn = sqlite3.connect(DB)
conn.execute("PRAGMA foreign_keys = OFF")
conn.execute("PRAGMA journal_mode = WAL")

def already_applied(app, name):
    c = conn.execute(
        "SELECT COUNT(*) FROM django_migrations WHERE app=? AND name=?",
        (app, name)
    )
    return c.fetchone()[0] > 0

def mark_applied(app, name):
    conn.execute(
        "INSERT INTO django_migrations (app, name, applied) VALUES (?, ?, datetime('now'))",
        (app, name)
    )
    conn.commit()
    print(f"  Marked {app}/{name} as applied.")

def column_exists(table, col):
    c = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in c.fetchall())

def table_exists(tbl):
    c = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
    )
    return c.fetchone()[0] > 0

def index_exists(name):
    c = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name=?", (name,)
    )
    return c.fetchone()[0] > 0

print("=== Starting marketplace migration fix ===\n")

# ─── tenants/0032 ──────────────────────────────────────────────────────────────
if not already_applied("tenants", "0032_marketplace_upgrade_and_car_dealer"):
    print("Applying tenants/0032 (alter business.business_kind)...")
    # This migration only alters choices metadata, no schema change needed in SQLite
    mark_applied("tenants", "0032_marketplace_upgrade_and_car_dealer")
else:
    print("tenants/0032 already applied.")

# ─── inventory/1041 ────────────────────────────────────────────────────────────
if not already_applied("inventory", "1041_marketplace_upgrade_and_car_dealer"):
    print("\nApplying inventory/1041 (marketplace upgrade)...")

    # 1. Create MarketplaceListingImage table
    if not table_exists("inventory_marketplacelistingimage"):
        print("  Creating inventory_marketplacelistingimage...")
        conn.execute("""
            CREATE TABLE "inventory_marketplacelistingimage" (
                "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                "image" varchar(100) NOT NULL,
                "caption" varchar(200) NOT NULL DEFAULT '',
                "sort_order" smallint unsigned NOT NULL DEFAULT 0,
                "uploaded_at" datetime NOT NULL,
                "listing_id" bigint NOT NULL REFERENCES "inventory_marketplacelisting" ("id")
            )
        """)
        conn.execute("""
            CREATE INDEX "inventory_marketplacelistingimage_sort_order_idx"
            ON "inventory_marketplacelistingimage" ("sort_order")
        """)
        conn.execute("""
            CREATE INDEX "inventory_marketplacelistingimage_uploaded_at_idx"
            ON "inventory_marketplacelistingimage" ("uploaded_at")
        """)
        conn.execute("""
            CREATE INDEX "inventory_marketplacelistingimage_listing_id_idx"
            ON "inventory_marketplacelistingimage" ("listing_id")
        """)
        conn.commit()

    # 2. Add status field to MarketplaceListing (replaces is_active)
    if not column_exists("inventory_marketplacelisting", "status"):
        print("  Adding status column to inventory_marketplacelisting...")
        conn.execute(
            "ALTER TABLE inventory_marketplacelisting ADD COLUMN "
            "\"status\" varchar(20) NOT NULL DEFAULT 'draft'"
        )
        conn.commit()

    # 3. Add listing_slug
    if not column_exists("inventory_marketplacelisting", "listing_slug"):
        print("  Adding listing_slug column...")
        conn.execute(
            "ALTER TABLE inventory_marketplacelisting ADD COLUMN "
            "\"listing_slug\" varchar(100) NOT NULL DEFAULT ''"
        )
        conn.commit()

    # 4. Add address
    if not column_exists("inventory_marketplacelisting", "address"):
        print("  Adding address column...")
        conn.execute(
            "ALTER TABLE inventory_marketplacelisting ADD COLUMN "
            "\"address\" varchar(200) NOT NULL DEFAULT ''"
        )
        conn.commit()

    # 5. Add contact_phone
    if not column_exists("inventory_marketplacelisting", "contact_phone"):
        print("  Adding contact_phone column...")
        conn.execute(
            "ALTER TABLE inventory_marketplacelisting ADD COLUMN "
            "\"contact_phone\" varchar(30) NOT NULL DEFAULT ''"
        )
        conn.commit()

    # 6. Add contact_email
    if not column_exists("inventory_marketplacelisting", "contact_email"):
        print("  Adding contact_email column...")
        conn.execute(
            "ALTER TABLE inventory_marketplacelisting ADD COLUMN "
            "\"contact_email\" varchar(254) NOT NULL DEFAULT ''"
        )
        conn.commit()

    # 7. Add location_text
    if not column_exists("inventory_marketplacelisting", "location_text"):
        print("  Adding location_text column...")
        conn.execute(
            "ALTER TABLE inventory_marketplacelisting ADD COLUMN "
            "\"location_text\" varchar(200) NOT NULL DEFAULT ''"
        )
        conn.commit()

    # 8. Add vertical_metadata (JSON stored as TEXT in SQLite)
    if not column_exists("inventory_marketplacelisting", "vertical_metadata"):
        print("  Adding vertical_metadata column...")
        conn.execute(
            "ALTER TABLE inventory_marketplacelisting ADD COLUMN "
            "\"vertical_metadata\" text NOT NULL DEFAULT '{}'"
        )
        conn.commit()

    # 9. Add inventory_item_id FK
    if not column_exists("inventory_marketplacelisting", "inventory_item_id"):
        print("  Adding inventory_item_id column...")
        conn.execute(
            "ALTER TABLE inventory_marketplacelisting ADD COLUMN "
            "\"inventory_item_id\" bigint NULL REFERENCES \"inventory_inventoryitem\" (\"id\")"
        )
        conn.commit()

    # 10. Drop old is_active-based indexes and add status-based ones
    for old_idx in ("inventory_m_busines_b3b99a_idx", "inventory_m_vertica_7bba40_idx"):
        if index_exists(old_idx):
            print(f"  Dropping old index {old_idx}...")
            conn.execute(f'DROP INDEX IF EXISTS "{old_idx}"')
            conn.commit()

    if not index_exists("inventory_m_busines_7c9c74_idx"):
        print("  Creating index (business, status)...")
        conn.execute(
            "CREATE INDEX \"inventory_m_busines_7c9c74_idx\" "
            "ON \"inventory_marketplacelisting\" (\"business_id\", \"status\")"
        )
        conn.commit()

    if not index_exists("inventory_m_vertica_9183b2_idx"):
        print("  Creating index (vertical, status)...")
        conn.execute(
            "CREATE INDEX \"inventory_m_vertica_9183b2_idx\" "
            "ON \"inventory_marketplacelisting\" (\"vertical\", \"status\")"
        )
        conn.commit()

    if not index_exists("inventory_m_busines_b0bd78_idx"):
        print("  Creating index (business, listing_slug)...")
        conn.execute(
            "CREATE INDEX \"inventory_m_busines_b0bd78_idx\" "
            "ON \"inventory_marketplacelisting\" (\"business_id\", \"listing_slug\")"
        )
        conn.commit()

    # Add db_index on status
    if not index_exists("inventory_marketplacelisting_status_idx"):
        conn.execute(
            "CREATE INDEX \"inventory_marketplacelisting_status_idx\" "
            "ON \"inventory_marketplacelisting\" (\"status\")"
        )
        conn.commit()

    mark_applied("inventory", "1041_marketplace_upgrade_and_car_dealer")
else:
    print("inventory/1041 already applied.")

# ─── inventory/1042 ────────────────────────────────────────────────────────────
if not already_applied("inventory", "1042_backfill_marketplace_listing_status"):
    print("\nApplying inventory/1042 (backfill status = live for old rows)...")
    # All existing rows had is_active=True by default → set to 'live'
    result = conn.execute(
        "UPDATE inventory_marketplacelisting SET status='live' WHERE status='draft'"
    )
    print(f"  Updated {result.rowcount} existing listings to 'live'.")
    conn.commit()
    mark_applied("inventory", "1042_backfill_marketplace_listing_status")
else:
    print("inventory/1042 already applied.")

# ─── inventory/1043 ────────────────────────────────────────────────────────────
# Migration 1043 creates CarMake, CarModel, CarDealerVehicle tables etc.
# Check if the table already exists (might have been created by another path)
if not already_applied("inventory", "1043_car_dealer_vehicle_models"):
    print("\nApplying inventory/1043 schema check (car dealer models)...")
    if not table_exists("inventory_carmake"):
        print("  CarMake table missing — creating car dealer tables...")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS "inventory_carmake" (
                "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                "name" varchar(100) NOT NULL UNIQUE,
                "created_at" datetime NOT NULL
            );

            CREATE TABLE IF NOT EXISTS "inventory_carmodel" (
                "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                "name" varchar(100) NOT NULL,
                "year_introduced" smallint unsigned NULL,
                "year_discontinued" smallint unsigned NULL,
                "make_id" bigint NOT NULL REFERENCES "inventory_carmake" ("id"),
                "created_at" datetime NOT NULL
            );

            CREATE TABLE IF NOT EXISTS "inventory_cardealervehicle" (
                "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                "vin" varchar(50) NOT NULL DEFAULT '',
                "year" smallint unsigned NOT NULL,
                "color" varchar(50) NOT NULL DEFAULT '',
                "mileage_km" integer unsigned NULL,
                "condition" varchar(20) NOT NULL DEFAULT 'used',
                "transmission" varchar(20) NOT NULL DEFAULT 'manual',
                "fuel_type" varchar(20) NOT NULL DEFAULT 'petrol',
                "body_type" varchar(20) NOT NULL DEFAULT 'sedan',
                "asking_price" decimal NOT NULL DEFAULT 0,
                "cost_price" decimal NULL,
                "status" varchar(20) NOT NULL DEFAULT 'available',
                "description" varchar(1000) NOT NULL DEFAULT '',
                "notes" varchar(500) NOT NULL DEFAULT '',
                "date_acquired" date NOT NULL,
                "date_sold" date NULL,
                "sold_price" decimal NULL,
                "business_id" bigint NOT NULL REFERENCES "tenants_business" ("id"),
                "make_id" bigint NOT NULL REFERENCES "inventory_carmake" ("id"),
                "model_id" bigint NOT NULL REFERENCES "inventory_carmodel" ("id"),
                "sold_by_id" integer NULL REFERENCES "accounts_user" ("id"),
                "created_by_id" integer NULL REFERENCES "accounts_user" ("id"),
                "created_at" datetime NOT NULL,
                "updated_at" datetime NOT NULL
            );

            CREATE TABLE IF NOT EXISTS "inventory_cardealervehicleimage" (
                "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                "image" varchar(100) NOT NULL,
                "caption" varchar(200) NOT NULL DEFAULT '',
                "sort_order" smallint unsigned NOT NULL DEFAULT 0,
                "uploaded_at" datetime NOT NULL,
                "vehicle_id" bigint NOT NULL REFERENCES "inventory_cardealervehicle" ("id")
            );

            CREATE TABLE IF NOT EXISTS "inventory_maintenancerecord" (
                "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                "maintenance_type" varchar(30) NOT NULL,
                "description" varchar(500) NOT NULL DEFAULT '',
                "cost" decimal NOT NULL DEFAULT 0,
                "date" date NOT NULL,
                "vehicle_id" bigint NOT NULL REFERENCES "inventory_cardealervehicle" ("id"),
                "created_by_id" integer NULL REFERENCES "accounts_user" ("id"),
                "created_at" datetime NOT NULL
            );
        """)
        conn.commit()
        print("  Car dealer tables created.")
    else:
        print("  Car dealer tables already exist.")
    mark_applied("inventory", "1043_car_dealer_vehicle_models")
else:
    print("inventory/1043 already applied.")

print("\n=== Migration fix complete ===")

# Verify
print("\nVerification:")
c = conn.execute("PRAGMA table_info(inventory_marketplacelisting)")
cols = [row[1] for row in c.fetchall()]
print("Columns:", cols)
assert "status" in cols, "ERROR: status column missing!"
print("✓ status column present")

c2 = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_marketplacelistingimage'")
assert c2.fetchone(), "ERROR: MarketplaceListingImage table missing!"
print("✓ MarketplaceListingImage table present")

print("\nAll checks passed!")
conn.close()
