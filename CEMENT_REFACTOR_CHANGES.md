# CEMENT VERTICAL REFACTORING - SSOT & UX IMPROVEMENTS

## Summary

This document outlines the comprehensive refactoring of the Cement/Construction Materials vertical to implement:

1. **SSOT (Single Source of Truth)** for all product definitions
2. **Fixed Malawi paint sizes** (1L, 5L, 20L - NO 4L)
3. **Removed cement brand duplicates** (cleaned canonical list)
4. **Card-based Stock-In wizard** (Category → Product → Variant → Qty/Price)
5. **Legacy size handling** (4L URLs redirect safely to 5L)

## Changes Overview

### A) Fixed Malawi Paint Sizes (1L, 5L, 20L)

**Problem**: Paint sizes showed 4L but Malawi standard is 1L, 5L, 20L.

**Solution**:
- Defined paint sizes in SSOT: `PAINT_SIZES = ["1L", "5L", "20L"]`
- Updated hardware.py catalog to use SSOT sizes
- Created `normalize_paint_size()` function to handle legacy 4L → 5L conversion
- Updated views (`products_catalog`, `product_detail`) to redirect 4L URLs to 5L
- Stock-In flow normalizes 4L to 5L internally

**Files Changed**:
- `inventory/catalog/construction_materials.py` (NEW - defines SSOT)
- `inventory/catalog/hardware.py` (uses SSOT paint sizes)
- `inventory/verticals/cement.py` (handles legacy 4L URLs)

**Tests**:
- ✅ `test_paint_sizes_malawi_correct()` - verifies sizes are 1L, 5L, 20L
- ✅ `test_no_4l_in_paint_sizes()` - ensures 4L is NOT in catalog
- ✅ `test_legacy_4l_normalizes_to_5l()` - verifies normalization
- ✅ `test_stock_in_paint_legacy_4l_normalizes_to_5l()` - integration test

### B) Cement Brands - NO DUPLICATES

**Problem**: Cement brands had duplicates like "Njati" and "Njati Extra".

**Solution**:
- Created canonical cement brand list with 8 unique brands:
  - Dangote, Akshar (not "Aksher"), Duracrete, Khoma, Lime, Njati (single entry), Nkope, Nthanthwe
- Removed "Njati Extra" from canonical list (was duplicate)
- Updated cement_seed.py to use SSOT brands

**Files Changed**:
- `inventory/catalog/construction_materials.py` (canonical CEMENT_BRANDS)
- `inventory/cement_seed.py` (imports from SSOT)

**Tests**:
- ✅ `test_cement_brands_no_duplicates()` - ensures unique brands
- ✅ `test_cement_brands_no_njati_extra()` - verifies no "Njati Extra"
- ✅ `test_cement_brands_akshar_normalized()` - checks "Akshar" spelling
- ✅ `test_cement_brand_count()` - validates 8 canonical brands

### C) Card-Based Stock-In Wizard

**Problem**: Stock-In flow wasn't following catalog-driven card UX.

**Solution**:
Implemented 4-step wizard with card-based UI:

1. **Step 1: Category Cards**
   - "Construction Materials" (future-proof for expansion)

2. **Step 2: Product Cards**
   - Cement, Paint, Iron Sheets, Angle Iron (from catalog)

3. **Step 3: Variant Selection**
   - Brand → Size → Finish/Color (dynamic per product)
   - Cement: Brand + Size (50KG)
   - Paint: Brand + Size (1L/5L/20L) + Finish + Color

4. **Step 4: Quantity & Pricing**
   - Quantity, Cost Price, Selling Price
   - Creates/updates inventory immediately
   - Product is sellable after stock-in

**Files Changed**:
- `inventory/verticals/cement.py` (new `stock_in()` view)
- `templates/verticals/cement/stock_in_v2.html` (NEW - card-based wizard)

**Tests**:
- ✅ `test_stock_in_step1_category_renders()` - Step 1 UI
- ✅ `test_stock_in_step3_variant_renders_paint()` - Paint sizes (1L, 5L, 20L)
- ✅ `test_stock_in_complete_flow_cement()` - Full cement flow
- ✅ `test_stock_in_complete_flow_paint_5l()` - Full paint flow
- ✅ `test_stocked_product_is_sellable()` - Validates item is ready for sale

### D) SSOT Implementation

**Core Module**: `inventory/catalog/construction_materials.py`

**Defines**:
- Categories: Construction Materials
- Products: Cement, Paint, Iron Sheets, Angle Iron
- Brands: Canonical lists for cement and paint
- Sizes/Variants: Per-product specifications
- Helpers:
  - `get_all_products()` - Get all products
  - `get_product_by_slug()` - Get single product
  - `build_product_name()` - Standardized naming
  - `normalize_paint_size()` - Legacy 4L handling
  - `is_valid_paint_size()` - Validation

**Consumers** (All read from SSOT):
- `inventory/cement_seed.py` - Seeds cement brands
- `inventory/catalog/hardware.py` - Uses paint sizes
- `inventory/verticals/cement.py` - Stock-In, products_catalog, product_detail
- `templates/verticals/cement/stock_in_v2.html` - Wizard UI

**Tests**:
- ✅ `test_cement_seed_uses_ssot()` - Verifies seed uses SSOT
- ✅ `test_hardware_catalog_uses_ssot_paint_sizes()` - Verifies hardware.py uses SSOT

## Files Created

1. `inventory/catalog/construction_materials.py` - **SSOT catalog**
2. `templates/verticals/cement/stock_in_v2.html` - **Card-based wizard**
3. `inventory/tests/test_construction_materials_ssot.py` - **Unit tests (23 tests)**
4. `inventory/tests/test_cement_stock_in_flow.py` - **Integration tests (12 tests)**

## Files Modified

1. `inventory/cement_seed.py` - Uses SSOT brands, removes duplicates
2. `inventory/catalog/hardware.py` - Uses SSOT paint sizes
3. `inventory/verticals/cement.py` - New stock_in view, legacy 4L handling

## Test Results

### Unit Tests (23 passed)
```bash
python -m pytest inventory/tests/test_construction_materials_ssot.py -v
# Result: 23 passed
```

**Coverage**:
- Paint sizes (1L, 5L, 20L)
- Legacy 4L normalization
- Cement brand uniqueness
- Product name building
- SSOT catalog functions

### Integration Tests (12 passed)
```bash
python -m pytest inventory/tests/test_cement_stock_in_flow.py -v
# Result: 12 passed
```

**Coverage**:
- Stock-In wizard (all 4 steps)
- Complete flow (cement + paint)
- Legacy 4L handling in flow
- Product is sellable after stock-in
- Updates existing products (no duplicates)

### Regression Tests (9 passed)
```bash
python -m pytest inventory/tests/test_cement_pages_render.py -v
# Result: 9 passed (NO REGRESSIONS)
```

## Commands to Run Tests

```bash
# All new tests
python -m pytest inventory/tests/test_construction_materials_ssot.py inventory/tests/test_cement_stock_in_flow.py -v

# Specific test suites
python -m pytest inventory/tests/test_construction_materials_ssot.py -v  # Unit tests
python -m pytest inventory/tests/test_cement_stock_in_flow.py -v        # Integration tests
python -m pytest inventory/tests/test_cement_pages_render.py -v         # Regression tests

# Quick smoke test
python -m pytest -k "paint_sizes" -v
```

## How to Use

### For Developers

1. **All product definitions come from SSOT**:
   ```python
   from inventory.catalog.construction_materials import (
       get_all_products,
       get_product_by_slug,
       build_product_name,
       normalize_paint_size,
   )
   ```

2. **Add new product to catalog**:
   Edit `inventory/catalog/construction_materials.py`, add to `CONSTRUCTION_PRODUCTS`.

3. **Add new brand**:
   Edit relevant brand list (e.g., `CEMENT_BRANDS`, `PAINT_BRANDS`).

### For Users

1. **Stock-In Flow**:
   - Navigate to `/cement/stock-in/`
   - Select **Category** (Construction Materials)
   - Select **Product** (Cement, Paint, etc.)
   - Select **Variants** (Brand, Size, Finish, Color)
   - Enter **Quantity & Pricing**
   - Product is immediately available for sale

2. **Paint Sizes**:
   - Use **1L, 5L, 20L** (standard Malawi sizes)
   - Old 4L links redirect automatically to 5L

3. **Cement Brands**:
   - Canonical list: Dangote, Akshar, Duracrete, Khoma, Lime, Njati, Nkope, Nthanthwe

## Non-Negotiable Rules Compliance

✅ **NO REGRESSIONS**: All existing cement pages still work (9/9 tests pass)
✅ **SSOT REQUIRED**: All product definitions in one place (`construction_materials.py`)
✅ **LOCK WITH TESTS**: 35 total tests added (23 unit + 12 integration)
✅ **PAINT SIZES**: Exactly 1L, 5L, 20L (NO 4L in UI)
✅ **LEGACY SAFE**: Old 4L URLs redirect to 5L (no 500 errors)
✅ **NO DUPLICATES**: Cement brands are unique (8 canonical)
✅ **CARD-BASED UX**: Stock-In follows catalog-driven wizard pattern
✅ **IMMEDIATELY SELLABLE**: Stock-In creates active, trackable products

## Future Enhancements

1. **Expand categories**: Add more construction material categories
2. **Add more products**: Nails, binding wire, boards (already in SSOT)
3. **Cypress E2E tests**: Add browser automation tests for wizard
4. **Product images**: Add image support to SSOT catalog
5. **Pricing intelligence**: Suggest optimal pricing based on cost

## Support

For questions or issues:
- Check SSOT catalog: `inventory/catalog/construction_materials.py`
- Review tests: `inventory/tests/test_construction_materials_ssot.py`
- Verify wizard: `inventory/tests/test_cement_stock_in_flow.py`

---

**Status**: ✅ COMPLETE
**Tests**: 35/35 PASSED
**Regressions**: 0
**Date**: 2026-01-08

