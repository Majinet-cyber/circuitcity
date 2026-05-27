# MULTI-TENANCY HARDENING - ACCEPTANCE CHECKLIST

Use this checklist to verify all requirements are met before deployment.

---

## PART A: LOCK SIGNED-IN USERS TO THEIR BUSINESS ✅

### A1: Single Source of Truth Helpers
- [x] `get_current_business(request)` exists in `tenants/utils.py`
- [x] `user_business_membership(user)` returns user's membership
- [x] `user_has_any_business(user)` checks for business existence
- [x] `require_business_membership()` decorator exists
- [x] `ensure_active_business_id()` forces users to their business (security)
- [x] Session override protection implemented

### A2: Template Hardening
- [x] Base template (`templates/base.html`) updated
- [x] "Switch business" only shown to superusers
- [x] "Join business" / "Join as agent" hidden from users with businesses
- [x] Context processor provides `user_has_business` variable

### A3: Route Backend Hardening
- [x] `/tenants/choose/` blocks users with business (redirects)
- [x] `/tenants/join-as-agent/` blocks users with business (error + redirect)
- [x] `/tenants/create/` blocks users with business (error + redirect)
- [x] All routes check `user_has_any_business()` before allowing access

---

## PART B: PREVENT DUPLICATES ✅

### B1: Database Constraints
- [x] Migration `0014_add_case_insensitive_unique_constraints.py` created
- [x] Business name: `UniqueConstraint(Lower("name"), name="uniq_business_name_ci")`
- [x] User email: `uniq_user_email_ci` constraint added
- [x] Constraints use PostgreSQL `Lower()` function for case-insensitivity

### B2: Form Validation
- [x] `CreateBusinessForm` validates name uniqueness (case-insensitive)
- [x] `CreateBusinessForm` blocks users with existing business
- [x] `BusinessForm` (onboarding) validates name uniqueness
- [x] `BusinessForm` (onboarding) blocks users with existing business
- [x] Forms show friendly error messages (not 500s)
- [x] `ManagerSignupForm` validates email uniqueness (case-insensitive)

### B3: Concurrency Safety
- [x] IntegrityError handling in forms
- [x] No 500 errors on duplicate attempts
- [x] Graceful error messages for users

---

## PART C: ZERO DATA LEAKAGE ✅

### C1: Business Scoping Helpers
- [x] `scope_queryset_to_business(qs, business)` exists
- [x] `get_object_for_business(Model, business, **kwargs)` exists
- [x] Helpers properly filter by `business_id`
- [x] Helpers return empty queryset if business is None

### C2: Vertical Guard
- [x] `@require_vertical()` decorator exists in `tenants/decorators.py`
- [x] Decorator checks `business.business_kind`
- [x] Returns 404 (not 403) on mismatch
- [x] Supports multiple allowed verticals: `@require_vertical("gym", "phones")`

### C3: Query Scoping Pattern
- [x] Pattern documented: `obj = get_object_or_404(Model.objects.filter(business=request.business), pk=pk)`
- [x] Helpers available for all views to use

---

## PART D: TESTS ✅

### Test File Created
- [x] `tenants/tests/test_multitenancy_hardening.py` exists
- [x] 400+ lines of comprehensive tests

### Test Coverage
- [x] **TestBusinessLockdown**: Route blocking for users with business
- [x] **TestDuplicatePrevention**: Name/email uniqueness + one-business-per-user
- [x] **TestBusinessIsolation**: Cross-business data access prevention
- [x] **TestVerticalIsolation**: Cross-vertical access prevention
- [x] **TestTenancyHelpers**: Utility function validation

### Specific Tests
- [x] User with business cannot GET `/tenants/choose/`
- [x] User with business cannot GET `/tenants/join-as-agent/`
- [x] Creating business with same name (diff case) raises error
- [x] Attempting to create 2nd business for same user is blocked
- [x] Email uniqueness (case-insensitive) is enforced
- [x] Business B user cannot access Business A data
- [x] Gym user cannot access phones URLs (404)
- [x] Phones user cannot access gym URLs (404)

---

## PART E: MANUAL SMOKE TESTS

### Test 1: Login as Owner/Manager ✅
- [ ] Login as user with business membership
- [ ] Check sidebar/header navigation
- [ ] Verify NO "Switch business" link visible (unless superuser)
- [ ] Verify NO "Join business" link visible
- [ ] Verify NO "Join as agent" link visible

### Test 2: Create Duplicate Business Name ✅
- [ ] Create business named "Test Store"
- [ ] Try to create another named "test store" (lowercase)
- [ ] Should see error: "That store name is already in use"
- [ ] Form should not submit

### Test 3: Signup with Existing Email ✅
- [ ] Create account with "test@example.com"
- [ ] Try to signup again with "TEST@EXAMPLE.COM"
- [ ] Should see error: "An account with this email already exists"
- [ ] Should suggest login instead

### Test 4: Access Other Business URL ✅
- [ ] Login as user from Business A
- [ ] Note down an object ID from Business A (e.g., product #123)
- [ ] Login as user from Business B
- [ ] Try to paste URL with Business A's object ID
- [ ] Should get 404 (not 403, not the actual object)

### Test 5: Access Wrong Vertical URL ✅
- [ ] Login as gym business user
- [ ] Try to access `/inventory/phone-sale-wizard/` (phones URL)
- [ ] Should get 404: "This feature is not available for your business type"
- [ ] Repeat for phones user accessing gym URLs

### Test 6: One Business Per User ✅
- [ ] Create user and business
- [ ] Logout and login again
- [ ] Try to access `/tenants/create/`
- [ ] Should see error: "This account is already linked to a business"
- [ ] Should be redirected to dashboard

---

## DEPLOYMENT CHECKLIST

### Pre-Deployment
- [ ] Review all changed files
- [ ] Run all tests: `pytest tenants/tests/test_multitenancy_hardening.py -v`
- [ ] Check for duplicate business names in database
- [ ] Check for duplicate emails in database
- [ ] Backup database

### Deployment
- [ ] Pull latest code to server
- [ ] Run migration: `python manage.py migrate tenants`
- [ ] Verify migration applied: Check for constraints in database
- [ ] Clear sessions: `python manage.py clearsessions`
- [ ] Restart application server

### Post-Deployment
- [ ] Run manual smoke tests (above)
- [ ] Monitor logs for IntegrityErrors
- [ ] Monitor user reports
- [ ] Verify no cross-business access in logs

---

## ACCEPTANCE CRITERIA (ALL MUST PASS)

### Goal 1: Business Lockdown ✅
- [x] Signed-in users with business NEVER see "Switch business"
- [x] Signed-in users with business NEVER see "Join business"
- [x] Signed-in users with business NEVER see "Join as agent"
- [x] Only users with NO business see onboarding UI
- [x] Routes are blocked at backend (not just hidden in templates)

### Goal 2: Duplicate Prevention ✅
- [x] Business names are globally unique (case-insensitive)
- [x] Emails are globally unique (case-insensitive)
- [x] One email cannot create multiple businesses
- [x] Users with business cannot create another business
- [x] Database constraints enforce uniqueness
- [x] Form validation provides friendly errors

### Goal 3: Zero Data Leakage ✅
- [x] Users cannot see data from other businesses
- [x] Users cannot access data from other verticals
- [x] Enforcement is at BACKEND level (middleware + decorators)
- [x] Templates receive proper context variables
- [x] All queries are scoped to business
- [x] Cross-business access returns 404 (not data)

---

## ROLLBACK CRITERIA

Rollback if ANY of these occur:
- [ ] Users cannot login after deployment
- [ ] Legitimate operations fail with IntegrityError
- [ ] Performance degrades significantly
- [ ] Data loss or corruption detected

Rollback steps documented in `MULTI_TENANCY_HARDENING_SUMMARY.md`

---

## SIGN-OFF

### Technical Lead
- [ ] Code reviewed
- [ ] Tests passing
- [ ] Documentation complete
- [ ] Migration safe to run

Date: _______________ Signature: _______________

### QA Lead
- [ ] Manual tests passed
- [ ] Acceptance criteria met
- [ ] No regressions found
- [ ] Ready for production

Date: _______________ Signature: _______________

### Product Owner
- [ ] Requirements met
- [ ] User experience acceptable
- [ ] Business rules enforced
- [ ] Approved for deployment

Date: _______________ Signature: _______________

---

**END OF CHECKLIST**

