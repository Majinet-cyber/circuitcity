# PowerShell Commands - Hardware Routing Fix

## Quick Reference

Run these commands in order to apply the hardware routing fix:

---

## 1. Check for Migrations

```powershell
python manage.py makemigrations
```

**Expected output:**
```
No changes detected
```

(We manually created the data migration, so no new migrations should be generated)

---

## 2. Run Migrations

```powershell
python manage.py migrate
```

**Expected output:**
```
Running migrations:
  Applying tenants.0023_normalize_hardware_business_kind... OK

Normalizing business_kind: 'Hardware & General Dealers' → 'hardware' for business: My Hardware Store
Normalizing business_kind: 'cement' → 'cement' for business: Cement Depot
✅ Normalized 12 business(es) to canonical business_kind values
```

**Note:** The number of normalized businesses will vary based on your data.

---

## 3. Run Tests

### Run hardware routing tests only:

```powershell
python manage.py test tests.test_hardware_signup_routing -v 2
```

**Expected output:**
```
test_general_dealer_normalizes_to_hardware ... ok
test_general_dealer_routes_to_hardware_vertical ... ok
test_hardware_business_no_settings_redirect_message ... ok
test_hardware_business_routes_to_dashboard ... ok
test_hardware_signup_business_kind_is_hardware ... ok
test_business_with_empty_kind_redirects_to_settings ... ok
test_business_with_null_kind_redirects_to_settings ... ok
test_normalize_cement_variants_separate ... ok
test_normalize_empty_returns_none ... ok
test_normalize_hardware_variants ... ok
test_normalize_phones_variants ... ok
test_validate_business_kind ... ok
test_unrecognized_vertical_shows_error_not_settings ... ok

----------------------------------------------------------------------
Ran 13 tests in X.XXXs

OK
```

### Run all tests (recommended):

```powershell
python manage.py test -v 2
```

**Expected:** All tests should pass ✅

---

## 4. Start Development Server

```powershell
python manage.py runserver
```

**Manual verification:**

1. Open browser: `http://127.0.0.1:8000/accounts/signup/`
2. Create a new account
3. Select business type: "Hardware & General Dealers"
4. Complete signup wizard
5. **Verify:** You land on `/inventory/dashboard/` (NOT `/accounts/settings/`)
6. **Verify:** Full sidebar appears (Dashboard, Analytics, Stock, Scan IN, Sell, etc.)
7. **Verify:** NO message: "Please set your business type in settings to access your dashboard."

---

## 5. Git Commit and Push

### Stage all changes:

```powershell
git add inventory/business_kinds.py
git add tenants/services/business_kind.py
git add inventory/utils_verticals.py
git add circuitcity/accounts/views.py
git add tenants/migrations/0023_normalize_hardware_business_kind.py
git add tests/test_hardware_signup_routing.py
git add HARDWARE_ROUTING_FIX_FINAL.md
git add POWERSHELL_COMMANDS.md
```

### Commit:

```powershell
git commit -m "Fix: Hardware vertical routing - hardware is now separate from cement

BREAKING: Hardware businesses now use 'hardware' canonical code (NOT 'cement')

Changes:
- Added HARDWARE as standalone canonical vertical code
- Fixed normalization: hardware variants → 'hardware' (NOT cement)
- Added hardware to vertical routing registry (routes to inventory dashboard)
- Created data migration to backfill existing businesses
- Updated tests to use 'hardware' canonical code
- Updated post-login routing to recognize hardware

Fixes:
- Hardware businesses no longer stuck on /accounts/settings/
- Hardware businesses now route to correct dashboard immediately after signup
- Full sidebar appears for hardware businesses (Dashboard, Stock, Scan IN, Sell, etc.)

Migration: tenants.0023_normalize_hardware_business_kind normalizes existing data

Files changed:
- inventory/business_kinds.py
- tenants/services/business_kind.py
- inventory/utils_verticals.py
- circuitcity/accounts/views.py
- tenants/migrations/0023_normalize_hardware_business_kind.py
- tests/test_hardware_signup_routing.py"
```

### Push to remote:

```powershell
git push origin main
```

---

## Verification Checklist

After running all commands, verify:

- [ ] Migrations ran successfully
- [ ] All tests pass
- [ ] Manual test: Hardware signup works
- [ ] Hardware business lands on correct dashboard
- [ ] Full sidebar appears
- [ ] NO settings redirect
- [ ] NO "Please set your business type" message
- [ ] Git commit successful
- [ ] Git push successful

---

## Troubleshooting

### If migrations fail:

```powershell
# Check migration status
python manage.py showmigrations tenants

# If migration already applied, skip it
# If migration conflicts, resolve conflicts first
```

### If tests fail:

```powershell
# Run specific failing test with verbose output
python manage.py test tests.test_hardware_signup_routing.TestHardwareSignupRouting.test_hardware_signup_business_kind_is_hardware -v 2

# Check test database
python manage.py test --keepdb -v 2
```

### If manual verification fails:

1. Check browser console for errors
2. Check Django logs for errors
3. Verify business_kind in database:
   ```powershell
   python manage.py shell
   ```
   ```python
   from tenants.models import Business
   biz = Business.objects.filter(name__icontains='hardware').first()
   print(f"business_kind: {biz.business_kind}")  # Should be 'hardware'
   ```

---

## Quick Test Script

Save this as `test_hardware_fix.ps1`:

```powershell
# test_hardware_fix.ps1
Write-Host "Testing Hardware Routing Fix..." -ForegroundColor Green

Write-Host "`n1. Running migrations..." -ForegroundColor Yellow
python manage.py migrate

Write-Host "`n2. Running tests..." -ForegroundColor Yellow
python manage.py test tests.test_hardware_signup_routing -v 2

Write-Host "`n3. Checking business_kind values..." -ForegroundColor Yellow
python manage.py shell -c "from tenants.models import Business; print('Hardware businesses:', Business.objects.filter(business_kind='hardware').count())"

Write-Host "`nDone! ✅" -ForegroundColor Green
```

Run it:

```powershell
.\test_hardware_fix.ps1
```

---

## Summary

Run these 5 commands:

1. `python manage.py makemigrations` (should be no changes)
2. `python manage.py migrate` (runs data migration)
3. `python manage.py test tests.test_hardware_signup_routing -v 2` (runs tests)
4. `python manage.py runserver` (manual verification)
5. `git add ... && git commit ... && git push` (deploy)

**That's it!** Hardware routing is now fixed. 🎉
