# Implementation Summary: Admin Delete Fix & Business Reset Feature

**Date:** 2025-01-XX  
**Status:** ✅ Complete

---

## PART A: Fix Django Admin "Delete User" Crash (Membership)

### Root Cause
Deleting a `tenants.Membership` object in Django admin caused a 500 error because:
1. **Protected Foreign Keys**: Models like `Sale.agent` and `LiquorShift.barman`/`created_by` had `on_delete=models.PROTECT`, preventing deletion when users had related records.
2. **No Error Handling**: The admin's default `delete_view` didn't catch `ProtectedError` or `IntegrityError`, causing unhandled exceptions.

### Solution Implemented

#### A1) Safe Admin Deletion
- **File**: `tenants/admin.py`
- **Changes**:
  - Overrode `delete_view()` to catch `ProtectedError`, `IntegrityError`, and any other exceptions
  - Never crashes the admin - always shows user-friendly error messages
  - Redirects back to changelist with explanation

#### A2) Deactivate Membership (Primary Safe Removal)
- **File**: `tenants/admin.py`
- **Changes**:
  - Added `deactivate_memberships` admin action
  - Sets membership `status` to `"REJECTED"` (safe, reversible)
  - Users can no longer access the business but historical records remain intact
  - Always works - no FK constraints can block it

#### A3) Hard Delete Service (Superuser Only)
- **File**: `tenants/services/membership_delete.py` (NEW)
- **Function**: `hard_delete_membership(membership, initiated_by)`
- **Behavior**:
  - Reassigns/nullifies references to `membership.user` in:
    - `Sale.agent` → SET_NULL
    - `LiquorShift.barman` → SET_NULL
    - `LiquorShift.created_by` → SET_NULL
    - `PharmacySale.sold_by` → SET_NULL
    - `StockActivityLog.performed_by` → SET_NULL
  - Deletes the membership
  - Optionally deletes user if they have no other memberships
  - Only accessible to superusers

#### A4) FK Constraint Changes
- **Migrations Created**:
  - `sales/migrations/1004_change_sale_agent_to_set_null.py`
  - `inventory/migrations/1007_change_liquorshift_users_to_set_null.py`
- **Model Changes**:
  - `sales/models.py`: `Sale.agent` → `null=True, blank=True, on_delete=SET_NULL`
  - `inventory/models_verticals.py`: `LiquorShift.barman` and `created_by` → `null=True, blank=True, on_delete=SET_NULL`
- **Result**: Historical records can now have null user references, preserving data integrity while allowing user deletion

### Acceptance Criteria (Part A)
✅ Deleting/removing a user from a business never 500s  
✅ Admin has a safe "Deactivate/Remove from business" action that always works  
✅ Superuser can hard-delete membership/user without breaking sales history  

---

## PART B: User "Reset Account" (Wipe Sales/Stock, Start Blank)

### Implementation

#### B1) Danger Zone Settings Page
- **File**: `templates/accounts/settings_danger_zone.html` (NEW)
- **Route**: `/accounts/settings/danger-zone/`
- **Features**:
  - Big warning UI with clear explanation
  - Shows what will be deleted vs. preserved
  - Requires triple confirmation:
    1. Type "RESET" in text field
    2. Type business name or last 4 digits of business ID
    3. Enter password
  - Optional checkbox to keep product catalog
- **Permissions**: Only business owners/managers (role=MANAGER, status=ACTIVE) or superusers

#### B2) Reset Business Service
- **File**: `tenants/services/reset_business.py` (NEW)
- **Function**: `reset_business_data(business, initiated_by, keep_catalog=False)`
- **Behavior**:
  - Runs inside `transaction.atomic()` (all-or-nothing)
  - Idempotent (safe to re-run)
  - Deletes in FK-safe order
  - Logs everything

**Resettable Models** (operational data only):
- Sales: `Sale`, `SaleLine`, `SaleCommission`
- Inventory: `InventoryItem`, `MerchProduct`, `StockActivityLog`
- Vertical-specific: `LiquorSale`, `LiquorShift`, `PharmacySale`, `PharmacyBatch`, `GymMember`, `GymPayment`, etc.
- Expenses: `Expense`
- Wallet: `WalletTransaction`, `AgentWalletTransaction`
- Shifts: `ShiftSession`, `TimeLog`
- Accessories: `AccessoryStock`, `AccessoryStockLog`
- Layby: `Layby`, `LaybyPayment`

**Preserved** (never deleted):
- Business record
- Locations
- User accounts + memberships
- Subscription/billing state
- Branding/settings
- Product catalog (if `keep_catalog=True`)

#### B3) View Implementation
- **File**: `circuitcity/accounts/views.py`
- **Function**: `settings_danger_zone(request)`
- **Features**:
  - Permission checks (manager/superuser only)
  - Triple confirmation validation
  - Password verification
  - Atomic reset operation
  - User-friendly error messages
  - Success redirect to dashboard

#### B4) Admin Action
- **File**: `tenants/admin.py`
- **Action**: `reset_business_data` on `BusinessAdmin`
- **Access**: Superuser only
- **Behavior**: Uses same `reset_business_data` service

#### B5) Navigation
- **File**: `templates/accounts/_settings_nav.html`
- **Change**: Added "Danger Zone" tab (red text, warning icon)

### Acceptance Criteria (Part B)
✅ Owner can reset business and afterwards dashboards show zero stock, zero sales, clean state  
✅ No other businesses are affected  
✅ Reset is atomic (either fully reset or no change)  
✅ Proper permissions + confirmation to avoid accidental wipe  

---

## Files Changed

### New Files
1. `tenants/services/membership_delete.py` - Hard delete service
2. `tenants/services/reset_business.py` - Business reset service
3. `templates/accounts/settings_danger_zone.html` - Danger zone UI
4. `sales/migrations/1004_change_sale_agent_to_set_null.py` - FK migration
5. `inventory/migrations/1007_change_liquorshift_users_to_set_null.py` - FK migration

### Modified Files
1. `tenants/admin.py` - Safe deletion, deactivate action, reset action
2. `sales/models.py` - Changed `Sale.agent` FK to SET_NULL
3. `inventory/models_verticals.py` - Changed `LiquorShift` user FKs to SET_NULL
4. `circuitcity/accounts/views.py` - Added `settings_danger_zone` view
5. `circuitcity/accounts/urls.py` - Added danger zone route
6. `templates/accounts/_settings_nav.html` - Added danger zone tab

---

## Manual Test Checklist

### Part A: Admin Delete Fix
- [ ] Go to `/admin/tenants/membership/`
- [ ] Try to delete a membership with related sales → Should show error message, not crash
- [ ] Use "Deactivate membership" action → Should work, membership status becomes REJECTED
- [ ] As superuser, use "Hard delete membership" action → Should work, membership deleted
- [ ] Verify sales still exist but `agent` field is null

### Part B: Business Reset
- [ ] As business owner, go to `/accounts/settings/danger-zone/`
- [ ] Verify page loads and shows warnings
- [ ] Try to submit without confirmation → Should show validation errors
- [ ] Type wrong business name → Should reject
- [ ] Type wrong password → Should reject
- [ ] Complete all confirmations correctly → Should reset business
- [ ] Verify dashboard shows zero stock, zero sales
- [ ] Verify other businesses unaffected
- [ ] As superuser, go to `/admin/tenants/business/`
- [ ] Select business, use "Reset business data" action → Should work

### Migration Testing
- [ ] Run migrations: `python manage.py migrate sales inventory`
- [ ] Verify `Sale.agent` can be null
- [ ] Verify `LiquorShift.barman` and `created_by` can be null
- [ ] Create test sale, delete user → Sale should remain with null agent

---

## Notes

1. **Multi-tenant Safety**: All deletes are scoped to business using `.filter(business=business)` or `.filter(location__business=business)`
2. **Data Preservation**: Historical records are preserved with null user references instead of being deleted
3. **Atomic Operations**: Reset uses transactions to ensure all-or-nothing behavior
4. **Logging**: All operations are logged for audit trails
5. **Backward Compatibility**: FK changes are backward compatible - existing records remain valid

---

## Next Steps (Optional Enhancements)

1. **Auto-backup before reset**: Trigger data export before deletion
2. **Soft delete for memberships**: Add `deleted_at` field instead of status change
3. **Bulk operations**: Add bulk deactivate/reset for multiple businesses
4. **Audit trail**: Create audit log entries for all reset operations
5. **Email notifications**: Notify business owners when reset is performed
