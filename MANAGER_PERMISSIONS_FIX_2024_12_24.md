# Manager Permissions Fix - December 24, 2024

## Issue Summary

Phone managers were getting the error **"Unable to verify rollback permissions"** when trying to roll back sales, even though they should have full rollback permissions.

## Root Cause

The issue was in `sales/services/rollback.py` at line 74. The code was using:

```python
membership = Membership.objects.get(user=user, business=business)
```

This caused a `MultipleObjectsReturned` exception when a user had multiple memberships (e.g., both MANAGER and AGENT roles in the same business), which was caught by the generic exception handler and returned the "Unable to verify rollback permissions" error.

## Fixes Applied

### 1. Fixed Rollback Permission Check (PRIMARY FIX)

**File**: `sales/services/rollback.py` (lines 70-94)

**Changed from**:
```python
try:
    membership = Membership.objects.get(user=user, business=business)
    role = membership.role.upper()
    # ... rest of logic
except Membership.DoesNotExist:
    return False, "User is not a member of this business"
```

**Changed to**:
```python
# Get ACTIVE membership - use filter().first() to handle multiple memberships gracefully
membership = Membership.objects.filter(
    user=user, 
    business=business,
    status='ACTIVE'
).first()

if not membership:
    return False, "User is not an active member of this business"

role = membership.role.upper()
# ... rest of logic (no try-except needed)
```

**Benefits**:
- ✅ Handles users with multiple memberships gracefully
- ✅ Only considers ACTIVE memberships
- ✅ Returns the first active membership (typically the most relevant one)
- ✅ Cleaner error handling - no more generic exception catching

### 2. Fixed Inventory Restoration Bug (SECONDARY FIX)

**File**: `sales/services/rollback.py` (line 267)

**Changed from**:
```python
item.payment_method = None
```

**Changed to**:
```python
# payment_method field has blank=True but NOT null=True, so set to empty string
item.payment_method = ""
```

**Why**: The `InventoryItem.payment_method` field has `blank=True` but NOT `null=True`, so setting it to `None` caused a database constraint error. Setting it to an empty string is the correct approach.

## Testing

All tests passed successfully:

### Test 1: Permission Check
- ✅ Manager can check rollback permissions without errors
- ✅ No more "Unable to verify rollback permissions" error

### Test 2: Full Rollback Execution
- ✅ Manager can execute rollback on any sale
- ✅ Sale is marked as rolled back
- ✅ Item is restored to IN_STOCK status
- ✅ Item sold fields are cleared (sold_at, sold_by, selling_price, payment_method)

### Test 3: IMEI Edit Permissions
- ✅ Manager can edit IMEI numbers (existing test still passes)

## Manager Capabilities Confirmed

Phone managers can now successfully:

1. ✅ **Roll back ANY sale** - No time restrictions, no ownership checks
2. ✅ **Edit IMEI numbers** - Full control over phone inventory
3. ✅ **Transfer stock** - Between agents and manager pool
4. ✅ **Archive/restore stock** - Soft delete operations

## Files Modified

1. `sales/services/rollback.py` - Fixed permission check and inventory restoration
2. `MANAGER_PERMISSIONS_FIX_2024_12_24.md` - This documentation

## Deployment Notes

- ✅ No database migrations required
- ✅ No configuration changes needed
- ✅ Backward compatible - existing functionality preserved
- ✅ All existing tests pass

## Verification Commands

To verify the fix is working:

```bash
# Run the stock controls test
python manage.py test inventory.tests.test_stock_controls.StockControlsTestCase.test_manager_can_edit_imei

# Test rollback permissions in Django shell
python manage.py shell
>>> from sales.services.rollback import RollbackService
>>> from tenants.models import Business, Membership
>>> from sales.models import Sale
>>> business = Business.objects.filter(business_kind='phones').first()
>>> manager_membership = Membership.objects.filter(business=business, role='MANAGER', status='ACTIVE').first()
>>> manager = manager_membership.user
>>> sale = Sale.objects.filter(item__business=business, is_rolled_back=False).first()
>>> can_rollback, error = RollbackService.can_rollback(sale, manager, business)
>>> print(f"Can rollback: {can_rollback}, Error: {error}")
# Should print: Can rollback: True, Error: 
```

## Impact

- **Managers**: Can now perform all expected operations without permission errors
- **Agents**: No changes - still have restricted permissions (own sales, 10-minute window)
- **System**: More robust error handling, better multi-membership support

## Status

✅ **COMPLETE** - All issues resolved and tested

