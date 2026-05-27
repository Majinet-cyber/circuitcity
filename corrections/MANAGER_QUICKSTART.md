# Data Corrections - Manager Quick Start Guide

**Last Updated**: February 5, 2026

## What is Data Corrections?

The Data Corrections system allows you (as a manager) to safely fix errors in your business data with:
- ✅ **Full audit trail** - Every change is logged
- ✅ **Preview before apply** - See the impact first
- ✅ **Rollback support** - Undo if you made a mistake
- ✅ **Batch operations** - Fix multiple records at once

## Who Can Use This?

**Only Managers** can create and apply data corrections. This ensures accountability and prevents unauthorized changes.

## When Should You Use Corrections?

Use data corrections when you need to fix:
- ❌ **Wrong prices** (selling price, cost price)
- ❌ **Wrong quantities** (stock levels, sale quantities)
- ❌ **Wrong payment methods** (marked as CASH but was MOBILE_MONEY)
- ❌ **Wrong product info** (name, size, color)
- ❌ **Wrong dates** (membership dates, payment dates)
- ❌ **Wrong member/customer info** (names, phone numbers)

**DO NOT** use corrections for:
- ✋ Deleting records (use archive/void features instead)
- ✋ Adding new records (use regular create forms)
- ✋ Routine data entry (this is for fixing mistakes)

---

## How to Use (Step by Step)

### For PHONES Vertical

1. **Go to Data Correction**
   - Navigate to: `/verticals/phones/data-correction/` (or click "Data Correction" in sidebar)

2. **Search for the Record**
   - Use the search box to find the item by IMEI, product name, or SKU
   - Apply filters: All / Sales / Stock-In / Accessories / Voided

3. **Click "Edit" on the Record**
   - Opens the correction form

4. **Make Your Changes**
   - Enter the correct values
   - **REQUIRED**: Explain why you're making this change in the "Reason" field
   - Example reason: "Customer disputed price - correcting from 50000 to 55000"

5. **Preview the Impact**
   - See how this will affect revenue and profit
   - Review all changes before applying

6. **Apply the Correction**
   - Click "Apply Correction"
   - Changes are applied immediately and logged

7. **Verify**
   - Check the record to ensure it's corrected
   - Review the audit trail

### For CLOTHING Vertical

**Coming Soon!** The Clothing corrections adapter is ready, but the UI is being built.

**What you can correct**:
- Product prices (selling_price, cost_price)
- Stock quantities (quantity_in_stock)
- Sale transactions (unit_price, total_price, quantity)
- Product info (name, size, color)

### For GYM Vertical

**Coming Soon!** The Gym corrections adapter is ready, but the UI is being built.

**What you can correct**:
- Member info (name, phone, email)
- Payment amounts (membership_amount, trainer_fee)
- Membership dates (start_date, end_date)
- Payment methods

---

## Using Python API (Advanced)

If you're technical, you can use the corrections service directly in Django shell or views:

```python
from corrections.service import CorrectionService
from tenants.models import Business

# Get your business
business = Business.objects.get(name="My Business")

# Initialize service (must be manager)
service = CorrectionService(
    business=business,
    user=request.user,  # Must be a manager
    request=request,
)

# Create a batch
result = service.create_batch(
    vertical='phones',  # or 'clothing', 'gym'
    reason='Fix incorrect prices from data import',
    notes='Batch correction for Feb 2026 import',
)
batch = result.batch

# Add correction items
result = service.add_items(
    batch=batch,
    items=[
        {
            'entity_label': 'phone_sale',
            'object_id': 123,  # InventoryItem ID
            'field_name': 'selling_price',
            'new_value': '55000',
        },
    ],
)

# Preview impact
result = service.preview_batch(batch)
print(f"Revenue impact: {batch.revenue_impact}")
print(f"Profit impact: {batch.profit_impact}")

# Apply corrections
result = service.apply_batch(batch)
if result.success:
    print(f"Applied {batch.items_applied} corrections")
else:
    print(f"Errors: {result.errors}")
```

---

## Finding Erroneous Entries Automatically

The system can automatically find records that may need correction:

### Phones
- Sales where selling price < cost price (losses)
- Accessories with negative stock
- Stock items with cost = 0

### Clothing
- Products with negative stock
- Products where selling_price < cost_price
- Sales where total_price < total_cost

### Gym
- Payments where total amount doesn't match membership + trainer fee
- Members with expired memberships still marked as active
- Members with negative fees

**How to use**:
```python
from corrections.registry import registry

# Get adapter
adapter = registry.get_adapter('phones')

# Find erroneous entries
items = adapter.find_erroneous_entries(
    entity_label='phone_sale',
    business=business,
    limit=50,
)
```

---

## Audit Trail

Every correction is logged with:
- **Who** made the change (your name)
- **What** was changed (field, old value → new value)
- **When** it was changed (timestamp)
- **Why** it was changed (your reason)
- **Where** the request came from (IP address)

To view the audit trail:
- Go to: `/verticals/<vertical>/data-correction/audit/`
- Or check the "Correction History" section on each correction page

---

## Rollback (Undo)

If you realize a correction was wrong, you can roll it back:

1. Find the batch in the audit trail
2. Click "Rollback Batch"
3. Confirm rollback
4. Original values are restored

**Note**: You can only rollback batches that have been applied. Draft/preview batches cannot be rolled back.

---

## Best Practices

### ✅ DO
- **Write clear reasons** - Future you (or another manager) needs to understand why
- **Preview before applying** - Always check the impact first
- **Use batches** - Group related corrections together
- **Verify after applying** - Check the record to ensure it's correct
- **Document patterns** - If you see the same error repeatedly, fix the root cause

### ❌ DON'T
- **Guess values** - If you're not sure, investigate first
- **Batch unrelated corrections** - Keep batches focused (one type of error per batch)
- **Skip the reason** - This is required for accountability
- **Correct without understanding** - Understand why the error occurred
- **Use corrections for routine data entry** - This is for fixing mistakes only

---

## Common Scenarios

### Scenario 1: Wrong Price Entered
**Problem**: Agent entered selling price as 5000 instead of 50000 (missed a zero)

**Solution**:
1. Search for the sale by IMEI or product
2. Click "Edit"
3. Change selling_price from 5000 to 50000
4. Reason: "Missing zero in price entry - should be 50000 not 5000"
5. Preview impact: Revenue +45000, Profit +45000
6. Apply correction

### Scenario 2: Wrong Payment Method
**Problem**: Sale was marked as CASH but customer paid via MOBILE_MONEY

**Solution**:
1. Find the sale
2. Edit payment_method from CASH to MOBILE_MONEY
3. Reason: "Customer paid via mobile money, not cash"
4. Apply (no revenue impact, just classification)

### Scenario 3: Negative Stock
**Problem**: Stock shows -5 units due to a bug

**Solution**:
1. Find the accessory product
2. Edit quantity_in_stock from -5 to 0 (or correct value)
3. Reason: "Stock went negative due to double-deduction bug - correcting to actual stock count of 0"
4. Apply correction

### Scenario 4: Batch Import Error
**Problem**: Imported 50 products with cost_price = 0 instead of actual cost

**Solution**:
1. Create a batch: "Fix imported products with zero cost"
2. Add items (you can do this programmatically for 50 items)
3. Preview total impact
4. Apply batch (all 50 corrections applied at once)

---

## Troubleshooting

### "Permission Denied"
**Cause**: You're not a manager
**Solution**: Contact your business owner to grant you manager permissions

### "Invalid value for field"
**Cause**: The new value doesn't pass validation (e.g., negative price)
**Solution**: Check the field requirements and enter a valid value

### "Object not found"
**Cause**: The record was deleted or doesn't belong to your business
**Solution**: Verify the record exists and you have access

### "Batch already applied"
**Cause**: You're trying to apply a batch that was already applied
**Solution**: Create a new batch if you need to make more corrections

---

## FAQ

**Q: Can I correct data from other businesses?**
A: No, you can only correct data for your own business.

**Q: Can I delete a correction after applying it?**
A: No, but you can **rollback** the batch to restore original values.

**Q: How long are audit logs kept?**
A: Forever. Audit logs are never deleted for compliance.

**Q: Can I correct the same record multiple times?**
A: Yes, you can apply multiple corrections to the same record. Each correction is logged separately.

**Q: What happens if a correction fails?**
A: The item is marked as failed with an error message. Other items in the batch are still applied (if valid).

**Q: Can I export correction logs?**
A: Yes, go to the audit trail page and click "Export CSV".

---

## Getting Help

If you have questions or encounter issues:
1. Check this guide first
2. Check the corrections README: `corrections/README.md`
3. Contact your system administrator
4. Report bugs to the dev team

---

## Security Notes

- Only managers can create/apply corrections
- Every action is audited (who, what, when, why)
- IP addresses are logged for forensics
- Corrections cannot be deleted (only rolled back)
- You cannot modify another business's data

---

## Version History

- **v1.0** (Feb 5, 2026) - Initial release with Phones, Clothing, Gym adapters

---

**Remember**: Data corrections are powerful but should be used carefully. Always preview before applying, and write clear reasons for every change!

