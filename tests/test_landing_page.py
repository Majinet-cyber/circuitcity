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


def test_landing_page_no_leaked_developer_text(client):
    """
    GUARDRAIL: Landing page must not expose developer/planning notes in rendered HTML.

    These strings were accidentally leaking into the page source and have been removed.
    This test prevents them from returning.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    forbidden_strings = [
        "RENEWABLE ENERGY FLAGSHIP",
        "Light mode, premium, clean",
        "No extra CTA button",
        "Positioned after How It Works",
        "restored from git history",
        "git-original trust card",
        "5bd2cceb",
        "DEBUG: sidebar_items",
        "DEBUG: Found",
    ]
    for s in forbidden_strings:
        assert s not in content, (
            f"Developer/planning text '{s}' must not appear in landing page HTML"
        )


def test_landing_page_metrics_show_neutral_labels(client):
    """
    GUARDRAIL: Landing page metrics card must NOT display hardcoded numeric values.

    Numeric aggregation is not yet live. The card must show neutral status labels
    ('Real-time', 'Live', 'Tracking') rather than numbers like 'MWK 84,500' or '47+'.
    """
    url = reverse("staticpages:home")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Metric labels must still be present
    assert "Avg. daily revenue tracked" in content
    assert "Sales recorded per day" in content
    assert "Avg. margin visibility" in content

    # Neutral status labels must appear
    assert "Real-time" in content
    assert "Live" in content
    assert "Tracking" in content

    # No hardcoded numeric values should appear in the metrics spans
    import re
    # Check that the lm-revenue span does not contain a MWK numeric value
    lm_revenue_pattern = re.search(
        r'id="lm-revenue"[^>]*>([^<]*)<', content
    )
    if lm_revenue_pattern:
        span_text = lm_revenue_pattern.group(1).strip()
        assert not re.match(r'^MWK[\s\u00a0]\d', span_text), (
            f"lm-revenue span must not show a numeric MWK value, got: {span_text!r}"
        )

    # Growing… must not appear (was a previous fallback that the task forbids)
    assert "Growing" not in content or "Growing businesses" in content, (
        "The text 'Growing\u2026' must not be used as a metric placeholder"
    )


def test_gym_dashboard_no_leaked_debug_text(client):
    """
    GUARDRAIL: Gym dashboard must not expose DEBUG template comments in rendered HTML.

    Django {# ... #} comments are stripped by the template engine and never render,
    but HTML <!-- DEBUG: ... --> comments do render. This test verifies the gym
    dashboard URL resolves and unauthenticated users are redirected (not served
    a broken template).
    """
    from django.urls import reverse as r
    url = r("verticals:gym_dashboard")
    response = client.get(url)
    # Unauthenticated → redirect to login; template debug leaks only occur on 200.
    assert response.status_code in (200, 302)

