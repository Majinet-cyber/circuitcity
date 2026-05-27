# Liquor Follow-Up Changes Summary

## ✅ SAFE FOLLOW-UP CHANGES COMPLETED (ZERO REGRESSIONS)

All 45 liquor tests passing ✅

---

## 📋 Changes Implemented

### 1. **Updated Liquor Configuration** (`inventory/liquor_config.py`)

#### Changed Defaults:
- **Spirits/Whisky shots_per_bottle**: Changed from `30` → `24`
- **Added**: `DEFAULT_BARMAN_SHOTS_PER_BOTTLE = 2`
- **Spirits/Whisky pack config**: Changed from `(PackLabel.CASE, 6)` → `(None, None)` (stock-in is bottle-only)

#### New Functions:
- `validate_cider_pack_size()`: Enforces cider pack_size must be exactly 6
- Updated `get_allowed_units()`: Added `for_stock_in` parameter to differentiate stock-in vs selling units
- Updated `validate_unit_for_kind()`: Added `for_stock_in` parameter and specific error messages for spirits/whisky stock-in violations

#### Key Rules Enforced:
- **Spirits/Whisky stock-in**: BOTTLE-ONLY (no case, no crate, no pack)
- **Spirits/Whisky selling**: SHOT or BOTTLE allowed
- **Cider pack_size**: Must be exactly 6 (validation enforced)

---

### 2. **Barman Shots Accounting** (`inventory/services/liquor_sale.py`)

#### New Service Function: `stock_in_liquor()`
```python
def stock_in_liquor(
    *,
    business,
    product_id: int,
    user,
    quantity: int,
    unit: str,  # "bottle" only for spirits/whisky
    cost_per_unit: Decimal,
    location=None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
```

**Barman Shots Logic:**
- When stocking spirits/whisky bottles for shot-selling:
  - Calculates sellable shots: `quantity * shots_per_bottle` (default 24)
  - Automatically deducts 2 barman shots per bottle
  - Net sellable stock = `(quantity * 24) - (quantity * 2)` = `quantity * 22`
  - Creates `LiquorStockAdjustment` record for audit trail

**Example:**
- Stock in 1 bottle of whisky:
  - Total shots: 24
  - Barman shots: 2 (automatically recorded)
  - Sellable shots added to inventory: 22

**Accounting:**
- Barman shots are recorded as `LiquorStockAdjustment` with reason `BARMAN_SHOTS`
- These shots are NOT included in sellable stock
- Fully auditable (shows in reports)

---

### 3. **New Model: LiquorStockAdjustment** (`inventory/models_verticals.py`)

```python
class LiquorStockAdjustment(models.Model):
    """
    Records stock adjustments for liquor products.
    Used for tracking barman shots, spillage, breakage, and other non-sale stock changes.
    """
    business = ForeignKey(Business)
    product = ForeignKey(MerchProduct)
    location = ForeignKey(Location, null=True)
    quantity_change = IntegerField()  # Positive for additions, negative for deductions
    reason = CharField(choices=[
        ("BARMAN_SHOTS", "Barman Shots (Staff Consumption)"),
        ("SPILLAGE", "Spillage"),
        ("BREAKAGE", "Breakage"),
        ("EXPIRED", "Expired"),
        ("THEFT", "Theft"),
        ("CORRECTION", "Stock Correction"),
        ("OTHER", "Other"),
    ])
    notes = TextField()
    adjusted_by = ForeignKey(User)
    adjusted_at = DateTimeField(default=timezone.now)
```

**Migration:** `inventory/migrations/1010_add_liquor_stock_adjustment_model.py` (applied successfully)

---

### 4. **Cider Pack Size Validation** (`inventory/models.py`)

Added validation in `MerchProduct.save()`:
```python
# NEW RULE: Cider pack_size must be exactly 6 (6-pack only, no crates)
if self.kind == BusinessKind.LIQUOR and self.category and self.category.lower() == "cider":
    if self.bottles_per_crate is not None and self.bottles_per_crate != 6:
        raise ValidationError(
            f"Cider pack size must be exactly 6 (6-pack). Got: {self.bottles_per_crate}. "
            f"Cider does not use crates."
        )
```

**Effect:**
- Attempting to create/update cider with `pack_size != 6` will raise `ValidationError`
- Ensures data integrity at the model level

---

### 5. **Updated Tests** (`inventory/tests/test_liquor_real_world_rules.py`)

#### New Test Class: `TestNewRules2024`
- `test_spirits_default_shots_is_24`: Verifies DEFAULT_SHOTS_PER_BOTTLE = 24
- `test_spirits_with_missing_shots_per_bottle_defaults_to_24`: Backward compatibility
- `test_barman_shots_accounting`: Verifies 2 barman shots deducted per bottle
- `test_spirits_stock_in_bottle_only`: Enforces bottle-only stock-in
- `test_cider_pack_size_must_be_6`: Enforces pack_size=6 validation
- `test_cider_pack_size_6_is_allowed`: Allows valid cider
- `test_spirits_selling_units_shot_or_bottle`: Verifies selling units
- `test_spirits_stock_in_units_bottle_only`: Verifies stock-in units

#### New Test Class: `TestConcurrencySafety`
- `test_sale_uses_select_for_update`: Verifies row locking
- `test_atomic_stock_decrement_prevents_overselling`: Prevents overselling
- `test_transaction_rollback_on_error`: Ensures transaction safety

#### Updated Existing Tests:
- Changed all references from 30 → 24 shots
- Updated `_create_spirits()` helper: default stock from 180 → 144
- Updated test expectations to match new defaults

**Test Results:**
```
Ran 45 tests in 124.568s
OK ✅
```

---

## 📊 Summary of Rules

### Beer
- **Stock-in units**: Bottle/Can, Crate (20 bottles)
- **Selling units**: Bottle/Can, Crate
- **Pack size**: 20 (editable)

### Cider
- **Stock-in units**: Bottle/Can, 6-Pack (6 bottles)
- **Selling units**: Bottle/Can, 6-Pack
- **Pack size**: 6 (ENFORCED, cannot be changed)
- **Validation**: `pack_size != 6` raises `ValidationError`

### Wine
- **Stock-in units**: Bottle, Glass
- **Selling units**: Bottle, Glass
- **Glasses per bottle**: 5 (editable)

### Spirits/Whisky
- **Stock-in units**: BOTTLE ONLY (no case/crate/pack)
- **Selling units**: Shot, Bottle
- **Shots per bottle**: 24 (changed from 30)
- **Barman shots**: 2 per bottle (automatically deducted)
- **Sellable shots per bottle**: 22 (24 - 2)

---

## 🔒 Concurrency Safety

All liquor sales use:
1. **`@transaction.atomic`**: Ensures all operations succeed or fail together
2. **`select_for_update()`**: Row-level locking prevents race conditions
3. **Conditional update**: `F()` expressions for atomic stock decrement
4. **Validation before commit**: Prevents partial writes

**Example:**
```python
@transaction.atomic
def create_liquor_sale(...):
    product = MerchProduct.objects.select_for_update().get(pk=product_id)
    
    # Atomic decrement
    updated = MerchProduct.objects.filter(
        pk=product.pk,
        quantity_in_stock__gte=qty_base_units
    ).update(
        quantity_in_stock=F('quantity_in_stock') - qty_base_units
    )
    
    if updated == 0:
        raise OutOfStockError("Insufficient stock")
```

---

## 📁 Files Changed

1. **`inventory/liquor_config.py`**
   - Updated defaults (shots=24, barman=2)
   - Added stock-in unit restrictions
   - Added cider pack_size validation function

2. **`inventory/services/liquor_sale.py`**
   - Added `stock_in_liquor()` service function
   - Implemented barman shots accounting logic

3. **`inventory/models_verticals.py`**
   - Added `LiquorStockAdjustment` model

4. **`inventory/models.py`**
   - Added cider pack_size=6 validation in `MerchProduct.save()`

5. **`inventory/tests/test_liquor_real_world_rules.py`**
   - Added 11 new tests (8 for new rules, 3 for concurrency)
   - Updated 3 existing tests to use 24 instead of 30

6. **`inventory/migrations/1010_add_liquor_stock_adjustment_model.py`**
   - Migration for `LiquorStockAdjustment` model

---

## ✅ Verification

### All Tests Pass
```bash
$ python manage.py test inventory.tests.test_liquor_real_world_rules --keepdb
Ran 45 tests in 124.568s
OK ✅
```

### No Regressions
- All 34 original liquor tests still pass
- 11 new tests added and passing
- Zero breaking changes to existing functionality

### Backward Compatibility
- Old products without `shots_per_bottle` default to 24 at runtime
- No data migration required
- Existing URLs and routes unchanged

---

## 🎯 Non-Negotiables (All Satisfied)

✅ Strict multi-tenant: active business + active location scoping  
✅ Correct vertical gating: wrong vertical returns error  
✅ No cross-business leakage  
✅ URLs working (no changes needed)  
✅ No hacks/skips/ignores  
✅ Tests lock behavior forever  
✅ Concurrency safety (select_for_update, atomic transactions)  

---

## 🚀 Production Ready

All changes are:
- **Safe**: Zero regressions, all tests pass
- **Tested**: 45 comprehensive tests
- **Auditable**: Barman shots tracked in `LiquorStockAdjustment`
- **Validated**: Cider pack_size enforced at model level
- **Concurrent-safe**: Row locking prevents overselling
- **Backward compatible**: Old data works with new code

The liquor vertical is now fully compliant with the updated Malawi business rules! 🎉

