# MULTI-TENANCY HARDENING - QUICK REFERENCE

## FILES CHANGED (10 files)

### Modified Files
1. `tenants/utils.py` - Added security helpers
2. `tenants/forms.py` - Enhanced with one-business-per-user validation
3. `tenants/views.py` - Hardened routes (choose/join/create)
4. `onboarding/forms.py` - Enhanced with one-business-per-user validation
5. `templates/base.html` - Removed switch UI for regular users
6. `tenants/context_processors.py` - Added `user_has_business` context

### New Files
7. `tenants/decorators.py` - Vertical & business isolation decorators
8. `tenants/migrations/0014_add_case_insensitive_unique_constraints.py` - DB constraints
9. `tenants/tests/test_multitenancy_hardening.py` - Test suite
10. `MULTI_TENANCY_HARDENING_SUMMARY.md` - Full documentation

---

## MIGRATIONS

```bash
# Apply migration
python manage.py migrate tenants

# Migration adds:
# - uniq_business_name_ci (Business name case-insensitive unique)
# - uniq_user_email_ci (User email case-insensitive unique)
```

---

## HOW TO USE NEW FEATURES

### 1. Business Scoping in Views

```python
from tenants.utils import scope_queryset_to_business, get_active_business

def my_view(request):
    business = get_active_business(request)
    products = scope_queryset_to_business(Product.objects.all(), business)
    return render(request, "list.html", {"products": products})
```

### 2. Vertical Isolation

```python
from tenants.decorators import require_vertical

@require_vertical("gym")
def gym_dashboard(request):
    # Only gym businesses can access
    return render(request, "gym/dashboard.html")
```

### 3. Check User Business Status

```python
from tenants.utils import user_has_any_business

if user_has_any_business(request.user):
    # User has a business
else:
    # User needs onboarding
```

### 4. Require Business Membership

```python
from tenants.decorators import require_business_access

@require_business_access
def protected_view(request):
    # Only users with business can access
    return render(request, "protected.html")
```

---

## TESTING

```bash
# Run all multi-tenancy tests
pytest tenants/tests/test_multitenancy_hardening.py -v

# Run specific test class
pytest tenants/tests/test_multitenancy_hardening.py::TestBusinessLockdown -v
```

---

## WHAT CHANGED FOR USERS

### Before
- ❌ Could switch between businesses
- ❌ Could join multiple businesses
- ❌ Could create multiple businesses with one email
- ❌ Duplicate names allowed ("Majinet" vs "majinet")

### After
- ✅ Locked to one business (no switching for regular users)
- ✅ Cannot join if already has a business
- ✅ One business per user/email
- ✅ Names globally unique (case-insensitive)
- ✅ Emails globally unique (case-insensitive)

---

## SUPERUSER EXCEPTIONS

Superusers retain ability to:
- Switch between businesses (for admin/support)
- Access all vertical routes
- View all businesses in admin

Regular users (managers, agents) are locked to their business.

---

## KEY GUARANTEES

1. **Business Lockdown**: Users with membership cannot switch/join
2. **Duplicate Prevention**: Names/emails unique (case-insensitive)
3. **Zero Data Leakage**: Business + vertical isolation enforced

---

## TROUBLESHOOTING

### User can't access anything after upgrade
→ Run: `python manage.py clearsessions`

### Migration fails with duplicate key error
→ Clean duplicates first (see full documentation)

### Form shows "already linked" but user has no business
→ Check pending memberships: `Membership.objects.filter(user=user)`

---

## ROLLBACK

```bash
# Revert migration
python manage.py migrate tenants 0013_add_location_tracking

# Revert code
git revert <commit-hash>
```

---

For full details, see `MULTI_TENANCY_HARDENING_SUMMARY.md`

