# Quick Test Guide - Smoke Tests Validation

This guide helps you **validate that all smoke tests work correctly** after implementation.

## Prerequisites

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Install Playwright browsers (for E2E tests)
playwright install chromium
```

## Step 1: Validate Django Smoke Tests (Fast - 1 minute)

### Test 1: Syntax Check

```bash
# Verify all test files import correctly
python -c "from tests.smoke import fixtures, helpers"
python -c "from tests.smoke.test_sidebar_routes_admin import *"
python -c "from tests.smoke.test_sidebar_routes_agent import *"
python -c "from tests.smoke.test_hq_sidebar import *"
python -c "from tests.smoke.test_core_workflows import *"
```

**Expected**: No errors

### Test 2: Fixture Creation

```bash
# Verify fixtures create test data correctly
python manage.py shell
```

```python
from tests.smoke.fixtures import SmokeTestFixtures
from inventory.business_kinds import BusinessKind

# Create test setup for Phones
setup = SmokeTestFixtures.create_complete_vertical_setup(BusinessKind.PHONES)

# Verify data
print(f"Business: {setup['business'].name}")
print(f"Location: {setup['location'].name}")
print(f"Admin: {setup['admin_user'].username}")
print(f"Agent: {setup['agent_user'].username}")
print(f"Product: {setup['product'].name if setup['product'] else 'N/A'}")

# Cleanup
setup['business'].delete()
exit()
```

**Expected**: All objects created successfully

### Test 3: Run One Test Class

```bash
# Run Phones admin tests only
pytest tests/smoke/test_sidebar_routes_admin.py::TestSidebarRoutesAdminPhones -v
```

**Expected**:
```
tests/smoke/test_sidebar_routes_admin.py::TestSidebarRoutesAdminPhones::test_phones_admin_sidebar_urls_resolve PASSED
tests/smoke/test_sidebar_routes_admin.py::TestSidebarRoutesAdminPhones::test_phones_admin_sidebar_urls_load PASSED

==================== 2 passed in 3.45s ====================
```

### Test 4: Run Full Django Smoke Suite

```bash
# Run all Django smoke tests
pytest tests/smoke/ -v --tb=short
```

**Expected**: 30+ tests pass in < 60 seconds

**Common Issues**:

- **Import errors**: Run migrations (`python manage.py migrate`)
- **Database errors**: Check `DJANGO_SETTINGS_MODULE=cc.settings`
- **Fixture errors**: Check that `conftest.py` has `unique_slug` helper

---

## Step 2: Validate Playwright E2E Tests (Slow - 10 minutes)

### Prerequisite: Create Test Users

```bash
# Create test users manually (one-time setup)
python manage.py shell
```

```python
from tests.smoke.fixtures import SmokeTestFixtures
from inventory.business_kinds import BusinessKind

# Create complete setups for all verticals
for kind in [BusinessKind.PHONES, BusinessKind.PHARMACY, BusinessKind.CLOTHING, BusinessKind.LIQUOR, BusinessKind.GYM]:
    print(f"Creating {kind}...")
    setup = SmokeTestFixtures.create_complete_vertical_setup(kind, f"Test {kind} E2E")
    print(f"  Admin: {setup['admin_user'].username} / testpass123")
    print(f"  Agent: {setup['agent_user'].username} / testpass123")

# Create superuser for HQ tests
superuser = SmokeTestFixtures.create_superuser()
print(f"Superuser: {superuser.username} / testpass123")

exit()
```

### Test 1: Start Django Server

```bash
# Terminal 1: Start server
python manage.py runserver
```

Wait for: `Starting development server at http://127.0.0.1:8000/`

### Test 2: Test Playwright Helper Functions

```bash
# Terminal 2: Test Playwright imports
python -c "from tests.e2e.helpers import PlaywrightHelper"
python -c "from tests.e2e.conftest import browser, context, page, base_url"
```

**Expected**: No errors

### Test 3: Run One Playwright Test

```bash
# Run Phones admin E2E test (in Terminal 2)
pytest tests/e2e/test_sidebar_clicks_admin.py::TestAdminSidebarClicksPhones -v --headed
```

**Expected**:
- Browser opens
- Logs into Phones dashboard
- Clicks each sidebar link
- Test passes

### Test 4: Run Full Playwright Suite (Headless)

```bash
# Run all E2E tests headless (in Terminal 2)
pytest tests/e2e/ -v --tb=short
```

**Expected**: 11 tests pass in ~5-10 minutes

**Common Issues**:

- **Login fails**: Verify test users exist with password `testpass123`
- **Timeout errors**: Increase timeout in `conftest.py` or check server is running
- **Element not found**: Sidebar may not have loaded; check selector `.cc-sidebar`

---

## Step 3: Validate CI Integration

### Test 1: Validate Workflow File

```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('.github/workflows/smoke-tests.yml'))"
```

**Expected**: No errors

### Test 2: Simulate CI Run (Local)

```bash
# Set CI environment variables
export DJANGO_SETTINGS_MODULE=cc.settings
export POSTGRES_DB=circuitcity
export POSTGRES_USER=ccuser
export POSTGRES_PASSWORD=testpassword
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432

# Run migrations
python manage.py migrate --noinput

# Run Django smoke tests (as CI would)
pytest tests/smoke/ -v --tb=short -m "not e2e"
```

**Expected**: All tests pass

### Test 3: Push to GitHub

```bash
# Commit all changes
git add .
git commit -m "Add comprehensive smoke tests for all verticals

- Django test client smoke tests (fast route validation)
- Playwright E2E smoke tests (true UI click tests)
- Test fixtures and helpers
- CI/CD integration via GitHub Actions
- Complete user journey documentation

Covers all 5 verticals (Phones, Pharmacy, Clothing, Liquor, Gym) + HQ platform.
Tests 144 sidebar links (96 Admin + 48 Agent).
Validates role-based access control and core workflows.
"

# Push to GitHub
git push origin <your-branch>
```

**Expected**: GitHub Actions runs smoke tests automatically

---

## Step 4: Validate Documentation

### Test 1: Check Documentation Exists

```bash
# Verify documentation files
ls -lh docs/user_journeys_all_verticals.md
ls -lh tests/smoke/README.md
ls -lh SMOKE_TESTS_IMPLEMENTATION_SUMMARY.md
```

**Expected**: All files exist and are > 10 KB

### Test 2: Read Documentation

```bash
# Open in editor or browser
cat docs/user_journeys_all_verticals.md | head -n 50
cat tests/smoke/README.md | head -n 50
```

**Expected**: Well-formatted Markdown with clear structure

---

## Step 5: Final Validation Checklist

Run through this checklist to confirm everything works:

- [ ] Django smoke tests run and pass (`pytest tests/smoke/`)
- [ ] Playwright tests run and pass (`pytest tests/e2e/`) with server running
- [ ] Test users created for all verticals
- [ ] Fixtures create data correctly
- [ ] CI workflow file is valid YAML
- [ ] Documentation is complete and readable
- [ ] All TODO items marked as completed
- [ ] Code committed and pushed to GitHub

---

## Expected Test Output Summary

### Django Smoke Tests

```
==================== test session starts ====================
platform linux -- Python 3.12.0, pytest-8.3.2, pluggy-1.5.0
rootdir: /path/to/circuitcity_clean
plugins: django-4.8.0, cov-5.0.0
collected 32 items

tests/smoke/test_sidebar_routes_admin.py .......... [ 31%]
tests/smoke/test_sidebar_routes_agent.py .......... [ 62%]
tests/smoke/test_hq_sidebar.py ...                 [ 71%]
tests/smoke/test_core_workflows.py .........       [100%]

==================== 32 passed in 45.23s ====================
```

### Playwright E2E Tests

```
==================== test session starts ====================
platform linux -- Python 3.12.0, pytest-8.3.2, pluggy-1.5.0
rootdir: /path/to/circuitcity_clean
plugins: django-4.8.0, playwright-1.48.0
collected 11 items

tests/e2e/test_sidebar_clicks_admin.py ......      [ 54%]
tests/e2e/test_sidebar_clicks_agent.py .....       [100%]

==================== 11 passed in 8:32.15 ====================
```

---

## Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'tests.smoke'`

**Solution**: Ensure you're in the project root directory and `tests/smoke/__init__.py` exists

### Issue: `django.db.utils.OperationalError: connection to server failed`

**Solution**: Check PostgreSQL is running or use SQLite for tests

### Issue: `playwright._impl._errors.TimeoutError: Timeout 5000ms exceeded`

**Solution**:
1. Increase timeout in `tests/e2e/helpers.py`
2. Ensure Django server is running on `http://localhost:8000`
3. Check that test users exist

### Issue: `NoReverseMatch at /path/ - Reverse for 'some_url' not found`

**Solution**: Ensure URL pattern exists in `urls.py` and matches the name in `get_vertical_sidebar_items()`

### Issue: GitHub Actions failing

**Solution**:
1. Check workflow file syntax
2. Verify all dependencies in `requirements-dev.txt`
3. Check PostgreSQL service configuration in workflow

---

## Success Criteria

✅ **Django smoke tests**: All pass in < 60 seconds  
✅ **Playwright tests**: All pass in < 10 minutes  
✅ **CI integration**: Workflow runs successfully  
✅ **Documentation**: Complete and readable  
✅ **Test coverage**: 144 sidebar links tested  

---

**All tests passing? Great! You've successfully validated the smoke test implementation.** 🎉

Now commit and push to GitHub, and watch the CI pipeline validate your work automatically.

