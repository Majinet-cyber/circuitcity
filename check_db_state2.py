import sqlite3

conn = sqlite3.connect("db.sqlite3")

print("=== TENANTS MIGRATIONS ===")
c = conn.execute("SELECT name FROM django_migrations WHERE app='tenants' ORDER BY name DESC LIMIT 10")
for r in c.fetchall():
    print(r[0])

conn.close()
