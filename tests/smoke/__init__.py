# tests/smoke/__init__.py
"""
Smoke test suite for Circuit City / Emajinet SaaS.

This package contains automated smoke tests that validate:
- All sidebar navigation links load without errors
- URL resolution works for all verticals
- Critical user workflows (stock-in, sell) work end-to-end
- Role-based access control functions correctly

Tests are organized by:
- test_sidebar_routes_*.py: Django test client route validation (fast)
- test_sidebar_clicks_*.py: Playwright UI click tests (comprehensive)
- test_core_workflows.py: Business logic validation
- test_hq_sidebar.py: Platform admin tests
"""

