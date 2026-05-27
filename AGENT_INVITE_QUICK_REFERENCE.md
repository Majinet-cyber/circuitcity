# Agent Invitation Flow - Quick Reference

## For Developers

### Password Requirements (NEW)
- **Minimum length:** 12 characters (increased from 8)
- **Complexity:** Must include ALL of:
  - At least 1 uppercase letter (A-Z)
  - At least 1 lowercase letter (a-z)
  - At least 1 digit (0-9)
  - At least 1 symbol (@, #, $, %, &, !, etc.)

### Examples
✓ **Valid:** `MyAgent2024!Pass`, `SecureP@ssw0rd`, `Test#Password123`  
✗ **Invalid:** `password123` (no uppercase, no symbol), `PASSWORD123!` (no lowercase)

---

## For Managers

### Creating Agent Invites
1. Go to **Agents** page
2. Fill in agent details:
   - **Name:** Required (letters only, no numbers)
   - **Email:** Optional but recommended
   - **Phone:** Optional
3. Click **Create Invite**
4. Share the invite link with your agent

### Field Requirements
- **Name:** Cannot be only numbers (e.g., "123456" is rejected)
- **Email:** Must be valid email format if provided
- **Phone:** Must be valid phone number if provided

---

## For Agents

### Accepting an Invite
1. Click the invite link from your manager
2. You'll see a form with:
   - **Email:** Pre-filled and locked (cannot be changed)
   - **Password:** Enter a strong password
   - **Confirm:** Re-enter the same password
3. Password must meet these requirements:
   - At least 12 characters
   - Include uppercase, lowercase, digit, and symbol
   - Example: `MyAgent2024!Pass`
4. Click **Create account**
5. You'll be logged in and redirected to your dashboard

### Troubleshooting
- **"Password too weak"**: Make sure you have uppercase, lowercase, digit, and symbol
- **"Passwords don't match"**: Re-type carefully in both fields
- **"Invite expired"**: Ask your manager to send a new invite
- **"Invalid invite link"**: Contact your manager for a fresh link

---

## What Was Fixed

### Before (Problems)
- ❌ Agents saw confusing "join as agent" or "switch business" prompts
- ❌ Weak 8-character passwords were accepted
- ❌ Managers could enter numbers where names should be
- ❌ Agents could land in wrong business/tenant
- ❌ Some validation was only client-side (could be bypassed)

### After (Solutions)
- ✅ Clean, single-page invite acceptance
- ✅ Strong 12+ character passwords enforced server-side
- ✅ Field validation prevents invalid data (numeric names, etc.)
- ✅ Agent always assigned to correct business (from invite)
- ✅ Defense in depth: validation at form AND view levels
- ✅ CSRF protection verified on all forms
- ✅ Safe redirects (no open redirect vulnerability)

---

## Files Modified

1. `tenants/validators.py` - New StrongPasswordValidator
2. `cc/settings.py` - Updated AUTH_PASSWORD_VALIDATORS
3. `tenants/forms.py` - Enhanced form validation
4. `tenants/views_invites.py` - Secure view logic
5. `templates/tenants/invite_accept.html` - Better UX and messaging

---

## Testing Commands

### Run the development server
```bash
python manage.py runserver
```

### Test as Manager
1. Login as manager
2. Go to `/tenants/manager/agents/`
3. Create a test invite
4. Copy the invite link

### Test as Agent
1. Open invite link in incognito/private window
2. Try weak password (should be rejected)
3. Try strong password (should succeed)
4. Verify you land on agent dashboard (not business chooser)

---

## Security Checklist

- [x] Passwords validated server-side
- [x] CSRF tokens on all forms
- [x] Field validation prevents invalid data
- [x] Tokens are random and expire
- [x] No open redirect vulnerability
- [x] Business isolation maintained
- [x] No XSS vulnerabilities
- [x] Proper error handling

---

## Support

If you encounter issues:
1. Check `AGENT_INVITE_SECURITY_FIX.md` for detailed documentation
2. Review Django logs for error details
3. Verify `tenants.validators.StrongPasswordValidator` is in settings
4. Ensure all template changes are deployed

---

**Last Updated:** December 9, 2025

