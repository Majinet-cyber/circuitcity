# tests/e2e/__init__.py
"""
End-to-end smoke tests using Playwright.

These tests simulate real user interactions:
- Click every sidebar link
- Verify pages load without errors
- Screenshot on failures for debugging

Run with:
    pytest tests/e2e/ --headed  # See browser
    pytest tests/e2e/           # Headless mode
"""

