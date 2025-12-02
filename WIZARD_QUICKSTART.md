# Signup Wizard Quick Start Guide

## How to Test the Wizard

### 1. Run Migrations (Already Done ✅)
```bash
python manage.py migrate accounts
```

### 2. Start the Development Server
```bash
python manage.py runserver
```

### 3. Access the Wizard
Open your browser and go to:
```
http://localhost:8000/accounts/signup/
```

Or click "Create a Manager account" from the login page:
```
http://localhost:8000/accounts/login/
```

## Test Data Examples

### Step 1: Your Account
- **Full Name**: `Test Manager`
- **Email**: `test@circuitcity.com`
- **Password**: `TestPassword123!`
- **Confirm Password**: `TestPassword123!`

### Step 2: Your Business
- **Business Name**: `Circuit City Test Store`
- **Country**: `Zambia`
- **Currency**: `ZMW - Zambian Kwacha`
- **Business Type**: `Phones & Electronics`

### Step 3: First Location
- **Location Name**: `Main Store`
- **City**: `Lusaka`
- **Staff Count**: `5` (optional)

### Step 4: Goals
Select any combination of goals:
- ☑ Stop theft and missing stock
- ☑ See profit and losses clearly
- ☐ Track agent performance and rankings
- ☑ Move off hardcover notebooks

## What Happens After Completion?

1. **User is created** with email as username
2. **Business is created** with status=ACTIVE
3. **First Location is created** as default
4. **Manager membership** is assigned
5. **OnboardingProfile** is saved with selected goals
6. **User is logged in** automatically
7. **Business context** is set in session
8. **Redirected to dashboard** with success message

## Verify the Setup

### Check User Created
```python
python manage.py shell

from django.contrib.auth import get_user_model
User = get_user_model()

user = User.objects.get(email='test@circuitcity.com')
print(f"User: {user.get_full_name()}")
print(f"Is Manager: {user.profile.is_manager}")
print(f"Groups: {list(user.groups.values_list('name', flat=True))}")
```

### Check Business Created
```python
from tenants.models import Business, Membership

biz = Business.objects.get(name='Circuit City Test Store')
print(f"Business: {biz.name}")
print(f"Status: {biz.status}")
print(f"Vertical: {biz.business_kind}")
print(f"Slug: {biz.slug}")

membership = Membership.objects.get(user=user, business=biz)
print(f"Role: {membership.role}")
print(f"Status: {membership.status}")
```

### Check Location Created
```python
from inventory.models import Location

location = Location.objects.get(business=biz, name='Main Store')
print(f"Location: {location.name}")
print(f"City: {location.city}")
print(f"Is Default: {location.is_default}")
```

### Check OnboardingProfile
```python
from circuitcity.accounts.models import OnboardingProfile

profile = OnboardingProfile.objects.get(user=user)
print(f"Goals: {profile.selected_goals}")
print(f"Business: {profile.first_business_name}")
print(f"Location: {profile.first_location_name}")
print(f"Vertical: {profile.chosen_vertical}")
print(f"Completed: {profile.completed_at}")
```

## Testing Validation Errors

### Test Duplicate Email (Step 1)
1. Complete the wizard once
2. Start the wizard again
3. Use the same email from Step 1
4. Should show: "You already have an account with this email"

### Test Password Mismatch (Step 1)
- **Password**: `TestPassword123!`
- **Confirm Password**: `DifferentPassword456!`
- Should show validation error

### Test Missing Required Fields
Try submitting any step with empty required fields to see validation messages.

### Test Skipping Steps
Try accessing `/accounts/signup/wizard/3/` directly without completing Steps 1 & 2.
Should redirect you back to Step 1.

## Testing Navigation

### Going Back
1. Complete Step 1
2. Complete Step 2
3. Click "← Back" on Step 3
4. Data should be preserved
5. Continue forward again - data still there

### Session Persistence
1. Complete Steps 1 & 2
2. Close the browser tab (but not the browser)
3. Open a new tab and go to Step 3
4. Your data should still be there

## Browser Testing

### Desktop Browsers
- ✅ Chrome
- ✅ Firefox
- ✅ Safari
- ✅ Edge

### Mobile Browsers
- ✅ Mobile Chrome (Android)
- ✅ Mobile Safari (iOS)
- ✅ Samsung Internet

### Responsive Design
Test at these breakpoints:
- **Mobile**: 375px width
- **Tablet**: 768px width
- **Desktop**: 1024px+ width

## Visual Testing Checklist

### Step 0 (Welcome)
- [ ] Logo and brand visible
- [ ] Progress bar shows step 1/5
- [ ] Benefits list with checkmarks
- [ ] "Get Started" button prominent
- [ ] Glassmorphic card effect visible
- [ ] Background gradient visible

### Step 1 (Your Account)
- [ ] Level badge shows "🎯 Level 1"
- [ ] Progress bar shows step 2/5 with dot 1 completed
- [ ] All form fields visible and styled
- [ ] Input fields have proper focus states
- [ ] Password fields hide text
- [ ] "Back" and "Continue" buttons aligned

### Step 2 (Your Business)
- [ ] Level badge shows "🏢 Level 2"
- [ ] Progress bar shows step 3/5
- [ ] Currency dropdown styled
- [ ] Business type dropdown styled
- [ ] Field hints visible

### Step 3 (First Location)
- [ ] Level badge shows "📍 Level 3"
- [ ] Progress bar shows step 4/5
- [ ] Vertical pill shows selected business type
- [ ] Staff count is optional

### Step 4 (Goals & Finish)
- [ ] Level badge shows "🎯 Level 4"
- [ ] Progress bar shows step 5/5
- [ ] Checkboxes styled properly
- [ ] Summary card shows all data
- [ ] "🚀 Launch My Dashboard" button prominent

## Performance Testing

### Time to Complete
Target: < 2 minutes (as advertised)

Measure from Step 0 to completion:
- Step 0: ~10 seconds (read benefits)
- Step 1: ~30 seconds (enter credentials)
- Step 2: ~20 seconds (business details)
- Step 3: ~20 seconds (location)
- Step 4: ~30 seconds (select goals, review summary)
- **Total**: ~2 minutes ✅

### Page Load Speed
- Each step should load in < 500ms
- No layout shift (CLS score)
- Smooth animations

## Accessibility Testing

### Keyboard Navigation
1. Use `Tab` to navigate through fields
2. Use `Enter` to submit forms
3. Use `Shift+Tab` to go backwards
4. All interactive elements should be reachable

### Screen Reader Testing
- Labels properly associated with inputs
- Error messages announced
- Progress indicator accessible

## Edge Cases to Test

### Already Authenticated User
1. Login as an existing user
2. Try to access `/accounts/signup/`
3. Should redirect to dashboard

### Invalid Step Numbers
- `/accounts/signup/wizard/-1/` → Redirect to Step 0
- `/accounts/signup/wizard/99/` → Redirect to Step 0

### Session Expiry
1. Complete Step 1
2. Wait for session to expire (or clear cookies)
3. Try to access Step 2
4. Should still work (data lost, but no error)

### Server Errors
Simulate database connection issues to ensure graceful error handling.

## Known Issues / Limitations

1. **Migration Issue**: Pre-existing inventory migrations prevent full test suite from running (unrelated to wizard)
2. **Confetti**: Currently uses emoji instead of canvas-based confetti animation
3. **IE11**: Not supported (uses modern CSS features like backdrop-filter)

## Rollback Instructions

If you need to revert to the old signup:

1. Update login template:
```html
<a href="{% url 'accounts:signup_manager' %}">Create a Manager account</a>
```

2. The old `/accounts/signup/manager/` URL still works as a fallback

3. Or hide the wizard routes in `urls.py` (comment them out)

## Production Deployment Checklist

Before deploying to production:

- [ ] Run `python manage.py migrate accounts` on production DB
- [ ] Test the wizard on staging environment
- [ ] Verify SSL/HTTPS works (forms have sensitive data)
- [ ] Check session storage is configured properly
- [ ] Monitor signup conversion rates
- [ ] Set up analytics tracking for each step
- [ ] Configure SMTP for welcome emails (if applicable)
- [ ] Test password reset flow still works
- [ ] Verify existing users can still login
- [ ] Check mobile experience on real devices

## Monitoring & Analytics

Consider tracking these metrics:
- Conversion rate per step (funnel analysis)
- Time spent on each step
- Most common exit points
- Most selected goals
- Device/browser breakdown
- Error rates per field

## Support & Troubleshooting

### Users Report Issues
- Check session middleware is enabled
- Verify CSRF tokens are present
- Check browser console for JavaScript errors
- Verify templates are loading correctly

### Business Not Created
- Check transaction rollback in logs
- Verify Business model constraints
- Check slug generation for duplicates
- Verify TENANT_SESSION_KEY is set

### User Can't Login After Signup
- Verify password was hashed (not stored plain)
- Check user.is_active is True
- Verify no middleware is blocking login

## Success Criteria ✅

The wizard is working correctly if:
- ✅ User can complete all 5 steps
- ✅ Data persists between steps
- ✅ User can go back and forth
- ✅ All entities are created (User, Business, Location, etc.)
- ✅ User is logged in after completion
- ✅ User lands on dashboard with correct business context
- ✅ Design is beautiful and responsive
- ✅ No JavaScript errors in console
- ✅ No server errors in logs
- ✅ Existing users can still login
- ✅ Old signup URL still works (backwards compat)

---

**Ready to test?** 🚀

Start the server and visit `/accounts/signup/` to begin!

