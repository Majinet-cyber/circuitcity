# tests/critical/__init__.py
"""
Critical Reliability Gate Tests

These tests are the MUST-PASS gate that prevents deployment if failing.
Run with: pytest -m critical --maxfail=1

All tests in this folder are marked @pytest.mark.critical and cover:
1. Auth & Signup - users can register and login
2. Business & Location Bootstrap - vertical setup works
3. Vertical Dashboards - no 500 errors on dashboard access
4. Stock Add - core inventory operations
5. Sales & Ledger - sales decrement stock, update ledger
6. Permissions & Scoping - cross-tenant isolation

RULES:
- No flaky tests allowed (quarantine with @pytest.mark.flaky if needed)
- No timing-sensitive code (no sleep(), use timezone-aware datetimes)
- Tests must be deterministic and stable
- Keep total suite runtime < 5 minutes
"""

