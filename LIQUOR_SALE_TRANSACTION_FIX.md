# Liquor Sale Transaction Fix

## Problem

Liquor Quick Sell was sometimes failing with the error:
```
"Sale failed: select_for_update cannot be used outside of a transaction."
```

## Root Cause

In `inventory/views_liquor.py`, the `sell_liquor` view was calling `select_for_update()` at line 183 **before** entering the `transaction.atomic()` block (which starts at line 274). Django's PostgreSQL backend requires `select_for_update()` to be executed within an atomic transaction block.

## Solution

### 1. Created Centralized Liquor Sale Service (`inventory/services/liquor_sale.py`)

- **`create_liquor_sale()`**: Main service function that wraps all sale operations in `@transaction.atomic`
- **`create_liquor_sale_by_barcode()`**: Barcode-based quick sell function for Fast Sell API
- Both functions ensure:
  - All `select_for_update()` calls happen inside the transaction
  - Stock decrements use atomic `F()` expressions to prevent race conditions
  - All related records (sale, credit, wallet) are created consistently

### 2. Updated `sell_liquor` View

- Removed `select_for_update()` call outside transaction
- Now uses `create_liquor_sale()` service function
- Improved error handling to catch `TransactionManagementError` and return user-friendly messages

### 3. Fixed Fast Sell API (`inventory/verticals/liquor.py`)

- Updated `fast_sell_create_api()` to use `create_liquor_sale_by_barcode()`
- Added proper error handling for transaction errors

### 4. Improved Error Handling

- All endpoints now catch `TransactionManagementError` and related DB errors
- Users never see raw "select_for_update..." errors
- Errors are logged with context (business_id, product_id, quantity, user_id)

## Key Changes

### Files Modified:
1. **`inventory/views_liquor.py`**
   - Removed `select_for_update()` outside transaction
   - Uses `create_liquor_sale()` service
   - Improved error handling

2. **`inventory/verticals/liquor.py`**
   - Updated `fast_sell_create_api()` to use new service
   - Added transaction error handling

### Files Created:
1. **`inventory/services/liquor_sale.py`**
   - Centralized liquor sale service with atomic transactions
   - `OutOfStockError` exception for stock validation
   - Barcode-based quick sell support

2. **`inventory/tests_liquor_transaction_safety.py`**
   - Comprehensive tests for transaction safety
   - Tests verify no `TransactionManagementError` is ever raised
   - Tests concurrent sales to prevent overselling

## Technical Details

### Atomic Stock Decrement

The service uses Django's `F()` expression for atomic stock decrement:

```python
updated = MerchProduct.objects.filter(
    pk=product.pk,
    quantity_in_stock__gte=quantity
).update(
    quantity_in_stock=F('quantity_in_stock') - quantity
)

if updated == 0:
    raise OutOfStockError(...)
```

This approach:
- Prevents race conditions (no overselling)
- Is more efficient than `select_for_update()` + manual decrement
- Works correctly even under high concurrency

### Transaction Boundaries

All critical operations happen within a single `@transaction.atomic` block:
- Product lookup with `select_for_update()`
- Stock validation and decrement
- Sale record creation
- Credit record creation (if credit sale)
- Wallet entry creation (if cash sale)

## Testing

### Manual Smoke Tests:
1. Go to Liquor → Quick Sell
2. Sell Beer (no shots) 10x - should succeed
3. Sell Spirits (shots) 10x - should succeed
4. Open two sessions and try selling the last remaining item simultaneously:
   - One should succeed
   - Other should get "Not enough stock" (no crashes)

### Automated Tests:
- `test_create_liquor_sale_is_atomic()` - Verifies service is atomic
- `test_select_for_update_inside_transaction()` - Ensures no TransactionManagementError
- `test_sale_fails_when_insufficient_stock()` - Stock validation
- `test_concurrent_sales_prevent_overselling()` - Race condition prevention
- `test_atomic_stock_decrement()` - F() expression correctness

## Acceptance Criteria Met

✅ **1. Liquor Quick Sell completes successfully**
   - Creates sale, reduces stock, records shift/ledger

✅ **2. No endpoint can raise "select_for_update cannot be used outside of a transaction"**
   - All `select_for_update()` calls are inside `@transaction.atomic`

✅ **3. All concurrency-sensitive stock deductions are atomic and safe**
   - Uses `F()` expressions for atomic decrement
   - Prevents overselling even under high concurrency

✅ **4. Errors are handled gracefully**
   - User-friendly messages (never raw DB errors)
   - Exceptions logged with context

✅ **5. Tests added**
   - Transaction safety tests
   - Stock validation tests
   - Concurrent sale tests

## Future Improvements

- Consider removing nested transactions in `create_liquor_sale_by_barcode()` (calls `create_liquor_sale()` which is already atomic)
- Add performance monitoring for transaction duration
- Consider using database-level constraints for additional safety

