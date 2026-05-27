"""Check FK violations across all tables to find root cause of FOREIGN KEY constraint failed."""
import sqlite3, os, sys

db_path = os.path.join(os.path.dirname(__file__), 'db.sqlite3')
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Enable FK enforcement
cur.execute("PRAGMA foreign_keys = ON")

# Get all tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
all_tables = [r[0] for r in cur.fetchall()]

print(f"Checking {len(all_tables)} tables for FK violations...\n")
any_violations = False
for tbl in all_tables:
    try:
        cur.execute(f"PRAGMA foreign_key_check({tbl})")
        violations = cur.fetchall()
        if violations:
            any_violations = True
            print(f"VIOLATION in {tbl}:")
            for v in violations[:5]:
                print(f"  {v}")
    except Exception as e:
        print(f"  Error checking {tbl}: {e}")

if not any_violations:
    print("No FK violations found in any table.")

# Now check inventory_grocerysale FK list explicitly
print("\n--- GrocerySale FK constraints ---")
cur.execute("PRAGMA foreign_key_list(inventory_grocerysale)")
for r in cur.fetchall():
    print(r)

# Check if AgentProfile has any FK issues
print("\n--- inventory_agentprofile FK check ---")
cur.execute("PRAGMA foreign_key_check(inventory_agentprofile)")
for r in cur.fetchall():
    print("VIOLATION:", r)

conn.close()
print("\nDone.")
