#!/usr/bin/env python
"""Quick check if accessories items are in sidebar config."""
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cc.settings")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from inventory.utils_verticals import get_vertical_sidebar_items

items = get_vertical_sidebar_items("phones")
acc_items = [i for i in items if "accessories" in i.get("key", "")]

print("=" * 60)
print("ACCESSORIES ITEMS IN PHONES SIDEBAR:")
print("=" * 60)
for item in acc_items:
    print(f"\nLabel: {item['label']}")
    print(f"Key: {item['key']}")
    print(f"URL: {item['url']}")
    print(f"Section: {item['section']}")
    print(f"testid: {item.get('testid', 'MISSING!!!')}")
    print(f"require_manager: {item.get('require_manager', False)}")

print("\n" + "=" * 60)
print(f"Total accessories items found: {len(acc_items)}")
print("=" * 60)

if len(acc_items) == 2:
    print("\n✅ SUCCESS: Both accessories items are in the config!")
else:
    print(f"\n❌ ERROR: Expected 2 items, found {len(acc_items)}")
    sys.exit(1)
