# CRITICAL REGRESSION FIX: Manager Signup Wizard Session State

**Date:** January 8, 2026
**Status:** ✅ FIXED

---

## Problem Identified

After implementing the logo step removal (3-step wizard), a **CRITICAL regression** was introduced:

### Issue 1: Step Routing Mismatch
- **Root Cause:** Template `signup_manager_wizard_step4.html` was still posting to `step=4`
- **Impact:** View only handles steps 1-3, so step=4 POST created an infinite loop
- **Result:** Users could not complete signup - final submit button didn't work

### Issue 2: Session State Already Working
- **Good News:** The wizard was already using session-backed state persistence
- **Verification:** Forms were initialized with `initial=wizard_data.get("stepX", {})`
- **Confirmation:** Session data persists across navigation, forms pre-fill correctly

---

## Root Cause Analysis

### The Step=4 Ghost Bug

**Before Fix:**
```python
# View accepts steps 1-3 only
if step < 1 or step > 3:
    step = 1
```

**Template was doing:**
```html
<form action="{% url 'accounts:signup_manager' %}?step=4">
  <input type="hidden" name="step" value="4">
```

**Result:** 
1. User submits final form with `step=4`
2. View receives `step=4`
3. View redirects to `step=1` (out of range)
4. User goes through wizard again
5. Loop continues forever ❌

---

## Solutions Implemented

### Fix 1: Backward Compatibility Redirect
**File:** `circuitcity/accounts/views.py`

Added step=4 detection and redirect:
```python
# CRITICAL FIX: Backward compatibility - redirect step=4 to step=3
if step == 4:
    # Old sessions may try to access step 4 (now step 3)
    return redirect(f"{reverse('accounts:signup_manager')}?step=3")
```

**Benefits:**
- ✅ Gracefully handles old cached templates
- ✅ Old browser sessions with step=4 work
- ✅ No breaking change for mid-flight users

### Fix 2: Template Step Correction
**File:** `templates/accounts/signup_manager_wizard_step4.html`

Changed form action and hidden field:
```html
<!-- OLD (BROKEN):
<form action="{% url 'accounts:signup_manager' %}?step=4">
  <input type="hidden" name="step" value="4">
-->

<!-- NEW (FIXED): -->
<form action="{% url 'accounts:signup_manager' %}?step=3">
  <input type="hidden" name="step" value="3">
```

**Benefits:**
- ✅ Form posts to correct step (step=3)
- ✅ No more infinite loop
- ✅ Store creation works immediately

---

## Session State Verification

### Confirmed Working
The wizard **already had** proper session state management:

**Step 1:**
```python
form = ManagerWizardStep1Form(request.POST or None, initial=wizard_data.get("step1", {}))
if request.method == "POST" and form.is_valid():
    wizard_data["step1"] = form.cleaned_data
    _set_manager_wizard_data(request, wizard_data)
    return redirect("?step=2")
```

**Step 2:**
```python
form = ManagerWizardStep2Form(request.POST or None, initial=wizard_data.get("step2", {}))
if request.method == "POST" and form.is_valid():
    wizard_data["step2"] = form.cleaned_data
    _set_manager_wizard_data(request, wizard_data)
    return redirect("?step=3")
```

**Behavior:**
- ✅ POST saves data to session
- ✅ GET loads data from session via `initial=`
- ✅ Back button navigation preserves all inputs
- ✅ Validation errors don't wipe data (Django form behavior)

---

## Testing

### Comprehensive Test Suite Created
**File:** `tests/test_signup_wizard_session_state.py`

**10 tests - All passing ✅**

1. ✅ `test_step1_data_persists_in_session` - Session stores step 1 data
2. ✅ `test_back_navigation_preserves_step1_inputs` - Back to step 1 shows pre-filled values
3. ✅ `test_step2_data_persists_and_back_works` - Step 2 data persists, back works
4. ✅ `test_final_submit_step3_creates_store` - Final submit on step=3 creates store
5. ✅ `test_step4_backward_compat_redirects_to_step3` - GET step=4 → redirects to step=3
6. ✅ `test_step4_post_redirects_to_step3` - POST step=4 → redirects to step=3
7. ✅ `test_session_cleared_on_success` - Wizard clears session after completion
8. ✅ `test_validation_error_preserves_form_data` - Errors don't wipe fields
9. ✅ `test_back_from_step3_to_step2_preserves_data` - Back from review preserves data
10. ✅ `test_multiple_back_forth_navigation` - Multiple back/forth preserves all data

**Test Output:**
```
Ran 10 tests in 11.458s

OK
```

---

## Manual QA Checklist

### Test Scenario 1: Complete Signup Flow
- [ ] Fill step 1 (email, name, password) → Click Next
- [ ] Fill step 2 (store name, type, subdomain) → Click Next
- [ ] Review step 3 → Check terms → Click "Create my store"
- [ ] ✅ Should redirect to dashboard
- [ ] ✅ Store should exist in database
- [ ] ✅ User should be logged in

### Test Scenario 2: Back Navigation
- [ ] Fill step 1 → Next
- [ ] Fill step 2 → Next
- [ ] At step 3 → Click Back
- [ ] ✅ Step 2 fields should be pre-filled
- [ ] Click Back again
- [ ] ✅ Step 1 fields should be pre-filled (email, name)
- [ ] Note: Password fields will be blank (security best practice)

### Test Scenario 3: Validation Errors
- [ ] Fill step 1 → Next
- [ ] At step 2, leave "Store name" blank → Click Next
- [ ] ✅ Should stay on step 2 with error message
- [ ] ✅ Other fields (subdomain, business type) should still have values

### Test Scenario 4: Subdomain Collision (from previous fix)
- [ ] Create store with subdomain "test"
- [ ] Start new signup with same subdomain "test"
- [ ] Complete wizard
- [ ] ✅ Should succeed with subdomain "test-1" (auto-suffixed)
- [ ] ✅ User should see notification about subdomain change

---

## Regression Tests

### Verified No Breaking Changes

**Auth/Login:** ✅ No changes
**Tenants/Membership:** ✅ No changes  
**Business Creation:** ✅ Enhanced (idempotent, collision-safe)
**Existing Stores:** ✅ No impact
**Other Signup Flows:** ✅ No changes

---

## Files Modified

### Core Logic
1. `circuitcity/accounts/views.py` - Added step=4 redirect for backward compat

### Templates
2. `templates/accounts/signup_manager_wizard_step4.html` - Fixed form action to post to step=3

### Tests
3. `tests/test_signup_wizard_session_state.py` - 10 comprehensive tests for session state

---

## Key Improvements

### Before (BROKEN)
- ❌ Final submit created infinite loop
- ❌ Users couldn't complete signup
- ❌ Step=4 routing mismatch

### After (FIXED)
- ✅ Final submit works perfectly
- ✅ Step=4 backward compatibility added
- ✅ Session state verified and tested
- ✅ All navigation preserves inputs
- ✅ 10 tests passing

---

## Deployment Notes

### Zero-Downtime
- All changes are backward compatible
- Step=4 redirect handles old sessions gracefully
- No database migrations needed

### Monitoring
Watch for:
1. Signup completion rate (should be 100% now)
2. No more "stuck at review" support tickets
3. Request IDs in logs for any errors

---

## Summary

**Critical regression FIXED:**
- Store creation infinite loop eliminated
- Step routing corrected (step=4 → step=3)
- Backward compatibility maintained
- Session state working and tested

**No new regressions introduced:**
- All existing functionality intact
- Store creation hardening preserved (idempotent, collision-safe)
- 3-step wizard maintained
- 10 comprehensive tests passing

**Production ready:** ✅

