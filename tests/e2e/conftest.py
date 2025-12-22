# tests/e2e/conftest.py
"""
Pytest fixtures for Playwright E2E tests.
"""
import pytest
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page


@pytest.fixture(scope="session")
def browser():
    """Launch browser for entire test session."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


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


@pytest.fixture
def base_url():
    """Base URL for the application (update for your environment)."""
    # Default to localhost:8000, can be overridden via env var
    import os
    return os.getenv('BASE_URL', 'http://localhost:8000')

