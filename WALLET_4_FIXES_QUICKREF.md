# Wallet 4 Fixes - Quick Reference

## What Was Fixed?

| Issue | Before | After |
|-------|--------|-------|
| **Units Sold** | Shows 2 after 1 sale | Shows 1 ✅ |
| **Commission Rate** | 12% (MK 60k on MK 500k) | 3% (MK 15k) ✅ |
| **Duplicates** | 2 commission txns per sale | 1 commission txn ✅ |
| **Ranking** | "Ranking unavailable" | Works like dashboard ✅ |
| **Payslip** | "No payslips yet" | Updates immediately ✅ |

## Files Changed (6)

1. `wallet/signals.py` - Removed duplicate signal
2. `sales/signals.py` - Added idempotency
3. `tenants/utils_commission.py` - Changed 12% → 3%
4. `wallet/views.py` - Fixed ranking + dynamic payslips
5. `tests/test_wallet_phones_agent_fixes.py` - NEW tests
6. `cypress/e2e/phones_agent_invite_flow.cy.js` - Added assertions

## Test Commands

```bash
# Unit tests
pytest tests/test_wallet_phones_agent_fixes.py -v

# Cypress E2E
npx cypress run --spec cypress/e2e/phones_agent_invite_flow.cy.js

# Run all phones tests
pytest tests/test_phones*.py tests/test_wallet*.py -v
```

## Verify After Deployment

1. Login as agent
2. Scan + sell 1 phone (e.g., MK 500,000)
3. Go to My Wallet
4. Verify:
   - ✅ "1 unit sold" (not 2)
   - ✅ Earnings = MK 15,000 (3% of 500k)
   - ✅ Ranking chart shows data
   - ✅ Payslip shows current month

## Root Causes

### Issue 1 & 3 (Units sold + Duplicates)
**Root:** Two signals both creating commissions:
- `sales/signals.py` → WalletTransaction
- `wallet/signals.py` → AgentWalletTransaction (REMOVED)

### Issue 2 (Commission %)
**Root:** `tenants/utils_commission.py` hardcoded `Decimal("0.12")`

### Issue 4 (Ranking)
**Root:** `wallet/views.py::api_ranking()` not using `agent_earnings` service

### Issue 5 (Payslip)
**Root:** Widget only queried formal `Payslip` model, not real-time commissions

## Key Code Changes

### 1. Removed Duplicate Signal
```python
# wallet/signals.py (line 32)
# REMOVED: Duplicate signal - commission is now created in sales/signals.py only
```

### 2. Changed Commission Rate
```python
# tenants/utils_commission.py
return Decimal("0.03")  # Changed from 0.12
```

### 3. Added Idempotency
```python
# sales/signals.py
existing = WalletTransaction.objects.filter(
    meta__sale_id=instance.id
).exists()
if existing:
    return  # Skip duplicate
```

### 4. Fixed Ranking API
```python
# wallet/views.py::api_ranking()
from inventory.services.agent_earnings import get_agent_earnings
earnings_data = get_agent_earnings(business=biz, ...)
```

### 5. Dynamic Payslips
```python
# wallet/views.py::AgentWalletView.get_context_data()
monthly_earnings = defaultdict(lambda: {'gross': Decimal('0'), ...})
for txn in commission_txns:
    year_month = (txn.effective_date.year, txn.effective_date.month)
    monthly_earnings[year_month]['gross'] += txn.amount
```

## No Migrations Required ✅

All changes are code-only. No database schema changes.

## Historical Data

- Old sales keep 12% commission (unchanged)
- New sales use 3% commission going forward
- No retroactive recalculation needed

## Per-Business Override

```python
from sales.models import CommissionConfig
config = CommissionConfig.ensure_config(business)
config.base_commission_pct = Decimal("5.00")  # Custom %
config.save()
```

## Support Checklist

If issues persist:
- [ ] Check signal logs: `grep "commission" logs/*.log`
- [ ] Verify commission rate: `get_phone_commission_pct(business)`
- [ ] Check for duplicate WalletTransactions: `WalletTransaction.objects.filter(meta__sale_id=X).count()`
- [ ] Verify agent_earnings service: `get_agent_earnings(business, ...)`

## Rollback Plan

If needed, revert commit and:
1. Restore `wallet/signals.py` handler
2. Change `tenants/utils_commission.py` back to 0.12
3. Revert `wallet/views.py` changes
4. Delete test files

## Success Metrics

After 24 hours in production:
- [ ] No "2 units sold" reports
- [ ] Agent commissions ~3% of sales (not 12%)
- [ ] No duplicate commission complaints
- [ ] Ranking charts loading in wallet
- [ ] Payslip showing current month data

---

**✅ All fixes complete with tests. Ready for deployment.**

