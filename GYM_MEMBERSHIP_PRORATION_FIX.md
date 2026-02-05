# Gym Membership Proration Fix

## Problem Statement

The gym membership system was not properly prorating membership days based on payment amount. It always granted exactly 30 days regardless of the amount paid, using a hardcoded global monthly fee instead of each member's actual monthly fee.

### Expected Behavior

Every monthly payment should buy 30 days at the **current monthly membership fee**:
- Daily rate = monthly_fee / 30
- Days granted = amount_paid / daily_rate

**Example:** If monthly_fee = 50,000 MWK and amount_paid = 55,000 MWK:
- Daily rate = 50,000 / 30 = 1,666.67 MWK/day
- Days granted = 55,000 / 1,666.67 = 33 days

### Actual Behavior (Before Fix)

The system used a global constant `GYM_MONTHLY_FEE = 55,000` for all calculations, ignoring each member's actual `membership_fee` field. This caused incorrect proration when:
1. A member's monthly fee differed from the global constant
2. A member paid more or less than their monthly fee

## Root Cause

The `calculate_prorated_days()` function in `inventory/utils_gym.py` only accepted an `amount` parameter and always used the global `GYM_MONTHLY_FEE` constant for calculating the daily rate, instead of using each member's actual monthly fee.

## Solution

### Changes Made

#### 1. Updated `calculate_prorated_days()` (inventory/utils_gym.py)

**Before:**
```python
def calculate_prorated_days(amount: Decimal) -> int:
    # Always used GYM_MONTHLY_FEE (55,000)
    days_decimal = (amount / GYM_DAILY_RATE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    days = int(days_decimal)
    return max(1, days)
```

**After:**
```python
def calculate_prorated_days(amount: Decimal, monthly_fee: Optional[Decimal] = None) -> int:
    # Use provided monthly_fee or fall back to global constant
    if monthly_fee is None or monthly_fee <= 0:
        monthly_fee = GYM_MONTHLY_FEE
    
    # Calculate daily rate: monthly_fee / 30 days
    daily_rate = monthly_fee / Decimal("30")
    
    # Calculate days with ROUND_HALF_UP
    days_decimal = (amount / daily_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    days = int(days_decimal)
    
    # Ensure minimum 30 days if paying full monthly fee or more
    if amount >= monthly_fee:
        days = max(30, days)
    
    # Ensure minimum 1 day for any payment
    return max(1, days)
```

#### 2. Updated `calculate_membership_period()` (inventory/utils_gym.py)

Now passes the member's actual `membership_fee` to `calculate_prorated_days()`:

```python
def calculate_membership_period(
    amount: Decimal, member: "GymMember", start_date: Optional[date] = None, today: Optional[date] = None
) -> tuple[date, date, int]:
    # Calculate days to grant based on amount and member's monthly fee
    days_granted = calculate_prorated_days(amount, monthly_fee=member.membership_fee)
    # ... rest of logic
```

#### 3. Fixed `GymMember.set_paid()` (inventory/models_verticals.py)

Updated the order of operations to set the member's fee BEFORE calculating the period:

```python
def set_paid(self, payment_date=None, membership_fee=None, trainer_fee=None, paid_by=None, amount=None):
    # Update fees FIRST if provided (needed for proration calculation)
    if membership_fee is not None:
        self.membership_fee = membership_fee
    if trainer_fee is not None:
        self.trainer_fee = trainer_fee
    
    # Now calculate with the updated fee
    new_start, new_end, days_granted = calculate_membership_period(
        amount=total_amount, member=self, start_date=payment_date, today=payment_date
    )
```

#### 4. Updated `member_set_paid()` view (inventory/views_gym.py)

Fixed the days_granted calculation for the success message to use only the membership fee (not including trainer fee):

```python
# Calculate days granted for message (based on membership fee only, not trainer fee)
days_granted = calculate_prorated_days(member.membership_fee, monthly_fee=member.membership_fee)
```

## Business Rules Implemented

1. **Proportional Days:** Days granted = amount_paid / (monthly_fee / 30)
2. **Fair Rounding:** Uses `ROUND_HALF_UP` for fair rounding (not `ROUND_FLOOR`)
3. **Minimum Grant:** 
   - Any positive payment grants at least 1 day
   - Paying full monthly fee or more grants at least 30 days
4. **Decimal Math:** Uses Python's `Decimal` type to avoid floating-point rounding errors
5. **Standard Case Preserved:** Paying exactly the monthly fee still yields exactly 30 days

## Testing

### New Tests Added

Created `tests/test_gym_membership_proration_fix.py` with 20 comprehensive tests:

**Test Coverage:**
- Exact monthly fee grants 30 days
- Overpayment grants proportional days (55,000 on 50,000 fee → 33 days)
- Double payment grants 60 days
- Half payment grants 15 days
- Minimum payment grants at least 1 day
- Full payment grants at least 30 days
- Rounding is fair (ROUND_HALF_UP)
- Different monthly fees work correctly
- Auto-extension with overpayment
- Regression scenarios

### Test Results

```
✅ 20 new tests: ALL PASSED
✅ 200 existing gym tests: ALL PASSED (no regressions)
✅ Total: 220 gym-related tests passing
```

## Verification

### Manual Test Scenario

**Given:**
- Member with monthly_fee = 50,000 MWK
- Payment amount = 55,000 MWK

**Expected:**
- Daily rate = 50,000 / 30 = 1,666.67 MWK/day
- Days granted = 55,000 / 1,666.67 = 33 days
- Membership end date = start_date + 32 days (33 days inclusive)

**Actual (After Fix):**
✅ Grants exactly 33 days
✅ Membership end date is correct
✅ Standard case (50,000 payment) still grants 30 days

## Files Changed

1. `inventory/utils_gym.py` - Core proration logic
2. `inventory/models_verticals.py` - GymMember.set_paid() method
3. `inventory/views_gym.py` - member_set_paid() view
4. `tests/test_gym_membership_proration_fix.py` - New comprehensive test suite

## Breaking Changes

**None.** The fix is backward compatible:
- Members without a `membership_fee` fall back to the global constant
- Standard case (paying exactly monthly fee) still yields 30 days
- No schema changes
- No API changes

## Deployment Notes

- No migrations required
- No data migration needed
- Existing memberships are unaffected
- New payments will use the correct proration logic immediately

## Commit Message

```
fix: prorate gym membership days by payment amount

Every monthly payment now buys 30 days at the current monthly membership fee.
Daily rate = monthly_fee / 30.
Days granted = amount_paid / daily_rate.

Example: monthly_fee=50,000; amount_paid=55,000 => days=33.

Changes:
- Updated calculate_prorated_days() to accept monthly_fee parameter
- Updated calculate_membership_period() to pass member's monthly_fee
- Fixed GymMember.set_paid() to update fees before calculation
- Fixed member_set_paid() view to calculate days from membership fee only

Business rules:
- Uses ROUND_HALF_UP for fair rounding
- Minimum 1 day for any payment
- Minimum 30 days if paying full monthly fee or more
- Uses Decimal math (no float rounding bugs)

Testing:
- Added 20 new comprehensive tests
- All 200 existing gym tests still pass
- No regressions

Fixes #gym-proration
```

