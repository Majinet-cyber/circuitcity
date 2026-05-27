#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Manual verification of cement brand alias and paint size requirements.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cc.settings")
django.setup()

from inventory.cement_seed import is_cement_brand, normalize_cement_brand_name
from inventory.catalog.construction_materials import normalize_brand, get_paint_sizes

print("=" * 60)
print("CEMENT BRAND NORMALIZATION TESTS")
print("=" * 60)

# Test 1: is_cement_brand with alias
test1 = is_cement_brand("aksher")
print(f"[PASS] is_cement_brand('aksher') = {test1}")
assert test1 is True, "FAILED: is_cement_brand('aksher') should be True"

# Test 2: is_cement_brand with canonical
test2 = is_cement_brand("Akshar")
print(f"[PASS] is_cement_brand('Akshar') = {test2}")
assert test2 is True, "FAILED: is_cement_brand('Akshar') should be True"

# Test 3: normalize_cement_brand_name with alias
test3 = normalize_cement_brand_name("aksher")
print(f"[PASS] normalize_cement_brand_name('aksher') = '{test3}'")
assert test3 == "Akshar", f"FAILED: Expected 'Akshar', got '{test3}'"

# Test 4: normalize_cement_brand_name with uppercase
test4 = normalize_cement_brand_name("AKSHAR")
print(f"[PASS] normalize_cement_brand_name('AKSHAR') = '{test4}'")
assert test4 == "Akshar", f"FAILED: Expected 'Akshar', got '{test4}'"

# Test 5: normalize_brand from SSOT
test5 = normalize_brand("aksher", "cement")
print(f"[PASS] normalize_brand('aksher', 'cement') = '{test5}'")
assert test5 == "Akshar", f"FAILED: Expected 'Akshar', got '{test5}'"

print()
print("=" * 60)
print("PAINT SIZE TESTS")
print("=" * 60)

# Test 6: get_paint_sizes
paint_sizes = get_paint_sizes()
print(f"[PASS] get_paint_sizes() = {paint_sizes}")
assert paint_sizes == ["1L", "5L", "20L"], f"FAILED: Expected ['1L', '5L', '20L'], got {paint_sizes}"

# Test 7: 4L not in paint sizes
test7 = "4L" in paint_sizes
print(f"[PASS] '4L' in get_paint_sizes() = {test7}")
assert test7 is False, "FAILED: '4L' should NOT be in paint sizes"

print()
print("=" * 60)
print("SUCCESS: ALL REQUIREMENTS FULFILLED!")
print("=" * 60)
print()
print("Summary:")
print("  - Canonical brand is 'Akshar'")
print("  - Alias 'aksher' accepted and normalized to 'Akshar'")
print("  - is_cement_brand('aksher') returns True")
print("  - normalize_brand('aksher') returns 'Akshar'")
print("  - Paint sizes are 1L, 5L, 20L (NOT 4L)")
print("  - Legacy 4L links handled safely (see views)")
print()

