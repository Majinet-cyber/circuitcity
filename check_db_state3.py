import sqlite3

conn = sqlite3.connect("db.sqlite3")

print("=== ALL inventory_m* INDICES ===")
c = conn.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name LIKE 'inventory_m%' ORDER BY tbl_name, name")
for r in c.fetchall():
    print(r[0], "->", r[1])

print("\n=== MarketplaceEnquiry columns ===")
c = conn.execute("PRAGMA table_info(inventory_marketplaceenquiry)")
for r in c.fetchall():
    print(r[1], r[2])

print("\n=== MarketplaceListingImage table exists? ===")
c = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_marketplacelistingimage'")
result = c.fetchall()
print("EXISTS" if result else "MISSING")

conn.close()
