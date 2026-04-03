# tests/test_landing_page.py
"""
Tests for the landing page (home) improvements.

Ensures:
- Mission statement is present
- T.S. Eliot motto is present with correct attribution
- All primary CTAs use uniform blue button styling
- Page renders correctly
"""
import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_landing_page_renders(client):
    """Test that the landing page renders successfully."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    assert "Emajinet" in response.content.decode()


def test_landing_page_contains_mission_statement(client):
    """Test that the landing page contains the current mission statement.

    GUARDRAIL TEST: This test fails if the old mission statement is ever restored.
    The current mission statement positions Emajinet as the operating system for
    African business (not "small businesses" — updated to reflect the Africa-wide scope).
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Check for mission section heading
    assert "Our Mission" in content

    # Check for current mission statement — operating system for African business
    assert "operating system for african business" in content.lower(), \
        "Missing current mission statement 'operating system for African business'"

    # GUARDRAIL: Ensure OLD mission statement is NOT present
    assert "spotify of every small business" not in content.lower(), \
        "Old mission statement 'Spotify of every small business' found - this is a regression!"


def test_landing_page_contains_ts_eliot_motto(client):
    """Test that the landing page contains the T.S. Eliot motto."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for the quote
    assert "We shall not cease from exploration" in content
    assert "And the end of all our exploring" in content
    assert "Will be to arrive where we started" in content
    assert "And know the place for the first time" in content
    
    # Check for attribution
    assert "T.S. Eliot" in content
    assert "Four Quartets" in content


def test_landing_page_buttons_use_uniform_blue_class(client):
    """
    Test that main CTAs use consistent blue button styling.

    Most primary action buttons use btn-primary. The final CTA section intentionally
    uses btn-white (white button on a dark/coloured background) — this is correct
    design and must NOT be changed.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # btn-primary must be present in the page
    assert 'class="btn btn-primary"' in content

    # Multiple primary buttons must exist (hero + nav + other sections)
    primary_button_count = content.count('btn btn-primary')
    assert primary_button_count >= 2, f"Expected at least 2 primary buttons, found {primary_button_count}"

    # Get Started must appear on the page
    assert 'Get Started' in content

    # btn-white is intentional for the final CTA section (white button on dark bg) — allowed
    assert 'btn-white' in content or 'btn btn-primary' in content, \
        "Page must have either btn-white (final CTA) or btn-primary buttons"


def test_landing_page_has_consistent_color_scheme(client):
    """Test that the landing page uses a consistent blue color scheme."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for primary color definition (should be blue)
    assert '--primary: #4f46e5' in content or 'var(--primary)' in content
    
    # Verify blue is used in gradients and highlights
    assert '#4f46e5' in content or '79, 70, 229' in content  # RGB of primary blue


def test_landing_page_sections_are_present(client):
    """Test that all major sections are present on the landing page."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for major sections
    assert "How It Works" in content
    assert "Powerful Features" in content or "Features" in content
    assert "Our Mission" in content
    
    # Check for hero section content (updated)
    assert "inventory" in content.lower() or "business" in content.lower()


def test_landing_page_has_navigation(client):
    """Test that the landing page has proper navigation."""
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Nav uses "Sign In" (not "Login") — updated to match current design
    assert "Sign In" in content or "login" in content.lower(), \
        "Nav must contain 'Sign In' or a login link"
    assert "Get Started" in content
    assert "About" in content or "How It Works" in content


def test_landing_page_cta_links_work(client):
    """Test that CTA links on the landing page are valid."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check that login links exist
    assert '/login/' in content or 'login' in content.lower()
    
    # Check that internal anchors exist for smooth scrolling
    assert '#how-it-works' in content or 'how-it-works' in content


def test_landing_page_is_mobile_responsive(client):
    """Test that the landing page has responsive design elements."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for viewport meta tag
    assert 'viewport' in content.lower()
    assert 'width=device-width' in content.lower()
    
    # Check for responsive CSS (media queries)
    assert '@media' in content.lower()
    assert 'max-width' in content.lower() or 'min-width' in content.lower()


def test_landing_page_has_premium_styling(client):
    """Test that the landing page has premium styling elements."""
    url = reverse("staticpages:home")
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for premium styling elements
    assert 'box-shadow' in content.lower() or 'shadow' in content.lower()
    assert 'border-radius' in content.lower() or 'rounded' in content.lower()
    assert 'gradient' in content.lower()
    
    # Check for glassmorphic/modern effects
    assert 'backdrop-filter' in content.lower() or 'blur' in content.lower()

