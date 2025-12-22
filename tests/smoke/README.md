# Smoke Tests - Complete Regression Protection

This directory contains **comprehensive smoke tests** for the Circuit City / Emajinet SaaS platform.

## Purpose

These tests provide **complete regression protection** by validating that:

1. ✅ **All sidebar navigation links work** (no 500 errors, no NoReverseMatch)
2. ✅ **Role-based access control functions** (agents can't access manager-only pages)
3. ✅ **Core workflows operate correctly** (stock-in, sell, dashboard updates)
4. ✅ **All verticals are stable** (phones, pharmacy, clothing, liquor, gym)
5. ✅ **HQ platform admin features work**

## Test Layers

We implement **two complementary test layers**:

### Layer 1: Django Test Client Smoke Tests (Fast)

**Location**: `tests/smoke/test_sidebar_routes_*.py`, `test_hq_sidebar.py`, `test_core_workflows.py`

**Purpose**: Fast route validation using Django's test client

**What it tests**:
- URL resolution (no `NoReverseMatch`)
- HTTP status codes (no 500 errors)
- Basic access control (agents can't access manager pages)
- Template rendering (no template errors)

**Run with**:
```bash
pytest tests/smoke/ -v
```

**Speed**: ~30-60 seconds for all verticals

### Layer 2: Playwright E2E Smoke Tests (Comprehensive)

**Location**: `tests/e2e/test_sidebar_clicks_*.py`

**Purpose**: True UI click regression protection

**What it tests**:
- Real browser navigation (clicks every sidebar link)
- JavaScript-rendered content
- Dynamic UI behaviors
- Complete page load verification
- Screenshot capture on failures

**Run with**:
```bash
# Start Django dev server first
python manage.py runserver

# In another terminal:
pytest tests/e2e/ -v
```

**Speed**: ~5-10 minutes for all verticals (requires browser)

## Test Coverage Matrix

| Vertical | Admin Links | Agent Links | Django Tests | Playwright Tests | Core Workflows |
|----------|-------------|-------------|--------------|------------------|----------------|
| **Phones** | 18 | 10 | ✅ | ✅ | ✅ |
| **Pharmacy** | 17 | 10 | ✅ | ✅ | ✅ |
| **Clothing** | 18 | 10 | ✅ | ✅ | ✅ |
| **Liquor** | 18 | 11 | ✅ | ✅ | ✅ |
| **Gym** | 14 | 7 | ✅ | ✅ | ✅ |
| **HQ Platform** | 11 | N/A | ✅ | ✅ | ✅ |

## File Structure

```
tests/smoke/
├── __init__.py              # Package init
├── README.md                # This file
├── fixtures.py              # Test data factories
├── helpers.py               # Django test helpers
├── test_sidebar_routes_admin.py   # Admin sidebar routes (Django)
├── test_sidebar_routes_agent.py   # Agent sidebar routes (Django)
├── test_hq_sidebar.py       # HQ platform routes (Django)
└── test_core_workflows.py   # Business logic smoke tests

tests/e2e/
├── __init__.py              # Package init
├── conftest.py              # Playwright fixtures
├── helpers.py               # Playwright helpers
├── test_sidebar_clicks_admin.py   # Admin UI clicks (Playwright)
└── test_sidebar_clicks_agent.py   # Agent UI clicks (Playwright)
```

## Running Tests

### Quick Start (Django only - recommended for CI)

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run all Django smoke tests
pytest tests/smoke/ -v

# Run specific vertical
pytest tests/smoke/test_sidebar_routes_admin.py::TestSidebarRoutesAdminPhones -v

# Run specific test
pytest tests/smoke/test_sidebar_routes_admin.py -k "phones_admin_sidebar_urls_load" -v
```

### Full Suite (Django + Playwright)

```bash
# Install Playwright browsers (one-time setup)
playwright install chromium

# Start Django dev server (terminal 1)
python manage.py runserver

# Create test users (one-time setup)
# You'll need to create test users manually or via fixtures
python manage.py shell
>>> from tests.smoke.fixtures import SmokeTestFixtures
>>> from inventory.business_kinds import BusinessKind
>>> for kind in [BusinessKind.PHONES, BusinessKind.PHARMACY, BusinessKind.CLOTHING, BusinessKind.LIQUOR, BusinessKind.GYM]:
...     SmokeTestFixtures.create_complete_vertical_setup(kind, f"Test {kind} Business")

# Run Playwright tests (terminal 2)
pytest tests/e2e/ -v

# Run with visible browser (for debugging)
pytest tests/e2e/ -v --headed
```

### CI/CD Integration

Smoke tests run automatically on every push/PR via GitHub Actions:

- **Django smoke tests**: `.github/workflows/smoke-tests.yml`
- **Fast execution**: Runs in parallel with unit tests
- **Failure artifacts**: Screenshots uploaded on Playwright failures

## Test Data Setup

Tests use **deterministic test fixtures** via `SmokeTestFixtures`:

```python
from tests.smoke.fixtures import SmokeTestFixtures
from inventory.business_kinds import BusinessKind

# Create complete setup for a vertical
setup = SmokeTestFixtures.create_complete_vertical_setup(
    BusinessKind.PHONES, "Test Phones Business"
)

# Returns: {
#   'business': Business object,
#   'location': Location object,
#   'admin_user': User (manager role),
#   'admin_password': 'testpass123',
#   'agent_user': User (agent role),
#   'agent_password': 'testpass123',
#   'product': MerchProduct (if applicable),
# }
```

## Adding New Tests

### Adding a New Vertical

1. **Add sidebar items** in `inventory/utils_verticals.py`:
   ```python
   def get_vertical_sidebar_items(business_kind: str) -> list[dict]:
       if business_kind == "my_new_vertical":
           return [
               {"section": "MAIN", "key": "dashboard", "url": "my_vertical:dashboard", ...},
               # ... more items
           ]
   ```

2. **Add Django smoke test**:
   - Copy `TestSidebarRoutesAdminPhones` class
   - Rename to `TestSidebarRoutesAdminMyVertical`
   - Update `business_kind` in setup

3. **Add Playwright test**:
   - Copy `TestAdminSidebarClicksPhones` class
   - Update URLs and test names

4. **Update documentation**:
   - Add row to coverage matrix in `docs/user_journeys_all_verticals.md`
   - Add test class to this README

### Adding a New Sidebar Link

No code changes needed! Tests automatically detect new sidebar links from `get_vertical_sidebar_items()`.

Just ensure:
1. URL is added to `get_vertical_sidebar_items()`
2. Named URL can be reversed (no `NoReverseMatch`)
3. View returns HTTP 200 or 302

## Debugging Failures

### Django Test Failures

```bash
# Run with verbose output
pytest tests/smoke/ -vv

# Run with full traceback
pytest tests/smoke/ --tb=long

# Run specific failing test
pytest tests/smoke/test_sidebar_routes_admin.py::TestSidebarRoutesAdminPhones::test_phones_admin_sidebar_urls_load -vv
```

### Playwright Test Failures

```bash
# Run with visible browser
pytest tests/e2e/ --headed

# Take screenshots on failure (automatic)
# Saved to: screenshots/*.png

# Run in slow motion (for debugging)
pytest tests/e2e/ --headed --slowmo 1000

# Run specific test with debugging
pytest tests/e2e/test_sidebar_clicks_admin.py::TestAdminSidebarClicksPhones::test_phones_admin_clicks_all_sidebar_links --headed
```

### Common Issues

**Issue**: `NoReverseMatch` in URL resolution

**Fix**: Ensure named URL is defined in `urls.py` and matches the `url` field in `get_vertical_sidebar_items()`

---

**Issue**: HTTP 500 on sidebar link

**Fix**: Check view logic, template syntax, and context variables

---

**Issue**: Agent can access manager-only page

**Fix**: Add `@require_manager` decorator or check `IS_MANAGER` in template

---

**Issue**: Playwright login fails

**Fix**: Ensure test users exist with correct credentials (`testpass123`)

## Acceptance Criteria

### ✅ PASS Conditions

1. All sidebar links return HTTP 200 or 302
2. No "Server Error (500)" text in responses
3. No `NoReverseMatch` exceptions
4. No template syntax errors
5. Agents cannot access manager-only pages
6. Core workflows (stock-in, sell) complete successfully

### ❌ FAIL Conditions

1. Any 500 error on sidebar navigation
2. `NoReverseMatch` when reversing named URLs
3. Template does not exist errors
4. Agent accessing manager-only page without redirect/403
5. Stock-in does not increase stock count
6. Sell does not create sale record

## Performance Targets

- **Django smoke tests**: < 60 seconds for all verticals
- **Playwright smoke tests**: < 10 minutes for all verticals
- **Total CI time**: < 15 minutes (Django + Playwright in parallel)

## Maintenance

**Update this suite when**:

1. **New vertical added**: Add test classes for admin + agent
2. **New sidebar link added**: Tests auto-detect, just verify URL resolves
3. **URL pattern changes**: Update `get_vertical_sidebar_items()` and test data
4. **Role logic changes**: Update access control tests

**Review frequency**: Before every major release

---

**Questions?** Contact the Engineering Team or see `docs/user_journeys_all_verticals.md` for complete user journey specifications.

