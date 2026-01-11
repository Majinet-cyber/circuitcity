# Critical Reliability Gate Tests

**MUST-PASS tests that block deployment if failing.**

## Overview

This folder contains the "bank-grade" reliability tests for the CircuitCity monorepo. These tests focus on:

1. **Core authentication flows** - Users can signup, login, logout
2. **Business bootstrap** - Businesses and locations can be created
3. **Dashboard accessibility** - All vertical dashboards load without 500 errors
4. **Stock management** - Products can be added to inventory
5. **Sales recording** - Sales can be recorded
6. **Permissions & scoping** - Multi-tenant isolation is enforced

## Running the Critical Suite

### Windows (PowerShell)
```powershell
.\scripts\test_critical.ps1
```

### Linux/Mac (Bash)
```bash
./scripts/test_critical.sh
```

### Manual
```bash
pytest -m critical --maxfail=1 -q
```

## Test Files

| File | Covers |
|------|--------|
| `test_01_auth_and_signup.py` | Signup, login, logout, OTP |
| `test_02_business_and_location_bootstrap.py` | Business/location creation, membership |
| `test_03_vertical_dashboards_no500.py` | All vertical dashboards load without 500 |
| `test_04_stock_add_core.py` | Stock/inventory add functionality |
| `test_05_sales_and_ledger_core.py` | Sales recording, ledger |
| `test_06_permissions_and_scoping.py` | Multi-tenant isolation, RBAC |

## Verticals Covered

Tests are parametrized across these core verticals:
- `phones` - Phones & Electronics
- `liquor` - Liquor / Bar
- `grocery` - Grocery / General
- `pharmacy` - Cosmetics & Pharmacy

(Other verticals like gym, farm, welding are tested separately due to different data models)

## Adding New Critical Tests

1. Create a test in this folder with the `@pytest.mark.critical` marker
2. Keep tests **deterministic** (no `sleep()`, use timezone-aware datetimes)
3. Keep tests **fast** (total suite should run in < 5 minutes)
4. Focus on **no-500 policy** - pages must not crash
5. Use existing fixtures from `conftest.py`

## Current Status

- **72 tests passing**
- **~34 seconds runtime**
- **< 5 minute target: ✅ Achieved**
