# Clothing Stock Summary Fix - Quick Reference

## 🎯 What Was Fixed
Stock Summary cards on `/verticals/clothing/dashboard/` now show **actual stock** instead of 0.

## 🔧 Changes Made

### File: `inventory/verticals/clothing.py` (lines 94-191)

**Old Logic:**
```python
# Only counted MerchProduct.quantity_in_stock
stock_summary = (
    MerchProduct.objects.filter(...)
    .values("category")
    .annotate(total_quantity=Sum("quantity_in_stock"))
)
# Result: Tracked units (ClothingBarcodeUnit) were IGNORED ❌
```

**New Logic:**
```python
# Counts BOTH tracked units AND common stock
1. Query ClothingBarcodeUnit (status=IN_STOCK) → tracked units
2. Query MerchProduct (quantity_in_stock > 0) → common stock
3. Exclude products with tracked units from common (no double-counting)
4. Merge by category → total = tracked + common
```

## 📊 Context Variables (Template)

```python
stock_summary = [
    {
        "category": "Shoes",  # Title case
        "icon": "👞",
        "total_items": 5,  # Number of distinct product styles
        "total_quantity": 50,  # Total units in stock
        "tracked_quantity": 20,  # Barcoded units
        "common_quantity": 30,  # Common stock units
    },
    ...
]
```

## ✅ Testing

### Run New Tests
```bash
pytest tests/test_clothing_dashboard_stock_summary.py -v
# Expected: 7 passed
```

### Run All Clothing Tests
```bash
pytest tests/test_verticals_clothing.py tests/test_clothing_dashboard_stock_summary.py -v
# Expected: 27 passed (2 pre-existing failures unrelated to this fix)
```

## 🚀 How It Works

### Tracked Stock (ClothingBarcodeUnit)
```python
# Example: 5 barcoded Puma Jordan shoes
ClothingBarcodeUnit.objects.filter(
    business=business,
    category="shoes",
    status="IN_STOCK",  # CRITICAL: excludes SOLD units
    is_active=True,
).count()
# Result: 5 units
```

### Common Stock (MerchProduct)
```python
# Example: 10 basic jeans in quantity_in_stock
MerchProduct.objects.filter(
    business=business,
    category="jeans",
    quantity_in_stock__gt=0,
    is_active=True,
    is_archived=False,
).exclude(
    id__in=products_with_tracked_units  # Prevents double-counting
)
```

## 🔍 Key Rules

### Double-Counting Prevention
- If a product has tracked units (ClothingBarcodeUnit), we **ONLY** count the tracked units
- The product's `quantity_in_stock` is **IGNORED** for that product
- This prevents showing 50 + 50 = 100 when only 50 units actually exist

### Scoping
- **Business**: All queries filter by `business=business`
- **Location**: Applied to tracked units when available
- **Status**: Only `IN_STOCK` tracked units counted (excludes `SOLD`)

### Categories
```python
{
    "shoes": "👞",
    "shirt": "👔", 
    "dress": "👗",
    "jeans": "👖",
    # ... etc
}
```

## 🐛 Debugging

### Q: Stock shows 0 when I know there's stock?
**Check:**
1. Are tracked units marked as `status="IN_STOCK"` (not "SOLD")?
2. Is `is_active=True` on both `ClothingBarcodeUnit` and `MerchProduct`?
3. Is `is_archived=False` on `MerchProduct`?
4. Is the `category` field populated and matching?

### Q: Stock is double-counted?
**Check:**
- Products with tracked units should NOT have `quantity_in_stock > 0`
- If they do, the exclusion logic should prevent double-counting
- Debug: Print `products_with_tracked_units` to see exclusion list

### Q: Wrong business's stock showing?
**Check:**
- All queries must filter by `business=business`
- `base_context(request)` should provide the correct business
- Check session/middleware for tenant scoping

## 📝 Examples

### Example 1: Pure Tracked Stock
```python
# Product: Puma Jordan (Size 42)
# ClothingBarcodeUnit: 5 units (status=IN_STOCK)
# MerchProduct.quantity_in_stock: 0

Stock Summary:
  Category: Shoes
  Total: 5
  Tracked: 5
  Common: 0
```

### Example 2: Pure Common Stock
```python
# Product: Basic Jeans (Size 32)
# ClothingBarcodeUnit: None
# MerchProduct.quantity_in_stock: 10

Stock Summary:
  Category: Jeans
  Total: 10
  Tracked: 0
  Common: 10
```

### Example 3: Mixed Stock
```python
# Product 1: Nike Air (tracked) - 3 units
# Product 2: Adidas Samba (common) - 7 units

Stock Summary:
  Category: Shoes
  Total: 10 (3 + 7)
  Tracked: 3
  Common: 7
  Styles: 2
```

## 🔗 Related Code

### Models
- `inventory/models.py` → `MerchProduct`
- `inventory/models_clothing_barcode.py` → `ClothingBarcodeUnit`

### Views
- `inventory/verticals/clothing.py` → `dashboard()` function
- `inventory/verticals/base.py` → `base_context()` helper

### Tests
- `tests/test_clothing_dashboard_stock_summary.py` → New comprehensive tests
- `tests/test_verticals_clothing.py` → Existing clothing tests

## 🚨 Common Mistakes

### ❌ Don't Do This
```python
# BAD: Counting products instead of units
tracked_units = ClothingBarcodeUnit.objects.filter(...).count()
# This counts products, not total units per product
```

### ✅ Do This Instead
```python
# GOOD: Count units, group by category
tracked_summary = tracked_query.values("category").annotate(
    unit_count=Count("id"),  # Counts all units
    style_count=Count("product_id", distinct=True)  # Counts distinct products
)
```

### ❌ Don't Do This
```python
# BAD: Forgetting to exclude sold units
tracked_query = ClothingBarcodeUnit.objects.filter(business=business)
# This includes SOLD units! ❌
```

### ✅ Do This Instead
```python
# GOOD: Filter by status
tracked_query = ClothingBarcodeUnit.objects.filter(
    business=business,
    status="IN_STOCK",  # CRITICAL
    is_active=True,
)
```

## 📚 Further Reading

- **Full Documentation**: `CLOTHING_STOCK_SUMMARY_FIX_COMPLETE.md`
- **Test Suite**: `tests/test_clothing_dashboard_stock_summary.py`
- **Original Issue**: Stock Summary cards showing 0 stock

---

**Status**: ✅ Complete and Production-Ready
**Tests**: ✅ 7/7 passing
**Regressions**: ✅ None detected







