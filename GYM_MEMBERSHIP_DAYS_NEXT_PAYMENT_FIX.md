# GYM Membership Days Left & Next Payment Fix

## Summary

Fixed two critical bugs in the GYM membership logic:

1. **"Days Left" showing values like "31 / 30 days"** - The numerator now never exceeds the total membership days
2. **"Next Payment" showing "-" (blank)** - Now always shows a concrete date for active memberships

## Problems Fixed

### Problem 1: Days Left Could Exceed Total Days ("31 / 30 days")

**Root Cause:**
- The `GymMember.days_left_current` property was calculating days remaining without capping at the membership duration
- This caused displays like "31 / 30 days" when members were just past their membership period

**Solution:**
- Created `compute_membership_days()` helper function in `inventory/utils_gym.py`
- This function ensures `days_left` is always capped between 0 and `duration_days`
- Updated `GymMember.days_left_current` to use this centralized function

### Problem 2: Next Payment Date Was Blank ("-")

**Root Cause:**
- The check-in view was passing `membership_status["end_date"]` as the next payment date
- This is the LAST day of the current membership, not the date when the next payment is due
- For members without a membership, this was `None`, showing as "-"

**Solution:**
- Created `compute_next_payment_date()` helper function in `inventory/utils_gym.py`
- Business rule: Next payment is due exactly `duration_days` after the last payment date
- For a 30-day membership starting Jan 1 (ending Jan 30), next payment is due Jan 31
- Updated `GymMember.next_payment_date()` to use this helper function
- Updated the check-in view to pass the correct next payment date to the template

## Files Changed

### 1. `inventory/utils_gym.py`

Added two new helper functions:

#### `compute_membership_days(start_date, duration_days, today=None)`
```python
def compute_membership_days(start_date: date, duration_days: int, today: Optional[date] = None) -> tuple[int, int]:
    """
    Compute days left and total days for a membership period.
    
    This ensures that days_left NEVER exceeds duration_days, fixing the "31 / 30 days" bug.
    
    Returns:
        Tuple of (days_left, total_days)
        - days_left: Number of days remaining (0 to duration_days, inclusive)
        - total_days: The duration_days parameter
    """
```

**Logic:**
- Calculates how many days have elapsed since the start date
- Clamps elapsed days to [0, duration_days]
- Returns remaining days = duration_days - elapsed_days
- **Ensures days_left never exceeds duration_days**

#### `compute_next_payment_date(last_payment_date, duration_days)`
```python
def compute_next_payment_date(last_payment_date: Optional[date], duration_days: int) -> Optional[date]:
    """
    Calculate the next payment due date.
    
    Business rule: Next payment is due exactly duration_days after the last payment.
    
    Returns:
        The next payment date, or None if no payment has been made
    """
```

**Logic:**
- Returns `last_payment_date + timedelta(days=duration_days)`
- For a 30-day membership starting Jan 1, returns Jan 31
- Returns `None` only if the member has never paid

### 2. `inventory/models_verticals.py`

#### Updated `GymMember.days_left_current` property

**Before:**
```python
days = (payment.end_date - today).days + 1
return max(days, 0)
```

**After:**
```python
from inventory.utils_gym import compute_membership_days, GYM_MEMBERSHIP_DAYS

days_left, _ = compute_membership_days(payment.start_date, GYM_MEMBERSHIP_DAYS, today)
return days_left
```

**Result:** Days left is now properly capped at 30 and never shows "31 / 30 days"

#### Updated `GymMember.next_payment_date()` method

**Before:**
```python
def next_payment_date(self):
    """Return the next payment date (membership_end + 1 day)"""
    if not self.membership_end:
        return None
    return self.membership_end
```

**After:**
```python
def next_payment_date(self):
    """
    Return the next payment due date.
    
    Business rule: Next payment is due exactly 30 days after the last payment.
    For a membership starting Jan 1, ending Jan 30, next payment is due Jan 31.
    """
    from inventory.utils_gym import compute_next_payment_date, GYM_MEMBERSHIP_DAYS
    
    if not self.last_payment_date:
        return None
    
    return compute_next_payment_date(self.last_payment_date, GYM_MEMBERSHIP_DAYS)
```

**Result:** Next payment date is now calculated correctly and never blank for paid members

### 3. `inventory/views_gym.py`

#### Updated `checkin_page()` view

**Before:**
```python
"next_payment": membership_status["end_date"],
```

**After:**
```python
# Get next payment date (the date when payment is due, not the last day of membership)
next_payment_date = member.next_payment_date()

"next_payment": next_payment_date,
```

**Result:** View now passes the correct next payment date to the template

### 4. `templates/inventory/gym/checkin_page.html`

#### Fixed table columns to use view context data

**Before:**
- Used `data.member.days_left_current` (not capped)
- Hardcoded "30" in the template

**After:**
- Uses `data.days_left` and `data.total_days` from view context
- Displays: `{{ data.days_left }} / {{ data.total_days }} days`
- Also fixed membership status to use `data.membership_status.status_code`

**Result:** Template now displays correct, capped values

## Tests Added

Created comprehensive test suite: `inventory/tests/test_gym_membership_days_and_next_payment.py`

**24 tests covering:**

1. **Helper function tests:**
   - `compute_membership_days()` with various dates
   - Ensures days left never exceeds duration_days
   - Tests edge cases (before start, at start, during, at end, after end)
   
2. **Next payment date tests:**
   - Verifies next payment is exactly 30 days after last payment
   - Handles None for members who haven't paid
   - Works with different duration values

3. **Model property tests:**
   - `GymMember.days_left_current` caps at duration_days
   - `GymMember.next_payment_date()` returns correct date
   
4. **Integration tests:**
   - Complete 30-day lifecycle
   - Specifically tests prevention of "31 / 30 days" bug
   - Verifies next payment is never blank for paid members

**All 24 tests pass ✅**

## Verification

### Test Results
```bash
python -m pytest inventory/tests/test_gym_membership_days_and_next_payment.py -v
# Result: 24 passed, 11 warnings in 16.63s
```

### Expected Behavior on `/gym/checkin/` Page

#### For a freshly paid 30-day membership:
- **Days Left:** Shows `30 / 30 days` (not 31)
- **Next Payment:** Shows a date exactly 30 days from payment date (e.g., `31 Jan 2025`)

#### For a membership after 5 days:
- **Days Left:** Shows `25 / 30 days`
- **Next Payment:** Unchanged (still the date 30 days from original payment)

#### For an expired membership (30+ days):
- **Days Left:** Shows `0 / 30 days` (not negative, not > 30)
- **Next Payment:** Still shows the date (when payment was due)

## Business Logic Summary

### Membership Duration
- Standard membership: **30 days** (configurable via `GYM_MEMBERSHIP_DAYS`)
- If payment on Jan 1:
  - Membership period: Jan 1 - Jan 30 (inclusive, 30 days)
  - Next payment due: Jan 31

### Days Left Calculation
- **Formula:** `days_left = duration_days - days_elapsed`
- **Constraints:** 
  - Minimum: 0 (never negative)
  - Maximum: duration_days (never exceeds 30 for standard plan)
- **Display:** Always shows as `X / Y days` where X ≤ Y

### Next Payment Date
- **Formula:** `next_payment = last_payment_date + duration_days`
- **Example:** Payment on Jan 1 → Next payment due Jan 31
- **Display:** Always shows a concrete date for members who have paid
- **Special case:** Shows "-" only if member has never paid

## Impact on Other Verticals

✅ **No impact** - All changes are isolated to the GYM vertical:
- New helper functions are in `inventory/utils_gym.py` (gym-specific)
- Model changes only affect `GymMember` model
- View changes only affect `inventory/views_gym.py`
- Template changes only affect `templates/inventory/gym/checkin_page.html`

## Backward Compatibility

✅ **Fully backward compatible:**
- No database migrations required
- No breaking changes to existing APIs
- Deprecated methods still work (with deprecation notes)
- All existing gym tests still pass

## Key Improvements

1. **Centralized Logic:** All membership days calculations now use helper functions
2. **Consistent Behavior:** Days left calculation is the same everywhere
3. **Better UX:** Users see accurate, never-confusing values
4. **Well-Tested:** 24 comprehensive tests ensure correctness
5. **Clear Documentation:** Code comments explain the business rules

## Files Modified

1. `inventory/utils_gym.py` - Added helper functions
2. `inventory/models_verticals.py` - Updated `GymMember` properties
3. `inventory/views_gym.py` - Fixed check-in view
4. `templates/inventory/gym/checkin_page.html` - Fixed template display
5. `inventory/tests/test_gym_membership_days_and_next_payment.py` - New test suite (24 tests)

## No Regressions

✅ All existing inventory tests pass:
```bash
python -m pytest inventory/tests/ -v
# All tests pass including the 24 new gym membership tests
```

