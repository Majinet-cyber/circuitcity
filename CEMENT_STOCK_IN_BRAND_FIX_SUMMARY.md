# Cement Stock-In Brand Product Fix - Complete Summary

## Problem Statement
Cement stock-in wizard was showing:
1. Generic "Cement BAG (50KG)" instead of actual brand products (Dangote, Akshar, etc.)
2. All product types (Cement, Paint, Iron Sheets, Angle Iron) in step 2, even when only cement was stocked
3. Catalog brands instead of actual DB products in step 3

## Goal (STRICT CEMENT-ONLY SCOPE)
Fix cement stock-in flow to:
1. Show only Cement in step 2 by default (hide Paint/Iron unless products exist)
2. Show real cement brand products from DB in step 3 (not catalog)
3. Show selected brand product name in step 4 (not generic)

## Files Changed (CEMENT-ONLY)

### 1. `inventory/verticals/cement.py` ✅ FIXED
**Lines changed:** 
- 845-882: Step 2 - Filter products based on what exists in DB
- 884-920: Step 3 - Show real cement products from DB for brand selection
- 649-686: POST Step 3 - Handle product_id selection for cement
- 688-797: POST Step 4 - Update existing product when product_id is set
- 828-835: Removed auto-redirect for cement (now shows brand selection)
- 636-646: Removed auto-skip to step 4 for cement

**Changes:**
- Step 2 now filters product types - only shows types that have products in DB
- Always shows Cement, hides Paint/Iron/Angle unless business has stocked them
- Step 3 for cement now shows actual brand products from DB (Dangote, Akshar, etc.)
- Captures `product_id` instead of just brand name
- Step 4 uses the selected product and updates its stock (no generic creation)

### 2. `templates/verticals/cement/stock_in_v2.html` ✅ UPDATED
**Lines changed:** 321-429

**Changes:**
- Added cement brand product selection UI in step 3
- Shows cards for each real cement product from DB
- Uses `product_id` radio input instead of `brand`
- Shows empty state if no cement products exist
- Preserves existing Paint/Iron variant selection logic (untouched)

### 3. `inventory/tests/test_cement_stock_in_brands.py` ✅ NEW (5 tests)
**Tests added:**
1. `test_step2_shows_only_cement_when_only_cement_products_exist` - Verifies Paint/Iron hidden
2. `test_step3_lists_real_cement_brand_products_from_db` - Verifies DB products shown
3. `test_step4_shows_selected_brand_product_name` - Verifies specific brand name shown
4. `test_step4_updates_existing_cement_product_stock` - Verifies stock updates work
5. `test_step2_shows_paint_when_paint_products_exist` - Verifies dynamic type filtering

### 4. `inventory/tests/test_cement_stock_in_flow.py` ✅ UPDATED
**Tests updated:** 4 existing tests adapted to new flow
- `test_stock_in_complete_flow_cement` - Now creates product first, uses `product_id`
- `test_stock_in_step3_skipped_for_cement` - Now expects step 3 to show (not skip)
- `test_stock_in_updates_existing_product` - Uses `product_id` instead of `brand`
- `test_stocked_product_is_sellable` - Uses `product_id` instead of `brand`

## What Changed (Summary)

### Before Fix:
```python
# Step 2: Always showed all product types
products = get_all_products()  # Cement, Paint, Iron, Angle

# Step 3: Used catalog brands (static list)
brands = CEMENT_BRANDS  # ["Dangote", "Akshar", ...]

# Step 4: Created generic "Cement BAG (50KG)"
product_name = "Cement BAG (50KG)"
```

### After Fix:
```python
# Step 2: Only shows products that exist in DB
filtered_products = []
for product_def in all_products:
    if product_def["slug"] == "cement":
        filtered_products.append(product_def)  # Always show cement
    elif has_products_of_type(product_def["slug"]):
        filtered_products.append(product_def)  # Show if stocked

# Step 3: Shows real DB products (for cement)
cement_products = MerchProduct.objects.filter(
    business=business, kind=BusinessKind.CEMENT, category__icontains="cement"
).exclude(name__iexact="Cement")  # Exclude generic placeholder

# Step 4: Uses selected product
selected_product = MerchProduct.objects.get(id=product_id)
selected_product.quantity_in_stock += quantity  # Update existing
```

## Test Results

### New Tests (Cement Brand Selection)
```bash
$ python -m pytest inventory/tests/test_cement_stock_in_brands.py -v
============================= test session starts =============================
collected 5 items

inventory\tests\test_cement_stock_in_brands.py .....                     [100%]

============================= 5 passed ========================================
```

### Existing Tests (No Regressions)
```bash
$ python -m pytest inventory/tests/test_cement_stock_in_flow.py -v
============================= test session starts =============================
collected 25 items

inventory\tests\test_cement_stock_in_flow.py .........................   [100%]

============================= 25 passed =======================================
```

### Full Test Suite (All Green)
```bash
$ python -m pytest -q
============================= test session starts =============================
2606 items collected

2591 passed, 15 skipped in 148.20s (0:02:28)
```

## Verification

### Before Fix (Production Bug):
1. Step 2: Showed Paint, Iron Sheets, Angle Iron even when not stocked
2. Step 3: Showed catalog brands (static list, not real products)
3. Step 4: Displayed "Product: Cement BAG (50KG)" (generic)
4. Result: Created generic products, not actual brands

### After Fix:
1. ✅ Step 2: Shows only Cement (Paint/Iron hidden until stocked)
2. ✅ Step 3: Shows real products: "Dangote", "Akshar", "Duracrete", etc.
3. ✅ Step 4: Shows "Product: Dangote Cement BAG (50KG)" (specific brand)
4. ✅ Result: Updates existing product stock (no generic creation)

## Impact Analysis

### Minimal/Surgical Changes ✅
- **Only cement stock-in flow changed** (no other verticals affected)
- **No changes to models** or migrations
- **No changes to sell flow** or other cement pages
- **No changes to paint/iron logic** (preserved as-is)
- **Template changes isolated** to cement stock-in step 3

### Zero Regressions ✅
- All existing cement tests updated and pass (25 passed)
- New regression tests added (5 passed)
- Full test suite passes (2591 passed, 15 skipped)
- No linter errors

## Why This Fix is Robust

1. **Reuses Existing Products**: Now uses actual DB products, not generic catalog
2. **Dynamic Product Types**: Step 2 adapts based on what's actually stocked
3. **No Hardcoded Logic**: Filters products dynamically per business
4. **Backwards Compatible**: Paint/Iron/Angle logic unchanged
5. **Comprehensive Tests**: 5 new tests + 4 updated tests validate behavior
6. **No Band-Aids**: Fixed the root cause (catalog vs DB products)

## Future Benefits

1. **Cement-only businesses** see only Cement in step 2 (clean UI)
2. **Multi-product businesses** see all stocked types (flexible)
3. **Brand selection** uses real products (accurate inventory)
4. **Stock updates** target specific products (no duplicates)
5. **Empty states** handled gracefully (no crashes)

## Commit Message

```
Cement stock-in: show brand products + hide non-cement types unless added

FIX: Cement stock-in wizard now uses actual DB products for brand selection
instead of generic catalog brands. Step 2 now hides Paint/Iron/Angle types
unless the business has actually stocked them (cement businesses see only Cement by default).

Changes (cement-only scope):
- inventory/verticals/cement.py (stock_in view + POST handlers)
- templates/verticals/cement/stock_in_v2.html (step 3 brand selection UI)
- inventory/tests/test_cement_stock_in_brands.py (5 new regression tests)
- inventory/tests/test_cement_stock_in_flow.py (4 tests updated for new flow)

Tests: 2591 passed, 15 skipped (full suite green)
No regressions. Cement stock-in now shows: "Dangote Cement BAG (50KG)" not "Cement BAG (50KG)"
```

