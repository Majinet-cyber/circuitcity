# Quick Verification Guide — 3 Upgrades

## TL;DR Commands

```bash
# 1. Apply migrations
python manage.py migrate inventory

# 2. Seed clothing jerseys
python manage.py seed_clothing_jerseys

# 3. Run tests
python -m pytest inventory/tests/test_gym_qr.py -v

# All done! ✅
```

---

## Detailed Verification Steps

### ✅ TASK 1: Clothing Jerseys

**Verify in UI:**
1. Navigate to: `/clothing/hub/` (or Clothing dashboard)
2. Click "Add Product" or "Stock In"
3. **Expected:** "Jersey" appears in category dropdown with ⚽ icon

**Seed Data:**
```bash
# Dry run (preview only)
python manage.py seed_clothing_jerseys --dry-run

# Actual seeding
python manage.py seed_clothing_jerseys
```

**Expected Output:**
```
Found 1 clothing business(es)
Processing business: My Store (ID: 1)
  ✓ CREATED: Chelsea FC 2024/25 Home Jersey (4 sizes, 40 units, K55000)
  ✓ CREATED: Chelsea FC 2024/25 Away Jersey (4 sizes, 38 units, K52000)
  ... (42 products total)
SEEDING COMPLETE: Created 42 products, skipped 0 existing
```

**Test a Sale:**
1. Go to Clothing → Inventory
2. Find any seeded jersey (e.g., "Manchester United 2024/25 Home Jersey")
3. Click "Sell" → Select size → Enter quantity
4. **Expected:** Sale completes, stock decreases, profit recorded

---

### ✅ TASK 2: Gym Gamification

**Run Migration:**
```bash
python manage.py migrate inventory
# Expected: Applying inventory.0107_add_gym_gamification_fields... OK
```

**Verify Check-In Page:**
1. Navigate to: `/gym/checkins/`
2. **Expected:** New "Streak & Badge" column visible
3. Check in any member
4. **Expected:** Success message shows: "✓ [Name] checked in! 🔥 X-day streak! [Badge]"

**Verify Gamification Stats:**
1. Go to Gym → Members → Click any member
2. **Expected:** Member detail shows:
   - Streak counter
   - Monthly check-ins
   - Total check-ins
   - Badge level (if earned)

**Verify Editable Fees:**
1. Navigate to: `/gym/member/add/`
2. **Expected:** "Membership Fee" and "Trainer Fee" fields visible and editable
3. Change fee value → Create member
4. **Expected:** Fee saved correctly (view member detail to confirm)

**Run Tests:**
```bash
python -m pytest inventory/tests/test_gym_qr.py -v
```

**Expected Output:**
```
inventory\tests\test_gym_qr.py ..........   [100%]
======================= 10 passed, 10 warnings in 6.41s =======================
```

---

### ✅ TASK 3: Input Validation

**Test Name Validation:**
1. Navigate to: `/gym/member/add/`
2. Enter name with digits: "John123"
3. Click Save
4. **Expected:** Error message: "This field should not contain numbers. Please enter text only."

**Test Fee Validation:**
1. Same form, try entering negative fee: "-100"
2. **Expected:** HTML5 validation prevents negative (or server rejects)
3. Try valid fee: "55000.50"
4. **Expected:** Accepted

**Test Phone Validation:**
1. Enter invalid phone: "abc123"
2. **Expected:** Error message about phone format
3. Enter valid phone: "0999123456"
4. **Expected:** Accepted and cleaned

---

## Quick Health Checks

### Database
```bash
# Verify migration applied
python manage.py showmigrations inventory | grep "0107_add_gym_gamification_fields"
# Expected: [X] 0107_add_gym_gamification_fields
```

### Code Quality
```bash
# Check for linting errors (optional)
python -m flake8 inventory/models_verticals.py inventory/views_gym.py core/validators.py --max-line-length=120
```

### Test Suite
```bash
# Run broader test suite (optional, may take longer)
python -m pytest inventory/tests/ -q
```

---

## Rollback (If Needed)

**Rollback Migration:**
```bash
python manage.py migrate inventory 0106  # Replace with previous migration number
```

**Remove Seeded Jerseys:**
```sql
-- Connect to DB and run (careful!):
DELETE FROM inventory_merchproduct WHERE category = 'jersey';
```

**Restore Validation:**
- Remove validators from forms
- Remove `from core.validators import ...` statements

---

## Common Issues & Solutions

### Issue: "Jersey not appearing in dropdown"
**Solution:** Clear browser cache or hard refresh (Ctrl+Shift+R)

### Issue: "Migration already applied"
**Solution:** This is normal if you ran it before. Migration is idempotent.

### Issue: "Seed command creates duplicates"
**Solution:** The command is idempotent (checks for existing products). Delete manually if needed.

### Issue: "Tests fail with import errors"
**Solution:** Ensure you're in the correct virtualenv and all dependencies installed:
```bash
pip install pytest pytest-django qrcode Pillow
```

### Issue: "QR code generation error"
**Solution:** Verify qrcode library installed:
```bash
pip install qrcode[pil]
```

---

## Files Reference

**Created:**
- `inventory/management/commands/seed_clothing_jerseys.py`
- `inventory/migrations/0107_add_gym_gamification_fields.py`
- `inventory/tests/test_gym_qr.py`
- `core/validators.py`
- `IMPLEMENTATION_SUMMARY_3_UPGRADES.md`
- `QUICK_VERIFICATION_GUIDE.md`

**Modified:**
- `inventory/clothing_config.py` (added jersey category)
- `inventory/models_verticals.py` (gamification fields + methods)
- `inventory/views_gym.py` (editable fees, validation)
- `templates/inventory/gym/checkin_page.html` (gamification UI)

---

## Support

If issues arise:
1. Check logs: `tail -f logs/django.log` (if logging configured)
2. Run tests with verbose output: `pytest -vv`
3. Check migration status: `python manage.py showmigrations`
4. Verify database: Check tables exist (`gym_member` has new fields)

---

**All systems green! ✅**

