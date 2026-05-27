# Gym Trainers Feature Implementation

**Date:** 2025-12-13  
**Status:** ✅ Complete

## Overview

Implemented a comprehensive trainers feature for the GYM vertical, including:
- Optional trainer assignment per payment with separate trainer fee
- Trainer wallet crediting system
- Trainers ranking dashboard
- Fixed Cypress test failures with stable data-cy attributes
- Ensured membership proration only uses membership_amount (trainer fee does NOT buy extra days)

## Key Requirements Met

✅ **A) Fixed Cypress Failure**
- Added stable data-cy attributes to payment form fields
- Updated Cypress test to use data-cy selectors first with fallback

✅ **B) Trainers Feature**
- Created/updated GymTrainer model with optional linked user FK
- Updated GymPayment model with membership_amount, trainer_fee, and trainer FK
- Implemented 3 default trainers per business (Steve, Lester, Philip)
- Proration calculated from membership_amount ONLY
- Trainer wallet crediting via WalletTransaction system
- Auto-extension logic preserved

✅ **C) Dashboard: Trainers Ranking**
- Added Trainers Ranking section showing fees earned and session count
- Sorted by total trainer fees (descending)
- Shows rank badges (🥇 1st, 🥈 2nd, 🥉 3rd)

✅ **D) Gym Auth/Role UX**
- Trainers use existing role/permission system
- No breaking changes to other verticals

✅ **E) Cypress Test Updated**
- Uses data-cy selectors throughout
- Tests trainer selection and fee entry
- Asserts correct days calculation (30/30 for 55,000 membership)
- Verifies total payment includes trainer fee
- Checks trainers ranking on dashboard

## Files Changed

### Backend (Python)

1. **inventory/models_verticals.py**
   - Updated `GymTrainer` model:
     - Added `user` FK for wallet access
     - Added `total_fees_earned()` method
     - Added `payment_count()` method
   - Updated `GymPayment` model:
     - Added `membership_amount` field (used for days calculation)
     - Added `trainer_fee` field (does not affect days)
     - Added `trainer` FK
     - Updated `amount` to be total (membership + trainer)
     - Added `total_amount` property

2. **inventory/views_gym.py**
   - Updated `GymPaymentForm`:
     - Split amount into `membership_amount` and `trainer_fee`
     - Added `trainer` selection field
     - Added validation: trainer required if fee > 0, and vice versa
     - Added data-cy attributes to all fields
   - Updated `add_payment` view:
     - Handles separate membership_amount and trainer_fee
     - Calculates days from membership_amount ONLY
     - Credits trainer's wallet via WalletTransaction
     - Handles case where trainer has no linked user
   - Updated `gym_dashboard` view:
     - Added trainer fees aggregation
     - Added payment count per trainer
     - Added `trainer_ranking` (sorted by fees earned)

3. **inventory/utils_gym.py**
   - No changes needed (already calculates days from amount parameter)
   - Documentation confirms: proration only uses membership_amount

4. **inventory/migrations/0054_add_gym_trainer_fees.py**
   - Added `membership_amount` field to GymPayment (default 55,000)
   - Added `trainer_fee` field to GymPayment (default 0)
   - Added `trainer` FK to GymPayment
   - Added `user` FK to GymTrainer
   - Added data migration to copy existing `amount` to `membership_amount`
   - Added index on (trainer, paid_at)

5. **inventory/management/commands/seed_gym_trainers.py**
   - New management command to seed default trainers
   - Creates Steve, Lester, Philip for all gym businesses
   - Idempotent (won't create duplicates)
   - Supports `--business-id` flag for specific business

### Frontend (Templates)

6. **templates/inventory/gym/payment_form.html**
   - Split amount field into membership_amount and trainer_fee
   - Added trainer dropdown with data-cy="gym-payment-trainer"
   - Added membership_amount input with data-cy="gym-payment-membership-amount"
   - Added trainer_fee input with data-cy="gym-payment-trainer-fee"
   - Added submit button with data-cy="gym-payment-submit"
   - Updated help text to clarify trainer fee does not add days
   - Added information sidebar explaining trainer fees

7. **templates/inventory/gym/dashboard.html**
   - Replaced "Trainer Performance" with "Trainers Ranking"
   - Shows rank badges (🥇 1st, 🥈 2nd, 🥉 3rd)
   - Displays:
     - Trainer name
     - Fees earned (in period)
     - Sessions/payments count
     - Active members
   - Sorted by fees earned (descending)

### Testing

8. **cypress/e2e/gym_membership_numbers.cy.js**
   - Updated to use data-cy selectors first with fallbacks
   - Tests trainer selection:
     - Selects first available trainer from dropdown
     - Enters trainer_fee = 15000
   - Tests membership_amount = 55000 (not total)
   - Asserts 30/30 days (membership_amount only, not trainer_fee)
   - Verifies total payment = 70,000 (55k + 15k)
   - Checks trainers ranking on dashboard shows at least 15,000

## Key Implementation Details

### 1. Proration Logic

```python
# In add_payment view:
membership_amount = data["membership_amount"]  # e.g., 55,000
trainer_fee = data.get("trainer_fee") or Decimal("0.00")  # e.g., 15,000

# IMPORTANT: Calculate days from membership_amount ONLY
new_start, new_end, days_granted = calculate_membership_period(
    amount=membership_amount,  # Only this, not trainer_fee
    member=member,
    start_date=start_date,
    today=timezone.now().date()
)

# Total paid = membership + trainer
total_amount = membership_amount + trainer_fee  # e.g., 70,000
```

### 2. Trainer Wallet Crediting

```python
# Credit trainer's wallet if trainer_fee > 0 and trainer has linked user
if trainer and trainer_fee > 0:
    if trainer.user:
        WalletTransaction.objects.create(
            ledger=Ledger.AGENT,
            agent=trainer.user,
            type=TxnType.BONUS,
            amount=trainer_fee,
            note=f"Trainer fee from {member.name} (gym)",
            reference=f"gym_payment_{payment.id}",
            effective_date=timezone.now().date(),
            created_by=request.user,
            business=business,
            meta={
                "kind": "gym_trainer_fee",
                "member_id": member.id,
                "payment_id": payment.id,
                "member_name": member.name,
            }
        )
```

### 3. Trainers Ranking

```python
# In gym_dashboard view:
for trainer in trainers:
    # Total trainer fees earned in date range
    trainer_fees = GymPayment.objects.filter(
        trainer=trainer,
        is_active=True,
        paid_at__gte=start_dt,
        paid_at__lte=end_dt
    ).aggregate(total=Sum("trainer_fee"))["total"] or Decimal("0.00")
    
    # Number of payments with this trainer
    payment_count = GymPayment.objects.filter(
        trainer=trainer,
        is_active=True,
        paid_at__gte=start_dt,
        paid_at__lte=end_dt
    ).count()

# Sort by trainer fees (descending) for rankings
trainer_ranking = sorted(trainer_stats, key=lambda x: x["trainer_fees"], reverse=True)
```

## Examples

### Example 1: Member Pays 55,000 Membership + 15,000 Trainer Fee

**Input:**
- Member: John Doe
- Membership amount: 55,000 MWK
- Trainer: Steve
- Trainer fee: 15,000 MWK
- Start date: Jan 1

**Calculation:**
- Days granted: 55,000 / 1,833.33 = 30 days (from membership_amount only)
- Start: Jan 1
- End: Jan 30 (30 days inclusive)
- Total paid: 70,000 MWK (55,000 + 15,000)

**Results:**
- Member gets 30 days of membership
- Status: "Active" (green badge)
- Display: "30 / 30 days"
- Steve's wallet is credited with 15,000 MWK
- Trainers Ranking shows Steve with +15,000 fees

### Example 2: Member Pays 100,000 Membership + No Trainer

**Input:**
- Member: Jane Smith
- Membership amount: 100,000 MWK
- Trainer: None
- Trainer fee: 0 MWK
- Start date: Jan 1

**Calculation:**
- Days granted: 100,000 / 1,833.33 = 55 days (rounded)
- Start: Jan 1
- End: Feb 24 (55 days inclusive)
- Total paid: 100,000 MWK

**Results:**
- Member gets 55 days of membership
- Status: "Active" (green badge)
- Display: "55 / 55 days"
- No trainer wallet credit
- Trainers Ranking unchanged

## Testing

### Manual Testing Steps

1. **Run migrations:**
   ```bash
   python manage.py migrate inventory
   ```

2. **Seed default trainers:**
   ```bash
   python manage.py seed_gym_trainers
   ```

3. **Test payment with trainer:**
   - Go to /gym/members/
   - Add a new member
   - Click "Add Payment"
   - Enter membership amount: 55,000
   - Select trainer: Steve
   - Enter trainer fee: 15,000
   - Submit
   - Verify: 30/30 days, status Active, total 70,000

4. **Check trainers ranking:**
   - Go to /gym/ dashboard
   - Scroll to "Trainers Ranking"
   - Verify Steve shows 15,000 fees earned, 1 session

5. **Check trainer wallet (if linked user):**
   - Login as trainer user (if configured)
   - Go to My Wallet
   - Verify 15,000 credit with note "Trainer fee from [member name]"

### Automated Testing

```bash
# Run Cypress test
npx cypress run --spec cypress/e2e/gym_membership_numbers.cy.js
```

Expected results:
- ✅ Member created
- ✅ Payment recorded with trainer
- ✅ Status: Active
- ✅ Days: 30/30
- ✅ Total paid: 70,000
- ✅ Trainers Ranking shows 15,000

## Backward Compatibility

✅ **Existing payments preserved:**
- Migration copies old `amount` to `membership_amount`
- Old payments have `trainer_fee = 0` and `trainer = NULL`
- Days calculation still works correctly

✅ **Existing flows work:**
- Add Member → Add Payment → Mark as Paid
- Payment without trainer (fee = 0)
- Auto-extension logic unchanged
- Status badge logic unchanged

✅ **No breaking changes:**
- Other verticals (Phones, Liquor, Clothing) unaffected
- Existing tests continue to pass
- Wallet system unchanged

## Default Trainers

Three default trainers are created for each gym business:
1. **Steve** - Active trainer
2. **Lester** - Active trainer
3. **Philip** - Active trainer

These can be:
- Edited in the UI (/gym/trainers/)
- Renamed or deactivated
- Linked to user accounts for wallet access
- Additional trainers can be added

## Data-cy Attributes

All payment form fields have stable data-cy attributes for Cypress:

| Field | data-cy Attribute |
|-------|------------------|
| Member select | `gym-payment-member` |
| Membership amount | `gym-payment-membership-amount` |
| Trainer select | `gym-payment-trainer` |
| Trainer fee | `gym-payment-trainer-fee` |
| Submit button | `gym-payment-submit` |

## Known Edge Cases

✅ **Handled:**
- Trainer with no linked user: Fee stored, no wallet credit
- Trainer fee without trainer selected: Validation error
- Trainer selected without fee: Validation error
- Existing payments: Migrated correctly
- Auto-extension: Works with new fields

## Future Enhancements (Optional)

1. **Configurable trainer fee:**
   - Add default_trainer_fee to GymSettings
   - Auto-populate trainer_fee when trainer selected

2. **Trainer commissions:**
   - Calculate % of membership_amount for trainer
   - Track commission vs flat fee

3. **Trainer analytics:**
   - Member retention per trainer
   - Average attendance per trainer
   - Revenue per trainer (membership + fees)

4. **Trainer schedules:**
   - Link trainers to time slots
   - Show available trainers at check-in

## Deployment Checklist

- [x] Migrations created and tested
- [x] Default trainers seeded
- [x] Payment form updated
- [x] Dashboard ranking added
- [x] Cypress test updated
- [x] No linter errors
- [x] Backward compatibility verified
- [x] Documentation complete

## Files Changed Summary

**Total files changed: 8**

### Backend (5 files)
1. inventory/models_verticals.py
2. inventory/views_gym.py
3. inventory/utils_gym.py (no changes, already correct)
4. inventory/migrations/0054_add_gym_trainer_fees.py
5. inventory/management/commands/seed_gym_trainers.py

### Frontend (2 files)
6. templates/inventory/gym/payment_form.html
7. templates/inventory/gym/dashboard.html

### Testing (1 file)
8. cypress/e2e/gym_membership_numbers.cy.js

---

**Implementation Complete** ✅

All requirements met, tests passing, no regressions.

