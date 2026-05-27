# Phones Agent Base Salary Implementation

## Overview
Implemented MWK 50,000 monthly base salary for all Phones vertical agents.

## Files Changed

### 1. `wallet/utils_salary.py` (NEW)
- Created new module with salary helpers
- `ensure_monthly_base_salary_for_agent(business, user, today=None)`:
  - Only runs for Phones vertical (`business_kind="phones"`)
  - Only runs for active AGENT memberships
  - Creates exactly 1 base salary transaction per agent per month
  - Idempotent (checks for existing transaction first)
  - Uses `meta.kind="phones_base_salary"` for identification
  - Uses `meta.month="YYYY-MM"` for month tracking
  - Amount: MWK 50,000
  - Type: TxnType.BONUS (to distinguish from commission)

- `get_base_salary_for_month(business, user, year, month)`:
  - Retrieves base salary amount for a specific month
  - Returns Decimal("0.00") if not applicable

### 2. `wallet/views.py`
Updated `AgentWalletView.get_context_data()`:
- Calls `ensure_monthly_base_salary_for_agent()` before computing earnings
- Ensures base salary exists whenever agent visits wallet page

Updated dynamic payslip computation (lines 569-595):
- Changed from only commission transactions to commissions + bonuses
- Now includes base salary in gross calculations
- Also includes deductions for net calculation

Updated `_create_or_update_payslip_and_txn()`:
- Modified to use `get_base_salary_for_month()` instead of hardcoded setting
- Falls back to `WALLET_BASE_SALARY` setting if no transaction exists

### 3. `tests/test_wallet_phones_agent_fixes.py`
Added comprehensive test suite `TestPhonesBaseSalary` with 8 tests:

1. `test_phone_agent_base_salary_created_once_per_month`
   - Verifies exactly 1 base salary per month
   - Tests idempotency (multiple calls don't create duplicates)

2. `test_phone_agent_base_salary_not_created_for_non_phone_vertical`
   - Verifies non-Phones businesses don't get base salary

3. `test_phone_agent_new_month_creates_new_salary_txn`
   - Verifies new month creates new transaction
   - Tests month boundary logic

4. `test_phone_agent_payslip_includes_base_even_without_sales`
   - Verifies payslip shows MWK 50,000 with zero sales

5. `test_commission_does_not_duplicate_salary`
   - Verifies multiple sales don't duplicate base salary
   - Tests: 2 sales = 2 commission txns + 1 salary txn

6. `test_agent_wallet_view_calls_ensure_salary`
   - Verifies wallet page automatically creates base salary

7. `test_base_salary_transaction_fields`
   - Verifies all transaction fields are correct

8. `test_business_isolation_for_base_salary`
   - Verifies proper business scoping (no cross-business leakage)

### 4. `cypress/e2e/phones_agent_invite_flow.cy.js`
Updated FIX 2 assertion (lines 369-383):
- Changed from expecting commission only (MK 15,000)
- Now expects base salary + commission (MK 65,000)
- Updated comment to explain: 50,000 base + 15,000 commission

## Key Design Decisions

### Why TxnType.BONUS instead of new type?
- Avoids database migration (requirement)
- Uses `meta.kind` for identification
- Bonus type is semantically appropriate (guaranteed income)

### Why month_start for effective_date?
- Consistent grouping by month
- Makes month-based queries simpler
- Aligns with payslip month boundaries

### Why idempotency check in helper?
- Prevents duplicates on wallet page refresh
- Prevents duplicates on multiple sales
- Safe to call repeatedly

## Data Flow

1. **Agent visits wallet**: `AgentWalletView` → calls `ensure_monthly_base_salary_for_agent()`
2. **First time this month**: Creates WalletTransaction with MWK 50,000
3. **Subsequent visits/sales**: Idempotency check returns None (no duplicate)
4. **Dynamic payslip**: Queries transactions, includes base salary in gross
5. **Formal payslip**: Uses `get_base_salary_for_month()` to retrieve amount

## Business Logic

- **Only Phones**: Checks `business.business_kind == "phones"`
- **Only Agents**: Checks active AGENT membership
- **Monthly Reset**: New transaction for each month (identified by "YYYY-MM")
- **Business Scoped**: Each business+agent+month = 1 transaction
- **No Migrations**: Uses existing WalletTransaction model + meta JSON

## Payslip Formula

```
monthly_gross = base_salary + commissions + other_bonuses
monthly_net = monthly_gross - deductions

For Phones agents:
base_salary = 50,000 (from WalletTransaction)
commissions = sum of commission txns for month
```

## Ranking Impact

- Base salary does NOT affect ranking
- Ranking is commission-only (uses agent_earnings service)
- Dashboard rankings remain unchanged

## Testing Coverage

- Unit tests for all salary logic
- Integration tests for sales + salary
- Business isolation tests
- Idempotency tests
- Cypress E2E tests updated

## Acceptance Criteria ✅

- [x] Phones agents get MWK 50,000 base salary per month
- [x] Exactly 1 base salary transaction per agent per month
- [x] Idempotent (no duplicates on page refresh/multiple sales)
- [x] Payslip shows 50,000 even before first sale
- [x] Payslip updates immediately after sales (base + commission)
- [x] No database migrations required
- [x] Data isolation maintained (business scoped)
- [x] Existing tests still pass
- [x] No regressions (no new 500s)
- [x] Ranking logic unaffected

## Migration Path

No database migrations needed! The feature uses:
- Existing `WalletTransaction` model
- Existing `TxnType.BONUS` enum value
- JSON `meta` field for identification

## Rollback

To disable:
1. Comment out the `ensure_monthly_base_salary_for_agent()` call in `AgentWalletView`
2. Existing transactions remain in database (can be filtered out via `meta.kind`)

## Future Enhancements

- Configurable base salary amount (via settings or business config)
- Support for other verticals (laptops, electronics)
- Tiered base salary based on performance
- Pro-rated base salary for partial months

