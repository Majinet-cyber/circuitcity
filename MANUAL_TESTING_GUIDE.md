# Agent Invite Flow - Manual Testing Guide

## Quick Start

Run the verification script first:
```bash
python verify_invite_flow.py
```

All checks should pass ✅ before proceeding to browser testing.

---

## Browser Testing Procedure

### Setup
1. **Start the development server**:
   ```bash
   python manage.py runserver
   ```

2. **Login as MANAGER** (use your normal browser)
   - Go to http://localhost:8000
   - Navigate to the Agents management page
   - Create a new agent invite
   - Copy the generated invite link

---

## Test Case 1: New Agent Signup (CRITICAL)

**This is the primary flow that was failing with 500 errors.**

### Steps:
1. **Open Incognito/Private window** (to simulate a new user)
2. **Paste the invite link** from above
3. **Verify the page loads**:
   - ✅ No 500 error
   - ✅ Form displays cleanly
   - ✅ Card fits on screen without awkward scrolling
   - ✅ See: "Join [Business Name]" heading
   - ✅ See: Email field, Password fields, "Create account" button

4. **Check browser console** (F12):
   - ✅ No `active_tab` variable errors
   - ✅ No JavaScript errors

5. **Fill out the form**:
   ```
   Name: Test Agent One
   Email: (should be pre-filled or locked if invite has email)
   Password: StrongPass123!
   Confirm: StrongPass123!
   ```

6. **Submit the form**:
   - Click "Create account"
   - Button text changes to "Creating account…"

7. **Expected Success Behavior**:
   - ✅ **NO 500 Internal Server Error**
   - ✅ **NO CSRF 403 Forbidden**
   - ✅ Redirects to agent dashboard or inventory scan page
   - ✅ User is logged in (see username in header)
   - ✅ Success message displays (e.g., "You're now part of [Business]")

8. **Verify in Database** (as manager):
   - Go to Django Admin → Users
   - ✅ New user exists with correct email
   - Go to Django Admin → Memberships
   - ✅ Membership exists (Status=ACTIVE, Role=AGENT)
   - Go to Django Admin → Agent Invites
   - ✅ Invite status is "JOINED"
   - ✅ `joined_user` field points to new user

---

## Test Case 2: Form Validation

### Test 2a: Mismatched Passwords
1. Open invite link in Incognito
2. Fill form with **different passwords**:
   ```
   Password: TestPass123!
   Confirm: DifferentPass456!
   ```
3. Submit
4. **Expected**:
   - ✅ Returns 400 (not 500)
   - ✅ Shows error: "Passwords do not match"
   - ✅ Form stays on page (doesn't blank out)
   - ✅ User NOT created in database

### Test 2b: Weak Password
1. Open invite link in Incognito
2. Fill form with **short password**:
   ```
   Password: 123
   Confirm: 123
   ```
3. Submit
4. **Expected**:
   - ✅ Returns 400 (not 500)
   - ✅ Shows error: "Password must be at least 8 characters"
   - ✅ User NOT created

---

## Test Case 3: Invalid/Expired Invites

### Test 3a: Invalid Token
1. Open URL: `http://localhost:8000/tenants/invites/accept/fake-invalid-token-xyz/`
2. **Expected**:
   - ✅ Returns 404 (not 500)
   - ✅ Shows: "Invalid invite" message
   - ✅ Friendly error page (not Django debug page)

### Test 3b: Expired Invite
1. In Django Admin, create an invite with **past expiry date**:
   ```
   Business: [your test business]
   Email: expired@test.com
   Expires At: [yesterday's date]
   ```
2. Copy the token from the invite
3. Open: `http://localhost:8000/tenants/invites/accept/[that-token]/`
4. **Expected**:
   - ✅ Returns 410 Gone (not 500)
   - ✅ Shows: "Invite has expired" or "Invite expired" message
   - ✅ Friendly error page

---

## Test Case 4: Already Authenticated User

### Steps:
1. **Login as an existing user** (any account, not necessarily the invite's target)
2. **While still logged in**, open an invite link
3. **Expected**:
   - ✅ Does NOT show the signup form
   - ✅ Auto-accepts the invite
   - ✅ Redirects to agent dashboard
   - ✅ Membership created for the logged-in user
   - ✅ Success message appears

---

## Test Case 5: CSRF Protection

### Steps:
1. Open invite link in Incognito
2. **Open browser DevTools** (F12) → Network tab
3. Fill out and submit the form
4. **Check the POST request**:
   - ✅ Request includes `csrfmiddlewaretoken` in form data
   - ✅ Response is **302 redirect** (success) or **400** (validation error)
   - ✅ **NOT 403 Forbidden**

---

## Test Case 6: UI/UX Check

### Screen Sizes to Test:
1. **Desktop (1366x768)** - typical laptop
2. **Tablet (768x1024)** - landscape
3. **Mobile (375x667)** - iPhone SE

### Checklist for Each Size:
- ✅ Card is centered on screen
- ✅ No horizontal scrolling needed
- ✅ All fields visible without awkward vertical scrolling
- ✅ Button is fully visible
- ✅ Form looks professional and modern

---

## Console Checks (Throughout All Tests)

### What You SHOULD NOT See:
- ❌ `Exception while resolving variable 'active_tab'`
- ❌ `500 Internal Server Error`
- ❌ `403 Forbidden (CSRF verification failed)`
- ❌ Blank error pages
- ❌ Raw exception tracebacks (in production mode)

### What You SHOULD See (in dev server console):
- ✅ `User [username] logged in via invite [token]` (on success)
- ✅ `Created new user [username] (email) for invite [token]` (on new signup)
- ✅ Detailed exception logs if errors occur (with `logger.exception`)

---

## Troubleshooting

### If you see a 500 error:
1. Check the **dev server console** output
2. Look for `logger.exception()` messages with full traceback
3. The error should be caught and logged with context (invite token, email, etc.)
4. Report the specific exception to fix it

### If you see a CSRF error:
1. Verify template has `{% csrf_token %}`
2. Check that form `method="post"`
3. Ensure `@ensure_csrf_cookie` decorator is on view
4. Clear browser cookies and try again

### If form doesn't submit:
1. Check browser console for JavaScript errors
2. Verify passwords match and meet minimum length
3. Check that submit button isn't disabled permanently

---

## Success Criteria

**The invite flow is considered 100% solid when:**

✅ **All 6 test cases above pass without errors**  
✅ **No 500 errors on valid or invalid submissions**  
✅ **No CSRF 403 errors**  
✅ **No `active_tab` template warnings**  
✅ **Clear, user-friendly error messages for all failure cases**  
✅ **Form validates and provides helpful feedback**  
✅ **Successful signups create user, membership, and log them in**  
✅ **UI is responsive and looks good on mobile/tablet/desktop**

---

## Post-Testing Actions

### If All Tests Pass:
1. ✅ Mark the invite flow as production-ready
2. 🚀 Deploy to staging for final verification
3. 📊 Monitor logs for first week in production
4. 📧 Consider adding email verification as enhancement

### If Any Tests Fail:
1. 📝 Document the exact failure (screenshot + console logs)
2. 🔍 Check dev server logs for exception details
3. 🐛 Fix the specific issue
4. ♻️  Re-run verification script: `python verify_invite_flow.py`
5. 🔁 Repeat manual tests until all pass

---

## Files Changed (For Reference)

- **tenants/forms.py** - Safer email field handling
- **tenants/views_invites.py** - Comprehensive error handling
- **templates/tenants/invite_accept.html** - Already optimal (no changes needed)
- **tests/test_agents_and_invites.py** - Test cleanup

---

## Need Help?

- See **INVITE_FLOW_FIXES.md** for technical details of changes
- Run **verify_invite_flow.py** to check code fixes are in place
- Check server logs for detailed error messages with context

---

**Happy Testing! 🎉**

