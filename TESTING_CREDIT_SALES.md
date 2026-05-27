# Testing Guide: Liquor Credit Sales Fix

## Quick Test Scenario

### Prerequisites
- Access as Manager role in a Liquor business
- At least one active liquor product in inventory

---

## Test 1: Record Credit Sale & Verify KPIs Don't Change

### Steps:
1. **Check Initial KPIs**
   - Navigate to `/liquor/` (Liquor Dashboard)
   - Note the current **Revenue** value
   - Take a screenshot or write down the amount

2. **Record a Credit Sale**
   - Option A (via Wizard/Sell page):
     - Go to Liquor → Sell
     - Select a product
     - Choose "Credit Sale" as sale type
     - Enter customer name: "Test Customer A"
     - Enter amount: MK 10,000
     - Submit
   
   - Option B (Convert existing sale):
     - Go to Liquor → Sales
     - Find a recent cash sale
     - Click "Convert to Credit"
     - Enter customer name: "Test Customer A"
     - Submit

3. **Verify Credit Appears**
   - Go to `/liquor/credits/`
   - Should see credit for "Test Customer A"
   - Status: **Outstanding** (yellow badge)
   - Balance: **MK 10,000.00**

4. **Verify KPIs Unchanged**
   - Go back to `/liquor/` (Dashboard)
   - Revenue should be **EXACTLY THE SAME** as before
   - ✅ **PASS:** Credit does not count in revenue yet

---

## Test 2: Clear Credit & Verify Revenue Increases

### Steps:
1. **Note Current Revenue**
   - Go to `/liquor/` (Dashboard)
   - Write down current **Revenue** value
   - Example: MK 50,000.00

2. **Clear the Credit**
   - Go to `/liquor/credits/`
   - Find "Test Customer A" credit
   - Click green **"Clear"** button
   - **Modal appears** with:
     - Explanation of what clearing does
     - Customer name: Test Customer A
     - Amount: MK 10,000.00
     - Confirmation prompt
   - Click **"Yes, Clear Credit"**

3. **Verify Success Message**
   - Should see: ✅ "Credit cleared for Test Customer A! MK 10,000.00 now included in revenue."

4. **Verify Credit Status Changed**
   - Credit status now: **Settled** (green badge)
   - Still appears in credits list (history)

5. **Verify Revenue Increased**
   - Go to `/liquor/` (Dashboard)
   - Revenue should now be: **Previous + MK 10,000.00**
   - Example: MK 50,000 + MK 10,000 = **MK 60,000.00**
   - ✅ **PASS:** Cleared credit counts in revenue

---

## Test 3: Cash Sales Still Work (No Regressions)

### Steps:
1. **Note Current Revenue**
   - Dashboard shows: MK 60,000.00 (from previous tests)

2. **Record Cash Sale**
   - Go to Liquor → Sell
   - Select any product
   - Select "Cash Sale" (default)
   - Enter amount: MK 5,000
   - Submit

3. **Verify Immediate Revenue Increase**
   - Go to Dashboard
   - Revenue should now be: **MK 65,000.00**
   - ✅ **PASS:** Cash sales counted immediately (no change in behavior)

---

## Test 4: Filter and Search Credits

### Steps:
1. **Go to `/liquor/credits/`**

2. **Test Status Filter**
   - Select "Outstanding" → Should show only open/partial credits
   - Select "Settled" → Should show only cleared credits
   - Select "All Statuses" → Shows everything

3. **Test Search**
   - Enter customer name in search box
   - Click "Filter"
   - Should show only matching credits

4. **Clear Filters**
   - Click "Clear Filters" button
   - All credits visible again

---

## Test 5: Security (Manager-Only)

### Steps:
1. **Login as Non-Manager (Agent/Bartender)**

2. **Try to Clear Credit**
   - Go to `/liquor/credits/`
   - Credits list visible ✅
   - "Clear" button **should NOT be visible** for non-managers
   - Or if visible, clicking should show: "Access denied" or redirect

3. **Try Direct URL**
   - Try accessing: `/liquor/credit/1/clear/` (POST)
   - Should get: "Permission denied" or redirect
   - ✅ **PASS:** Only managers can clear credits

---

## Expected Results Summary

| Action | Revenue Before | Revenue After | Expected |
|--------|----------------|---------------|----------|
| Record credit sale (MK 10,000) | MK 50,000 | MK 50,000 | ✅ No change |
| Clear credit (MK 10,000) | MK 50,000 | MK 60,000 | ✅ Increased by cleared amount |
| Cash sale (MK 5,000) | MK 60,000 | MK 65,000 | ✅ Increased immediately |

---

## Common Issues & Solutions

### Issue: "Clear" button not visible
**Solution:** Ensure you're logged in as Manager role

### Issue: Modal doesn't appear
**Solution:** Check browser console for JS errors, ensure Bootstrap JS is loaded

### Issue: Revenue doesn't update after clearing
**Solution:**
1. Hard refresh the dashboard (Ctrl+F5)
2. Check if credit status changed to "Settled"
3. Check server logs for errors

### Issue: Credit not appearing in list
**Solution:** 
1. Check if filters are active (clear them)
2. Verify credit was created successfully (check database or recent activities)

---

## Database Queries for Verification

```sql
-- Check outstanding credits
SELECT customer_name, amount, status, created_at 
FROM inventory_liquorcredit 
WHERE business_id = YOUR_BUSINESS_ID 
  AND status = 'open';

-- Check settled credits
SELECT customer_name, amount, status, settled_at, settled_by_id
FROM inventory_liquorcredit 
WHERE business_id = YOUR_BUSINESS_ID 
  AND status = 'settled';

-- Check credit sales in LiquorSale
SELECT id, product_id, total_price, is_credit, sold_at
FROM inventory_liquorsale
WHERE business_id = YOUR_BUSINESS_ID
  AND is_credit = true;
```

---

## Automated Test Script (Optional)

```python
# tests/test_liquor_credits.py
from django.test import TestCase
from inventory.models_verticals import LiquorCredit, LiquorCreditStatus
from decimal import Decimal

class LiquorCreditsTestCase(TestCase):
    def test_credit_revenue_flow(self):
        # 1. Get initial revenue
        initial_revenue = self.get_dashboard_revenue()
        
        # 2. Create credit
        credit = self.create_credit_sale(amount=Decimal("10000.00"))
        
        # 3. Verify revenue unchanged
        current_revenue = self.get_dashboard_revenue()
        self.assertEqual(current_revenue, initial_revenue)
        
        # 4. Clear credit
        self.clear_credit(credit)
        
        # 5. Verify revenue increased
        final_revenue = self.get_dashboard_revenue()
        self.assertEqual(final_revenue, initial_revenue + Decimal("10000.00"))
        
        # 6. Verify credit status
        credit.refresh_from_db()
        self.assertEqual(credit.status, LiquorCreditStatus.SETTLED)
```

---

## Video Walkthrough (Recommended)

Record a 2-minute screen recording showing:
1. Dashboard before (note revenue)
2. Create credit sale
3. Dashboard after (revenue unchanged)
4. Click Clear button
5. Confirm modal
6. Dashboard after clearing (revenue increased)
7. Credits list showing settled status

Share with team for training purposes.

---

## Sign-Off Checklist

- [ ] Test 1: Credit doesn't affect revenue - PASS
- [ ] Test 2: Clearing credit increases revenue - PASS
- [ ] Test 3: Cash sales still work - PASS
- [ ] Test 4: Filters work correctly - PASS
- [ ] Test 5: Manager-only security - PASS
- [ ] UI looks good on mobile
- [ ] UI looks good on desktop
- [ ] No console errors
- [ ] No server errors in logs

**Tester Name:** _______________  
**Date:** _______________  
**Status:** ☐ APPROVED  ☐ NEEDS FIXES

---

**Ready for Production!** 🚀

