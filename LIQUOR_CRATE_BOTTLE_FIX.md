# LIQUOR: Crate Order vs Bottle Sale Fix

## Problem Statement

Currently, crate stock-in cost-per-bottle is computed OK, but selling validates/forces crate-based price. **This is wrong**.

## REQUIRED BUSINESS RULES

### Stock In (Crate Handling)

When user chooses **Crate** for stock-in:
1. Ask for **order price per crate** (e.g., MK 45,000)
2. System knows `bottles_per_crate` (e.g., 20 - stored in MerchProduct.bottles_per_crate)
3. **Compute and store**: `cost_per_bottle = crate_order_price / bottles_per_crate`
   - Example: 45,000 / 20 = **MK 2,250 per bottle**
4. Store this in `MerchProduct.cost_per_bottle`

### Sell (DEFAULT: Per Bottle)

**Sale should be per bottle by default** (NOT crate):
1. User enters **selling price per bottle** (editable, pre-filled from `product.price_per_bottle`)
2. Compare to `cost_per_bottle` ONLY for profit display
3. **DO NOT validate as crate**
4. **Profit calculation**: `(sell_price_per_bottle - cost_per_bottle) * bottles_sold`

### Optional: Sell as Crate

Only if **explicitly selected** by user:
1. Decrement stock by: `bottles_per_crate * crate_qty`
2. Use crate selling price if configured

## Files to Modify

### 1. Product Creation Wizard (`inventory/views_wizard.py`)

**Current Code** (lines 83-142):
- Already handles `cost_per_bottle` correctly in `liquor_wizard_submit`
- **FIX NEEDED**: Add crate handling option

**Required Changes**:
```python
# In liquor_wizard_submit, add:
bottles_per_crate = int(data.get('bottles_per_crate', 20))  # Default 20
is_crate_product = data.get('is_crate_product', False)

if is_crate_product and data.get('crate_order_price'):
    crate_price = Decimal(data.get('crate_order_price'))
    cost_per_bottle = crate_price / Decimal(bottles_per_crate)
else:
    cost_per_bottle = Decimal(data.get('cost_per_bottle', 0)) if data.get('cost_per_bottle') else None

# Then use cost_per_bottle when creating product (line 124)
product = MerchProduct.objects.create(
    # ... existing fields ...
    cost_per_bottle=cost_per_bottle,
    bottles_per_crate=bottles_per_crate,
    # ... rest of fields ...
)
```

### 2. Sell View (`inventory/views_liquor.py`)

**Current Code** (lines 105-250):
- Line 194: `unit_price = product.price_per_bottle` ✅ Already correct - uses bottle price
- Line 198: `unit_cost = product.get_cost_for_unit(unit)` ✅ Already correct

**Issue**: The validation or pricing might force crate-based logic elsewhere.

**Required Fix**:
- Ensure `product.get_cost_for_unit("bottle")` returns `cost_per_bottle` (NOT crate-based cost)
- DEFAULT selling mode should be "bottle" (line 162)
- Remove any crate validation that prevents bottle sales

### 3. MerchProduct Model (`inventory/models.py`)

**Check `get_cost_for_unit` method** (around line 350):
```python
def get_cost_for_unit(self, unit_type):
    """Get cost for a specific unit type"""
    from decimal import Decimal
    if unit_type == "bottle":
        return self.cost_per_bottle or Decimal("0.00")  # ✅ Correct
    elif unit_type == "shot":
        return self.cost_per_shot or Decimal("0.00")
    elif unit_type == "crate":
        # NEW: Add crate cost calculation
        if self.cost_per_bottle and self.bottles_per_crate:
            return self.cost_per_bottle * Decimal(self.bottles_per_crate)
        return Decimal("0.00")
    else:
        return self.cost_per_bottle or Decimal("0.00")
```

### 4. Stock-In Logic

**Find where liquor products are stocked in** (likely in liquor inventory dashboard or scan-in view).

**Required**:
- If stock-in by **crate**:
  - User enters: `crate_order_price` and `crate_quantity`
  - System computes: `cost_per_bottle = crate_order_price / bottles_per_crate`
  - Increase `quantity_in_stock` by: `crate_quantity * bottles_per_crate` (bottles)
  - Store `cost_per_bottle` on product

- If stock-in by **bottle**:
  - User enters: `bottle_cost` and `bottle_quantity`
  - Store `cost_per_bottle = bottle_cost`
  - Increase `quantity_in_stock` by: `bottle_quantity`

### 5. Dashboard KPIs

**Ensure profit calculations use bottle-based cost**:
- Sales are recorded per bottle (or per shot)
- Profit = `(selling_price_per_bottle - cost_per_bottle) * bottles_sold`
- **Do NOT truncate numbers** in KPI display (no "..." truncation)
- Show full numbers with proper formatting

## Testing Checklist

- [ ] Create liquor product with crate pricing (20 bottles @ MK 45,000)
- [ ] Verify `cost_per_bottle` = MK 2,250
- [ ] Sell 1 bottle at MK 3,500
- [ ] Verify profit = MK 1,250 (3,500 - 2,250)
- [ ] Stock-in by crate: verify bottles are added correctly
- [ ] Stock-in by bottle: verify cost is per bottle
- [ ] Dashboard KPIs show full numbers (no truncation)

## Priority: CRITICAL

This is a **critical business rule** fix. Incorrect cost/profit calculations directly impact business financial reporting.

## Implementation Status

- [ ] Product wizard: Add crate pricing calculation
- [ ] Stock-in: Handle crate vs bottle stock-in
- [ ] Sell view: Verify bottle-first default (already correct?)
- [ ] Model: Verify `get_cost_for_unit` handles all cases
- [ ] Dashboard: Verify KPIs use correct calculations
- [ ] Tests: Add unit tests for crate/bottle logic

## Notes

The existing code in `sell_liquor` (lines 188-195) already uses `product.price_per_bottle` and `product.get_cost_for_unit(unit)`, which suggests the logic might already be correct for selling. The issue might be:
1. During product creation (wizard doesn't compute cost_per_bottle from crate price)
2. During stock-in (crate stock-in doesn't compute/update cost_per_bottle)
3. KPI calculations somewhere truncating numbers or using wrong cost basis

**Action**: Focus on ensuring `cost_per_bottle` is correctly computed when crate pricing is used during product creation or stock-in.

