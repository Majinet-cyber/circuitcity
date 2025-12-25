# Manager Permissions Fix - December 24, 2024 (UPDATED)

## Issue Summary

Phone managers were getting two errors when trying to roll back sales:
1. **"Unable to verify rollback permissions"** - Permission check was failing completely
2. **"Agents can only rollback their own sales"** - Managers were being treated as agents

Both issues prevented managers from exercising their full operational control over sales.

## Root Causes

### Issue 1: "Unable to verify rollback permissions"
The code in `sales/services/rollback.py` at line 74 was using:
```python
membership = Membership.objects.get(user=user, business=business)
```

This caused a `MultipleObjectsReturned` exception when a user had multiple memberships, which was caught by the generic exception handler and returned the "Unable to verify rollback permissions" error.

### Issue 2: "Agents can only rollback their own sales"
Even after fixing Issue 1, if the `.first()` query returned an AGENT membership when the user had multiple roles, the manager would be treated as an agent and denied permission to rollback sales made by other agents.

## Fixes Applied

### 1. Fixed Rollback Permission Check with Role Prioritization (PRIMARY FIX)

**File**: `sales/services/rollback.py` (lines 70-101)

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
# Get ACTIVE membership - prioritize MANAGER > AGENT
# This handles users with multiple memberships by checking manager role first
from django.db.models import Case, When, Value, IntegerField

membership = Membership.objects.filter(
    user=user, 
    business=business,
    status='ACTIVE'
).annotate(
    role_priority=Case(
        When(role='MANAGER', then=Value(1)),
        When(role='OWNER', then=Value(1)),
        When(role='ADMIN', then=Value(1)),
        When(role='AGENT', then=Value(2)),
        default=Value(3),
        output_field=IntegerField()
    )
).order_by('role_priority').first()

if not membership:
    return False, "User is not an active member of this business"

role = membership.role.upper()
# ... rest of logic (no try-except needed)
```

**Benefits**:
- ✅ Handles users with multiple memberships gracefully
- ✅ Only considers ACTIVE memberships
- ✅ **Prioritizes MANAGER/OWNER/ADMIN over AGENT** - This is the key fix!
- ✅ Ensures managers are never treated as agents
- ✅ Cleaner error handling - no more generic exception catching

**Role Priority**:
- Priority 1: MANAGER, OWNER, ADMIN (full permissions)
- Priority 2: AGENT (restricted permissions)
- Priority 3: Other roles

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
- ✅ No more "Agents can only rollback their own sales" error for managers

### Test 2: Role Prioritization
- ✅ MANAGER role takes precedence over AGENT role
- ✅ Query correctly prioritizes roles (MANAGER=1, AGENT=2)
- ✅ Managers with any role configuration are treated as managers

### Test 3: Full Rollback Execution
- ✅ Manager can execute rollback on ANY sale (including sales by other agents)
- ✅ Sale is marked as rolled back
- ✅ Item is restored to IN_STOCK status
- ✅ Item sold fields are cleared (sold_at, sold_by, selling_price, payment_method)

### Test 4: IMEI Edit Permissions
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

## Additional Notes

### Why Role Prioritization Matters

In the CircuitCity system, it's possible (though rare) for a user to have multiple memberships with different roles in the same business context. When this happens, the system must determine which role to use for permission checks.

The fix ensures that:
1. **Manager roles always take precedence** - If a user has both MANAGER and AGENT roles, they are always treated as a manager
2. **Permission elevation, not restriction** - Users get the highest level of permissions they're entitled to
3. **Predictable behavior** - The same user always gets the same permissions, regardless of database ordering

### Testing with Real Data

To verify the fix is working in production:

```python
# Test with a manager user
from sales.services.rollback import RollbackService
from tenants.models import Membership

# Get a manager
manager = Membership.objects.filter(role='MANAGER', status='ACTIVE').first().user

# Get any un-rolled sale
sale = Sale.objects.filter(is_rolled_back=False).first()

# This should return (True, "")
can_rollback, error = RollbackService.can_rollback(sale, manager, sale.item.business)
print(f"Manager can rollback: {can_rollback}, Error: {error}")
```

## Status

✅ **COMPLETE** - All issues resolved and tested

**Issues Fixed**:
1. ✅ "Unable to verify rollback permissions" error
2. ✅ "Agents can only rollback their own sales" error for managers
3. ✅ Role prioritization for users with multiple memberships
4. ✅ Inventory restoration bug (payment_method field)

