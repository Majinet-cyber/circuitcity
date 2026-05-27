# Quick Test Guide: Agent Commission & Products Hide

## Quick Verification (5 minutes)

### 1. Test Products Hidden from Agents

```bash
# Start Django server
python manage.py runserver

# In browser:
# 1. Login as AGENT (from phones_agent_invite_flow test)
# 2. Navigate to /inventory/dashboard/
# 3. Check sidebar: "Products" link should NOT be visible
# 4. Try direct URL: /inventory/phone-products/ → Should get 403/Forbidden

# 5. Login as MANAGER/Owner
# 6. Navigate to /inventory/dashboard/
# 7. Check sidebar: "Products" link SHOULD be visible
# 8. Click Products → Should work normally
```

**Expected**: ✅ Agents don't see Products; Managers do

---

### 2. Test Commission Recording

```bash
# As AGENT:
# 1. Navigate to /inventory/phones/scan-in/
# 2. Scan in a phone:
#    - Brand: ITEL (or any brand)
#    - Model: Any model from dropdown
#    - IMEI: 123456789012345 (15 digits)
# 3. Click "Add to Stock"
# 4. Navigate to /inventory/phone-sale-wizard/
# 5. Sell the phone:
#    - Brand: ITEL
#    - Model: Same as above
#    - IMEI: 123456789012345
#    - Price: MWK 500,000
#    - Payment: Cash
# 6. Click "Complete Sale"
# 7. Navigate to /wallet/
```

**Expected**: ✅ My Wallet shows:
- Today Earnings: MWK 60,000 (12% of 500,000)
- Month to Date: MWK 60,000+
- All-Time: MWK 60,000+
- Current Balance: MWK 60,000+

---

### 3. Test Business Costs Include Commissions

```bash
# As MANAGER:
# 1. Navigate to /inventory/verticals/phones/dashboard/
# 2. Look at "COSTS" card:
#    - Should show "Cost of goods: MWK X"
#    - Should show "Business costs: MWK Y" (includes commission 60,000)
# 3. Look at "PROFIT" card:
#    - Should be: Revenue - (Cost of goods + Business costs)
#    - Example: 500,000 - (0 + 60,000) = 440,000
```

**Expected**: ✅ Commissions appear in "Business costs" and reduce Profit

---

## Database Verification (Optional)

```bash
# Django shell
python manage.py shell

# Check Sale record
from sales.models import Sale
sale = Sale.objects.filter(price=500000).last()
print(f"Sale price: {sale.price}")
print(f"Commission %: {sale.commission_pct}")
print(f"Commission amount: {sale.commission_amount}")  # Should be 60,000

# Check WalletTransaction
from wallet.models import WalletTransaction, Ledger, TxnType
commission_txn = WalletTransaction.objects.filter(
    ledger=Ledger.AGENT,
    type=TxnType.COMMISSION,
    amount=60000
).last()
print(f"Agent: {commission_txn.agent}")
print(f"Amount: {commission_txn.amount}")  # Should be 60,000
print(f"Note: {commission_txn.note}")
```

---

## Cypress Test (Full Integration)

```bash
# Run the full agent invite flow
npx cypress run --spec "cypress/e2e/phones_agent_invite_flow.cy.js"

# Or run in headed mode to watch:
npx cypress open
# Then select phones_agent_invite_flow.cy.js
```

**Expected**: ✅ Test passes (GREEN)
- Agent signup works
- Agent scans in phone
- Agent sells phone
- Agent walks sidebar (Products NOT visible, no 500 errors)
- Commission recorded automatically

---

## Troubleshooting

### Products Still Visible to Agent?
- Check `inventory/utils_verticals.py` line 341: `require_manager: True`
- Clear browser cache / use incognito
- Restart Django server

### Commission Not Showing in Wallet?
1. Check Sale was created:
   ```python
   from sales.models import Sale
   Sale.objects.filter(agent__username="agent_username").count()  # Should be > 0
   ```

2. Check WalletTransaction was created:
   ```python
   from wallet.models import WalletTransaction
   WalletTransaction.objects.filter(type="commission").count()  # Should be > 0
   ```

3. Check signals are enabled:
   ```python
   # In sales/apps.py, verify:
   def ready(self):
       import sales.signals  # Should be present
   ```

### Profit Calculation Wrong?
- Check `inventory/services/dashboard_metrics.py`
- Verify commissions are included in `total_business_costs`
- Check logs: `python manage.py runserver` (look for "Dashboard KPIs" log lines)

---

## Quick Rollback (If Needed)

```bash
# Revert sidebar change:
git checkout inventory/utils_verticals.py

# Revert commission wiring:
git checkout inventory/views_phone_sale_wizard.py

# Revert business costs:
git checkout inventory/services/dashboard_metrics.py

# Revert wallet template:
git checkout templates/wallet/agent_wallet.html
```

---

## Success Criteria

✅ Agents don't see "Products" in sidebar
✅ Agent sales create `Sale` objects with 12% commission
✅ WalletTransaction created automatically for each sale
✅ My Wallet shows commission earnings (Today/MTD/All-Time)
✅ Business costs include commissions
✅ Profit = Revenue - (COGS + Admin Costs + Commissions)
✅ Cypress test `phones_agent_invite_flow.cy.js` passes

---

## What Changed?

**4 files modified** (+ 1 template):
1. `inventory/utils_verticals.py` - Hide Products link
2. `inventory/views_phone_sale_wizard.py` - Create Sale records
3. `inventory/services/dashboard_metrics.py` - Include commissions in costs
4. `templates/wallet/agent_wallet.html` - Add test attributes

**Existing infrastructure reused** (no changes needed):
- `sales/signals.py` - Already handles commission creation
- `wallet/services_commission.py` - Already records commissions
- `wallet/services.py` - Already aggregates wallet data
- `wallet/views.py` - Already displays agent summary

**Commission rate**: 12% (default, configurable via `CommissionConfig`)

---

Ready to test! 🚀

