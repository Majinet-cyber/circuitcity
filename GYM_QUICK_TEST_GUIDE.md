# Gym Vertical - Quick Test Guide

## 🚀 Quick Manual Testing Steps

### Test 1: New Member Payment is Active (NOT in Arrears)

**Goal:** Verify that a brand-new member with payment today shows as ACTIVE with 30 days left, and is NOT counted in arrears.

**Steps:**
1. Navigate to **Gym → Members**
2. Click **"Add Member"**
3. Fill in:
   - Name: "Test Member 1"
   - Phone: "0977111111"
   - Email: "test1@gym.com"
4. Save
5. Click **"Record Payment"** on the member detail page
6. Enter:
   - Amount: K150.00
   - Date: Today
7. Save payment
8. Navigate to **Gym Dashboard**

**Expected Results:**
- Dashboard shows:
  - **TOTAL MEMBERS: 1**
  - **ACTIVE MEMBERS: 1**
  - **IN ARREARS: 0** ✅ (NOT 1!)
- Member detail page shows:
  - Status: "Active" (green badge)
  - Days Left: "30 of 30 days"
  - Next Payment: (29 days from today)

---

### Test 2: Member Check-In Shows "Present"

**Goal:** Verify that checking in a member clearly shows "Present" in the Today column.

**Steps:**
1. Navigate to **Gym → Member Check-ins**
2. Find an active member (from Test 1)
3. Observe the **"Today"** column - should show "Absent" or "-"
4. Click **"Check In"** button for that member
5. Page reloads

**Expected Results:**
- After check-in:
  - **"Today" column shows "✓ Present"** (green badge, large and visible)
  - Check-in button becomes "Checked In" (disabled)
- If you try to check in again:
  - Toast message: "Member 'Test Member 1' already checked in today."
  - No duplicate check-in created

---

### Test 3: Expired Member Cannot Check In

**Goal:** Verify that expired members show "Inactive" and cannot check in.

**Steps:**
1. In Django Admin or via DB:
   - Find the test member
   - Set `membership_end` to yesterday's date
   - Save
2. Navigate to **Gym → Member Check-ins**
3. Find the member

**Expected Results:**
- Member shows:
  - Status: "Expired" (red badge)
  - Days Left: "0 days"
  - **Today: "Inactive"** (red badge)
  - Button: "🔒 Inactive" (disabled)
- Hovering over button shows tooltip: "Membership inactive. Record payment first."
- Clicking does nothing (button is disabled)

---

### Test 4: Days Count Down Properly

**Goal:** Verify that days_left decrements correctly day by day.

**Steps:**
1. Create a new member with payment today
2. Check member detail:
   - Should show "30 of 30 days"
3. In Django Admin:
   - Set `membership_start` to 2 days ago
   - Set `membership_end` to 27 days from today (so total is still 30 days)
   - Save
4. Refresh member detail page

**Expected Results:**
- Should now show "28 of 30 days" (2 days have passed)
- Status still "Active" (green)

**Bonus:**
- Set `membership_end` to today
- Refresh: Should show "1 of 30 days" (last day, still active)
- Set `membership_end` to yesterday
- Refresh: Should show "Expired" status, "0 days"

---

### Test 5: Dashboard IN ARREARS Count is Accurate

**Goal:** Verify dashboard counts active vs in arrears correctly.

**Steps:**
1. Create 3 members:
   - **Member A:** Payment today (active)
   - **Member B:** Payment 40 days ago (expired)
   - **Member C:** No payment at all
2. Navigate to **Gym Dashboard**

**Expected Results:**
- Dashboard shows:
  - **TOTAL MEMBERS: 3**
  - **ACTIVE MEMBERS: 1** (only Member A)
  - **IN ARREARS: 2** (Member B + Member C)

**Critical:**
- Member A (new active member) should NEVER appear in IN ARREARS count!

---

### Test 6: Trainer Fee Warning

**Goal:** Verify that missing trainer fees show warnings.

**Steps:**
1. Navigate to **Gym → Trainers**
2. Add a trainer:
   - Name: "Steve"
   - Phone: "0977222222"
3. Edit an active member (from Test 1)
4. Assign trainer: "Steve"
5. Save
6. Navigate to member detail page

**Expected Results:**
- Member detail shows:
  - Trainer: "Steve"
  - ⚠️ **Warning badge: "Fee not recorded"** (yellow/orange)
7. Record trainer fee (via admin or future UI)
8. Refresh member detail
9. Warning badge disappears

---

## 🧪 Automated Test Suite

Run all gym tests:

```bash
pytest tests/test_gym_membership_fixes.py -v
```

**Expected output:**
```
14 passed in ~4s
```

---

## ✅ Regression Testing

Verify no other verticals were broken:

```bash
# Test pharmacy
pytest inventory/tests/test_pharmacy_vertical.py -v

# Test phones (if exists)
pytest inventory/tests/test_phone_*.py -v
```

All should pass with no errors related to gym changes.

---

## 🐛 Common Issues & Fixes

### Issue: Dashboard shows IN ARREARS = 1 for new member
**Cause:** Old logic using `days_left() == 0`  
**Fix:** Verify `inventory/verticals/gym.py` uses `get_membership_status()` helper  
**Test:** Run Test 1 above

### Issue: Check-in doesn't show "Present"
**Cause:** Template not updated to use new context variables  
**Fix:** Verify `templates/inventory/gym/checkin_page.html` has "Today" column  
**Test:** Run Test 2 above

### Issue: Member shows 29 days instead of 30 on day 1
**Cause:** Non-inclusive day counting  
**Fix:** Verify `utils_gym.py` uses `(end - today).days + 1`  
**Test:** Create member with payment today, check days_left

---

## 📊 Expected Data Flow

### New Member Payment:
```
1. Staff clicks "Record Payment"
2. View calls member.set_paid(payment_date=today)
3. Model sets:
   - membership_start = today
   - membership_end = today + 29 days
   - status = ACTIVE
4. GymPayment record created
5. Redirect to member detail
6. Detail page calls get_membership_status()
7. Returns: {
     status_code: "active",
     days_remaining: 30,
     label: "Active"
   }
8. Template displays: "Active" badge, "30 of 30 days"
```

### Check-In Flow:
```
1. Staff opens /gym/checkin/
2. View loops through members:
   - Calls get_membership_status()
   - Checks if checked_in_today
   - Sets today_status = "present" | "absent" | "inactive"
3. Template displays "Today" column with status
4. Staff clicks "Check In"
5. POST to /gym/member/<id>/checkin/
6. View creates GymCheckIn record
7. Redirect back to checkin page
8. Now shows "Present" badge
```

---

## 🎯 Key Success Metrics

After implementation, the following should ALWAYS be true:

1. ✅ New paying member = ACTIVE (not in arrears)
2. ✅ Dashboard IN ARREARS count = expired + no-membership only
3. ✅ Check-in page shows "Present" after check-in
4. ✅ Expired members cannot check in (button disabled)
5. ✅ Days count down from 30 to 1 (inclusive)
6. ✅ Trainer fee warnings shown when missing

If any of these fail, the implementation has a bug.

---

## 📞 Support

For issues or questions:
- Check `GYM_MEMBERSHIP_FIX_IMPLEMENTATION.md` for detailed implementation docs
- Review test cases in `tests/test_gym_membership_fixes.py`
- All gym logic in `inventory/utils_gym.py` (single source of truth)

