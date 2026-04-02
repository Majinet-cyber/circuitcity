import sqlite3

conn = sqlite3.connect("db.sqlite3")

print("=== COLUMNS ===")
c = conn.execute("PRAGMA table_info(inventory_marketplacelisting)")
for r in c.fetchall():
    print(r[1], r[2])

print("\n=== INDICES ===")
c = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='inventory_marketplacelisting'")
for r in c.fetchall():
    print(r[0])

print("\n=== APPLIED MARKETPLACE MIGRATIONS ===")
c = conn.execute("SELECT app, name FROM django_migrations WHERE app='inventory' AND name LIKE '10%' ORDER BY name DESC LIMIT 20")
for r in c.fetchall():
    print(r[0], r[1])

conn.close()
