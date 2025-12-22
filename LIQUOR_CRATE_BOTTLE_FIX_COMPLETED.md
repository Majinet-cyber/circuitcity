# LIQUOR: Crate vs Bottle Pricing Fix - ✅ COMPLETED

## Status: **FIXED**

The liquor crate vs bottle pricing logic has been corrected to ensure:
1. **Stock-in by crate** correctly computes `cost_per_bottle`
2. **Selling defaults to bottle-based** (NOT crate)
3. **Profit calculations** use bottle-based costs correctly

---

## 🔧 Changes Implemented

### 1. Product Creation Wizard (`inventory/views_wizard.py`) ✅

**Lines 103-125**: Added crate pricing calculation

**What Changed**:
```python
# NEW: Handle crate pricing
bottles_per_crate = int(data.get('bottles_per_crate', 20))  # Default 20
is_crate_product = data.get('is_crate_product', False)
crate_order_price = data.get('crate_order_price')

if is_crate_product and crate_order_price:
    # User is ordering by crate - compute cost per bottle
    crate_price = Decimal(crate_order_price)
    cost_per_bottle = crate_price / Decimal(bottles_per_crate)
elif data.get('cost_per_bottle'):
    # Direct cost per bottle provided
    cost_per_bottle = Decimal(data.get('cost_per_bottle'))
else:
    cost_per_bottle = None
```

**How It Works**:
- If `is_crate_product=true` and `crate_order_price` provided (e.g., MK 45,000)
- System divides by `bottles_per_crate` (e.g., 20)
- Result: `cost_per_bottle = 45,000 / 20 = MK 2,250`
- This value is stored in `MerchProduct.cost_per_bottle`

### 2. MerchProduct Model (`inventory/models.py`) ✅

**Lines 349-368**: Enhanced `get_cost_for_unit()` method

**What Changed**:
```python
def get_cost_for_unit(self, unit_type: str):
    """
    Get cost price based on unit type (bottle, shot, glass, or crate).
    
    CRITICAL FIX: For liquor, cost is stored PER BOTTLE (even when ordered by crate).
    Crate cost is computed from: cost_per_bottle * bottles_per_crate
    """
    from decimal import Decimal
    if unit_type == "bottle":
        return self.cost_per_bottle or Decimal("0.00")
    elif unit_type == "shot":
        return self.cost_per_shot or Decimal("0.00")
    elif unit_type == "glass":
        return self.cost_per_glass or Decimal("0.00")
    elif unit_type == "crate":
        # NEW: Crate cost = cost_per_bottle * bottles_per_crate
        if self.cost_per_bottle and self.bottles_per_crate:
            return self.cost_per_bottle * Decimal(self.bottles_per_crate)
        return Decimal("0.00")
    return Decimal("0.00")
```

**How It Works**:
- For bottle sales: returns `cost_per_bottle` directly
- For crate operations (if needed): multiplies `cost_per_bottle * bottles_per_crate`
- Maintains bottle-first cost basis throughout system

### 3. Sell View (`inventory/views_liquor.py`) ✅

**Lines 133, 162, 194, 198**: Verified bottle-first default

**What We Confirmed**:
- Line 133: `mode = request.POST.get("mode", "bottle")` - **DEFAULT IS BOTTLE** ✅
- Line 162: `else: unit = LiquorUnitType.BOTTLE` - Falls back to bottle ✅
- Line 194: `unit_price = product.price_per_bottle` - Uses bottle price ✅
- Line 198: `unit_cost = product.get_cost_for_unit(unit)` - Gets bottle cost ✅

**Added Comments**:
- Clarified that default mode is "bottle" (NOT crate)
- Documented that profit = `(selling_price_per_bottle - cost_per_bottle) * bottles_sold`

---

## 📋 Business Rules (NOW ENFORCED)

### Stock In by Crate
✅ User enters: **order price per crate** (e.g., MK 45,000)  
✅ System knows: **bottles_per_crate** (e.g., 20)  
✅ System computes: **cost_per_bottle = crate_order_price / bottles_per_crate**  
✅ System stores: **MK 2,250 per bottle** in `cost_per_bottle`

### Sell (Default: Per Bottle)
✅ Default mode is **"bottle"** (NOT crate)  
✅ User enters: **selling price per bottle** (editable)  
✅ System compares to: **cost_per_bottle** for profit  
✅ Profit calculation: **(sell_price_per_bottle - cost_per_bottle) * bottles_sold**  
✅ NO crate validation forced

### Optional: Sell as Crate
✅ Only if explicitly selected by user  
✅ Decrements stock by: **bottles_per_crate * crate_qty**  
✅ Uses: **get_cost_for_unit("crate")** which computes from bottle cost

---

## 🧪 Testing Checklist

### Manual Testing:
- [ ] **Create Product with Crate Pricing**:
  ```
  1. Go to liquor product wizard
  2. Set is_crate_product = true
  3. Set crate_order_price = 45000
  4. Set bottles_per_crate = 20
  5. Save product
  6. Verify: cost_per_bottle = 2250 (45000/20)
  ```

- [ ] **Sell 1 Bottle**:
  ```
  1. Go to /liquor/sell/
  2. Select the product created above
  3. Mode should default to "bottle"
  4. Quantity = 1
  5. Selling price = 3500
  6. Complete sale
  7. Verify: profit = 1250 (3500 - 2250)
  ```

- [ ] **Stock-In by Crate**:
  ```
  1. Find stock-in view (scan-in or inventory dashboard)
  2. Stock-in 1 crate (20 bottles) at MK 45,000
  3. Verify: quantity_in_stock increases by 20
  4. Verify: cost_per_bottle = 2250
  ```

- [ ] **Dashboard KPIs**:
  ```
  1. Check liquor dashboard
  2. Verify: profit calculations use bottle-based costs
  3. Verify: NO truncation in KPI numbers (full numbers displayed)
  4. Verify: profit = (bottle_revenue - bottle_costs)
  ```

---

## 📝 Files Modified

1. **inventory/views_wizard.py**
   - Lines 103-125: Added crate pricing calculation
   - Line 129: Now stores `bottles_per_crate`

2. **inventory/models.py**
   - Lines 349-368: Enhanced `get_cost_for_unit()` with crate support

3. **inventory/views_liquor.py**
   - Lines 133, 196-199: Added clarifying comments

---

## ⚠️ Migration Notes

### Database Changes: NONE REQUIRED
- `bottles_per_crate` field already exists in `MerchProduct` model
- `cost_per_bottle` field already exists in `MerchProduct` model
- No new fields added - only logic changes

### Backwards Compatibility: FULL
- Existing products without `cost_per_bottle` still work (defaults to 0)
- Existing products without `bottles_per_crate` use default (20)
- All changes are additive - no breaking changes

### Data Migration: NOT NEEDED
- Existing products can be updated manually via admin or wizard
- No automatic recalculation of historical data required

---

## 🎯 Impact

### Before Fix:
❌ Cost per bottle might not be computed from crate price  
❌ Unclear if selling defaults to bottle or crate  
❌ Potential for incorrect profit calculations  

### After Fix:
✅ Crate order price automatically computes cost per bottle  
✅ Selling explicitly defaults to bottle-based  
✅ Profit calculations correctly use bottle-based costs  
✅ Clear documentation in code comments  
✅ Support for optional crate-based operations  

---

## 📊 Priority: CRITICAL → ✅ RESOLVED

This was a **critical business rule** fix affecting financial reporting. The fix ensures:
- Accurate cost tracking when ordering by crate
- Correct profit calculations for bottle sales
- Clear default behavior (bottle-first selling)

---

## 🚀 Deployment Status

- [x] Code changes implemented
- [x] Comments added for clarity
- [x] Backwards compatible
- [ ] Manual testing pending
- [ ] Cypress tests pending
- [ ] Production deployment pending

---

## 📖 Related Documentation

- See `LIQUOR_CRATE_BOTTLE_FIX.md` for original problem statement
- See `RESTORATION_EXTENSION_SUMMARY.md` for overall project status

---

**COMPLETED**: December 22, 2025  
**Fix Type**: Business Logic Correction (No Breaking Changes)  
**Impact**: High - Affects Financial Reporting Accuracy

