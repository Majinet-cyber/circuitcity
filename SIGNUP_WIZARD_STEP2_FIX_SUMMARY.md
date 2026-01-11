# Signup Wizard Step 2 Template Variable Fix - Summary

## Problem

Dev server logs showed repeated template exceptions on `/accounts/signup/manager/?step=2`:

```
VariableDoesNotExist: Failed lookup for key [business_name] in {}
VariableDoesNotExist: Failed lookup for key [business_kind] in {}
```

**Root Cause**: The template was using `{% with has_err=form.errors.business_name %}` which tried to access dictionary keys on an empty `ErrorDict` when the form was unbound, causing `VariableDoesNotExist` exceptions.

## Solution

Changed from accessing `form.errors.field_name` (which fails on unbound forms) to accessing `form.field_name.errors` (which is always safe).

### Changes Made

**File**: `templates/accounts/signup_manager_wizard_step2.html`

#### Before (Broken):
```django
{% with has_err=form.errors.business_name %}
<div class="field">
  <input class="input{% if has_err %} is-error{% endif %}"
         name="business_name"
         value="{{ form.business_name.value|default:'' }}">
  {% if has_err %}<div class="err">{{ form.errors.business_name|striptags }}</div>{% endif %}
</div>
{% endwith %}
```

#### After (Fixed):
```django
<div class="field">
  <input class="input{% if form.business_name.errors %} is-error{% endif %}"
         name="business_name"
         value="{{ form.business_name.value|default:'' }}">
  {% if form.business_name.errors %}<div class="err">{{ form.business_name.errors|striptags }}</div>{% endif %}
</div>
```

### Key Changes:

1. **Removed `{% with has_err=form.errors.business_name %}` blocks**
   - Accessing `form.errors.business_name` on an empty ErrorDict causes `VariableDoesNotExist`

2. **Changed to `form.business_name.errors`**
   - This is the correct Django pattern for accessing field-specific errors
   - Works correctly on unbound, bound-invalid, and bound-valid forms

3. **Applied fix to both fields**:
   - `business_name` field
   - `business_kind` field

## Testing

Created comprehensive regression test suite in `tests/test_signup_step2_template_fix.py`:

### Test Coverage:

1. **`test_template_renders_with_unbound_form`**
   - Verifies template renders without errors when form has no data
   - This is the core regression test for the bug

2. **`test_template_renders_with_bound_invalid_form`**
   - Verifies template correctly shows validation errors
   - Ensures error styling and messages appear

3. **`test_template_renders_with_valid_form`**
   - Verifies template preserves form values
   - Ensures selected options are marked correctly

### Test Results:
```
Ran 3 tests in 0.147s

OK
```

## Verification Steps

To verify the fix works:

1. **Clear Django cache**:
   ```bash
   python manage.py shell -c "from django.core.cache import cache; cache.clear()"
   ```

2. **Navigate to step 2**:
   - Go to `/accounts/signup/manager/?step=1`
   - Fill in step 1 form with valid data
   - Submit to proceed to step 2

3. **Verify no errors in logs**:
   - Check dev server console
   - Should see NO `VariableDoesNotExist` exceptions
   - Page should render cleanly

4. **Test form validation**:
   - Submit step 2 with empty fields
   - Should see error messages displayed correctly
   - Error styling should be applied

## Impact

✅ **Zero regressions** - UI and functionality remain unchanged
✅ **Clean logs** - No more `VariableDoesNotExist` exceptions
✅ **Better code** - Follows Django best practices for form error handling
✅ **Test coverage** - Regression tests prevent future breakage

## Django Best Practice

**Always use `form.field_name.errors` instead of `form.errors.field_name`**

```django
✅ CORRECT:
{% if form.email.errors %}
  <div class="error">{{ form.email.errors|striptags }}</div>
{% endif %}

❌ WRONG:
{% with has_err=form.errors.email %}
  {% if has_err %}
    <div class="error">{{ form.errors.email|striptags }}</div>
  {% endif %}
{% endwith %}
```

The `form.field_name.errors` pattern:
- Works on unbound forms (returns empty list)
- Works on bound-valid forms (returns empty list)
- Works on bound-invalid forms (returns error list)
- Never raises `VariableDoesNotExist`

## Files Modified

1. `templates/accounts/signup_manager_wizard_step2.html` - Fixed template
2. `tests/test_signup_step2_template_fix.py` - Added regression tests (NEW)
3. `tests/test_signup_wizard_step2_template.py` - Added integration tests (NEW)

## Related Files (No Changes Needed)

- `circuitcity/accounts/views.py` - View logic is correct
- `circuitcity/accounts/forms.py` - Form definition is correct
- `templates/accounts/signup_manager_wizard_step1.html` - Already correct
- `templates/accounts/signup_manager_wizard_step3.html` - Already correct
- `templates/accounts/signup_manager_wizard_step4.html` - Already correct

## Acceptance Criteria

✅ No "VariableDoesNotExist" logs for business_name/business_kind
✅ Step 2 form works normally and preserves values
✅ No UI regressions
✅ Tests pass: `python manage.py test tests.test_signup_step2_template_fix`

## Deployment Notes

- No database migrations required
- No settings changes required
- Template cache will auto-refresh on next request
- Safe to deploy immediately
