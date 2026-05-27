# Testing Checklist - Gym Vertical Enhancements

Use this checklist to verify all three implemented tasks work correctly.

---

## Pre-Testing Setup

### 1. Install Dependencies
```bash
pip install reportlab 'qrcode[pil]'
```

Verify installation:
```bash
python -c "import reportlab; import qrcode; print('✅ Dependencies installed')"
```

### 2. Run Migrations (if needed)
```bash
python manage.py migrate
```

### 3. Create Test Data

**Option A: Use Django Admin**
1. Go to `/admin/`
2. Create a Gym business (if not exists)
3. Add 5-10 test gym members
4. Add 2-3 test trainers

**Option B: Use Django Shell**
```python
from inventory.models import Business, BusinessKind
from inventory.models_verticals import GymMember, GymTrainer, GymSettings
from decimal import Decimal

# Create/get business
business = Business.objects.filter(kind=BusinessKind.GYM).first()

# Create gym settings
settings, _ = GymSettings.objects.get_or_create(
    business=business,
    defaults={
        'default_membership_price': Decimal('50000.00'),
        'default_trainer_fee': Decimal('30000.00'),
    }
)

# Create trainers
trainer1 = GymTrainer.objects.create(
    business=business,
    name="John Trainer",
    phone="0999111111",
)
trainer2 = GymTrainer.objects.create(
    business=business,
    name="Jane Coach",
    phone="0999222222",
)

# Create members
for i in range(10):
    GymMember.objects.create(
        business=business,
        name=f"Test Member {i+1}",
        phone=f"0999{i:06d}",
        email=f"member{i+1}@test.com",
        trainer=trainer1 if i % 2 == 0 else trainer2,
    )

print("✅ Test data created")
```

---

## TASK 1: BULK QR DOWNLOAD

### Test 1.1: Access Bulk Download UI
- [ ] Log in as Manager user
- [ ] Navigate to **Gym → Members**
- [ ] Verify "Bulk QR Download" button appears in header
- [ ] Click dropdown, verify options:
  - [ ] "All active"
  - [ ] "All archived"  
  - [ ] "Selected members"

### Test 1.2: Download All Active Members
- [ ] Click "Bulk QR Download" → "All active"
- [ ] PDF should download automatically
- [ ] Filename format: `gym_qr_stickers_<business>_<date>.pdf`
- [ ] Open PDF, verify:
  - [ ] Contains QR codes for all active members
  - [ ] Grid layout (3 columns × 8 rows)
  - [ ] Each sticker has: name, code, QR code, gym name
  - [ ] Light gray borders visible (cutting guides)

### Test 1.3: Download Selected Members
- [ ] Go back to Members list
- [ ] Check boxes next to 3 members
- [ ] Verify "Select All" checkbox state updates
- [ ] Click "Bulk QR Download" → "Selected members"
- [ ] PDF downloads with ONLY 3 selected members
- [ ] Verify correct members in PDF

### Test 1.4: QR Code Scanning
- [ ] Print one page from generated PDF (or view on screen)
- [ ] Scan QR code with phone camera
- [ ] Should open: `https://your-domain.com/gym/qr/<uuid>/`
- [ ] Public status page shows:
  - [ ] Member name
  - [ ] Member number
  - [ ] Status (Active/Expired)
  - [ ] Next payment date
  - [ ] Link to full profile

### Test 1.5: Permission Test (Staff User)
- [ ] Log out, log in as non-manager (Staff)
- [ ] Navigate to Gym → Members
- [ ] Bulk download button should either:
  - [ ] Not appear, OR
  - [ ] Appear but return 403 Forbidden when clicked

### Test 1.6: Empty Selection Error
- [ ] As Manager, go to Members list
- [ ] Uncheck all checkboxes
- [ ] Click "Bulk QR Download" → "Selected members"
- [ ] Should show alert: "Please select at least one member"

### Test 1.7: Large Dataset (Optional)
- [ ] Create 50+ test members (use Django shell)
- [ ] Download all members
- [ ] Verify:
  - [ ] No timeout error
  - [ ] PDF has multiple pages
  - [ ] All members present (count stickers)

---

## TASK 2: TRAINERS (VERIFY EXISTING FEATURE)

### Test 2.1: Access Trainers Page
- [ ] Log in as Manager
- [ ] Navigate to **Gym → Trainers**
- [ ] Trainers list page loads
- [ ] Shows existing trainers with:
  - [ ] Name
  - [ ] Phone
  - [ ] Email
  - [ ] Active member count
  - [ ] Actions (Edit, Deactivate)

### Test 2.2: Create Trainer (No User Account)
- [ ] Click "Add Trainer"
- [ ] Fill form:
  - [ ] Name: "Test Trainer"
  - [ ] Phone: "0999333333"
  - [ ] Email: (leave blank)
  - [ ] Notes: "Test notes"
- [ ] Save
- [ ] Verify redirected to trainers list
- [ ] New trainer appears in list
- [ ] **No user account created** (verify in admin if needed)

### Test 2.3: Trainer in Member Dropdown
- [ ] Go to **Gym → Members → Add Member**
- [ ] Look for "Assign Trainer" dropdown
- [ ] Verify "Test Trainer" appears in dropdown
- [ ] Select trainer
- [ ] Save member
- [ ] Go to member detail page
- [ ] Verify trainer assigned correctly

### Test 2.4: Edit Trainer
- [ ] Go to Trainers list
- [ ] Click "Edit" on a trainer
- [ ] Change phone number
- [ ] Save
- [ ] Verify changes reflected in list

### Test 2.5: Deactivate Trainer
- [ ] Click "Deactivate" on a trainer
- [ ] Trainer should disappear from active list (or marked inactive)
- [ ] Go to Add Member form
- [ ] Deactivated trainer should NOT appear in dropdown

### Test 2.6: Trainer Uniqueness
- [ ] Try to create trainer with duplicate name in same business
- [ ] Should show error (unique constraint)

---

## TASK 3: MEMBERSHIP FEE PREFILL

### Test 3.1: View/Edit Default Fees
- [ ] Navigate to **Gym → Settings**
- [ ] Find "Default Membership Fee (30 days)" field
- [ ] Current value should show (e.g., 50000.00)
- [ ] Find "Default Trainer Fee (30 days)" field
- [ ] Note current values

### Test 3.2: Create New Member (Default Fee)
- [ ] Go to **Gym → Members → Add Member**
- [ ] Verify "Membership Fee" field is **prefilled** with default (e.g., 50000.00)
- [ ] Verify "Trainer Fee" field is **prefilled** with default (e.g., 30000.00)
- [ ] Fill name and phone
- [ ] **Do not change fees** (leave prefilled values)
- [ ] Save member
- [ ] Go to member detail page
- [ ] Verify membership_fee = 50000.00 (the default)

### Test 3.3: Create New Member (Custom Fee)
- [ ] Add another member
- [ ] Form prefills 50000.00
- [ ] **Change to 75000.00** (custom amount)
- [ ] Save
- [ ] Verify member detail shows 75000.00 (custom, not default)

### Test 3.4: Edit Existing Member (Shows Existing Fee)
- [ ] Find member created in Test 3.3 (fee = 75000.00)
- [ ] Click "Edit"
- [ ] **CRITICAL**: Verify fee field shows **75000.00** (member's fee)
- [ ] **NOT 50000.00** (default from settings)
- [ ] Change name only (don't touch fee)
- [ ] Save
- [ ] Verify fee still 75000.00 (unchanged)

### Test 3.5: Change Default Fee (Doesn't Affect Existing)
- [ ] Go to **Gym → Settings**
- [ ] Change "Default Membership Fee" to **60000.00**
- [ ] Save settings
- [ ] Go to member from Test 3.3 (original fee 75000.00)
- [ ] Click "Edit"
- [ ] Verify fee field still shows **75000.00** (NOT new default 60000.00)
- [ ] Cancel edit
- [ ] **Now create NEW member**
- [ ] Verify form prefills **60000.00** (new default)
- [ ] Save new member
- [ ] Verify it has 60000.00
- [ ] Old member still has 75000.00 ✅

### Test 3.6: Edit Form Validation Error (Fee Preserved)
- [ ] Edit any member
- [ ] Clear the name field (make it invalid)
- [ ] Note the current fee shown (e.g., 55000.00)
- [ ] Submit form (should fail validation)
- [ ] Form re-renders with error
- [ ] Verify fee field **still shows 55000.00** (preserved)
- [ ] **NOT reset to default**

### Test 3.7: Trainer Fee Follows Same Pattern
- [ ] Verify trainer fee behaves identically:
  - [ ] Create: prefills default trainer fee
  - [ ] Edit: shows member's existing trainer fee
  - [ ] Changing default doesn't affect existing members

---

## AUTOMATED TEST SUITE

### Run All Gym Tests
```bash
pytest inventory/tests/test_gym*.py -v
```

Expected output:
```
test_gym_bulk_qr.py::TestBulkQRPDFPermissions::test_unauthenticated_user_cannot_download PASSED
test_gym_bulk_qr.py::TestBulkQRPDFPermissions::test_staff_user_cannot_download PASSED
test_gym_bulk_qr.py::TestBulkQRPDFPermissions::test_manager_user_can_download PASSED
... (42 more tests)

======================== 45 passed in 5.23s ========================
```

### Run Specific Test Files
```bash
# Bulk QR tests
pytest inventory/tests/test_gym_bulk_qr.py -v

# Trainer tests
pytest inventory/tests/test_gym_trainers.py -v

# Fee prefill tests
pytest inventory/tests/test_gym_membership_fee_prefill.py -v
```

### Check Test Coverage
```bash
pytest inventory/tests/test_gym*.py --cov=inventory.views_gym_bulk_qr --cov=inventory.views_gym --cov-report=html
```

---

## Common Issues & Solutions

### Issue: "PDF generation not available"
- **Cause**: ReportLab or qrcode not installed
- **Fix**: `pip install reportlab 'qrcode[pil]'`

### Issue: Bulk download returns 403
- **Cause**: User is not Manager
- **Fix**: Assign Manager role in business settings

### Issue: Fee shows default instead of member's fee in edit form
- **Cause**: Code not updated
- **Fix**: Verify `inventory/views_gym.py` line 258-297 has the fix

### Issue: QR codes don't scan
- **Cause**: Low print quality or wrong URL
- **Fix**: Print at high quality, verify URL in QR matches domain

### Issue: Trainers don't appear in dropdown
- **Cause**: Trainer is deactivated
- **Fix**: Activate trainer in Trainers list

### Issue: Test failures
- **Cause**: Database state or missing fixtures
- **Fix**: Run `python manage.py migrate`, clear test database

---

## Sign-Off Checklist

After completing all tests above, verify:

- [x] ✅ All 3 tasks implemented
- [ ] ✅ Bulk QR download works (all selection options)
- [ ] ✅ Trainers management accessible and functional
- [ ] ✅ Membership fee prefill correct (create vs edit)
- [ ] ✅ All 45 automated tests pass
- [ ] ✅ No linting errors
- [ ] ✅ No regressions to other verticals
- [ ] ✅ Documentation complete
- [ ] ✅ Dependencies installed
- [ ] ✅ Ready for production deployment

---

**Tester Name**: _________________________

**Date**: _________________________

**Environment**: [ ] Development  [ ] Staging  [ ] Production

**Result**: [ ] PASS  [ ] FAIL (see notes)

**Notes**:
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________

---

**Next Steps After Testing**:

1. ✅ All tests pass → Deploy to production
2. ❌ Issues found → Review logs, fix issues, re-test
3. Document any workarounds or special configurations needed

---

**Support**: If issues persist, check:
- Server logs: `tail -f /var/log/gunicorn/error.log`
- Django logs: Check `DEBUG=True` output
- Test output: `pytest -v --tb=short`

