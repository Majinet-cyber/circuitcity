# Hotfix: Accessories Normal Sell - JSON Serialization

**Date:** December 22, 2025  
**Issue:** TypeError when accessing `/verticals/phones/accessories/sell/`  
**Error:** `Object of type Decimal is not JSON serializable`

## Problem

When rendering the accessories normal sell page, the view was trying to serialize a list of products containing `Decimal` objects (prices) directly to JSON using `json.dumps()`. Python's standard `json` module doesn't support Decimal serialization.

## Error Details

```python
# Line 503 in inventory/verticals/phones_accessories.py
'default_selling_price': product.default_selling_price,  # Decimal object

# Line 512 - JSON serialization fails
'products': json.dumps(products_with_stock),  # TypeError
```

## Solution

Convert `Decimal` to `float` before JSON serialization:

```python
# Fixed Line 503
'default_selling_price': float(product.default_selling_price) if product.default_selling_price else 0.0,
```

## File Changed

- `inventory/verticals/phones_accessories.py` (line 503)

## Verification

Other JSON serialization points already had proper float() conversions:
- ✅ `accessories_lookup_api()` - lines 357-358 (already correct)
- ✅ `accessories_stock_in()` - lines 242-243 (already correct)

## Testing

```bash
# Access the normal sell page
curl http://localhost:8000/verticals/phones/accessories/sell/

# Should return 200 OK (not 500)
```

## Status

✅ **FIXED** - Normal sell page now loads correctly

---

**Related Files:**
- Main implementation: `inventory/verticals/phones_accessories.py`
- Template: `templates/verticals/phones/accessories_normal_sell.html`
- Tests: `tests/test_accessories_comprehensive.py`

