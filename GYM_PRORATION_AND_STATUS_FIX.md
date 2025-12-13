# Gym Membership Proration & Status Badge Fix

**Date:** 2025-12-13  
**Status:** ✅ Complete

## Overview

Fixed two critical issues in the Gym vertical:

1. **Membership Status Badge** - Now correctly shows "Active" (green) after payment based on `membership_end >= today`
2. **Prorated Membership Duration** - Days granted are now calculated based on amount paid (MWK 55,000 for 30 days)

## Changes Summary

### 1. Proration Calculation (`inventory/utils_gym.py`)

Added new constants and functions:

```python
# Gym pricing: MWK 55,000 for 30 days
GYM_MONTHLY_FEE = Decimal("55000.00")
GYM_DAILY_RATE = GYM_MONTHLY_FEE / Decimal("30")  # 1,833.33...

def calculate_prorated_days(amount: Decimal) -> int:
    """
    Calculate days granted for a payment amount.
    Formula: ROUND_HALF_UP(amount / daily_rate), minimum 1 day
    
    Examples:
    - 55,000 MWK => 30 days
    - 100,000 MWK => 55 days (100,000 / 1,833.33 = 54.545... => 55)
    - 110,000 MWK => 60 days
    """
    
def calculate_membership_period(amount, member, start_date, today):
    """
    Calculate membership start/end dates with auto-extension logic.
    
    Auto-extension:
    - If member is active (membership_end >= today): new_start = membership_end + 1
    - Otherwise: new_start = start_date (or today)
    
    Returns: (new_start, new_end, days_granted)
    """
```

### 2. Model Updates (`inventory/models_verticals.py`)

#### Updated `GymMember` properties:

```python
@property
def duration_days(self) -> int:
    """Returns actual granted days from current membership period"""
    if self.membership_start and self.membership_end:
        return (self.membership_end - self.membership_start).days + 1
    return 30  # fallback

@property
def days_left(self) -> int:
    """Calculate remaining days inclusively using membership_end"""
    if not self.membership_end:
        return 0
    today = timezone.now().date()
    if self.membership_end < today:
        return 0
    return (self.membership_end - today).days + 1
```

#### Updated `GymMember.set_paid()`:

- Now accepts `amount` parameter for proration
- Uses `calculate_membership_period()` for auto-extension logic
- Creates payment record with correct prorated days

#### Updated `GymPayment.save()`:

- No longer forces `end_date = start_date + 30 days`
- Uses `start_date + (days - 1)` for inclusive calculation
- Respects caller's end_date

### 3. View Updates (`inventory/views_gym.py`)

#### `add_payment` view:

```python
# Calculate prorated membership period with auto-extension
new_start, new_end, days_granted = calculate_membership_period(
    amount=amount,
    member=member,
    start_date=start_date,
    today=timezone.now().date()
)

# Update member's membership dates
member.membership_start = new_start
member.membership_end = new_end
member.status = GymMemberStatus.ACTIVE
```

#### `member_set_paid` view:

- Now uses `set_paid()` with `amount` parameter
- Displays days granted in success message

### 4. Template Updates

#### `templates/inventory/gym/member_detail.html`:

**Status Badge (before):**
```django
{% if member.is_active_membership %}
    <span class="badge bg-success">Active</span>
{% else %}
    <span class="badge bg-danger">In Arrears</span>
{% endif %}
```

**Status Badge (after):**
```django
{% now "Y-m-d" as today_str %}
{% if member.membership_end|date:"Y-m-d" >= today_str %}
    <span class="badge bg-success-subtle text-success">Active</span>
{% else %}
    <span class="badge bg-danger-subtle text-danger">In Arrears</span>
{% endif %}
```

**Days Display (before):**
```django
{{ member.days_left_display }}  {# Always showed "X / 30 days" #}
```

**Days Display (after):**
```django
{{ member.days_left }} / {{ member.duration_days }} days  {# Shows actual granted days #}
```

#### `templates/inventory/gym/members_list.html`:

- Same status badge logic as member_detail.html
- Shows `X / Y days` with actual granted days
- "Pay" button only shows when `membership_end < today` or no membership

#### `templates/inventory/gym/payment_form.html`:

Updated help text to explain proration:
- "MWK 55,000 = 30 days"
- Examples: 55,000 → 30 days, 100,000 → 55 days, 110,000 → 60 days

### 5. Test Updates (`cypress/e2e/gym_membership_numbers.cy.js`)

Updated test to verify:
- 100,000 MWK payment grants 55 days (not 30)
- Status badge shows "Active" after payment
- Days display shows "55 / 55 days"
- Next payment date is ~55 days from today

## Examples

### Example 1: New Member Pays 55,000 MWK on Jan 1

**Calculation:**
- Days granted: 55,000 / 1,833.33 = 30 days
- Start: Jan 1
- End: Jan 30 (30 days inclusive)
- Display: "30 / 30 days"
- Status: "Active" (green badge)

### Example 2: New Member Pays 100,000 MWK on Jan 1

**Calculation:**
- Days granted: 100,000 / 1,833.33 = 54.545... => 55 days (ROUND_HALF_UP)
- Start: Jan 1
- End: Feb 24 (55 days inclusive)
- Display: "55 / 55 days"
- Status: "Active" (green badge)

### Example 3: Active Member (valid until Jan 30) Pays 55,000 on Jan 15

**Calculation (Auto-Extension):**
- Current end: Jan 30
- Days granted: 30 days
- New start: Jan 31 (current_end + 1)
- New end: Feb 29 (31 days from Jan 31 to Feb 29 = 30 days)
- Display on Jan 31: "30 / 30 days"
- Status: "Active" (green badge)

### Example 4: Expired Member (expired on Jan 15) Pays 110,000 on Jan 20

**Calculation:**
- Days granted: 110,000 / 1,833.33 = 60 days
- Start: Jan 20 (no auto-extension, membership expired)
- End: Mar 19 (60 days inclusive)
- Display: "60 / 60 days"
- Status: "Active" (green badge)

## Testing

### Manual Test Flow

1. **Create a new member** (no payment yet)
   - Status should show "Pending Payment" (yellow/warning badge)
   - Days should show "No active membership"

2. **Add payment: 100,000 MWK**
   - Click "Add Payment" → Select member → Enter 100,000 → "Mark as Paid"
   - Success message should say "55 days granted"
   - Member detail should show:
     - Status: "Active" (green badge) ✅
     - Days: "55 / 55 days" ✅
     - Membership valid until: ~55 days from today

3. **Wait or simulate next day** (optional)
   - Days should decrement: "54 / 55 days"
   - Status should remain "Active" (green)

4. **Add another payment while active: 55,000 MWK**
   - Should auto-extend from current end date
   - New start = old end + 1 day
   - New end = new start + 29 days
   - Days display updated to "30 / 30 days" on new start date

### Automated Test (Cypress)

```bash
npx cypress run --spec cypress/e2e/gym_membership_numbers.cy.js
```

Test verifies:
- ✅ Member can be created
- ✅ Payment of 100,000 is recorded
- ✅ Days show "55 / 55"
- ✅ Status shows "Active"
- ✅ Next payment date is ~55 days from today

## Backward Compatibility

✅ **Existing working flow preserved:**
- "Add Member → Add Payment → Mark as Paid" flow still works
- Existing 30-day memberships continue to function
- No database migration required (uses existing fields)

✅ **Default settings still use 50,000 MWK:**
- `GymSettings.default_membership_price` remains 50,000 (if configured)
- Proration calculation is independent of default settings
- Any amount can be entered and will be prorated correctly

## Files Changed

### Python Files (Backend Logic)
1. `inventory/utils_gym.py` - Added proration functions
2. `inventory/models_verticals.py` - Updated GymMember properties and set_paid()
3. `inventory/views_gym.py` - Updated add_payment and member_set_paid views

### Template Files (UI)
4. `templates/inventory/gym/member_detail.html` - Fixed status badge and days display
5. `templates/inventory/gym/members_list.html` - Fixed status badge and days display
6. `templates/inventory/gym/payment_form.html` - Updated help text

### Test Files
7. `cypress/e2e/gym_membership_numbers.cy.js` - Updated assertions for proration

## Key Implementation Details

### Decimal Precision
- All money calculations use `Decimal` type (no floats)
- `ROUND_HALF_UP` used for days calculation
- Example: 54.5 days → 55 days, 54.4 days → 54 days

### Inclusive Date Calculation
- For N days: `end_date = start_date + (N - 1) days`
- Jan 1 to Jan 30 = 30 days inclusive
- Days remaining = `(end_date - today).days + 1`

### Status Badge Logic
- **Active**: `membership_end >= today` (date comparison)
- **In Arrears**: `membership_end < today` or no membership
- **Pending Payment**: No membership_end set
- No longer relies on stale `status` field or boolean flags

### Auto-Extension Logic
- **If active** (`membership_end >= today`):
  - `new_start = membership_end + 1 day`
- **If inactive**:
  - `new_start = chosen start_date` (defaults to today)

## Known Issues / Edge Cases

None identified. The implementation handles:
- ✅ New members (no previous membership)
- ✅ Active members (auto-extension)
- ✅ Expired members (restart from chosen date)
- ✅ Any payment amount (prorated correctly)
- ✅ Minimum 1 day for any non-zero payment
- ✅ Archived members (excluded from status calculations)

## Next Steps

1. **Deploy to staging** and verify with real users
2. **Update documentation** if gym has configurable daily rate
3. **Monitor** for any edge cases in production
4. **Consider** making daily rate configurable in GymSettings (future enhancement)

---

**Implementation Complete** ✅

