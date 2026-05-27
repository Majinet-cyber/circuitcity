# Critical Reliability Gate Tests

**MUST-PASS tests that block deployment if failing.**

## Overview

This folder contains the "bank-grade" reliability tests for the CircuitCity monorepo. These tests enforce:

1. **Core authentication flows** - Signup, login, logout, OTP verification
2. **Business bootstrap** - Businesses/locations for all 10 verticals
3. **Dashboard accessibility** - All vertical dashboards load without 500 errors
4. **Stock management** - Products added to inventory (Tier A only)
5. **Sales recording** - Sales recorded with financial invariants (Tier A only)
6. **Transaction atomicity** - No partial writes on failures (Tier A only)
7. **Security contracts** - Auth + CSRF enforcement (Tier A only)
8. **Multi-tenant isolation** - Business/location scoping enforced
9. **Performance guardrails** - N+1 query explosion detection (Tier A only)

---

## Vertical Tiers

### Tier A: Core/Mature (Full Testing)
| Vertical | Dashboard | Stock | Sales | Invariants | Notes |
|----------|-----------|-------|-------|------------|-------|
| `phones` | ✅ | ✅ (IMEI/serial) | ✅ | ✅ | Primary vertical |
| `liquor` | ✅ | ✅ (barcode) | ✅ | ✅ | |
| `grocery` | ✅ | ✅ (barcode) | ✅ | ✅ | |
| `pharmacy` | ✅ | ✅ (barcode) | ✅ | ✅ | |
| `clothing` | ✅ | ✅ (no-barcode) | ✅ | ✅ | Size/color variants |
| `gym` | ✅ | N/A | N/A | N/A | Membership-based |
| `hardware` | ✅ | ⚠️ xfail | ✅ | ✅ | Redirect loop on scan-in |
| `cement` | ✅ | ✅ (SKU) | ✅ | ✅ | |

### Tier B: New/Experimental (Minimal Testing)
| Vertical | Dashboard | Stock | Sales | Invariants | Notes |
|----------|-----------|-------|-------|------------|-------|
| `farm` | ✅ | — | — | — | Ledger-based, not traditional |
| `welding` | ✅ | — | — | — | Job-based invoicing |

**Tier B policy**: Only dashboard no-500 + auth/scoping tests. No deeper flows to avoid token/time waste on experimental verticals.

---

## Test Suites

| Suite | File | Runs On | What It Tests |
|-------|------|---------|---------------|
| Auth & Signup | `test_01_auth_and_signup.py` | All | Login, logout, signup |
| OTP Verification | `test_01b_otp_verify_enabled.py` | All | OTP email flow |
| Business Bootstrap | `test_02_business_and_location_bootstrap.py` | All | Business/location creation |
| Dashboard No-500 | `test_03_vertical_dashboards_no500.py` | **ALL** | Dashboard accessibility |
| Redirect Loop Detection | `test_04b_no_redirect_loops.py` | **CORE** | No infinite redirects |
| Stock Add | `test_04_stock_add_core.py` | **CORE** | Inventory operations |
| Sales & Ledger | `test_05_sales_and_ledger_core.py` | **CORE** | Sale recording |
| Financial Invariants | `test_05b_financial_invariants.py` | **CORE** | Money integrity |
| Transaction Atomicity | `test_05c_atomicity.py` | **CORE** | Rollback on failure |
| Permissions & Scoping | `test_06_permissions_and_scoping.py` | CORE + 1 New | Multi-tenant isolation |
| Security Contracts | `test_07_security_contracts.py` | **CORE** | Auth + CSRF |

---

## Financial Invariants Enforced (Tier A)

These invariants are tested in `test_05b_financial_invariants.py`:

1. **Stock non-negative**: Stock quantity >= 0 after valid sale
2. **Sale total matches line items**: `sale.total == sum(item.total_price)`
3. **Profit calculation**: `profit = selling_price - cost_price`
4. **Business scoping**: Products/sales only visible to owning business
5. **Location scoping**: Products/sales scoped to correct location
6. **Timestamps**: Sale records have valid created_at timestamp

---

## Known Bugs (xfail strict)

Known bugs are tracked with `@pytest.mark.xfail(strict=True)` - visible but don't block:

| Vertical | Bug | Endpoint | Test | Status |
|----------|-----|----------|------|--------|
| `hardware` | Redirect loop | `/inventory/scan-in/` | `test_04b_no_redirect_loops.py` | xfail strict |

**Policy**: When a bug is fixed, the xfail becomes xpass and CI fails, prompting removal of the xfail.

---

## Running the Critical Suite

### PR CI (Fast)
```bash
pytest -m critical --maxfail=1 -q --strict-markers --strict-config -W error
```

### Nightly CI (Full)
```bash
pytest -m critical -v --strict-markers --strict-config -W error -ra --durations=20
```

### Local (PowerShell)
```powershell
.\scripts\test_critical.ps1
```

### Local (Bash)
```bash
./scripts/test_critical.sh
```

### OTP Tests Only
```bash
ENABLE_EMAIL_OTP=1 pytest -m "critical and otp" -q
```

---

## OTP Testing

OTP tests are marked with `@pytest.mark.critical` + `@pytest.mark.otp`.

- **Local**: Set `ENABLE_EMAIL_OTP=1` environment variable
- **CI**: Separate step runs with `ENABLE_EMAIL_OTP=1`
- **Email backend**: Uses `locmem.EmailBackend` to capture OTP emails

---

## Strict Mode & Warnings Policy

### Enabled Options
- `--strict-markers`: Unknown markers cause errors
- `--strict-config`: Invalid config causes errors  
- `-W error`: Warnings treated as errors
- `PYTHONWARNINGS=error`: CI environment variable

### Allowed Warnings (Filtered)
```ini
# Third-party deprecation warnings (out of our control)
ignore::DeprecationWarning:reportlab.*
ignore::DeprecationWarning:anymail.*

# Django 6.0 deprecations (will be fixed before upgrade)
ignore:CheckConstraint.check is deprecated:django.utils.deprecation.RemovedInDjango60Warning
```

**Policy**: Filters are minimal and justified. All production-code warnings should be fixed.

---

## CI Configuration

### Database Parity
- **Production**: PostgreSQL (Render)
- **CI**: PostgreSQL 16 (GitHub Actions service)
- **Local**: SQLite (for speed) or PostgreSQL (for parity)

### PR CI Steps
1. **Critical tests** (quality gate): `pytest -m critical --maxfail=1 -W error`
2. **OTP tests** (with OTP enabled): `pytest -m "critical and otp" -W error`
3. **Full test suite** (after gate passes)

### Nightly CI
- Runs at 3:00 AM UTC
- Full test suite with `--durations=20`
- Reports slowest tests for optimization
- Checks xfail strict for fixed bugs

---

## Performance Guardrails

Dashboard tests include a lightweight query count check for CORE verticals:

- **Cap**: 80 queries per dashboard (generous)
- **Purpose**: Catch accidental N+1 explosions
- **Not**: Strict optimization enforcement

---

## Adding New Critical Tests

1. Add `@pytest.mark.critical` marker
2. Keep tests **deterministic** (no `sleep()`, timezone-aware datetimes)
3. Keep tests **fast** (total suite < 2 minutes locally)
4. Focus on **no-500 policy** - pages must not crash
5. Use `reverse()` for URL resolution (not hardcoded paths)
6. Use fixtures from `conftest.py`
7. For new verticals, add to Tier B initially

---

## Root Cause: Farm/Welding Tables

**Issue**: Previously, `django_db_use_migrations = False` caused pytest-django to use syncdb. Models in separate files (`models_farm.py`, `models_welding.py`) weren't registered.

**Fix**: Explicit imports in `inventory/models.py`:
```python
from .models_farm import FarmLedgerEntry, FarmCropSeason, ...
from .models_welding import WeldingMaterial, WeldingJob, ...
```

---

## Current Status

| Metric | Value |
|--------|-------|
| **Tests Passed** | 165 |
| **Tests Skipped** | 2 (OTP in non-OTP mode) |
| **Tests xfailed** | 3 (known hardware bugs) |
| **Runtime** | ~65 seconds (1:04) |
| **Target** | < 2 minutes locally ✅ |
| **Verticals Covered** | 10/10 dashboards |
| **Tier A Tests** | Dashboard + Stock + Sales + Invariants + Security |
| **Tier B Tests** | Dashboard only |

---

## Known xfails (Strict)

| Test | Reason | Status |
|------|--------|--------|
| `test_stock_add_no_redirect_loop[hardware]` | Redirect loop on scan-in | xfail |
| `test_sell_no_redirect_loop[hardware]` | Redirect loop on scan-sold | xfail |
| `test_hardware_stock_add_redirect_loop_is_known_bug` | Explicit tracker for hardware bug | xfail strict |

When these bugs are fixed, the xfail becomes xpass and CI fails, prompting removal of the xfail.

---

## Intentional Gaps

| Gap | Reason | Mitigation |
|-----|--------|------------|
| Hardware stock/sell | Known redirect loop bug | xfail strict, dashboard tested |
| OTP skipped in default mode | `ENABLE_EMAIL_OTP=False` | Separate CI step with OTP=1 |
| Farm/Welding deep flows | Tier B experimental | Dashboard + auth only |
| E2E signup wizard | Multi-step complexity | Covered by Cypress E2E |
