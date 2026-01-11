# tests/e2e/conftest.py
"""
Pytest fixtures for Playwright E2E tests.

CRITICAL: These tests require Playwright browsers to be installed.
If browsers are missing, tests will be skipped with a clear message.
Run: python -m playwright install
"""
import os
import pytest


def _playwright_browsers_installed() -> bool:
    """
    Check if Playwright browsers are installed.
    Returns True if chromium is available, False otherwise.
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Try to get the executable path - this will fail if not installed
            chromium_path = p.chromium.executable_path
            if chromium_path and os.path.exists(chromium_path):
                return True
            # If path doesn't exist or is None, browsers aren't installed
            return False
    except Exception:
        return False


# Check once at module load time
_PLAYWRIGHT_AVAILABLE = None


def playwright_available() -> bool:
    """Lazy check for Playwright availability."""
    global _PLAYWRIGHT_AVAILABLE
    if _PLAYWRIGHT_AVAILABLE is None:
        _PLAYWRIGHT_AVAILABLE = _playwright_browsers_installed()
    return _PLAYWRIGHT_AVAILABLE


# Skip all e2e tests if Playwright browsers not installed
pytestmark = pytest.mark.skipif(
    not playwright_available(),
    reason="Playwright browsers not installed. Run: python -m playwright install"
)


# Only import Playwright if available to avoid import errors
if playwright_available():
    from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
else:
    # Stub types for type hints when Playwright not available
    sync_playwright = None
    Browser = object
    BrowserContext = object
    Page = object


@pytest.fixture(scope="session")
def browser():
    """
    Launch browser for entire test session.
    
    CRITICAL: This fixture skips all tests if Playwright browsers are not installed.
    """
    if not playwright_available():
        pytest.skip("Playwright browsers not installed. Run: python -m playwright install")
    
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            yield browser
            browser.close()
        except Exception as e:
            if "Executable doesn't exist" in str(e) or "not found" in str(e).lower():
                pytest.skip(f"Playwright Chromium not installed: {e}. Run: python -m playwright install")
            raise


@pytest.fixture
def context(browser: Browser) -> BrowserContext:
    """Create a new browser context for each test."""
    context = browser.new_context(
        viewport={'width': 1280, 'height': 720},
        ignore_https_errors=True,
    )
    yield context
    context.close()


@pytest.fixture
def page(context: BrowserContext) -> Page:
    """Create a new page for each test."""
    page = context.new_page()
    yield page
    page.close()


@pytest.fixture(scope="session")
def base_url():
    """
    Base URL for the application (update for your environment).
    
    Session-scoped to allow use by other session-scoped fixtures.
    """
    # Default to localhost:8000, can be overridden via env var
    import os
    return os.getenv('BASE_URL', 'http://localhost:8000')

