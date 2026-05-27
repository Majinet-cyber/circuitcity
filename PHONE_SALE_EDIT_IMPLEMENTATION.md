# Phone Sale Edit Feature - Implementation Summary

## Overview
Added the ability to correct phone sale details (price and IMEI) without rolling back the sale. This allows managers to fix data entry errors without undoing the sale or affecting stock quantities.

## Files Created/Modified

### New Files
1. **`sales/services/phone_sale_edit.py`**
   - `PhoneSaleEditService.edit_phone_sale()` - Main service function for editing sales
   - `PhoneSaleEditService.can_edit_sale()` - Permission check function
   - `PhoneSaleEditService._update_commission()` - Updates SaleCommission records
   - `PhoneSaleEditService._update_wallet_commission()` - Updates WalletTransaction records
   - `SaleEditError` - Custom exception class

2. **`templates/sales/edit_phone_sale.html`**
   - Edit form template for correcting sale details
   - Shows current sale details
   - Form for updating price and IMEI
   - Cost price warning if selling price is below cost

### Modified Files
1. **`sales/views_rollback.py`**
   - Updated `rollback_confirm()` to show action choice (rollback vs edit)
   - Added `edit_phone_sale()` view for handling edit form submission
   - Added phone sale detection logic

2. **`templates/sales/rollback_confirm.html`**
   - Added action choice UI (rollback or edit)
   - Shows two action cards when viewing a phone sale
   - Redirects to edit form when "Correct Sale Details" is chosen

3. **`sales/urls.py`**
   - Added route: `path('phones/<int:sale_id>/edit/', views_rollback.edit_phone_sale, name='edit_phone_sale')`

## Features Implemented

### 1. Action Choice UI
- When viewing a phone sale rollback page, users see two options:
  - ✅ **Rollback Sale** - Undo the sale and restore stock
  - ✏️ **Correct Sale Details** - Update price/IMEI without undoing

### 2. Edit Sale Service
- **Atomic Transactions**: All updates happen in a single transaction
- **Row Locking**: Uses `select_for_update()` to prevent concurrent edits
- **Validation**:
  - Price must be >= 0
  - IMEI must be exactly 15 digits (if provided)
  - IMEI conflict checking (prevents duplicate IMEIs in sold items)
  - Business ownership verification
  - Prevents editing rolled-back sales

### 3. Automatic Updates
When a sale is edited, the following are automatically updated:
- **Sale.price** - Updated to new selling price
- **InventoryItem.selling_price** - Updated to match
- **InventoryItem.imei** - Updated if provided
- **SaleCommission.base_commission** - Recalculated based on new price
- **SaleCommission.net_amount** - Recalculated (bonuses/penalties preserved)
- **WalletTransaction.amount** - Updated commission amount if exists

### 4. Stock Quantities
- **NOT affected** - Stock quantities remain unchanged when editing
- This is intentional - editing is for correcting data, not undoing sales

### 5. Permissions
- Same permission model as rollback:
  - **Managers/Owners/Admins**: Can edit any sale
  - **Agents**: Can only edit their own sales
- Cannot edit sales that have been rolled back

## User Flow

1. User navigates to Sales → Rollback
2. User selects a phone sale to rollback
3. **NEW**: User sees action choice:
   - Option 1: Rollback Sale (existing flow)
   - Option 2: Correct Sale Details (new flow)
4. If "Correct Sale Details" is chosen:
   - User sees edit form with current price and IMEI
   - User updates price and/or IMEI
   - System validates inputs
   - System updates sale, commissions, and wallet transactions
   - Success message shown
   - User redirected back to rollback confirm page

## Validation Rules

### Selling Price
- Must be >= 0
- Must be numeric
- Warning shown if below cost price (but still allowed)

### IMEI
- Optional (can leave blank to keep current)
- If provided, must be exactly 15 digits
- Cannot conflict with another sold item's IMEI
- Can conflict with in-stock items (warning logged, but allowed)

## Technical Details

### Transaction Safety
- All operations wrapped in `@transaction.atomic`
- Row-level locking with `select_for_update()`
- Idempotent checks to prevent duplicate updates

### Commission Recalculation
- Uses `CommissionConfig` to determine commission mode (PERCENT or FIXED)
- Recalculates base commission based on new price
- Preserves bonuses and penalties
- Updates both `SaleCommission` and `WalletTransaction` records

### Error Handling
- All errors caught and displayed as user-friendly messages
- No HTTP 500 errors exposed to users
- Detailed logging for debugging

## Testing Checklist

1. ✅ Editing price updates sale total correctly
2. ✅ Editing IMEI updates stored IMEI correctly
3. ✅ Editing does NOT affect stock quantities
4. ✅ Permission test: non-manager cannot edit
5. ✅ Editing rolled-back sale is blocked
6. ✅ Commission amounts are recalculated correctly
7. ✅ Wallet transactions are updated correctly
8. ✅ IMEI validation works (15 digits, conflict checking)
9. ✅ Cost price warning appears when price < cost

## Manual Smoke Test

1. Make a phone sale with wrong price
2. Go to rollback page → select that sale
3. Choose "Correct Sale Details"
4. Set correct price and IMEI → Save
5. Verify:
   - Sale total updated
   - Dashboards revenue updated
   - Stock unchanged
   - Sale list shows new price/IMEI
   - Commission amounts updated

## Notes

- This feature is **phones-only** (detected by IMEI field on InventoryItem)
- Other verticals continue to use the standard rollback flow
- Email notifications are NOT automatically resent when sale is edited
- Reports and dashboards will automatically reflect updated totals (they query Sale.price directly)

## Future Enhancements (Optional)

- Add edit history/audit trail
- Support editing payment method
- Add "sale edited" email notifications
- Extend to other verticals (liquor, pharmacy, etc.)

